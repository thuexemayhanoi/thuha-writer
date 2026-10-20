"""Create-only publisher, durable write-ahead intent, readback and reconciliation."""
import os
import uuid
from .audit import inventory, parse
from .common import ROOT, REPO, SITE, digest, load, now, urlkey
from .coordinator import timestamp
from .quality import evaluate
from .research import collisions
from .store import GitError,GitHub,event


def release_guard(release,store):
    if not store.durable_remote:raise ValueError('Production requires cross-host durable remote CAS')
    if not release.get('enabled') or not release.get('approved') or release.get('paused') or release.get('emergency_stop'):
        raise ValueError('Production publishing is OFF; separate owner go-live approval required')
    if not release.get('approval_ref') or os.environ.get('THUHA_GO_LIVE_APPROVAL')!=release['approval_ref']:
        raise ValueError('Protected environment approval reference missing')
    if not release.get('cross_publisher_coordination_verified'):
        raise ValueError('Other publishers must be coordinated before pilot')
    stage=release.get('stage','pilot')
    if stage=='pilot':
        if release.get('pilot_max_posts')!=2:raise ValueError('Initial pilot is restricted to two intents')
    elif stage=='controlled-scale':
        if (len(store.read()['receipts'])<2 or release.get('expansion_approval_ref')!=release['approval_ref'] or
            not 2<=release.get('approved_capacity',0)<=2000 or not 1<=release.get('maximum_daily_posts',0)<=20):
            raise ValueError('Controlled scale requires two verified pilot receipts and a separately scoped expansion release')
    else:raise ValueError('Unknown release stage')


def verify_security(api):
    branch=api.request('GET','/repos/'+REPO+'/branches/main/protection')
    state_branch=api.request('GET','/repos/'+REPO+'/branches/factory-state/protection')
    environment=api.request('GET','/repos/'+REPO+'/environments/thuha-production')
    reviewers=branch.get('required_pull_request_reviews',{}).get('required_approving_review_count',0)
    rules=environment.get('protection_rules',[])
    checks=branch.get('required_status_checks',{}).get('contexts',[])
    if reviewers<1 or 'quality' not in checks or not any(r.get('type')=='required_reviewers' and r.get('reviewers') for r in rules):
        raise ValueError('Required branch checks/review and environment reviewers are not enforced')
    restrictions=state_branch.get('restrictions',{})
    if not restrictions.get('apps') or state_branch.get('allow_force_pushes',{}).get('enabled'):
        raise ValueError('Factory-state must restrict writes to the trusted automation app and forbid force pushes')
    return {'main_review':True,'quality_check':True,'environment_review':True,'checked_at':now()}


