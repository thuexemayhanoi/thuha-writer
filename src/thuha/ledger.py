"""Controlled hand-over of a session ledger into the shared ledger that GitHub Actions read.

A writer session that can push only to its own branch keeps its ledger (`data/state/factory.json`) and immutable
documents (`data/documents/`) in that branch (`GitBranchStore`). Nothing reads that copy: the publisher and the
maintenance workflows read `factory-state`. `promote` moves the session ledger into `factory-state` under three rules:

* append-only: the live ledger's history must be the first part of the session ledger's history (a fast-forward).
  Anything else (the live ledger moved on, or the two never shared a history) is refused and nothing is written;
* no overwrite and no duplicate: documents are content-addressed and immutable, existing ones are compared and kept,
  every topic, submission, review, QA report and event of the live ledger survives byte for byte;
* idempotent: promoting a ledger that the live one already contains writes nothing.

The session ledger may still be schema 4. A session ledger never publishes: its intents and receipts must equal the live
ones. Work done on a stale copy of the live ledger cannot be merged automatically; `sync` first, then work.
"""
import copy
import re
import time
from pathlib import Path
from .common import canonical_json, digest, load, now
from .store import SCHEMA, event, initial, migrate, validate

DOCUMENT = re.compile(r'[a-f0-9]{64}\.json')
# Fields of a topic that never change after admission; a session ledger may not alter them.
TOPIC_FIXED = ('language', 'proposed_url', 'proposed_title', 'category_id', 'category_path', 'primary_keyword',
               'search_intent', 'sources', 'intent_review', 'admitted_at', 'cluster')


def logical(events):
    """What each event says, in order, ignoring the hash chain and schema-migration markers.

    The chain differs between two copies of the same history that were migrated at different points; what the events
    say does not.
    """
    return [digest({k: v for k, v in e.items() if k not in ('previous', 'sha256')}) for e in events if e.get('action') != 'SCHEMA_MIGRATION']


def _prefix(short, long):
    return len(short) <= len(long) and long[:len(short)] == short


def plan(live, handoff, promote=True):
    """Decide what bringing `handoff` into `live` would do. Pure; raw (possibly schema 4) ledgers in, no writes.

    `promote` is the session-to-shared direction, where the session ledger may add topics, drafts, reviews and events but
    never intents or receipts (only the publisher writes those). `sync` uses the other direction.
    """
    result = {'status': None, 'reasons': [], 'live_version': live.get('version'), 'handoff_version': handoff.get('version')}
    try:
        live_m, handoff_m = migrate(copy.deepcopy(live)), migrate(copy.deepcopy(handoff))
        validate(live_m)
        validate(handoff_m)
    except ValueError as exc:
        result.update(status='INVALID_LEDGER', reasons=[str(exc)])
        return result
    mine, theirs = logical(live_m['events']), logical(handoff_m['events'])
    result.update(live_events=len(mine), handoff_events=len(theirs))
    if _prefix(theirs, mine):
        missing = covered(live_m, handoff_m)
        if missing:
            result.update(status='INCONSISTENT', reasons=['The session ledger holds state that no event explains and the shared ledger lacks: '
                                                          + '; '.join(missing[:5]) + '. Nothing was written.'])
            return result
        result['status'] = 'ALREADY_INCLUDED'
        return result
    if not _prefix(mine, theirs):
        common = len(os_common(mine, theirs))
        actions = [e['action'] for e in live_m['events'] if e.get('action') != 'SCHEMA_MIGRATION'][common:]
        result.update(status='DIVERGED', reasons=['The two ledgers have different histories: the shared ledger holds ' + str(len(actions)) +
                                                  ' event(s) the other lacks (' + ', '.join(sorted(set(actions))) + '). Work done on a stale copy '
                                                  'cannot be merged automatically; nothing was written. Sync a session ledger from the shared '
                                                  'one BEFORE working.'])
        return result
    lease = live.get('publisher_lease')
    if lease and lease.get('expires_at', 0) > time.time():
        result.update(status='BLOCKED', reasons=['A publisher currently holds the live ledger; promote when it has finished.'])
        return result
    problems = continuity(live_m, handoff_m, promote)
    if problems:
        result.update(status='INCONSISTENT', reasons=problems)
        return result
    result['status'] = 'FAST_FORWARD'
    return result


