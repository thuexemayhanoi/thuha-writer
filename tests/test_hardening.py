"""Regression tests for defects found by the independent review: each one failed before its fix."""
import copy
import io
import json
import os
import unittest
import urllib.error
from unittest.mock import patch
import test_factory as tf
from thuha import htmlpolicy, quota
from thuha.adapter import validate_payload, build_payload
from thuha.common import SITE, digest, now, ROOT
from thuha.coordinator import claim, submit
from thuha.http import NetworkError, error_code
from thuha.language import TOPIC_ID, LEGACY_TOPIC_ID
from thuha.pipeline import remaining_budget
from thuha.publisher import Publisher, idempotency_key
from thuha.quality import evaluate
from thuha.research import refill, intake
from thuha.store import initial, migrate, validate

VECTORS = json.load(open(ROOT / 'tests/fixtures/html-policy-vectors.json', encoding='utf-8'))
MARKER = '<!-- thuha:v5 topic=TH-VI-0001 sha256=' + 'b' * 64 + ' -->'


def payload(**over):
    base = build_payload({'topic_id': 'TH-VI-0001', 'language': 'vi', 'category_id': 152},
                         {'title': 'Tiêu đề rõ ràng', 'body_html': '<p>Nội dung.</p>', 'featured_media': 51, 'seo_title': 'Tiêu đề SEO',
                          'meta_description': 'Mô tả ngắn gọn.', 'focus_keyword': 'từ khóa'}, 'a' * 64, MARKER, 'bai-viet-moi')
    base.update(over)
    return base


class HtmlPolicyTests(unittest.TestCase):
    def test_vectors(self):
        for html in VECTORS['ok']:
            self.assertEqual(htmlpolicy.violations(html), [], html)
        for html in VECTORS['bad']:
            self.assertTrue(htmlpolicy.violations(html), html)

    def test_qa_refuses_the_bypasses_the_old_regex_missed_and_accepts_ordinary_prose(self):
        class Q(tf.Fixture):
            def runTest(self):pass
        q = Q();q.setUp()
        try:
            t, a, s = q.ready('en')
            for bad in ('<svg/onload=alert(1)>', '<img src="x"onerror=alert(1)>', '<a href="&#106;avascript:alert(1)">x</a>'):
                mutated = copy.deepcopy(a);mutated['body_html'] += bad
                failures = evaluate(mutated, t, dict(s, article_sha=digest(mutated)), q.inv, q.policy, q.store)['hard_fails']
                self.assertIn('UNSAFE_OR_DUPLICATE_SCHEMA_HTML', failures, bad)
            prose = copy.deepcopy(a);prose['body_html'] += '<p>JavaScript: a language, and one = two.</p>'
            self.assertNotIn('UNSAFE_OR_DUPLICATE_SCHEMA_HTML', evaluate(prose, t, dict(s, article_sha=digest(prose)), q.inv, q.policy, q.store)['hard_fails'])
        finally:
            q.temp.cleanup()

    def test_seo_fields_must_survive_an_seo_plugins_re_sanitising(self):
        class Q(tf.Fixture):
            def runTest(self):pass
        q = Q();q.setUp()
        try:
            t, a, s = q.ready('en')
            for field, value, code in (('seo_title', 'Two  spaces here in the title for a quiet Hanoi day', 'SEO_TITLE_NOT_CANONICAL_PLAIN_TEXT'),
                                       ('meta_description', '<b>Markup</b> in a description that is long enough to look plausible to a reader here', 'META_DESCRIPTION_NOT_CANONICAL_PLAIN_TEXT'),
                                       ('focus_keyword', 'walk "plan" 1', 'FOCUS_KEYWORD_HAS_QUOTES')):
                m = copy.deepcopy(a);m[field] = value
                self.assertIn(code, evaluate(m, t, dict(s, article_sha=digest(m)), q.inv, q.policy, q.store)['hard_fails'], field)
        finally:
            q.temp.cleanup()


