"""Automatic QA must tell "the article is wrong" apart from "the data it needs does not exist yet".

A verdict made on an unusable inventory says nothing about the article, and an article that waits for pages that are
planned but not yet live must not burn a bounded repair or be sent back to a writer who cannot fix it. Real faults still
go to repair, an image is never waited for automatically (someone must choose it), and nothing is ever marked READY
without passing every check.
"""
import contextlib
import copy
import datetime as dt
import io
import json
import unittest
from test_factory import Fixture
from thuha import cli, quality, runtime
from thuha.common import ROOT, SITE
from thuha.coordinator import claim, submit
from thuha.publisher import Publisher
from thuha.research import intake

PLANNED = [SITE + '/vi/mot-bai-sap-dang-mot/', SITE + '/vi/mot-bai-sap-dang-hai/']
LIVE_LINKS = (SITE + '/vi/gioi-thieu-cua-hang/', SITE + '/vi/bai-viet-co-san/')
CATEGORY_LINKS = (SITE + '/vi/chuyen-muc/cam-nang/', SITE + '/vi/chuyen-muc/gia-thue-va-chi-phi/')


def aged(inv, hours):
    old = copy.deepcopy(inv)
    old['captured_at'] = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours)).isoformat()
    return old


def relink(article, *urls):
    """Point the two body links of the fixture article at `urls` (one URL keeps the second link out)."""
    body = article['body_html']
    for old, new in zip(LIVE_LINKS, urls):
        body = body.replace(old, new)
    if len(urls) < 2:
        body = body.replace(' và <a href="%s">bài viết liên quan</a>' % LIVE_LINKS[1], '')
    article['body_html'] = body


class QaDataHelpers(Fixture):
    def drafted(self, lang='vi', i=1, mutate=None):
        """A DRAFT_READY submission; `mutate` edits the article before it is stored."""
        topic = self.candidate(i, lang)
        intake(self.store, [topic], self.inv)
        lease = claim(self.store, 'session-qa%d' % i, 'writer-qa%d' % i)
        article = self.article_for(topic, 'session-qa%d' % i, 'writer-qa%d' % i)
        if mutate:
            mutate(article)
        sub = submit(self.store, lease['slot'], lease['session'], lease['fence'], article)
        return topic, article, sub

    def planned_draft(self, i=1):
        """A finished draft that links to two pages which are planned in the ledger but not live yet."""
        self.plan_urls()
        return self.drafted('vi', i, mutate=lambda a: relink(a, *PLANNED))

    def plan_urls(self):
        """Topics of the ledger whose pages are planned but not live: legitimate link targets to wait for."""
        for n, url in enumerate(PLANNED, start=2):
            other = {'topic_id': 'TH-VI-%04d' % n, 'language': 'vi', 'status': 'PLANNED', 'proposed_url': url}
            self.store.mutate(lambda s, other=other: s['topics'].update({other['topic_id']: other}))

    def live_with(self, *urls):
        inv = copy.deepcopy(self.inv)
        for n, url in enumerate(urls, start=90):
            slug = url.rstrip('/').rsplit('/', 1)[1]
            inv['items'].append({'id': n, 'url': url, 'slug': slug, 'title': 'Bài khác số %d' % n, 'type': 'posts', 'status': 'publish', 'language': 'vi',
                                 'canonical': url, 'search_intent': 'UNREVIEWED', 'content_signature': ['khac%d' % n], 'public_check': {'http_status': 200}})
        return inv

    def inv_without_vi_content(self):
        value = copy.deepcopy(self.inv)
        value['items'] = [i for i in value['items'] if i['language'] != 'vi']
        return value

    def inv_without_media(self):
        value = copy.deepcopy(self.inv)
        value['media'] = []
        return value

    def state_of(self, tid):
        state = self.store.read()
        return state['topics'][tid]['status'], state['qa'].get(tid), state['submissions'][tid]['repair_count']


