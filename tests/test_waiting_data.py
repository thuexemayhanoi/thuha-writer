"""Drafts that wait for data: first-party evidence, a planning inventory, WAITING_DATA, and the export of drafts.

A draft that waits for an image, a live link or an authoritative inventory is stored with exactly what it lacks. It is never
READY and never "QA pass", nothing is invented to make it pass, and it is not claimed again until the data exists.
"""
import contextlib
import copy
import datetime as dt
import io
import json
import unittest
import unittest.mock
from pathlib import Path
from test_factory import Fixture
from thuha import audit, cli, dashboard, drafts, ledger, pipeline, quality, research, runtime
from thuha.common import ROOT, SITE, digest, load, now
from thuha.coordinator import WAIT_CODES, claim, release, recover, submit
from thuha.research import capture_repository_file, evidence_current, intake

FACTS = 'config/business-facts.json'
FACTORY = load(ROOT / 'config/factory.json')


def aged(inv, hours):
    old = copy.deepcopy(inv)
    old['captured_at'] = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours)).isoformat()
    return old


def without_vi_media(inv):
    """The live situation: the media library holds only English alt text, so a Vietnamese article has no image to choose."""
    value = copy.deepcopy(inv)
    value['media'] = [m for m in value['media'] if m['id'] == 50]
    return value


class FirstPartyEvidenceTests(Fixture):
    def test_the_business_facts_file_is_captured_as_labelled_repository_evidence(self):
        out = capture_repository_file(self.store, FACTS)
        evidence = self.store.get_document(out['document'])
        self.assertEqual((evidence['capture_method'], evidence['url'], evidence['http_status']), ('repository-file', 'repo://' + FACTS, 200))
        self.assertEqual(evidence['file_sha256'], digest((ROOT / FACTS).read_bytes()))
        self.assertLessEqual(len(evidence['excerpt'].split()), 20)  # an excerpt, never the whole file
        self.assertLess(len(json.dumps(evidence, ensure_ascii=False)), len((ROOT / FACTS).read_text(encoding='utf-8')))

    def test_only_the_owner_facts_file_can_be_captured_this_way(self):
        for bad in ('config/release.json', '../etc/passwd', 'src/thuha/cli.py', '/etc/hosts', FACTS + '/../release.json'):
            with self.subTest(bad), self.assertRaises(ValueError):
                capture_repository_file(self.store, bad)

    def test_evidence_goes_stale_when_the_facts_file_changes(self):
        evidence = self.store.get_document(capture_repository_file(self.store, FACTS)['document'])
        self.assertTrue(evidence_current(evidence))
        self.assertFalse(evidence_current(dict(evidence, file_sha256='0' * 64)))
        self.assertTrue(evidence_current({'url': 'https://example.org/', 'http_status': 200}))  # a web capture has no file to compare

    def test_intake_accepts_first_party_evidence_and_refuses_it_once_stale(self):
        candidate = self.candidate(1, 'vi')
        document = capture_repository_file(self.store, FACTS)['document']
        candidate['sources'] = [{'url': 'repo://' + FACTS, 'document': document, 'supports': 'Địa chỉ, giờ mở cửa và khoảng giá tham khảo do chủ cửa hàng cung cấp.'}]
        self.assertEqual(intake(self.store, [candidate], self.inv), ['TH-VI-0001'])
        stale = self.candidate(2, 'vi')
        fake = self.store.put_document(dict(self.store.get_document(document), file_sha256='1' * 64))
        stale['sources'] = [{'url': 'repo://' + FACTS, 'document': fake, 'supports': 'Địa chỉ, giờ mở cửa và khoảng giá tham khảo do chủ cửa hàng cung cấp.'}]
        with self.assertRaisesRegex(ValueError, 'stale'):
            intake(self.store, [stale], self.inv)

    def test_qa_accepts_first_party_evidence_and_rejects_it_once_stale(self):
        topic, article, sub = self.ready('vi')
        document = capture_repository_file(self.store, FACTS)['document']
        article = copy.deepcopy(article)
        article['sources'] = [{'url': 'repo://' + FACTS, 'document': document, 'supports': 'Địa chỉ, giờ mở cửa và khoảng giá tham khảo do chủ cửa hàng cung cấp.'}]
        sub = dict(sub, article_sha=digest(article))
        self.assertNotIn('SOURCE_STALE_OR_UNVERIFIED', quality.evaluate(article, topic, sub, self.inv, self.policy, self.store)['hard_fails'])
        stale = self.store.put_document(dict(self.store.get_document(document), file_sha256='2' * 64))
        article['sources'][0]['document'] = stale
        sub = dict(sub, article_sha=digest(article))
        self.assertIn('SOURCE_STALE_OR_UNVERIFIED', quality.evaluate(article, topic, sub, self.inv, self.policy, self.store)['hard_fails'])


