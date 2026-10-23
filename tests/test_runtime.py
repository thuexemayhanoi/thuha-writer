"""V5 writer-session runtime: external evidence, prechecks and admission stay gated."""
import copy
import json
import os
import tempfile
import unittest
from unittest.mock import patch
from thuha.common import SITE, ROOT, digest, load, now
from thuha.store import LocalStore, GitHub
from thuha.coordinator import claim
from thuha.research import capture_external_source, intake
from thuha.runtime import kit, precheck, admit, cycle, link_catalogue
from thuha.cli import main
from test_factory import Fixture


def record(url, **override):
    value = {'url': url, 'fetcher': 'parallel-web-fetch', 'status': 'ok', 'fetched_at': now(),
             'title': 'Official page', 'content': ' '.join('evidence' + str(i) for i in range(80))}
    value.update(override)
    return value


class ExternalSourceTests(Fixture):
    def test_successful_external_fetch_becomes_labelled_snapshot(self):
        url = 'https://example.org/official-notice/'
        with patch('thuha.research.safe_public_url', lambda u: u):
            out = capture_external_source(self.store, url, record(url))
        snapshot = self.store.get_document(out['document'])
        self.assertEqual(snapshot['capture_method'], 'external-fetcher')
        self.assertEqual(snapshot['http_status'], 200)
        self.assertEqual(snapshot['url'], url)

    def test_failed_thin_mismatched_or_stale_records_are_rejected(self):
        url = 'https://example.org/official-notice/'
        bad = [record(url, status='error', error='HTTP 404'), record(url, content='too short'),
               record('https://example.org/other/'), record(url, fetched_at='2020-01-01T00:00:00+00:00'),
               record(url, fetcher='imagination')]
        with patch('thuha.research.safe_public_url', lambda u: u):
            for value in bad:
                with self.assertRaises(ValueError):
                    capture_external_source(self.store, url, value)


