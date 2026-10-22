import copy
import concurrent.futures
import datetime as dt
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from thuha.common import SITE,ROOT,digest,load,now,category_path
from thuha.store import LocalStore,GitStore,GitError,initial,validate
from thuha.coordinator import claim,heartbeat,submit,release,recover
from thuha.research import intake,refill,collisions
from thuha.quality import evaluate,run_qa,REVIEW_CHECKS
from thuha.publisher import Publisher,release_guard,idempotency_key
from thuha.audit import summarize,matrix,Page,counts
from thuha.http import HTTP,WordPress,safe_public_url,NetworkError,ADAPTER_CREATE_URL
from thuha.dashboard import report
from thuha.language import post_url


VI_SENTENCE='Chuẩn bị lộ trình trước khi đi giúp bạn chủ động hơn và tránh những đoạn đường không cần thiết trong thành phố. '
EN_SENTENCE=' '.join('word'+str(i) for i in range(720))


def inventory_fixture():
    items=[
      {'id':1,'url':SITE+'/existing-one/','slug':'existing-one','title':'Existing one','type':'posts','status':'publish','language':'en',
       'canonical':SITE+'/existing-one/','search_intent':'UNREVIEWED','content_signature':['oldone'],'public_check':{'http_status':200}},
      {'id':2,'url':SITE+'/existing-two/','slug':'existing-two','title':'Existing two','type':'posts','status':'publish','language':'en',
       'canonical':SITE+'/existing-two/','search_intent':'UNREVIEWED','content_signature':['oldtwo'],'public_check':{'http_status':200}},
      {'id':3,'url':SITE+'/vi/gioi-thieu-cua-hang/','slug':'gioi-thieu-cua-hang','title':'Giới thiệu cửa hàng','type':'pages','status':'publish','language':'vi',
       'canonical':SITE+'/vi/gioi-thieu-cua-hang/','search_intent':'UNREVIEWED','content_signature':['oldpage'],'public_check':{'http_status':200}},
      {'id':4,'url':SITE+'/vi/bai-viet-co-san/','slug':'bai-viet-co-san','title':'Bài viết có sẵn','type':'posts','status':'publish','language':'vi',
       'canonical':SITE+'/vi/bai-viet-co-san/','search_intent':'UNREVIEWED','content_signature':['oldvi'],'public_check':{'http_status':200}}]
    return {'site':SITE,'schema':'bilingual-1','language_source':'adapter','captured_at':now(),'complete':True,'errors':[],'items':items,
      'categories':[{'id':10,'parent':0,'name':'Blog','slug':'blog','language':'en','link':SITE+'/blog/'},
                    {'id':20,'parent':10,'name':'Travel','slug':'travel','language':'en','link':SITE+'/blog/travel/'},
                    {'id':140,'parent':0,'name':'Cẩm nang','slug':'cam-nang','language':'vi','link':SITE+'/vi/chuyen-muc/cam-nang/'},
                    {'id':152,'parent':140,'name':'Giá thuê và chi phí','slug':'gia-thue-va-chi-phi','language':'vi','link':SITE+'/vi/chuyen-muc/gia-thue-va-chi-phi/'}],
      'media':[{'id':50,'alt_text':'Map of the local route','source_url':SITE+'/image.webp'},
               {'id':51,'alt_text':'Bản đồ tuyến đi trong khu phố cổ Hà Nội','source_url':SITE+'/anh.webp'}],
      'counts':counts(items)}


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=LocalStore(self.temp.name)
        self.policy=load(ROOT/'config/qa.json');self.policy['trusted_reviewers']=['reviewer-qa']
        self.business=load(ROOT/'config/business-facts.json')
        self.inv=inventory_fixture()
        evidence={'url':SITE+'/existing-one/','checked_at':now(),'http_status':200,'response_sha256':'a'*64,'excerpt':'Actual supporting facts for the test.'}
        self.source={'url':evidence['url'],'document':self.store.put_document(evidence),'supports':'Route planning information used in this fictional test fixture.'}

    def candidate(self,i=1,lang='en'):
        review={'verdict':'DISTINCT','inventory_sha256':digest(self.inv),'reviewer_id':'researcher-fixture','language':lang,'rationale':'Independent fixture intent for concurrency testing.'}
        if lang=='vi':
            slug=f'ke-hoach-lo-trinh-nhe-nhang-{i}'
            return {'topic_id':f'TH-VI-{i:04d}','language':'vi','primary_keyword':f'lộ trình nhẹ nhàng số {i}',
              'search_intent':f'kế hoạch lộ trình riêng biệt số {i} cho người mới',
              'proposed_title':f'Kế hoạch lộ trình nhẹ nhàng số {i} với hướng dẫn thực tế riêng',
              'category_id':152,'category_path':[140,152],'cluster':'ke-hoach','proposed_url':post_url('vi',slug),
              'sources':[self.source],'intent_review':review}
        return {'topic_id':f'TH-EN-{i:04d}','language':'en','primary_keyword':f'walk plan {i}','search_intent':f'unique quiet route plan {i}',
          'proposed_title':f'Quiet route plan number {i} with distinctive practical guidance',
          'category_id':20,'category_path':[10,20],'cluster':'hanoi-guides',
          'proposed_url':SITE+f'/quiet-route-plan-{i}/','sources':[self.source],'intent_review':review}

    def article_for(self,topic,session='session-test',agent='writer-fixture'):
        if topic['language']=='vi':
            body=('<h2>Chuẩn bị lộ trình</h2><p>'+VI_SENTENCE*45+'</p><h2>Điểm dừng thực tế</h2><p>Xem thêm <a href="'+SITE+'/vi/gioi-thieu-cua-hang/">giới thiệu cửa hàng</a> và <a href="'
                  +SITE+'/vi/bai-viet-co-san/">bài viết liên quan</a>.</p>')
            return {'topic_id':topic['topic_id'],'session':session,'agent_id':agent,'language':'vi','title':topic['proposed_title'],
              'seo_title':'Kế hoạch lộ trình nhẹ nhàng cho một ngày di chuyển thoải mái','meta_description':'Chuẩn bị lộ trình, điểm dừng thực tế và các liên kết hữu ích trước khi chọn chi tiết cho chuyến đi trong ngày của bạn tại Hà Nội.',
              'focus_keyword':topic['primary_keyword'],'body_html':body,'canonical':topic['proposed_url'],'category_id':152,'featured_media':51,
              'sources':[self.source],'business_claims':[],'source_commit':'a'*40}
        body='<h2>Planning the route</h2><p>'+EN_SENTENCE+'</p><h2>Practical stops</h2><p>See <a href="'+SITE+'/existing-one/">route overview</a> and <a href="'+SITE+'/existing-two/">other route</a>.</p>'
        return {'topic_id':topic['topic_id'],'session':session,'agent_id':agent,'language':'en-US',
          'title':topic['proposed_title'],'seo_title':'A practical quiet route planner for an unhurried Hanoi day',
          'meta_description':'Plan a quiet day with useful route choices, practical stops, walking time and links to related guides before choosing the details of your outing.',
          'focus_keyword':topic['primary_keyword'],'body_html':body,'canonical':topic['proposed_url'],
          'category_id':20,'featured_media':50,'sources':[self.source],'business_claims':[],'source_commit':'a'*40}

    def ready(self,lang='en',i=1,session='session-test',agent='writer-fixture'):
        topic=self.candidate(i,lang);intake(self.store,[topic],self.inv)
        lease=claim(self.store,session,agent)
        article=self.article_for(topic,session,agent)
        receipt=submit(self.store,lease['slot'],lease['session'],lease['fence'],article)
        review={'article_sha':receipt['article_sha'],'reviewer_id':'reviewer-qa','language':lang,'checked_at':now(),
                'checks':{k:True for k in REVIEW_CHECKS},'notes':'Synthetic test review, never production evidence.'}
        review_sha=self.store.put_document(review)
        self.store.mutate(lambda s:s.setdefault('reviews',{}).update({topic['topic_id']:review_sha}))
        qa=run_qa(self.store,topic['topic_id'],self.inv,self.policy,self.business)
        self.assertEqual(qa['status'],'PASS',qa)
        return topic,article,receipt


