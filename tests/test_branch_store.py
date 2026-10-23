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
        self.store.mutate(lambda s: s['topics'].update({'TH-EN-0001': {'status': 'PLANNED', 'language': 'en'}}))
        remote_log = git('log', '--format=%s', 'session/test', cwd=self.bare)
        self.assertIn('factory checkpoint v1', remote_log)
        tracked = git('ls-tree', '-r', '--name-only', 'session/test', cwd=self.bare)
        self.assertIn('data/state/factory.json', tracked); self.assertNotIn('unrelated.py', tracked)
        self.assertEqual(self.store.read()['topics']['TH-EN-0001']['status'], 'PLANNED')

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
        self.store.mutate(lambda s: s['topics'].update({'TH-EN-0002': {'status': 'PLANNED', 'language': 'en'}}))
        log = git('log', '--format=%s', 'session/test', cwd=self.bare)
        self.assertIn('remote move', log); self.assertIn('factory checkpoint v1', log)

    def other_clone(self):
        other = Path(self.temp.name) / ('other-%d' % len(list(Path(self.temp.name).glob('other-*'))))
        git('clone', '-q', '-b', 'session/test', str(self.bare), str(other), cwd=self.temp.name)
        git('config', 'user.email', 'o@example.org', cwd=other); git('config', 'user.name', 'other', cwd=other)
        return other

    def test_two_clones_changing_the_ledger_both_keep_their_change_and_nothing_is_left_half_merged(self):
        self.store.mutate(lambda s: s['topics'].update({'TH-EN-0001': {'status': 'PLANNED', 'language': 'en'}}))
        other = self.other_clone()
        theirs = GitBranchStore(other)
        theirs.mutate(lambda s: s['topics'].update({'TH-EN-0002': {'status': 'PLANNED', 'language': 'en'}}))
        # Our clone is now behind and edits the same file: the commit must be dropped and the mutation redone, not rebased.
        self.store.mutate(lambda s: s['topics'].update({'TH-EN-0003': {'status': 'PLANNED', 'language': 'en'}}))
        state = self.store.read()  # readable: no conflict markers
        self.assertEqual(set(state['topics']), {'TH-EN-0001', 'TH-EN-0002', 'TH-EN-0003'})
        self.assertEqual(git('status', '--porcelain', cwd=self.work).strip(), '')
        self.assertFalse((self.work / '.git' / 'rebase-merge').exists() or (self.work / '.git' / 'rebase-apply').exists())
        remote = json.loads(git('show', 'session/test:data/state/factory.json', cwd=self.bare))
        self.assertEqual(set(remote['topics']), {'TH-EN-0001', 'TH-EN-0002', 'TH-EN-0003'})
        self.assertEqual(remote['version'], 3)

    def test_a_document_written_but_never_committed_is_committed_by_the_retry(self):
        value = {'article': 'cut off before the commit'}
        sha = digest(value)
        path = self.work / 'data/documents' / (sha + '.json')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(__import__('thuha.common', fromlist=['canonical_json']).canonical_json(value))  # the process died here
        self.assertNotIn(sha, git('ls-tree', '-r', '--name-only', 'session/test', cwd=self.bare))
        self.assertEqual(self.store.put_document(value), sha)
        self.assertIn('data/documents/' + sha + '.json', git('ls-tree', '-r', '--name-only', 'session/test', cwd=self.bare))

    def test_a_truncated_uncommitted_document_is_replaced_but_a_committed_one_never_is(self):
        value = {'article': 'whole document'}
        sha = digest(value)
        path = self.work / 'data/documents' / (sha + '.json')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"article": "whole doc')  # half written
        self.assertEqual(self.store.put_document(value), sha)
        self.assertEqual(self.store.get_document(sha), value)
        path.write_text('{"article": "tampered"}')  # now it is committed: a change is a collision
        with self.assertRaises(ValueError):
            self.store.put_document(value)

    def test_a_branch_that_cannot_be_fast_forwarded_is_reported_not_corrupted(self):
        (self.work / 'local.txt').write_text('local only'); git('add', 'local.txt', cwd=self.work); git('commit', '-q', '-m', 'unpushed local', cwd=self.work)
        other = self.other_clone()
        GitBranchStore(other).mutate(lambda s: s['topics'].update({'TH-EN-0009': {'status': 'PLANNED', 'language': 'en'}}))
        with self.assertRaisesRegex(RuntimeError, 'local commits'):
            self.store.mutate(lambda s: s['topics'].update({'TH-EN-0001': {'status': 'PLANNED', 'language': 'en'}}))
        self.assertEqual(git('status', '--porcelain', cwd=self.work).strip(), '')

    def test_invalid_state_is_not_committed(self):
        def bad(s): s['leases']['W1'] = {'topic_id': 'missing', 'expires_at': 0}
        with self.assertRaises(ValueError):
            self.store.mutate(bad)
        self.assertNotIn('data/state', git('ls-tree', '-r', '--name-only', 'session/test', cwd=self.bare))


if __name__ == '__main__':
    unittest.main()
