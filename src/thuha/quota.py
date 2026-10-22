"""Per-language publication quota: 500 distinct published posts per language, site-wide.

Existing posts count. Pages, drafts and trash never do. An intent whose outcome is
unknown is counted as if it had published, so an uncertain POST can neither push a
language past its ceiling nor be forgotten.
"""
from .language import LANGUAGES

OPEN_TOPIC_STATES = ('PLANNED', 'CLAIMED', 'DRAFT_READY', 'READY', 'NEEDS_REPAIR',
                     'NEEDS_REVIEW', 'BLOCKED', 'PUBLISHING')


SOURCES = ('adapter', 'authenticated-snapshot')


def published(inv):
    """Published-post counts by language from a language-aware inventory.

    The public REST collection can hide native Vietnamese posts, so a count taken
    from it would under-report and let a language overshoot its ceiling.
    """
    if inv.get('language_source') not in SOURCES:
        raise ValueError('Inventory language source is not authoritative; use the adapter or the authenticated snapshot')
    counts = inv.get('counts', {}).get('posts_by_language')
    if not isinstance(counts, dict) or set(counts) != set(LANGUAGES) or any(
            not isinstance(v, int) or v < 0 for v in counts.values()):
        raise ValueError('Language-aware live inventory required: per-language published counts are missing')
    return counts


# Intent phases in which no post and no draft can exist (the POST was never sent, or the plugin refused it before
# creating anything and a read-back by key confirmed it). They free their publication slot; every other phase
# except VERIFIED stays unresolved and keeps counting.
CLOSED_PHASES = ('NOT_SENT', 'REJECTED')


class LanguageComplete(ValueError):
    """The language already holds its ceiling of posts (live plus unresolved intents)."""


def unresolved(state, lang, ignore=None):
    return [k for k, v in state['intents'].items()
            if v['language'] == lang and v.get('phase') not in ('VERIFIED',) + CLOSED_PHASES and k != ignore]


def active_intents(state):
    """Intents that still occupy publication budget (closed ones never reached WordPress)."""
    return {k: v for k, v in state['intents'].items() if v.get('phase') not in CLOSED_PHASES}


def verified_outside_inventory(state, lang, live_ids):
    """Verified factory posts a possibly older inventory read does not yet contain."""
    return [k for k, v in state['intents'].items()
            if v['language'] == lang and v.get('phase') == 'VERIFIED' and v.get('wp_id') not in live_ids]


def status(state, counts, targets):
    out = {}
    for lang in LANGUAGES:
        pending = len(unresolved(state, lang))
        used = counts[lang] + pending
        out[lang] = {
            'target': targets[lang], 'published_live': counts[lang], 'unresolved_intents': pending,
            'remaining': max(0, targets[lang] - used), 'complete': used >= targets[lang],
            'over_target': counts[lang] > targets[lang],
            'open_topics': sum(1 for t in state['topics'].values()
                               if t['language'] == lang and t['status'] in OPEN_TOPIC_STATES),
        }
    return out


def reserve(state, counts, targets, lang, topic_id, live_ids=None):
    """Raise unless exactly one more `lang` post fits under its ceiling.

    `live_ids` (WordPress IDs in the inventory the counts came from) closes the window where another factory
    publisher finished and verified a post after that inventory was read.
    """
    late = len(verified_outside_inventory(state, lang, live_ids)) if live_ids is not None else 0
    if counts[lang] + late + len(unresolved(state, lang, ignore=topic_id)) + 1 > targets[lang]:
        raise LanguageComplete('Language target reached: ' + lang + ' has no remaining publication slot')


def topics_needed(state, counts, targets, lang):
    """New topics worth admitting: ceiling minus live posts minus every open topic."""
    open_topics = sum(1 for t in state['topics'].values()
                      if t['language'] == lang and t['status'] != 'VERIFIED')
    return max(0, targets[lang] - counts[lang] - open_topics)


def complete_languages(state, counts, targets):
    return {lang for lang, v in status(state, counts, targets).items() if v['complete']}
