"""The whole line against a simulated WordPress, over real HTTP plumbing:

writer session ledger -> hand-over to the shared ledger -> QA -> shared queue -> publisher -> receipt,
including network faults, repeated runs and two publishers at once.

WordPress is simulated (tests/fake_wordpress.py). Passing here shows the factory's own logic holds up; it is not
evidence about the real site, the native Vietnamese plugin or Yoast.
"""
import copy
import datetime as dt
import os
import random
import re
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
import test_factory as tf
from fake_wordpress import FakeWordPress, PLUGIN
from test_remote_and_recovery import MemoryGitHub
from thuha import audit, dashboard, ledger, pipeline, quality
from thuha.adapter import AdapterClient
from thuha.common import ROOT, SITE, digest, load, now
from thuha.coordinator import claim, submit
from thuha.language import post_url
from thuha.publisher import Publisher, quota_unresolved
from thuha.research import intake
from thuha.store import GitStore, validate

VI = [('bảo dưỡng xe tay ga định kỳ', 'Lịch bảo dưỡng định kỳ cho xe tay ga: những hạng mục cần kiểm tra', 'lich-bao-duong-dinh-ky-xe-tay-ga'),
      ('chọn mũ bảo hiểm phù hợp', 'Cách chọn mũ bảo hiểm vừa đầu và đạt chuẩn an toàn khi đi phố', 'cach-chon-mu-bao-hiem-vua-dau'),
      ('đổ xăng đúng cách', 'Đổ xăng cho xe máy: loại xăng, lượng xăng và những lỗi hay gặp', 'do-xang-cho-xe-may-dung-cach')]
EN = [('carry luggage on a scooter', 'How to carry a small backpack safely on a rented scooter', 'carry-backpack-safely-rented-scooter')]


VI_WORDS = ('bảo', 'dưỡng', 'phanh', 'lốp', 'nhớt', 'xích', 'đèn', 'gương', 'còi', 'ắc', 'quy', 'bugi', 'lọc', 'gió', 'nước', 'làm', 'mát',
            'kiểm', 'tra', 'thay', 'định', 'kỳ', 'tháng', 'quãng', 'đường', 'cây', 'số', 'tiết', 'kiệm', 'xăng', 'động', 'cơ', 'êm', 'ái',
            'phố', 'cổ', 'ngõ', 'nhỏ', 'đông', 'đúc', 'giờ', 'cao', 'điểm', 'mưa', 'trơn', 'trượt', 'cẩn', 'thận', 'tốc', 'độ', 'vừa', 'phải',
            'hành', 'lý', 'ba', 'lô', 'túi', 'yên', 'sau', 'cốp', 'khóa', 'cổ', 'giấy', 'tờ', 'đăng', 'ký', 'bảo', 'hiểm', 'mũ', 'quai', 'cài')
EN_WORDS = ('pack', 'strap', 'seat', 'luggage', 'balance', 'weight', 'corner', 'brake', 'mirror', 'pedal', 'helmet', 'zip', 'pocket',
            'route', 'traffic', 'morning', 'evening', 'market', 'lake', 'bridge', 'station', 'ticket', 'rain', 'dry', 'narrow', 'wide',
            'slow', 'steady', 'careful', 'friendly', 'local', 'quiet', 'busy', 'early', 'late', 'plan', 'carry', 'lock', 'park', 'fuel',
            'tank', 'engine', 'chain', 'light', 'horn', 'gear', 'speed', 'limit', 'sign', 'turn', 'signal', 'lane', 'crossing', 'crowd')


def distinct_body(article, lang):
    """Give every article its own prose: identical bodies would (rightly) trip the content-overlap check."""
    rng = random.Random(article['topic_id'])
    words, count = (VI_WORDS, 1100) if lang == 'vi' else (EN_WORDS, 760)
    text = ' '.join(rng.choice(words) for _ in range(count))
    article = copy.deepcopy(article)
    article['body_html'] = re.sub(r'<p>.*?</p>', lambda m: '<p>' + text + '</p>', article['body_html'], count=1, flags=re.S)
    return article


class LockedGitHub(MemoryGitHub):
    """GitHub answers each request atomically; the plain double does not promise that across threads."""
    def __init__(self):
        super().__init__()
        self.mutex = threading.RLock()

    def request(self, method, path, body=None):
        with self.mutex:
            return super().request(method, path, body)


