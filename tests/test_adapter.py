"""Adapter contract: Python client, PHP plugin (offline simulation), package integrity."""
import json
import shutil
import subprocess
import unittest
import zipfile
from unittest.mock import patch
from thuha import adapter, package
from thuha.adapter import AdapterClient, NOT_DEPLOYED, build_payload, validate_payload
from thuha.audit import inventory_bilingual
from thuha.common import ROOT, SITE, digest, load
from thuha.http import ADAPTER_BASE, ADAPTER_CREATE_URL, HTTP, NetworkError
from thuha.language import post_url


class ScriptedHTTP:
    """Replays canned adapter answers; records every URL so the transport rules are observable."""
    def __init__(self, routes):
        self.routes, self.calls = routes, []
    def request(self, url, *, method='GET', body=None, auth=False):
        self.calls.append((method, url, auth))
        for needle, answer in self.routes.items():
            if needle in url:
                if isinstance(answer, Exception):
                    raise answer
                return json.dumps(answer).encode(), {}, 200
        raise NetworkError('HTTP 404 for ' + url, 404)


def good_preflight(**over):
    base = {'contract': 'thuha-writer/1', 'adapter_version': '1.0.0',
            'native_vi': {'present': True, 'version': '1.0.0', 'set_vi': True, 'is_vi': True, 'term_is_vi': True, 'taxonomy': 'rbhvi_language'},
            'yoast': {'present': True}, 'user': {'id': 2, 'can': {'edit_posts': True, 'publish_posts': True}},
            'auth': {'application_password': True}, 'settings': {'sitemap_pairs_only': False}}
    base.update(over)
    return base


