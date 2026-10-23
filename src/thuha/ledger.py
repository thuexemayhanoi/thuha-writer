"""Controlled hand-over of a session ledger into the shared ledger that GitHub Actions read.

A writer session that can push only to its own branch keeps its ledger (`data/state/factory.json`) and immutable
documents (`data/documents/`) in that branch (`GitBranchStore`). Nothing reads that copy: the publisher and the
maintenance workflows read `factory-state`. `promote` moves the session ledger into `factory-state` under three rules:

* append-only: the live ledger's history must be the first part of the session ledger's history (a fast-forward).
  Anything else (the live ledger moved on, or the two never shared a history) is refused and nothing is written;
* no overwrite and no duplicate: documents are content-addressed and immutable, existing ones are compared and kept,
  every topic, submission, review, QA report and event of the live ledger survives byte for byte;
* idempotent: promoting a ledger that the live one already contains writes nothing.

The session ledger may still be schema 4. The schema migration is deterministic (see `store.migrate`), so the live
ledger and the session ledger can both have been migrated by different processes and still be comparable.
"""
import copy
import re
from pathlib import Path
from .common import canonical_json, digest, load, now
from .store import SCHEMA, event, initial, migrate, validate

DOCUMENT = re.compile(r'[a-f0-9]{64}\.json')
# Fields of a topic that never change after admission; a session ledger may not alter them.
TOPIC_FIXED = ('language', 'proposed_url', 'proposed_title', 'category_id', 'category_path', 'primary_keyword',
               'search_intent', 'sources', 'intent_review', 'admitted_at', 'cluster')


def lineage(state):
    """Events before the schema migration marker, and the events written after it.

    A ledger born under schema 5 has no marker: its whole history is the lineage and it has no tail.
    """
    events = state.get('events', [])
    for index, entry in enumerate(events):
        if entry.get('action') == 'SCHEMA_MIGRATION':
            return events[:index], events[index + 1:]
    return list(events), []


def _prefix(short, long):
    return len(short) <= len(long) and long[:len(short)] == short


def plan(live, handoff):
    """Decide what promoting `handoff` into `live` would do. Pure; raw (possibly schema 4) ledgers in, no writes."""
    result = {'status': None, 'reasons': [], 'live_version': live.get('version'), 'handoff_version': handoff.get('version')}
    try:
        validate(migrate(copy.deepcopy(live)))
        validate(migrate(copy.deepcopy(handoff)))
    except ValueError as exc:
        result.update(status='INVALID_LEDGER', reasons=[str(exc)])
        return result
    live_events, live_tail = lineage(live)
    handoff_events, _ = lineage(handoff)
    result.update(live_events=len(live_events), handoff_events=len(handoff_events), live_events_after_migration=len(live_tail))
    if _prefix(handoff_events, live_events):
        result['status'] = 'ALREADY_INCLUDED'
        return result
    if not _prefix(live_events, handoff_events):
        result.update(status='DIVERGED', reasons=['The live ledger and the session ledger do not share a history: the live ledger'
                                                  ' has events the session ledger lacks. Sync the session branch from the live'
                                                  ' ledger before promoting again; nothing was written.'])
        return result
    if live_tail:
        result.update(status='DIVERGED', reasons=['The live ledger was written after its schema migration ('
                                                  + ', '.join(sorted({e['action'] for e in live_tail})) + '); promoting would'
                                                  ' discard those events. Nothing was written.'])
        return result
    if live.get('publisher_lease'):
        result.update(status='BLOCKED', reasons=['A publisher currently holds the live ledger; promote when it has finished.'])
        return result
    problems = continuity(migrate(copy.deepcopy(live)), migrate(copy.deepcopy(handoff)))
    if problems:
        result.update(status='INCONSISTENT', reasons=problems)
        return result
    result['status'] = 'FAST_FORWARD'
    return result


def continuity(live, handoff):
    """Everything the live ledger holds must still be there, unchanged where it is evidence."""
    problems = []
    for key in live['topics']:
        if key not in handoff['topics']:
            problems.append('Topic missing from session ledger: ' + key)
            continue
        for field in TOPIC_FIXED:
            if live['topics'][key].get(field) != handoff['topics'][key].get(field):
                problems.append('Topic field changed: ' + key + '.' + field)
    for key, value in live['submissions'].items():
        new = handoff['submissions'].get(key)
        if not new or (new['article_sha'] != value['article_sha'] and new.get('repair_count', 0) <= value.get('repair_count', 0)):
            problems.append('Submission replaced without a repair: ' + key)
    for key, value in live['receipts'].items():
        if handoff['receipts'].get(key) != value:
            problems.append('Receipt differs: ' + key)
    for key, value in live['intents'].items():
        new = handoff['intents'].get(key)
        if not new or new['article_sha'] != value['article_sha']:
            problems.append('Publication intent differs: ' + key)
    for key in live['research_requests']:
        if key not in handoff['research_requests']:
            problems.append('Research request missing: ' + key)
    for key, sha in live.get('reviews', {}).items():
        if handoff.get('reviews', {}).get(key) != sha and handoff['submissions'].get(key, {}).get('article_sha') == live['submissions'].get(key, {}).get('article_sha'):
            problems.append('Review changed for an unchanged draft: ' + key)
    return problems