class Line(tf.Fixture):
    """Shared set-up: a session ledger (what a writer's branch holds), the shared ledger, a simulated WordPress."""

    def setUp(self):
        super().setUp()
        self.wp = FakeWordPress(self.inv)
        self.api = LockedGitHub()
        self.shared = GitStore(self.api)
        self.release = {'approved': True, 'enabled': True, 'paused': False, 'emergency_stop': False, 'approval_ref': 'e2e-synthetic',
                        'cross_publisher_coordination_verified': True, 'stage': 'pilot', 'pilot_max_posts': 2, 'approved_capacity': 2,
                        'maximum_daily_posts': 2, 'minimum_post_interval_seconds': 0, 'languages_enabled': ['vi', 'en']}
        environment = patch.dict(os.environ, {'THUHA_WP_USER': 'publisher', 'THUHA_WP_APPLICATION_PASSWORD': 'synthetic',
                                              'THUHA_GO_LIVE_APPROVAL': 'e2e-synthetic'})
        environment.start()
        self.addCleanup(environment.stop)
        for target in ('thuha.http.time.sleep', 'thuha.pipeline.time.sleep'):
            sleeper = patch(target, lambda _seconds: None)
            sleeper.start()
            self.addCleanup(sleeper.stop)
        self.sessions = 0

    # -- the writer side: a session ledger, then a hand-over -----------------------------------------------------------

    def draft(self, lang, subject, reviewed=True):
        keyword, title, slug = subject
        self.sessions += 1
        number = self.sessions
        topic = self.candidate(number, lang)
        topic.update(topic_id=('TH-VI-' if lang == 'vi' else 'TH-EN-') + '%04d' % number, primary_keyword=keyword,
                     search_intent='hướng dẫn ' + keyword if lang == 'vi' else 'guide to ' + keyword, proposed_title=title,
                     proposed_url=post_url(lang, slug) if lang == 'vi' else SITE + '/' + slug + '/')
        intake(self.store, [topic], self.inv)
        session, agent = 'session-w%d' % number, 'writer-w%d' % number
        lease = claim(self.store, session, agent)
        self.assertEqual(lease['topic_id'], topic['topic_id'])
        receipt = submit(self.store, lease['slot'], lease['session'], lease['fence'], distinct_body(self.article_for(topic, session, agent), lang))
        if reviewed:
            review = {'article_sha': receipt['article_sha'], 'reviewer_id': 'reviewer-qa', 'language': lang, 'checked_at': now(),
                      'checks': {k: True for k in quality.REVIEW_CHECKS}, 'notes': 'Synthetic review for an end-to-end test; never evidence.'}
            sha = self.store.put_document(review)
            self.store.mutate(lambda s: s.setdefault('reviews', {}).update({topic['topic_id']: sha}))
        return topic['topic_id']

    def hand_over(self, apply=True):
        return ledger.promote(self.shared, self.store.raw()[0], ledger.read_documents(self.store.directory / 'documents'), apply=apply)

    # -- the Actions side: audit, QA, drain ---------------------------------------------------------------------------

    def audit(self):
        inventory = audit.inventory_bilingual(AdapterClient(self.wp.http(False)))
        self.assertTrue(inventory['complete'], inventory['errors'])
        document = self.shared.put_document(inventory)
        self.shared.mutate(lambda s: s.update(inventory_document=document))
        return inventory

    def qa(self):
        inventory = self.audit()
        return {tid: quality.run_qa(self.shared, tid, inventory, self.policy, self.business)['status']
                for tid in quality.pending_qa(self.shared, self.policy)}

    def publisher(self, **release):
        merged = {**self.release, **release}
        document = self.shared.read()['inventory_document']
        publisher = Publisher(self.shared, AdapterClient(self.wp.http(True)), self.shared.get_document(document), self.policy,
                              self.business, lambda: merged, lambda: {'test': True})
        return publisher

    def drain(self, **release):
        return pipeline.drain(self.publisher(**release), sleep=lambda _seconds: None)

    def state(self):
        return self.shared.read()

    def two_vietnamese_one_english(self):
        ids = [self.draft('vi', VI[0]), self.draft('vi', VI[1]), self.draft('en', EN[0])]
        self.assertEqual(self.hand_over()['status'], 'FAST_FORWARD')
        self.assertEqual(self.qa(), {i: 'PASS' for i in ids})
        return ids


