"""Contract and client for the companion plugin `thuha-native-vi-publisher`.

The plugin (wordpress/thuha-native-vi-publisher, packaged under dist/) is the only
write path. It creates a draft that carries the ownership/idempotency marker,
attaches the native Vietnamese marker through RBHVI_Language::set_vi(), writes the
SEO fields and only then publishes, so no post is ever live at an English URL
first. It also returns a read-only inventory of BOTH languages because the public
REST collection can hide Vietnamese posts.

Nothing here has been run against the real website: live deployment is PENDING.
"""
import json
import re
from urllib.parse import urlencode
from .common import SITE
from . import htmlpolicy
from .http import ADAPTER_BASE, NetworkError, WordPress
from .language import LANGUAGES, TOPIC_ID, LEGACY_TOPIC_ID, SLUG as SLUG_RE

CONTRACT = 'thuha-writer/1'
PLUGIN_SLUG = 'thuha-native-vi-publisher'
from .policy import LIMITS, HTML_POLICY, DEFINITIVE_REJECTIONS
KEY = re.compile(r'[a-f0-9]{64}')
MARKER = re.compile(r'<!-- thuha:v5 topic=(TH-(?:VI|EN)-[0-9]{4}|TH-[0-9]{6}) sha256=[a-f0-9]{64} -->')
YOAST_META = ('_yoast_wpseo_title', '_yoast_wpseo_metadesc', '_yoast_wpseo_focuskw')
CREATE_FIELDS = ('contract', 'idempotency_key', 'topic_id', 'language', 'slug', 'title', 'content',
                 'category_id', 'featured_media', 'seo', 'marker')
SEO_FIELDS = ('title', 'description', 'focus_keyword')
ROUTES = {
    'preflight': ('GET', '/preflight'),
    'inventory': ('GET', '/inventory'),
    'categories': ('GET', '/categories'),
    'create': ('POST', '/posts'),
    'reconcile': ('GET', '/posts/by-key/(?P<key>[a-f0-9]{64})'),
}
NOT_DEPLOYED = 'BLOCKED_ADAPTER_NOT_DEPLOYED'


def build_payload(topic, article, key, marker, slug):
    """The exact, closed set of fields the adapter accepts; nothing else is sent."""
    return {
        'contract': CONTRACT, 'idempotency_key': key, 'topic_id': topic['topic_id'],
        'language': topic['language'], 'slug': slug, 'title': article['title'],
        'content': article['body_html'] + '\n' + marker, 'category_id': topic['category_id'],
        'featured_media': article['featured_media'], 'marker': marker,
        'seo': {'title': article['seo_title'], 'description': article['meta_description'],
                'focus_keyword': article['focus_keyword']},
    }


def validate_payload(payload):
    """Client-side mirror of the plugin's schema validation (the plugin enforces it again).

    Run BEFORE the intent is reserved: a payload the plugin would refuse must never cost a publication slot.
    """
    if set(payload) != set(CREATE_FIELDS):
        raise ValueError('Adapter payload fields do not match the contract')
    if payload['contract'] != CONTRACT or not KEY.fullmatch(str(payload['idempotency_key'])):
        raise ValueError('Adapter contract or idempotency key invalid')
    if payload['language'] not in LANGUAGES:
        raise ValueError('Adapter payload language invalid')
    if not (TOPIC_ID.fullmatch(payload['topic_id']) or LEGACY_TOPIC_ID.fullmatch(payload['topic_id'])):
        raise ValueError('Adapter topic ID invalid')
    if set(payload['seo']) != set(SEO_FIELDS):
        raise ValueError('Adapter SEO fields invalid')
    if not isinstance(payload['category_id'], int) or not isinstance(payload['featured_media'], int):
        raise ValueError('Adapter category and media IDs must be integers')
    topic_language = 'en' if LEGACY_TOPIC_ID.fullmatch(payload['topic_id']) else TOPIC_ID.fullmatch(payload['topic_id']).group(1).lower()
    if topic_language != payload['language']:
        raise ValueError('Topic ID language does not match the payload language')
    if not SLUG_RE.fullmatch(payload['slug']) or len(payload['slug'].encode()) > LIMITS['slug_bytes']:
        raise ValueError('Adapter slug invalid')
    marker = payload['marker']
    if not MARKER.fullmatch(marker) or MARKER.fullmatch(marker).group(1) != payload['topic_id']:
        raise ValueError('Adapter ownership marker is malformed or names another topic')
    if not payload['content'].endswith(marker) or payload['content'].count('<!-- thuha:') != 1:
        raise ValueError('Adapter content must end with exactly one ownership marker')
    sizes = (('content', payload['content'], 'content_bytes'), ('title', payload['title'], 'title_bytes'))
    sizes += tuple(('seo ' + k, v, 'seo_bytes') for k, v in payload['seo'].items())
    for name, value, limit in sizes:
        if not isinstance(value, str) or not value or len(value.encode()) > LIMITS[limit]:
            raise ValueError('Adapter ' + name + ' is empty or over the ' + str(LIMITS[limit]) + '-byte limit')
    for name, value in (('title', payload['title']),) + tuple(('seo ' + k, v) for k, v in payload['seo'].items()):
        if '<' in value or '>' in value or value != ' '.join(value.split()):
            raise ValueError('Adapter ' + name + ' must be plain text with single spaces')
    problems = htmlpolicy.violations(payload['content'][:-len(marker)])
    if problems:
        raise ValueError('Adapter content breaks the HTML policy: ' + ', '.join(problems[:3]))
    return payload


