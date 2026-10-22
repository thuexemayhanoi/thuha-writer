"""Source-inspired queue orchestration with the existing ThuHa safety gates, Vietnamese first.

Adapted from the *workflow pattern* in thuexemayhanoi/wp-aiwriter.
This module neither generates AI prose nor bypasses the guarded publisher.
"""
import time
from datetime import datetime, timezone
from .coordinator import timestamp, claim_order
from .language import LANGUAGES
from .publisher import release_guard
from .quota import LanguageComplete, CLOSED_PHASES


def brief(state, limit=10, language=None):
    """Read-only, compact handoff to an actual ChatGPT/Claude writer session."""
    if not isinstance(limit, int) or not 1 <= limit <= 50:
        raise ValueError('Brief limit must be between 1 and 50')
    if language is not None and language not in LANGUAGES:
        raise ValueError('Unknown language')
    claimed = {lease.get('topic_id') for lease in state.get('leases', {}).values()}
    records = []
    topics = state.get('topics', {})
    for topic_id, topic in sorted(topics.items(), key=lambda kv: claim_order({**kv[1], 'topic_id': kv[0]})):
        if topic.get('status') != 'PLANNED' or topic_id in claimed or (language and topic.get('language') != language):
            continue
        records.append({
            'topic_id': topic_id, 'language': topic.get('language'), 'title': topic.get('proposed_title'),
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
        'order': 'Vietnamese first, then English',
        'topics': records,
        'next': 'Claim with a unique session/fence; research and submit original native-language JSON via existing CLI',
    }


def remaining_budget(state, release, day=None):
    """Bound any queue drain by immutable intents, daily cap and unknown outcomes.

    Per-language ceilings are enforced by the publisher against a fresh adapter
    inventory at reservation; this window only limits how many attempts are made.
    """
    day = day or datetime.now(timezone.utc).date().isoformat()
    intents = {k: v for k, v in state.get('intents', {}).items() if v.get('phase') not in CLOSED_PHASES}
    pending = [key for key, val in intents.items() if val.get('phase') != 'VERIFIED']
    cap = release['pilot_max_posts'] if release.get('stage', 'pilot') == 'pilot' else release['approved_capacity']
    daily = sum(v.get('reserved_at', '')[:10] == day for v in intents.values())
    return {
        'remaining': max(0, min(cap - len(intents), release['maximum_daily_posts'] - daily)),
        'unresolved_intents': pending, 'intents': len(intents),
        'daily_intents': daily, 'day_utc': day,
        'languages_enabled': list(release.get('languages_enabled', [])),
    }


def drain(publisher, sleep=time.sleep):
    """Serialize all currently eligible QA-ready items *within approved release limits*, VI first.

    Production access is closed by default. The original protected publish()
    rechecks live inventory, QA, review, branch/security controls and creates
    exactly one durable intent before each WordPress POST. A language that has
    reached its ceiling is skipped; any other failure stops the drain.
    """
    release = publisher.release_loader()
    release_guard(release, publisher.store)
    state = publisher.store.read()
    window = remaining_budget(state, release)
    if window['unresolved_intents']:
        raise ValueError('Unresolved publication intent: reconcile before draining the queue')
    enabled = set(release.get('languages_enabled', []))
    candidates = sorted((k for k, v in state.get('topics', {}).items()
                         if v.get('status') == 'READY' and v.get('language') in enabled),
                        key=lambda k: claim_order({**state['topics'][k], 'topic_id': k}))
    receipts, full = [], set()
    for topic_id in candidates:
        if len(receipts) >= window['remaining']:
            break
        release = publisher.release_loader()
        release_guard(release, publisher.store)
        latest = publisher.store.read()
        lang = latest['topics'].get(topic_id, {}).get('language')
        if lang in full:
            continue
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
        try:
            receipt = publisher.publish(topic_id)
        except LanguageComplete:
            full.add(lang)
            continue
        receipts.append({'topic_id': topic_id, 'language': lang, 'receipt': receipt})
    return {
        'mode': 'guarded-drain', 'attempted_and_readback_verified': len(receipts),
        'receipts': receipts, 'languages_at_ceiling': sorted(full),
        'remaining_ready_not_attempted': len([k for k in candidates if k not in {r['topic_id'] for r in receipts}
                                              and state['topics'][k]['language'] not in full]),
        'notice': 'No new AI text generated; verified WordPress receipts only; limits from approved release',
    }
