"""Writer -> automatic QA -> publisher event, on the shared ledger.

A completed draft submitted to the shared ledger is evaluated at once and a pass dispatches `thuha-qa-ready`; a draft stored
while it waits for data is not evaluated and dispatches nothing; a session ledger never dispatches (Actions do not read it);
an unreachable site never turns a stored draft into a failed submit. The hourly run stays the fallback.
"""
import contextlib
import io
import json
import types
import unittest
from pathlib import Path
from unittest.mock import patch
from test_queue_e2e import Line, LockedGitHub
from thuha import cli
from thuha.common import ROOT, SITE, now
from thuha.coordinator import claim, submit
from thuha.http import NetworkError
from thuha.research import intake
from thuha.store import GitStore, LocalStore


class RecordingGitHub(LockedGitHub):
    """GitHub double that also accepts repository_dispatch (HTTP 204, an empty answer)."""

    def __init__(self):
        super().__init__()
        self.dispatches = []

    def request(self, method, path, body=None):
        if method == 'POST' and path.endswith('/dispatches'):
            self.dispatches.append(body)
            return {}
        return super().request(method, path, body)


class SharedWriterTests(Line):
    def setUp(self):
        super().setUp()
        self.api = RecordingGitHub()
        self.shared = GitStore(self.api)
        self.shared.put_document(self.store.get_document(self.source['document']))  # the evidence QA will read
        document = self.shared.put_document(self.inv)
        self.shared.mutate(lambda s: s.update(inventory_document=document))

    def claimed(self, number=1):
        topic = self.candidate(number, 'en')
        intake(self.shared, [topic], self.inv)
        lease = claim(self.shared, 'session-d%d' % number, 'writer-d%d' % number)
        return topic, lease

    def without_media(self):
        """The live situation for a waiting draft: the library holds no image the article could use yet."""
        document = self.shared.put_document(dict(self.inv, media=[]))
        self.shared.mutate(lambda s: s.update(inventory_document=document))

    def run_submit(self, topic, lease, mutate=None, waiting_for=None, allow_faults=False):
        article = self.article_for(topic, lease['session'], lease['agent_id'])
        if mutate:
            mutate(article)
        path = Path(self.temp.name) / ('article-%s.json' % topic['topic_id'])
        path.write_text(json.dumps(article))
        argv = ['--remote', 'submit', '--slot', lease['slot'], '--session', lease['session'], '--fence', lease['fence'], '--file', str(path)]
        if waiting_for:
            argv += ['--waiting-for'] + waiting_for
        if allow_faults:
            argv += ['--allow-faults']
        out = io.StringIO()
        with patch('thuha.cli.GitStore', lambda: self.shared), contextlib.redirect_stdout(out):
            code = cli.main(argv)
        return code, json.loads(out.getvalue())

    def test_a_completed_draft_is_checked_at_once_and_a_pass_dispatches_the_queue(self):
        topic, lease = self.claimed()
        code, result = self.run_submit(topic, lease)
        self.assertEqual((code, result['qa']['status']), (0, 'PASS'))
        self.assertEqual(result['publisher_trigger'], {'status': 'DISPATCH_ACCEPTED', 'topics': [topic['topic_id']]})
        self.assertEqual(self.api.dispatches, [{'event_type': 'thuha-qa-ready', 'client_payload': {'topic_ids': [topic['topic_id']]}}])
        self.assertEqual(self.shared.read()['topics'][topic['topic_id']]['status'], 'READY')

    def test_a_draft_stored_while_it_waits_for_data_is_not_evaluated_and_dispatches_nothing(self):
        topic, lease = self.claimed()
        self.without_media()
        code, result = self.run_submit(topic, lease, mutate=lambda a: a.update(featured_media=None), waiting_for=['FEATURED_MEDIA'])
        self.assertEqual(code, 0)
        self.assertNotIn('qa', result)
        self.assertNotIn('publisher_trigger', result)
        self.assertEqual(self.api.dispatches, [])
        state = self.shared.read()
        self.assertEqual((state['topics'][topic['topic_id']]['status'], state['qa']), ('WAITING_DATA', {}))

    def test_a_draft_known_to_fail_is_not_submitted_and_spends_no_repair(self):
        topic, lease = self.claimed()
        code, result = self.run_submit(topic, lease, mutate=lambda a: a.update(body_html=a['body_html'] + '<p>no deposit</p>'))
        self.assertEqual((code, result['status'], result['ledger_writes']), (1, 'NOT_SUBMITTED', 0))
        self.assertEqual(result['content_fails'], ['UNVERIFIED_BUSINESS_OR_FIRSTHAND_CLAIM'])
        self.assertEqual([f['code'] for f in result['fixes']], ['UNVERIFIED_BUSINESS_OR_FIRSTHAND_CLAIM'])  # and where and how to fix it
        state = self.shared.read()
        self.assertEqual((state['topics'][topic['topic_id']]['status'], state['submissions'], state['qa']), ('CLAIMED', {}, {}))
        self.assertEqual(self.api.dispatches, [])

    def test_a_draft_that_fails_qa_exits_1_and_dispatches_nothing(self):
        topic, lease = self.claimed()
        code, result = self.run_submit(topic, lease, mutate=lambda a: a.update(body_html=a['body_html'] + '<p>no deposit</p>'), allow_faults=True)
        self.assertEqual((code, result['qa']['status']), (1, 'FAIL'))
        self.assertNotIn('publisher_trigger', result)
        self.assertEqual(self.api.dispatches, [])
        self.assertEqual(self.shared.read()['topics'][topic['topic_id']]['status'], 'NEEDS_REPAIR')

    def test_a_site_that_cannot_be_reached_never_turns_a_stored_draft_into_a_failed_submit(self):
        old = dict(self.inv, captured_at='2020-01-01T00:00:00+00:00')
        document = self.shared.put_document(old)
        self.shared.mutate(lambda s: s.update(inventory_document=document))
        topic, lease = self.claimed()
        with patch('thuha.cli.audit.inventory', side_effect=NetworkError('the site does not answer')):
            code, result = self.run_submit(topic, lease)
        self.assertEqual(code, 0)
        self.assertEqual((result['qa']['status'], result['qa']['kind']), ('BLOCKED', 'INFRASTRUCTURE'))
        self.assertEqual(self.api.dispatches, [])
        self.assertEqual(self.shared.read()['topics'][topic['topic_id']]['status'], 'DRAFT_READY')  # stored; the scheduled QA evaluates it

    def test_an_expired_inventory_is_refreshed_from_the_public_site_before_the_check(self):
        old = dict(self.inv, captured_at='2020-01-01T00:00:00+00:00')
        document = self.shared.put_document(old)
        self.shared.mutate(lambda s: s.update(inventory_document=document))
        topic, lease = self.claimed()
        with patch('thuha.cli.audit.inventory', return_value=dict(self.inv, captured_at=now(), language_source='public-rest-unverified')) as fetch:
            code, result = self.run_submit(topic, lease)
        self.assertEqual((code, result['qa']['status']), (0, 'PASS'))  # an English draft can be checked on the public inventory
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(self.shared.get_document(self.shared.read()['inventory_document'])['language_source'], 'public-rest-unverified')

    def test_a_batch_qa_run_dispatches_once_for_what_passed_and_never_for_a_repeat(self):
        topic, lease = self.claimed()
        article = self.article_for(topic, lease['session'], lease['agent_id'])
        submit(self.shared, lease['slot'], lease['session'], lease['fence'], article)  # stored, not yet evaluated

        def run_qa_command():
            out = io.StringIO()
            with patch('thuha.cli.GitStore', lambda: self.shared), contextlib.redirect_stdout(out):
                code = cli.main(['--remote', 'qa', '--pending'])
            return code, json.loads(out.getvalue())
        (first_code, first), (second_code, second) = run_qa_command(), run_qa_command()
        self.assertEqual((first_code, second_code), (0, 0))
        self.assertEqual(first['publisher_trigger']['status'], 'DISPATCH_ACCEPTED')
        self.assertNotIn('publisher_trigger', second)  # nothing is pending any more
        self.assertEqual(len(self.api.dispatches), 1)


