"""The whole line against a simulated WordPress, over real HTTP plumbing:

writer session ledger -> hand-over to the shared ledger -> QA -> shared queue -> publisher -> receipt,
including network faults, repeated runs and two publishers at once.

WordPress is simulated (tests/fake_wordpress.py). Passing here shows the factory's own logic holds up; it is not
evidence about the real site, the native Vietnamese plugin or Yoast.
"""
import contextlib
import copy
import datetime as dt
import errno
import io
import json
import os
import random
import re
import threading
import time
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch
import test_factory as tf
from fake_wordpress import FakeWordPress, PLUGIN
from test_remote_and_recovery import MemoryGitHub
from thuha import audit, cli, dashboard, ledger, pipeline, quality
from thuha import publisher as pubmod
from thuha.quota import LanguageComplete
from thuha.adapter import AdapterClient
from thuha.common import ROOT, SITE, digest, load, now, save
from thuha.coordinator import claim, submit
from thuha.language import post_url
from thuha.publisher import Publisher, quota_unresolved
from thuha.research import intake
from thuha.store import GitStore, LocalStore, event, validate

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

    def test_explicit_owner_auto_scale_continues_after_two_verified_posts(self):
        vi1, vi2, en1 = self.two_vietnamese_one_english()
        auto = dict(stage='auto-scale', approved_capacity=10, maximum_daily_posts=10,
                    expansion_approval_ref='e2e-synthetic')
        result = self.drain(**auto)
        self.assertEqual([p['topic_id'] for p in result['published']], [vi1, vi2, en1])
        self.assertEqual(len(self.state()['receipts']), 3)
        self.assertIsNone(result['halted'])
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

    def test_a_draft_without_a_review_passes_qa_and_publishes(self):
        unreviewed = self.draft('vi', VI[2], reviewed=False)
        reviewed = self.draft('vi', VI[0])
        self.hand_over()
        self.assertEqual(self.qa(), {unreviewed: 'PASS', reviewed: 'PASS'})
        self.assertEqual(self.state()['topics'][unreviewed]['status'], 'READY')
        self.assertNotIn(unreviewed, self.state()['reviews'])
        self.assertEqual({p['topic_id'] for p in self.drain()['published']}, {reviewed, unreviewed})
        self.assertNotIn(unreviewed, self.state()['reviews'])

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

    def test_the_dashboard_shows_the_queue_the_checks_the_alerts_and_the_blockers(self):
        unreviewed = self.draft('vi', VI[2], reviewed=False)
        vi1, vi2 = self.draft('vi', VI[0]), self.draft('vi', VI[1])
        before = dashboard.report(self.store, self.inv, self.release)  # the session ledger before any hand-over
        self.assertEqual(set(before['queue']['vi']['awaiting_qa']), {unreviewed, vi1, vi2})
        self.assertNotIn('awaiting_review', before['queue']['vi'])
        self.hand_over()
        self.qa()
        self.wp.page_faults.add('canonical')
        self.drain()
        value = dashboard.report(self.shared, self.shared.get_document(self.state()['inventory_document']), self.release)
        self.assertEqual(value['queue']['vi']['published'], [unreviewed, vi1])
        self.assertEqual(value['queue']['vi']['qa_pass'], [vi2])
        self.assertEqual(value['post_checks']['counts'], {'WARNING': 2})
        self.assertEqual(sorted(value['post_checks']['warnings']), [unreviewed, vi1])
        self.assertEqual(value['factory_published_receipts'], 2)
        self.assertEqual(value['languages']['vi']['published_live'], 3)  # the fixture's own Vietnamese post plus the two published since the audit
        self.assertEqual(value['languages']['vi']['remaining'], 497)
        self.assertFalse(any('independent review' in b for b in value['blockers']))
        self.assertEqual(value['open_alerts'], [])
        text = dashboard.write_report(value, self.temp.name) or (Path(self.temp.name) / 'dashboard.md').read_text(encoding='utf-8')
        for heading in ('Shared queue', 'Public-page checks after publication', 'warning TH-VI-0002'):
            self.assertIn(heading, text)

    def test_the_dashboard_says_when_no_image_has_alt_text_in_a_language(self):
        english_only = copy.deepcopy(self.inv)
        english_only['media'] = [m for m in english_only['media'] if m['id'] == 50]
        english_only['media_library'] = 'complete'
        self.assertFalse(any(b.startswith('NEEDS_MEDIA') for b in dashboard.report(self.store, dict(english_only, media_library=None), self.release)['blockers']))
        value = dashboard.report(self.store, english_only, self.release)
        self.assertTrue(any(b.startswith('NEEDS_MEDIA') and ' vi ' in b for b in value['blockers']))
        self.assertFalse(any(b.startswith('NEEDS_MEDIA') and ' en ' in b for b in value['blockers']))

    def test_an_explicit_stopped_release_publishes_nothing(self):
        self.two_vietnamese_one_english()
        release = dict(load(ROOT / 'config/release.json'), enabled=False, approved=False, paused=True, languages_enabled=[])
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