class CoordinationTests(Fixture):
    def test_nine_slots_and_no_duplicate_claim_under_threads(self):
        # Different titles/intents avoid deliberately conservative title matching.
        def seed(s):
            for i in range(10):s['topics'][f'TH-EN-{i:04d}']={'topic_id':f'TH-EN-{i:04d}','language':'en','status':'PLANNED'}
        self.store.mutate(seed)
        def work(i):
            try:return claim(LocalStore(self.temp.name),f'session-{i}',f'agent-{i}')
            except ValueError:return None
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:leases=list(pool.map(work,range(10)))
        leases=[l for l in leases if l]
        self.assertEqual(len(leases),9);self.assertEqual(len({l['topic_id'] for l in leases}),9)

    def test_expired_fence_cannot_heartbeat_reclaimed_topic(self):
        intake(self.store,[self.candidate()],self.inv)
        old=claim(self.store,'session-old','agent-old',ttl=-1)
        new=claim(self.store,'session-new','agent-new')
        self.assertNotEqual(old['fence'],new['fence'])
        with self.assertRaises(ValueError):heartbeat(self.store,old['slot'],old['session'],old['fence'])

    def test_checkpoint_survives_lease_expiry(self):
        topic,article,sub=self.ready()
        self.assertEqual(self.store.get_document(sub['article_sha']),article)
        self.assertEqual(LocalStore(self.temp.name).read()['submissions'][topic['topic_id']]['article_sha'],sub['article_sha'])

    def test_checkpoint_integrity_detects_tampering(self):
        sha=self.store.put_document({'test':'original'})
        (Path(self.temp.name)/'documents'/(sha+'.json')).write_text('{"test":"changed"}')
        with self.assertRaises(ValueError):self.store.get_document(sha)

    def test_receipt_cannot_be_overwritten(self):
        self.store.mutate(lambda s:s['receipts'].update({'x':{'id':1}}))
        with self.assertRaises(ValueError):self.store.mutate(lambda s:s['receipts'].update({'x':{'id':2}}))

    def test_emergency_stop_blocks_claim(self):
        self.store.mutate(lambda s:s['controls'].update(emergency_stop=True))
        with self.assertRaises(ValueError):claim(self.store,'test-session','test-agent')

    def test_no_free_ai_runtime_is_faked(self):
        value=report(self.store,self.inv,load(ROOT/'config/release.json'))
        self.assertEqual(len(value['slots']),9)
        self.assertTrue(all(x['ai_execution']=='NOT_OBSERVED' for x in value['slots'].values()))
        self.assertEqual(value['factory_verified_receipts'],0)