class FullLineTests(Line):
    def test_submit_hand_over_qa_queue_publish_receipt_with_vietnamese_first(self):
        vi1, vi2, en1 = self.two_vietnamese_one_english()
        before = self.state()
        self.assertEqual({t['status'] for t in before['topics'].values()}, {'READY'})
        self.assertEqual(before['receipts'], {})
        result = self.drain()
        after = self.state()
        # The two-post pilot budget goes to the Vietnamese drafts; English waits, still READY.
        self.assertEqual([p['topic_id'] for p in result['published']], [vi1, vi2])
        self.assertIsNone(result['halted'])
        self.assertEqual(set(after['receipts']), {vi1, vi2})
        self.assertEqual(after['topics'][en1]['status'], 'READY')
        self.assertEqual([p['topic_id'] for p in self.wp.created], [vi1, vi2])
        for tid in (vi1, vi2):
            receipt = after['receipts'][tid]
            post = self.wp.posts_for(tid)[0]
            self.assertEqual((receipt['wp_id'], receipt['url'], receipt['language']), (post['id'], post['link'], 'vi'))
            self.assertTrue(receipt['url'].startswith(SITE + '/vi/'))
            self.assertEqual(after['intents'][tid]['phase'], 'PUBLISHED')
            self.assertEqual(after['intents'][tid]['post_check']['status'], 'PASSED')
            self.assertEqual(self.shared.get_document(receipt['document'])['integrity']['status'], 'MATCH')
        validate(after)

    def test_running_the_drain_again_changes_nothing(self):
        self.two_vietnamese_one_english()
        self.drain()
        snapshot = copy.deepcopy(self.state()['receipts'])
        posts = len(self.wp.post_requests())
        for _ in range(3):
            again = self.drain()
            self.assertEqual(again['published'], [])
        self.assertEqual(self.state()['receipts'], snapshot)
        self.assertEqual(len(self.wp.post_requests()), posts)
        self.assertEqual(len(self.wp.created), 2)

    def test_the_next_stage_publishes_the_rest_only_after_two_public_pages_passed(self):
        vi1, vi2, en1 = self.two_vietnamese_one_english()
        self.drain()
        scale = dict(stage='controlled-scale', approved_capacity=10, maximum_daily_posts=10, expansion_approval_ref='e2e-synthetic')
        self.assertEqual([p['topic_id'] for p in self.drain(**scale)['published']], [en1])
        self.assertEqual(len(self.wp.created), 3)
        self.assertEqual(self.state()['receipts'][en1]['language'], 'en')

    def test_scale_is_refused_while_the_public_page_checks_have_not_passed(self):
        vi1, vi2, en1 = self.two_vietnamese_one_english()
        self.wp.page_faults.add('canonical')
        self.drain()
        self.assertEqual(len(self.state()['receipts']), 2)
        scale = dict(stage='controlled-scale', approved_capacity=10, maximum_daily_posts=10, expansion_approval_ref='e2e-synthetic')
        with self.assertRaisesRegex(ValueError, 'public-page check passed'):
            self.drain(**scale)
        self.assertEqual(len(self.wp.created), 2)

    def test_a_draft_without_a_review_waits_and_is_not_sent_to_repair(self):
        unreviewed = self.draft('vi', VI[2], reviewed=False)
        reviewed = self.draft('vi', VI[0])
        self.hand_over()
        self.assertEqual(self.qa(), {reviewed: 'PASS'})
        self.assertEqual(self.state()['topics'][unreviewed]['status'], 'DRAFT_READY')
        self.assertEqual([p['topic_id'] for p in self.drain()['published']], [reviewed])

    def test_a_ready_draft_whose_qa_predates_the_policy_is_qualified_again_before_it_can_publish(self):
        vi1 = self.draft('vi', VI[0])
        self.hand_over()
        self.qa()
        self.assertEqual(quality.pending_qa(self.shared, self.policy), [])
        stricter = dict(self.policy, score_threshold=self.policy['score_threshold'] - 5)  # any change of the policy changes its digest
        self.assertEqual(quality.pending_qa(self.shared, stricter), [vi1])
        self.policy.update(stricter)
        skipped = self.drain()
        self.assertIn('run QA again', skipped['skipped'][vi1])  # the old report is not accepted; the topic is neither sent back nor published
        self.assertEqual(self.state()['topics'][vi1]['status'], 'READY')
        self.assertEqual(self.wp.created, [])
        self.assertEqual(self.qa(), {vi1: 'PASS'})
        self.assertEqual([p['topic_id'] for p in self.drain()['published']], [vi1])

    def test_default_configuration_publishes_nothing(self):
        self.two_vietnamese_one_english()
        release = load(ROOT / 'config/release.json')
        with self.assertRaisesRegex(ValueError, 'OFF'):
            pipeline.drain(self.publisher(**release))
        self.assertEqual(self.wp.created, [])
        self.assertEqual(self.wp.post_requests(), [])

    def test_the_adapter_not_being_installed_stops_before_anything_is_reserved(self):
        self.two_vietnamese_one_english()
        self.wp.preflight_status = 404
        result = self.drain()
        self.assertIn('Publishing stopped', result['halted'])
        self.assertEqual(self.state()['intents'], {})
        self.assertEqual(self.wp.post_requests(), [])


