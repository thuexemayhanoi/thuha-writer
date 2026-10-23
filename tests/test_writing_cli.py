"""The writing commands end to end: pack, build, precheck, the submit guard and next. All of it works from the repository alone."""
import contextlib
import io
import json
import unittest
from pathlib import Path
from unittest.mock import patch
from test_factory import Fixture, vi_filler
from test_waiting_data import without_vi_media
from thuha import cli, quality, writing
from thuha.common import SITE, digest, load, now
from thuha.coordinator import claim, hold
from thuha.language import post_url
from thuha.research import intake

COMMIT = 'c' * 40


class Cli(Fixture):
    def run_cli(self, *argv, inv=None, inventory=True):
        path = Path(self.temp.name) / 'inv.json'
        path.write_text(json.dumps(inv or self.inv))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main(['--state-dir', self.temp.name] + (['--inventory', str(path)] if inventory else []) + list(argv))
        return code, json.loads(out.getvalue())

    def write(self, name, value):
        path = Path(self.temp.name) / name
        path.write_text(value if isinstance(value, str) else json.dumps(value), encoding='utf-8')
        return str(path)

    def distinct(self, number):
        """A Vietnamese topic whose title, keyword and intent share nothing with the fixture's others (intake refuses near-duplicates)."""
        names = {2: ('Cách chia tiền xăng khi cả nhóm đi nhiều xe', 'chia tiền xăng cả nhóm', 'cách tính phần xăng cho từng người trong nhóm', 'cach-chia-tien-xang-ca-nhom'),
                 3: ('Kiểm tra phanh và đèn trước khi nhận xe', 'kiểm tra phanh đèn khi nhận xe', 'những điểm cần nhìn trên xe lúc nhận', 'kiem-tra-phanh-den-khi-nhan-xe')}
        title, keyword, intent, slug = names[number]
        return dict(self.candidate(number, 'vi'), proposed_title=title, primary_keyword=keyword, search_intent=intent, proposed_url=post_url('vi', slug))

    def leased(self, number=1, lang='vi'):
        topic = self.candidate(number, lang) if number == 1 or lang != 'vi' else self.distinct(number)
        intake(self.store, [topic], self.inv)
        return topic, claim(self.store, 'session-w%d' % number, 'writer-w%d' % number)

    def body(self, topic, links=True):
        tail = ('<h2>Điểm dừng thực tế</h2><p>Xem thêm <a href="%s/vi/gioi-thieu-cua-hang/">giới thiệu cửa hàng</a> và <a href="%s/vi/bai-viet-co-san/">bài viết liên quan</a>.</p>' % (SITE, SITE)) if links else ''
        return '<h2>Chuẩn bị lộ trình</h2>' + vi_filler(topic['topic_id']) + tail

    META = {'seo_title': 'Kế hoạch lộ trình nhẹ nhàng cho một ngày di chuyển thoải mái', 'featured_media': 51,
            'meta_description': 'Chuẩn bị lộ trình, điểm dừng thực tế và các liên kết hữu ích trước khi chọn chi tiết cho chuyến đi trong ngày của bạn tại Hà Nội.'}


class ConfigTiesToQaTests(Cli):
    """The bands in config/writing.json are the ones QA scores; if either side moves, this fails instead of letting a writer aim at the wrong target."""

    def setUp(self):
        super().setUp()
        self.topic = self.candidate(1, 'vi')
        intake(self.store, [self.topic], self.inv)
        claim(self.store, 'session-b', 'writer-b')

    def raw_score(self, **fields):
        topic = self.topic
        article = dict(self.article_for(topic, 'session-b', 'writer-b'), **fields)
        submission = {'article_sha': digest(article), 'session': 'session-b', 'agent_id': 'writer-b'}
        return quality.evaluate(article, self.store.read()['topics']['TH-VI-0001'], submission, self.inv, self.policy, self.store, None, self.business)['raw_score']

    def test_the_seo_title_band_is_the_one_qa_scores(self):
        band = writing.settings()['metadata']['seo_title']
        score = lambda n: self.raw_score(seo_title=('Kế hoạch lộ trình ' + 'a' * 100)[:n])
        self.assertEqual(score(band['min']) - score(band['min'] - 1), 10)
        self.assertEqual(score(band['max']) - score(band['max'] + 1), 10)

    def test_the_meta_description_band_is_the_one_qa_scores(self):
        band = writing.settings()['metadata']['meta_description']
        score = lambda n: self.raw_score(meta_description=('Chuẩn bị lộ trình trước khi đi ' + 'a' * 200)[:n])
        self.assertEqual(score(band['min']) - score(band['min'] - 1), 10)
        self.assertEqual(score(band['max']) - score(band['max'] + 1), 10)
        self.assertLessEqual(band['recommended_max'], band['max'])


