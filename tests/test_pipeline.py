"""Safe adaptations of wp-aiwriter's queue/publisher workflow, Vietnamese first."""
import unittest
from unittest.mock import Mock, patch
from thuha.pipeline import brief, remaining_budget, drain, demotable
from thuha.publisher import PublishBlocked
from thuha.quota import LanguageComplete
from thuha.cli import dispatch_qa_ready


def pub_with(state, release, publish):
    store = Mock(durable_remote=True)
    store.read.return_value = state
    pub = Mock(store=store)
    pub.release_loader.return_value = release
    pub.publish.side_effect = publish
    return pub


class QueuePipelineTests(unittest.TestCase):
    def test_brief_is_readonly_vietnamese_first_and_only_unclaimed_planned(self):
        state = {
            'topics': {
                'TH-EN-0002': {'status': 'READY', 'language': 'en'},
                'TH-EN-0001': {'status': 'PLANNED', 'language': 'en', 'proposed_title': 'A', 'category_id': 113},
                'TH-VI-0001': {'status': 'PLANNED', 'language': 'vi', 'proposed_title': 'B'},
                'TH-VI-0002': {'status': 'PLANNED', 'language': 'vi', 'proposed_title': 'C'},
            },
            'leases': {'W2': {'topic_id': 'TH-VI-0002'}},
        }
        out = brief(state, 10)
        self.assertEqual([x['topic_id'] for x in out['topics']], ['TH-VI-0001', 'TH-EN-0001'])
        self.assertEqual(out['wordpress_writes'], 0)
        self.assertEqual([x['topic_id'] for x in brief(state, 10, 'en')['topics']], ['TH-EN-0001'])
        with self.assertRaises(ValueError):
            brief(state, 0)
        with self.assertRaises(ValueError):
            brief(state, 5, 'fr')

    def test_budget_never_counts_unverified_as_capacity(self):
        release = {'stage': 'pilot', 'pilot_max_posts': 2, 'maximum_daily_posts': 2}
        state = {'intents': {
            'TH-VI-0001': {'phase': 'NEEDS_RECONCILIATION', 'reserved_at': '2026-10-22T01:00:00Z'}
        }}
        result = remaining_budget(state, release, '2026-10-22')
        self.assertEqual(result['remaining'], 1)
        self.assertEqual(result['unresolved_intents'], ['TH-VI-0001'])

    def test_default_off_cannot_publish_or_write(self):
        store = Mock(durable_remote=True)
        pub = Mock(store=store)
        pub.release_loader.return_value = {'enabled': False, 'approved': False, 'paused': True}
        with self.assertRaisesRegex(ValueError, 'OFF'):
            drain(pub, sleep=lambda _: None)
        pub.publish.assert_not_called()

    def test_successful_drain_never_exceeds_release_limit_and_publishes_vietnamese_first(self):
        state = {'topics': {
            'TH-EN-0001': {'status': 'READY', 'language': 'en'},
            'TH-VI-0002': {'status': 'READY', 'language': 'vi'},
            'TH-VI-0001': {'status': 'READY', 'language': 'vi'},
        }, 'intents': {}}
        release = {'stage': 'pilot', 'pilot_max_posts': 2, 'maximum_daily_posts': 2,
                   'minimum_post_interval_seconds': 0, 'languages_enabled': ['vi', 'en']}
        pub = pub_with(state, release, lambda tid: {'topic_id': tid, 'verified': True})
        with patch('thuha.pipeline.release_guard') as guard:
            result = drain(pub, sleep=lambda _: None)
        self.assertEqual(result['attempted_and_published'], 2)
        self.assertEqual([c.args[0] for c in pub.publish.call_args_list], ['TH-VI-0001', 'TH-VI-0002'])
        self.assertEqual(result['remaining_ready_not_attempted'], 1)
        self.assertTrue(guard.called)

    def test_language_not_enabled_in_release_is_never_attempted(self):
        state = {'topics': {'TH-VI-0001': {'status': 'READY', 'language': 'vi'},
                            'TH-EN-0001': {'status': 'READY', 'language': 'en'}}, 'intents': {}}
        release = {'stage': 'pilot', 'pilot_max_posts': 2, 'maximum_daily_posts': 2,
                   'minimum_post_interval_seconds': 0, 'languages_enabled': ['en']}
        pub = pub_with(state, release, lambda tid: {'topic_id': tid})
        with patch('thuha.pipeline.release_guard'):
            drain(pub, sleep=lambda _: None)
        self.assertEqual([c.args[0] for c in pub.publish.call_args_list], ['TH-EN-0001'])

    def test_a_language_at_its_ceiling_is_skipped_but_the_other_continues(self):
        state = {'topics': {
            'TH-VI-0001': {'status': 'READY', 'language': 'vi'}, 'TH-VI-0002': {'status': 'READY', 'language': 'vi'},
            'TH-EN-0001': {'status': 'READY', 'language': 'en'}}, 'intents': {}}
        release = {'stage': 'pilot', 'pilot_max_posts': 2, 'maximum_daily_posts': 2,
                   'minimum_post_interval_seconds': 0, 'languages_enabled': ['vi', 'en']}

        def publish(tid):
            if tid.startswith('TH-VI'):
                raise LanguageComplete('Language target reached: vi')
            return {'topic_id': tid}
        pub = pub_with(state, release, publish)
        with patch('thuha.pipeline.release_guard'):
            result = drain(pub, sleep=lambda _: None)
        self.assertEqual(result['languages_at_ceiling'], ['vi'])
        self.assertEqual([c.args[0] for c in pub.publish.call_args_list], ['TH-VI-0001', 'TH-EN-0001'])

    def test_any_other_failure_stops_the_drain_and_says_why(self):
        state = {'topics': {'TH-VI-0001': {'status': 'READY', 'language': 'vi'},
                            'TH-EN-0001': {'status': 'READY', 'language': 'en'}}, 'intents': {}}
        release = {'stage': 'pilot', 'pilot_max_posts': 2, 'maximum_daily_posts': 2,
                   'minimum_post_interval_seconds': 0, 'languages_enabled': ['vi', 'en']}

        def publish(tid):
            raise ValueError('Post identity/status/URL mismatch')
        pub = pub_with(state, release, publish)
        with patch('thuha.pipeline.release_guard'):
            result = drain(pub, sleep=lambda _: None)
        self.assertEqual(pub.publish.call_count, 1)
        self.assertIn('Publishing stopped at TH-VI-0001', result['halted'])
        pub.run_post_checks.assert_called_once()  # public-page checks are still attempted when publishing stops

    def test_an_unresolved_intent_is_reconciled_first_and_stops_the_run_while_unknown(self):
        state = {'topics': {'TH-VI-0001': {'status': 'READY', 'language': 'vi'}},
                 'intents': {'TH-VI-0002': {'phase': 'NEEDS_RECONCILIATION', 'reserved_at': '2026-10-22T01:00:00Z'}}}
        release = {'stage': 'pilot', 'pilot_max_posts': 2, 'maximum_daily_posts': 2,
                   'minimum_post_interval_seconds': 0, 'languages_enabled': ['vi', 'en']}
        pub = pub_with(state, release, lambda tid: {'topic_id': tid})
        pub.reconcile_all.return_value = {'TH-VI-0002': {'status': 'UNRESOLVED'}}
        with patch('thuha.pipeline.release_guard'):
            result = drain(pub, sleep=lambda _: None)
        pub.reconcile_all.assert_called_once()
        pub.publish.assert_not_called()
        self.assertIn('Unresolved publication outcome', result['halted'])

    def test_an_open_integrity_alert_stops_publication(self):
        state = {'topics': {'TH-VI-0001': {'status': 'READY', 'language': 'vi'}}, 'intents': {},
                 'alerts': [{'topic_id': 'TH-VI-0009', 'acknowledged': False}]}
        release = {'stage': 'pilot', 'pilot_max_posts': 2, 'maximum_daily_posts': 2,
                   'minimum_post_interval_seconds': 0, 'languages_enabled': ['vi']}
        pub = pub_with(state, release, lambda tid: {'topic_id': tid})
        with patch('thuha.pipeline.release_guard'):
            result = drain(pub, sleep=lambda _: None)
        pub.publish.assert_not_called()
        self.assertIn('integrity alert', result['halted'])

    def test_a_topic_that_cannot_publish_goes_to_repair_and_the_queue_moves_on(self):
        state = {'topics': {'TH-VI-0001': {'status': 'READY', 'language': 'vi'},
                            'TH-VI-0002': {'status': 'READY', 'language': 'vi'}}, 'intents': {}}
        release = {'stage': 'pilot', 'pilot_max_posts': 2, 'maximum_daily_posts': 2,
                   'minimum_post_interval_seconds': 0, 'languages_enabled': ['vi']}

        def publish(tid):
            if tid == 'TH-VI-0001':
                raise PublishBlocked('Fresh QA failed', ['DUPLICATE_OR_CANNIBALIZATION'])
            return {'topic_id': tid}
        pub = pub_with(state, release, publish)
        with patch('thuha.pipeline.release_guard'), patch('thuha.pipeline.demote') as demote:
            result = drain(pub, sleep=lambda _: None)
        demote.assert_called_once()
        self.assertEqual(list(result['sent_back_to_repair']), ['TH-VI-0001'])
        self.assertEqual([x['topic_id'] for x in result['published']], ['TH-VI-0002'])
        self.assertIsNone(result['halted'])

    def test_failures_a_fresh_audit_can_clear_are_retried_not_demoted(self):
        self.assertFalse(demotable(['INTERNAL_LINK_NOT_LIVE_VERIFIED', 'INSUFFICIENT_REAL_INTERNAL_LINKS']))
        self.assertFalse(demotable(['Inventory is stale']))
        self.assertFalse(demotable([]))
        self.assertTrue(demotable(['DUPLICATE_OR_CANNIBALIZATION']))
        self.assertTrue(demotable(['INTERNAL_LINK_NOT_LIVE_VERIFIED', 'UNAPPROVED_PRICE']))