class ReviewFindingsTests(Line):
    """Defects an independent reviewer reproduced; each failed before its fix."""

    def one_ready(self):
        tid = self.draft('vi', VI[0])
        self.hand_over()
        self.qa()
        return tid

    def test_a_closed_intent_never_blocks_qa_again(self):
        tid = self.one_ready()
        self.wp.fail('POST', '/posts', 'refuse')
        self.drain()
        self.assertEqual(self.state()['intents'][tid]['phase'], 'NOT_SENT')
        self.policy.update(score_threshold=self.policy['score_threshold'] - 5)  # a merged policy change invalidates the old report
        self.assertEqual(quality.pending_qa(self.shared, self.policy), [tid])
        self.assertEqual(self.qa(), {tid: 'PASS'})  # used to raise "Publication pending" forever
        self.assertEqual([p['topic_id'] for p in self.drain()['published']], [tid])

    def test_a_repaired_draft_after_a_rejected_intent_can_be_qualified_again(self):
        tid = self.one_ready()
        self.wp.fail('POST', '/posts', 'reject:409:thuha_slug_conflict')
        self.drain()
        state = self.state()
        self.assertEqual((state['intents'][tid]['phase'], state['topics'][tid]['status']), ('REJECTED', 'NEEDS_REPAIR'))
        lease = claim(self.shared, 'session-repair', 'writer-repair')
        article = dict(self.shared.get_document(state['submissions'][tid]['article_sha']), session='session-repair', agent_id='writer-repair')
        article['body_html'] = article['body_html'].replace('<p>', '<p>Bổ sung một câu. ', 1)
        submit(self.shared, lease['slot'], lease['session'], lease['fence'], article)
        self.assertEqual(quality.pending_qa(self.shared, self.policy), [tid])
        self.assertEqual(self.qa(), {tid: 'PASS'})

    def test_a_stale_review_does_not_send_a_repaired_draft_back_to_repair(self):
        tid = self.one_ready()
        publisher = self.publisher()
        self.assertTrue(pipeline.demote(publisher, tid, 'live duplicate', ['DUPLICATE_OR_CANNIBALIZATION']))
        lease = claim(self.shared, 'session-repair', 'writer-repair')
        article = dict(self.shared.get_document(self.state()['submissions'][tid]['article_sha']), session='session-repair', agent_id='writer-repair')
        article['body_html'] = article['body_html'].replace('<p>', '<p>Bổ sung. ', 1)
        submit(self.shared, lease['slot'], lease['session'], lease['fence'], article)
        self.assertEqual(self.state()['topics'][tid]['status'], 'DRAFT_READY')
        self.assertEqual(self.qa(), {tid: 'PASS'})  # the old review never gates the repaired revision
        self.assertEqual(self.state()['topics'][tid]['status'], 'READY')

    def test_a_draft_held_by_wordpress_that_a_person_deleted_closes_after_the_grace_period_and_can_publish_again(self):
        tid = self.one_ready()
        original = self.wp.create

        def drafted(payload):
            original(payload)
            self.wp.created[-1]['status'] = 'draft'
            raise self.wp.error(422, 'thuha_content_altered')
        self.wp.create = drafted
        self.drain()
        self.assertEqual(self.state()['intents'][tid]['phase'], 'DRAFT_HELD')
        self.wp.create = original
        self.wp.created.clear()  # the stray draft is deleted in WordPress
        self.assertIn('Unresolved', self.drain()['halted'])  # inside the grace period nothing is concluded
        long_ago = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=5)).isoformat()
        self.shared.mutate(lambda s: s['intents'][tid].update(reserved_at=long_ago, reserved_epoch=0))
        result = self.drain()
        self.assertEqual(result['reconciled'][tid]['phase'], 'REJECTED')
        self.assertEqual(self.state()['intents'][tid]['phase'] if tid not in result['published'] else 'x', 'PUBLISHED')
        self.assertEqual([p['topic_id'] for p in result['published']], [tid])

    def test_an_error_after_the_request_was_delivered_is_never_taken_for_a_request_that_never_left(self):
        tid = self.one_ready()
        original = self.wp.create

        def processed_then_unreachable(payload):
            original(payload)  # WordPress processed and published the post ...
            raise urllib.error.URLError(OSError(errno.EHOSTUNREACH, 'No route to host'))  # ... the answer never came back
        self.wp.create = processed_then_unreachable
        result = self.drain()
        self.assertEqual([p['topic_id'] for p in result['published']], [tid])  # reconciled by key, not closed as NOT_SENT
        self.assertEqual((len(self.wp.post_requests()), len(self.wp.created)), (1, 1))
        self.assertEqual(self.state()['intents'][tid]['phase'], 'PUBLISHED')

    def test_a_qa_failure_in_a_scheduled_batch_is_not_a_failed_step(self):
        tid = self.one_ready()
        self.policy.update(score_threshold=self.policy['score_threshold'] - 5)
        out = io.StringIO()
        real = cli.load
        with patch('thuha.cli.GitStore', lambda: self.shared), patch('thuha.cli.load', lambda p: self.policy if str(p).endswith('config/qa.json') else real(p)), \
                patch('thuha.cli.inventory_for', lambda store, path, max_age=None: self.shared.get_document(self.state()['inventory_document'])), \
                patch('thuha.quality.run_qa', return_value={'status': 'FAIL'}), contextlib.redirect_stdout(out):
            pending = cli.main(['--remote', 'qa', '--pending'])
            single = cli.main(['--remote', 'qa', '--topic-id', tid])
        self.assertEqual((pending, single), (0, 1))  # the scheduled batch reports in the ledger; an explicit single run still says FAIL


    def test_recording_a_review_leaves_an_event_so_the_hand_over_sees_it(self):
        tid = self.draft('en', EN[0], reviewed=False)
        sha = self.store.read()['submissions'][tid]['article_sha']
        review = Path(self.temp.name) / 'review.json'
        review.write_text(json.dumps({'article_sha': sha, 'reviewer_id': 'claude-editorial-reviewer', 'language': 'en', 'checked_at': now(),
                                      'checks': {k: True for k in quality.REVIEW_CHECKS}, 'notes': 'Synthetic review through the command line.'}))
        before = len(self.store.read()['events'])
        with patch.dict(os.environ, {'THUHA_REVIEWER_ID': 'claude-editorial-reviewer'}), contextlib.redirect_stdout(io.StringIO()):
            cli.main(['--state-dir', self.temp.name, 'review', '--file', str(review), '--topic-id', tid])
        state = self.store.read()
        self.assertIn(tid, state['reviews'])
        self.assertEqual([e['action'] for e in state['events']][before:], ['REVIEW'])
        self.assertEqual(self.hand_over()['status'], 'FAST_FORWARD')  # and it travels