class PlanningInventoryTests(Fixture):
    def test_a_planning_inventory_may_be_older_than_the_publishing_limit_but_not_unlimited(self):
        old = aged(self.inv, 12)
        candidate = self.candidate(1, 'vi')
        candidate['intent_review'] = dict(candidate['intent_review'], inventory_sha256=digest(old))
        with self.assertRaisesRegex(ValueError, 'stale'):
            research.validate_candidate(candidate, old, [], self.store)
        self.assertTrue(research.validate_candidate(candidate, old, [], self.store, inventory_max_age=FACTORY['planning_inventory_max_age_seconds']))
        with self.assertRaisesRegex(ValueError, 'stale'):
            research.validate_candidate(dict(candidate, intent_review=dict(candidate['intent_review'], inventory_sha256=digest(aged(self.inv, 24 * 30))), ),
                                        aged(self.inv, 24 * 30), [], self.store, inventory_max_age=FACTORY['planning_inventory_max_age_seconds'])
        self.assertGreater(FACTORY['planning_inventory_max_age_seconds'], self.policy['inventory_max_age_seconds'])

    def test_qa_never_uses_the_planning_age(self):
        topic, article, sub = self.ready('en')
        self.assertIn('Inventory is stale or future-dated', quality.evaluate(article, topic, sub, aged(self.inv, 12), self.policy, self.store)['hard_fails'])

    def test_a_legacy_stored_inventory_without_language_labels_is_replaced_by_the_authenticated_snapshot(self):
        legacy = {'site': SITE, 'complete': True, 'errors': [], 'items': [], 'categories': [], 'captured_at': now()}
        self.store.mutate(lambda s: s.update(inventory_document=self.store.put_document(legacy)))
        chosen = cli.inventory_for(self.store, None)
        self.assertEqual(chosen['language_source'], 'authenticated-snapshot')
        self.assertEqual(chosen['counts']['posts_by_language'], {'vi': 0, 'en': 275})
        self.store.mutate(lambda s: s.update(inventory_document=self.store.put_document(self.inv)))
        self.assertEqual(cli.inventory_for(self.store, None)['language_source'], 'adapter')
        labelled = dict(self.inv, language_source='public-rest-unverified')
        self.store.mutate(lambda s: s.update(inventory_document=self.store.put_document(labelled)))
        self.assertEqual(cli.inventory_for(self.store, None)['language_source'], 'public-rest-unverified')  # honest labels are kept

    def test_the_age_limit_depends_on_where_the_inventory_comes_from(self):
        self.assertEqual(cli.inventory_max_age({'language_source': 'adapter'}, self.policy, FACTORY), self.policy['inventory_max_age_seconds'])
        self.assertEqual(cli.inventory_max_age({'language_source': 'public-rest-unverified'}, self.policy, FACTORY), self.policy['inventory_max_age_seconds'])
        self.assertEqual(cli.inventory_max_age({'language_source': 'authenticated-snapshot'}, self.policy, FACTORY), FACTORY['planning_inventory_max_age_seconds'])

    def test_the_committed_snapshot_counts_the_live_english_posts_only(self):
        self.assertEqual(audit.snapshot_inventory()['counts']['posts_by_language'], {'vi': 0, 'en': 275})


class WaitingHelpers(Fixture):
    def waiting(self, codes=('FEATURED_MEDIA', 'INTERNAL_LINKS', 'AUTHORITATIVE_INVENTORY'), i=1, lang='vi'):
        topic = self.candidate(i, lang)
        intake(self.store, [topic], self.inv)
        lease = claim(self.store, 'session-w%d' % i, 'writer-w%d' % i)
        article = self.article_for(topic, 'session-w%d' % i, 'writer-w%d' % i)
        article['featured_media'] = None
        out = submit(self.store, lease['slot'], lease['session'], lease['fence'], article, waiting_for=codes)
        return topic, article, lease, out