class Publisher:
    def __init__(self,store,client,inv,qa_policy,business,release_loader=None,security=None):
        self.store,self.client,self.inv=store,client,inv
        self.policy,self.business=qa_policy,business
        self.release_loader=release_loader or (lambda:load(ROOT/'config/release.json'))
        self.security=security or (lambda:verify_security(
            GitHub(os.environ['THUHA_GITHUB_SECURITY_TOKEN']) if os.environ.get('THUHA_GITHUB_SECURITY_TOKEN') else store.api))

    def prepare(self,topic_id,live=None):
        s=self.store.read();topic=s['topics'][topic_id];sub=s['submissions'][topic_id]
        if topic['status']!='READY':raise ValueError('Topic is not READY')
        recorded=s['qa'].get(topic_id,{})
        report=self.store.get_document(recorded.get('report_sha',''))
        if report['status']!='PASS' or report['article_sha']!=sub['article_sha'] or report['policy_sha256']!=digest(self.policy):
            raise ValueError('QA evidence/source/policy mismatch')
        article=self.store.get_document(sub['article_sha'])
        review=self.store.get_document(s['reviews'][topic_id]) if topic_id in s.get('reviews',{}) else None
        current=live or self.inv
        qa=evaluate(article,topic,sub,current,self.policy,self.store,review,self.business)
        if qa['status']!='PASS':raise ValueError('Fresh QA failed: '+','.join(qa['hard_fails']))
        if collisions(topic,current,[]):raise ValueError('Live duplicate detected')
        return topic,sub,article,qa

    def dry_run(self):
        s=self.store.read();rows=[]
        for tid,t in s['topics'].items():
            if t['status']!='READY':continue
            try:
                _,sub,_,qa=self.prepare(tid)
                rows.append({'topic_id':tid,'status':'DRY_RUN_READY','article_sha':sub['article_sha'],'score':qa['score']})
            except Exception as exc:rows.append({'topic_id':tid,'status':'BLOCKED','error':str(exc)})
        return {'mode':'dry-run','wordpress_writes':0,'ready':rows,'publishing_enabled':self.release_loader()['enabled']}

    def fresh_inventory(self):
        live=inventory(self.client,check_pages=False)
        if not live['complete']:raise ValueError('Live WordPress inventory is incomplete')
        previous={x['id']:x for x in self.inv['items']}
        for item in live['items']:
            old=previous.get(item['id'])
            if old and old['content_sha256']==item['content_sha256']:
                item['public_check']=old.get('public_check',{})
        return live

    def publish(self,topic_id):
        release=self.release_loader();release_guard(release,self.store)
        if topic_id in self.store.read()['intents']:
            return self.reconcile(topic_id) # Read-only. Never send the POST again.
        self.security();self.client.preflight()
        live=self.fresh_inventory()
        if live['counts']['posts']>=2000:raise ValueError('Website article target reached; reconcile and improve existing content')
        topic,sub,article,qa=self.prepare(topic_id,live)
        marker='<!-- thuha:v4 topic='+topic_id+' sha256='+sub['article_sha']+' -->'
        payload={'status':'publish','slug':topic['proposed_url'].removeprefix(SITE+'/').rstrip('/'),
                 'title':article['title'],'content':article['body_html']+'\n'+marker,
                 'categories':[topic['category_id']],'featured_media':article['featured_media'],
                 'meta':{'_yoast_wpseo_title':article['seo_title'],'_yoast_wpseo_metadesc':article['meta_description'],
                         '_yoast_wpseo_focuskw':article['focus_keyword']}}
        fence=uuid.uuid4().hex
        def reserve(s):
            if any(s['controls'].values()):raise ValueError('Factory is paused')
            if topic_id in s['intents']:raise ValueError('Intent already reserved')
            limit=release['pilot_max_posts'] if release.get('stage','pilot')=='pilot' else release['approved_capacity']
            if len(s['intents'])>=limit:raise ValueError('Approved publication intent budget exhausted')
            today=now()[:10]
            if sum(x['reserved_at'][:10]==today for x in s['intents'].values())>=release.get('maximum_daily_posts',2):
                raise ValueError('Daily publication intent limit reached')
            active=s.get('publisher_lease')
            if active and active['expires_at']>timestamp():raise ValueError('Another publisher owns the lease')
            latest=max((x['reserved_epoch'] for x in s['intents'].values()),default=0)
            if timestamp()-latest<release['minimum_post_interval_seconds']:raise ValueError('Publish rate limit')
            if s['submissions'][topic_id]['article_sha']!=sub['article_sha'] or s['topics'][topic_id]['status']!='READY':
                raise ValueError('Draft changed while preparing publication')
            s['publisher_lease']={'fence':fence,'expires_at':timestamp()+1800}
            s['intents'][topic_id]={'phase':'INTENT','article_sha':sub['article_sha'],'payload_sha':digest(payload),
                 'marker':marker,'reserved_at':now(),'reserved_epoch':timestamp(),'expected_url':topic['proposed_url'],
                 'category_id':topic['category_id'],'agent_id':sub['agent_id'],'session':sub['session'],
                 'commit':os.environ.get('GITHUB_SHA',article.get('source_commit')),'run_id':os.environ.get('GITHUB_RUN_ID'),
                 'approval_ref':release['approval_ref'],'fence':fence}
            s['intents'][topic_id]['preexisting_wp_ids']=[x['id'] for x in live['items']]
            s['topics'][topic_id]['status']='PUBLISHING'
            event(s,'PUBLICATION_INTENT',topic_id=topic_id,payload_sha=digest(payload))
        self.store.mutate(reserve) # This remote commit MUST succeed before POST.
        try:
            release_guard(self.release_loader(),self.store)
            current=self.store.read()
            if any(current['controls'].values()) or current['publisher_lease']['fence']!=fence or current['publisher_lease']['expires_at']<=timestamp():
                raise ValueError('Stopped after durable intent; reconcile required')
            created=self.client.create(payload) # EXACTLY ONE HTTP attempt.
            def record(s):
                s['intents'][topic_id].update(phase='VERIFY_PENDING',wp_id=created['id'])
            self.store.mutate(record)
            return self.reconcile(topic_id)
        except Exception:
            def uncertain(s):
                s['intents'][topic_id]['phase']='NEEDS_RECONCILIATION'
                s['topics'][topic_id]['status']='BLOCKED'
                if s.get('publisher_lease',{}).get('fence')==fence:s.pop('publisher_lease',None)
                event(s,'PUBLISH_OUTCOME_UNCERTAIN',topic_id=topic_id)
            self.store.mutate(uncertain)
            raise

    def reconcile(self,topic_id):
        s=self.store.read();intent=s['intents'][topic_id]
        if topic_id in s['receipts']:
            # Re-check live independently; immutable historical receipt is retained.
            self.verify(topic_id,intent)
            return s['receipts'][topic_id]
        proof=self.verify(topic_id,intent)
        receipt={'topic_id':topic_id,'article_sha':intent['article_sha'],'verified_at':now(),
                 'agent_id':intent['agent_id'],'agent_identity_status':'declared external-session attribution',
                 'session':intent['session'],'source_commit':intent['commit'],'run_id':intent['run_id'],**proof}
        receipt_sha=self.store.put_document(receipt)
        def transaction(s):
            if topic_id in s['receipts']:return s['receipts'][topic_id]
            s['receipts'][topic_id]={'document':receipt_sha,'wp_id':proof['wp_id'],'url':proof['url'],
                 'article_sha':intent['article_sha'],'agent_id':intent['agent_id'],'verified_at':receipt['verified_at']}
            s['intents'][topic_id].update(phase='VERIFIED',wp_id=proof['wp_id'])
            s['topics'][topic_id]['status']='VERIFIED'
            if s.get('publisher_lease',{}).get('fence')==intent['fence']:s.pop('publisher_lease',None)
            event(s,'PUBLICATION_VERIFIED',topic_id=topic_id,receipt_sha=receipt_sha)
            return s['receipts'][topic_id]
        return self.store.mutate(transaction)

    def verify(self,topic_id,intent):
        article=self.store.get_document(intent['article_sha'])
        slug=intent['expected_url'].removeprefix(SITE+'/').rstrip('/')
        posts,_=self.client.get('posts',auth=True,slug=slug,status='any',context='edit',per_page=100)
        if len(posts)!=1:raise ValueError('Unresolved slug; never retry POST')
        p=posts[0]
        if p['id'] in intent.get('preexisting_wp_ids',[]):raise ValueError('Existing protected WordPress ID cannot become a new factory receipt')
        content=p.get('content',{}).get('raw',p.get('content',{}).get('rendered',''))
        if intent['marker'] not in content:raise ValueError('Post lacks exact factory ownership marker')
        if (intent.get('wp_id') and p['id']!=intent['wp_id']) or p.get('status')!='publish' or p.get('link')!=intent['expected_url'] or p.get('slug')!=slug:
            raise ValueError('Post identity/status/URL mismatch')
        if p.get('categories')!=[intent['category_id']] or p.get('featured_media')!=article['featured_media']:
            raise ValueError('Readback taxonomy or featured image mismatch')
        if ' '.join(parse(content).text).split()!=' '.join(parse(article['body_html']).text).split():
            raise ValueError('Readback visible article body mismatch')
        meta=p.get('meta',{})
        if meta.get('_yoast_wpseo_focuskw')!=article['focus_keyword']:raise ValueError('Yoast focus keyword did not persist')
        source,headers,status=self.client.page(p['link']);page=parse(source)
        if status!=200 or page.canonicals!=[p['link']] or page.title!=article['seo_title'] or page.descriptions!=[article['meta_description']]:
            raise ValueError('Public canonical/title/meta readback mismatch')
        if 'noindex' in str(page.robots).lower() or 'noindex' in str(headers.get('X-Robots-Tag',headers.get('x-robots-tag'))).lower():
            raise ValueError('Published page is noindex')
        if page.schema_errors or not set(page.valid_schema_types)&{'Article','BlogPosting'}:
            raise ValueError('Valid article schema absent in rendered page')
        return {'wp_id':p['id'],'url':p['link'],'status':p['status'],'canonical':page.canonicals[0],
                'category_id':intent['category_id'],'seo_title':page.title,'meta_description':page.descriptions[0],
                'public_html_sha256':digest(source.encode()),'http_status':status,'schema_present':True}
