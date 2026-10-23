"""Submit again the drafts a replaced session ledger held.

`sync --apply --discard-unpromoted` replaces a diverged session ledger with the shared one and lists what the session held that
the shared ledger lacked (`unpromoted`: its drafts, in submission order, and the records of the topics only the session had
admitted). Nothing is lost, because every immutable document stays where it is, but the shared ledger does not have those drafts.
`replay` puts them back through the normal gates, one command at a time, exactly as a writer would:

    intake (topics the shared ledger does not know)  ->  claim (--revise when the draft waits, --topic-id when it is planned)
    ->  submit --waiting-for auto  with the stored document, or with a rewritten article given in `overrides`

It decides nothing about content and bypasses nothing: the submit guard, the data-wait classifier and automatic QA run as they
always do, a draft whose topic has moved on in the shared ledger is skipped and reported, and the first refusal stops the run
after releasing its lease. `run(*argv) -> (exit code, parsed JSON)` is the thuha CLI with the caller's global flags already set.
"""
import json
import tempfile
from pathlib import Path

from .common import digest, load


class ReplayStop(Exception):
    """The run stopped at the first problem; the results so far are in `args[1]`."""


def draft_order(drafts):
    return sorted(drafts, key=lambda d: (d.get('submitted_at') or '', d['topic_id']))


def listing(plan):
    """The `unpromoted` block of a `sync --discard-unpromoted` result (or the block itself)."""
    block = plan.get('unpromoted', plan)
    if 'drafts' not in block:
        raise ValueError('The plan has no drafts: pass the JSON printed by `sync --apply --discard-unpromoted`')
    return block


def replay(run, plan, documents, only=(), overrides=None, log=print):
    """Re-submit the listed drafts; returns one result per draft. `only` limits topics, `overrides` maps a topic to an article file."""
    block = listing(plan)
    overrides = {k: Path(v) for k, v in (overrides or {}).items()}
    documents = Path(documents)
    results = []

    def stop(message):
        log('STOP: ' + message)
        raise ReplayStop(message, results)

    def current(tid):
        code, out = run('resume', '--topic-id', tid)
        return out if code == 0 and out.get('topic') else None

    wanted = [t for t in block.get('topics', []) if not only or t['topic_id'] in only]
    unknown = [t for t in wanted if current(t['topic_id']) is None]
    if unknown:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'candidates.json'
            path.write_text(json.dumps(unknown, ensure_ascii=False), encoding='utf-8')
            code, out = run('intake', '--file', str(path))
        if code != 0:
            stop('intake of %s was refused: %s' % (', '.join(t['topic_id'] for t in unknown), json.dumps(out, ensure_ascii=False)[:400]))
        log('admitted again: ' + ', '.join(t['topic_id'] for t in unknown))
    for draft in draft_order(block['drafts']):
        tid = draft['topic_id']
        if only and tid not in only:
            continue
        state = current(tid)
        if state is None:
            stop('%s is not in the shared ledger and the plan holds no admission record for it' % tid)
        status = state['topic']['status']
        sub = state.get('submission') or {}
        if tid not in overrides and sub.get('article_sha') == draft['article_sha'] and status not in ('WAITING_DATA', 'PLANNED', 'CLAIMED'):
            results.append({'topic_id': tid, 'result': 'ALREADY_THERE', 'status': status})
            log('%s already there (%s)' % (tid, status))
            continue
        if status == 'WAITING_DATA':
            mode = ['--revise', tid]
        elif status == 'PLANNED':
            mode = ['--topic-id', tid]
        else:
            results.append({'topic_id': tid, 'result': 'SKIPPED', 'status': status, 'why': 'the shared ledger has moved on for this topic'})
            log('%s skipped: it is %s in the shared ledger' % (tid, status))
            continue
        code, lease = run('claim', '--session', draft['session'], '--agent-id', draft['agent_id'], *mode)
        if code != 0 or lease.get('topic_id') != tid:
            stop('claim of %s failed: %s' % (tid, json.dumps(lease, ensure_ascii=False)[:500]))
        path = overrides.get(tid) or documents / (draft['article_sha'] + '.json')
        if not path.exists():
            run('release', '--slot', lease['slot'], '--session', draft['session'], '--fence', lease['fence'])
            stop('the document of %s is missing: %s' % (tid, path))
        expected = digest(load(path))
        code, out = run('submit', '--slot', lease['slot'], '--session', draft['session'], '--fence', lease['fence'], '--file', str(path), '--waiting-for', 'auto')
        stored = (out.get('submission') or {}).get('article_sha')
        if code != 0 and stored != expected:
            run('release', '--slot', lease['slot'], '--session', draft['session'], '--fence', lease['fence'])
            stop('submit of %s was refused: %s' % (tid, json.dumps(out, ensure_ascii=False)[:700]))
        after = (current(tid) or {}).get('topic', {})
        item = {'topic_id': tid, 'result': 'SUBMITTED' if stored == expected else 'DIFFERENT', 'revised': tid in overrides, 'status': after.get('status'),
                'waiting_for': after.get('waiting_for'), 'qa': (out.get('qa') or {}).get('status'), 'article_sha': stored}
        results.append(item)
        log('%s %s -> %s %s' % (tid, item['result'], item['status'], item['waiting_for'] or ''))
        if item['result'] != 'SUBMITTED':
            stop('the stored article of %s is not the one that was submitted' % tid)
    return results