class PackTests(Cli):
    def test_a_pack_holds_what_a_writer_needs_and_changes_nothing(self):
        topic, lease = self.leased()
        before = self.store.read()
        with patch('thuha.writing.git_head', return_value=COMMIT):
            code, out = self.run_cli('pack', '--topic-id', 'TH-VI-0001')
        after = self.store.read()
        self.assertEqual((code, out['ledger_writes'], out['wordpress_writes']), (0, 0, 0))
        self.assertEqual((after['version'], len(after['events'])), (before['version'], len(before['events'])))
        self.assertEqual((out['language'], out['article_language_value'], out['canonical']), ('vi', 'vi', topic['proposed_url']))
        self.assertEqual([(c['id'], c['source']) for c in out['taxonomy']], [(140, 'inventory'), (152, 'inventory')])
        skeleton = out['skeleton']
        self.assertEqual((skeleton['topic_id'], skeleton['session'], skeleton['agent_id'], skeleton['source_commit']), ('TH-VI-0001', 'session-w1', 'writer-w1', COMMIT))
        self.assertEqual((skeleton['language'], skeleton['category_id'], skeleton['canonical'], skeleton['featured_media']), ('vi', 152, topic['proposed_url'], None))
        self.assertEqual(skeleton['sources'], [dict(topic['sources'][0])])
        self.assertEqual(skeleton['focus_keyword'], topic['primary_keyword'])
        self.assertEqual((out['lease']['slot'], out['lease']['fence']), (lease['slot'], lease['fence']))

    def test_links_and_images_offered_are_of_the_articles_language_only(self):
        self.leased()
        vi = self.run_cli('pack', '--topic-id', 'TH-VI-0001')[1]
        self.assertEqual([x['id'] for x in vi['internal_links']['live']], [4, 3])  # posts before pages, and no English page
        self.assertEqual([a['id'] for a in vi['internal_links']['archives']], [152, 140])  # the topic's own category first
        self.assertEqual([m['id'] for m in vi['media']['options']], [51])  # the English alt text is not offered to a Vietnamese article
        topic = self.candidate(2, 'en')
        intake(self.store, [topic], self.inv)
        en = self.run_cli('pack', '--topic-id', 'TH-EN-0002')[1]
        self.assertEqual([x['id'] for x in en['internal_links']['live']], [1, 2])
        self.assertEqual([m['id'] for m in en['media']['options']], [50])
        self.assertIsNone(en['skeleton']['session'])  # not leased: nothing to build yet

    def test_the_shop_facts_come_from_the_confirmed_file_and_a_price_is_never_made_up(self):
        self.leased()
        out = self.run_cli('pack', '--topic-id', 'TH-VI-0001')[1]
        business = out['business']
        self.assertIn('0334 699 969', business['contact_html'])
        rows = {(r['vehicle'], r['period']): r for r in business['price_table']}
        self.assertIsNone(rows[('electric', 'day')]['interval'])
        self.assertEqual(rows[('Air Blade', 'week')]['interval'], [900000, 900000])
        self.assertEqual(business['never_assert'], ['delivery', 'deposit procedure', 'deposit refunds'])
        self.assertEqual(business['extension_policy']['hourly_rate_vnd'], 20000)
        self.assertEqual(business['extension_policy']['one_rental_day_when_extension_hours_exceed'], 6)
        self.assertEqual(business['extension_policy']['confirmed_by'], 'website owner')
        self.assertTrue(quality.re.search(quality.DISCLAIMER['vi'], business['price_disclaimer'], quality.re.I))

    def test_a_saved_source_of_another_topic_that_fits_is_offered_for_reuse_but_never_re_captured(self):
        first, _ = self.leased(1)
        evidence = {'url': SITE + '/lo-trinh-nhe-nhang/', 'checked_at': now(), 'http_status': 200, 'response_sha256': 'b' * 64,
                    'page_title': 'Kế hoạch lộ trình nhẹ nhàng cho người mới đi xe', 'excerpt': 'Một đoạn trích ngắn.'}
        ref = {'url': evidence['url'], 'document': self.store.put_document(evidence), 'supports': 'Trang này nói về việc lên kế hoạch lộ trình nhẹ nhàng cho người mới.'}
        other = dict(self.distinct(2), sources=[ref])
        intake(self.store, [other], self.inv)
        out = self.run_cli('pack', '--topic-id', 'TH-VI-0001')[1]
        self.assertEqual([s['url'] for s in out['sources']['saved']], [first['sources'][0]['url']])
        self.assertEqual([(s['url'], s['used_by'], s['current']) for s in out['sources']['reusable']], [(evidence['url'], 'TH-VI-0002', True)])
        self.assertEqual(out['skeleton']['sources'][0]['document'], first['sources'][0]['document'])  # nothing is attached on the writer's behalf

    def test_a_first_party_capture_the_facts_file_has_outgrown_is_left_out_and_the_fresh_one_goes_in(self):
        topic, _ = self.leased()
        stale = {'url': 'repo://config/business-facts.json', 'checked_at': now(), 'http_status': 200, 'response_sha256': 'a' * 64, 'file_sha256': '0' * 64,
                 'capture_method': 'repository-file', 'excerpt': 'x', 'page_title': 'config/business-facts.json'}
        ref = dict(topic['sources'][0], url=stale['url'], document=self.store.put_document(stale))
        self.store.mutate(lambda s: s['topics']['TH-VI-0001'].update(sources=[ref]))
        pack = self.run_cli('pack', '--topic-id', 'TH-VI-0001')[1]
        self.assertFalse(pack['sources']['saved'][0]['current'])
        self.assertIn('source --repository-file', pack['sources']['saved'][0]['problem'])
        fresh = self.run_cli('source', '--repository-file', 'config/business-facts.json')[1]
        extra = {'url': fresh['url'], 'document': fresh['document'], 'supports': 'Thông tin cửa hàng dùng ở phần liên hệ của bài, chụp lại sau khi tệp đổi.'}
        with patch('thuha.writing.git_head', return_value=COMMIT):
            code, out = self.run_cli('build', '--topic-id', 'TH-VI-0001', '--body', self.write('body.html', self.body(topic)),
                                     '--meta', self.write('meta.json', dict(self.META, extra_sources=[extra])), '--out', str(Path(self.temp.name) / 'built.json'))
        article = load(Path(out['article_file']))
        self.assertEqual([s['document'] for s in article['sources']], [fresh['document']])
        self.assertEqual([s['document'] for s in out['left_out_stale_sources']], [ref['document']])
        self.assertNotIn('SOURCE_STALE_OR_UNVERIFIED', out['hard_fails'])

    def test_planned_pages_are_listed_but_are_never_live_links(self):
        self.leased()
        out = self.run_cli('pack', '--topic-id', 'TH-VI-0001')[1]
        planned = out['internal_links']['planned']
        self.assertTrue(planned)
        for entry in planned:
            self.assertEqual((entry['live'], entry['counts_for_qa']), (False, False))
            self.assertTrue(entry['url'].startswith(SITE + '/vi/'))

    def test_the_pack_says_what_the_inventory_lacks_and_expects_the_matching_waits(self):
        self.leased()
        bare = without_vi_media(self.inv)
        out = self.run_cli('pack', '--topic-id', 'TH-VI-0001', inv=bare)[1]
        self.assertEqual(out['media']['options'], [])
        self.assertEqual(out['expectations']['waits'], ['FEATURED_MEDIA'])
        self.assertTrue(any('FEATURED_MEDIA' in n for n in out['notes']))
        ok = self.run_cli('pack', '--topic-id', 'TH-VI-0001')[1]
        self.assertEqual((ok['expectations']['waits'], ok['expectations']['can_complete_without_waiting']), ([], True))

    def test_a_topic_that_is_only_a_matrix_row_gets_a_planning_pack_without_a_skeleton(self):
        out = self.run_cli('pack', '--topic-id', 'TH-VI-0017')[1]
        self.assertEqual((out['admitted'], out['skeleton'], out['lease']), (False, None, None))
        self.assertEqual(out['topic']['proposed_url'], 'https://rentbikehanoi.com/vi/doc-bang-gia-thue-xe-ghi-tu-tro-len-hoac-lien-he/')
        self.assertEqual([(c['id'], c['source']) for c in out['taxonomy']], [(140, 'inventory'), (146, 'matrix'), (152, 'inventory')])
        self.assertTrue(any('matrix row' in n for n in out['notes']))
        self.assertEqual(out['internal_links']['service_target']['candidates'], [])
        self.assertEqual((out['internal_links']['service_target']['url'], out['internal_links']['service_target']['note']),
                         ('https://rentbikehanoi.com/vi/bang-gia-thue-xe-may-ha-noi/', 'confirmed address'))  # a live page recorded from the adapter inventory
        monthly = self.run_cli('pack', '--topic-id', 'TH-VI-0058')[1]['internal_links']['service_target']
        self.assertEqual((monthly['key'], monthly['url']), ('monthly', None))
        self.assertIn('no dedicated live page', monthly['note'])  # nothing is guessed for a service that has no Vietnamese page

    def test_an_unknown_topic_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'Unknown topic'):
            self.run_cli('pack', '--topic-id', 'TH-VI-9999')

    def test_the_pack_can_be_saved_to_a_file(self):
        self.leased()
        target = Path(self.temp.name) / 'pack.json'
        code, out = self.run_cli('pack', '--topic-id', 'TH-VI-0001', '--out', str(target))
        self.assertEqual(load(target)['topic']['topic_id'], 'TH-VI-0001')