class ClientTests(unittest.TestCase):
    def test_missing_plugin_is_reported_as_blocked_not_deployed(self):
        client = AdapterClient(ScriptedHTTP({}))
        with self.assertRaisesRegex(ValueError, NOT_DEPLOYED):client.preflight()

    def test_rejected_credentials_are_not_mistaken_for_a_missing_plugin(self):
        for status in (401, 403):
            http = ScriptedHTTP({'/preflight': NetworkError('HTTP %d for /wp-json/thuha-writer/v1/preflight' % status, status)})
            with self.assertRaisesRegex(ValueError, 'ADAPTER_AUTH_REJECTED'):AdapterClient(http).preflight()

    def test_preflight_demands_every_native_and_publishing_prerequisite(self):
        self.assertEqual(AdapterClient(ScriptedHTTP({'/preflight': good_preflight()})).preflight()['contract'], 'thuha-writer/1')
        cases = {
            'native set_vi missing': good_preflight(native_vi={'present': True, 'set_vi': False, 'is_vi': True, 'term_is_vi': True, 'taxonomy': 'rbhvi_language'}),
            'taxonomy missing': good_preflight(native_vi={'present': True, 'set_vi': True, 'is_vi': True, 'term_is_vi': True, 'taxonomy': None}),
            'contributor': good_preflight(user={'id': 2, 'can': {'edit_posts': True, 'publish_posts': False}}),
            'cookie auth': good_preflight(auth={'application_password': False}),
            'pairs only sitemap': good_preflight(settings={'sitemap_pairs_only': True}),
            'unknown pairs setting': good_preflight(settings={'sitemap_pairs_only': None}),
            'no yoast': good_preflight(yoast={'present': False}),
            'other contract': good_preflight(contract='thuha-writer/2'),
        }
        for name, answer in cases.items():
            with self.subTest(name), self.assertRaisesRegex(ValueError, 'preflight failed'):
                AdapterClient(ScriptedHTTP({'/preflight': answer})).preflight()

    def test_inventory_pagination_must_be_complete_and_stable(self):
        rows = [{'id': i} for i in range(1, 4)]
        pages = iter([{'total': 3, 'total_pages': 2, 'items': rows[:2]}, {'total': 3, 'total_pages': 2, 'items': rows[2:]}])
        class Paged(ScriptedHTTP):
            def request(self, url, **kw):
                self.calls.append(url);return json.dumps(next(pages)).encode(), {}, 200
        self.assertEqual(len(AdapterClient(Paged({})).inventory_rows('post')), 3)
        short = iter([{'total': 3, 'total_pages': 1, 'items': rows[:2]}])
        class Short(ScriptedHTTP):
            def request(self, url, **kw):return json.dumps(next(short)).encode(), {}, 200
        with self.assertRaises(NetworkError):AdapterClient(Short({})).inventory_rows('post')
        moving = iter([{'total': 3, 'total_pages': 2, 'items': rows[:2]}, {'total': 4, 'total_pages': 2, 'items': rows[2:]}])
        class Moving(ScriptedHTTP):
            def request(self, url, **kw):return json.dumps(next(moving)).encode(), {}, 200
        with self.assertRaises(NetworkError):AdapterClient(Moving({})).inventory_rows('post')

    def test_categories_without_a_verified_language_are_refused(self):
        bad = {'items': [{'id': 1, 'language': 'conflict'}]}
        with self.assertRaises(NetworkError):AdapterClient(ScriptedHTTP({'/categories': bad})).categories()

    def test_inventory_counts_languages_and_excludes_pages(self):
        def row(i, lang, kind='post'):
            return {'id': i, 'type': kind, 'status': 'publish', 'language': lang, 'slug': 's%d' % i, 'title': 'T%d' % i,
                    'link': post_url(lang, 's%d' % i) if kind == 'post' else SITE + '/vi/trang-%d/' % i, 'content': '<p>x</p>',
                    'categories': [], 'featured_media': 0, 'meta': {}}
        class Fake(AdapterClient):
            def inventory_rows(self, kind, status='publish'):
                return [row(1, 'en'), row(2, 'en'), row(3, 'vi')] if kind == 'post' else [row(9, 'vi', 'page')]
            def categories(self):return []
            def collection(self, *a, **k):return []
        inv = inventory_bilingual(Fake(ScriptedHTTP({})), check_pages=False)
        self.assertTrue(inv['complete']);self.assertEqual(inv['language_source'], 'adapter')
        self.assertEqual(inv['counts']['posts_by_language'], {'vi': 1, 'en': 2})
        self.assertEqual(inv['counts']['pages_by_language'], {'vi': 1, 'en': 0});self.assertEqual(inv['counts']['posts'], 3)

    def test_a_row_without_a_verified_language_makes_the_inventory_incomplete(self):
        class Fake(AdapterClient):
            def inventory_rows(self, kind, status='publish'):return [{'id': 1, 'language': 'conflict'}]
        inv = inventory_bilingual(Fake(ScriptedHTTP({})), check_pages=False)
        self.assertFalse(inv['complete']);self.assertTrue(inv['errors'])


class TransportTests(unittest.TestCase):
    def test_the_only_write_is_one_post_to_the_adapter(self):
        http = HTTP(allow_write=True)
        for url in (SITE + '/wp-json/wp/v2/posts', SITE + '/wp-json/thuha-writer/v1/inventory', SITE + '/wp-json/wp/v2/posts/5'):
            with self.assertRaises(ValueError):http.request(url, method='POST', body={})
        for method in ('PUT', 'PATCH', 'DELETE'):
            with self.assertRaises(ValueError):http.request(ADAPTER_CREATE_URL, method=method, body={})
        with self.assertRaises(ValueError):HTTP().request(ADAPTER_CREATE_URL, method='POST', body={})  # writes are off by default

    def test_credentials_only_reach_the_production_rest_origin(self):
        with self.assertRaises(ValueError):HTTP().request('https://api.github.com/wp-json/', auth=True)  # fixed allowed host, so no DNS is needed

    def test_create_posts_only_the_closed_contract(self):
        topic = {'topic_id': 'TH-VI-0001', 'language': 'vi', 'category_id': 152}
        article = {'title': 'T', 'body_html': '<p>x</p>', 'featured_media': 51, 'seo_title': 's', 'meta_description': 'm', 'focus_keyword': 'k'}
        payload = build_payload(topic, article, 'a' * 64, '<!-- thuha:v5 topic=TH-VI-0001 sha256=' + 'b' * 64 + ' -->', 'slug')
        self.assertEqual(set(payload), set(adapter.CREATE_FIELDS));validate_payload(payload)
        for bad in (dict(payload, post_status='publish'), dict(payload, language='fr'), dict(payload, idempotency_key='x'),
                    dict(payload, category_id='152'), dict(payload, seo={'title': 'a'})):
            with self.assertRaises(ValueError):validate_payload(bad)
        http = ScriptedHTTP({'/posts': {'created': True, 'post': {'id': 5}}})
        AdapterClient(http).create(payload)
        self.assertEqual(http.calls, [('POST', ADAPTER_CREATE_URL, True)])


