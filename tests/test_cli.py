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
            self.assertFalse(report['production_enabled']);self.assertEqual(report['languages_enabled'], [])
            self.assertIn('Vietnamese first', open(out + '/dashboard.md').read())

    def test_publisher_dry_run_is_read_only_and_reports_no_enabled_language(self):
        code, result, _ = run('publisher', '--mode', 'dry-run')
        self.assertEqual((result['wordpress_writes'], result['publishing_enabled']), (0, False))

    def test_production_publishing_refuses_without_every_gate(self):
        with self.assertRaises(ValueError):run('publisher', '--mode', 'production', '--topic-id', 'TH-VI-0001')


if __name__ == '__main__':
    unittest.main()