class WaitingDataTests(WaitingHelpers):

    def test_a_draft_that_lacks_data_is_stored_waiting_and_frees_the_writer_slot(self):
        topic, article, lease, out = self.waiting()
        state = self.store.read()
        t = state['topics'][topic['topic_id']]
        self.assertEqual((t['status'], t['waiting_for']), ('WAITING_DATA', ['AUTHORITATIVE_INVENTORY', 'FEATURED_MEDIA', 'INTERNAL_LINKS']))
        self.assertEqual(state['submissions'][topic['topic_id']]['article_sha'], out['article_sha'])
        self.assertEqual(state['leases'], {})
        self.assertEqual(self.store.get_document(out['article_sha'])['featured_media'], None)
        self.assertEqual(state['events'][-1]['waiting_for'], ['AUTHORITATIVE_INVENTORY', 'FEATURED_MEDIA', 'INTERNAL_LINKS'])
        self.assertEqual(state['submissions'][topic['topic_id']]['repair_count'], 0)

    def test_nothing_can_be_invented_to_get_past_the_wait(self):
        topic = self.candidate(1, 'vi')
        intake(self.store, [topic], self.inv)
        lease = claim(self.store, 'session-w', 'writer-w')
        article = self.article_for(topic, 'session-w', 'writer-w')  # carries a real-looking media id 51
        with self.assertRaisesRegex(ValueError, 'featured_media'):
            submit(self.store, lease['slot'], lease['session'], lease['fence'], article, waiting_for=['FEATURED_MEDIA'])
        with self.assertRaisesRegex(ValueError, 'Unknown'):
            submit(self.store, lease['slot'], lease['session'], lease['fence'], dict(article, featured_media=None), waiting_for=['SOMETHING_ELSE'])
        self.assertEqual(self.store.read()['topics'][topic['topic_id']]['status'], 'CLAIMED')

    def test_a_waiting_draft_is_never_ready_never_qa_pass_and_never_published(self):
        topic, article, lease, out = self.waiting()
        tid = topic['topic_id']
        review = {'article_sha': out['article_sha'], 'reviewer_id': 'reviewer-qa', 'language': 'vi', 'checked_at': now(),
                  'checks': {k: True for k in quality.REVIEW_CHECKS}, 'notes': 'Synthetic.'}
        sha = self.store.put_document(review)
        self.store.mutate(lambda s: s.setdefault('reviews', {}).update({tid: sha}))
        self.assertEqual(quality.pending_qa(self.store, self.policy), [])
        with self.assertRaisesRegex(ValueError, 'waits for data'):
            quality.run_qa(self.store, tid, self.inv, self.policy, self.business)
        self.assertEqual(self.store.read()['topics'][tid]['status'], 'WAITING_DATA')
        self.assertEqual(self.store.read()['qa'], {})
        self.store.durable_remote = True
        publisher = __import__('thuha.publisher', fromlist=['Publisher']).Publisher(self.store, object(), self.inv, self.policy, self.business, lambda: {})
        with self.assertRaises(ValueError):
            publisher.prepare(tid)

    def test_a_waiting_topic_is_not_claimable_until_its_data_is_there(self):
        topic, article, lease, out = self.waiting()
        with self.assertRaisesRegex(ValueError, 'No admissible'):
            claim(self.store, 'session-other', 'writer-other')
        tid = topic['topic_id']
        self.store.mutate(lambda s: s['topics'][tid].update(waiting_for=[]))  # what recheck-data does when everything is available
        again = claim(self.store, 'session-other', 'writer-other')
        self.assertEqual(again['topic_id'], tid)
        self.assertEqual(self.store.read()['topics'][tid]['status'], 'CLAIMED')

    def test_a_waiting_draft_can_be_revised_while_its_data_is_still_missing(self):
        topic, article, lease, out = self.waiting()
        tid = topic['topic_id']
        with self.assertRaisesRegex(ValueError, 'No admissible'):
            claim(self.store, 'session-r', 'writer-r')  # not claimable the ordinary way
        revise = claim(self.store, 'session-r', 'writer-r', revise=tid)
        self.assertEqual(revise['topic_id'], tid)
        self.assertEqual(self.store.read()['topics'][tid]['status'], 'CLAIMED')
        fixed = dict(article, session='session-r', agent_id='writer-r', body_html=article['body_html'] + '<p>Một câu được sửa lại.</p>')
        result = submit(self.store, revise['slot'], 'session-r', revise['fence'], fixed, waiting_for=['FEATURED_MEDIA'])
        self.assertEqual(result['repair_count'], 0)  # a revision of a stored draft is not a repair
        state = self.store.read()
        self.assertEqual((state['topics'][tid]['status'], state['topics'][tid]['waiting_for']), ('WAITING_DATA', ['FEATURED_MEDIA']))
        self.assertEqual(state['leases'], {})
        self.assertNotEqual(result['article_sha'], out['article_sha'])

    def test_only_a_waiting_draft_can_be_revised_this_way(self):
        intake(self.store, [self.candidate(2, 'vi')], self.inv)
        with self.assertRaisesRegex(ValueError, 'waits for data'):
            claim(self.store, 'session-r2', 'writer-r2', revise='TH-VI-0002')
        with self.assertRaisesRegex(ValueError, 'waits for data'):
            claim(self.store, 'session-r3', 'writer-r3', revise='TH-VI-9999')

    def test_completing_a_draft_is_not_a_repair_and_a_lost_lease_returns_it_to_waiting(self):
        topic, article, lease, out = self.waiting()
        tid = topic['topic_id']
        self.store.mutate(lambda s: s['topics'][tid].update(waiting_for=[]))
        second = claim(self.store, 'session-complete', 'writer-complete')
        self.store.mutate(lambda s: s['leases'][second['slot']].update(expires_at=0))
        self.store.mutate(lambda s: recover(s))
        self.assertEqual(self.store.read()['topics'][tid]['status'], 'WAITING_DATA')  # not DRAFT_READY with an incomplete article
        third = claim(self.store, 'session-complete-2', 'writer-complete')
        done = dict(article, session='session-complete-2', agent_id='writer-complete', featured_media=51)
        done['body_html'] += '<p>Một đoạn bổ sung sau khi có dữ liệu.</p>'
        result = submit(self.store, third['slot'], third['session'], third['fence'], done)
        state = self.store.read()
        self.assertEqual(result['repair_count'], 0)
        self.assertEqual((state['topics'][tid]['status'], state['topics'][tid].get('waiting_for'), state['topics'][tid].get('completion_pending')),
                         ('DRAFT_READY', None, None))

    def test_a_lease_released_without_submitting_returns_a_completion_to_waiting(self):
        topic, article, lease, out = self.waiting()
        tid = topic['topic_id']
        self.store.mutate(lambda s: s['topics'][tid].update(waiting_for=[]))
        second = claim(self.store, 'session-complete', 'writer-complete')
        release(self.store, second['slot'], second['session'], second['fence'])
        self.assertEqual(self.store.read()['topics'][tid]['status'], 'WAITING_DATA')

    def test_a_waiting_draft_counts_as_an_open_topic_and_is_not_a_published_post(self):
        topic, article, lease, out = self.waiting()
        from thuha import quota
        state = self.store.read()
        self.assertEqual(quota.status(state, {'vi': 0, 'en': 2}, {'vi': 500, 'en': 500})['vi']['open_topics'], 1)
        self.assertEqual(quota.topics_needed(state, {'vi': 0, 'en': 2}, {'vi': 500, 'en': 500}, 'vi'), 499)
        self.assertEqual(state['receipts'], {})

    def test_recheck_clears_only_what_the_inventory_really_has(self):
        topic, article, lease, out = self.waiting()
        tid = topic['topic_id']
        none = readiness_cleared(self.store, self.inv_without_vi())
        self.assertEqual(none, {})
        self.assertEqual(len(self.store.read()['topics'][tid]['waiting_for']), 3)
        authoritative_only = copy.deepcopy(self.inv)
        authoritative_only['media'] = [m for m in authoritative_only['media'] if m['id'] == 50]  # English alt only
        authoritative_only['items'] = [i for i in authoritative_only['items'] if i['language'] == 'en']
        cleared = readiness_cleared(self.store, authoritative_only)
        self.assertEqual(cleared, {tid: ['AUTHORITATIVE_INVENTORY']})
        self.assertEqual(self.store.read()['topics'][tid]['waiting_for'], ['FEATURED_MEDIA', 'INTERNAL_LINKS'])
        cleared = readiness_cleared(self.store, self.inv)
        self.assertEqual(cleared, {tid: ['FEATURED_MEDIA', 'INTERNAL_LINKS']})
        state = self.store.read()
        self.assertEqual((state['topics'][tid]['status'], state['topics'][tid]['waiting_for']), ('WAITING_DATA', []))
        self.assertEqual([e['action'] for e in state['events']][-2:], ['DATA_AVAILABLE', 'DATA_AVAILABLE'])

    def inv_without_vi(self):
        value = copy.deepcopy(self.inv)
        value['language_source'] = 'public-rest-unverified'
        value['media'] = [m for m in value['media'] if m['id'] == 50]
        value['items'] = [i for i in value['items'] if i['language'] == 'en']
        return value

    def test_the_dashboard_and_the_cycle_show_what_each_draft_waits_for(self):
        topic, article, lease, out = self.waiting()
        report = dashboard.report(self.store, self.inv, load(ROOT / 'config/release.json'))
        self.assertEqual(report['queue']['vi']['waiting_data'], [topic['topic_id']])
        self.assertEqual(report['waiting_data'], {topic['topic_id']: ['AUTHORITATIVE_INVENTORY', 'FEATURED_MEDIA', 'INTERNAL_LINKS']})
        self.assertTrue(any('wait for data' in b and 'FEATURED_MEDIA' in b for b in report['blockers']))
        cycle = runtime.cycle(self.store.read(), self.inv, load(ROOT / 'config/release.json'))
        self.assertEqual(cycle['row']['WAITING DATA'], 1)
        self.assertEqual(cycle['row']['QA PASS'], 0)

    def test_precheck_separates_content_faults_from_data_waits(self):
        topic, article, lease, out = self.waiting()
        state = self.store.read()
        bare = without_vi_media(self.inv)  # nothing with Vietnamese alt text exists, so nothing could have been chosen
        result = runtime.precheck(self.store, state, bare, topic['topic_id'], dict(article, featured_media=None), self.policy, self.business)
        self.assertIn('FEATURED_MEDIA', result['data_waits'])
        self.assertNotIn('FEATURED_MEDIA_OR_ALT_NOT_VERIFIED', result['content_fails'])
        broken = dict(article, featured_media=None, body_html=article['body_html'] + '<p>không cần đặt cọc</p>')
        result = runtime.precheck(self.store, state, bare, topic['topic_id'], broken, self.policy, self.business)
        self.assertIn('UNVERIFIED_BUSINESS_OR_FIRSTHAND_CLAIM', result['content_fails'])  # a real fault stays a fault
        # With an image that could have been chosen, leaving the choice empty is the writer's to fix, not a wait.
        result = runtime.precheck(self.store, state, self.inv, topic['topic_id'], dict(article, featured_media=None), self.policy, self.business)
        self.assertEqual(result['data_waits'], [])
        self.assertIn('FEATURED_MEDIA_OR_ALT_NOT_VERIFIED', result['content_fails'])