class RuntimeTests(Fixture):
    def test_kit_is_read_only_and_lists_only_live_targets(self):
        intake(self.store, [self.candidate()], self.inv)
        before = copy.deepcopy(self.store.read())
        self.inv['items'].append({'id': 3, 'url': SITE + '/dead/', 'slug': 'dead', 'title': 'Dead', 'type': 'posts',
                                  'canonical': SITE + '/dead/', 'search_intent': 'UNREVIEWED', 'content_signature': [],
                                  'public_check': {'http_status': 404}})
        value = kit(self.store.read(), self.inv, 'TH-EN-0001', self.policy, self.business)
        self.assertEqual(self.store.read(), before)
        # English topic: English live targets only (the Vietnamese page and post are never offered), dead URLs excluded.
        self.assertEqual({x['id'] for x in value['internal_link_targets']}, {1, 2})
        self.assertEqual([m['id'] for m in value['featured_media_options']], [50])
        self.assertEqual(value['category_ancestry'][-1]['id'], 20)
        self.assertEqual(value['article_language_value'], 'en-US')
        self.assertEqual(value['blockers'], [])

    def test_vietnamese_kit_offers_only_vietnamese_targets_and_reports_missing_media(self):
        intake(self.store, [self.candidate(1, 'vi')], self.inv)
        value = kit(self.store.read(), self.inv, 'TH-VI-0001', self.policy, self.business)
        self.assertEqual({x['id'] for x in value['internal_link_targets']}, {3, 4})
        self.assertEqual([m['id'] for m in value['featured_media_options']], [51])
        self.assertEqual(value['article_language_value'], 'vi')
        self.assertTrue(any('tiếng Việt' in rule for rule in value['rules']))
        self.assertEqual(value['minimum_length']['unit'], 'syllables')
        english_only = copy.deepcopy(self.inv)
        english_only['media'] = [m for m in english_only['media'] if m['id'] == 50]
        blocked = kit(self.store.read(), english_only, 'TH-VI-0001', self.policy, self.business)
        self.assertEqual(blocked['featured_media_options'], [])
        self.assertTrue(blocked['blockers'][0].startswith('NEEDS_MEDIA'))

    def test_precheck_matches_qa_without_consuming_repairs(self):
        topic, article, sub = self.ready()
        state = self.store.read()
        before = copy.deepcopy(state)
        broken = dict(article); broken['body_html'] += '<p>we personally tested this</p>'
        out = precheck(self.store, state, self.inv, topic['topic_id'], broken, self.policy, self.business)
        self.assertIn('UNVERIFIED_BUSINESS_OR_FIRSTHAND_CLAIM', out['hard_fails_excluding_review'])
        clean = precheck(self.store, state, self.inv, topic['topic_id'], article, self.policy, self.business)
        self.assertEqual(clean['hard_fails_excluding_review'], [])
        self.assertTrue(clean['would_pass_after_review'])
        self.assertEqual(self.store.read(), before)
        self.assertEqual(self.store.read()['submissions'][topic['topic_id']]['repair_count'], 0)

    def test_admit_requires_records_for_every_source_and_rejects_batch_on_collision(self):
        url = 'https://example.org/official/'
        base = self.candidate(1); base['sources'] = [{'url': url, 'supports': 'Official notice describing the destination entity.'}]
        base['intent_review'] = {'verdict': 'DISTINCT', 'rationale': 'No existing guide covers this focal question.'}
        with patch('thuha.research.safe_public_url', lambda u: u):
            with self.assertRaises(ValueError):
                admit(self.store, self.inv, [base], 'claude-researcher', {})
            self.assertEqual(self.store.read()['topics'], {})
            admitted = admit(self.store, self.inv, [base], 'claude-researcher', {url: record(url)})
            self.assertEqual(admitted, ['TH-EN-0001'])
            stored = self.store.read()['topics']['TH-EN-0001']
            self.assertEqual(stored['intent_review']['inventory_sha256'], digest(self.inv))
            self.assertEqual(stored['intent_review']['reviewer_id'], 'claude-researcher')
            dup = self.candidate(2); dup['proposed_title'] = base['proposed_title']
            dup['sources'] = base['sources']; dup['intent_review'] = base['intent_review']
            with self.assertRaises(ValueError):
                admit(self.store, self.inv, [dup], 'claude-researcher', {url: record(url)})
            self.assertEqual(len(self.store.read()['topics']), 1)

    def test_admit_checks_extra_queue_from_other_publisher(self):
        url = 'https://example.org/official/'
        base = self.candidate(1); base['sources'] = [{'url': url, 'supports': 'Official notice describing the destination entity.'}]
        base['intent_review'] = {'verdict': 'DISTINCT', 'rationale': 'No existing guide covers this focal question.'}
        other = [{'proposed_title': base['proposed_title'], 'search_intent': 'different', 'proposed_url': SITE + '/elsewhere/'}]
        with patch('thuha.research.safe_public_url', lambda u: u):
            with self.assertRaises(ValueError):
                admit(self.store, self.inv, [base], 'claude-researcher', {url: record(url)}, extra_queue=other)

    def test_cycle_counts_only_receipts_as_verified(self):
        topic, article, sub = self.ready()
        value = cycle(self.store.read(), self.inv, load(ROOT / 'config/release.json'))
        self.assertEqual((value['row']['LIVE EN'], value['row']['LIVE VI']), (2, 1))
        self.assertEqual(value['row']['FACTORY VERIFIED'], 0)
        self.assertEqual(value['row']['QA PASS'], 1)
        self.assertEqual(value['row']['PUBLISHED'], 0)
        # 500 per language: the goal is no longer a single 2,000-post total.
        self.assertEqual((value['row']['REMAINING VI'], value['row']['REMAINING EN']), (499, 498))
        self.assertIn('REMAINING VI 499', value['line'])
        unknown = dict(self.inv, language_source='public-rest-unverified')
        self.assertEqual(cycle(self.store.read(), unknown, load(ROOT / 'config/release.json'))['row']['LIVE VI'], 'UNKNOWN')

    def test_link_catalogue_excludes_canonical_mismatch(self):
        self.inv['items'][1]['public_check'] = {'http_status': 200, 'canonicals': [SITE + '/elsewhere/']}
        self.assertEqual([x['id'] for x in link_catalogue(self.inv, 'en')], [1])
        self.assertEqual([x['id'] for x in link_catalogue(self.inv, 'vi')], [4, 3])


class TokenFallbackTests(unittest.TestCase):
    def test_github_token_fallback_is_used_only_when_thuha_token_absent(self):
        with patch.dict(os.environ, {'THUHA_GITHUB_TOKEN': '', 'GITHUB_TOKEN': 'harness'}, clear=False):
            self.assertEqual(GitHub().token, 'harness')
        with patch.dict(os.environ, {'THUHA_GITHUB_TOKEN': 'dedicated', 'GITHUB_TOKEN': 'harness'}, clear=False):
            self.assertEqual(GitHub().token, 'dedicated')
        with patch.dict(os.environ, {'THUHA_GITHUB_TOKEN': '', 'GITHUB_TOKEN': ''}, clear=False):
            with self.assertRaises(ValueError):
                GitHub()


class CliRuntimeTests(Fixture):
    def test_cli_precheck_reports_without_mutation(self):
        topic, article, sub = self.ready()
        inventory = os.path.join(self.temp.name, 'inv.json'); json.dump(self.inv, open(inventory, 'w'))
        draft = os.path.join(self.temp.name, 'a.json'); json.dump(article, open(draft, 'w'))
        before = copy.deepcopy(self.store.read())
        with patch('sys.stdout'):
            code = main(['--state-dir', self.temp.name, '--inventory', inventory, 'precheck', '--topic-id', topic['topic_id'], '--file', draft])
        self.assertEqual(code, 0)
        self.assertEqual(self.store.read(), before)

    def test_reviewer_roster_contains_no_writer_identity(self):
        policy = load(ROOT / 'config/qa.json')
        self.assertTrue(policy['trusted_reviewers'])
        self.assertTrue(all(r.startswith('claude-editorial') for r in policy['trusted_reviewers']))
        self.assertTrue(policy['semantic_review_required'])


if __name__ == '__main__':
    unittest.main()
