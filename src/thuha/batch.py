"""Claim, build and store a folder of finished article bodies, one topic at a time.

A writer who has finished several articles otherwise types the same four commands for each of them:

    claim --topic-id (or --revise for a draft that waits)  ->  build --body --meta  ->  submit --waiting-for auto  (or release)

`draft_batch` runs exactly those commands and decides nothing about content. The `build` precheck stays the judge: a draft goes to `submit`
only when it says `ready_to_submit`, and `submit` keeps its own guard, its data-wait classifier and automatic QA. A draft that is not ready
is reported with what to fix, its lease is released, and the batch goes on with the next topic. The first refusal of a ledger command
(`claim`, `build` without an answer, `submit`) stops the run after releasing the lease. `dry_run` only builds: no claim, no ledger write.

Files: `FOLDER/<TOPIC_ID>.html` is the body and `<TOPIC_ID>.json` the meta file (`meta_folder` to keep them apart): seo_title,
meta_description, featured_media, `claims` (shorthand such as "manual:month"), business_claims, extra_sources.
`run(*argv) -> (exit code, parsed JSON)` is the thuha CLI with the caller's global flags already set.
"""
import json
import tempfile
from pathlib import Path

CLAIMABLE = {'PLANNED': '--topic-id', 'WAITING_DATA': '--revise'}
DRY_SESSION = ('dry-run', 'dry-run-agent')  # `build` without a lease names a session only to fill the article's provenance


class BatchStop(Exception):
    """The run stopped at a problem it cannot go past; the results so far are in `args[1]`."""


def files_of(folder, topic_id, meta_folder=None):
    folder = Path(folder)
    return folder / (topic_id + '.html'), Path(meta_folder or folder) / (topic_id + '.json')


def draft_batch(run, folder, ids, session, agent_id, meta_folder=None, out_folder=None, dry_run=False, log=print):
    """Store every listed draft that is ready; returns one result per topic, in the order given."""
    results = []

    def stop(message):
        log('STOP: ' + message)
        raise BatchStop(message, results)

    def topic_state(tid):
        code, out = run('resume', '--topic-id', tid)
        return (out.get('topic') or {}) if code == 0 else {}

    ids = list(dict.fromkeys(ids))
    problems = []
    for tid in ids:
        body, meta = files_of(folder, tid, meta_folder)
        problems += ['%s: %s is missing' % (tid, f.name) for f in (body, meta) if not f.exists()]
        status = topic_state(tid).get('status')
        if status is None:
            problems.append('%s is not in the ledger: admit it first (`intake`)' % tid)
        elif not dry_run and status not in CLAIMABLE:
            problems.append('%s is %s: only a PLANNED topic or a WAITING_DATA draft can be written here' % (tid, status))
    if problems:  # nothing is claimed while anything is wrong: a half-run batch would leave leases behind
        stop('; '.join(problems))

    with tempfile.TemporaryDirectory() as scratch:
        out_dir = Path(out_folder or scratch)
        out_dir.mkdir(parents=True, exist_ok=True)
        for tid in ids:
            body, meta = files_of(folder, tid, meta_folder)
            article = out_dir / ('article-' + tid + '.json')
            lease = None
            if not dry_run:
                mode = CLAIMABLE[topic_state(tid)['status']]
                code, lease = run('claim', '--session', session, '--agent-id', agent_id, mode, tid)
                if code != 0 or lease.get('topic_id') != tid:
                    stop('claim of %s failed: %s' % (tid, json.dumps(lease, ensure_ascii=False)[:500]))
            identity = ('--session', DRY_SESSION[0], '--agent-id', DRY_SESSION[1]) if dry_run else ()

            def release():
                if lease:
                    run('release', '--slot', lease['slot'], '--session', session, '--fence', lease['fence'])

            code, built = run('build', '--topic-id', tid, '--body', str(body), '--meta', str(meta), '--out', str(article), *identity)
            if 'ready_to_submit' not in built:
                release()
                stop('build of %s gave no answer: %s' % (tid, json.dumps(built, ensure_ascii=False)[:700]))
            item = {'topic_id': tid, 'score': built.get('score'), 'potential_score': built.get('potential_score'), 'word_count': built.get('word_count'),
                    'waiting_for': built.get('submit_waiting_for') or [], 'lint': [f['code'] for f in built.get('lint', []) if f.get('severity') == 'fix']}
            if not built['ready_to_submit']:
                release()
                item.update(result='NOT_READY', problems=built.get('submit_problems') or [], content_fails=built.get('content_fails') or [], fixes=built.get('fixes') or {})
                results.append(item)
                log('%s not ready: %s' % (tid, '; '.join(item['problems'])[:300]))
                continue
            if dry_run:
                item['result'] = 'WOULD_SUBMIT'
                results.append(item)
                log('%s would be submitted (score %s, %s words%s)' % (tid, item['score'], item['word_count'], ', waiting for ' + ', '.join(item['waiting_for']) if item['waiting_for'] else ''))
                continue
            code, out = run('submit', '--slot', lease['slot'], '--session', session, '--fence', lease['fence'], '--file', str(article), '--waiting-for', 'auto')
            if code != 0:
                release()
                stop('submit of %s was refused: %s' % (tid, json.dumps(out, ensure_ascii=False)[:700]))
            after = topic_state(tid)
            item.update(result='SUBMITTED', status=after.get('status'), waiting_for=after.get('waiting_for') or [], qa=(out.get('qa') or {}).get('status'),
                        article_sha=(out.get('submission') or {}).get('article_sha'))
            results.append(item)
            log('%s submitted -> %s %s' % (tid, item['status'], ', '.join(item['waiting_for'])))
    return results
