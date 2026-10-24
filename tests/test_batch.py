"""Storing a folder of finished drafts: the order of the commands, what is released, what is skipped and where the run stops (no network)."""
import json
import tempfile
import unittest
from pathlib import Path

from thuha import batch


class FakeCli:
    """Just enough of the thuha CLI to show what `draft_batch` asks of it, with the ledger kept as a plain dict."""

    def __init__(self, topics, not_ready=(), refuse=(), silent=()):
        self.topics = {tid: dict(topic_id=tid, status=status) for tid, status in topics.items()}
        self.not_ready, self.refuse, self.silent = set(not_ready), set(refuse), set(silent)
        self.calls, self.leases = [], {}

    def __call__(self, *argv):
        self.calls.append(argv)
        command, args = argv[0], list(argv[1:])
        option = lambda name: args[args.index(name) + 1]
        if command == 'resume':
            tid = option('--topic-id')
            return (0, {'topic': self.topics[tid]}) if tid in self.topics else (1, {'status': 'BLOCKED', 'error': "'%s'" % tid})
        if command == 'claim':
            tid = option('--revise') if '--revise' in args else option('--topic-id')
            if 'claim' in self.refuse:
                return 1, {'status': 'BLOCKED', 'error': 'no free slot'}
            self.leases['W1'] = tid
            return 0, {'topic_id': tid, 'slot': 'W1', 'fence': 'f-' + tid}
        if command == 'build':
            tid = option('--topic-id')
            if tid in self.silent:
                return 1, {'status': 'BLOCKED', 'error': 'inventory unreadable'}
            Path(option('--out')).write_text(json.dumps({'topic_id': tid}), encoding='utf-8')
            if tid in self.not_ready:
                return 1, {'score': 62.5, 'word_count': 410, 'ready_to_submit': False, 'submit_problems': ['LENGTH is under the bar'],
                           'content_fails': ['LENGTH'], 'fixes': {'LENGTH': 'write more'}, 'lint': [{'code': 'LINT_PRICE_NOT_APPROVED', 'severity': 'fix'}, {'code': 'LINT_KEYWORD_NOT_IN_BODY', 'severity': 'consider'}]}
            waits = ['FEATURED_MEDIA'] if self.topics[tid]['status'] == 'WAITING_DATA' else []
            return 0, {'score': 100.0, 'potential_score': 100.0, 'word_count': 800, 'ready_to_submit': True, 'submit_waiting_for': waits, 'lint': []}
        if command == 'submit':
            tid = self.leases['W1']
            if tid in self.refuse and 'submit' in self.refuse:
                return 1, {'status': 'NOT_SUBMITTED', 'problems': ['a fault']}
            self.topics[tid]['status'] = 'READY'
            del self.leases['W1']  # a stored draft frees the writer slot
            return 0, {'submission': {'article_sha': 'sha-' + tid}, 'qa': {'status': 'PASS'}}
        if command == 'release':
            self.leases.pop(option('--slot'), None)
            return 0, {}
        raise AssertionError(argv)

    def commands(self):
        return [c[0] for c in self.calls if c[0] != 'resume']


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)

    def files(self, *ids, folder=None, meta_folder=None):
        for tid in ids:
            (Path(folder or self.folder) / (tid + '.html')).write_text('<p>%s</p>' % tid, encoding='utf-8')
            (Path(meta_folder or folder or self.folder) / (tid + '.json')).write_text(json.dumps({'seo_title': 't', 'meta_description': 'm'}), encoding='utf-8')

    def run_batch(self, cli, ids, **kw):
        return batch.draft_batch(cli, self.folder, ids, kw.pop('session', 's-batch'), kw.pop('agent_id', 'a-batch'), log=lambda m: None, **kw)

    def test_each_topic_goes_through_claim_build_submit_and_a_waiting_draft_is_revised_not_claimed_anew(self):
        self.files('TH-EN-0001', 'TH-VI-0002')
        cli = FakeCli({'TH-EN-0001': 'PLANNED', 'TH-VI-0002': 'WAITING_DATA'})
        results = self.run_batch(cli, ['TH-EN-0001', 'TH-VI-0002'])
        self.assertEqual(cli.commands(), ['claim', 'build', 'submit', 'claim', 'build', 'submit'])
        self.assertEqual([(r['topic_id'], r['result'], r['qa'], r['status']) for r in results], [('TH-EN-0001', 'SUBMITTED', 'PASS', 'READY'), ('TH-VI-0002', 'SUBMITTED', 'PASS', 'READY')])
        claims = [c for c in cli.calls if c[0] == 'claim']
        self.assertEqual(claims[0], ('claim', '--session', 's-batch', '--agent-id', 'a-batch', '--topic-id', 'TH-EN-0001'))
        self.assertEqual(claims[1][-2:], ('--revise', 'TH-VI-0002'))
        submit = next(c for c in cli.calls if c[0] == 'submit')
        self.assertEqual(submit[submit.index('--waiting-for') + 1], 'auto')  # a wait is declared only where the data is really missing
        self.assertEqual((submit[submit.index('--slot') + 1], submit[submit.index('--fence') + 1]), ('W1', 'f-TH-EN-0001'))
        self.assertEqual(cli.leases, {})  # nothing is left leased

    def test_the_build_names_no_session_because_the_lease_carries_the_identity(self):
        self.files('TH-EN-0001')
        cli = FakeCli({'TH-EN-0001': 'PLANNED'})
        self.run_batch(cli, ['TH-EN-0001'])
        build = next(c for c in cli.calls if c[0] == 'build')
        self.assertNotIn('--session', build)
        self.assertEqual(build[build.index('--body') + 1], str(self.folder / 'TH-EN-0001.html'))
        self.assertEqual(build[build.index('--meta') + 1], str(self.folder / 'TH-EN-0001.json'))

    def test_a_draft_that_is_not_ready_is_released_with_what_to_fix_and_the_batch_goes_on(self):
        self.files('TH-EN-0001', 'TH-EN-0002')
        cli = FakeCli({'TH-EN-0001': 'PLANNED', 'TH-EN-0002': 'PLANNED'}, not_ready={'TH-EN-0001'})
        results = self.run_batch(cli, ['TH-EN-0001', 'TH-EN-0002'])
        self.assertEqual(cli.commands(), ['claim', 'build', 'release', 'claim', 'build', 'submit'])
        first, second = results
        self.assertEqual((first['result'], first['problems'], first['content_fails'], first['fixes'], first['lint']),
                         ('NOT_READY', ['LENGTH is under the bar'], ['LENGTH'], {'LENGTH': 'write more'}, ['LINT_PRICE_NOT_APPROVED']))  # only a lint that needs a fix is listed
        self.assertEqual(second['result'], 'SUBMITTED')

    def test_a_dry_run_only_builds_and_touches_nothing(self):
        self.files('TH-EN-0001', 'TH-EN-0002')
        cli = FakeCli({'TH-EN-0001': 'PLANNED', 'TH-EN-0002': 'READY'}, not_ready={'TH-EN-0001'})
        results = self.run_batch(cli, ['TH-EN-0001', 'TH-EN-0002'], dry_run=True)
        self.assertEqual(cli.commands(), ['build', 'build'])  # no claim, no submit, no release, and a stored topic may be checked too
        self.assertEqual([r['result'] for r in results], ['NOT_READY', 'WOULD_SUBMIT'])
        build = next(c for c in cli.calls if c[0] == 'build')
        self.assertEqual(build[-4:], ('--session', 'dry-run', '--agent-id', 'dry-run-agent'))

    def test_a_waiting_topic_reports_what_it_will_wait_for(self):
        self.files('TH-VI-0002')
        cli = FakeCli({'TH-VI-0002': 'WAITING_DATA'})
        results = self.run_batch(cli, ['TH-VI-0002'], dry_run=True)
        self.assertEqual((results[0]['result'], results[0]['waiting_for']), ('WOULD_SUBMIT', ['FEATURED_MEDIA']))

    def test_nothing_is_claimed_while_any_file_or_topic_is_wrong(self):
        self.files('TH-EN-0001')
        (self.folder / 'TH-EN-0002.html').write_text('<p>x</p>', encoding='utf-8')  # no meta file
        cli = FakeCli({'TH-EN-0001': 'PLANNED', 'TH-EN-0002': 'PLANNED', 'TH-EN-0003': 'READY'})
        with self.assertRaises(batch.BatchStop) as raised:
            self.run_batch(cli, ['TH-EN-0001', 'TH-EN-0002', 'TH-EN-0003', 'TH-EN-0004'])
        message = raised.exception.args[0]
        self.assertIn('TH-EN-0002: TH-EN-0002.json is missing', message)
        self.assertIn('TH-EN-0003 is READY', message)
        self.assertIn('TH-EN-0004 is not in the ledger', message)
        self.assertEqual(cli.commands(), [])  # a half-run batch would leave leases behind

    def test_a_refused_claim_stops_without_building(self):
        self.files('TH-EN-0001')
        cli = FakeCli({'TH-EN-0001': 'PLANNED'}, refuse={'claim'})
        with self.assertRaisesRegex(batch.BatchStop, 'claim of TH-EN-0001 failed'):
            self.run_batch(cli, ['TH-EN-0001'])
        self.assertEqual(cli.commands(), ['claim'])

    def test_a_refused_submit_releases_the_lease_and_stops_with_what_was_done(self):
        self.files('TH-EN-0001', 'TH-EN-0002', 'TH-EN-0003')
        cli = FakeCli({t: 'PLANNED' for t in ('TH-EN-0001', 'TH-EN-0002', 'TH-EN-0003')})
        original = cli.__call__

        def refusing(*argv):
            if argv[0] == 'submit' and cli.leases.get('W1') == 'TH-EN-0002':
                cli.calls.append(argv)
                return 1, {'status': 'NOT_SUBMITTED', 'problems': ['a fault']}
            return original(*argv)

        with self.assertRaises(batch.BatchStop) as raised:
            self.run_batch(refusing, ['TH-EN-0001', 'TH-EN-0002', 'TH-EN-0003'])
        self.assertIn('submit of TH-EN-0002 was refused', raised.exception.args[0])
        self.assertEqual([r['topic_id'] for r in raised.exception.args[1]], ['TH-EN-0001'])
        self.assertEqual((cli.commands()[-1], cli.leases), ('release', {}))  # the writer slot is free again and the third topic was never claimed
        self.assertEqual(sum(c[0] == 'claim' for c in cli.calls), 2)

    def test_a_build_that_gives_no_answer_releases_the_lease_and_stops(self):
        self.files('TH-EN-0001')
        cli = FakeCli({'TH-EN-0001': 'PLANNED'}, silent={'TH-EN-0001'})
        with self.assertRaisesRegex(batch.BatchStop, 'build of TH-EN-0001 gave no answer'):
            self.run_batch(cli, ['TH-EN-0001'])
        self.assertEqual((cli.commands(), cli.leases), (['claim', 'build', 'release'], {}))

    def test_meta_files_may_live_in_another_folder_and_the_built_articles_can_be_kept(self):
        meta = Path(self.temp.name) / 'meta'
        keep = Path(self.temp.name) / 'built' / 'deeper'
        meta.mkdir()
        self.files('TH-EN-0001', meta_folder=meta)
        cli = FakeCli({'TH-EN-0001': 'PLANNED'})
        self.run_batch(cli, ['TH-EN-0001'], meta_folder=meta, out_folder=keep)
        build = next(c for c in cli.calls if c[0] == 'build')
        self.assertEqual(build[build.index('--meta') + 1], str(meta / 'TH-EN-0001.json'))
        self.assertTrue((keep / 'article-TH-EN-0001.json').exists())

    def test_a_topic_named_twice_is_handled_once(self):
        self.files('TH-EN-0001')
        cli = FakeCli({'TH-EN-0001': 'PLANNED'})
        results = self.run_batch(cli, ['TH-EN-0001', 'TH-EN-0001'])
        self.assertEqual((len(results), cli.commands()), (1, ['claim', 'build', 'submit']))


if __name__ == '__main__':
    unittest.main()
