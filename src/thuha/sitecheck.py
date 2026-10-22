"""Archive, pagination, sitemap, robots and language-isolation checks for the VI/EN site.

Every function here is pure: it judges HTML/XML/text the caller already fetched. Offline tests feed it
fixtures; the credentialed publisher feeds it live pages after the first post of a category exists
(`plan_after_publication`). Passing the fixtures says the CHECKS work, not that the website passes.
"""
import re
import xml.etree.ElementTree as ET
from urllib.parse import urljoin
from .audit import parse
from .common import SITE, urlkey
from .language import LANGUAGES, html_lang_matches, url_language

MAX_XML = 5_000_000


def _noindex(page, headers):
    header = (headers or {}).get('X-Robots-Tag', (headers or {}).get('x-robots-tag'))
    return 'noindex' in str(page.robots).lower() or 'noindex' in str(header).lower()


def check_archive(url, html, status, headers, lang, expect_urls=(), foreign_urls=()):
    """A category archive (page 1 or N): reachable, indexable, self-canonical, in language, lists the posts it must."""
    page = parse(html)
    problems = []
    if status != 200:
        problems.append('ARCHIVE_HTTP_' + str(status))
    if page.canonicals != [url]:
        problems.append('ARCHIVE_CANONICAL_NOT_SELF')
    if _noindex(page, headers):
        # A noindex used while the archive was empty must be lifted once it holds posts.
        problems.append('ARCHIVE_NOINDEX')
    if not html_lang_matches(lang, page.html_lang):
        problems.append('ARCHIVE_HTML_LANG')
    linked = {urlkey(urljoin(url, x)) for x in page.links if urljoin(url, x).startswith(SITE)}
    for expected in expect_urls:
        if urlkey(expected) not in linked:
            problems.append('ARCHIVE_MISSING_POST ' + expected)
    for foreign in foreign_urls:
        if urlkey(foreign) in linked:
            problems.append('ARCHIVE_LISTS_OTHER_LANGUAGE_POST ' + foreign)
    return problems


def check_pagination(first_url, first_html, second_url, second_html, second_status, headers2, lang):
    """Page 1 points to page 2 and back; page 2 is indexable and self-canonical (no canonical to page 1)."""
    one, two = parse(first_html), parse(second_html)
    problems = []
    if [urlkey(urljoin(first_url, x)) for x in one.rels.get('next', [])] != [urlkey(second_url)]:
        problems.append('PAGINATION_NEXT_MISSING')
    if second_status != 200:
        problems.append('PAGINATION_PAGE2_HTTP_' + str(second_status))
    if two.canonicals != [second_url]:
        problems.append('PAGINATION_PAGE2_CANONICAL')
    if [urlkey(urljoin(second_url, x)) for x in two.rels.get('prev', [])] != [urlkey(first_url)]:
        problems.append('PAGINATION_PREV_MISSING')
    if _noindex(two, headers2):
        problems.append('PAGINATION_PAGE2_NOINDEX')
    if not html_lang_matches(lang, two.html_lang):
        problems.append('PAGINATION_HTML_LANG')
    return problems


def locs(xml_text):
    if len(xml_text) > MAX_XML:
        raise ValueError('Sitemap too large to inspect')
    root = ET.fromstring(xml_text)
    return [e.text.strip() for e in root.iter() if e.tag.endswith('}loc') or e.tag == 'loc']


def check_sitemap(index_xml, fetch, include=(), exclude=()):
    """Every `include` URL appears somewhere under the sitemap index; no `exclude` URL does.

    `fetch(url)` returns a child sitemap's XML. Independent Vietnamese posts must be listed even with no
    English pair (`sitemap_pairs_only=false`)."""
    found = set()
    for entry in locs(index_xml):
        if entry.endswith('.xml'):
            found.update(urlkey(x) for x in locs(fetch(entry)))
        else:
            found.add(urlkey(entry))
    problems = ['SITEMAP_MISSING ' + u for u in include if urlkey(u) not in found]
    problems += ['SITEMAP_SHOULD_NOT_LIST ' + u for u in exclude if urlkey(u) in found]
    return problems


def check_robots(text):
    """robots.txt must not block the Vietnamese namespace and should announce a sitemap."""
    problems, agent_all = [], False
    for raw in text.splitlines():
        line = raw.split('#')[0].strip()
        if line.lower().startswith('user-agent:'):
            agent_all = line.split(':', 1)[1].strip() == '*'
        elif agent_all and line.lower().startswith('disallow:'):
            path = line.split(':', 1)[1].strip()
            if path and ('/vi/'.startswith(path) or path.startswith('/vi/')):
                problems.append('ROBOTS_BLOCKS_VIETNAMESE ' + path)
    if not re.search(r'(?im)^\s*sitemap:\s*https://', text):
        problems.append('ROBOTS_NO_SITEMAP')
    return problems


def check_language_isolation(inv):
    """Inventory-level isolation: URL namespace, category language and slug uniqueness agree per item."""
    by_cat = {c['id']: c for c in inv['categories']}
    problems, slugs = [], {}
    for item in inv['items']:
        if item['type'] != 'posts':
            continue
        lang = item['language']
        if lang not in LANGUAGES:
            problems.append('LANGUAGE_UNVERIFIED ' + str(item['id']))
            continue
        if url_language(item['url']) != lang:
            problems.append('URL_NAMESPACE_MISMATCH ' + str(item['id']))
        for cid in item.get('categories', []):
            if by_cat.get(cid, {}).get('language') != lang:
                problems.append('CATEGORY_LANGUAGE_MISMATCH %s category %s' % (item['id'], cid))
        if slugs.setdefault(item['slug'], item['id']) != item['id']:
            problems.append('SLUG_SHARED ' + item['slug'])
    for cat in inv['categories']:
        parent = by_cat.get(cat.get('parent'))
        if parent and parent['language'] != cat['language']:
            problems.append('CATEGORY_PARENT_OTHER_LANGUAGE %s' % cat['id'])
    return problems


def plan_after_publication(post_url, lang, category_path, inv):
    """What to fetch after the first post of a category: the leaf and every ancestor archive, the sitemap, robots."""
    by_cat = {c['id']: c for c in inv['categories']}
    return {'post_url': post_url, 'language': lang,
            'archives': [by_cat[i]['link'] for i in reversed(category_path)],
            'sitemap_index': SITE + '/sitemap_index.xml', 'robots': SITE + '/robots.txt',
            'status': 'PENDING_LIVE: run by the credentialed publisher once a post exists'}
