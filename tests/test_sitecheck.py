"""Archive, pagination, sitemap, robots and language isolation, judged on local fixtures only."""
import unittest
from thuha import sitecheck
from thuha.common import SITE

LEAF = SITE + '/vi/chuyen-muc/gia-thue-va-chi-phi/'
PARENT = SITE + '/vi/chuyen-muc/huong-dan-thue-xe/'
POST = SITE + '/vi/ngan-sach-thue-xe-mot-ngay/'
EN_POST = SITE + '/motorbike-rental-prices-in-hanoi/'


def archive(url, links=(), lang='vi', robots='', extra=''):
    meta = '<meta name="robots" content="%s">' % robots if robots else ''
    anchors = ''.join('<article><a href="%s">post</a></article>' % x for x in links)
    return '<html lang="%s"><head><link rel="canonical" href="%s">%s%s</head><body>%s</body></html>' % (lang, url, meta, extra, anchors)


class ArchiveTests(unittest.TestCase):
    def test_a_good_archive_lists_its_post_is_indexable_and_self_canonical(self):
        self.assertEqual(sitecheck.check_archive(LEAF, archive(LEAF, [POST]), 200, {}, 'vi', [POST]), [])

    def test_parent_archive_must_contain_the_child_category_post(self):
        self.assertEqual(sitecheck.check_archive(PARENT, archive(PARENT, [POST]), 200, {}, 'vi', [POST]), [])
        self.assertEqual(sitecheck.check_archive(PARENT, archive(PARENT, []), 200, {}, 'vi', [POST]), ['ARCHIVE_MISSING_POST ' + POST])

    def test_noindex_left_over_from_the_empty_state_is_caught_in_meta_and_header(self):
        self.assertIn('ARCHIVE_NOINDEX', sitecheck.check_archive(LEAF, archive(LEAF, [POST], robots='noindex,follow'), 200, {}, 'vi', [POST]))
        self.assertIn('ARCHIVE_NOINDEX', sitecheck.check_archive(LEAF, archive(LEAF, [POST]), 200, {'X-Robots-Tag': 'noindex'}, 'vi', [POST]))

    def test_wrong_canonical_status_and_html_lang_are_caught(self):
        problems = sitecheck.check_archive(LEAF, archive(PARENT, [POST], lang='en'), 404, {}, 'vi', [POST])
        self.assertEqual(set(problems), {'ARCHIVE_HTTP_404', 'ARCHIVE_CANONICAL_NOT_SELF', 'ARCHIVE_HTML_LANG'})

    def test_a_vietnamese_archive_must_not_list_an_english_post(self):
        problems = sitecheck.check_archive(LEAF, archive(LEAF, [POST, EN_POST]), 200, {}, 'vi', [POST], foreign_urls=[EN_POST])
        self.assertEqual(problems, ['ARCHIVE_LISTS_OTHER_LANGUAGE_POST ' + EN_POST])


class PaginationTests(unittest.TestCase):
    P2 = LEAF + 'page/2/'

    def pages(self, **over):
        one = archive(LEAF, [POST], extra='<link rel="next" href="%s">' % self.P2)
        two = archive(self.P2, [], extra='<link rel="prev" href="%s">' % LEAF)
        return over.get('one', one), over.get('two', two)

    def test_linked_self_canonical_indexable_second_page_passes(self):
        one, two = self.pages()
        self.assertEqual(sitecheck.check_pagination(LEAF, one, self.P2, two, 200, {}, 'vi'), [])

    def test_missing_links_wrong_canonical_and_noindex_on_page_two_are_caught(self):
        one, two = self.pages(one=archive(LEAF, [POST]), two=archive(LEAF, [], robots='noindex'))
        problems = set(sitecheck.check_pagination(LEAF, one, self.P2, two, 200, {}, 'vi'))
        self.assertEqual(problems, {'PAGINATION_NEXT_MISSING', 'PAGINATION_PAGE2_CANONICAL', 'PAGINATION_PREV_MISSING', 'PAGINATION_PAGE2_NOINDEX'})


def sitemap(*urls):
    return '<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + ''.join('<url><loc>%s</loc></url>' % u for u in urls) + '</urlset>'