def readiness_cleared(store, inv):
    from thuha import coordinator
    return store.mutate(lambda s: coordinator.clear_satisfied(s, inv))


class EditorialHoldTests(WaitingHelpers):
    """A topic that should not be written (it overlaps another, or its draft adds nothing) is held, not deleted."""

    def test_a_held_topic_is_not_claimable_not_qaed_and_remembers_where_it_was(self):
        from thuha.coordinator import hold, unhold
        topic, article, lease, out = self.waiting()
        tid = topic['topic_id']
        hold(self.store, tid, 'Overlaps another row; its angle moves into TH-VI-0011.')
        state = self.store.read()
        self.assertEqual((state['topics'][tid]['status'], state['topics'][tid]['held']['from']), ('HELD', 'WAITING_DATA'))
        self.assertIn(state['topics'][tid]['status'], __import__('thuha.quota', fromlist=['x']).OPEN_TOPIC_STATES)
        self.assertEqual(state['events'][-1]['action'], 'TOPIC_HELD')
        with self.assertRaisesRegex(ValueError, 'No admissible'):
            claim(self.store, 'session-h', 'writer-h')
        self.store.mutate(lambda s: s['topics'][tid].update(waiting_for=[]))
        with self.assertRaisesRegex(ValueError, 'No admissible'):
            claim(self.store, 'session-h', 'writer-h')  # even with no data wait left, a hold is a hold
        self.assertEqual(self.store.read()['qa'], {})
        unhold(self.store, tid)
        self.assertEqual(self.store.read()['topics'][tid]['status'], 'WAITING_DATA')
        self.assertNotIn('held', self.store.read()['topics'][tid])

    def test_only_an_unleased_topic_that_is_not_in_publication_can_be_held(self):
        from thuha.coordinator import hold
        intake(self.store, [self.candidate(2, 'vi')], self.inv)
        lease = claim(self.store, 'session-h2', 'writer-h2')
        with self.assertRaisesRegex(ValueError, 'cannot be held'):
            hold(self.store, 'TH-VI-0002', 'reason')
        with self.assertRaisesRegex(ValueError, 'reason'):
            hold(self.store, 'TH-VI-0002', '')
        release(self.store, lease['slot'], lease['session'], lease['fence'])
        hold(self.store, 'TH-VI-0002', 'Overlaps another row.')
        self.store.mutate(lambda s: s['topics']['TH-VI-0002'].update(status='PUBLISHING'))
        with self.assertRaisesRegex(ValueError, 'cannot be held'):
            hold(self.store, 'TH-VI-0002', 'again')

    def test_the_dashboard_lists_held_topics_apart_from_the_queue(self):
        from thuha.coordinator import hold
        topic, article, lease, out = self.waiting()
        hold(self.store, topic['topic_id'], 'Overlaps another row.')
        report = dashboard.report(self.store, self.inv, load(ROOT / 'config/release.json'))
        self.assertEqual(report['queue']['vi']['held_or_unknown'], [topic['topic_id']])
        self.assertEqual(report['held'], {topic['topic_id']: 'Overlaps another row.'})
        self.assertEqual(report['queue']['vi']['waiting_data'], [])

    def test_the_command_line_holds_and_unholds(self):
        topic, article, lease, out = self.waiting()
        path = Path(self.temp.name) / 'inv.json'
        path.write_text(json.dumps(self.inv))
        def run(*argv):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = cli.main(['--state-dir', self.temp.name, '--inventory', str(path)] + list(argv))
            return code, json.loads(buf.getvalue())
        self.assertEqual(run('hold', '--topic-id', topic['topic_id'], '--reason', 'Overlaps another row.')[0], 0)
        self.assertEqual(self.store.read()['topics'][topic['topic_id']]['status'], 'HELD')
        self.assertEqual(run('unhold', '--topic-id', topic['topic_id'])[0], 0)
        self.assertEqual(self.store.read()['topics'][topic['topic_id']]['status'], 'WAITING_DATA')


