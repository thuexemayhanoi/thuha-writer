"""Putting back the drafts of a replaced session ledger: the order of the commands, what is skipped and where it stops (no network)."""
import json
import tempfile
import unittest
from pathlib import Path

from thuha import replay
from thuha.common import digest


class FakeCli:
    """Just enough of the thuha CLI to show what `replay` asks of it, with the ledger kept as a plain dict."""

    def __init__(self, topics=None, refuse=()):
        self.topics = {tid: dict(topic_id=tid, **fields) for tid, fields in (topics or {}).items()}
        self.submissions = {}
        self.calls = []
        self.refuse = set(refuse)
        self.leases = {}

    def __call__(self, *argv):
        self.calls.append(argv)
        command, args = argv[0], list(argv[1:])
        option = lambda name: args[args.index(name) + 1]
        if command == 'resume':
            tid = option('--topic-id')
            if tid not in self.topics:
                return 1, {'status': 'BLOCKED', 'error': "'%s'" % tid}
            return 0, {'topic': self.topics[tid], 'submission': self.submissions.get(tid)}
        if command == 'intake':
            for topic in json.loads(Path(option('--file')).read_text(encoding='utf-8')):
                self.topics[topic['topic_id']] = dict(topic, status='PLANNED')
            return 0, {'admitted': []}
        if command == 'claim':
            tid = option('--revise') if '--revise' in args else option('--topic-id')
            if tid in self.refuse and 'claim' in self.refuse:
                return 1, {'status': 'BLOCKED', 'error': 'no free slot'}
            self.leases['W1'] = tid
            return 0, {'topic_id': tid, 'slot': 'W1', 'fence': 'f-' + tid, 'session': option('--session')}
        if command == 'submit':
            article = json.loads(Path(option('--file')).read_text(encoding='utf-8'))
            tid = article['topic_id']
            if tid in self.refuse and 'submit' in self.refuse:
                return 1, {'status': 'NOT_SUBMITTED', 'problems': ['a fault']}
            sha = digest(article)
            self.submissions[tid] = {'article_sha': sha}
            self.topics[tid]['status'] = 'READY'
            self.topics[tid].pop('waiting_for', None)
            return 0, {'submission': {'article_sha': sha}, 'qa': {'status': 'PASS'}}
        if command == 'release':
            self.leases.pop(option('--slot'), None)
            return 0, {}
        raise AssertionError(argv)

    def commands(self):
        return [c[0] for c in self.calls if c[0] != 'resume']