class ConcurrencyTests(Line):
    def test_two_publishers_draining_at_once_never_publish_a_topic_twice(self):
        for round_number in range(6):
            with self.subTest(round=round_number):
                self.setUp()
                ids = [self.draft('vi', VI[0]), self.draft('vi', VI[1])]
                self.hand_over()
                self.qa()
                results, errors = [], []

                def run():
                    try:
                        results.append(pipeline.drain(self.publisher(), sleep=lambda _s: None))
                    except Exception as exc:  # a refused reservation may raise out of a drain's own checks
                        errors.append(exc)
                threads = [threading.Thread(target=run) for _ in range(2)]
                for t in threads:
                    t.start()
                for t in threads:
                    t.join()
                created = [p['topic_id'] for p in self.wp.created]
                self.assertEqual(len(created), len(set(created)), created)  # never a topic twice
                self.assertLessEqual(len(created), 2)
                state = self.state()
                validate(state)
                self.assertEqual(set(state['receipts']), set(created))  # the ledger and WordPress agree
                for tid in created:
                    self.assertEqual(state['intents'][tid]['phase'], 'PUBLISHED')
                self.assertEqual(len(self.wp.post_requests()), len(created))  # one POST per post: nobody sent a second


class GuardTests(Line):
    """Each safeguard of publish() and drain() alone: remove one and one of these goes red."""

    def ready(self, count=1):
        ids = [self.draft('vi', VI[i]) for i in range(count)]
        self.hand_over()
        self.qa()
        return ids

    def test_a_live_lease_of_another_publisher_stops_the_reservation(self):
        tid = self.ready()[0]
        self.shared.mutate(lambda s: s.update(publisher_lease={'fence': 'someone-else', 'expires_at': time.time() + 600}))
        with self.assertRaisesRegex(ValueError, 'owns the lease'):
            self.publisher().publish(tid)
        self.assertEqual(self.wp.post_requests(), [])
        self.assertEqual(self.state()['intents'], {})

    def test_a_lease_taken_over_between_reservation_and_post_stops_the_post(self):
        tid = self.ready()[0]
        publisher = self.publisher()
        calls = []
        base = publisher.release_loader

        def loader():
            calls.append(1)
            if len(calls) == 2:  # the look just before the POST
                self.shared.mutate(lambda s: s['publisher_lease'].update(fence='thief'))
            return base()
        publisher.release_loader = loader
        with self.assertRaisesRegex(ValueError, 'Stopped after durable intent'):
            publisher.publish(tid)
        self.assertEqual(self.wp.post_requests(), [])
        self.assertEqual(self.state()['intents'][tid]['phase'], 'NOT_SENT')

    def test_the_rate_limit_the_pilot_budget_and_the_changed_draft_each_stop_a_reservation(self):
        first, second, third = self.ready(3)
        publisher = self.publisher(minimum_post_interval_seconds=3600)
        publisher.publish(first)
        with self.assertRaisesRegex(ValueError, 'Publish rate limit'):
            publisher.publish(second)
        publisher = self.publisher()  # no interval: the budget is next
        publisher.publish(second)
        with self.assertRaisesRegex(ValueError, 'budget exhausted'):
            publisher.publish(third)
        self.assertEqual(len(self.wp.created), 2)

    def test_a_draft_that_changes_while_the_payload_is_prepared_is_not_published(self):
        tid = self.ready()[0]
        real = pubmod.build_payload

        def moves_the_ledger(*args):
            self.shared.mutate(lambda s: s['topics'][tid].update(status='NEEDS_REPAIR'))
            return real(*args)
        with patch('thuha.publisher.build_payload', moves_the_ledger):
            with self.assertRaisesRegex(ValueError, 'Draft changed'):
                self.publisher().publish(tid)
        self.assertEqual((self.wp.post_requests(), self.state()['intents']), ([], {}))

    def test_an_unresolved_intent_counts_when_the_last_slot_is_taken_even_if_the_live_count_has_room(self):
        self.fill(498)  # 498 + the fixture's own post = 499 live
        tid = self.ready()[0]

        def other_topic_unresolved(s):
            s['topics']['TH-VI-0099'] = {'language': 'vi', 'status': 'BLOCKED'}
            s['intents']['TH-VI-0099'] = {'phase': 'NEEDS_RECONCILIATION', 'language': 'vi', 'article_sha': 'a' * 64, 'reserved_at': now(), 'reserved_epoch': 0}
        self.shared.mutate(other_topic_unresolved)
        with self.assertRaises(LanguageComplete):
            self.publisher().publish(tid)
        self.assertEqual(self.wp.post_requests(), [])

    def fill(self, vi):
        CeilingTests.fill(self, vi)

    def test_a_full_language_is_refused_before_any_QA_or_payload_work_is_done(self):
        self.fill(499)  # 499 + the fixture's post = 500 live Vietnamese posts
        tid = self.ready()[0]
        publisher = self.publisher()
        with patch.object(publisher, 'prepare', side_effect=AssertionError('QA ran for a language that is already complete')):
            with self.assertRaises(LanguageComplete):
                publisher.publish(tid)
        self.assertEqual(self.state()['intents'], {})

    def test_an_open_alert_stops_a_publication_before_any_request_and_also_at_the_reservation(self):
        first, second = self.ready(2)
        self.wp.readback_override = {'title': 'Edited by a plugin'}
        publisher = self.publisher()
        publisher.publish(first)
        self.assertEqual(len(self.state()['alerts']), 1)
        self.wp.readback_override = {}
        requests = len(self.wp.requests)
        with self.assertRaisesRegex(ValueError, 'integrity alert'):
            publisher.publish(second)
        self.assertEqual(len(self.wp.requests), requests)  # stopped before even asking WordPress anything
        # ... and an alert that appears while the payload is being prepared stops the reservation itself.
        publisher.acknowledge(first, 'Compared the title with the reviewed one in WordPress by hand')
        real = pubmod.build_payload

        def alert_appears(*args):
            self.shared.mutate(lambda s: s.setdefault('alerts', []).append({'id': 'x', 'topic_id': first, 'code': 'INTEGRITY_MISMATCH',
                                                                           'problems': ['title'], 'at': now(), 'acknowledged': False}))
            return real(*args)
        with patch('thuha.publisher.build_payload', alert_appears):
            with self.assertRaisesRegex(ValueError, 'integrity alert'):
                publisher.publish(second)
        self.assertEqual(len(self.wp.created), 1)

    def test_the_github_controls_check_and_the_pilot_size_are_enforced(self):
        tid = self.ready()[0]

        def refuses():
            raise ValueError('Required branch checks/review and environment reviewers are not enforced')
        publisher = self.publisher()
        publisher.security = refuses
        with self.assertRaisesRegex(ValueError, 'not enforced'):
            publisher.publish(tid)
        self.assertEqual(self.state()['intents'], {})
        with self.assertRaisesRegex(ValueError, 'two intents'):
            self.publisher(pilot_max_posts=3).publish(tid)

    def test_what_wordpress_stored_is_compared_field_by_field(self):
        cases = {
            'visible body text': lambda r: r.update(content_raw=r['content_raw'].replace('<h2>', '<h2>Edited ', 1)),
            'category or its language': lambda r: r.update(categories=[20], category_languages=['en']),
            'Yoast SEO fields': lambda r: r['meta'].update(_yoast_wpseo_metadesc='A description nobody reviewed, written by a plugin.'),
            'featured image': lambda r: r.update(featured_media=50),
            'native language marker': lambda r: r.update(language_markers={'is_vi': False, 'taxonomy_vi': True}),
        }
        for problem, change in cases.items():
            with self.subTest(problem):
                self.setUp()
                tid = self.ready()[0]
                original = self.wp.plain_readback

                def altered(post, original=original, change=change):
                    result = original(post)
                    change(result)
                    return result
                self.wp.plain_readback = altered
                receipt = self.publisher().publish(tid)
                self.assertEqual(self.state()['intents'][tid]['phase'], 'PUBLISHED')
                self.assertIn(problem, self.shared.get_document(receipt['document'])['integrity']['problems'])
                self.assertEqual(len(self.state()['alerts']), 1)

    def test_recording_the_same_publication_twice_changes_nothing(self):
        tid = self.ready()[0]
        publisher = self.publisher()
        publisher.publish(tid)
        before = copy.deepcopy(self.state())
        intent = before['intents'][tid]
        again = publisher.finish(tid, self.wp.readback(self.wp.created[0]), 'adapter-reconcile')
        after = self.state()
        self.assertEqual(again['status'], 'PUBLISHED')
        self.assertEqual(after['receipts'], before['receipts'])
        self.assertEqual([e['action'] for e in after['events']].count('PUBLICATION_PUBLISHED'), 1)
        post = dict(self.wp.readback(self.wp.created[0]))
        self.assertEqual(publisher.judge(post, dict(intent, wp_id=post['id'] + 1))[0], 'INCONSISTENT')  # the ID recorded earlier is pinned
        self.assertEqual(publisher.judge(post, intent)[0], 'PUBLISHED')

    def test_a_published_topic_is_never_sent_back_to_repair(self):
        tid = self.ready()[0]
        publisher = self.publisher()
        publisher.publish(tid)
        self.assertFalse(pipeline.demote(publisher, tid, 'too late', ['DUPLICATE_OR_CANNIBALIZATION']))
        self.assertEqual(self.state()['topics'][tid]['status'], 'PUBLISHED')

    def test_the_drain_refuses_to_wait_longer_than_five_minutes_for_the_interval(self):
        first, second = self.ready(2)
        slow = dict(minimum_post_interval_seconds=3600, maximum_daily_posts=2)
        self.assertEqual([p['topic_id'] for p in self.drain(**slow)['published']], [first])
        result = self.drain(**slow)
        self.assertIn('Unsafe publication interval', result['halted'])
        self.assertEqual(len(self.wp.created), 1)

    def test_sync_replans_when_the_session_ledger_moves_while_it_is_being_brought_up_to_date(self):
        self.hand_over()  # an empty hand-over first so the shared ledger exists
        topic_id = self.draft('vi', VI[0])
        self.hand_over()
        self.qa()
        stale = LocalStore(Path(self.temp.name) / 'stale')
        save(stale.path, self.shared.raw()[0])
        self.shared.mutate(lambda s: event(s, 'CONTROL_CHANGE', controls=s['controls']))  # the shared ledger moves on
        original = stale.adopt

        def adopt_after_a_local_write(builder):
            stale.mutate(lambda s: event(s, 'CLAIM', topic_id=topic_id))  # someone writes the session ledger first
            return original(builder)
        stale.adopt = adopt_after_a_local_write
        result = ledger.sync(stale, self.shared, apply=True)
        self.assertFalse(result['applied'])
        self.assertIn('CLAIM', [e['action'] for e in stale.raw()[0]['events']])  # their write was not overwritten