def os_common(a, b):
    """The common leading part of two event lists."""
    out = []
    for x, y in zip(a, b):
        if x != y:
            break
        out.append(x)
    return out


def covered(live, handoff):
    """For a ledger the shared one already contains: is every topic, draft and review of it really there?"""
    gaps = []
    for key in handoff['topics']:
        if key not in live['topics']:
            gaps.append('topic ' + key)
    for key, sub in handoff['submissions'].items():
        have = live['submissions'].get(key)
        if not have or (have['article_sha'] != sub['article_sha'] and have.get('repair_count', 0) <= sub.get('repair_count', 0)):
            gaps.append('draft ' + key)
    for key, sha in handoff.get('reviews', {}).items():
        if live.get('reviews', {}).get(key) != sha and live['submissions'].get(key, {}).get('article_sha') == handoff['submissions'].get(key, {}).get('article_sha'):
            gaps.append('review ' + key)
    for key in handoff['research_requests']:
        if key not in live['research_requests']:
            gaps.append('research request ' + key)
    return gaps


def continuity(live, handoff, promote=True):
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
        elif promote and new != value:
            problems.append('Publication intent changed in the session ledger: ' + key)
    if promote:
        for key in set(handoff['receipts']) - set(live['receipts']):
            problems.append('The session ledger carries a receipt the publisher never wrote: ' + key)
        for key in set(handoff['intents']) - set(live['intents']):
            problems.append('The session ledger carries a publication intent the publisher never wrote: ' + key)
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
    new['alerts'] = copy.deepcopy(live.get('alerts', []))
    new['intents'], new['receipts'] = copy.deepcopy(live['intents']), copy.deepcopy(live['receipts'])  # only the publisher writes these
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
    def have(sha):
        return documents[sha] if sha in documents else store.get_document(sha)
    missing = [x for x in referenced(handoff, have) if x not in documents and not _exists(store, x)]
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


def referenced(state, getter=None):
    """Document addresses the ledger depends on, including the source snapshots that article documents point to.

    `getter(sha)` returns a document or raises; without it only the references held in the ledger itself are listed.
    """
    found = set()
    if state.get('inventory_document'):
        found.add(state['inventory_document'])
    articles = set()
    for topic in state.get('topics', {}).values():
        found.update(x['document'] for x in topic.get('sources', []) if isinstance(x, dict) and x.get('document'))
        if topic.get('held_article_sha'):
            articles.add(topic['held_article_sha'])
    articles.update(x['article_sha'] for x in state.get('submissions', {}).values())
    found.update(articles)
    found.update(x['report_sha'] for x in state.get('qa', {}).values())
    found.update(state.get('reviews', {}).values())
    found.update(x['document'] for x in state.get('receipts', {}).values() if x.get('document'))
    if getter:
        for sha in articles:
            try:
                article = getter(sha)
            except Exception:
                continue  # a missing article is reported by the caller as a missing document
            found.update(x['document'] for x in article.get('sources', []) if isinstance(x, dict) and x.get('document'))
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
    verdict = plan(mine, theirs, promote=False)
    verdict.update(mode='sync', applied=False)
    if verdict['status'] != 'FAST_FORWARD' or not apply:
        return verdict
    fetched = 0
    for sha in referenced(migrate(copy.deepcopy(theirs)), remote.get_document):
        if not _exists(local, sha):
            local.put_document(remote.get_document(sha))
            fetched += 1
    new = local.adopt(lambda raw: migrate(copy.deepcopy(theirs)) if plan(raw, theirs, promote=False)['status'] == 'FAST_FORWARD' else None)
    verdict.update(applied=new is not None, documents_fetched=fetched)
    return verdict