class InventoryGuardTests(QaDataHelpers):
    def test_a_stale_inventory_changes_nothing_and_costs_no_repair(self):
        topic, article, sub = self.drafted('en')
        tid = topic['topic_id']
        before = self.store.read()
        documents = sorted(p.name for p in (self.store.directory / 'documents').iterdir())
        with self.assertRaisesRegex(ValueError, 'Inventory'):
            quality.run_qa(self.store, tid, aged(self.inv, 12), self.policy, self.business)
        after = self.store.read()
        self.assertEqual((after['version'], after['events']), (before['version'], before['events']))
        self.assertEqual(self.state_of(tid), ('DRAFT_READY', None, 0))
        self.assertEqual(documents, sorted(p.name for p in (self.store.directory / 'documents').iterdir()))  # no report was written

    def test_an_incomplete_inventory_is_refused_the_same_way(self):
        topic, article, sub = self.drafted('en')
        broken = dict(copy.deepcopy(self.inv), complete=False)
        with self.assertRaisesRegex(ValueError, 'Inventory'):
            quality.run_qa(self.store, topic['topic_id'], broken, self.policy, self.business)
        self.assertEqual(self.state_of(topic['topic_id']), ('DRAFT_READY', None, 0))

    def test_a_ready_draft_stays_ready_when_the_new_check_cannot_run(self):
        topic, article, sub = self.ready('en')
        tid = topic['topic_id']
        newer = dict(self.policy, score_threshold=80)  # a new policy hash makes the old report stale
        self.assertEqual(quality.pending_qa(self.store, newer), [tid])
        with self.assertRaises(ValueError):
            quality.run_qa(self.store, tid, aged(self.inv, 12), newer, self.business)
        self.assertEqual(self.store.read()['topics'][tid]['status'], 'READY')  # nothing was learned, so nothing changed


class SubmitGuardTests(QaDataHelpers):
    def test_an_empty_image_must_be_declared_as_a_wait_and_never_invented(self):
        topic = self.candidate(1, 'vi')
        intake(self.store, [topic], self.inv)
        lease = claim(self.store, 'session-g', 'writer-g')
        empty = dict(self.article_for(topic, 'session-g', 'writer-g'), featured_media=None)
        with self.assertRaisesRegex(ValueError, 'featured_media is empty'):
            submit(self.store, lease['slot'], lease['session'], lease['fence'], empty)
        with self.assertRaisesRegex(ValueError, 'featured_media is empty'):
            submit(self.store, lease['slot'], lease['session'], lease['fence'], empty, waiting_for=['INTERNAL_LINKS'])
        self.assertEqual(self.store.read()['topics'][topic['topic_id']]['status'], 'CLAIMED')
        submit(self.store, lease['slot'], lease['session'], lease['fence'], empty, waiting_for=['FEATURED_MEDIA'])
        self.assertEqual(self.store.read()['topics'][topic['topic_id']]['status'], 'WAITING_DATA')