class ContractTests(unittest.TestCase):
    def test_python_and_plugin_contracts_agree(self):
        contract = load(package.SOURCE / 'contract.json')
        mine = adapter.manifest()
        for key in ('contract', 'namespace', 'create_fields', 'seo_fields', 'yoast_meta'):
            self.assertEqual(contract[key], mine[key], key)
        self.assertEqual(contract['routes'], {k: list(v) for k, v in mine['routes'].items()})
        self.assertEqual(contract['safety']['public_routes'], 0)
        self.assertFalse(contract['safety']['raw_sql']);self.assertFalse(contract['safety']['replay_mutates'])
        self.assertIn('NOT_DEPLOYED', contract['live_status'])

    def test_php_declares_the_same_create_fields_and_yoast_keys(self):
        php = (package.SOURCE / 'includes/class-thuha-contract.php').read_text()
        for field in adapter.CREATE_FIELDS + adapter.SEO_FIELDS + adapter.YOAST_META:
            self.assertIn("'" + field + "'", php, field)
        self.assertIn(adapter.CONTRACT, php)

    def test_archive_is_current_reproducible_and_safe(self):
        evidence = package.verify()
        self.assertEqual(evidence['safety_scan'], 'clean')
        data = package.build_bytes();self.assertEqual(data, package.build_bytes())
        with zipfile.ZipFile(package.DIST / package.archive_name()) as archive:
            names = archive.namelist()
            self.assertTrue(all(n.startswith(package.SLUG + '/') for n in names))
            self.assertIn(package.SLUG + '/' + package.SLUG + '.php', names)
            self.assertFalse([n for n in names if n.endswith(('.key', '.pem', '.env')) or 'secret' in n.lower()])
            self.assertEqual({i.date_time for i in archive.infolist()}, {package.STAMP})
        import hashlib
        self.assertEqual(evidence['sha256'], hashlib.sha256(data).hexdigest())

    def test_safety_scan_catches_forbidden_constructs(self):
        for snippet in ('$wpdb->query("DELETE FROM x");', 'eval($_POST["c"]);', 'register_rest_route("a","/b",array("permission_callback"=>"__return_true"));',
                        'unserialize($x);', 'wp_remote_get("https://x");', 'file_put_contents("a","b");', '$x = $_POST["a"];', 'include $path;'):
            hits = [l for l, pattern in package.FORBIDDEN.items() if __import__('re').search(pattern, snippet)]
            self.assertTrue(hits, snippet)


@unittest.skipUnless(shutil.which('php'), 'php is not installed; the CI workflow runs this harness')
class PluginHarnessTests(unittest.TestCase):
    def test_every_php_file_lints(self):
        for path in package.files():
            if path.suffix == '.php':
                result = subprocess.run(['php', '-l', str(path)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_plugin_logic_against_the_wordpress_simulation(self):
        result = subprocess.run(['php', str(ROOT / 'tests/php/run.php')], capture_output=True, text=True)
        report = json.loads(result.stdout)
        self.assertEqual(report['failed'], [], result.stderr)
        self.assertGreaterEqual(len(report['passed']), 17)


if __name__ == '__main__':
    unittest.main()