class ResearchTests(Fixture):
    def test_valid_admission_in_both_languages(self):
        self.assertEqual(intake(self.store,[self.candidate(1,'en')],self.inv),['TH-EN-0001'])
        self.assertEqual(intake(self.store,[self.candidate(1,'vi')],self.inv),['TH-VI-0001'])
    def test_wrong_parent_blocks_intake(self):
        c=self.candidate();c['category_path']=[20]
        with self.assertRaises(ValueError):intake(self.store,[c],self.inv)
    def test_duplicate_canonical_blocks_intake(self):
        c=self.candidate();c['proposed_url']=SITE+'/existing-one/'
        with self.assertRaises(ValueError):intake(self.store,[c],self.inv)
    def test_existing_slug_is_protected_even_with_a_different_permalink_shape(self):
        c=self.candidate();self.inv['items'][0]['slug']='quiet-route-plan-1'
        self.assertEqual(collisions(c,self.inv,[])[0]['reason'],'SLUG')
    def test_slug_is_unique_across_languages(self):
        # EN /existing-one/ and a VI post slugged existing-one share one WordPress slug space.
        c=self.candidate(1,'vi');c['proposed_url']=post_url('vi','existing-one')
        self.assertEqual(collisions(c,self.inv,[])[0]['reason'],'SLUG')
        with self.assertRaises(ValueError):intake(self.store,[c],self.inv)
    def test_title_similarity_never_crosses_languages(self):
        en=self.candidate(1,'en');vi=self.candidate(1,'vi');intake(self.store,[en],self.inv)
        self.assertEqual(collisions(vi,self.inv,self.store.read()['topics'].values()),[])
    def test_incomplete_inventory_blocks_new_topics(self):
        self.inv['complete']=False
        with self.assertRaises(ValueError):intake(self.store,[self.candidate()],self.inv)
    def test_missing_source_snapshot_blocks_intake(self):
        c=self.candidate();c['sources']=[{'document':'b'*64,'url':SITE+'/source/','supports':'a sufficiently specific supporting claim'}]
        with self.assertRaises((OSError,ValueError)):intake(self.store,[c],self.inv)
    def test_batch_failure_does_not_partially_admit(self):
        bad=self.candidate(2);bad['category_id']=999
        with self.assertRaises(ValueError):intake(self.store,[self.candidate(),bad],self.inv)
        self.assertEqual(self.store.read()['topics'],{})
    def test_category_of_the_other_language_is_not_a_substitute(self):
        vi=self.candidate(1,'vi');vi['category_id']=20;vi['category_path']=[10,20]
        with self.assertRaises(ValueError):intake(self.store,[vi],self.inv)
        en=self.candidate(1,'en');en['category_id']=152;en['category_path']=[140,152]
        with self.assertRaises(ValueError):intake(self.store,[en],self.inv)
    def test_url_namespace_must_match_language(self):
        vi=self.candidate(1,'vi');vi['proposed_url']=SITE+'/ke-hoach-lo-trinh-nhe-nhang-1/'
        with self.assertRaises(ValueError):intake(self.store,[vi],self.inv)
    def test_topic_id_must_carry_its_language(self):
        vi=self.candidate(1,'vi');vi['topic_id']='TH-EN-0001'
        with self.assertRaises(ValueError):intake(self.store,[vi],self.inv)
    def test_refill_is_idempotent_request_not_fake_topics_and_asks_vietnamese_first(self):
        a=refill(self.store,self.inv);b=refill(self.store,self.inv)
        self.assertEqual(a,b);self.assertEqual(a['language'],'vi');self.assertEqual(a['maximum_topics'],100)
        self.assertEqual(self.store.read()['topics'],{})
    def test_english_is_requested_only_when_vietnamese_needs_nothing(self):
        self.inv['counts']['posts_by_language']['vi']=500
        self.assertEqual(refill(self.store,self.inv)['language'],'en')
    def test_refill_stops_when_both_languages_hold_their_ceiling(self):
        self.inv['counts']['posts_by_language']={'vi':500,'en':500}
        r=refill(self.store,self.inv);self.assertFalse(r['needed']);self.assertEqual(r['languages']['vi']['reason'],'CAPACITY')
    def test_admission_cannot_exceed_remaining_capacity_of_a_language(self):
        self.inv['counts']['posts_by_language']['en']=499
        intake(self.store,[self.candidate(1,'en')],self.inv)
        with self.assertRaises(ValueError):intake(self.store,[self.candidate(2,'en')],self.inv)
        intake(self.store,[self.candidate(1,'vi')],self.inv) # the other language is unaffected
    def test_public_rest_counts_are_not_trusted_for_quota(self):
        self.inv['language_source']='public-rest-unverified'
        with self.assertRaises(ValueError):refill(self.store,self.inv)