class DataOnlyFailureTests(QaDataHelpers):
    def test_planned_link_targets_that_are_not_live_yet_are_a_data_wait(self):
        topic, article, sub = self.planned_draft()
        tid = topic['topic_id']
        result = quality.run_qa(self.store, tid, self.inv, self.policy, self.business)
        self.assertEqual((result['status'], result['waiting_for']), ('BLOCKED_DATA', ['INTERNAL_LINKS']))
        self.assertGreaterEqual(result['potential_score'], self.policy['score_threshold'])
        status, record, repairs = self.state_of(tid)
        self.assertEqual((status, record['status'], record['waiting_for'], record['article_sha'], repairs), ('DRAFT_READY', 'BLOCKED_DATA', ['INTERNAL_LINKS'], sub['article_sha'], 0))
        self.assertEqual(record['policy_sha256'], __import__('thuha.common', fromlist=['digest']).digest(self.policy))
        self.assertEqual(self.store.get_document(record['report_sha'])['status'], 'BLOCKED_DATA')  # the stored report is truthful

    def test_a_data_blocked_draft_frees_its_writers_slot_like_any_stored_draft(self):
        topic, article, sub = self.planned_draft()
        self.assertEqual(len(self.store.read()['leases']), 1)  # the writer still holds the slot after submitting
        quality.run_qa(self.store, topic['topic_id'], self.inv, self.policy, self.business)
        self.assertEqual(self.store.read()['leases'], {})

    def test_the_wait_is_not_a_pass_and_nothing_can_publish_it(self):
        topic, article, sub = self.planned_draft()
        tid = topic['topic_id']
        quality.run_qa(self.store, tid, self.inv, self.policy, self.business)
        self.assertNotEqual(self.store.read()['topics'][tid]['status'], 'READY')
        with self.assertRaises(ValueError):
            Publisher(self.store, object(), self.inv, self.policy, self.business, lambda: {}).prepare(tid)

    def test_the_same_wait_is_not_recorded_again(self):
        topic, article, sub = self.planned_draft()
        tid = topic['topic_id']
        quality.run_qa(self.store, tid, self.inv, self.policy, self.business)
        first = self.store.read()
        again = quality.run_qa(self.store, tid, self.inv, self.policy, self.business)
        self.assertEqual((again['status'], again['waiting_for']), ('BLOCKED_DATA', ['INTERNAL_LINKS']))
        second = self.store.read()
        self.assertEqual((second['version'], second['events']), (first['version'], first['events']))  # hourly runs add no noise

    def test_when_the_planned_pages_go_live_the_same_draft_passes_without_a_writer(self):
        topic, article, sub = self.planned_draft()
        tid = topic['topic_id']
        waiting = quality.run_qa(self.store, tid, self.inv, self.policy, self.business)
        half = quality.run_qa(self.store, tid, self.live_with(PLANNED[0]), self.policy, self.business)
        self.assertEqual((half['status'], half['waiting_for']), ('BLOCKED_DATA', ['INTERNAL_LINKS']))  # one of the two is still missing
        done = quality.run_qa(self.store, tid, self.live_with(*PLANNED), self.policy, self.business)
        self.assertEqual(done['status'], 'PASS', done['hard_fails'])
        self.assertEqual(waiting['potential_score'], done['score'])  # what the wait promised is what the pass gives
        status, record, repairs = self.state_of(tid)
        self.assertEqual((status, record['status'], repairs), ('READY', 'PASS', 0))

    def test_a_link_to_a_page_that_exists_nowhere_is_a_fault_not_a_wait(self):
        self.plan_urls()
        topic, article, sub = self.drafted('vi', mutate=lambda a: relink(a, PLANNED[0], SITE + '/vi/trang-khong-ton-tai/'))
        result = quality.run_qa(self.store, topic['topic_id'], self.inv, self.policy, self.business)
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual(self.state_of(topic['topic_id'])[0], 'NEEDS_REPAIR')

    def test_too_few_links_is_a_fault_not_a_wait(self):
        topic, article, sub = self.drafted('vi', mutate=lambda a: relink(a, LIVE_LINKS[0]))
        self.assertEqual(self.store.get_document(sub['article_sha'])['body_html'].count('<a '), 1)
        result = quality.run_qa(self.store, topic['topic_id'], self.inv, self.policy, self.business)
        self.assertEqual(result['status'], 'FAIL')
        self.assertIn('INSUFFICIENT_REAL_INTERNAL_LINKS', result['hard_fails'])
        self.assertEqual(self.state_of(topic['topic_id'])[0], 'NEEDS_REPAIR')

    def test_category_links_alone_never_satisfy_the_content_link_rule_so_qa_sends_the_draft_to_repair(self):
        topic, article, sub = self.drafted('vi', mutate=lambda a: relink(a, *CATEGORY_LINKS))
        for inv in (self.inv, self.inv_without_vi_content()):
            result = quality.run_qa(self.store, topic['topic_id'], inv, self.policy, self.business)
            self.assertEqual(result['status'], 'FAIL')
            self.assertEqual(self.state_of(topic['topic_id'])[0], 'NEEDS_REPAIR')
            self.store.mutate(lambda s: s['topics'][topic['topic_id']].update(status='DRAFT_READY'))  # evaluate the same draft again

    def test_an_image_is_never_an_automatic_wait_because_someone_must_choose_it(self):
        topic, article, sub = self.drafted('vi')
        legacy = self.store.put_document(dict(article, featured_media=None))  # a stored draft from before the submit guard
        self.store.mutate(lambda s: s['submissions'][topic['topic_id']].update(article_sha=legacy))
        for inv in (self.inv_without_media(), self.inv):
            result = quality.run_qa(self.store, topic['topic_id'], inv, self.policy, self.business)
            self.assertEqual(result['status'], 'FAIL')
            self.assertEqual(self.state_of(topic['topic_id'])[0], 'NEEDS_REPAIR')
            self.store.mutate(lambda s: s['topics'][topic['topic_id']].update(status='DRAFT_READY'))

    def test_a_chosen_image_that_the_inventory_does_not_show_is_a_fault_the_writer_can_fix(self):
        topic, article, sub = self.drafted('vi')  # media 51 chosen, but the inventory lacks every image
        result = quality.run_qa(self.store, topic['topic_id'], self.inv_without_media(), self.policy, self.business)
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual(self.state_of(topic['topic_id'])[0], 'NEEDS_REPAIR')

    def test_a_real_fault_next_to_a_data_wait_still_goes_to_repair(self):
        self.plan_urls()

        def broken(article):
            relink(article, *PLANNED)
            article['body_html'] += '<p>không cần đặt cọc</p>'
        topic, article, sub = self.drafted('vi', mutate=broken)
        result = quality.run_qa(self.store, topic['topic_id'], self.inv, self.policy, self.business)
        self.assertEqual(result['status'], 'FAIL')
        self.assertIn('UNVERIFIED_BUSINESS_OR_FIRSTHAND_CLAIM', result['hard_fails'])
        status, record, repairs = self.state_of(topic['topic_id'])
        self.assertEqual((status, record['status']), ('NEEDS_REPAIR', 'FAIL'))

    def test_a_wait_that_cannot_reach_the_threshold_even_with_the_data_is_a_fault(self):
        self.plan_urls()

        def thin(article):
            relink(article, *PLANNED)
            article['body_html'] = article['body_html'].replace('<h2>Điểm dừng thực tế</h2>', '<h3>Điểm dừng thực tế</h3>')  # one h2 less: -10 points
            article['seo_title'] = 'Ngắn'  # outside the title length band: -10 points
            article['meta_description'] = 'Quá ngắn.'  # still below 75 after missing data becomes available
        topic, article, sub = self.drafted('vi', mutate=thin)
        result = quality.run_qa(self.store, topic['topic_id'], self.inv, self.policy, self.business)
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual(self.state_of(topic['topic_id'])[0], 'NEEDS_REPAIR')

    def test_a_ready_draft_whose_check_can_no_longer_be_renewed_is_not_shown_as_qa_pass(self):
        topic, article, sub = self.ready('vi')
        tid = topic['topic_id']
        self.assertEqual(self.state_of(tid)[0], 'READY')
        newer = dict(self.policy, score_threshold=80)
        unverified = copy.deepcopy(self.inv)
        for item in unverified['items']:
            item['public_check'] = {}  # the linked pages are in WordPress but no check has confirmed them yet
        result = quality.run_qa(self.store, tid, unverified, newer, self.business)
        self.assertEqual((result['status'], result['waiting_for']), ('BLOCKED_DATA', ['INTERNAL_LINKS']))
        self.assertEqual(self.state_of(tid)[0], 'DRAFT_READY')  # READY meant "passed under the current policy"; it no longer does
        self.assertEqual(quality.pending_qa(self.store, newer), [tid])  # and it is checked again by itself on the next run

    def test_a_waiting_topic_is_counted_on_the_cycle_and_the_dashboard_and_never_as_a_pass(self):
        topic, article, sub = self.planned_draft()
        quality.run_qa(self.store, topic['topic_id'], self.inv, self.policy, self.business)
        release = json.loads((ROOT / 'config/release.json').read_text())
        cycle = runtime.cycle(self.store.read(), self.inv, release)
        row = cycle['row']
        self.assertEqual((row['QA PASS'], row['QA BLOCKED DATA'], row['QA FAIL'], row['WRITING']), (0, 1, 0, 0))
        self.assertEqual((cycle['languages']['vi']['qa_blocked_data'], cycle['languages']['vi']['writing']), (1, 0))
        from thuha import dashboard
        report = dashboard.report(self.store, self.inv, release)
        self.assertEqual(report['queue']['vi']['qa_blocked_data'], [topic['topic_id']])
        self.assertEqual(report['queue']['vi']['awaiting_qa'], [])
        self.assertEqual(report['qa_blocked_data'], {topic['topic_id']: ['INTERNAL_LINKS']})
        self.assertTrue(any('cannot pass QA yet' in b for b in report['blockers']))


