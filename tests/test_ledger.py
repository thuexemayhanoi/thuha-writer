"""Hand-over of a session ledger into the shared ledger: fast-forward only, append-only, idempotent."""
import copy
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from thuha import ledger
from thuha.common import ROOT, SITE, digest, load, now, save
from thuha.store import GitBranchStore, GitStore, LocalStore, event, initial, migrate, validate
from test_remote_and_recovery import MemoryGitHub

FIXTURE = Path(__file__).parent / 'fixtures' / 'live-factory-state-2026-10-23.json'


def topic(tid):
    return {'topic_id': tid, 'status': 'PLANNED', 'proposed_url': SITE + '/guide-' + tid.lower() + '/', 'proposed_title': 'Guide ' + tid,
            'category_id': 20, 'category_path': [10, 20], 'primary_keyword': 'guide ' + tid, 'search_intent': 'intent ' + tid,
            'sources': [], 'intent_review': {}, 'admitted_at': now(), 'cluster': 'c'}


def legacy_live(topics=('TH-000001', 'TH-000002')):
    """A schema-4 ledger shaped like the one factory-state holds."""
    state = initial()
    state['schema'] = 4
    for tid in topics:
        state['topics'][tid] = topic(tid)
        event(state, 'RESEARCH_INTAKE', topic_id=tid)
    state['version'] = 5
    return state


def advanced(live, tid='TH-000003', doc=None):
    """What a session branch holds: the live ledger plus new work (a topic, a claim, a submission)."""
    state = copy.deepcopy(live)
    state['topics'][tid] = topic(tid)
    event(state, 'RESEARCH_INTAKE', topic_id=tid)
    state['topics'][tid]['status'] = 'DRAFT_READY'
    state['submissions'][tid] = {'article_sha': doc or 'a' * 64, 'session': 'session-w3', 'agent_id': 'claude-writer-W3',
                                 'slot': 'W3', 'fence': 'f', 'submitted_at': now(), 'repair_count': 0, 'commit': 'c'}
    event(state, 'SUBMISSION', topic_id=tid, article_sha=state['submissions'][tid]['article_sha'])
    state['version'] = 40
    return state


class PlanTests(unittest.TestCase):
    def test_extension_of_the_live_history_is_a_fast_forward(self):
        live = legacy_live()
        self.assertEqual(ledger.plan(live, advanced(live))['status'], 'FAST_FORWARD')

    def test_identical_or_older_session_ledger_is_already_included(self):
        live = legacy_live()
        self.assertEqual(ledger.plan(live, copy.deepcopy(live))['status'], 'ALREADY_INCLUDED')
        ahead = advanced(live)
        self.assertEqual(ledger.plan(ahead, live)['status'], 'ALREADY_INCLUDED')

    def test_a_live_ledger_with_other_history_is_refused(self):
        live = legacy_live()
        other = copy.deepcopy(live)
        event(other, 'REFILL_REQUEST', request_id='x')
        verdict = ledger.plan(other, advanced(live))
        self.assertEqual(verdict['status'], 'DIVERGED')
        self.assertIn('nothing was written', ' '.join(verdict['reasons']).lower())

    def test_events_the_live_ledger_wrote_after_its_migration_are_never_discarded(self):
        base = legacy_live()
        live = migrate(copy.deepcopy(base))
        event(live, 'REFILL_REQUEST', request_id='written-after-migration')
        verdict = ledger.plan(live, advanced(base))
        self.assertEqual(verdict['status'], 'DIVERGED')
        self.assertIn('REFILL_REQUEST', ' '.join(verdict['reasons']))

    def test_a_live_ledger_migrated_by_another_process_still_fast_forwards(self):
        live = legacy_live()
        self.assertEqual(ledger.plan(migrate(copy.deepcopy(live)), advanced(live))['status'], 'FAST_FORWARD')

    def test_tampered_history_is_invalid(self):
        live = legacy_live()
        handoff = advanced(live)
        handoff['events'][1]['topic_id'] = 'TH-000099'
        self.assertEqual(ledger.plan(live, handoff)['status'], 'INVALID_LEDGER')

    def test_evidence_the_live_ledger_holds_cannot_change(self):
        live = legacy_live()
        live['submissions']['TH-000001'] = {'article_sha': 'b' * 64, 'session': 's', 'agent_id': 'a', 'slot': 'W1', 'fence': 'f',
                                            'submitted_at': now(), 'repair_count': 0, 'commit': 'c'}
        event(live, 'SUBMISSION', topic_id='TH-000001', article_sha='b' * 64)
        for mutate, text in ((lambda s: s['topics']['TH-000001'].update(proposed_url=SITE + '/changed/'), 'Topic field changed'),
                             (lambda s: s['submissions']['TH-000001'].update(article_sha='c' * 64), 'Submission replaced'),
                             (lambda s: s['topics'].pop('TH-000002'), 'Topic missing')):
            handoff = advanced(live)
            mutate(handoff)
            verdict = ledger.plan(live, handoff)
            self.assertEqual(verdict['status'], 'INCONSISTENT', text)
            self.assertIn(text, ' '.join(verdict['reasons']))

    def test_a_running_publisher_blocks_promotion(self):
        live = legacy_live()
        live['publisher_lease'] = {'fence': 'x', 'expires_at': 9e12}
        self.assertEqual(ledger.plan(live, advanced(live))['status'], 'BLOCKED')

    def test_migration_is_deterministic(self):
        live = legacy_live()
        first, second = migrate(copy.deepcopy(live)), migrate(copy.deepcopy(live))
        self.assertEqual(first['events'], second['events'])
        self.assertEqual(first['events'][-1]['at'], live['events'][-1]['at'])


class PromoteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.api = MemoryGitHub()
        self.remote = GitStore(self.api)
        self.live = legacy_live()
        self.api.files[GitStore.state_path] = copy.deepcopy(self.live)
        self.session = LocalStore(Path(self.temp.name) / 'session')
        self.doc = self.session.put_document({'article': 'body of a submitted draft'})
        self.handoff = advanced(self.live, doc=self.doc)
        self.documents = {self.doc: self.session.get_document(self.doc)}

    def run_promote(self, apply=True, handoff=None, documents=None):
        return ledger.promote(self.remote, handoff or self.handoff, self.documents if documents is None else documents, apply=apply)

    def test_dry_run_reports_the_plan_and_writes_nothing(self):
        result = self.run_promote(apply=False)
        self.assertEqual((result['status'], result['applied']), ('FAST_FORWARD', False))
        self.assertEqual(self.api.writes, 0)

    def test_apply_copies_documents_then_moves_the_ledger_forward(self):
        result = self.run_promote()
        self.assertTrue(result['applied'])
        self.assertIn('data/documents/' + self.doc + '.json', self.api.files)
        state = self.remote.read()
        self.assertEqual(state['schema'], 5)
        self.assertEqual(set(state['topics']), {'TH-000001', 'TH-000002', 'TH-000003'})
        self.assertEqual(state['topics']['TH-000003']['status'], 'DRAFT_READY')
        self.assertEqual(state['topics']['TH-000003']['language'], 'en')
        self.assertEqual(state['submissions']['TH-000003']['article_sha'], self.doc)
        self.assertGreater(state['version'], self.live['version'])
        actions = [e['action'] for e in state['events']]
        self.assertEqual(actions[-2:], ['SCHEMA_MIGRATION', 'LEDGER_PROMOTION'])
        self.assertEqual(state['events'][:len(self.live['events'])], self.live['events'])  # history is kept verbatim
        validate(state)

    def test_second_run_writes_nothing(self):
        self.run_promote()
        writes = self.api.writes
        again = self.run_promote()
        self.assertEqual((again['status'], again['applied']), ('ALREADY_INCLUDED', False))
        self.assertEqual(self.api.writes, writes)

    def test_documents_are_in_place_before_the_ledger_references_them(self):
        order = []
        original = self.api.request

        def spy(method, path, body=None):
            if method == 'PUT':
                order.append('state' if path.endswith('factory.json') else 'document')
            return original(method, path, body)
        self.api.request = spy
        self.run_promote()
        self.assertEqual(order[-1], 'state')
        self.assertEqual(order.count('state'), 1)

    def test_a_missing_referenced_document_stops_before_any_ledger_write(self):
        before = copy.deepcopy(self.api.files[GitStore.state_path])
        with self.assertRaisesRegex(ValueError, 'neither place'):
            self.run_promote(documents={})
        self.assertEqual(self.api.files[GitStore.state_path], before)

    def test_a_document_that_collides_with_an_existing_address_is_refused(self):
        self.api.files['data/documents/' + self.doc + '.json'] = {'article': 'someone else'}
        with self.assertRaises(ValueError):
            self.run_promote()
        self.assertEqual(self.api.files[GitStore.state_path]['version'], 5)

    def test_a_ledger_that_moves_between_plan_and_write_is_replanned_not_overwritten(self):
        original = self.api.request
        state = {'done': False}

        def racing(method, path, body=None):
            if method == 'PUT' and path.endswith('factory.json') and not state['done']:
                state['done'] = True
                other = copy.deepcopy(self.api.files[GitStore.state_path])
                event(other, 'REFILL_REQUEST', request_id='raced')
                other['version'] += 1
                self.api.files[GitStore.state_path] = other
            return original(method, path, body)
        self.api.request = racing
        result = self.run_promote()
        self.assertFalse(result['applied'])
        self.assertEqual(result['status'], 'DIVERGED')
        self.assertIn('REFILL_REQUEST', [e['action'] for e in self.api.files[GitStore.state_path]['events']])
        self.assertNotIn('TH-000003', self.api.files[GitStore.state_path]['topics'])

    def test_the_stricter_of_the_two_controls_wins_and_inventory_pointer_stays_live(self):
        live_inventory = self.remote.put_document({'inventory': 'live'})
        old_inventory = self.session.put_document({'inventory': 'older, from the session'})
        self.api.files[GitStore.state_path]['controls']['paused'] = True
        self.api.files[GitStore.state_path]['inventory_document'] = live_inventory
        self.handoff['inventory_document'] = old_inventory
        self.documents[old_inventory] = {'inventory': 'older, from the session'}
        self.run_promote()
        state = self.remote.read()
        self.assertTrue(state['controls']['paused'])
        self.assertEqual(state['inventory_document'], live_inventory)

    def test_a_first_promotion_into_an_empty_shared_ledger_creates_it(self):
        self.api.files.clear()
        self.assertEqual(self.run_promote()['status'], 'FAST_FORWARD')
        self.assertTrue(self.api.branch)
        self.assertEqual(len(self.remote.read()['topics']), 3)

    def test_documents_are_verified_against_their_address(self):
        directory = Path(self.temp.name) / 'docs'
        directory.mkdir()
        (directory / (('a' * 64) + '.json')).write_text('{"not": "that digest"}')
        with self.assertRaisesRegex(ValueError, 'does not match its address'):
            ledger.read_documents(directory)
        (directory / (('a' * 64) + '.json')).unlink()
        (directory / 'notes.txt').write_text('x')
        self.assertEqual(ledger.read_documents(directory), {})  # only *.json are documents
        (directory / 'surprise.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'Unexpected file'):
            ledger.read_documents(directory)


class SyncTests(unittest.TestCase):
    """A session ledger is refreshed from the live one before more work, so the next promotion is a fast-forward again."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.api = MemoryGitHub()
        self.remote = GitStore(self.api)
        self.root = Path(self.temp.name) / 'local'
        self.local = LocalStore(self.root)

    def test_session_ledger_behind_live_is_brought_forward_with_its_documents(self):
        stale = legacy_live()
        self.local.adopt(lambda raw: migrate(copy.deepcopy(stale)))
        live = advanced(stale, doc=self.remote.put_document({'article': 'written elsewhere'}))
        self.api.files[GitStore.state_path] = live
        result = ledger.sync(self.local, self.remote, apply=True)
        self.assertTrue(result['applied'])
        state = self.local.read()
        self.assertIn('TH-000003', state['topics'])
        self.assertEqual(self.local.get_document(live['submissions']['TH-000003']['article_sha']), {'article': 'written elsewhere'})
        self.assertEqual(ledger.plan(self.api.files[GitStore.state_path], self.local.raw()[0])['status'], 'ALREADY_INCLUDED')

    def test_unpromoted_session_work_is_never_overwritten(self):
        live = legacy_live()
        self.api.files[GitStore.state_path] = live
        mine = advanced(live)
        self.local.adopt(lambda raw: migrate(copy.deepcopy(mine)))
        result = ledger.sync(self.local, self.remote, apply=True)
        self.assertEqual(result['status'], 'ALREADY_INCLUDED')
        self.assertIn('TH-000003', self.local.read()['topics'])

    def test_session_work_on_top_of_a_stale_ledger_is_refused(self):
        stale = legacy_live()
        mine = migrate(copy.deepcopy(stale))
        event(mine, 'CLAIM', topic_id='TH-000001')
        self.local.adopt(lambda raw: copy.deepcopy(mine))
        live = copy.deepcopy(stale)
        event(live, 'REFILL_REQUEST', request_id='r')
        self.api.files[GitStore.state_path] = live
        result = ledger.sync(self.local, self.remote, apply=True)
        self.assertEqual(result['status'], 'DIVERGED')
        self.assertFalse(result['applied'])


class RealLedgerTests(unittest.TestCase):
    """The session ledger committed in this repository against the live ledger as factory-state held it on 2026-10-23."""

    def test_the_committed_session_ledger_fast_forwards_the_live_snapshot_and_keeps_every_draft(self):
        live = load(FIXTURE)
        handoff = load(ROOT / 'data/state/factory.json')
        documents = ledger.read_documents(ROOT / 'data/documents')
        self.assertEqual(ledger.plan(live, handoff)['status'], 'FAST_FORWARD')
        missing = [x for x in ledger.referenced(handoff) if x not in documents]
        self.assertEqual(missing, [])
        with tempfile.TemporaryDirectory() as temp:
            store = LocalStore(temp)
            save(store.path, live)  # the ledger exactly as factory-state holds it: schema 4, not yet migrated
            result = ledger.promote(store, handoff, documents, apply=True)
            self.assertTrue(result['applied'], result)
            state = store.read()
        self.assertGreaterEqual(len(state['submissions']), 9)
        self.assertEqual(state['submissions'], migrate(copy.deepcopy(handoff))['submissions'])
        self.assertEqual(state['reviews'], handoff['reviews'])
        self.assertEqual(state['qa'], handoff['qa'])
        self.assertEqual(state['events'][:len(handoff['events'])], handoff['events'])
        self.assertTrue(all(t['language'] == 'en' for t in state['topics'].values()))
        self.assertEqual(state['receipts'], {})
        self.assertEqual(state['intents'], {})

    def test_the_session_documents_are_complete_and_untouched(self):
        documents = ledger.read_documents(ROOT / 'data/documents')
        self.assertGreaterEqual(len(documents), 277)


if __name__ == '__main__':
    unittest.main()