class BuildTests(Cli):
    def build(self, topic, body=None, meta=None, extra=(), inv=None):
        with patch('thuha.writing.git_head', return_value=COMMIT):
            return self.run_cli('build', '--topic-id', topic['topic_id'], '--body', self.write('body.html', body if body is not None else self.body(topic)),
                                '--meta', self.write('meta.json', meta or self.META), '--out', str(Path(self.temp.name) / 'built.json'), *extra, inv=inv)

    def test_build_writes_the_article_from_the_pack_and_runs_the_precheck(self):
        topic, lease = self.leased()
        code, out = self.build(topic)
        article = load(Path(out['article_file']))
        self.assertEqual((article['session'], article['agent_id'], article['source_commit']), ('session-w1', 'writer-w1', COMMIT))
        self.assertEqual((article['language'], article['category_id'], article['canonical'], article['featured_media']), ('vi', 152, topic['proposed_url'], 51))
        self.assertEqual((article['title'], article['focus_keyword']), (topic['proposed_title'], topic['primary_keyword']))
        self.assertEqual(article['sources'], [dict(topic['sources'][0])])
        self.assertEqual([k for k in runtimefields() if k not in article], [])
        self.assertEqual((code, out['status'], out['ready_to_submit']), (0, 'PASS', True))
        self.assertEqual(out['lint'] and [f['severity'] for f in out['lint']], [f['severity'] for f in out['lint']])  # present, whatever they say
        self.assertEqual(self.store.read()['submissions'], {})  # building stores nothing

    def test_build_needs_a_lease_unless_a_session_is_named(self):
        topic = self.candidate(1, 'vi')
        intake(self.store, [topic], self.inv)
        with self.assertRaisesRegex(ValueError, 'No lease'):
            self.build(topic)
        code, out = self.build(topic, extra=('--session', 'session-x', '--agent-id', 'writer-x'))
        self.assertEqual(load(Path(out['article_file']))['session'], 'session-x')

    def test_build_refuses_an_image_that_is_not_a_verified_option_and_never_invents_one(self):
        topic, _ = self.leased()
        with self.assertRaisesRegex(ValueError, 'not one of the verified options'):
            self.build(topic, meta=dict(self.META, featured_media=50))  # English alt text: not an option for a Vietnamese article
        with self.assertRaisesRegex(ValueError, 'not one of the verified options'):
            self.build(topic, meta=dict(self.META, featured_media=99999))

    def test_build_needs_the_two_search_fields_and_nothing_else_is_typed_again(self):
        topic, _ = self.leased()
        with self.assertRaisesRegex(ValueError, 'seo_title'):
            self.build(topic, meta={'meta_description': self.META['meta_description']})
        with self.assertRaisesRegex(ValueError, 'meta_description'):
            self.build(topic, meta={'seo_title': self.META['seo_title']})

    def test_build_leaves_the_image_empty_when_none_exists_and_the_precheck_says_wait(self):
        topic, _ = self.leased()
        code, out = self.build(topic, meta={k: v for k, v in self.META.items() if k != 'featured_media'}, inv=without_vi_media(self.inv))
        self.assertEqual((code, out['data_waits'], out['submit_waiting_for'], out['ready_to_submit']), (3, ['FEATURED_MEDIA'], ['FEATURED_MEDIA'], True))
        self.assertIsNone(load(Path(out['article_file']))['featured_media'])

    def test_a_faulty_body_comes_back_with_where_and_how_to_fix_each_fault(self):
        topic, _ = self.leased()
        code, out = self.build(topic, body=self.body(topic) + '<p>không cần đặt cọc</p>')
        self.assertEqual((code, out['ready_to_submit']), (1, False))
        self.assertIn('UNVERIFIED_BUSINESS_OR_FIRSTHAND_CLAIM', out['content_fails'])
        fix = next(f for f in out['fixes'] if f['code'] == 'UNVERIFIED_BUSINESS_OR_FIRSTHAND_CLAIM')
        self.assertTrue(fix['where'] and fix['fix'])
        self.assertTrue(any('Known faults' in p for p in out['submit_problems']))

    def test_a_lint_finding_that_needs_a_fix_stops_the_exit_code_even_when_qa_would_pass(self):
        topic, _ = self.leased()
        sentence = 'Hãy xác nhận lại giờ nhận xe và giờ trả xe với cửa hàng trước khi chuyển tiền cho bất kỳ ai.'
        code, out = self.build(topic, body=self.body(topic) + '<p>' + sentence + '</p><p>' + sentence + '</p>')
        self.assertTrue(out['would_pass_qa'])
        self.assertEqual((code, out['ready_to_submit']), (1, False))
        self.assertIn('LINT_PADDING', [f['code'] for f in out['lint'] if f['severity'] == 'fix'])