class PayloadContractTests(unittest.TestCase):
    def test_a_valid_payload_passes(self):
        validate_payload(payload())

    def test_limits_are_bytes_not_characters(self):
        # 70,000 Vietnamese characters of ~3 bytes each exceed 200,000 bytes although they are far fewer characters.
        with self.assertRaisesRegex(ValueError, 'byte limit'):validate_payload(payload(content='<p>' + 'ế' * 70000 + '</p>\n' + MARKER))
        with self.assertRaisesRegex(ValueError, 'byte limit'):validate_payload(payload(title='đ' * 160))

    def test_everything_the_plugin_refuses_is_refused_before_a_slot_is_spent(self):
        for name, bad in {
            'legacy ID is English only': payload(topic_id='TH-000001'),
            'unicode digits': payload(topic_id='TH-VI-١٢٣٤'),
            'padded title': payload(title='Hai  dấu cách'),
            'markup in seo': payload(seo={'title': '<b>x</b>', 'description': 'd', 'focus_keyword': 'k'}),
            'marker for another topic': payload(marker=MARKER.replace('0001', '0002')),
            'html violation': payload(content='<svg/onload=1>' + '\n' + MARKER),
            'content not ending in marker': payload(content='<p>x</p>'),
            'upper-case slug': payload(slug='Bai-Viet'),
        }.items():
            with self.subTest(name), self.assertRaises(ValueError):validate_payload(bad)

    def test_topic_ids_and_the_submit_limit_use_ascii_digits_and_bytes(self):
        self.assertIsNone(TOPIC_ID.fullmatch('TH-VI-١٢٣٤'));self.assertIsNone(LEGACY_TOPIC_ID.fullmatch('TH-٠٠٠٠٠١'))

        class S(tf.Fixture):
            def runTest(self):pass
        f = S();f.setUp()
        try:
            topic = f.candidate(1, 'vi');intake(f.store, [topic], f.inv)
            lease = claim(f.store, 'session-test', 'writer-fixture')
            article = f.article_for(topic);article['body_html'] = '<p>' + 'ế' * 70000 + '</p>'
            with self.assertRaisesRegex(ValueError, 'too large'):submit(f.store, lease['slot'], lease['session'], lease['fence'], article)
        finally:
            f.temp.cleanup()


class ClosedIntentTests(tf.PublisherBase):
    def test_a_payload_the_plugin_would_refuse_never_reserves_anything(self):
        p, tid = self.publisher('vi')
        real = build_payload
        with patch('thuha.publisher.build_payload', side_effect=lambda *a: dict(real(*a), post_status='publish')):
            with self.assertRaises(ValueError):self.publish(p, tid)
        state = self.store.read()
        self.assertEqual(state['intents'], {});self.assertEqual(state['topics'][tid]['status'], 'READY');self.assertEqual(self.client.posts, [])

    def test_a_stop_after_reservation_but_before_the_post_closes_the_intent_and_frees_the_slot(self):
        p, tid = self.publisher('vi');calls = []
        def loader():
            calls.append(1)
            return dict(self.release, paused=len(calls) == 2) # the second look, just before the POST, finds the factory paused
        p.release_loader = loader
        with self.assertRaises(ValueError):self.publish(p, tid)
        state = self.store.read()
        self.assertEqual((state['intents'][tid]['phase'], state['topics'][tid]['status']), ('NOT_SENT', 'READY'))
        self.assertEqual(self.client.posts, []);self.assertNotIn('publisher_lease', state)
        self.assertEqual(quota.unresolved(state, 'vi'), [])
        self.assertEqual(remaining_budget(state, self.release)['unresolved_intents'], [])
        p.release_loader = lambda: self.release
        self.assertEqual(self.publish(p, tid)['language'], 'vi')  # the topic can be published afterwards
        self.assertEqual(self.store.read()['intents'][tid]['phase'], 'PUBLISHED')

    def test_an_authoritative_plugin_refusal_closes_the_intent_only_when_a_readback_finds_nothing(self):
        # A refusal after which a draft exists is NOT proof that nothing was created: the draft is found by key and held.
        for code, creates_draft, phase, topic_status in (('thuha_unsafe_html', False, 'REJECTED', 'NEEDS_REPAIR'),
                                                         ('thuha_slug_conflict', False, 'REJECTED', 'NEEDS_REPAIR'),
                                                         ('thuha_language_marker_failed', True, 'DRAFT_HELD', 'BLOCKED'),
                                                         ('thuha_unsafe_html', True, 'DRAFT_HELD', 'BLOCKED'),
                                                         (None, False, 'NEEDS_RECONCILIATION', 'BLOCKED')):
            with self.subTest(code=code, draft=creates_draft):
                self.setUp();p, tid = self.publisher('vi');client = self.client;original = client.create
                def refuse(payload, code=code, creates_draft=creates_draft):
                    if creates_draft:
                        original(dict(payload))  # a draft exists although the call reports failure
                        client.posts[-1]['status'] = 'draft'
                    raise NetworkError('HTTP 422 for /wp-json/thuha-writer/v1/posts', 422, code)
                client.create = refuse
                with self.assertRaises(NetworkError):self.publish(p, tid)
                state = self.store.read()
                self.assertEqual((state['intents'][tid]['phase'], state['topics'][tid]['status']), (phase, topic_status))
                self.assertEqual(self.store.read()['receipts'], {})
                self.assertEqual(bool(quota.unresolved(state, 'vi')), phase in ('NEEDS_RECONCILIATION', 'DRAFT_HELD'))

    def test_a_closed_intent_frees_the_pilot_budget_but_an_unresolved_one_does_not(self):
        state = {'intents': {'a': {'phase': 'REJECTED', 'reserved_at': now()}, 'b': {'phase': 'NOT_SENT', 'reserved_at': now()},
                             'c': {'phase': 'NEEDS_RECONCILIATION', 'reserved_at': now()}}}
        window = remaining_budget(state, {'stage': 'pilot', 'pilot_max_posts': 2, 'maximum_daily_posts': 5})
        self.assertEqual((window['remaining'], window['unresolved_intents'], window['intents']), (1, ['c'], 1))

    def test_a_recorded_publication_is_never_overwritten_by_a_lost_response(self):
        p, tid = self.publisher('vi');original = self.store.mutate
        def lose_response_after_commit(callback):
            result = original(callback)
            if callback.__name__ == 'transaction':raise OSError('response lost after the receipt was committed')
            return result
        self.store.mutate = lose_response_after_commit
        receipt = self.publish(p, tid)  # the lost answer is recovered from the ledger, not turned into a failure
        state = original(lambda s: s)  # read through the real transaction
        self.assertEqual(receipt['wp_id'], 999)
        self.assertEqual(state['intents'][tid]['phase'], 'PUBLISHED');self.assertEqual(state['topics'][tid]['status'], 'PUBLISHED')
        self.assertIn(tid, state['receipts']);self.assertEqual(len(self.client.posts), 1)

    def test_a_replacement_reservation_may_follow_a_repaired_article(self):
        p, tid = self.publisher('vi')
        self.client.create = lambda payload: (_ for _ in ()).throw(NetworkError('HTTP 422', 422, 'thuha_unsafe_html'))
        with self.assertRaises(NetworkError):self.publish(p, tid)
        old = self.store.read()['intents'][tid]
        self.store.mutate(lambda s: s['intents'][tid].update(article_sha='f' * 64))  # a closed intent may change source
        self.assertEqual(self.store.read()['intents'][tid]['article_sha'], 'f' * 64)
        self.assertEqual(old['phase'], 'REJECTED')