class QualityTests(Fixture):
    def test_article_cannot_inject_head_metadata_or_publisher_marker(self):
        t,a,s=self.ready();a['body_html']+='<meta name="robots" content="noindex"><!-- thuha:v4 forged -->'
        failures=evaluate(a,t,s,self.inv,self.policy,self.store)['hard_fails']
        self.assertIn('UNSAFE_OR_DUPLICATE_SCHEMA_HTML',failures);self.assertIn('RESERVED_PROVENANCE_MARKER',failures)
    def test_qa_cannot_close_another_writers_live_repair_lease(self):
        topic,article,sub=self.ready()
        self.store.mutate(lambda s:s['topics'][topic['topic_id']].update(status='NEEDS_REPAIR'))
        lease=claim(self.store,'repair-session','another-writer')
        with self.assertRaises(ValueError):run_qa(self.store,topic['topic_id'],self.inv,self.policy,self.business)
        self.assertEqual(self.store.read()['leases'][lease['slot']]['fence'],lease['fence'])
    def test_missing_independent_review_is_hard_fail(self):
        t,a,s=self.ready();r=evaluate(a,t,s,self.inv,self.policy,self.store,None,self.business)
        self.assertEqual(r['status'],'FAIL');self.assertIn('INDEPENDENT_SEMANTIC_REVIEW_REQUIRED',r['hard_fails'])
    def test_self_review_rejected(self):
        t,a,s=self.ready();self.policy['trusted_reviewers']=['writer-fixture']
        review={'reviewer_id':'writer-fixture','language':'en','article_sha':digest(a),'checks':{k:True for k in REVIEW_CHECKS},'notes':'fake','checked_at':now()}
        self.assertEqual(evaluate(a,t,s,self.inv,self.policy,self.store,review,self.business)['status'],'FAIL')
    def test_forged_report_does_not_authorize_changed_draft(self):
        t,a,s=self.ready();sha=self.store.read()['qa'][t['topic_id']]['report_sha']
        a['body_html']+='<p>tampered</p>'
        r=evaluate(a,t,s,self.inv,self.policy,self.store)
        self.assertIn('SUBMISSION_HASH_MISMATCH',r['hard_fails'])
        self.assertEqual(self.store.get_document(sha)['article_sha'],s['article_sha'])
    def test_hard_fail_cannot_be_bypassed_by_score_threshold(self):
        t,a,s=self.ready();a['body_html']+='<p>no deposit</p>';self.policy['score_threshold']=0
        r=evaluate(a,t,s,self.inv,self.policy,self.store,None,self.business)
        self.assertEqual(r['status'],'FAIL');self.assertIn('UNVERIFIED_BUSINESS_OR_FIRSTHAND_CLAIM',r['hard_fails'])
    def test_unknown_electric_daily_rate_rejected(self):
        t,a,s=self.ready();a['business_claims']=[{'kind':'reference_price','vehicle':'electric','period':'day','value_vnd':150000}]
        r=evaluate(a,t,s,self.inv,self.policy,self.store,None,self.business)
        self.assertIn('UNAPPROVED_PRICE',r['hard_fails'])
    def test_invalid_internal_link_rejected(self):
        t,a,s=self.ready();a['body_html']+='<a href="/invented/">made-up link</a>'
        self.assertIn('INTERNAL_LINK_NOT_LIVE_VERIFIED',evaluate(a,t,s,self.inv,self.policy,self.store)['hard_fails'])


