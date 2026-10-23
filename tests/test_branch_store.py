"""Git-branch state adapter: durable through commits/pushes, CAS through push rejection."""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from thuha.common import digest
from thuha.store import GitBranchStore


def git(*args, cwd):
    return subprocess.run(['git', *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


class BranchStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.bare = base / 'remote.git'; git('init', '-q', '--bare', str(self.bare), cwd=base)
        self.work = base / 'work'; self.work.mkdir()
        git('init', '-q', '-b', 'session/test', cwd=self.work)
        git('config', 'user.email', 't@example.org', cwd=self.work); git('config', 'user.name', 'tests', cwd=self.work)
        (self.work / 'README.md').write_text('x'); git('add', 'README.md', cwd=self.work); git('commit', '-q', '-m', 'init', cwd=self.work)
        git('remote', 'add', 'origin', str(self.bare), cwd=self.work); git('push', '-q', 'origin', 'session/test', cwd=self.work)
        self.store = GitBranchStore(self.work)

    def test_rejects_default_branch(self):
        git('checkout', '-q', '-b', 'main', cwd=self.work)
        with self.assertRaises(ValueError):
            GitBranchStore(self.work)

    def test_mutation_commits_only_state_and_pushes(self):
        (self.work / 'unrelated.py').write_text('print(1)')  # dirty working tree must not be swept in
        self.store.mutate(lambda s: s['topics'].update({'TH-000001': {'status': 'PLANNED'}}))
        remote_log = git('log', '--format=%s', 'session/test', cwd=self.bare)
        self.assertIn('factory checkpoint v1', remote_log)
        tracked = git('ls-tree', '-r', '--name-only', 'session/test', cwd=self.bare)
        self.assertIn('data/state/factory.json', tracked); self.assertNotIn('unrelated.py', tracked)
        self.assertEqual(self.store.read()['topics']['TH-000001']['status'], 'PLANNED')

    def test_document_is_immutable_and_pushed(self):
        sha = self.store.put_document({'a': 1})
        self.assertEqual(self.store.put_document({'a': 1}), sha)
        self.assertEqual(self.store.get_document(sha), {'a': 1})
        tracked = git('ls-tree', '-r', '--name-only', 'session/test', cwd=self.bare)
        self.assertIn('data/documents/' + sha + '.json', tracked)
        (self.work / 'data/documents' / (sha + '.json')).write_text('{"a":2}')
        with self.assertRaises(ValueError):
            self.store.put_document({'a': 1})

    def test_push_rejection_is_retried_after_rebase(self):
        # Another clone moves the branch; our push must rebase and succeed without losing either change.
        other = Path(self.temp.name) / 'other'; git('clone', '-q', '-b', 'session/test', str(self.bare), str(other), cwd=self.temp.name)
        git('config', 'user.email', 'o@example.org', cwd=other); git('config', 'user.name', 'other', cwd=other)
        (other / 'note.txt').write_text('remote moved'); git('add', 'note.txt', cwd=other); git('commit', '-q', '-m', 'remote move', cwd=other); git('push', '-q', cwd=other)
        self.store.mutate(lambda s: s['topics'].update({'TH-000002': {'status': 'PLANNED'}}))
        log = git('log', '--format=%s', 'session/test', cwd=self.bare)
        self.assertIn('remote move', log); self.assertIn('factory checkpoint v1', log)

    def test_invalid_state_is_not_committed(self):
        def bad(s): s['leases']['W1'] = {'topic_id': 'missing', 'expires_at': 0}
        with self.assertRaises(ValueError):
            self.store.mutate(bad)
        self.assertNotIn('data/state', git('ls-tree', '-r', '--name-only', 'session/test', cwd=self.bare))


if __name__ == '__main__':
    unittest.main()