class ReviseBlockedDraftTests(QaDataHelpers):
    """A draft that waits for planned pages must not be stuck if those pages never go live: a writer can re-point its links."""

    def blocked(self):
        topic, article, sub = self.planned_draft()
        quality.run_qa(self.store, topic['topic_id'], self.inv, self.policy, self.business)
        return topic, article, sub

    def test_a_data_blocked_draft_can_be_claimed_for_revision_and_the_revision_is_not_a_repair(self):
        topic, article, sub = self.blocked()
        tid = topic['topic_id']
        lease = claim(self.store, 'session-fix', 'writer-fix', revise=tid)
        self.assertEqual((lease['topic_id'], self.store.read()['topics'][tid]['status']), (tid, 'CLAIMED'))
        fixed = dict(article, session='session-fix', agent_id='writer-fix')
        fixed['body_html'] = fixed['body_html'].replace(PLANNED[0], LIVE_LINKS[0]).replace(PLANNED[1], LIVE_LINKS[1])  # live pages instead of planned ones
        result = submit(self.store, lease['slot'], lease['session'], lease['fence'], fixed)
        self.assertEqual(result['repair_count'], 0)
        self.assertEqual(self.state_of(tid)[0], 'DRAFT_READY')
        self.assertEqual(quality.pending_qa(self.store, self.policy), [tid])
        self.assertEqual(quality.run_qa(self.store, tid, self.inv, self.policy, self.business)['status'], 'PASS')

    def test_only_a_draft_that_really_waits_can_be_revised_this_way(self):
        topic, article, sub = self.drafted('vi', 1)  # a plain DRAFT_READY draft: nothing is blocked, nothing waits
        with self.assertRaisesRegex(ValueError, 'waits for data'):
            claim(self.store, 'session-no', 'writer-no', revise=topic['topic_id'])

    def test_a_lost_lease_leaves_the_draft_unfinished_and_claimable_not_ready(self):
        topic, article, sub = self.blocked()
        tid = topic['topic_id']
        lease = claim(self.store, 'session-lost', 'writer-lost', revise=tid, ttl=-1)
        from thuha.coordinator import recover
        self.store.mutate(lambda s: recover(s))
        status = self.store.read()['topics'][tid]
        self.assertEqual((status['status'], status.get('waiting_for', [])), ('WAITING_DATA', []))
        self.assertEqual(claim(self.store, 'session-again', 'writer-again')['topic_id'], tid)