class SitemapRobotsTests(unittest.TestCase):
    INDEX = '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><sitemap><loc>%s/post-sitemap.xml</loc></sitemap></sitemapindex>' % SITE

    def test_an_independent_vietnamese_post_must_be_in_the_sitemap_without_an_english_pair(self):
        fetch = lambda url: sitemap(EN_POST, POST)
        self.assertEqual(sitecheck.check_sitemap(self.INDEX, fetch, include=[POST, EN_POST]), [])
        self.assertEqual(sitecheck.check_sitemap(self.INDEX, lambda u: sitemap(EN_POST), include=[POST]), ['SITEMAP_MISSING ' + POST])

    def test_drafts_or_foreign_urls_must_not_be_listed(self):
        draft = SITE + '/?p=1234'
        self.assertEqual(sitecheck.check_sitemap(self.INDEX, lambda u: sitemap(POST, draft), include=[POST], exclude=[draft]), ['SITEMAP_SHOULD_NOT_LIST ' + draft])

    def test_robots_must_not_block_the_vietnamese_namespace(self):
        good = 'User-agent: *\nDisallow: /wp-admin/\nSitemap: %s/sitemap_index.xml\n' % SITE
        self.assertEqual(sitecheck.check_robots(good), [])
        for blocked in ('/', '/vi/', '/vi', '/vi/chuyen-muc/'):
            bad = 'User-agent: *\nDisallow: %s\nSitemap: %s/sitemap_index.xml\n' % (blocked, SITE)
            self.assertTrue([p for p in sitecheck.check_robots(bad) if p.startswith('ROBOTS_BLOCKS')], blocked)
        self.assertEqual(sitecheck.check_robots('User-agent: *\nDisallow: /video/\nSitemap: https://x/s.xml\n'), [])
        self.assertEqual(sitecheck.check_robots('User-agent: *\nDisallow: /wp-admin/\n'), ['ROBOTS_NO_SITEMAP'])
        self.assertEqual(sitecheck.check_robots('User-agent: BadBot\nDisallow: /\nSitemap: https://x/s.xml\n'), [])


class IsolationTests(unittest.TestCase):
    def inv(self):
        return {'categories': [{'id': 10, 'parent': 0, 'language': 'en'}, {'id': 140, 'parent': 0, 'language': 'vi'}, {'id': 152, 'parent': 140, 'language': 'vi'}],
                'items': [{'id': 1, 'type': 'posts', 'language': 'en', 'url': EN_POST, 'slug': 'motorbike-rental-prices-in-hanoi', 'categories': [10]},
                          {'id': 2, 'type': 'posts', 'language': 'vi', 'url': POST, 'slug': 'ngan-sach-thue-xe-mot-ngay', 'categories': [152]}]}

    def test_clean_inventory_is_isolated(self):
        self.assertEqual(sitecheck.check_language_isolation(self.inv()), [])

    def test_every_leak_is_reported(self):
        inv = self.inv()
        inv['items'][1]['categories'] = [10]      # VI post in an EN category
        inv['items'][0]['url'] = SITE + '/vi/x/'  # EN post inside /vi/
        inv['items'].append({'id': 3, 'type': 'posts', 'language': 'vi', 'url': SITE + '/vi/y/', 'slug': 'motorbike-rental-prices-in-hanoi', 'categories': [152]})
        inv['categories'].append({'id': 99, 'parent': 140, 'language': 'en'})
        codes = {p.split()[0] for p in sitecheck.check_language_isolation(inv)}
        self.assertEqual(codes, {'CATEGORY_LANGUAGE_MISMATCH', 'URL_NAMESPACE_MISMATCH', 'SLUG_SHARED', 'CATEGORY_PARENT_OTHER_LANGUAGE'})

    def test_an_unverified_language_is_a_problem_not_a_default(self):
        inv = self.inv();inv['items'][0]['language'] = 'conflict'
        self.assertEqual(sitecheck.check_language_isolation(inv), ['LANGUAGE_UNVERIFIED 1'])

    def test_live_plan_names_leaf_and_every_ancestor_archive_and_stays_pending(self):
        inv = {'categories': [{'id': 140, 'link': SITE + '/vi/chuyen-muc/cam-nang/'}, {'id': 146, 'link': PARENT}, {'id': 152, 'link': LEAF}]}
        plan = sitecheck.plan_after_publication(POST, 'vi', [140, 146, 152], inv)
        self.assertEqual(plan['archives'], [LEAF, PARENT, SITE + '/vi/chuyen-muc/cam-nang/'])
        self.assertIn('PENDING_LIVE', plan['status'])


if __name__ == '__main__':
    unittest.main()