class FreshnessTests(unittest.TestCase):
    def test_an_inventory_dated_in_the_future_is_never_fresh(self):
        import datetime as dt
        from thuha.common import fresh
        future = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=2)).isoformat()
        past = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=30)).isoformat()
        self.assertFalse(fresh(future, 1000))
        self.assertTrue(fresh(past, 1000))
        self.assertFalse(fresh(past, 10))


class QuotaRaceTests(unittest.TestCase):
    def test_a_post_published_after_the_inventory_was_read_still_counts(self):
        state = initial()
        for tid, wp in (('TH-VI-0001', 777), ('TH-VI-0002', 5)):
            state['topics'][tid] = {'language': 'vi', 'status': 'PUBLISHED'}
            state['intents'][tid] = {'language': 'vi', 'phase': 'PUBLISHED', 'wp_id': wp, 'article_sha': 'a' * 64}
        state['topics']['TH-VI-0003'] = {'language': 'vi', 'status': 'READY'}
        counts, targets = {'vi': 499, 'en': 0}, {'vi': 500, 'en': 500}
        # 777 is not in the stale inventory (it was published after it was read): the 500th slot is already taken.
        with self.assertRaises(quota.LanguageComplete):quota.reserve(state, counts, targets, 'vi', 'TH-VI-0003', live_ids={5})
        quota.reserve(state, counts, targets, 'vi', 'TH-VI-0003', live_ids={5, 777})  # both are in the inventory: 499 + 1 fits

    def test_closed_phases_never_count(self):
        state = initial()
        state['intents']['TH-VI-0001'] = {'language': 'vi', 'phase': 'REJECTED'}
        state['intents']['TH-VI-0002'] = {'language': 'vi', 'phase': 'NOT_SENT'}
        state['intents']['TH-VI-0003'] = {'language': 'vi', 'phase': 'VERIFY_PENDING'}
        self.assertEqual(quota.unresolved(state, 'vi'), ['TH-VI-0003'])