class WaitCodeTests(unittest.TestCase):
    def test_every_wait_code_has_the_hard_fails_that_mean_it(self):
        self.assertEqual(set(runtime.DATA_WAIT_FAILS), set(WAIT_CODES))
        for fails in runtime.DATA_WAIT_FAILS.values():
            self.assertTrue(fails)


class SubmitCommandTests(Fixture):
    def test_the_command_line_stores_a_waiting_draft(self):
        topic = self.candidate(1, 'vi')
        intake(self.store, [topic], self.inv)
        lease = claim(self.store, 'session-cli', 'writer-cli')
        article = dict(self.article_for(topic, 'session-cli', 'writer-cli'), featured_media=None)
        path = Path(self.temp.name) / 'article.json'
        path.write_text(json.dumps(article))
        with contextlib.redirect_stdout(io.StringIO()):
            code = cli.main(['--state-dir', self.temp.name, 'submit', '--slot', lease['slot'], '--session', lease['session'], '--fence', lease['fence'],
                             '--file', str(path), '--waiting-for', 'FEATURED_MEDIA', 'INTERNAL_LINKS'])
        self.assertEqual(code, 0)
        self.assertEqual(self.store.read()['topics'][topic['topic_id']]['waiting_for'], ['FEATURED_MEDIA', 'INTERNAL_LINKS'])
        self.assertEqual(set(WAIT_CODES), {'FEATURED_MEDIA', 'INTERNAL_LINKS', 'AUTHORITATIVE_INVENTORY'})


