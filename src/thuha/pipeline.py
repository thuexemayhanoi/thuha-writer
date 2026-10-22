"""Source-inspired English queue orchestration, with existing ThuHa safety gates.

Adapted from the *workflow pattern* in thuexemayhanoi/wp-aiwriter.
This module neither generates AI prose nor bypasses the guarded publisher.
"""
import time
from datetime import datetime, timezone
from .coordinator import timestamp
from .publisher import release_guard


def brief(state, limit=10):
    """Read-only, compact handoff to an actual ChatGPT/Claude writer session."""
    if not isinstance(limit, int) or not 1 <= limit <= 50:
        raise ValueError('Brief limit must be between 1 and 50')
    claimed = {lease.get('topic_id') for lease in state.get('leases', {}).values()}
    records = []
    for topic_id, topic in sorted(state.get('topics', {}).items()):
        if topic.get('status') != 'PLANNED' or topic_id in claimed:
            continue
        records.append({
            'topic_id': topic_id, 'title': topic.get('proposed_title'),
            'primary_keyword': topic.get('primary_keyword'),
            'search_intent': topic.get('search_intent'),
            'category_id': topic.get('category_id'),
            'category_path': topic.get('category_path'),
            'proposed_url': topic.get('proposed_url'),
            'sources': topic.get('sources', []),
        })
        if len(records) == limit:
            break
    return {
        'mode': 'read-only-writer-brief', 'wordpress_writes': 0,
        'ai_runtime': 'Requires an active authorized external ChatGPT/Claude session',
        'topics': records,
        'next': 'Claim with a unique session/fence; research and submit original English JSON via existing CLI',
    }


def remaining_budget(state, release, day=None):
    """Bound any queue drain by immutable intents, daily cap and unknown outcomes."""
    day = day or datetime.now(timezone.utc).date().isoformat()
    intents = state.get('intents', {})
    pending = [key for key, val in intents.items() if val.get('phase') != 'VERIFIED']
    cap = release['pilot_max_posts'] if release.get('stage', 'pilot') == 'pilot' else release['approved_capacity']
    daily = sum(v.get('reserved_at', '')[:10] == day for v in intents.values())
    return {
        'remaining': max(0, min(cap - len(intents), release['maximum_daily_posts'] - daily)),
        'unresolved_intents': pending, 'intents': len(intents),
        'daily_intents': daily, 'day_utc': day,
    }


def drain(publisher, sleep=time.sleep):
    """Serialize all currently eligible QA-ready items *within approved release limits*.

    Production access is closed by default. The original protected publish()
    rechecks live inventory, QA, review, branch/security controls and creates
    exactly one durable intent before each WordPress POST.
    """
    release = publisher.release_loader()
    release_guard(release, publisher.store)
    state = publisher.store.read()
    window = remaining_budget(state, release)
    if window['unresolved_intents']:
        raise ValueError('Unresolved publication intent: reconcile before draining the queue')
    candidates = sorted(k for k, v in state.get('topics', {}).items() if v.get('status') == 'READY')
    receipts = []
    for topic_id in candidates[:window['remaining']]:
        release = publisher.release_loader()
        release_guard(release, publisher.store)
        latest = publisher.store.read()
        budget = remaining_budget(latest, release)
        if budget['unresolved_intents']:
            raise ValueError('Publication intent changed: reconcile first')
        if budget['remaining'] == 0:
            break
        if latest['topics'].get(topic_id, {}).get('status') != 'READY':
            continue
        interval = release['minimum_post_interval_seconds']
        last = max((v.get('reserved_epoch', 0) for v in latest.get('intents', {}).values()), default=0)
        delay = max(0, interval - (timestamp() - last))
        if delay > 300:
            raise ValueError('Unsafe publication interval; operator review needed')
        if delay:
            sleep(delay)
        receipt = publisher.publish(topic_id)
        receipts.append({'topic_id': topic_id, 'receipt': receipt})
    return {
        'mode': 'guarded-drain', 'attempted_and_readback_verified': len(receipts),
        'receipts': receipts, 'remaining_ready_not_attempted': max(0, len(candidates) - len(receipts)),
        'notice': 'No new AI text generated; verified WordPress receipts only; limits from approved release',
    }