class RefillOnMigratedStateTests(tf.Fixture):
    def test_an_english_request_migrated_from_schema_four_does_not_block_a_vietnamese_one(self):
        def old(s):
            s['research_requests']['research-legacy'] = {'request_id': 'research-legacy', 'status': 'AWAITING_EXTERNAL_RESEARCH', 'created_at': now()}
            s['research_requests']['research-legacy'].pop('language', None)
        self.store.mutate(old)
        state = self.store.read();state['schema'] = 4  # what the remote branch really holds
        state['research_requests']['research-legacy'].pop('language', None)
        self.assertEqual(migrate(state)['research_requests']['research-legacy']['language'], 'en')
        self.store.mutate(lambda s: s['research_requests']['research-legacy'].update(language='en'))
        request = refill(self.store, self.inv)
        self.assertEqual(request['language'], 'vi')
        self.assertEqual(refill(self.store, self.inv), request)  # idempotent
        self.assertEqual(sorted(r['language'] for r in self.store.read()['research_requests'].values()), ['en', 'vi'])

    def test_a_vietnamese_request_comes_first_when_both_are_outstanding(self):
        refill(self.store, self.inv)
        self.store.mutate(lambda s: s['research_requests'].update({'research-en': {'request_id': 'research-en', 'language': 'en', 'status': 'AWAITING_EXTERNAL_RESEARCH'}}))
        self.assertEqual(refill(self.store, self.inv)['language'], 'vi')


class VerifyAndInventoryGuards(tf.PublisherBase):
    def test_a_title_wordpress_changed_is_published_but_raises_an_alert_that_stops_new_posts(self):
        p, tid = self.publisher('vi');original = self.client.create
        def altered(payload):
            result = original(payload);result['post']['title'] = payload['title'] + ' (edited)';return result
        self.client.create = altered
        receipt = self.publish(p, tid)  # WordPress did publish it: that is what counts
        state = self.store.read()
        self.assertEqual(state['intents'][tid]['phase'], 'PUBLISHED')
        self.assertEqual(self.store.get_document(receipt['document'])['integrity']['problems'], ['title'])
        self.assertEqual(len([a for a in state['alerts'] if not a['acknowledged']]), 1)

    def test_a_snapshot_inventory_cannot_be_used_for_publishing(self):
        p, tid = self.publisher('vi')
        p.inv = dict(self.inv, language_source='authenticated-snapshot')
        with self.assertRaisesRegex(ValueError, 'adapter inventory'):self.publish(p, tid)
        self.assertEqual(self.client.posts, []);self.assertEqual(self.store.read()['intents'], {})


class ErrorCodeTests(unittest.TestCase):
    def http_error(self, body):
        return urllib.error.HTTPError('https://rentbikehanoi.com/x', 422, 'x', {}, io.BytesIO(body))

    def test_only_a_well_formed_machine_code_is_kept_and_never_the_body(self):
        self.assertEqual(error_code(self.http_error(b'{"code":"thuha_unsafe_html","message":"secret detail"}')), 'thuha_unsafe_html')
        for bad in (b'<html>nope</html>', b'{"code":"Has Spaces!"}', b'{"code":123}', b'{}', b'{"code":"' + b'a' * 80 + b'"}', b''):
            self.assertIsNone(error_code(self.http_error(bad)), bad)

    def test_transport_exposes_the_code_on_the_exception_without_the_body(self):
        from thuha.http import HTTP
        http = HTTP(allow_write=True)
        err = self.http_error(b'{"code":"thuha_schema","message":"leaky body text"}')
        with patch.object(http.opener, 'open', side_effect=err):
            with self.assertRaises(NetworkError) as ctx:
                http.request(SITE + '/wp-json/thuha-writer/v1/inventory')
        self.assertEqual((ctx.exception.status, ctx.exception.code), (422, 'thuha_schema'))
        self.assertNotIn('leaky', str(ctx.exception))

    def test_every_definitive_rejection_is_a_real_plugin_error_code(self):
        from thuha import package
        from thuha.policy import DEFINITIVE_REJECTIONS
        self.assertFalse(set(DEFINITIVE_REJECTIONS) - set(package.ERROR_CODES))
        # Codes that can be returned AFTER a draft exists must never be treated as proof that nothing was created.
        for after_insert in ('thuha_language_marker_failed', 'thuha_seo_failed', 'thuha_media_failed', 'thuha_category_failed', 'thuha_slug_changed',
                             'thuha_permalink_mismatch', 'thuha_publish_failed', 'thuha_revert_failed', 'thuha_content_altered', 'thuha_in_progress',
                             'thuha_duplicate_key'):
            self.assertNotIn(after_insert, DEFINITIVE_REJECTIONS)


if __name__ == '__main__':
    unittest.main()