class LinkTypoTests(Fixture):
    def test_a_link_to_nowhere_is_a_content_fault_not_a_data_wait(self):
        topic = self.candidate(1, 'vi')
        intake(self.store, [topic], self.inv)
        article = dict(self.article_for(topic), featured_media=None)
        bare = without_vi_media(self.inv)
        typo = dict(article, body_html=article['body_html'] + '<p><a href="' + SITE + '/vi/chuyen-muc/khong-co-chuyen-muc-nay/">sai</a></p>')
        result = runtime.precheck(self.store, self.store.read(), bare, 'TH-VI-0001', typo, self.policy, self.business)
        self.assertIn('INTERNAL_LINK_TARGET_UNKNOWN', result['content_fails'])
        self.assertEqual(result['unknown_internal_links'], [SITE + '/vi/chuyen-muc/khong-co-chuyen-muc-nay/'])
        clean = runtime.precheck(self.store, self.store.read(), bare, 'TH-VI-0001', article, self.policy, self.business)
        self.assertEqual((clean['content_fails'], clean['unknown_internal_links']), ([], []))

    def test_a_planned_url_of_the_matrix_or_the_ledger_is_not_a_typo(self):
        topic = self.candidate(1, 'vi')
        intake(self.store, [topic], self.inv)
        planned = load(ROOT / 'data/bilingual/matrix/vi500.json')['rows'][0]['proposed_url']
        article = dict(self.article_for(topic), featured_media=None)
        article = dict(article, body_html=article['body_html'] + '<p><a href="' + planned + '">bài sẽ đăng</a></p>')
        result = runtime.precheck(self.store, self.store.read(), self.inv, 'TH-VI-0001', article, self.policy, self.business)
        self.assertEqual(result['unknown_internal_links'], [])


