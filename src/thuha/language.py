"""Language registry for the two native readerships: URL space, locale and text screens.

English stays at the site root; Vietnamese lives under /vi/. The screens here are
deterministic technical checks (diacritics and function words). They catch an
untranslated, mixed or wrong-language draft; they do not judge prose quality and
never replace the independent native-language review.
"""
import re
import unicodedata
from urllib.parse import urlsplit
from .common import SITE, ROOT, fold, load

LANGUAGES = ('vi', 'en')  # priority order: Vietnamese first
SPEC = {
    'en': {'locale': 'en-US', 'html_lang': 'en', 'url_prefix': '', 'category_prefix': '', 'topic_prefix': 'TH-EN-', 'label': 'English'},
    'vi': {'locale': 'vi', 'html_lang': 'vi', 'url_prefix': 'vi/', 'category_prefix': 'vi/chuyen-muc/', 'topic_prefix': 'TH-VI-', 'label': 'Tiếng Việt'},
}
SLUG = re.compile(r'[a-z0-9]+(?:-[a-z0-9]+)*')
TOPIC_ID = re.compile(r'TH-(VI|EN)-([0-9]{4})')
LEGACY_TOPIC_ID = re.compile(r'TH-[0-9]{6}')  # schema-4 English-only IDs already in remote state


def check(lang):
    if lang not in SPEC:
        raise ValueError('Unknown language: ' + repr(lang))
    return lang


def locale(lang):
    return SPEC[check(lang)]['locale']


def targets(project=None):
    goal = (project or load(ROOT / 'config/project.json'))['goal']['targets']
    if set(goal) != set(LANGUAGES) or any(not isinstance(v, int) or v < 1 for v in goal.values()):
        raise ValueError('Per-language targets must be positive integers for vi and en')
    return dict(goal)


def topic_language(topic_id):
    match = TOPIC_ID.fullmatch(topic_id or '')
    if match:
        return match.group(1).lower()
    if LEGACY_TOPIC_ID.fullmatch(topic_id or ''):
        return 'en'
    raise ValueError('Invalid topic ID')


def slugify(text):
    """ASCII URL slug; Vietnamese diacritics and đ are folded."""
    return '-'.join(re.findall(r'[a-z0-9]+', fold(text).lower()))


def post_url(lang, slug):
    if not SLUG.fullmatch(slug):
        raise ValueError('Slug must be lowercase ASCII words joined by hyphens')
    return SITE + '/' + SPEC[check(lang)]['url_prefix'] + slug + '/'


def split_url(url):
    """(language, slug) for a canonical article URL on this site."""
    p = urlsplit(url)
    if p.scheme != 'https' or p.netloc != urlsplit(SITE).netloc or p.query or p.fragment:
        raise ValueError('Not a canonical article URL on the production site')
    parts = [x for x in p.path.split('/') if x]
    lang = 'vi' if parts[:1] == ['vi'] else 'en'
    if lang == 'vi':
        parts = parts[1:]
    if len(parts) != 1 or not SLUG.fullmatch(parts[0]) or not p.path.endswith('/'):
        raise ValueError('Article URLs are one clean slug segment with a trailing slash')
    return lang, parts[0]


def url_language(url):
    """Language namespace of any same-site URL; non-site URLs have none."""
    p = urlsplit(url)
    if p.netloc != urlsplit(SITE).netloc:
        return None
    return 'vi' if p.path == '/vi' or p.path.startswith('/vi/') else 'en'


# --- text screens -----------------------------------------------------------

def _vietnamese_letters():
    letters = set('đ')
    for base in 'aăâeêioôơuưy':
        letters.add(base)
        for mark in (0x300, 0x301, 0x309, 0x303, 0x323):
            letters.add(unicodedata.normalize('NFC', base + chr(mark)))
    return {c for c in letters if c not in 'aeiouy'}


VI_ALL = _vietnamese_letters()
VI_ALL |= {c.upper() for c in VI_ALL}
# Letters shared with French/Spanish/Portuguese: absent from this set so a cafe or
# resume in English text is not mistaken for Vietnamese.
SHARED = set('àáâãèéêìíòóôõùúý') | set('ÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚÝ')
VI_SPECIFIC = VI_ALL - SHARED
VI_FUNCTION = {'và', 'của', 'là', 'có', 'không', 'được', 'cho', 'những', 'một', 'các', 'trong', 'với', 'này',
               'khi', 'để', 'đã', 'sẽ', 'nên', 'hoặc', 'nếu', 'bạn', 'cần', 'rất', 'thì', 'mà', 'nhưng'}
EN_FUNCTION = {'the', 'and', 'of', 'to', 'is', 'for', 'with', 'that', 'this', 'are', 'you', 'your', 'from',
               'not', 'on', 'at', 'by', 'be', 'or', 'it', 'as', 'can', 'will', 'before', 'after'}


def profile(text):
    tokens = re.findall(r'[^\W\d_]+', unicodedata.normalize('NFC', str(text)))
    n = len(tokens)
    lower = [t.lower() for t in tokens]
    return {
        'tokens': n,
        'vi_ratio': (sum(any(c in VI_ALL for c in t) for t in lower) / n) if n else 0.0,
        'vi_function_hits': sum(t in VI_FUNCTION for t in lower),
        'en_function_ratio': (sum(t in EN_FUNCTION for t in lower) / n) if n else 0.0,
    }


def screen(lang, text, short=False):
    """Hard-fail reasons when text does not read as `lang`; empty list = plausible.

    Short fields (titles, meta, alt text, keywords) are judged more leniently:
    a Vietnamese title can have few diacritics and an English title can carry a
    Vietnamese dish or place name. Long text must clearly be one language.
    """
    check(lang)
    p = profile(text)
    n = p['tokens']
    if n == 0:
        return ['EMPTY_TEXT']
    errors = []
    if lang == 'vi':
        if short:
            if n >= 4 and p['vi_ratio'] < 0.15:
                errors.append('NOT_VIETNAMESE_TEXT')
            if p['en_function_ratio'] > 0.2:
                errors.append('ENGLISH_MIXED_INTO_VIETNAMESE')
        else:
            if p['vi_ratio'] < 0.35:
                errors.append('NOT_VIETNAMESE_TEXT')
            if p['en_function_ratio'] > 0.04:
                errors.append('ENGLISH_MIXED_INTO_VIETNAMESE')
        return errors
    if short:
        if p['vi_function_hits'] >= 1 or (n >= 5 and p['vi_ratio'] > 0.5):
            errors.append('VIETNAMESE_MIXED_INTO_ENGLISH')
    elif p['vi_ratio'] > 0.12 or p['vi_function_hits'] >= 3:
        errors.append('VIETNAMESE_MIXED_INTO_ENGLISH')
    return errors


def html_lang_matches(lang, value):
    return str(value or '').lower().replace('_', '-').split('-')[0] == SPEC[check(lang)]['html_lang']
