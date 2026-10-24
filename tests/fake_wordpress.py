"""An HTTP-level stand-in for WordPress plus the companion plugin, for end-to-end tests.

It sits behind the real `HTTP` transport (the opener is replaced), so the real `AdapterClient`, inventory builder,
publisher and error handling run unchanged. It behaves like the plugin's contract (see wordpress/.../contract.json):
create-only POST, idempotent replay by key, one post per topic, slugs unique across languages, readback by key.
It is a simulation: nothing here proves how the real site, Yoast or the native Vietnamese plugin behave.
"""
import copy
import html
import io
import json
import math
import re
import threading
import urllib.error
from urllib.parse import parse_qs, urlsplit
from thuha.adapter import validate_payload
from thuha.common import SITE, digest
from thuha.http import HTTP
from thuha.language import post_url, url_language

PLUGIN = '/wp-json/thuha-writer/v1'


class Response:
    def __init__(self, body, status=200, headers=None):
        self.body = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.status = status
        self.headers = headers or {}

    def read(self, limit=None):
        return self.body if limit is None else self.body[:limit]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeOpener:
    def __init__(self, wordpress):
        self.wordpress = wordpress

    def open(self, request, timeout=None):
        return self.wordpress.handle(request.get_method(), request.full_url, request.data)


class FakeWordPress:
    def __init__(self, inventory):
        """`inventory` is a bilingual inventory fixture: its posts and pages become the existing site."""
        self.lock = threading.RLock()
        self.next_id = 1000
        self.rows = []
        self.categories = copy.deepcopy(inventory['categories'])
        self.media = copy.deepcopy(inventory['media'])
        self.created = []  # posts made through the plugin, in order
        self.requests = []  # (method, path) of every request, for assertions
        self.faults = []  # [method, path suffix, kind, remaining]
        self.page_faults = set()  # public-page problems: 'canonical', 'lang', 'noindex', 'schema', 'down'
        self.stored_title_suffix = ''  # makes WordPress store a different title than the one sent
        self.readback_override = {}  # field -> value WordPress reports back although something else was sent
        self.preflight_status = 200
        for item in inventory['items']:
            self.rows.append({'id': item['id'], 'type': 'post' if item['type'] == 'posts' else 'page', 'link': item['url'],
                              'slug': item['slug'], 'status': 'publish', 'title': item['title'],
                              'content': '<p>Existing content number ' + str(item['id']) + ' ' + item['slug'].replace('-', ' ') + '.</p>',
                              'modified_gmt': '2026-10-01T00:00:00', 'language': item['language'],
                              'categories': [20] if item['language'] == 'en' else [152], 'featured_media': 0, 'meta': {}})

    def http(self, allow_write=True):
        client = HTTP(allow_write=allow_write)
        client.opener = FakeOpener(self)
        return client

    # ------------------------------------------------------------------ faults

    def fail(self, method, suffix, kind, count=1):
        """kind: refuse | timeout_before | reject:<status>:<code> (nothing created) | timeout_after | reset_after |
        http500_after:<code> | http_error:<status>:<code> (after the post was created)"""
        self.faults.append([method, suffix, kind, count])

    def take_fault(self, method, path):
        for fault in self.faults:
            if fault[0] == method and path.endswith(fault[1]) and fault[3] > 0:
                fault[3] -= 1
                return fault[2]
        return None

    # ----------------------------------------------------------------- routing

    def handle(self, method, url, body):
        with self.lock:
            parts = urlsplit(url)
            path, query = parts.path, parse_qs(parts.query)
            self.requests.append((method, path))
            fault = self.take_fault(method, path)
            if fault == 'refuse':
                raise urllib.error.URLError(ConnectionRefusedError(111, 'Connection refused'))
            if fault == 'timeout_before':
                raise TimeoutError('timed out')
            if fault and fault.startswith('reject:'):  # the plugin refuses before creating anything
                _, status, code = fault.split(':')
                raise self.error(int(status), code)
            response = self.route(method, path, query, json.loads(body) if body else None, url)
            if fault == 'timeout_after':
                raise TimeoutError('timed out')
            if fault == 'reset_after':
                raise ConnectionResetError('Connection reset by peer')
            if fault and fault.startswith('http500_after'):
                raise self.error(500, fault.split(':', 1)[1] if ':' in fault else None)
            if fault and fault.startswith('http_error'):
                _, status, code = fault.split(':')
                raise self.error(int(status), code)
            return response

    def error(self, status, code):
        payload = json.dumps({'code': code, 'message': 'details that must never be kept'} if code else {}).encode()
        return urllib.error.HTTPError('https://rentbikehanoi.com' + PLUGIN, status, 'error', {}, io.BytesIO(payload))

    def route(self, method, path, query, body, url):
        if path == PLUGIN + '/preflight':
            if self.preflight_status != 200:
                raise self.error(self.preflight_status, 'rest_no_route')
            return Response({'contract': 'thuha-writer/1', 'adapter_version': '1.0.0',
                             'native_vi': {'present': True, 'set_vi': True, 'is_vi': True, 'term_is_vi': True,
                                           'taxonomy': 'rbhvi_language', 'version': '1.1.1'},
                             'yoast': {'present': True}, 'user': {'can': {'edit_posts': True, 'publish_posts': True}},
                             'auth': {'application_password': True}, 'settings': {'sitemap_pairs_only': False}})
        if path == PLUGIN + '/inventory':
            kind, status = query['type'][0], query['status'][0]
            rows = [r for r in self.rows + [self.inventory_row(p) for p in self.created] if r['type'] == kind and r['status'] == status]
            per, page = int(query['per_page'][0]), int(query['page'][0])
            return Response({'total': len(rows), 'total_pages': max(1, math.ceil(len(rows) / per)),
                             'items': rows[(page - 1) * per:page * per]})
        if path == PLUGIN + '/categories':
            return Response({'items': self.categories})
        match = re.fullmatch(re.escape(PLUGIN) + r'/posts/by-key/([a-f0-9]{64})', path)
        if match:
            post = next((p for p in self.created if p['idempotency_key'] == match.group(1)), None)
            return Response({'found': True, 'post': self.readback(post)} if post else {'found': False})
        if path == PLUGIN + '/posts' and method == 'POST':
            return self.create(body)
        if path == '/wp-json/wp/v2/media':
            return self.collection(self.media, query)
        if method == 'GET' and urlsplit(url).netloc == 'rentbikehanoi.com':
            return self.public_page(url)
        raise self.error(404, 'rest_no_route')

    def collection(self, rows, query):
        if 'include' in query:
            wanted = {int(x) for x in query['include'][0].split(',')}
            rows = [r for r in rows if r['id'] in wanted]
        per, page = int(query['per_page'][0]), int(query['page'][0])
        headers = {'X-WP-Total': str(len(rows)), 'X-WP-TotalPages': str(max(1, math.ceil(len(rows) / per)))}
        return Response([dict(r, media_type='image') for r in rows[(page - 1) * per:page * per]], headers=headers)

    # ------------------------------------------------------------ plugin contract

    def create(self, payload):
        try:
            validate_payload(payload)
        except ValueError:
            raise self.error(422, 'thuha_schema') from None
        existing = next((p for p in self.created if p['idempotency_key'] == payload['idempotency_key']), None)
        if existing:
            if existing['payload_sha'] != digest(payload):
                raise self.error(409, 'thuha_key_payload_mismatch')
            return Response({'created': False, 'idempotent_replay': True, 'post': self.readback(existing)})
        if any(p['topic_id'] == payload['topic_id'] for p in self.created):
            raise self.error(409, 'thuha_topic_already_created')
        if any(r['slug'] == payload['slug'] for r in self.rows) or any(p['slug'] == payload['slug'] for p in self.created):
            raise self.error(409, 'thuha_slug_conflict')
        language = payload['language']
        chain = {c['id']: c for c in self.categories}.get(payload['category_id'])
        if not chain or chain['language'] != language:
            raise self.error(422, 'thuha_category_language_mismatch')
        post = {'id': self.next_id, 'status': 'publish', 'language': language, 'slug': payload['slug'],
                'link': post_url(language, payload['slug']), 'title': payload['title'] + self.stored_title_suffix,
                'content_raw': payload['content'], 'categories': [payload['category_id']], 'category_languages': [language],
                'featured_media': payload['featured_media'], 'seo': payload['seo'],
                'idempotency_key': payload['idempotency_key'], 'topic_id': payload['topic_id'], 'payload_sha': digest(payload)}
        self.next_id += 1
        self.created.append(post)
        return Response({'created': True, 'idempotent_replay': False, 'post': self.readback(post)})

    def readback(self, post):
        language = post['language']
        return dict(self.plain_readback(post), **self.readback_override)

    def plain_readback(self, post):
        language = post['language']
        return {'id': post['id'], 'type': 'post', 'status': post['status'], 'language': language, 'slug': post['slug'], 'link': post['link'],
                'title': post['title'], 'content': post['content_raw'], 'content_raw': post['content_raw'],
                'categories': post['categories'], 'category_languages': post['category_languages'],
                'featured_media': post['featured_media'],
                'meta': {'_yoast_wpseo_title': post['seo']['title'], '_yoast_wpseo_metadesc': post['seo']['description'],
                         '_yoast_wpseo_focuskw': post['seo']['focus_keyword']},
                'owner': 'thuha-writer', 'idempotency_key': post['idempotency_key'], 'marker_present': True, 'incomplete': False,
                'language_markers': {'is_vi': language == 'vi', 'taxonomy_vi': language == 'vi'}}

    def inventory_row(self, post):
        return {'id': post['id'], 'type': 'post', 'link': post['link'], 'slug': post['slug'], 'status': post['status'],
                'title': post['title'], 'content': post['content_raw'], 'modified_gmt': '2026-10-23T00:00:00',
                'language': post['language'], 'categories': post['categories'], 'featured_media': post['featured_media'],
                'meta': {'_yoast_wpseo_title': post['seo']['title'], '_yoast_wpseo_metadesc': post['seo']['description'],
                         '_yoast_wpseo_focuskw': post['seo']['focus_keyword']}}

    def public_page(self, url):
        if 'down' in self.page_faults:
            raise self.error(503, None)
        post = next((p for p in self.created if p['link'] == url), None)
        row = next((r for r in self.rows if r['link'] == url), None)
        if not post and not row:
            raise self.error(404, None)
        lang = (post or row)['language']
        title = post['seo']['title'] if post else row['title']
        description = post['seo']['description'] if post else 'Existing page description.'
        canonical = SITE + '/wrong/' if 'canonical' in self.page_faults else url
        robots = '<meta name="robots" content="noindex">' if 'noindex' in self.page_faults else ''
        schema = '' if 'schema' in self.page_faults else '<script type="application/ld+json">{"@context":"https://schema.org","@type":"Article"}</script>'
        html_lang = 'en' if 'lang' in self.page_faults and lang == 'vi' else ('vi' if lang == 'vi' else 'en-US')
        rendered_h1 = (post or row)['title']
        if 'h1' in self.page_faults:
            rendered_h1 = 'Hanoi motorbike rental prices for visitors' if lang == 'vi' else 'Giá thuê xe máy tại Hà Nội'
        page = ('<html lang="' + html_lang + '"><head><title>' + title + '</title><meta name="description" content="' + description + '">'
                '<link rel="canonical" href="' + canonical + '">' + robots + schema + '</head><body><h1>' + html.escape(rendered_h1) + '</h1></body></html>')
        return Response(page.encode(), headers={'Content-Type': 'text/html'})

    # ----------------------------------------------------------------- helpers

    def posts_for(self, topic_id):
        return [p for p in self.created if p['topic_id'] == topic_id]

    def post_requests(self):
        return [r for r in self.requests if r == ('POST', PLUGIN + '/posts')]