def runtimefields():
    from thuha.runtime import ARTICLE_FIELDS
    return ARTICLE_FIELDS


class PrecheckAdditionsTests(Cli):
    def test_precheck_reports_lint_fixes_and_readiness_beside_the_qa_answer(self):
        topic, lease = self.leased()
        article = self.article_for(topic, lease['session'], lease['agent_id'])
        path = self.write('a.json', article)
        code, out = self.run_cli('precheck', '--topic-id', 'TH-VI-0001', '--file', path)
        self.assertEqual((code, out['status'], out['ready_to_submit'], out['submit_waiting_for'], out['submit_problems']), (0, 'PASS', True, [], []))
        self.assertIsInstance(out['lint'], list)
        self.assertEqual(out['fixes'], [])

    def test_precheck_compares_with_the_other_stored_drafts_of_the_same_language(self):
        first, lease = self.leased(1)
        from thuha.coordinator import submit
        a1 = self.article_for(first, lease['session'], lease['agent_id'])
        submit(self.store, lease['slot'], lease['session'], lease['fence'], a1)
        second, lease2 = self.leased(2)
        twin = dict(self.article_for(second, lease2['session'], lease2['agent_id']), body_html=a1['body_html'])
        code, out = self.run_cli('precheck', '--topic-id', 'TH-VI-0002', '--file', self.write('twin.json', twin))
        found = [f for f in out['lint'] if f['code'] == 'LINT_TEMPLATE_SIMILARITY']
        self.assertEqual([(f['other'], f['severity']) for f in found], [('TH-VI-0001', 'fix')])
        self.assertEqual((code, out['ready_to_submit']), (1, False))
        fresh = self.article_for(second, lease2['session'], lease2['agent_id'])
        self.assertEqual([f for f in self.run_cli('precheck', '--topic-id', 'TH-VI-0002', '--file', self.write('fresh.json', fresh))[1]['lint'] if f['code'] == 'LINT_TEMPLATE_SIMILARITY'], [])

    def test_an_english_draft_is_not_compared_with_vietnamese_ones(self):
        vi, lease = self.leased(1)
        from thuha.coordinator import submit
        submit(self.store, lease['slot'], lease['session'], lease['fence'], self.article_for(vi, lease['session'], lease['agent_id']))
        en = self.candidate(2, 'en')
        intake(self.store, [en], self.inv)
        lease2 = claim(self.store, 'session-e', 'writer-e')
        out = self.run_cli('precheck', '--topic-id', 'TH-EN-0002', '--file', self.write('e.json', self.article_for(en, 'session-e', 'writer-e')))[1]
        self.assertEqual([f for f in out['lint'] if f['code'] == 'LINT_TEMPLATE_SIMILARITY'], [])