class FakeAdapter:
    """Stand-in for the companion plugin: same contract, same idempotency, no WordPress."""
    def __init__(self):
        self.posts=[];self.timeout_after_create=False;self.wrong_canonical=False;self.wrong_html_lang=False
        self.drop_vi_marker=False;self.extra_hreflang=False;self.preflight_calls=0
    def preflight(self):self.preflight_calls+=1;return {'contract':'thuha-writer/1'}
    def create(self,payload):
        from thuha.adapter import validate_payload
        validate_payload(payload)
        old=next((p for p in self.posts if p['idempotency_key']==payload['idempotency_key']),None)
        if old:return {'created':False,'idempotent_replay':True,'post':old}
        lang=payload['language']
        post={'id':999,'type':'post','status':'publish','language':lang,'slug':payload['slug'],'link':post_url(lang,payload['slug']),
              'title':payload['title'],'content':payload['content'],'content_raw':payload['content'],'categories':[payload['category_id']],
              'category_languages':[lang],'featured_media':payload['featured_media'],
              'meta':{'_yoast_wpseo_title':payload['seo']['title'],'_yoast_wpseo_metadesc':payload['seo']['description'],'_yoast_wpseo_focuskw':payload['seo']['focus_keyword']},
              'owner':'thuha-writer','idempotency_key':payload['idempotency_key'],'marker_present':True,'incomplete':False,
              'language_markers':{'is_vi':lang=='vi' and not self.drop_vi_marker,'taxonomy_vi':lang=='vi' and not self.drop_vi_marker}}
        self.posts.append(post)
        if self.timeout_after_create:raise NetworkError('Timeout after server accepted POST')
        return {'created':True,'idempotent_replay':False,'post':post}
    def reconcile(self,key):
        post=next((p for p in self.posts if p['idempotency_key']==key),None)
        return {'found':True,'post':post} if post else {'found':False}
    def page(self,url):
        p=self.posts[0];meta=p['meta']
        canonical=SITE+'/wrong/' if self.wrong_canonical else p['link']
        lang='en' if self.wrong_html_lang and p['language']=='vi' else ('vi' if p['language']=='vi' else 'en')
        alt='<link rel="alternate" hreflang="en" href="'+SITE+'/some-english-pair/">' if self.extra_hreflang else ''
        return ('<html lang="'+lang+'"><head><title>'+meta['_yoast_wpseo_title']+'</title><meta name="description" content="'+meta['_yoast_wpseo_metadesc']+'"><link rel="canonical" href="'+canonical+'">'+alt+
                '<script type="application/ld+json">{"@context":"https://schema.org","@type":"Article"}</script></head></html>'),{},200