class AdapterClient(WordPress):
    """Authenticated reads plus the single create-only POST. Credentials stay in the environment."""

    def adapter_get(self, path, **query):
        url = ADAPTER_BASE + path + ('?' + urlencode(query) if query else '')
        try:
            data, _, _ = self.http.request(url, auth=True)
        except NetworkError as exc:
            if exc.status == 404:
                raise ValueError(NOT_DEPLOYED + ': the adapter route answered HTTP 404. Install and activate '
                                 + PLUGIN_SLUG + ' (see docs/bilingual/ADAPTER.md).') from None
            if exc.status in (401, 403):
                raise ValueError('ADAPTER_AUTH_REJECTED: HTTP ' + str(exc.status) + '. Use an Application Password of a user who '
                                 'may publish posts; cookie sessions and browser origins are refused.') from None
            raise
        return json.loads(data)

    def preflight(self):
        r = self.adapter_get(ROUTES['preflight'][1])
        vi, yoast, user = r.get('native_vi', {}), r.get('yoast', {}), r.get('user', {}).get('can', {})
        problems = []
        if r.get('contract') != CONTRACT:
            problems.append('contract version')
        if not (vi.get('present') and vi.get('set_vi') and vi.get('is_vi') and vi.get('term_is_vi')
                and vi.get('taxonomy') == 'rbhvi_language'):
            problems.append('native VI plugin API (RBHVI_Language::set_vi/is_vi/term_is_vi)')
        if not yoast.get('present'):
            problems.append('Yoast SEO')
        if not (user.get('edit_posts') and user.get('publish_posts')):
            problems.append('publish_posts capability')
        if not r.get('auth', {}).get('application_password'):
            problems.append('Application Password authentication')
        if r.get('settings', {}).get('sitemap_pairs_only') is not False:
            problems.append('sitemap_pairs_only must be false for independent Vietnamese posts')
        if problems:
            raise ValueError('Adapter preflight failed: ' + ', '.join(problems))
        return {'contract': CONTRACT, 'adapter_version': r.get('adapter_version'),
                'native_vi_version': vi.get('version')}

    def inventory_rows(self, kind, status='publish'):
        """Every row of one type/status from the adapter, with pagination proven complete."""
        rows, total, page, pages = [], None, 1, 1
        while page <= pages:
            r = self.adapter_get(ROUTES['inventory'][1], type=kind, status=status, per_page=100, page=page)
            if total is not None and r['total'] != total:
                raise NetworkError('Adapter collection changed during pagination')
            total, pages = r['total'], r['total_pages']
            rows.extend(r['items'])
            page += 1
        if total is None or len(rows) != total or len({x['id'] for x in rows}) != total:
            raise NetworkError('Incomplete or duplicate adapter pagination')
        return rows

    def categories(self):
        rows = self.adapter_get(ROUTES['categories'][1])['items']
        if any(x.get('language') not in LANGUAGES for x in rows):
            raise NetworkError('Adapter returned a category without a verified language')
        return rows

    def reconcile(self, key):
        if not KEY.fullmatch(key):
            raise ValueError('Invalid idempotency key')
        return self.adapter_get('/posts/by-key/' + key)

    def create(self, payload):
        data, _, _ = self.http.request(ADAPTER_BASE + ROUTES['create'][1], method='POST',
                                       body=validate_payload(payload), auth=True)
        return json.loads(data)


def manifest():
    """Contract summary compared with wordpress/.../contract.json by a test."""
    return {'contract': CONTRACT, 'namespace': 'thuha-writer/v1', 'routes': ROUTES,
            'create_fields': list(CREATE_FIELDS), 'seo_fields': list(SEO_FIELDS),
            'yoast_meta': list(YOAST_META), 'site': SITE, 'limits': LIMITS, 'html_policy': HTML_POLICY,
            'definitive_rejections_before_insert': list(DEFINITIVE_REJECTIONS)}