class SubmitGuardTests(Cli):
    def submit_args(self, lease, path, *extra):
        return ['submit', '--slot', lease['slot'], '--session', lease['session'], '--fence', lease['fence'], '--file', path, *extra]

    def article(self, topic, lease, **fields):
        return dict(self.article_for(topic, lease['session'], lease['agent_id']), **fields)

    def test_a_clean_draft_is_stored_and_checked_at_once(self):
        topic, lease = self.leased()
        path = self.write('a.json', self.article(topic, lease))
        code, out = self.run_cli(*self.submit_args(lease, path))
        self.assertEqual(code, 0)
        self.assertEqual(out['qa']['status'], 'PASS')
        self.assertEqual(self.store.read()['topics']['TH-VI-0001']['status'], 'READY')

    def test_a_known_fault_is_refused_with_nothing_stored_and_no_repair_spent(self):
        topic, lease = self.leased()
        path = self.write('a.json', self.article(topic, lease, body_html=self.article_for(topic)['body_html'] + '<p>không cần đặt cọc</p>'))
        before = self.store.read()
        code, out = self.run_cli(*self.submit_args(lease, path))
        after = self.store.read()
        self.assertEqual((code, out['status'], out['ledger_writes']), (1, 'NOT_SUBMITTED', 0))
        self.assertEqual((after['version'], after['submissions'], after['qa']), (before['version'], {}, {}))
        self.assertIn('UNVERIFIED_BUSINESS_OR_FIRSTHAND_CLAIM', out['content_fails'])
        self.assertTrue(all(f['where'] and f['fix'] for f in out['fixes']))

    def test_the_writer_may_store_a_faulty_draft_on_purpose_and_it_comes_back_as_a_repair(self):
        topic, lease = self.leased()
        path = self.write('a.json', self.article(topic, lease, body_html=self.article_for(topic)['body_html'] + '<p>không cần đặt cọc</p>'))
        code, out = self.run_cli(*self.submit_args(lease, path, '--allow-faults'))
        self.assertEqual((code, out['qa']['status']), (1, 'FAIL'))
        self.assertEqual(self.store.read()['topics']['TH-VI-0001']['status'], 'NEEDS_REPAIR')

    def test_a_draft_that_waits_for_data_must_say_so_and_auto_says_exactly_what(self):
        topic, lease = self.leased()
        bare = without_vi_media(self.inv)
        path = self.write('a.json', self.article(topic, lease, featured_media=None))
        code, out = self.run_cli(*self.submit_args(lease, path), inv=bare)
        self.assertEqual((code, out['status']), (1, 'NOT_SUBMITTED'))
        self.assertTrue(any('--waiting-for FEATURED_MEDIA' in p for p in out['problems']), out['problems'])
        self.assertEqual(self.store.read()['topics']['TH-VI-0001']['status'], 'CLAIMED')
        code, out = self.run_cli(*self.submit_args(lease, path, '--waiting-for', 'auto'), inv=bare)
        self.assertEqual(code, 0)
        self.assertNotIn('qa', out)
        topic_now = self.store.read()['topics']['TH-VI-0001']
        self.assertEqual((topic_now['status'], topic_now['waiting_for']), ('WAITING_DATA', ['FEATURED_MEDIA']))

    def test_auto_stores_a_complete_draft_as_complete(self):
        topic, lease = self.leased()
        path = self.write('a.json', self.article(topic, lease))
        code, out = self.run_cli(*self.submit_args(lease, path, '--waiting-for', 'auto'))
        self.assertEqual((code, out['qa']['status']), (0, 'PASS'))
        self.assertNotIn('waiting_for', self.store.read()['topics']['TH-VI-0001'])

    def test_a_wait_for_data_that_exists_is_refused_because_someone_must_choose_it(self):
        topic, lease = self.leased()
        path = self.write('a.json', self.article(topic, lease, featured_media=None))
        code, out = self.run_cli(*self.submit_args(lease, path, '--waiting-for', 'FEATURED_MEDIA'))  # an image with Vietnamese alt text exists
        self.assertEqual((code, out['status']), (1, 'NOT_SUBMITTED'))
        self.assertTrue(any('not needed' in p for p in out['problems']))
        self.assertIn('FEATURED_MEDIA_OR_ALT_NOT_VERIFIED', out['content_fails'])

    def test_an_offline_inventory_never_has_to_be_declared(self):
        topic, lease = self.leased()
        old = dict(self.inv, captured_at='2020-01-01T00:00:00+00:00')
        path = self.write('a.json', self.article(topic, lease))
        code, out = self.run_cli(*self.submit_args(lease, path), inv=old)
        self.assertEqual(code, 0)  # AUTHORITATIVE_INVENTORY is not a wait the writer must name; the stale inventory only blocks QA now
        self.assertEqual(out['qa']['status'], 'BLOCKED')
        self.assertEqual(self.store.read()['topics']['TH-VI-0001']['status'], 'DRAFT_READY')

    def test_the_guard_does_not_hide_a_provenance_error_of_the_lease(self):
        topic, lease = self.leased()
        path = self.write('a.json', self.article(topic, lease, agent_id='someone-else'))
        with self.assertRaisesRegex(ValueError, 'provenance'):
            self.run_cli(*self.submit_args(lease, path))