class CommandLineQaTests(QaDataHelpers):
    def run_cli(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main(['--state-dir', str(self.store.directory)] + list(args))
        return code, json.loads(out.getvalue())

    def store_inventory(self, inv):
        self.store.mutate(lambda s: s.update(inventory_document=self.store.put_document(inv)))

    def test_a_scheduled_run_stays_green_when_a_draft_only_waits_for_pages_to_go_live(self):
        topic, article, sub = self.planned_draft()
        self.store_inventory(self.inv)
        code, result = self.run_cli('qa', '--pending')
        entry = result['results'][topic['topic_id']]
        self.assertEqual((code, entry['status'], entry['waiting_for']), (0, 'BLOCKED_DATA', ['INTERNAL_LINKS']))

    def test_asking_for_one_topic_reports_the_wait_with_its_own_exit_code(self):
        topic, article, sub = self.planned_draft()
        self.store_inventory(self.inv)
        code, result = self.run_cli('qa', '--topic-id', topic['topic_id'])
        self.assertEqual((code, result['results'][topic['topic_id']]['status']), (3, 'BLOCKED_DATA'))

    def test_a_stale_inventory_does_not_poison_the_queue_and_the_run_is_red(self):
        self.drafted('en', 1)
        self.drafted('vi', 2)  # different languages never collide as duplicates
        self.store_inventory(aged(self.inv, 12))
        code, result = self.run_cli('qa', '--pending')
        self.assertEqual({(v['status'], v['kind']) for v in result['results'].values()}, {('BLOCKED', 'INFRASTRUCTURE')})
        self.assertEqual(code, 2)  # the run is red so a stale audit is noticed
        for tid in result['results']:
            self.assertEqual(self.state_of(tid), ('DRAFT_READY', None, 0))


class PrecheckAgreesWithQaTests(QaDataHelpers):
    """The writer's non-mutating check classifies a failure the way the real QA does; it only adds what a writer may declare."""

    def precheck(self, mutate, inv=None):
        topic = self.candidate(1, 'vi')
        if topic['topic_id'] not in self.store.read()['topics']:
            intake(self.store, [topic], self.inv)
        article = self.article_for(topic)
        mutate(article)
        return runtime.precheck(self.store, self.store.read(), inv or self.inv, topic['topic_id'], article, self.policy, self.business)

    def test_a_planned_link_target_is_a_data_wait(self):
        self.plan_urls()
        result = self.precheck(lambda a: relink(a, *PLANNED))
        self.assertEqual((result['data_waits'], result['content_fails']), (['INTERNAL_LINKS'], []))
        self.assertGreaterEqual(result['potential_score'], self.policy['score_threshold'])

    def test_too_few_links_is_a_fault_while_the_site_has_content_to_link_to(self):
        result = self.precheck(lambda a: relink(a, LIVE_LINKS[0]))
        self.assertEqual(result['data_waits'], [])
        self.assertIn('INSUFFICIENT_REAL_INTERNAL_LINKS', result['content_fails'])

    def test_an_unfinished_draft_may_wait_for_links_only_while_the_site_has_no_live_content(self):
        categories_only = lambda a: relink(a, *CATEGORY_LINKS)
        result = self.precheck(categories_only, self.inv_without_vi_content())
        self.assertEqual((result['data_waits'], result['content_fails']), (['INTERNAL_LINKS'], []))  # nothing live to link to yet
        result = self.precheck(categories_only)  # live Vietnamese pages exist: the writer must link to one
        self.assertEqual(result['data_waits'], [])
        self.assertIn('INSUFFICIENT_REAL_INTERNAL_LINKS', result['content_fails'])

    def test_a_missing_choice_is_a_fault_when_an_image_exists_and_a_wait_when_none_does(self):
        result = self.precheck(lambda a: a.update(featured_media=None))
        self.assertEqual(result['data_waits'], [])
        self.assertIn('FEATURED_MEDIA_OR_ALT_NOT_VERIFIED', result['content_fails'])
        result = self.precheck(lambda a: a.update(featured_media=None), self.inv_without_media())
        self.assertEqual((result['data_waits'], result['content_fails']), (['FEATURED_MEDIA'], []))

    def test_a_stale_inventory_is_still_reported_as_a_wait_for_the_inventory(self):
        result = self.precheck(lambda a: None, aged(self.inv, 12))
        self.assertEqual(result['data_waits'], ['AUTHORITATIVE_INVENTORY'])

    def test_a_low_score_is_a_fault_even_when_data_is_also_missing(self):
        def thin(article):
            article.update(featured_media=None, seo_title='Ngắn', meta_description='Quá ngắn.')
            article['body_html'] = article['body_html'].replace('<h2>Điểm dừng thực tế</h2>', '<h3>Điểm dừng thực tế</h3>')  # below 75 even if an image becomes available
        result = self.precheck(thin, self.inv_without_media())
        self.assertIn('FEATURED_MEDIA', result['data_waits'])
        self.assertIn('SCORE_BELOW_THRESHOLD_EVEN_WITH_THE_DATA', result['content_fails'])


if __name__ == '__main__':
    unittest.main()