class PublisherBase(Fixture):
    def publisher(self,lang='en',enabled=('en','vi')):
        topic,article,sub=self.ready(lang)
        self.store.durable_remote=True # Test double for durable CAS; never used against a real site.
        self.release={'approved':True,'enabled':True,'paused':False,'emergency_stop':False,
              'approval_ref':'synthetic-test-only','cross_publisher_coordination_verified':True,
              'pilot_max_posts':2,'minimum_post_interval_seconds':60,'maximum_daily_posts':2,'languages_enabled':list(enabled)}
        self.client=FakeAdapter()
        p=Publisher(self.store,self.client,self.inv,self.policy,self.business,lambda:self.release,lambda:{'test':True})
        p.fresh_inventory=lambda:self.inv
        return p,topic['topic_id']

    def publish(self,p,tid):
        with patch.dict(os.environ,THUHA_GO_LIVE_APPROVAL='synthetic-test-only'):return p.publish(tid)

    def quota_publish(self,lang,live):
        p,tid=self.publisher(lang);self.inv['counts']['posts_by_language'][lang]=live
        return p,tid



class PublisherTests(PublisherBase):
    def test_default_configuration_never_posts(self):
        p,tid=self.publisher();self.release.update(load(ROOT/'config/release.json'))
        with self.assertRaises(ValueError):p.publish(tid)
        self.assertEqual(len(self.client.posts),0)
    def test_no_language_is_enabled_by_default(self):
        self.assertEqual(load(ROOT/'config/release.json')['languages_enabled'],[])
    def test_local_store_cannot_publish(self):
        p,tid=self.publisher();self.store.durable_remote=False
        with patch.dict(os.environ,THUHA_GO_LIVE_APPROVAL='synthetic-test-only'):
            with self.assertRaises(ValueError):p.publish(tid)
        self.assertEqual(self.client.posts,[])
    def test_dry_run_writes_nothing(self):
        p,tid=self.publisher();r=p.dry_run();self.assertEqual(r['wordpress_writes'],0);self.assertEqual(self.client.posts,[])
    def test_complete_publish_and_readback_in_both_languages(self):
        for lang in ('en','vi'):
            with self.subTest(lang=lang):
                self.setUp();p,tid=self.publisher(lang)
                receipt=self.publish(p,tid)
                self.assertEqual(receipt['wp_id'],999);self.assertEqual(receipt['language'],lang)
                self.assertEqual(self.store.read()['intents'][tid]['phase'],'VERIFIED')
                self.assertEqual(self.client.posts[0]['language_markers']['is_vi'],lang=='vi')
    def test_language_not_enabled_in_release_is_refused(self):
        p,tid=self.publisher('vi',enabled=('en',))
        with self.assertRaises(ValueError):self.publish(p,tid)
        self.assertEqual(self.client.posts,[])
    def test_timeout_reconciles_without_second_post(self):
        p,tid=self.publisher('vi');self.client.timeout_after_create=True
        with patch.dict(os.environ,THUHA_GO_LIVE_APPROVAL='synthetic-test-only'):
            with self.assertRaises(NetworkError):p.publish(tid)
            self.assertEqual(self.store.read()['intents'][tid]['phase'],'NEEDS_RECONCILIATION')
            self.assertEqual(self.store.read()['receipts'],{},'an unknown outcome is never a receipt')
            self.assertEqual(p.publish(tid)['wp_id'],999)
        self.assertEqual(len(self.client.posts),1)
    def test_unknown_outcome_without_a_post_stays_unresolved_and_is_never_reposted(self):
        p,tid=self.publisher('vi');original=self.client.create
        def lost(payload):
            raise NetworkError('Connection reset; outcome unknown')
        self.client.create=lost
        with self.assertRaises(NetworkError):self.publish(p,tid)
        self.client.create=original
        with self.assertRaises(ValueError):self.publish(p,tid) # reconcile finds nothing: do not POST again
        self.assertEqual(self.client.posts,[]);self.assertEqual(self.store.read()['receipts'],{})
        self.assertEqual(self.store.read()['intents'][tid]['phase'],'NEEDS_RECONCILIATION')
    def test_readback_drift_does_not_count_verified(self):
        for knob,attr in (('canonical','wrong_canonical'),('html lang','wrong_html_lang'),('foreign hreflang pair','extra_hreflang'),('vi marker','drop_vi_marker')):
            with self.subTest(knob):
                self.setUp();p,tid=self.publisher('vi');setattr(self.client,attr,True)
                with self.assertRaises(ValueError):self.publish(p,tid)
                self.assertEqual(self.store.read()['receipts'],{});self.assertEqual(len(self.client.posts),1)
    def test_failed_durable_intent_prevents_post(self):
        p,tid=self.publisher();original=self.store.mutate
        def fail(callback):
            if callback.__name__=='reserve':raise OSError('Remote state write failed')
            return original(callback)
        self.store.mutate=fail
        with patch.dict(os.environ,THUHA_GO_LIVE_APPROVAL='synthetic-test-only'):
            with self.assertRaises(OSError):p.publish(tid)
        self.assertEqual(self.client.posts,[])
    def test_emergency_stop_is_checked_before_post(self):
        p,tid=self.publisher();self.store.mutate(lambda s:s['controls'].update(emergency_stop=True))
        with patch.dict(os.environ,THUHA_GO_LIVE_APPROVAL='synthetic-test-only'):
            with self.assertRaises(ValueError):p.publish(tid)
        self.assertEqual(self.client.posts,[])
    def test_legacy_wordpress_id_is_never_counted_as_new_factory_post(self):
        p,tid=self.publisher();original=self.client.create
        def wrong_id(payload):
            result=original(payload);result['post']['id']=1;return result
        self.client.create=wrong_id
        with self.assertRaises(ValueError):self.publish(p,tid)
        self.assertEqual(self.store.read()['receipts'],{})
    def test_scale_cannot_skip_verified_pilot(self):
        p,tid=self.publisher();self.release.update(stage='controlled-scale',approved_capacity=1000,maximum_daily_posts=10,expansion_approval_ref='synthetic-test-only')
        with self.assertRaises(ValueError):self.publish(p,tid)
        self.assertEqual(self.client.posts,[])
    def test_payload_is_the_closed_adapter_contract_with_a_stable_key(self):
        p,tid=self.publisher('vi');self.publish(p,tid)
        sent=self.client.posts[0];intent=self.store.read()['intents'][tid]
        self.assertEqual(sent['idempotency_key'],intent['idempotency_key'])
        self.assertEqual(intent['idempotency_key'],idempotency_key(tid,intent['article_sha']))
        self.assertIn(intent['marker'],sent['content'])

    def test_quota_allows_the_500th_post_and_blocks_the_501st(self):
        for lang in ('vi','en'):
            with self.subTest(lang=lang):
                self.setUp();p,tid=self.quota_publish(lang,499)
                self.assertEqual(self.publish(p,tid)['language'],lang)
                self.setUp();p,tid=self.quota_publish(lang,500)
                with self.assertRaises(ValueError):self.publish(p,tid)
                self.assertEqual(self.client.posts,[]);self.assertEqual(self.store.read()['intents'],{})
    def test_unresolved_intent_counts_against_the_ceiling(self):
        p,tid=self.quota_publish('vi',499)
        self.client.timeout_after_create=True
        with patch.dict(os.environ,THUHA_GO_LIVE_APPROVAL='synthetic-test-only'):
            with self.assertRaises(NetworkError):p.publish(tid)
        self.assertEqual(self.store.read()['intents'][tid]['phase'],'NEEDS_RECONCILIATION')
        # A second Vietnamese post must not slip in as number 501 while the first outcome is unknown.
        from thuha.quota import reserve,status,LanguageComplete
        state=self.store.read();targets={'vi':500,'en':500}
        row=status(state,{'vi':499,'en':2},targets)['vi']
        self.assertEqual((row['unresolved_intents'],row['remaining'],row['complete']),(1,0,True))
        with self.assertRaises(LanguageComplete):reserve(state,{'vi':499,'en':2},targets,'vi','TH-VI-0002')
        reserve(state,{'vi':499,'en':2},targets,'en','TH-EN-0002') # English has its own ceiling


