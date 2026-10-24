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

    def test_newer_shared_submission_event_safely_supersedes_old_session_draft(self):
        handoff = advanced(legacy_live())
        live = copy.deepcopy(handoff)
        live['submissions']['TH-000003']['article_sha'] = 'b' * 64
        event(live, 'CLAIM', topic_id='TH-000003', session='vi-link-rescue')
        event(live, 'SUBMISSION', topic_id='TH-000003', article_sha='b' * 64)
        self.assertEqual(ledger.plan(live, handoff)['status'], 'ALREADY_INCLUDED')

    def test_shared_sha_change_without_later_submission_event_stays_inconsistent(self):
        handoff = advanced(legacy_live())
        live = copy.deepcopy(handoff)
        live['submissions']['TH-000003']['article_sha'] = 'b' * 64
        self.assertEqual(ledger.plan(live, handoff)['status'], 'INCONSISTENT')

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


class RoundsTests(unittest.TestCase):
    """The hand-over works repeatedly: sync, work, promote, while the shared ledger keeps moving (QA, publishing)."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.api = MemoryGitHub()
        self.remote = GitStore(self.api)
        self.base = legacy_live()
        self.api.files[GitStore.state_path] = copy.deepcopy(self.base)
        self.session = LocalStore(Path(self.temp.name) / 'session')
        save(self.session.path, advanced(self.base, doc=self.session.put_document({'article': 'round one'})))

    def promote(self):
        return ledger.promote(self.remote, self.session.raw()[0], ledger.read_documents(self.session.directory / 'documents'), apply=True)

    def work(self, tid):
        """One more topic with a draft in the session ledger, as a writer would leave it."""
        doc = self.session.put_document({'article': 'draft of ' + tid})

        def add(state):
            state['topics'][tid] = dict(topic(tid), language='en')
            event(state, 'RESEARCH_INTAKE', topic_ids=[tid])
            state['topics'][tid]['status'] = 'DRAFT_READY'
            state['submissions'][tid] = {'article_sha': doc, 'session': 's-' + tid, 'agent_id': 'a-' + tid, 'slot': 'W4', 'fence': 'f',
                                         'submitted_at': now(), 'repair_count': 0, 'commit': 'c'}
            event(state, 'SUBMISSION', topic_id=tid, article_sha=doc)
        self.session.mutate(add)

    def actions_move_the_shared_ledger(self, action):
        self.remote.mutate(lambda s: event(s, action, note='written by Actions'))

    def test_three_rounds_each_new_batch_arrives_and_the_shared_events_survive(self):
        self.assertEqual(self.promote()['status'], 'FAST_FORWARD')
        for tid in ('TH-000004', 'TH-000005'):
            self.actions_move_the_shared_ledger('QA')
            nothing_new = self.promote()  # the session did not look at the shared ledger, but it has nothing to hand over either
            self.assertEqual((nothing_new['status'], nothing_new['applied']), ('ALREADY_INCLUDED', False))
            self.assertEqual(ledger.sync(self.session, self.remote, apply=True)['status'], 'FAST_FORWARD')
            self.work(tid)
            result = self.promote()
            self.assertEqual((result['status'], result['applied']), ('FAST_FORWARD', True), result)
            state = self.remote.read()
            self.assertIn(tid, state['topics'])
            self.assertEqual(state['submissions'][tid]['agent_id'], 'a-' + tid)
        actions = [e['action'] for e in self.remote.read()['events']]
        self.assertEqual(actions.count('QA'), 2)  # what Actions wrote in between is still there
        self.assertEqual(actions.count('LEDGER_PROMOTION'), 3)
        validate(self.remote.read())

    def test_work_on_top_of_a_synced_ledger_is_not_reported_as_already_included(self):
        self.promote()
        self.actions_move_the_shared_ledger('QA')
        ledger.sync(self.session, self.remote, apply=True)
        self.work('TH-000004')
        verdict = ledger.plan(self.remote.raw()[0], self.session.raw()[0])
        self.assertEqual(verdict['status'], 'FAST_FORWARD')

    def test_a_session_that_never_synced_is_told_which_shared_events_it_lacks(self):
        self.promote()
        self.actions_move_the_shared_ledger('QA')
        self.work('TH-000004')
        verdict = ledger.plan(self.remote.raw()[0], self.session.raw()[0])
        self.assertEqual(verdict['status'], 'DIVERGED')
        self.assertIn('QA', ' '.join(verdict['reasons']))
        self.assertIn('LEDGER_PROMOTION', ' '.join(verdict['reasons']))

    def diverge(self):
        """The shared ledger moves on (a promotion, then QA written by Actions) while a session keeps working on its stale copy."""
        self.promote()
        self.actions_move_the_shared_ledger('QA')
        self.work('TH-000004')

    def test_sync_refuses_a_diverged_session_and_lists_what_it_holds_that_the_shared_ledger_lacks(self):
        self.diverge()
        before = copy.deepcopy(self.session.raw()[0])
        result = ledger.sync(self.session, self.remote, apply=True)
        self.assertEqual((result['status'], result['applied']), ('DIVERGED', False))
        self.assertEqual([d['topic_id'] for d in result['unpromoted']['drafts']], ['TH-000004'])
        self.assertEqual(result['unpromoted']['events'], {'RESEARCH_INTAKE': 1, 'SUBMISSION': 1})
        self.assertTrue(result['unpromoted']['drafts'][0]['submitted_at'])  # the order in which the drafts are submitted again
        admitted = result['unpromoted']['topics']  # admitted only in the session: the records to admit again
        self.assertEqual([t['topic_id'] for t in admitted], ['TH-000004'])
        self.assertEqual(set(admitted[0]) & {'status', 'admitted_at', 'waiting_for'}, set())  # lifecycle fields are not part of an admission
        self.assertEqual(set(ledger.ADMISSION_FIELDS) - set(admitted[0]), set())
        self.assertEqual(self.session.raw()[0], before)  # nothing was replaced

    def test_discarding_the_unpromoted_work_is_explicit_and_leaves_every_document_in_place(self):
        self.diverge()
        draft = self.session.raw()[0]['submissions']['TH-000004']['article_sha']
        listed = ledger.sync(self.session, self.remote, discard_unpromoted=True)  # without --apply this only lists
        self.assertFalse(listed['applied'])
        self.assertIn('TH-000004', self.session.raw()[0]['topics'])
        result = ledger.sync(self.session, self.remote, apply=True, discard_unpromoted=True)
        self.assertEqual((result['status'], result['applied']), ('REPLACED', True))
        self.assertEqual([d['topic_id'] for d in result['unpromoted']['drafts']], ['TH-000004'])  # still told what has to be submitted again
        state = self.session.raw()[0]
        self.assertNotIn('TH-000004', state['topics'])
        self.assertEqual(ledger.logical(state['events']), ledger.logical(self.remote.raw()[0]['events']))  # exactly the shared history
        self.assertEqual(self.session.get_document(draft), {'article': 'draft of TH-000004'})  # immutable documents are never deleted
        self.assertEqual(ledger.plan(self.remote.raw()[0], state)['status'], 'ALREADY_INCLUDED')
        self.work('TH-000004')  # the same draft is submitted again on top of the shared history
        again = self.promote()
        self.assertEqual((again['status'], again['applied']), ('FAST_FORWARD', True), again)
        self.assertEqual(self.remote.read()['submissions']['TH-000004']['article_sha'], draft)

    def test_discarding_is_refused_while_a_writer_holds_a_lease(self):
        self.diverge()
        lease = {'slot': 'W1', 'session': 's', 'agent_id': 'a', 'topic_id': 'TH-000004', 'language': 'en', 'fence': 'f',
                 'heartbeat_at': now(), 'expires_at': 4102444800}
        self.session.mutate(lambda s: s['leases'].update({'W1': lease}))
        result = ledger.sync(self.session, self.remote, apply=True, discard_unpromoted=True)
        self.assertEqual((result['status'], result['applied']), ('LEASES_HELD', False))
        self.assertIn('TH-000004', self.session.raw()[0]['topics'])
        self.assertEqual(self.session.raw()[0]['leases']['W1']['fence'], 'f')

    def test_the_command_line_replaces_a_diverged_ledger_only_when_asked(self):
        import contextlib
        import io
        from unittest.mock import patch
        from thuha import cli
        self.diverge()

        def run(*flags):
            out = io.StringIO()
            with patch('thuha.cli.GitStore', lambda: self.remote), contextlib.redirect_stdout(out):
                code = cli.main(['--state-dir', str(self.session.directory), 'sync', *flags])
            return code, json.loads(out.getvalue())
        code, result = run('--apply')
        self.assertEqual((code, result['status']), (1, 'DIVERGED'))
        self.assertEqual([d['topic_id'] for d in result['unpromoted']['drafts']], ['TH-000004'])
        self.assertIn('TH-000004', self.session.raw()[0]['topics'])
        code, result = run('--apply', '--discard-unpromoted')
        self.assertEqual((code, result['status']), (0, 'REPLACED'))
        self.assertNotIn('TH-000004', self.session.raw()[0]['topics'])

    def test_the_discard_option_changes_nothing_for_a_session_that_can_fast_forward(self):
        self.promote()
        self.actions_move_the_shared_ledger('QA')
        result = ledger.sync(self.session, self.remote, apply=True, discard_unpromoted=True)
        self.assertEqual((result['status'], result['applied']), ('FAST_FORWARD', True))  # a plain sync, no replacement

    def store_as_waiting(self, tid='TH-000003'):
        def store(state):  # what `submit --waiting-for` leaves behind
            state['topics'][tid]['status'] = 'WAITING_DATA'
            state['topics'][tid]['waiting_for'] = ['FEATURED_MEDIA']
            event(state, 'SUBMISSION', topic_id=tid, article_sha=state['submissions'][tid]['article_sha'], waiting_for=['FEATURED_MEDIA'])
        self.session.mutate(store)

    def replace_draft(self, text, status, tid='TH-000003'):
        finished = self.session.put_document({'article': text})

        def replace(state):  # the submission changes; repair_count does not
            state['submissions'][tid]['article_sha'] = finished
            state['topics'][tid]['status'] = status
            state['topics'][tid].pop('waiting_for', None)
            event(state, 'SUBMISSION', topic_id=tid, article_sha=finished)
        self.session.mutate(replace)
        return finished

    def test_a_waiting_draft_that_a_later_session_finishes_is_handed_over_without_a_repair(self):
        self.store_as_waiting()
        self.assertEqual(self.promote()['status'], 'FAST_FORWARD')  # the shared ledger now holds a draft that waits for data
        ledger.sync(self.session, self.remote, apply=True)
        finished = self.replace_draft('finished after the data arrived', 'DRAFT_READY')
        verdict = ledger.plan(self.remote.raw()[0], self.session.raw()[0])
        self.assertEqual(verdict['status'], 'FAST_FORWARD', verdict)  # finishing a stored draft is a completion, not a repair
        self.assertTrue(self.promote()['applied'])
        self.assertEqual(self.remote.read()['submissions']['TH-000003']['article_sha'], finished)

    def test_a_draft_that_was_not_waiting_still_cannot_be_replaced_without_a_repair(self):
        self.promote()  # TH-000003 is DRAFT_READY in the shared ledger
        ledger.sync(self.session, self.remote, apply=True)
        self.replace_draft('replaced without consuming a repair', 'DRAFT_READY')
        verdict = ledger.plan(self.remote.raw()[0], self.session.raw()[0])
        self.assertEqual(verdict['status'], 'INCONSISTENT')
        self.assertIn('Submission replaced without a repair', ' '.join(verdict['reasons']))

    def test_a_review_with_no_event_cannot_be_silently_dropped(self):
        self.promote()
        ledger.sync(self.session, self.remote, apply=True)
        review = self.session.put_document({'review': 'recorded without an event, as older code did'})
        self.session.mutate(lambda s: s.setdefault('reviews', {}).update({'TH-000003': review}))
        verdict = ledger.plan(self.remote.raw()[0], self.session.raw()[0])
        self.assertEqual(verdict['status'], 'INCONSISTENT')
        self.assertIn('review TH-000003', ' '.join(verdict['reasons']))

    def test_a_session_ledger_may_never_carry_intents_or_receipts_the_publisher_did_not_write(self):
        self.promote()
        ledger.sync(self.session, self.remote, apply=True)

        def forge(state):
            state['intents']['TH-000003'] = {'phase': 'NOT_SENT', 'language': 'en', 'article_sha': 'a' * 64, 'reserved_at': now()}
            event(state, 'CLAIM', topic_id='TH-000003')
        self.session.mutate(forge)
        verdict = ledger.plan(self.remote.raw()[0], self.session.raw()[0])
        self.assertEqual(verdict['status'], 'INCONSISTENT')
        self.assertIn('never wrote', ' '.join(verdict['reasons']))

    def test_a_session_ledger_that_forgets_a_publication_intent_or_forges_a_receipt_is_refused(self):
        live = legacy_live()
        live['topics']['TH-000003'] = dict(topic('TH-000003'), status='BLOCKED')
        event(live, 'RESEARCH_INTAKE', topic_ids=['TH-000003'])
        live['intents']['TH-000003'] = {'phase': 'NEEDS_RECONCILIATION', 'language': 'en', 'article_sha': 'a' * 64, 'reserved_at': now()}
        forgetful = copy.deepcopy(live)
        event(forgetful, 'CLAIM', topic_id='TH-000001')
        forgetful['intents'].clear()
        verdict = ledger.plan(live, forgetful)
        self.assertEqual(verdict['status'], 'INCONSISTENT')
        self.assertIn('Publication intent differs', ' '.join(verdict['reasons']))
        forger = copy.deepcopy(live)
        event(forger, 'CLAIM', topic_id='TH-000001')
        forger['receipts']['TH-000001'] = {'document': 'b' * 64, 'wp_id': 7, 'url': SITE + '/x/', 'language': 'en'}
        verdict = ledger.plan(live, forger)
        self.assertEqual(verdict['status'], 'INCONSISTENT')
        self.assertIn('receipt the publisher never wrote', ' '.join(verdict['reasons']))

    def test_an_unresolved_intent_cannot_be_rewritten_by_a_session(self):
        self.promote()
        article = self.session.raw()[0]['submissions']['TH-000003']['article_sha']

        def publisher_state(state):
            state['intents']['TH-000003'] = {'phase': 'NEEDS_RECONCILIATION', 'language': 'en', 'article_sha': article, 'reserved_at': now()}
            state['topics']['TH-000003']['status'] = 'BLOCKED'
            event(state, 'PUBLISH_OUTCOME_UNCERTAIN', topic_id='TH-000003')
        self.remote.mutate(publisher_state)
        ledger.sync(self.session, self.remote, apply=True)

        def tamper(state):
            state['intents']['TH-000003']['phase'] = 'NOT_SENT'  # would let the next run POST the same key again
            state['topics']['TH-000003']['status'] = 'READY'
            event(state, 'CLAIM', topic_id='TH-000003')
        self.session.mutate(tamper)
        verdict = ledger.plan(self.remote.raw()[0], self.session.raw()[0])
        self.assertEqual(verdict['status'], 'INCONSISTENT')
        self.assertIn('intent', ' '.join(verdict['reasons']).lower())

    def test_receipts_research_requests_and_reviews_of_the_shared_ledger_survive(self):
        for name, damage, text in (
                ('receipt', lambda s: s['receipts'].pop('TH-000003'), 'Receipt differs'),
                ('request', lambda s: s['research_requests'].pop('research-x'), 'Research request missing'),
                ('review', lambda s: s['reviews'].pop('TH-000003'), 'Review changed')):
            with self.subTest(name):
                live = legacy_live()
                live['topics']['TH-000003'] = topic('TH-000003')
                event(live, 'RESEARCH_INTAKE', topic_ids=['TH-000003'])
                live['submissions']['TH-000003'] = {'article_sha': 'a' * 64, 'session': 's', 'agent_id': 'a', 'slot': 'W1', 'fence': 'f',
                                                    'submitted_at': now(), 'repair_count': 0, 'commit': 'c'}
                live['receipts']['TH-000003'] = {'document': 'b' * 64, 'wp_id': 5, 'url': SITE + '/x/', 'language': 'en'}
                live['research_requests']['research-x'] = {'request_id': 'research-x', 'status': 'FULFILLED'}
                live['reviews'] = {'TH-000003': 'c' * 64}
                handoff = copy.deepcopy(live)
                event(handoff, 'CLAIM', topic_id='TH-000003')
                damage(handoff)
                verdict = ledger.plan(live, handoff)
                self.assertEqual(verdict['status'], 'INCONSISTENT')
                self.assertIn(text, ' '.join(verdict['reasons']))

    def test_an_expired_publisher_lease_does_not_block_but_a_live_one_does(self):
        live = legacy_live()
        handoff = advanced(live)
        live['publisher_lease'] = {'fence': 'x', 'expires_at': 1}
        self.assertEqual(ledger.plan(live, handoff)['status'], 'FAST_FORWARD')
        live['publisher_lease'] = {'fence': 'x', 'expires_at': 9e12}
        self.assertEqual(ledger.plan(live, handoff)['status'], 'BLOCKED')

    def test_a_lease_the_session_ledger_carries_never_reaches_the_shared_ledger(self):
        documents = ledger.read_documents(self.session.directory / 'documents')
        handoff = advanced(self.base, doc=next(iter(documents)))
        handoff['publisher_lease'] = {'fence': 'stale', 'expires_at': 1}
        result = ledger.promote(self.remote, handoff, documents, apply=True)
        self.assertTrue(result['applied'], result)
        self.assertNotIn('publisher_lease', self.remote.read())

    def test_source_snapshots_that_articles_point_to_are_found_and_fetched(self):
        snapshot = self.remote.put_document({'url': SITE + '/source/', 'excerpt': 'evidence'})
        article = self.remote.put_document({'title': 'An article', 'sources': [{'url': SITE + '/source/', 'document': snapshot, 'supports': 'x'}]})
        live = copy.deepcopy(self.base)
        live['topics']['TH-000003'] = topic('TH-000003')
        event(live, 'RESEARCH_INTAKE', topic_ids=['TH-000003'])
        live['submissions']['TH-000003'] = {'article_sha': article, 'session': 's', 'agent_id': 'a', 'slot': 'W1', 'fence': 'f',
                                            'submitted_at': now(), 'repair_count': 0, 'commit': 'c'}
        self.assertNotIn(snapshot, ledger.referenced(live))
        self.assertIn(snapshot, ledger.referenced(live, self.remote.get_document))
        self.api.files[GitStore.state_path] = live
        fresh = LocalStore(Path(self.temp.name) / 'fresh')
        save(fresh.path, self.base)
        self.assertEqual(ledger.sync(fresh, self.remote, apply=True)['status'], 'FAST_FORWARD')
        self.assertEqual(fresh.get_document(snapshot)['excerpt'], 'evidence')  # a fresh session has the evidence its QA will need


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
    """The session ledger committed in this repository: complete, valid, and built on the history factory-state held on 2026-10-23.

    The first hand-over was planned against that three-event snapshot. The shared ledger has moved on since (the queue promoted a session,
    ran QA and published nine posts), so the snapshot is no longer what a plan is compared with; what must stay true is that the committed
    ledger keeps every document, keeps that history as its beginning and never touches the nine V5 drafts.
    """

    def test_the_committed_session_ledger_is_complete_and_keeps_the_history_and_every_v5_draft(self):
        live = load(FIXTURE)
        handoff = load(ROOT / 'data/state/factory.json')
        documents = ledger.read_documents(ROOT / 'data/documents')
        missing = [x for x in ledger.referenced(handoff) if x not in documents]
        self.assertEqual(missing, [])
        state = migrate(copy.deepcopy(handoff))
        validate(state)
        self.assertEqual(ledger.logical(handoff['events'])[:len(live['events'])], ledger.logical(live['events']))  # sessions never rewrite shared history
        self.assertGreaterEqual(len(state['submissions']), 9)
        # The 57 legacy English topics of the V5 session are still there; topics admitted from matrix rows (TH-VI-####, TH-EN-####) may have been added since.
        self.assertEqual(len([k for k, t in state['topics'].items() if t['language'] == 'en' and k.startswith('TH-0')]), 57)
        self.assertTrue(all(t['language'] in ('en', 'vi') for t in state['topics'].values()))
        # The nine V5 drafts are the very same immutable documents: never rewritten, never counted twice.
        self.assertEqual({k: v['article_sha'] for k, v in state['submissions'].items() if k.startswith('TH-0')}, self.V5_DRAFTS)
        self.assertEqual(len([k for k in state['submissions'] if k.startswith('TH-0')]), 9)

    # Immutable documents of the V5 session, addressed by their own digest: they cannot change, so these stay true.
    V5_DRAFTS = {'TH-000001': '9239511fa076230a34d9eadb354fd1baccc9046d256f7e56fcbcd9cdf5527108',
                 'TH-000002': '0424d20de1a865635af3427fff418482f2cbcb46d16845e381d9e53677170526',
                 'TH-000003': '08893c452e4ebe616a8e1584420f2086d4638a224a75a49a18ed1a7cac23475c',
                 'TH-000004': '922d26572e8094d7635a9c76e5543f01c17eb9e026ea3f228680c31e5e7964bb',
                 'TH-000005': '4c9c33572db4391b8f446e8758157625b509808dc011faee63299c6740b2a316',
                 'TH-000006': '6470a5685780d07b6635001844ee40877e5df8807295f78307d6dd63e1905704',
                 'TH-000007': '1ca276f5ca3ab89804d58ad76b15eb955143d2f795dda72775c225e5e00e689f',
                 'TH-000008': '922c56c8c1b7b01c43393a923418f5e2e61bce7b43cc74f9be5d48489001a196',
                 'TH-000009': '095e553862927772bebab439268918959b31c476eb8cd3672e56d0cfb4acd7c4'}
    TH3_ARTICLE = '08893c452e4ebe616a8e1584420f2086d4638a224a75a49a18ed1a7cac23475c'
    TH5_REVIEW = '7d4bad6b4deab4218185ac9e11d702571aa402607d5fb91cc572403d9d170386'

    def test_an_english_guide_that_quotes_vietnamese_legal_terms_is_not_mixed_language(self):
        from thuha.audit import parse
        from thuha.language import screen
        article = ledger.read_documents(ROOT / 'data/documents')[self.TH3_ARTICLE]
        text = ' '.join(parse(article['body_html']).text)
        self.assertEqual(screen('en', text), [])  # it used to fail on five quoted Vietnamese function words in 2,000 tokens
        self.assertIn('VIETNAMESE_MIXED_INTO_ENGLISH', screen('en', text + ' ' + 'Chúng tôi có những xe máy cho bạn và của bạn để đi. ' * 40))

    def test_a_review_written_before_schema_five_stays_valid_for_english_only(self):
        from thuha.quality import review_checks_ok, review_language
        review = ledger.read_documents(ROOT / 'data/documents')[self.TH5_REVIEW]
        self.assertNotIn('language', review)
        self.assertEqual(review_language(review), 'en')
        self.assertTrue(review_checks_ok(review, 'en'))
        self.assertFalse(review_checks_ok(review, 'vi'))  # no native_language / no_machine_translation attestation

    def test_no_image_of_the_stored_inventory_can_illustrate_a_vietnamese_article(self):
        """The 15 captioned images of the site are English captions; the dashboard's NEEDS_MEDIA for Vietnamese is true."""
        from thuha.language import screen_alt
        inventory = ledger.read_documents(ROOT / 'data/documents')['da7c6de42b8554be3a7e0912c9598fb30c265ee8c9a8ce7f788be23412b5d42c']
        captioned = [m for m in inventory['media'] if str(m.get('alt_text', '')).strip()]
        self.assertEqual(len(captioned), 15)
        self.assertEqual([m['id'] for m in captioned if not screen_alt('vi', m['alt_text'])], [])
        self.assertEqual(len([m for m in captioned if not screen_alt('en', m['alt_text'])]), 15)

    def test_the_session_documents_are_complete_and_untouched(self):
        documents = ledger.read_documents(ROOT / 'data/documents')
        self.assertGreaterEqual(len(documents), 277)


if __name__ == '__main__':
    unittest.main()