class HandOverTests(Line):
    def test_a_dry_run_changes_nothing_and_a_second_hand_over_is_a_no_op(self):
        self.draft('vi', VI[0])
        self.assertEqual(self.hand_over(apply=False)['applied'], False)
        self.assertEqual(self.api.writes, 0)
        self.assertTrue(self.hand_over()['applied'])
        writes = self.api.writes
        again = self.hand_over()
        self.assertEqual((again['status'], again['applied']), ('ALREADY_INCLUDED', False))
        self.assertEqual(self.api.writes, writes)

    def test_a_session_that_kept_working_on_a_stale_ledger_is_refused_not_merged(self):
        first = self.draft('vi', VI[0])
        self.hand_over()
        self.qa()  # the shared ledger moves on: QA events the session does not have
        self.draft('vi', VI[1])  # ... while the session carries on from its old copy
        refused = self.hand_over()
        self.assertEqual(refused['status'], 'DIVERGED')
        self.assertFalse(refused['applied'])
        self.assertEqual(self.state()['topics'][first]['status'], 'READY')  # nothing of the shared ledger was lost
        self.assertEqual(len(self.state()['topics']), 1)


class NetworkFaultTests(Line):
    def one_ready(self):
        tid = self.draft('vi', VI[0])
        self.hand_over()
        self.qa()
        return tid

    def test_a_connection_that_never_opened_is_retried_by_the_next_run_with_one_post_in_total(self):
        tid = self.one_ready()
        self.wp.fail('POST', '/posts', 'refuse')
        first = self.drain()
        self.assertIn('Publishing stopped', first['halted'])
        state = self.state()
        self.assertEqual((state['intents'][tid]['phase'], state['topics'][tid]['status']), ('NOT_SENT', 'READY'))
        self.assertEqual(self.wp.created, [])
        second = self.drain()
        self.assertEqual([p['topic_id'] for p in second['published']], [tid])
        self.assertEqual(len(self.wp.created), 1)

    def test_a_timeout_after_wordpress_published_is_reconciled_in_the_same_run(self):
        tid = self.one_ready()
        self.wp.fail('POST', '/posts', 'timeout_after')
        result = self.drain()
        self.assertEqual([p['topic_id'] for p in result['published']], [tid])
        self.assertIsNone(result['halted'])
        self.assertEqual(len(self.wp.post_requests()), 1)
        self.assertEqual(len(self.wp.created), 1)
        self.assertEqual(self.state()['intents'][tid]['phase'], 'PUBLISHED')

    def test_a_connection_reset_and_a_server_error_after_publishing_are_reconciled_too(self):
        for kind in ('reset_after', 'http500_after'):
            with self.subTest(kind):
                self.setUp()
                tid = self.one_ready()
                self.wp.fail('POST', '/posts', kind)
                self.assertEqual([p['topic_id'] for p in self.drain()['published']], [tid])
                self.assertEqual((len(self.wp.post_requests()), len(self.wp.created)), (1, 1))

    def test_when_the_adapter_is_unreachable_too_the_outcome_stays_unknown_and_the_next_run_resolves_it(self):
        tid = self.one_ready()
        self.wp.fail('POST', '/posts', 'timeout_after')
        self.wp.fail('GET', '/posts/by-key/' + self.key(tid), 'timeout_before', count=3)  # the read-only retries are used up
        first = self.drain()
        self.assertIn('Publishing stopped', first['halted'])
        state = self.state()
        self.assertEqual(state['intents'][tid]['phase'], 'NEEDS_RECONCILIATION')
        self.assertEqual(state['receipts'], {})
        self.assertEqual(len(self.wp.created), 1)  # WordPress did publish it
        second = self.drain()
        self.assertEqual(second['reconciled'][tid]['status'], 'PUBLISHED')
        self.assertEqual(self.state()['intents'][tid]['phase'], 'PUBLISHED')
        self.assertEqual(len(self.wp.post_requests()), 1)  # never sent again
        self.assertEqual(len(self.wp.created), 1)

    def test_a_request_that_never_arrived_is_closed_only_after_the_grace_period_and_then_sent_once(self):
        tid = self.one_ready()
        self.wp.fail('POST', '/posts', 'timeout_before')
        self.assertIn('Publishing stopped', self.drain()['halted'])
        self.assertEqual(self.state()['intents'][tid]['phase'], 'NEEDS_RECONCILIATION')
        waiting = self.drain()
        self.assertIn('Unresolved publication outcome', waiting['halted'])  # still inside the grace period
        self.assertEqual(len(self.wp.post_requests()), 1)
        long_ago = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=3)).isoformat()
        self.shared.mutate(lambda s: s['intents'][tid].update(reserved_at=long_ago, reserved_epoch=0))
        resumed = self.drain()
        self.assertEqual(resumed['reconciled'][tid]['phase'], 'REJECTED')
        self.assertEqual([p['topic_id'] for p in resumed['published']], [tid])
        self.assertEqual((len(self.wp.post_requests()), len(self.wp.created)), (2, 1))  # one lost request, one that arrived

    def test_a_refusal_that_leaves_a_draft_is_held_not_counted_and_never_sent_again(self):
        tid = self.one_ready()
        original = self.wp.create

        def drafted(payload):
            response = original(payload)
            self.wp.created[-1]['status'] = 'draft'
            raise self.wp.error(500, 'thuha_permalink_mismatch')
        self.wp.create = drafted
        halted = self.drain()['halted']
        self.assertIn('Publishing stopped', halted)
        state = self.state()
        self.assertEqual((state['intents'][tid]['phase'], state['topics'][tid]['status'], state['receipts']), ('DRAFT_HELD', 'BLOCKED', {}))
        self.assertEqual(quota_unresolved(state), [tid])
        self.assertIn('Unresolved', self.drain()['halted'])
        self.assertEqual(len(self.wp.post_requests()), 1)
        self.wp.created[-1]['status'] = 'publish'  # a person publishes the draft in WordPress
        resolved = self.drain()
        self.assertEqual(resolved['reconciled'][tid]['status'], 'PUBLISHED')
        self.assertEqual(self.state()['topics'][tid]['status'], 'PUBLISHED')
        self.assertEqual(len(self.wp.post_requests()), 1)

    def key(self, tid):
        from thuha.publisher import idempotency_key
        return idempotency_key(tid, self.state()['submissions'][tid]['article_sha'])