def merged(live, handoff, source, copied):
    """The ledger after a fast-forward: the session ledger, plus whatever is only meaningful live."""
    live, new = migrate(copy.deepcopy(live)), migrate(copy.deepcopy(handoff))
    new['controls'] = {k: bool(live['controls'].get(k)) or bool(new['controls'].get(k)) for k in ('paused', 'emergency_stop')}
    for key in ('inventory_document', 'adapter'):
        if live.get(key):
            new[key] = live[key]  # pointers that change without an event: the live value is the newer one
    new.pop('publisher_lease', None)
    event(new, 'LEDGER_PROMOTION', source=source, live_version=live['version'], handoff_version=handoff['version'],
          handoff_sha256=digest(handoff), topics=len(new['topics']), submissions=len(new['submissions']),
          reviews=len(new.get('reviews', {})), documents_copied=copied)
    return new


def read_documents(directory):
    """Every immutable document of a session branch, verified against its own address."""
    found = {}
    for path in sorted(Path(directory).glob('*.json')) if Path(directory).is_dir() else []:
        if not DOCUMENT.fullmatch(path.name):
            raise ValueError('Unexpected file in the document directory: ' + path.name)
        value = load(path)
        if digest(value) != path.stem:
            raise ValueError('Document does not match its address: ' + path.name)
        found[path.stem] = value
    return found


def promote(store, handoff, documents, source='data/state/factory.json', apply=False):
    """Fast-forward `store` (the live ledger) to `handoff`. Documents first, then one compare-and-swap of the ledger."""
    live, _ = _raw(store)
    verdict = plan(live, handoff)
    verdict['documents_in_session'] = len(documents)
    verdict['applied'] = False
    if verdict['status'] not in ('FAST_FORWARD', 'ALREADY_INCLUDED') or not apply:
        return verdict
    if verdict['status'] == 'ALREADY_INCLUDED':
        return verdict
    for sha, value in documents.items():
        store.put_document(value)  # raises on a collision; an identical document is kept as it is
    missing = [x for x in referenced(handoff) if x not in documents and not _exists(store, x)]
    if missing:
        raise ValueError('The session ledger references documents that are in neither place: ' + ', '.join(missing[:5]))
    outcome = {}

    def build(raw):
        again = plan(raw, handoff)  # re-planned against whatever the compare-and-swap just read
        if again['status'] != 'FAST_FORWARD':
            outcome.update(again)
            return None
        outcome.update(again)
        return merged(raw, handoff, source, len(documents))
    new = store.adopt(build)
    verdict.update(outcome)
    verdict['applied'] = new is not None
    if new is not None:
        verdict.update(new_version=new['version'], events=len(new['events']))
    return verdict


def referenced(state):
    """Document addresses the ledger depends on."""
    found = set()
    if state.get('inventory_document'):
        found.add(state['inventory_document'])
    for topic in state.get('topics', {}).values():
        found.update(x['document'] for x in topic.get('sources', []) if isinstance(x, dict) and x.get('document'))
        if topic.get('held_article_sha'):
            found.add(topic['held_article_sha'])
    found.update(x['article_sha'] for x in state.get('submissions', {}).values())
    found.update(x['report_sha'] for x in state.get('qa', {}).values())
    found.update(state.get('reviews', {}).values())
    found.update(x['document'] for x in state.get('receipts', {}).values() if x.get('document'))
    return sorted(found)


def _exists(store, sha):
    try:
        store.get_document(sha)
        return True
    except Exception:
        return False


def _raw(store):
    if hasattr(store, 'raw'):
        return store.raw()
    return initial(), None


def sync(local, remote, apply=False):
    """Bring a session ledger up to the live one before more session work (the reverse of `promote`).

    Only possible while the session ledger holds nothing the live one lacks; the result is an exact copy, so the next
    promotion is a plain fast-forward again. Referenced documents are fetched first.
    """
    mine, _ = _raw(local)
    theirs, _ = _raw(remote)
    verdict = plan(mine, theirs)
    verdict.update(mode='sync', applied=False)
    if verdict['status'] != 'FAST_FORWARD' or not apply:
        return verdict
    fetched = 0
    for sha in referenced(migrate(copy.deepcopy(theirs))):
        if not _exists(local, sha):
            local.put_document(remote.get_document(sha))
            fetched += 1
    new = local.adopt(lambda raw: migrate(copy.deepcopy(theirs)) if plan(raw, theirs)['status'] == 'FAST_FORWARD' else None)
    verdict.update(applied=new is not None, documents_fetched=fetched)
    return verdict