class PickTests(Cli):
    """`claim --topic-id`: an informed override of the order, for a writer that knows which topics it can finish."""

    def seeded(self):
        vi, en = self.distinct(2), self.candidate(1, 'en')
        intake(self.store, [vi, en], self.inv)
        return vi, en

    def test_a_writer_can_pick_a_topic_that_the_order_would_not_give_yet(self):
        self.seeded()
        default = claim(self.store, 'session-d', 'writer-d')
        self.assertEqual(default['topic_id'], 'TH-VI-0002')  # Vietnamese first when nothing is picked
        code, out = self.run_cli('claim', '--session', 'session-p', '--agent-id', 'writer-p', '--topic-id', 'TH-EN-0001')
        self.assertEqual((code, out['topic_id'], out['picked']), (0, 'TH-EN-0001', True))
        event = self.store.read()['events'][-1]
        self.assertEqual((event['action'], event['topic_id'], event['picked']), ('CLAIM', 'TH-EN-0001', True))

    def test_an_ordinary_claim_is_not_marked_as_picked(self):
        self.seeded()
        self.assertNotIn('picked', claim(self.store, 'session-d', 'writer-d'))

    def test_only_a_claimable_unleased_topic_can_be_picked(self):
        self.seeded()
        claim(self.store, 'session-d', 'writer-d')  # leases TH-VI-0002
        for topic in ('TH-VI-0002', 'TH-VI-9999'):
            with self.assertRaisesRegex(ValueError, 'cannot be claimed now'):
                claim(self.store, 'session-p', 'writer-p', pick=topic)
        hold(self.store, 'TH-EN-0001', 'Needs a page that cannot be read here.')
        with self.assertRaisesRegex(ValueError, 'cannot be claimed now'):
            claim(self.store, 'session-p', 'writer-p', pick='TH-EN-0001')

    def test_a_language_at_its_ceiling_cannot_be_picked(self):
        self.seeded()
        with self.assertRaisesRegex(ValueError, 'cannot be claimed now'):
            claim(self.store, 'session-p', 'writer-p', counts={'vi': 0, 'en': 500}, targets={'vi': 500, 'en': 500}, pick='TH-EN-0001')

    def test_a_pick_and_a_revision_are_two_different_requests(self):
        self.seeded()
        with self.assertRaisesRegex(ValueError, 'Choose one'):
            claim(self.store, 'session-p', 'writer-p', revise='TH-VI-0002', pick='TH-VI-0002')