class PublicPageTests(Line):
    def test_a_failing_public_page_never_holds_up_the_next_post_and_is_rechecked_later(self):
        vi1, vi2, en1 = self.two_vietnamese_one_english()
        self.wp.page_faults.add('canonical')
        result = self.drain()
        self.assertEqual([p['topic_id'] for p in result['published']], [vi1, vi2])  # the second was not held up by the first
        self.assertIsNone(result['halted'])
        state = self.state()
        for tid in (vi1, vi2):
            check = state['intents'][tid]['post_check']
            self.assertEqual((state['topics'][tid]['status'], check['status']), ('PUBLISHED', 'WARNING'))
            self.assertIn('canonical', check['problem'].lower())
        # Not due yet (back-off); once the page is fixed and the back-off passed, the next drain passes it.
        self.assertEqual(self.drain()['post_checks'], {})
        self.wp.page_faults.clear()
        for tid in (vi1, vi2):
            self.shared.mutate(lambda s, tid=tid: s['intents'][tid]['post_check'].update(next_attempt_after=0))
        self.assertEqual(self.drain()['post_checks'], {vi1: 'PASSED', vi2: 'PASSED'})

    def test_each_kind_of_public_page_problem_is_only_a_warning(self):
        for fault in ('canonical', 'lang', 'noindex', 'schema', 'down'):
            with self.subTest(fault):
                self.setUp()
                tid = self.draft('vi', VI[0])
                self.hand_over()
                self.qa()
                self.wp.page_faults.add(fault)
                self.assertEqual([p['topic_id'] for p in self.drain()['published']], [tid])
                self.assertEqual(self.state()['intents'][tid]['post_check']['status'], 'WARNING')

    def test_content_that_wordpress_changed_stops_new_posts_until_a_person_acknowledges(self):
        vi1 = self.draft('vi', VI[0])
        vi2 = self.draft('vi', VI[1])
        self.hand_over()
        self.qa()
        self.wp.stored_title_suffix = ' (edited by a plugin)'
        first = self.drain(maximum_daily_posts=2, pilot_max_posts=2)
        self.assertEqual([p['topic_id'] for p in first['published']], [vi1])  # published; the alert stops the next one
        self.assertIn('integrity alert', first['halted'])
        self.assertEqual(len(self.wp.created), 1)
        publisher = self.publisher()
        publisher.acknowledge(vi1, 'Compared the stored title with the reviewed one in WordPress by hand')
        self.wp.stored_title_suffix = ''
        self.assertEqual([p['topic_id'] for p in self.drain()['published']], [vi2])