class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.documents = Path(self.temp.name)
        self.articles = {}

    def document(self, tid, **fields):
        article = dict(topic_id=tid, body_html='<p>%s</p>' % tid, **fields)
        sha = digest(article)
        (self.documents / (sha + '.json')).write_text(json.dumps(article), encoding='utf-8')
        self.articles[tid] = article
        return sha

    def draft(self, tid, when, status='READY'):
        return {'topic_id': tid, 'article_sha': self.document(tid), 'session': 's-' + tid, 'agent_id': 'a-' + tid,
                'submitted_at': when, 'status': status, 'waiting_for': None}

    def plan(self, drafts, topics=()):
        return {'status': 'REPLACED', 'unpromoted': {'events': {}, 'drafts': list(drafts), 'topics': list(topics)}}

    def test_unknown_topics_are_admitted_once_and_each_draft_goes_through_claim_then_submit_in_submission_order(self):
        late, early = self.draft('TH-EN-0002', '2026-10-23T12:00:00'), self.draft('TH-EN-0001', '2026-10-23T10:00:00')
        known = self.draft('TH-VI-0003', '2026-10-23T11:00:00', 'WAITING_DATA')
        topics = [{'topic_id': t, 'language': 'en', 'proposed_title': 't'} for t in ('TH-EN-0001', 'TH-EN-0002')]
        cli = FakeCli({'TH-VI-0003': {'status': 'WAITING_DATA', 'waiting_for': []}})
        results = replay.replay(cli, self.plan([late, known, early], topics), self.documents, log=lambda m: None)
        self.assertEqual(cli.commands(), ['intake', 'claim', 'submit', 'claim', 'submit', 'claim', 'submit'])
        self.assertEqual([r['topic_id'] for r in results], ['TH-EN-0001', 'TH-VI-0003', 'TH-EN-0002'])
        self.assertTrue(all(r['result'] == 'SUBMITTED' and r['qa'] == 'PASS' for r in results))
        claims = {c[c.index('--revise') + 1 if '--revise' in c else c.index('--topic-id') + 1]: c for c in cli.calls if c[0] == 'claim'}
        self.assertIn('--revise', claims['TH-VI-0003'])  # a waiting draft is completed, not claimed again as a new topic
        self.assertIn('--topic-id', claims['TH-EN-0001'])
        self.assertEqual(claims['TH-EN-0001'][1:5], ('--session', 's-TH-EN-0001', '--agent-id', 'a-TH-EN-0001'))  # the identity the draft was written under
        submit = next(c for c in cli.calls if c[0] == 'submit')
        self.assertEqual(submit[-2:], ('--waiting-for', 'auto'))  # a wait is declared only where the data is really missing

    def test_a_topic_the_shared_ledger_already_knows_is_not_admitted_again(self):
        item = self.draft('TH-EN-0001', '2026-10-23T10:00:00')
        cli = FakeCli({'TH-EN-0001': {'status': 'PLANNED'}})
        replay.replay(cli, self.plan([item], [{'topic_id': 'TH-EN-0001'}]), self.documents, log=lambda m: None)
        self.assertNotIn('intake', cli.commands())

    def test_a_draft_that_is_already_there_or_whose_topic_moved_on_is_reported_and_left_alone(self):
        same = self.draft('TH-EN-0001', '2026-10-23T10:00:00')
        moved = self.draft('TH-EN-0002', '2026-10-23T11:00:00')
        cli = FakeCli({'TH-EN-0001': {'status': 'READY'}, 'TH-EN-0002': {'status': 'PUBLISHED'}})
        cli.submissions['TH-EN-0001'] = {'article_sha': same['article_sha']}
        results = replay.replay(cli, self.plan([same, moved]), self.documents, log=lambda m: None)
        self.assertEqual([(r['topic_id'], r['result']) for r in results], [('TH-EN-0001', 'ALREADY_THERE'), ('TH-EN-0002', 'SKIPPED')])
        self.assertEqual(cli.commands(), [])  # no claim, no submit

    def test_a_rewritten_article_is_submitted_instead_of_the_stored_document(self):
        item = self.draft('TH-VI-0003', '2026-10-23T10:00:00', 'WAITING_DATA')
        rewritten = Path(self.temp.name) / 'new.json'
        article = dict(self.articles['TH-VI-0003'], body_html='<p>linked to a live page</p>')
        rewritten.write_text(json.dumps(article), encoding='utf-8')
        cli = FakeCli({'TH-VI-0003': {'status': 'WAITING_DATA'}})
        results = replay.replay(cli, self.plan([item]), self.documents, overrides={'TH-VI-0003': rewritten}, log=lambda m: None)
        self.assertEqual((results[0]['result'], results[0]['revised'], results[0]['article_sha']), ('SUBMITTED', True, digest(article)))
        self.assertNotEqual(results[0]['article_sha'], item['article_sha'])
        submit = next(c for c in cli.calls if c[0] == 'submit')
        self.assertEqual(Path(submit[submit.index('--file') + 1]), rewritten)

    def test_a_refused_submit_releases_the_lease_and_stops_with_what_was_done(self):
        first, second = self.draft('TH-EN-0001', '2026-10-23T10:00:00'), self.draft('TH-EN-0002', '2026-10-23T11:00:00')
        cli = FakeCli({'TH-EN-0001': {'status': 'PLANNED'}, 'TH-EN-0002': {'status': 'PLANNED'}}, refuse={'TH-EN-0002', 'submit'})
        with self.assertRaises(replay.ReplayStop) as raised:
            replay.replay(cli, self.plan([first, second]), self.documents, log=lambda m: None)
        self.assertIn('TH-EN-0002', raised.exception.args[0])
        self.assertEqual([r['topic_id'] for r in raised.exception.args[1]], ['TH-EN-0001'])
        self.assertEqual(cli.leases, {})  # the writer slot is free again
        self.assertEqual(cli.commands()[-1], 'release')

    def test_a_refused_claim_stops_without_submitting(self):
        item = self.draft('TH-EN-0001', '2026-10-23T10:00:00')
        cli = FakeCli({'TH-EN-0001': {'status': 'PLANNED'}}, refuse={'TH-EN-0001', 'claim'})
        with self.assertRaisesRegex(replay.ReplayStop, 'claim of TH-EN-0001 failed'):
            replay.replay(cli, self.plan([item]), self.documents, log=lambda m: None)
        self.assertNotIn('submit', cli.commands())

    def test_a_missing_document_stops_after_releasing_the_lease(self):
        item = self.draft('TH-EN-0001', '2026-10-23T10:00:00')
        (self.documents / (item['article_sha'] + '.json')).unlink()
        cli = FakeCli({'TH-EN-0001': {'status': 'PLANNED'}})
        with self.assertRaisesRegex(replay.ReplayStop, 'document of TH-EN-0001 is missing'):
            replay.replay(cli, self.plan([item]), self.documents, log=lambda m: None)
        self.assertEqual((cli.commands()[-1], cli.leases), ('release', {}))

    def test_a_draft_whose_topic_is_unknown_and_has_no_admission_record_stops_the_run(self):
        item = self.draft('TH-EN-0001', '2026-10-23T10:00:00')
        with self.assertRaisesRegex(replay.ReplayStop, 'not in the shared ledger'):
            replay.replay(FakeCli(), self.plan([item]), self.documents, log=lambda m: None)

    def test_only_limits_the_topics_and_the_plan_may_be_the_whole_sync_result_or_its_block(self):
        one, two = self.draft('TH-EN-0001', '2026-10-23T10:00:00'), self.draft('TH-EN-0002', '2026-10-23T11:00:00')
        cli = FakeCli({'TH-EN-0001': {'status': 'PLANNED'}, 'TH-EN-0002': {'status': 'PLANNED'}})
        results = replay.replay(cli, self.plan([one, two])['unpromoted'], self.documents, only={'TH-EN-0002'}, log=lambda m: None)
        self.assertEqual([r['topic_id'] for r in results], ['TH-EN-0002'])
        with self.assertRaisesRegex(ValueError, 'no drafts'):
            replay.listing({'status': 'FAST_FORWARD'})


if __name__ == '__main__':
    unittest.main()