class CommandLineTests(Fixture):
    def run_cli(self, *argv, inventory=True, inv=None):
        path = Path(self.temp.name) / 'inv.json'
        path.write_text(json.dumps(inv or self.inv))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main(['--state-dir', self.temp.name] + (['--inventory', str(path)] if inventory else []) + list(argv))
        return code, json.loads(out.getvalue())

    def test_recheck_data_clears_what_exists_and_leaves_the_draft_unfinished(self):
        topic = self.candidate(1, 'vi')
        intake(self.store, [topic], self.inv)
        lease = claim(self.store, 'session-r', 'writer-r')
        submit(self.store, lease['slot'], lease['session'], lease['fence'], dict(self.article_for(topic, 'session-r', 'writer-r'), featured_media=None),
               waiting_for=['FEATURED_MEDIA', 'AUTHORITATIVE_INVENTORY'])
        code, out = self.run_cli('recheck-data')
        self.assertEqual((code, out['cleared']), (0, {'TH-VI-0001': ['AUTHORITATIVE_INVENTORY', 'FEATURED_MEDIA']}))
        self.assertEqual(out['still_waiting'], {})
        topic_now = self.store.read()['topics']['TH-VI-0001']
        self.assertEqual((topic_now['status'], topic_now['waiting_for']), ('WAITING_DATA', []))
        self.assertEqual(self.store.read()['qa'], {})
        code, again = self.run_cli('recheck-data')
        self.assertEqual(again['cleared'], {})  # nothing more to clear, nothing written
        self.assertEqual(sum(e['action'] == 'DATA_AVAILABLE' for e in self.store.read()['events']), 1)

    def test_source_command_captures_first_party_facts_and_needs_exactly_one_source(self):
        code, out = self.run_cli('source', '--repository-file', FACTS)
        self.assertEqual((code, out['capture_method']), (0, 'repository-file'))
        self.assertEqual(self.store.get_document(out['document'])['url'], 'repo://' + FACTS)
        with self.assertRaisesRegex(ValueError, 'exactly one'):
            self.run_cli('source')
        with self.assertRaisesRegex(ValueError, 'exactly one'):
            self.run_cli('source', '--repository-file', FACTS, '--url', 'https://example.org/')

    def test_precheck_exit_codes_tell_a_fault_from_a_missing_image(self):
        topic = self.candidate(1, 'vi')
        intake(self.store, [topic], self.inv)
        article = dict(self.article_for(topic), featured_media=None)
        path = Path(self.temp.name) / 'a.json'
        path.write_text(json.dumps(article))
        bare = without_vi_media(self.inv)
        code, out = self.run_cli('precheck', '--topic-id', 'TH-VI-0001', '--file', str(path), inv=bare)
        self.assertEqual((code, out['data_waits'], out['content_fails']), (3, ['FEATURED_MEDIA'], []))
        self.assertEqual(self.run_cli('precheck', '--topic-id', 'TH-VI-0001', '--file', str(path))[0], 1)  # an image exists and was not chosen
        path.write_text(json.dumps(dict(article, body_html=article['body_html'] + '<p>không cần đặt cọc</p>')))
        self.assertEqual(self.run_cli('precheck', '--topic-id', 'TH-VI-0001', '--file', str(path), inv=bare)[0], 1)
        path.write_text(json.dumps(dict(article, featured_media=51)))
        self.assertEqual(self.run_cli('precheck', '--topic-id', 'TH-VI-0001', '--file', str(path))[0], 0)

    def test_a_topic_already_in_the_ledger_is_not_offered_again_as_the_next_one_to_research(self):
        rows = self.run_cli('matrix', 'next', '--language', 'vi', '--limit', '3', inventory=False)[1]['next_research']
        first = rows[0]['id']
        self.store.mutate(lambda s: s['topics'].update({first: {'topic_id': first, 'language': 'vi', 'status': 'PLANNED'}}))
        again = self.run_cli('matrix', 'next', '--language', 'vi', '--limit', '3', inventory=False)[1]['next_research']
        self.assertNotIn(first, [r['id'] for r in again])
        self.assertEqual(len(again), 3)

    def test_a_writer_can_claim_against_a_planning_snapshot_older_than_the_publishing_limit(self):
        intake(self.store, [self.candidate(1, 'vi')], self.inv)
        snapshot = aged(audit.snapshot_inventory(), 48)
        with unittest.mock.patch('thuha.cli.audit.snapshot_inventory', return_value=snapshot):
            code, out = self.run_cli('claim', '--session', 'session-plan', '--agent-id', 'writer-plan', inventory=False)
        self.assertEqual((code, out['topic_id']), (0, 'TH-VI-0001'))
        with unittest.mock.patch('thuha.cli.audit.snapshot_inventory', return_value=aged(snapshot, 24 * 30)), self.assertRaisesRegex(ValueError, 'stale'):
            self.run_cli('claim', '--session', 'session-plan-2', '--agent-id', 'writer-plan', inventory=False)


