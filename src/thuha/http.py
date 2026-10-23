"""Bounded GET retries; WordPress POST is create-only and NEVER retried."""
import base64
import ipaddress
import json
import os
import re
import socket
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit, urlencode
from .common import SITE

ADAPTER_BASE = SITE + '/wp-json/thuha-writer/v1'
ADAPTER_CREATE_URL = ADAPTER_BASE + '/posts'


class NetworkError(RuntimeError):
    def __init__(self, message, status=None, code=None):
        super().__init__(message)
        self.status = status
        self.code = code  # machine code from a JSON error answer (letters/underscores only); never the body text


def safe_url_shape(url):
    """Structural check only: HTTPS, a hostname, no credentials, default port."""
    p = urlsplit(url)
    if p.scheme != 'https' or not p.hostname or p.username or p.password or p.port not in (None, 443):
        raise ValueError('Unsafe source URL')
    return url


def safe_public_url(url):
    safe_url_shape(url)
    p = urlsplit(url)
    # These two fixed, user-authorized service origins are resolved by the
    # environment's egress proxy when local DNS is intentionally unavailable.
    # Arbitrary research URLs retain the strict public-address check below.
    if p.hostname in ('rentbikehanoi.com', 'api.github.com'):
        return url
    try:addresses = socket.getaddrinfo(p.hostname, 443, type=socket.SOCK_STREAM)
    except OSError:
        raise NetworkError('DNS lookup failed for source origin; no content verdict was made') from None
    if not addresses or any(not ipaddress.ip_address(x[4][0]).is_global for x in addresses):
        raise ValueError('Source resolves to a non-public address')
    return url


def error_code(exc):
    """The `code` field of a WordPress JSON error, or None; the rest of the body is discarded."""
    try:
        value = json.loads(exc.read(4096)).get('code')
    except (ValueError, OSError, AttributeError):
        return None
    return value if isinstance(value, str) and re.fullmatch(r'[a-z_]{3,60}', value) else None


class Redirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        safe_public_url(newurl)
        if req.get_header('Authorization') and urlsplit(req.full_url).netloc != urlsplit(newurl).netloc:
            raise NetworkError('Authenticated cross-origin redirect refused')
        if req.method != 'GET':
            raise NetworkError('POST redirect requires reconciliation')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class HTTP:
    def __init__(self, *, allow_write=False, timeout=25):
        self.allow_write = allow_write
        self.timeout = timeout
        self.opener = urllib.request.build_opener(Redirects())

    def request(self, url, *, method='GET', body=None, auth=False):
        safe_public_url(url)
        # The only write is one create-only POST to the companion adapter; core
        # /wp/v2/posts is never written because it cannot attach the VI marker first.
        if method != 'GET' and not (method == 'POST' and self.allow_write and url == ADAPTER_CREATE_URL):
            raise ValueError('Only explicitly enabled adapter create-post writes are supported')
        headers = {'User-Agent': 'ThuHa-Writer/4 read-only-audit', 'Accept-Encoding': 'identity'}
        if auth:
            if not url.startswith(SITE + '/wp-json/'):
                raise ValueError('Credentials may only reach the production REST origin')
            user, password = os.environ.get('THUHA_WP_USER'), os.environ.get('THUHA_WP_APPLICATION_PASSWORD')
            if not user or not password:
                raise ValueError('WordPress credentials are not configured')
            headers['Authorization'] = 'Basic ' + base64.b64encode((user+':'+password).encode()).decode()
        raw = None if body is None else json.dumps(body).encode()
        if raw is not None:
            headers['Content-Type'] = 'application/json'
        for attempt in range(3 if method == 'GET' else 1):
            try:
                req = urllib.request.Request(url, raw, headers, method=method)
                with self.opener.open(req, timeout=self.timeout) as response:
                    data = response.read(12_000_001)
                    if len(data) > 12_000_000:
                        raise NetworkError('Response size limit exceeded')
                    return data, dict(response.headers), response.status
            except urllib.error.HTTPError as exc:
                if method == 'GET' and exc.code in (429, 500, 502, 503, 504) and attempt < 2:
                    time.sleep(min(5, 1 + attempt))
                    continue
                raise NetworkError('HTTP '+str(exc.code)+' for '+urlsplit(url).path, exc.code, error_code(exc)) from None
            except (OSError, TimeoutError) as exc:
                if method == 'GET' and attempt < 2:
                    time.sleep(1+attempt)
                    continue
                raise NetworkError('Network failure; outcome may be unknown for POST') from None


class WordPress:
    def __init__(self, http=None):
        self.http = http or HTTP()

    def get(self, resource, auth=False, **query):
        url = SITE + '/wp-json/wp/v2/' + resource
        if query:
            url += '?' + urlencode(query)
        data, headers, status = self.http.request(url, auth=auth)
        return json.loads(data), headers

    def collection(self, resource, **query):
        rows, headers = self.get(resource, per_page=100, page=1, **query)
        total = int(headers.get('X-WP-Total', headers.get('x-wp-total', '-1')))
        pages = int(headers.get('X-WP-TotalPages', headers.get('x-wp-totalpages', '-1')))
        if total < 0 or pages < 0:
            raise NetworkError('Pagination headers absent')
        for page in range(2, pages+1):
            more, h = self.get(resource, per_page=100, page=page, **query)
            if int(h.get('X-WP-Total', h.get('x-wp-total', '-1'))) != total:
                raise NetworkError('Collection changed during pagination')
            rows.extend(more)
        _, last = self.get(resource, per_page=1, page=1, **query)
        if int(last.get('X-WP-Total', last.get('x-wp-total', '-1'))) != total:
            raise NetworkError('Collection count changed during capture')
        if len(rows) != total or len({r['id'] for r in rows}) != total:
            raise NetworkError('Incomplete or duplicate pagination')
        return rows

    def page(self, url):
        data, headers, status = self.http.request(url)
        return data.decode('utf-8'), headers, status