class WiringTests(unittest.TestCase):
    """The workflow that runs all of this on a schedule, read as text: the order and the gates are part of the contract."""

    def workflow(self, name):
        return (ROOT / '.github/workflows' / name).read_text(encoding='utf-8')

    def test_the_scheduled_workflow_hands_over_then_checks_then_publishes_inside_the_protected_gate(self):
        text = self.workflow('thuha-ready-publisher.yml')
        queue, gate = text.index('  queue:'), text.index('  protected-publish:')
        self.assertLess(queue, gate)
        outside, inside = text[queue:gate], text[gate:]
        # Outside the publishing job (no WordPress secret): hand-over first, then inventory, then English QA only.
        order = [outside.index(x) for x in ('thuha.cli --remote promote --apply', 'audit --max-age 18000', 'qa --pending --language en')]
        self.assertEqual(order, sorted(order))
        self.assertNotIn('THUHA_WP_', outside)
        self.assertNotIn('--mode drain', outside)
        # Publishing job: adapter check, authenticated inventory, QA of everything reviewed, then the drain.
        order = [inside.index(x) for x in ('adapter-preflight', ' audit', 'qa --pending', 'publisher --mode drain')]
        self.assertEqual(order, sorted(order))
        self.assertNotIn('environment: thuha-production', inside)
        self.assertNotIn('THUHA_GO_LIVE_APPROVAL', inside)
        self.assertIn('secrets.THUHA_WP_APPLICATION_PASSWORD', inside)
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

    def test_repository_release_requires_explicit_owner_approval(self):
        release = load(ROOT / 'config/release.json')
        if release['enabled']:
            self.assertTrue(release['approved'])
            self.assertFalse(release['paused'])
            self.assertTrue(release['approval_ref'])
            self.assertEqual(set(release['languages_enabled']), {'vi', 'en'})
            self.assertTrue(release['cross_publisher_coordination_verified'])
            self.assertEqual(release['pilot_max_posts'], 2)
        else:
            self.assertFalse(release['approved'])
            self.assertEqual(release['languages_enabled'], [])


if __name__ == '__main__':
    unittest.main()