class HTTPAndAuditTests(unittest.TestCase):
    def test_schema_marker_alone_is_not_valid_schema(self):
        p=Page();p.feed('<script type="application/ld+json">{}</script>')
        self.assertEqual(p.schema_errors,1);self.assertEqual(p.valid_schema_types,[])
    def test_readonly_transport_rejects_post(self):
        with self.assertRaises(ValueError):HTTP().request(SITE+'/wp-json/wp/v2/posts',method='POST',body={})
    def test_arbitrary_put_or_delete_rejected(self):
        for method in ('PUT','DELETE'):
            with self.assertRaises(ValueError):HTTP(allow_write=True).request(SITE+'/wp-json/wp/v2/posts/1',method=method)
    def test_private_source_address_rejected(self):
        with self.assertRaises(ValueError):safe_public_url('https://127.0.0.1/private')
    def test_missing_pagination_headers_is_not_complete(self):
        class Client(WordPress):
            def get(self,*a,**kw):return [],{}
        with self.assertRaises(NetworkError):Client().collection('posts')
    def test_changed_collection_count_rejected(self):
        class Client(WordPress):
            def get(self,*a,**kw):return [{'id':1}],{'X-WP-Total':'1' if kw['per_page']==100 else '2','X-WP-TotalPages':'1'}
        with self.assertRaises(NetworkError):Client().collection('posts')
    def test_missing_focus_keyword_is_unknown_not_invented(self):
        r=summarize({'id':1,'link':SITE+'/x/','slug':'x','status':'publish','content':{'rendered':'<p>Text</p>'}},'posts')
        self.assertEqual(r['focus_keyword_visibility'],'UNKNOWN');self.assertIsNone(r['focus_keyword'])
    def test_taxonomy_cycle_is_rejected(self):
        with self.assertRaises(ValueError):category_path(1,[{'id':1,'parent':2},{'id':2,'parent':1}])


if __name__=='__main__':unittest.main()