class QADispatchTests(unittest.TestCase):
    def test_remote_qa_pass_dispatches_without_waiting_for_cron(self):
        store = Mock(durable_remote=True)
        store.api.request.return_value = {}
        status = dispatch_qa_ready(store, ['TH-000001'])
        self.assertEqual(status['status'], 'DISPATCH_ACCEPTED')
        store.api.request.assert_called_once_with(
            'POST', '/repos/thuexemayhanoi/thuha-writer/dispatches',
            {'event_type': 'thuha-qa-ready', 'client_payload': {'topic_ids': ['TH-000001']}}
        )

    def test_offline_qa_never_dispatches_or_publishes(self):
        store = Mock(durable_remote=False)
        self.assertEqual(dispatch_qa_ready(store, ['TH-000001'])['status'], 'LOCAL_ONLY')
        store.api.request.assert_not_called()

    def test_dispatch_failure_keeps_ready_for_fallback(self):
        store = Mock(durable_remote=True)
        store.api.request.side_effect = RuntimeError('transient failure')
        result = dispatch_qa_ready(store, ['TH-000001'])
        self.assertEqual(result['status'], 'DISPATCH_FAILED')
        self.assertEqual(result['topics'], ['TH-000001'])


if __name__ == '__main__':
    unittest.main()