class WorkflowTests(unittest.TestCase):
    def test_the_protected_job_clears_waits_after_the_authenticated_audit_and_before_qa(self):
        text = (ROOT / '.github/workflows/thuha-ready-publisher.yml').read_text(encoding='utf-8')
        inside = text[text.index('  protected-publish:'):]
        order = [inside.index(x) for x in (' audit', 'recheck-data', 'qa --pending', 'publisher --mode drain')]
        self.assertEqual(order, sorted(order))
        self.assertNotIn('recheck-data', text[:text.index('  protected-publish:')])  # the job without WordPress access never writes it


class QualityWorkflowTests(unittest.TestCase):
    def test_a_pull_request_shows_the_hand_over_plan_and_never_applies_it(self):
        text = (ROOT / '.github/workflows/quality.yml').read_text(encoding='utf-8')
        step = text[text.index('Hand-over plan for this pull request'):text.index('Read authoritative remote state')]
        self.assertIn("github.event_name == 'pull_request'", step)
        self.assertIn('head.repo.full_name == github.repository', step)  # a fork has no token
        self.assertIn('thuha.cli --remote promote >', step)
        self.assertNotIn('--apply', text)  # no step of the quality workflow writes the shared ledger
        self.assertNotIn('contents: write', text)


class CommittedDraftsTests(unittest.TestCase):
    def test_the_committed_drafts_folder_is_exactly_what_the_committed_ledger_exports(self):
        """drafts/ is derived; a ledger change without `python3 scripts/export_drafts.py` fails here, like the matrices do."""
        import tempfile
        from thuha.store import migrate
        state = migrate(load(ROOT / 'data/state/factory.json'))
        documents = ledger.read_documents(ROOT / 'data/documents')
        with tempfile.TemporaryDirectory() as temp:
            written = drafts.export(state, lambda sha: documents[sha], Path(temp))
            expected = {p: (Path(temp) / p).read_bytes() for p in written + ['INDEX.md']}
        committed = {str(p.relative_to(ROOT / 'drafts')) for p in (ROOT / 'drafts').rglob('*') if p.is_file()}
        self.assertEqual(committed, set(expected), 'run python3 scripts/export_drafts.py')
        for name, raw in expected.items():
            self.assertEqual((ROOT / 'drafts' / name).read_bytes(), raw, name + ' is stale: run python3 scripts/export_drafts.py')

    def test_no_stored_draft_is_ready_or_qa_passed_without_an_independent_review(self):
        state = load(ROOT / 'data/state/factory.json')
        for tid, topic in state['topics'].items():
            if topic['status'] in ('WAITING_DATA', 'HELD'):
                self.assertNotIn(tid, state['qa'], tid)
                self.assertNotIn(tid, state['receipts'], tid)
                self.assertNotIn(tid, state['intents'], tid)
            if topic['status'] == 'WAITING_DATA':
                article = ledger.read_documents(ROOT / 'data/documents')[state['submissions'][tid]['article_sha']]
                self.assertIsNone(article['featured_media'], tid)  # nothing invented to get past the wait


class DraftExportTests(Fixture):
    def test_every_draft_is_exported_under_its_stable_id_and_the_export_is_exact_and_repeatable(self):
        topic = self.candidate(1, 'vi')
        intake(self.store, [topic], self.inv)
        lease = claim(self.store, 'session-x', 'writer-x')
        article = dict(self.article_for(topic, 'session-x', 'writer-x'), featured_media=None)
        out = submit(self.store, lease['slot'], lease['session'], lease['fence'], article, waiting_for=['FEATURED_MEDIA'])
        target = Path(self.temp.name) / 'drafts'
        written = drafts.export(self.store.read(), self.store.get_document, target)
        record = json.loads((target / 'vi' / 'TH-VI-0001.json').read_text(encoding='utf-8'))
        self.assertEqual(record['article'], self.store.get_document(out['article_sha']))
        self.assertEqual((record['status'], record['waiting_for'], record['article_sha']), ('WAITING_DATA', ['FEATURED_MEDIA'], out['article_sha']))
        self.assertEqual(record['source_documents'], [x['document'] for x in article['sources']])
        self.assertIn('TH-VI-0001', (target / 'INDEX.md').read_text(encoding='utf-8'))
        self.assertEqual(written, ['vi/TH-VI-0001.json'])
        before = {p: p.read_bytes() for p in target.rglob('*') if p.is_file()}
        drafts.export(self.store.read(), self.store.get_document, target)
        self.assertEqual({p: p.read_bytes() for p in target.rglob('*') if p.is_file()}, before)

    def test_a_topic_without_a_draft_is_not_exported(self):
        intake(self.store, [self.candidate(1, 'vi')], self.inv)
        target = Path(self.temp.name) / 'drafts'
        self.assertEqual(drafts.export(self.store.read(), self.store.get_document, target), [])


if __name__ == '__main__':
    unittest.main()