class NextTests(Cli):
    def matrix(self, rows):
        base = {'kind': 'NEW', 'writer_state': 'NEEDS_SOURCE', 'source_requirements': ['first_party_facts'], 'write_order': 1,
                'search_intent': 'một ý định riêng biệt', 'category_id': 152, 'category_path': [140, 152], 'proposed_url': SITE + '/vi/x/'}
        full = [dict(base, **row) for row in rows]
        for lang in ('vi', 'en'):
            Path(self.temp.name, lang + '.json').write_text(json.dumps({'rows': [r for r in full if r['id'].startswith('TH-' + lang.upper())]}), encoding='utf-8')
        return patch('thuha.writing.matrix_path', lambda lang: Path(self.temp.name) / (lang + '.json'))

    def rows(self):
        return [
            {'id': 'TH-VI-0001', 'title': 'Kế hoạch lộ trình nhẹ nhàng số 1 với hướng dẫn thực tế riêng', 'primary_keyword': 'lộ trình nhẹ nhàng số 1', 'write_order': 1},
            {'id': 'TH-VI-0002', 'title': 'Cách chia tiền xăng khi cả nhóm đi nhiều xe', 'primary_keyword': 'chia tiền xăng cả nhóm', 'write_order': 2},
            {'id': 'TH-VI-0060', 'title': 'Điều kiện nhận xe theo quy định', 'primary_keyword': 'điều kiện nhận xe', 'source_requirements': ['official_vn_law'], 'write_order': 2},
            {'id': 'TH-VI-0050', 'title': 'Cách chia tiền xăng khi đi nhóm nhiều xe máy', 'primary_keyword': 'chia tiền xăng đi nhóm', 'write_order': 3},
            {'id': 'TH-VI-0051', 'title': 'Cách chia tiền xăng khi đi nhóm bằng nhiều xe', 'primary_keyword': 'chia tiền xăng đi nhóm', 'write_order': 4},
            {'id': 'TH-VI-0052', 'title': 'Hướng dẫn kiểm tra phanh trước khi nhận xe', 'primary_keyword': 'kiểm tra phanh xe máy thuê', 'source_requirements': ['manufacturer_manual'], 'write_order': 5},
            {'id': 'TH-VI-0053', 'title': 'Hỏi gì về đặt cọc trước khi giữ xe', 'primary_keyword': 'đặt cọc thuê xe', 'source_requirements': ['editorial_only'], 'write_order': 6},
            {'id': 'TH-EN-0001', 'title': 'Quiet route plan number 1 with distinctive practical guidance', 'primary_keyword': 'walk plan 1', 'write_order': 1},
        ]

    def test_next_ranks_what_can_be_written_and_changes_nothing(self):
        self.leased(1)  # TH-VI-0001 is leased, so it is somebody's work now
        topic = self.distinct(2)
        intake(self.store, [topic], self.inv)
        before = self.store.read()
        with self.matrix(self.rows()):
            code, out = self.run_cli('next', '--language', 'vi')
        after = self.store.read()
        self.assertEqual((code, out['ledger_writes'], out['wordpress_writes']), (0, 0, 0))
        self.assertEqual((after['version'], len(after['events'])), (before['version'], len(before['events'])))
        self.assertEqual([(i['topic_id'], i['readiness']) for i in out['start_now']], [('TH-VI-0002', 'START')])  # the leased topic is not offered
        admit = {i['topic_id']: i for i in out['admit_first']}
        self.assertEqual(sorted(admit), ['TH-VI-0050', 'TH-VI-0051', 'TH-VI-0053'])
        self.assertEqual(out['not_writable_here'], {'NEEDS_SOURCE': 2})  # an official-law and a manufacturer page nobody has read
        self.assertEqual(out['held_not_offered'], 0)

    def test_two_rows_that_are_nearly_the_same_title_are_flagged_before_any_writing(self):
        with self.matrix(self.rows()):
            out = self.run_cli('next', '--language', 'vi')[1]
        flagged = {i['topic_id']: i for i in out['admit_first'] if i['readiness'] == 'CHECK_OVERLAP'}
        self.assertTrue({'TH-VI-0050', 'TH-VI-0051'} <= set(flagged), sorted(flagged))  # and the row about the same fuel question
        self.assertNotIn('TH-VI-0053', flagged)  # a different question
        self.assertTrue(all(i['reasons'][0].startswith('close to ') for i in flagged.values()))
        self.assertIn(flagged['TH-VI-0050']['overlap']['with'], ('TH-VI-0051', 'TH-VI-0002'))  # each names the row it is closest to
        order = [i['readiness'] for i in out['admit_first']]
        self.assertEqual(order, sorted(order, key=['ADMIT_FIRST', 'CHECK_OVERLAP'].index))  # flagged ones come last

    def test_a_topic_about_an_unconfirmed_policy_is_marked_so_the_article_asks_instead_of_asserting(self):
        with self.matrix(self.rows()):
            out = self.run_cli('next', '--language', 'vi')[1]
        deposit = next(i for i in out['admit_first'] if i['topic_id'] == 'TH-VI-0053')
        self.assertEqual(deposit['policy_flags'], ['deposit procedure'])
        self.assertTrue(any('never what the policy is' in r for r in deposit['reasons']))

    def test_expected_waits_are_shown_before_a_writer_starts(self):
        with self.matrix(self.rows()):
            out = self.run_cli('next', '--language', 'vi', inv=without_vi_media(self.inv))[1]
        self.assertTrue(out['admit_first'])
        self.assertTrue(all(i['waits_expected'] == ['FEATURED_MEDIA'] for i in out['admit_first']))
        row = next(i for i in out['admit_first'] if i['readiness'] == 'ADMIT_FIRST')
        self.assertTrue(any('not in the ledger' in r for r in row['reasons']))
        with self.matrix(self.rows()):
            ledger = self.run_cli('next', '--language', 'vi', inv=without_vi_media(self.inv))[1]

    def test_a_topic_that_needs_a_page_nobody_has_read_again_is_not_offered_as_writable_here(self):
        topic = self.candidate(1, 'en')  # its saved source is an external page captured as a title and a short excerpt
        intake(self.store, [topic], self.inv)
        with self.matrix([]):
            out = self.run_cli('next', '--language', 'en')[1]
        item = next(i for i in out['start_now'] if i['topic_id'] == 'TH-EN-0001')
        self.assertEqual(item['readiness'], 'READ_SOURCE_FIRST')
        self.assertTrue(any('read the page again' in r for r in item['reasons']))
        stale = dict(self.store.get_document(topic['sources'][0]['document']), checked_at='2020-01-01T00:00:00+00:00')
        self.store.mutate(lambda s: s['topics']['TH-EN-0001']['sources'][0].update(document=self.store.put_document(stale)))
        with self.matrix([]):
            out = self.run_cli('next', '--language', 'en')[1]
        self.assertNotIn('TH-EN-0001', [i['topic_id'] for i in out['start_now']])  # a stale capture is no source at all
        self.assertEqual(out['not_writable_here'], {'NEEDS_SOURCE': 1})

    def test_a_stored_draft_whose_first_party_evidence_is_stale_is_listed_so_it_is_recaptured_before_it_is_submitted_again(self):
        from thuha.coordinator import submit
        stale = {'url': 'repo://config/business-facts.json', 'checked_at': now(), 'http_status': 200, 'response_sha256': 'a' * 64, 'file_sha256': '0' * 64,
                 'capture_method': 'repository-file', 'excerpt': 'x', 'page_title': 'config/business-facts.json'}
        topic, lease = self.leased()
        ref = dict(topic['sources'][0], url=stale['url'], document=self.store.put_document(stale))
        article = dict(self.article_for(topic, lease['session'], lease['agent_id']), sources=[ref], featured_media=None)
        submit(self.store, lease['slot'], lease['session'], lease['fence'], article, waiting_for=['FEATURED_MEDIA'])
        other = self.distinct(2)
        intake(self.store, [other], self.inv)
        lease2 = claim(self.store, 'session-w2', 'writer-w2')
        held_article = dict(self.article_for(other, lease2['session'], lease2['agent_id']), sources=[ref], featured_media=None)
        submit(self.store, lease2['slot'], lease2['session'], lease2['fence'], held_article, waiting_for=['FEATURED_MEDIA'])
        hold(self.store, 'TH-VI-0002', 'Overlaps another row.')
        with self.matrix(self.rows()):
            out = self.run_cli('next', '--language', 'vi')[1]
        self.assertEqual(out['stale_first_party_evidence'], {'needs_recapture': [{'topic_id': 'TH-VI-0001', 'status': 'WAITING_DATA'}], 'held_not_resubmitted': 1})

    def test_a_held_topic_is_never_offered_and_is_counted(self):
        topic = self.distinct(2)
        intake(self.store, [topic], self.inv)
        hold(self.store, 'TH-VI-0002', 'Overlaps another row.')
        with self.matrix(self.rows()):
            out = self.run_cli('next', '--language', 'vi')[1]
        self.assertNotIn('TH-VI-0002', [i['topic_id'] for i in out['start_now'] + out['admit_first']])
        self.assertEqual(out['held_not_offered'], 1)

    def test_vietnamese_comes_before_english_and_the_limit_applies_per_list(self):
        with self.matrix(self.rows()):
            out = self.run_cli('next', '--limit', '1')[1]
        self.assertEqual([i['language'] for i in out['admit_first']], ['vi'])
        with self.matrix(self.rows()):
            both = self.run_cli('next', '--limit', '10')[1]
        languages = [i['language'] for i in both['admit_first']]
        self.assertEqual(languages, sorted(languages, key=['vi', 'en'].index))
        self.assertIn('en', languages)