class DispatchRulesTests(unittest.TestCase):
    def test_a_session_ledger_in_a_branch_never_dispatches(self):
        branch_store = types.SimpleNamespace(durable_remote=True)  # no API client: Actions do not read this ledger
        self.assertEqual(cli.dispatch_qa_ready(branch_store, ['TH-VI-0001'])['status'], 'LOCAL_ONLY')

    def test_a_failed_dispatch_leaves_the_topic_ready_for_the_hourly_fallback(self):
        class Refusing:
            def request(self, *args):
                raise RuntimeError('refused')
        store = types.SimpleNamespace(durable_remote=True, api=Refusing())
        self.assertEqual(cli.dispatch_qa_ready(store, ['TH-VI-0001'])['status'], 'DISPATCH_FAILED')


class InventoryRefreshTests(unittest.TestCase):
    def store_with(self, inventory):
        import tempfile
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        store = LocalStore(temp.name)
        store.durable_remote = True
        path = Path(temp.name) / 'inventory.json'
        path.write_text(json.dumps(inventory))
        return store, path

    def test_when_the_site_cannot_be_reached_the_old_inventory_is_kept_for_the_caller_to_refuse(self):
        old = {'site': SITE, 'captured_at': '2020-01-01T00:00:00+00:00', 'complete': True, 'errors': []}
        store, path = self.store_with(old)
        with patch('thuha.cli.audit.inventory', side_effect=NetworkError('offline')):
            self.assertEqual(cli.inventory_for(store, path, 21600), old)
        self.assertEqual(store.read().get('inventory_document'), None)  # nothing was stored

    def test_a_planning_limit_that_depends_on_the_source_keeps_a_two_day_old_snapshot(self):
        snapshot = {'site': SITE, 'captured_at': '2026-10-21T00:00:00+00:00', 'complete': True, 'errors': [], 'language_source': 'authenticated-snapshot'}
        store, path = self.store_with(snapshot)
        with patch('thuha.cli.audit.inventory') as fetch, patch('thuha.cli.validate_inventory', side_effect=lambda inv, age: None) as check:
            self.assertEqual(cli.inventory_for(store, path, lambda inv: 604800), snapshot)
        fetch.assert_not_called()
        self.assertEqual(check.call_args[0][1], 604800)  # the planning age was used, not the six-hour publishing age


class WorkflowTriggerTests(unittest.TestCase):
    def test_the_publisher_workflow_runs_on_the_dispatch_and_keeps_the_hourly_fallback(self):
        text = (ROOT / '.github/workflows/thuha-ready-publisher.yml').read_text(encoding='utf-8')
        head = text[:text.index('jobs:')]
        self.assertIn('repository_dispatch', head)
        self.assertIn('thuha-qa-ready', head)
        self.assertIn("cron: '13 * * * *'", head)
        for job in ('preflight', 'queue', 'protected-publish'):
            body = text[text.index('  ' + job + ':'):]
            gate = body[:body.index('runs-on')]
            self.assertNotIn('repository_dispatch', gate)  # no job names the event, so none excludes it (they only test other events)


if __name__ == '__main__':
    unittest.main()