class CeilingTests(Line):
    def fill(self, vi):
        """The live site already holds `vi` Vietnamese posts (published through the plugin or not)."""
        for i in range(vi):
            slug = 'bai-viet-co-san-%d' % i
            self.wp.rows.append({'id': 5000 + i, 'type': 'post', 'link': post_url('vi', slug), 'slug': slug, 'status': 'publish',
                                 'title': 'Bài viết có sẵn %d' % i, 'content': '<p>Nội dung có sẵn số %d.</p>' % i, 'modified_gmt': '2026-10-01T00:00:00',
                                 'language': 'vi', 'categories': [152], 'featured_media': 0, 'meta': {}})

    def test_the_five_hundredth_post_is_allowed_and_the_five_hundred_and_first_never(self):
        self.fill(498)  # 498 + the fixture's own Vietnamese post = 499
        ids = [self.draft('vi', VI[0]), self.draft('vi', VI[1])]
        english = self.draft('en', EN[0])
        self.hand_over()
        self.qa()
        result = self.drain()
        self.assertEqual([p['topic_id'] for p in result['published']], [ids[0], english])
        self.assertEqual(result['languages_at_ceiling'], ['vi'])
        self.assertEqual(self.state()['topics'][ids[1]]['status'], 'READY')
        self.assertEqual(len([p for p in self.wp.created if p['language'] == 'vi']), 1)


class WiringTests(unittest.TestCase):
    """The workflow that runs all of this on a schedule, read as text: the order and the gates are part of the contract."""

    def workflow(self, name):
        return (ROOT / '.github/workflows' / name).read_text(encoding='utf-8')

    def test_the_scheduled_workflow_hands_over_then_checks_then_publishes_inside_the_protected_gate(self):
        text = self.workflow('thuha-ready-publisher.yml')
        queue, gate = text.index('  queue:'), text.index('  protected-publish:')
        self.assertLess(queue, gate)
        outside, inside = text[queue:gate], text[gate:]
        # Outside the protected environment (no WordPress secret): hand-over first, then inventory, then English QA only.
        order = [outside.index(x) for x in ('thuha.cli --remote promote --apply', 'audit --max-age 18000', 'qa --pending --language en')]
        self.assertEqual(order, sorted(order))
        self.assertNotIn('THUHA_WP_', outside)
        self.assertNotIn('--mode drain', outside)
        # Inside it: adapter check, authenticated inventory, QA of everything reviewed, then the drain.
        order = [inside.index(x) for x in ('adapter-preflight', ' audit', 'qa --pending', 'publisher --mode drain')]
        self.assertEqual(order, sorted(order))
        self.assertIn('environment: thuha-production', inside)
        self.assertIn('needs.preflight.outputs.may_publish', inside)
        for gate_condition in ("release.get('enabled')", "release.get('approved')", 'approval_ref', 'cross_publisher_coordination_verified', 'languages_enabled'):
            self.assertIn(gate_condition, text)

    def test_a_merged_ledger_triggers_the_quality_run_that_starts_the_hand_over(self):
        quality = self.workflow('quality.yml')
        self.assertIn("'data/state/**'", quality)
        self.assertIn("'data/documents/**'", quality)
        self.assertIn("workflows: ['ThuHa V4 quality']", self.workflow('thuha-ready-publisher.yml'))

    def test_manual_runs_can_promote_acknowledge_and_reconcile(self):
        self.assertIn('promote) python3 -m thuha.cli --remote promote --apply', self.workflow('maintenance.yml'))
        publisher = self.workflow('publisher.yml')
        for mode in ('acknowledge', 'reconcile', 'verify'):
            self.assertIn(mode, publisher)

    def test_nothing_in_the_repository_switches_production_on(self):
        release = load(ROOT / 'config/release.json')
        self.assertFalse(release['enabled'])
        self.assertFalse(release['approved'])
        self.assertEqual(release['languages_enabled'], [])
        self.assertTrue(release['paused'])


if __name__ == '__main__':
    unittest.main()