class LinkCycleTests(Cli):
    """QA fails a link to a page that is not live, so a draft can pass only after the topics it links to are published; drafts that link to each other never can."""
    matrix = NextTests.matrix

    def stored_pair(self, a_links_b=True, b_links_a=True):
        from thuha.coordinator import submit
        a, b = self.candidate(1, 'vi'), self.distinct(2)
        intake(self.store, [a, b], self.inv)
        leases = [claim(self.store, 'session-w1', 'writer-w1'), claim(self.store, 'session-w2', 'writer-w2')]
        link = lambda target: '<p>Xem thêm <a href="%s">bài kế tiếp</a>.</p>' % target['proposed_url']
        for topic, lease, other, wanted in ((a, leases[0], b, a_links_b), (b, leases[1], a, b_links_a)):
            article = self.article_for(topic, lease['session'], lease['agent_id'])
            if wanted:
                article = dict(article, body_html=article['body_html'] + link(other))
            submit(self.store, lease['slot'], lease['session'], lease['fence'], article, waiting_for=['INTERNAL_LINKS'])
        return a, b

    def test_two_drafts_that_link_to_each_other_form_a_cycle(self):
        self.stored_pair()
        graph = writing.link_graph(self.store, self.store.read())
        self.assertEqual(graph['depends_on'], {'TH-VI-0001': ['TH-VI-0002'], 'TH-VI-0002': ['TH-VI-0001']})
        self.assertEqual(graph['cycles'], [['TH-VI-0001', 'TH-VI-0002']])

    def test_a_chain_is_not_a_cycle_because_the_first_draft_can_go_out_first(self):
        self.stored_pair(a_links_b=False)
        graph = writing.link_graph(self.store, self.store.read())
        self.assertEqual((graph['depends_on'], graph['cycles']), ({'TH-VI-0002': ['TH-VI-0001']}, []))

    def test_a_published_topic_is_no_longer_a_dependency(self):
        import copy
        self.stored_pair()
        state = copy.deepcopy(self.store.read())
        state['topics']['TH-VI-0001']['status'] = 'PUBLISHED'  # the page is live now, so a link to it is a live link
        graph = writing.link_graph(self.store, state)
        self.assertEqual((graph['depends_on'], graph['cycles']), ({}, []))

    def test_three_drafts_in_a_ring_are_one_cycle(self):
        edges = {'a': ['b'], 'b': ['c'], 'c': ['a'], 'd': ['a'], 'e': []}
        self.assertEqual(writing._cycles(edges), [['a', 'b', 'c']])  # d depends on the ring but is not in it

    def test_next_lists_the_cycles_among_stored_drafts(self):
        self.stored_pair()
        with self.matrix([]):
            out = self.run_cli('next', '--language', 'vi')[1]
        self.assertEqual(out['planned_link_cycles'], [['TH-VI-0001', 'TH-VI-0002']])

    def test_precheck_names_the_cycle_and_refuses_it_once_the_site_has_live_pages_to_link_to(self):
        a, b = self.stored_pair(b_links_a=False)  # TH-VI-0001 stored with a link to TH-VI-0002
        article = self.article_for(b, 'session-w2', 'writer-w2')
        article = dict(article, body_html=article['body_html'] + '<p>Xem thêm <a href="%s">bài trước</a>.</p>' % a['proposed_url'])
        code, out = self.run_cli('precheck', '--topic-id', 'TH-VI-0002', '--file', self.write('b.json', article))
        self.assertEqual(out['link_cycle'], ['TH-VI-0001', 'TH-VI-0002'])
        cycle = next(f for f in out['lint'] if f['code'] == 'LINT_LINK_CYCLE')
        self.assertEqual((code, cycle['severity'], out['ready_to_submit']), (1, 'fix', False))  # the fixture has live Vietnamese pages, so the wait is no excuse
        self.assertIn('LINT_LINK_CYCLE', ' '.join(out['submit_problems']))

    def test_before_any_page_is_live_a_cycle_is_a_warning_because_the_draft_waits_anyway(self):
        a, b = self.stored_pair(b_links_a=False)
        offline = dict(self.inv, items=[i for i in self.inv['items'] if i['language'] != 'vi'])
        archive = SITE + '/vi/chuyen-muc/gia-thue-va-chi-phi/'
        article = dict(self.article_for(b, 'session-w2', 'writer-w2'),
                       body_html='<h2>Chuẩn bị lộ trình</h2>' + vi_filler('TH-VI-0002') + '<h2>Điểm dừng</h2><p>Xem <a href="%s">chuyên mục</a> và <a href="%s">bài trước</a>.</p>' % (archive, a['proposed_url']))
        code, out = self.run_cli('precheck', '--topic-id', 'TH-VI-0002', '--file', self.write('b.json', article), inv=offline)
        cycle = next(f for f in out['lint'] if f['code'] == 'LINT_LINK_CYCLE')
        self.assertEqual(cycle['severity'], 'consider')
        self.assertIn('INTERNAL_LINKS', out['data_waits'])
        self.assertTrue(out['ready_to_submit'])  # it may be stored waiting; the cycle has to be cut before it is finished

    def test_a_link_to_a_topic_that_is_not_published_yet_is_listed_even_without_a_cycle(self):
        a, b = self.stored_pair(a_links_b=False, b_links_a=False)
        article = dict(self.article_for(b, 'session-w2', 'writer-w2'))
        article['body_html'] += '<p>Xem thêm <a href="%s">bài trước</a>.</p>' % a['proposed_url']
        out = self.run_cli('precheck', '--topic-id', 'TH-VI-0002', '--file', self.write('b.json', article))[1]
        self.assertEqual((out['planned_links'], out['link_cycle']), (['TH-VI-0001'], []))
        self.assertEqual(next(f for f in out['lint'] if f['code'] == 'LINT_PLANNED_LINK')['severity'], 'consider')


if __name__ == '__main__':
    unittest.main()
