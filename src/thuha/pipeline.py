"""Source-inspired queue orchestration with the existing ThuHa safety gates, Vietnamese first.

Adapted from the *workflow pattern* in thuexemayhanoi/wp-aiwriter.
This module neither generates AI prose nor bypasses the guarded publisher.
"""
import re
import time
from datetime import datetime, timezone
from .coordinator import timestamp, claim_order
from .http import NetworkError
from .language import LANGUAGES
from .publisher import PublishBlocked, release_guard, open_alerts, quota_unresolved
from .quota import LanguageComplete, CLOSED_PHASES
from .store import event


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
    pending = quota_unresolved(state)
    cap = release['pilot_max_posts'] if release.get('stage', 'pilot') == 'pilot' else release['approved_capacity']
    daily = sum(v.get('reserved_at', '')[:10] == day for v in intents.values())
    return {
        'remaining': max(0, min(cap - len(intents), release['maximum_daily_posts'] - daily)),
        'unresolved_intents': pending, 'intents': len(intents),
        'daily_intents': daily, 'day_utc': day,
        'languages_enabled': list(release.get('languages_enabled', [])),
    }


# These can fail only because the inventory has not caught up with a post published a moment ago.
INVENTORY_SENSITIVE = ('INTERNAL_LINK_NOT_LIVE_VERIFIED', 'INSUFFICIENT_REAL_INTERNAL_LINKS')


def demotable(hard_fails):
    """Only failures that belong to the article against the live site send it back to repair.

    A non-code failure (stale inventory, ...) or one that a fresh audit can clear is reported and retried instead.
    """
    codes = [h for h in hard_fails if re.fullmatch(r'[A-Z][A-Z0-9_]+', h)]
    return bool(hard_fails) and len(codes) == len(hard_fails) and any(h not in INVENTORY_SENSITIVE for h in codes)


def demote(publisher, topic_id, reason, hard_fails):
    """A READY topic that cannot publish any more (live duplicate, QA no longer passes) goes back to repair.

    Leaving it READY would put it at the head of every drain forever and show it as "QA pass" on the dashboard.
    """
    def transaction(state):
        topic = state['topics'][topic_id]
        if topic['status'] != 'READY' or topic_id in state['intents'] and state['intents'][topic_id]['phase'] not in CLOSED_PHASES:
            return False
        topic['status'] = 'NEEDS_REPAIR'
        topic['repair_notes'] = {'at': time_label(), 'reason': reason[:300], 'hard_fails': list(hard_fails)}
        event(state, 'PUBLISH_BLOCKED', topic_id=topic_id, hard_fails=list(hard_fails))
        return True
    return publisher.store.mutate(transaction)


def time_label():
    return datetime.now(timezone.utc).isoformat()


def drain(publisher, sleep=time.sleep):
    """Serialize the QA-ready queue *within approved release limits*, Vietnamese first. Safe to run again and again.

    Order of work, every run:
      1. read-only reconciliation of every unresolved intent (a lost POST response becomes a post, a closed intent
         or, while still unknown, a stop: the POST is never repeated);
      2. publish READY topics one at a time. A topic that cannot publish now (QA, duplicate, payload) is sent back to
         repair and the queue moves on; a language at its ceiling is skipped; anything touching WordPress that is not
         clean stops the run;
      3. public-page checks that are due. Their failures are warnings: they never stop publication.
    """
    release = publisher.release_loader()
    release_guard(release, publisher.store)
    summary = {'mode': 'guarded-drain', 'published': [], 'skipped': {}, 'sent_back_to_repair': {}, 'languages_at_ceiling': [],
               'reconciled': {}, 'halted': None, 'post_checks': {}}

    def halt(reason):
        summary['halted'] = reason
        return finish()

    def finish():
        summary['post_checks'] = publisher.run_post_checks()
        summary['attempted_and_published'] = len(summary['published'])
        summary['notice'] = 'No new AI text generated; WordPress-confirmed posts only; limits from the approved release'
        return summary

    state = publisher.store.read()
    if open_alerts(state):
        return halt('Unacknowledged integrity alert: ' + ', '.join(sorted({a['topic_id'] for a in open_alerts(state)})))
    if quota_unresolved(state):
        summary['reconciled'] = publisher.reconcile_all()
        state = publisher.store.read()
        if quota_unresolved(state):
            return halt('Unresolved publication outcome(s): ' + ', '.join(quota_unresolved(state)) + '. Reconcile; the POST is never repeated')
    enabled = set(release.get('languages_enabled', []))
    window = remaining_budget(state, release)
    candidates = sorted((k for k, v in state.get('topics', {}).items()
                         if v.get('status') == 'READY' and v.get('language') in enabled),
                        key=lambda k: claim_order({**state['topics'][k], 'topic_id': k}))
    full = set()
    for topic_id in candidates:
        if len(summary['published']) >= window['remaining']:
            break
        release = publisher.release_loader()
        release_guard(release, publisher.store)
        latest = publisher.store.read()
        lang = latest['topics'].get(topic_id, {}).get('language')
        if lang in full:
            continue
        budget = remaining_budget(latest, release)
        if budget['unresolved_intents']:
            return halt('Publication intent changed: reconcile first')
        if budget['remaining'] == 0:
            break
        if latest['topics'].get(topic_id, {}).get('status') != 'READY':
            continue
        interval = release['minimum_post_interval_seconds']
        last = max((v.get('reserved_epoch', 0) for v in latest.get('intents', {}).values()), default=0)
        delay = max(0, interval - (timestamp() - last))
        if delay > 300:
            return halt('Unsafe publication interval; operator review needed')
        if delay:
            sleep(delay)
        try:
            receipt = publisher.publish(topic_id)
        except LanguageComplete:
            full.add(lang)
            continue
        except PublishBlocked as exc:
            if demotable(exc.hard_fails):
                demote(publisher, topic_id, str(exc), exc.hard_fails)
                summary['sent_back_to_repair'][topic_id] = str(exc)[:300]
            else:
                summary['skipped'][topic_id] = str(exc)[:300]
            continue
        except (NetworkError, ValueError, OSError) as exc:
            summary['skipped'][topic_id] = str(exc)[:300]
            return halt('Publishing stopped at ' + topic_id + ': ' + str(exc)[:200])
        summary['published'].append({'topic_id': topic_id, 'language': lang, 'receipt': receipt})
    summary['languages_at_ceiling'] = sorted(full)
    summary['remaining_ready_not_attempted'] = len([k for k in candidates if k not in {r['topic_id'] for r in summary['published']}
                                                    and k not in summary['skipped'] and k not in summary['sent_back_to_repair']
                                                    and state['topics'][k]['language'] not in full])
    return finish()
