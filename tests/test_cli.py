"""Command-line surface: read-only matrix and quota views, validation, and the adapter gate."""
import io
import json
import os
import tempfile
import unittest
from unittest.mock import patch
from thuha.cli import main
from thuha.store import LocalStore


def run(*argv, env=None):
    out = io.StringIO()
    with tempfile.TemporaryDirectory() as temp, patch('sys.stdout', out), patch.dict(os.environ, env or {}):
        code = main(['--state-dir', temp, *argv])
        state = LocalStore(temp).read()
    return code, json.loads(out.getvalue()), state


class CliTests(unittest.TestCase):
    def test_matrix_next_is_read_only_and_vietnamese_first(self):
        code, result, state = run('matrix', 'next', '--limit', '5')
        self.assertEqual(code, 0);self.assertEqual(result['wordpress_writes'], 0)
        rows = result['next_research']
        self.assertEqual(len(rows), 10)  # five per language
        self.assertEqual([r['language'] for r in rows[:5]], ['vi'] * 5)
        self.assertTrue(all(r['writer_state'] == 'NEEDS_SOURCE' for r in rows))
        self.assertEqual(state['topics'], {})

    def test_matrix_next_single_language(self):
        code, result, _ = run('matrix', 'next', '--language', 'en', '--limit', '3')
        self.assertEqual({r['language'] for r in result['next_research']}, {'en'})
        self.assertTrue(all(r['id'].startswith('TH-EN-') for r in result['next_research']))

    def test_matrix_validate_reports_no_problems(self):
        code, result, _ = run('matrix', 'validate')
        self.assertEqual(code, 0);self.assertEqual(result, {'vi': [], 'en': []})

    def test_quota_command_shows_both_ceilings_from_the_snapshot(self):
        code, result, _ = run('quota')
        self.assertEqual(result['languages']['vi']['remaining'], 500);self.assertEqual(result['languages']['en']['remaining'], 225)
        self.assertEqual(result['inventory_language_source'], 'authenticated-snapshot')
        self.assertIn('not live counters', result['note'])

    def test_validate_checks_goal_matrices_and_package(self):
        code, result, _ = run('validate')
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['matrices']['vi']['new'], 500);self.assertEqual(result['matrices']['en']['protected'], 275)
        self.assertEqual(result['adapter_package']['safety_scan'], 'clean')

    def test_adapter_preflight_without_credentials_records_nothing(self):
        env = {'THUHA_WP_USER': '', 'THUHA_WP_APPLICATION_PASSWORD': ''}
        with self.assertRaises(ValueError):run('adapter-preflight', env=env)
        with tempfile.TemporaryDirectory() as temp:
            self.assertNotIn('adapter', LocalStore(temp).read())

    def test_dashboard_reports_the_adapter_as_blocked_until_verified(self):
        with tempfile.TemporaryDirectory() as temp, tempfile.TemporaryDirectory() as out:
            with patch('sys.stdout', io.StringIO()) as stdout:
                main(['--state-dir', temp, '--output', out, 'report'])
            report = json.loads(stdout.getvalue())
            self.assertEqual(report['adapter']['code'], 'BLOCKED_ADAPTER_NOT_DEPLOYED')
            self.assertTrue(any('BLOCKED_ADAPTER_NOT_DEPLOYED' in b for b in report['blockers']))
            release = load(ROOT / 'config/release.json')
            self.assertEqual(report['production_enabled'], release['enabled'])
            self.assertEqual(report['languages_enabled'], release['languages_enabled'])
            self.assertIn('Vietnamese first', open(out + '/dashboard.md').read())

    def test_publisher_dry_run_is_read_only_regardless_of_release_state(self):
        code, result, _ = run('publisher', '--mode', 'dry-run')
        self.assertEqual(result['wordpress_writes'], 0)
        self.assertEqual(result['publishing_enabled'], load(ROOT / 'config/release.json')['enabled'])

    def test_production_publishing_refuses_without_every_gate(self):
        with self.assertRaises(ValueError):run('publisher', '--mode', 'production', '--topic-id', 'TH-VI-0001')


class WorkflowThroughCliTests(unittest.TestCase):
    """intake -> brief -> claim -> quota with real files and one local store; no network, no WordPress."""
    def test_vietnamese_topic_is_briefed_and_claimed_before_english(self):
        from test_factory import Fixture, inventory_fixture
        from thuha.common import now, save
        class Seed(Fixture):
            def runTest(self):pass
        seed = Seed();seed.setUp()
        try:
            store = seed.store
            inv_path = os.path.join(seed.temp.name, 'inventory.json');save(inv_path, seed.inv)
            candidates = [seed.candidate(1, 'en'), seed.candidate(1, 'vi')]
            cand_path = os.path.join(seed.temp.name, 'candidates.json');save(cand_path, candidates)
            base = ['--state-dir', seed.temp.name, '--inventory', inv_path]
            def call(*argv):
                out = io.StringIO()
                with patch('sys.stdout', out):code = main(base + list(argv))
                return code, json.loads(out.getvalue())
            self.assertEqual(call('intake', '--file', cand_path)[1]['admitted'], ['TH-EN-0001', 'TH-VI-0001'])
            brief = call('brief')[1]
            self.assertEqual([t['topic_id'] for t in brief['topics']], ['TH-VI-0001', 'TH-EN-0001'])
            self.assertEqual([t['topic_id'] for t in call('brief', '--language', 'en')[1]['topics']], ['TH-EN-0001'])
            lease = call('claim', '--session', 'session-vi', '--agent-id', 'writer-vi')[1]
            self.assertEqual((lease['topic_id'], lease['language']), ('TH-VI-0001', 'vi'))
            quota = call('quota')[1]['languages']
            self.assertEqual(quota['vi']['open_topics'], 1);self.assertEqual(quota['en']['open_topics'], 1)
            self.assertEqual(call('resume', '--topic-id', 'TH-VI-0001')[1]['topic']['language'], 'vi')
        finally:
            seed.temp.cleanup()


if __name__ == '__main__':
    unittest.main()
