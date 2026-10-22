"""Safe adaptations of wp-aiwriter's queue/publisher workflow."""
import unittest
from unittest.mock import Mock
from thuha.pipeline import brief, remaining_budget, drain


class QueuePipelineTests(unittest.TestCase):
    def test_brief_is_readonly_and_only_unclaimed_planned(self):
        state = {
            'topics': {
                'TH-000002': {'status': 'READY'},
                'TH-000001': {'status': 'PLANNED', 'proposed_title': 'A', 'category_id': 113},
                'TH-000003': {'status': 'PLANNED', 'proposed_title': 'B'},
            },
            'leases': {'W2': {'topic_id': 'TH-000003'}},
        }
        out = brief(state, 10)
        self.assertEqual([x['topic_id'] for x in out['topics']], ['TH-000001'])
        self.assertEqual(out['wordpress_writes'], 0)
        with self.assertRaises(ValueError):
            brief(state, 0)

    def test_budget_never_counts_unverified_as_capacity(self):
        release = {'stage': 'pilot', 'pilot_max_posts': 2, 'maximum_daily_posts': 2}
        state = {'intents': {
            'TH-000001': {'phase': 'NEEDS_RECONCILIATION', 'reserved_at': '2026-10-22T01:00:00Z'}
        }}
        result = remaining_budget(state, release, '2026-10-22')
        self.assertEqual(result['remaining'], 1)
        self.assertEqual(result['unresolved_intents'], ['TH-000001'])

    def test_default_off_cannot_publish_or_write(self):
        store = Mock(durable_remote=True)
        pub = Mock(store=store)
        pub.release_loader.return_value = {
            'enabled': False, 'approved': False, 'paused': True
        }
        with self.assertRaisesRegex(ValueError, 'OFF'):
            drain(pub, sleep=lambda _: None)
        pub.publish.assert_not_called()

    def test_successful_drain_never_exceeds_release_limit(self):
        store = Mock(durable_remote=True)
        state = {'topics': {
            'TH-000001': {'status': 'READY'},
            'TH-000002': {'status': 'READY'},
            'TH-000003': {'status': 'READY'},
        }, 'intents': {}}
        store.read.return_value = state
        release = {'stage': 'pilot', 'pilot_max_posts': 2,
                   'maximum_daily_posts': 2,
                   'minimum_post_interval_seconds': 0}
        pub = Mock(store=store)
        pub.release_loader.return_value = release
        pub.publish.side_effect = lambda topic_id: {'topic_id': topic_id, 'verified': True}
        from unittest.mock import patch
        with patch('thuha.pipeline.release_guard') as guard:
            result = drain(pub, sleep=lambda _: None)
        self.assertEqual(result['attempted_and_readback_verified'], 2)
        self.assertEqual(pub.publish.call_count, 2)
        self.assertEqual(result['remaining_ready_not_attempted'], 1)
        self.assertTrue(guard.called)


if __name__ == '__main__':
    unittest.main()
