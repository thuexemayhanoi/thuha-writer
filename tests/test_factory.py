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
from thuha.publisher import Publisher,release_guard
from thuha.audit import summarize,matrix,Page
from thuha.http import HTTP,WordPress,safe_public_url,NetworkError
from thuha.dashboard import report


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=LocalStore(self.temp.name)
        self.policy=load(ROOT/'config/qa.json');self.policy['trusted_reviewers']=['reviewer-qa']
        self.business=load(ROOT/'config/business-facts.json')
        self.inv={'site':SITE,'captured_at':now(),'complete':True,'errors':[],
          'items':[{'id':1,'url':SITE+'/existing-one/','slug':'existing-one','title':'Existing one','type':'posts',
             'canonical':SITE+'/existing-one/','search_intent':'UNREVIEWED','content_signature':['oldone'],
             'public_check':{'http_status':200}},
             {'id':2,'url':SITE+'/existing-two/','slug':'existing-two','title':'Existing two','type':'posts',
              'canonical':SITE+'/existing-two/','search_intent':'UNREVIEWED','content_signature':['oldtwo'],
              'public_check':{'http_status':200}}],
          'categories':[{'id':10,'parent':0,'name':'Blog','slug':'blog'},{'id':20,'parent':10,'name':'Travel','slug':'travel'}],
          'media':[{'id':50,'alt_text':'Map of the local route','source_url':SITE+'/image.webp'}],
          'counts':{'posts':2,'pages':0,'live_verified_posts':2}}
        evidence={'url':SITE+'/existing-one/','checked_at':now(),'http_status':200,'response_sha256':'a'*64,'excerpt':'Actual supporting facts for the test.'}
        self.source={'url':evidence['url'],'document':self.store.put_document(evidence),'supports':'Route planning information used in this fictional test fixture.'}

    def candidate(self,i=1):
        return {'topic_id':f'TH-{i:06d}','primary_keyword':f'walk plan {i}','search_intent':f'unique quiet route plan {i}',
          'proposed_title':f'Quiet route plan number {i} with distinctive practical guidance',
          'category_id':20,'category_path':[10,20],'cluster':'hanoi-guides',
          'proposed_url':SITE+f'/quiet-route-plan-{i}/','sources':[self.source],
          'intent_review':{'verdict':'DISTINCT','inventory_sha256':digest(self.inv),'reviewer_id':'researcher-fixture','rationale':'Independent fixture intent for concurrency testing.'}}

    def ready(self):
        topic=self.candidate();intake(self.store,[topic],self.inv)
        lease=claim(self.store,'session-test','writer-fixture')
        body='<h2>Planning the route</h2><p>'+' '.join('word'+str(i) for i in range(720))+'</p><h2>Practical stops</h2><p>See <a href="'+SITE+'/existing-one/">route overview</a> and <a href="'+SITE+'/existing-two/">other route</a>.</p>'
        article={'topic_id':topic['topic_id'],'session':'session-test','agent_id':'writer-fixture','language':'en-US',
          'title':topic['proposed_title'],'seo_title':'A practical quiet route planner for an unhurried Hanoi day',
          'meta_description':'Plan a quiet day with useful route choices, practical stops, walking time and links to related guides before choosing the details of your outing.',
          'focus_keyword':topic['primary_keyword'],'body_html':body,'canonical':topic['proposed_url'],
          'category_id':20,'featured_media':50,'sources':[self.source],'business_claims':[],'source_commit':'a'*40}
        receipt=submit(self.store,lease['slot'],lease['session'],lease['fence'],article)
        review={'article_sha':receipt['article_sha'],'reviewer_id':'reviewer-qa','checked_at':now(),
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
            for i in range(10):s['topics'][f'TH-{i:06d}']={'topic_id':f'TH-{i:06d}','status':'PLANNED'}
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
    def test_valid_admission(self):self.assertEqual(intake(self.store,[self.candidate()],self.inv),['TH-000001'])
    def test_wrong_parent_blocks_intake(self):
        c=self.candidate();c['category_path']=[20]
        with self.assertRaises(ValueError):intake(self.store,[c],self.inv)
    def test_duplicate_canonical_blocks_intake(self):
        c=self.candidate();c['proposed_url']=SITE+'/existing-one/'
        with self.assertRaises(ValueError):intake(self.store,[c],self.inv)
    def test_existing_slug_is_protected_even_with_a_different_permalink_shape(self):
        c=self.candidate();self.inv['items'][0]['slug']='quiet-route-plan-1'
        self.assertEqual(collisions(c,self.inv,[])[0]['reason'],'SLUG')
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
    def test_refill_is_idempotent_request_not_fake_topics(self):
        a=refill(self.store,self.inv);b=refill(self.store,self.inv)
        self.assertEqual(a,b);self.assertEqual(a['maximum_topics'],100)
        self.assertEqual(self.store.read()['topics'],{})
    def test_refill_stops_at_existing_website_target(self):
        self.inv['counts']['posts']=2000
        self.assertEqual(refill(self.store,self.inv)['reason'],'CAPACITY')


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
        review={'reviewer_id':'writer-fixture','article_sha':digest(a),'checks':{k:True for k in REVIEW_CHECKS},'notes':'fake','checked_at':now()}
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


class FakeWordPress:
    def __init__(self):self.created=[];self.timeout_after_create=False;self.wrong_canonical=False
    def preflight(self):return {'ok':True}
    def create(self,payload):
        p={**copy.deepcopy(payload),'id':999,'link':SITE+'/'+payload['slug']+'/',
           'content':{'raw':payload['content']},'meta':payload['meta']}
        self.created.append(p)
        if self.timeout_after_create:raise NetworkError('Timeout after server accepted POST')
        return p
    def get(self,resource,**kwargs):return list(self.created),{}
    def page(self,url):
        p=self.created[0];meta=p['meta']
        canonical=SITE+'/wrong/' if self.wrong_canonical else p['link']
        return '<title>'+meta['_yoast_wpseo_title']+'</title><meta name="description" content="'+meta['_yoast_wpseo_metadesc']+'"><link rel="canonical" href="'+canonical+'"><script type="application/ld+json">{"@context":"https://schema.org","@type":"Article"}</script>',{},200


class PublisherTests(Fixture):
    def publisher(self):
        topic,article,sub=self.ready()
        self.store.durable_remote=True # Test double for durable CAS; never used against a real site.
        self.release={'approved':True,'enabled':True,'paused':False,'emergency_stop':False,
              'approval_ref':'synthetic-test-only','cross_publisher_coordination_verified':True,
              'pilot_max_posts':2,'minimum_post_interval_seconds':60}
        self.client=FakeWordPress()
        p=Publisher(self.store,self.client,self.inv,self.policy,self.business,lambda:self.release,lambda:{'test':True})
        p.fresh_inventory=lambda:self.inv
        return p,topic['topic_id']

    def test_default_configuration_never_posts(self):
        p,tid=self.publisher();self.release.update(load(ROOT/'config/release.json'))
        with self.assertRaises(ValueError):p.publish(tid)
        self.assertEqual(len(self.client.created),0)
    def test_local_store_cannot_publish(self):
        p,tid=self.publisher();self.store.durable_remote=False
        with patch.dict(os.environ,THUHA_GO_LIVE_APPROVAL='synthetic-test-only'):
            with self.assertRaises(ValueError):p.publish(tid)
        self.assertEqual(self.client.created,[])
    def test_dry_run_writes_nothing(self):
        p,tid=self.publisher();r=p.dry_run();self.assertEqual(r['wordpress_writes'],0);self.assertEqual(self.client.created,[])
    def test_complete_publish_and_readback(self):
        p,tid=self.publisher()
        with patch.dict(os.environ,THUHA_GO_LIVE_APPROVAL='synthetic-test-only'):receipt=p.publish(tid)
        self.assertEqual(receipt['wp_id'],999);self.assertEqual(self.store.read()['intents'][tid]['phase'],'VERIFIED')
    def test_timeout_reconciles_without_second_post(self):
        p,tid=self.publisher();self.client.timeout_after_create=True
        with patch.dict(os.environ,THUHA_GO_LIVE_APPROVAL='synthetic-test-only'):
            with self.assertRaises(NetworkError):p.publish(tid)
            self.assertEqual(self.store.read()['intents'][tid]['phase'],'NEEDS_RECONCILIATION')
            self.assertEqual(p.publish(tid)['wp_id'],999)
        self.assertEqual(len(self.client.created),1)
    def test_readback_drift_does_not_count_verified(self):
        p,tid=self.publisher();self.client.wrong_canonical=True
        with patch.dict(os.environ,THUHA_GO_LIVE_APPROVAL='synthetic-test-only'):
            with self.assertRaises(ValueError):p.publish(tid)
        self.assertEqual(self.store.read()['receipts'],{});self.assertEqual(len(self.client.created),1)
    def test_failed_durable_intent_prevents_post(self):
        p,tid=self.publisher();original=self.store.mutate
        def fail(callback):
            if callback.__name__=='reserve':raise OSError('Remote state write failed')
            return original(callback)
        self.store.mutate=fail
        with patch.dict(os.environ,THUHA_GO_LIVE_APPROVAL='synthetic-test-only'):
            with self.assertRaises(OSError):p.publish(tid)
        self.assertEqual(self.client.created,[])
    def test_emergency_stop_is_checked_before_post(self):
        p,tid=self.publisher();self.store.mutate(lambda s:s['controls'].update(emergency_stop=True))
        with patch.dict(os.environ,THUHA_GO_LIVE_APPROVAL='synthetic-test-only'):
            with self.assertRaises(ValueError):p.publish(tid)
        self.assertEqual(self.client.created,[])

    def test_legacy_wordpress_id_is_never_counted_as_new_factory_post(self):
        p,tid=self.publisher();original=self.client.create
        def wrong_id(payload):
            post=original(payload);post['id']=1;return post
        self.client.create=wrong_id
        with patch.dict(os.environ,THUHA_GO_LIVE_APPROVAL='synthetic-test-only'):
            with self.assertRaises(ValueError):p.publish(tid)
        self.assertEqual(self.store.read()['receipts'],{})
    def test_scale_cannot_skip_verified_pilot(self):
        p,tid=self.publisher();self.release.update(stage='controlled-scale',approved_capacity=2000,maximum_daily_posts=10,expansion_approval_ref='synthetic-test-only')
        with patch.dict(os.environ,THUHA_GO_LIVE_APPROVAL='synthetic-test-only'):
            with self.assertRaises(ValueError):p.publish(tid)
        self.assertEqual(self.client.created,[])


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
