"""Create-only bilingual publisher: durable write-ahead intent, adapter write, readback, reconciliation.

All writes go through the companion adapter (src/thuha/adapter.py). A post is
created as a draft that already carries the ownership/idempotency marker, receives
its language marker and SEO fields, and is only then published, so it never exists
at an English URL first. An unknown outcome is reconciled by idempotency key; the
POST is never sent twice and a draft or unknown intent is never counted as a post.
"""
import os
import uuid
from .adapter import NOT_DEPLOYED, build_payload, validate_payload
from .policy import DEFINITIVE_REJECTIONS
from .http import NetworkError
from .audit import inventory_bilingual, parse
from .common import ROOT, REPO, SITE, digest, load, now, urlkey
from .coordinator import timestamp
from .language import SPEC, html_lang_matches, split_url, targets as language_targets, url_language
from .quality import evaluate
from . import quota
from .quota import CLOSED_PHASES
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
    if not release.get('languages_enabled'):
        raise ValueError('No language is enabled in the approved release')
    stage=release.get('stage','pilot')
    if stage=='pilot':
        if release.get('pilot_max_posts')!=2:raise ValueError('Initial pilot is restricted to two intents')
    elif stage=='controlled-scale':
        ceiling=sum(language_targets().values())
        if (len(store.read()['receipts'])<2 or release.get('expansion_approval_ref')!=release['approval_ref'] or
            not 2<=release.get('approved_capacity',0)<=ceiling or not 1<=release.get('maximum_daily_posts',0)<=20):
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


def idempotency_key(topic_id,article_sha):
    return digest({'topic_id':topic_id,'article_sha':article_sha})


class Publisher:
    def __init__(self,store,client,inv,qa_policy,business,release_loader=None,security=None,targets=None):
        self.store,self.client,self.inv=store,client,inv
        self.policy,self.business=qa_policy,business
        self.targets=targets or language_targets()
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
        for tid,t in sorted(s['topics'].items(),key=lambda kv:(language_order(kv[1]),kv[0])):
            if t['status']!='READY':continue
            try:
                _,sub,_,qa=self.prepare(tid)
                rows.append({'topic_id':tid,'language':t['language'],'status':'DRY_RUN_READY','article_sha':sub['article_sha'],'score':qa['score']})
            except Exception as exc:rows.append({'topic_id':tid,'language':t['language'],'status':'BLOCKED','error':str(exc)})
        return {'mode':'dry-run','wordpress_writes':0,'ready':rows,'publishing_enabled':self.release_loader()['enabled']}

    def fresh_inventory(self):
        live=inventory_bilingual(self.client,check_pages=False)
        if not live['complete']:raise ValueError('Live WordPress inventory is incomplete')
        previous={x['id']:x for x in self.inv['items']}
        for item in live['items']:
            old=previous.get(item['id'])
            if old and old.get('content_sha256')==item['content_sha256']:
                item['public_check']=old.get('public_check',{})
        return live

    def publish(self,topic_id):
        release=self.release_loader();release_guard(release,self.store)
        state=self.store.read();lang=state['topics'][topic_id]['language']
        if lang not in release['languages_enabled']:raise ValueError('Language '+lang+' is not enabled in the approved release')
        prior=state['intents'].get(topic_id)
        if prior and prior['phase'] not in CLOSED_PHASES:
            return self.reconcile(topic_id) # Read-only. Never send the POST again.
        if self.inv.get('language_source')!='adapter':
            raise ValueError('The stored inventory is not an adapter inventory; run `audit` with adapter credentials before publishing')
        self.security();self.client.preflight() # BLOCKED_ADAPTER_NOT_DEPLOYED until the plugin answers
        live=self.fresh_inventory()
        if live.get('language_source')!='adapter':raise ValueError('Publishing needs an adapter inventory of both languages')
        counts=quota.published(live);live_ids={x['id'] for x in live['items']}
        if counts[lang]>=self.targets[lang]:raise quota.LanguageComplete('Language target reached: '+lang+'; reconcile and improve existing content')
        topic,sub,article,qa=self.prepare(topic_id,live)
        marker='<!-- thuha:v5 topic='+topic_id+' sha256='+sub['article_sha']+' -->'
        slug=split_url(topic['proposed_url'])[1]
        key=idempotency_key(topic_id,sub['article_sha'])
        payload=build_payload(topic,article,key,marker,slug)
        validate_payload(payload) # a payload the plugin would refuse must fail BEFORE it costs a publication slot
        fence=uuid.uuid4().hex
        def reserve(s):
            if any(s['controls'].values()):raise ValueError('Factory is paused')
            old=s['intents'].get(topic_id)
            if old and old['phase'] not in CLOSED_PHASES:raise ValueError('Intent already reserved')
            quota.reserve(s,counts,self.targets,lang,topic_id,live_ids) # 499 -> 500 passes, 500 -> 501 never
            active=quota.active_intents(s)
            active.pop(topic_id,None)
            limit=release['pilot_max_posts'] if release.get('stage','pilot')=='pilot' else release['approved_capacity']
            if len(active)>=limit:raise ValueError('Approved publication intent budget exhausted')
            today=now()[:10]
            if sum(x['reserved_at'][:10]==today for x in active.values())>=release.get('maximum_daily_posts',2):
                raise ValueError('Daily publication intent limit reached')
            lease=s.get('publisher_lease')
            if lease and lease['expires_at']>timestamp():raise ValueError('Another publisher owns the lease')
            latest=max((x['reserved_epoch'] for x in active.values()),default=0)
            if timestamp()-latest<release['minimum_post_interval_seconds']:raise ValueError('Publish rate limit')
            if s['submissions'][topic_id]['article_sha']!=sub['article_sha'] or s['topics'][topic_id]['status']!='READY':
                raise ValueError('Draft changed while preparing publication')
            s['publisher_lease']={'fence':fence,'expires_at':timestamp()+1800}
            s['intents'][topic_id]={'phase':'INTENT','language':lang,'article_sha':sub['article_sha'],'payload_sha':digest(payload),
                 'idempotency_key':key,'marker':marker,'reserved_at':now(),'reserved_epoch':timestamp(),
                 'expected_url':topic['proposed_url'],'category_id':topic['category_id'],'agent_id':sub['agent_id'],
                 'session':sub['session'],'commit':os.environ.get('GITHUB_SHA',article.get('source_commit')),
                 'run_id':os.environ.get('GITHUB_RUN_ID'),'approval_ref':release['approval_ref'],'fence':fence,
                 'live_counts_at_reservation':dict(counts)}
            s['intents'][topic_id]['preexisting_wp_ids']=sorted(live_ids)
            s['topics'][topic_id]['status']='PUBLISHING'
            event(s,'PUBLICATION_INTENT',topic_id=topic_id,language=lang,payload_sha=digest(payload))
        self.store.mutate(reserve) # This remote commit MUST succeed before POST.
        sent=False
        try:
            release_guard(self.release_loader(),self.store)
            current=self.store.read()
            if any(current['controls'].values()) or current['publisher_lease']['fence']!=fence or current['publisher_lease']['expires_at']<=timestamp():
                raise ValueError('Stopped after durable intent; reconcile required')
            sent=True # from here on the outcome of the POST can be unknown
            created=self.client.create(payload) # EXACTLY ONE HTTP attempt.
            def record(s):
                s['intents'][topic_id].update(phase='VERIFY_PENDING',wp_id=created['post']['id'])
            self.store.mutate(record)
            return self.reconcile(topic_id)
        except Exception as exc:
            closing=None
            if not sent:
                closing=('NOT_SENT',None)
            elif isinstance(exc,NetworkError) and exc.code in DEFINITIVE_REJECTIONS:
                try: # An authoritative refusal from the plugin; only a read-back proving nothing exists closes the intent.
                    if not self.client.reconcile(key).get('found'):closing=('REJECTED',exc.code)
                except Exception:closing=None
            def settle(s):
                intent=s['intents'][topic_id]
                if intent['phase']=='VERIFIED':return # a lost response must never undo a recorded verification
                if s.get('publisher_lease',{}).get('fence')==fence:s.pop('publisher_lease',None)
                if closing:
                    intent['phase']=closing[0];intent['closed_reason']=closing[1] or str(exc)[:200]
                    s['topics'][topic_id]['status']='READY' if closing[0]=='NOT_SENT' else 'NEEDS_REPAIR'
                    event(s,'PUBLICATION_INTENT_CLOSED',topic_id=topic_id,phase=closing[0])
                else:
                    intent['phase']='NEEDS_RECONCILIATION';s['topics'][topic_id]['status']='BLOCKED'
                    event(s,'PUBLISH_OUTCOME_UNCERTAIN',topic_id=topic_id)
            self.store.mutate(settle)
            raise

    def reconcile(self,topic_id):
        s=self.store.read();intent=s['intents'][topic_id]
        if topic_id in s['receipts']:
            # Re-check live independently; immutable historical receipt is retained.
            self.verify(topic_id,intent)
            return s['receipts'][topic_id]
        proof=self.verify(topic_id,intent)
        receipt={'topic_id':topic_id,'language':intent['language'],'article_sha':intent['article_sha'],'verified_at':now(),
                 'agent_id':intent['agent_id'],'agent_identity_status':'declared external-session attribution',
                 'session':intent['session'],'source_commit':intent['commit'],'run_id':intent['run_id'],**proof}
        receipt_sha=self.store.put_document(receipt)
        def transaction(s):
            if topic_id in s['receipts']:return s['receipts'][topic_id]
            s['receipts'][topic_id]={'document':receipt_sha,'language':intent['language'],'wp_id':proof['wp_id'],'url':proof['url'],
                 'article_sha':intent['article_sha'],'agent_id':intent['agent_id'],'verified_at':receipt['verified_at']}
            s['intents'][topic_id].update(phase='VERIFIED',wp_id=proof['wp_id'])
            s['topics'][topic_id]['status']='VERIFIED'
            if s.get('publisher_lease',{}).get('fence')==intent['fence']:s.pop('publisher_lease',None)
            event(s,'PUBLICATION_VERIFIED',topic_id=topic_id,language=intent['language'],receipt_sha=receipt_sha)
            return s['receipts'][topic_id]
        return self.store.mutate(transaction)

    def verify(self,topic_id,intent):
        """Prove from the adapter readback AND the public page; anything less leaves the intent unresolved."""
        lang=intent['language']
        article=self.store.get_document(intent['article_sha'])
        found=self.client.reconcile(intent['idempotency_key'])
        if not found.get('found'):raise ValueError('No post carries the idempotency key; never retry POST')
        p=found['post']
        slug=split_url(intent['expected_url'])[1]
        if p['id'] in intent.get('preexisting_wp_ids',[]):raise ValueError('Existing protected WordPress ID cannot become a new factory receipt')
        if p.get('owner')!='thuha-writer' or p.get('idempotency_key')!=intent['idempotency_key']:
            raise ValueError('Post is not owned by this factory intent')
        content=p.get('content_raw','')
        if intent['marker'] not in content or not p.get('marker_present'):raise ValueError('Post lacks exact factory ownership marker')
        if (intent.get('wp_id') and p['id']!=intent['wp_id']) or p.get('status')!='publish' or p.get('link')!=intent['expected_url'] or p.get('slug')!=slug:
            raise ValueError('Post identity/status/URL mismatch')
        if p.get('language')!=lang:raise ValueError('Post is registered as '+str(p.get('language'))+', expected '+lang)
        marks=p.get('language_markers',{})
        if marks.get('taxonomy_vi')!=(lang=='vi') or marks.get('is_vi')!=(lang=='vi'):
            raise ValueError('Native Vietnamese marker does not match the language (a VI category alone is not enough)')
        if p.get('categories')!=[intent['category_id']] or p.get('featured_media')!=article['featured_media']:
            raise ValueError('Readback taxonomy or featured image mismatch')
        if p.get('category_languages')!=[lang]:raise ValueError('Category language mismatch on readback')
        if ' '.join(parse(content).text).split()!=' '.join(parse(article['body_html']).text).split():
            raise ValueError('Readback visible article body mismatch')
        if p.get('title')!=article['title']:raise ValueError('Readback post title differs from the reviewed title')
        meta=p.get('meta',{})
        if (meta.get('_yoast_wpseo_focuskw')!=article['focus_keyword'] or meta.get('_yoast_wpseo_title')!=article['seo_title'] or
            meta.get('_yoast_wpseo_metadesc')!=article['meta_description']):
            raise ValueError('Yoast SEO fields did not persist')
        source,headers,status=self.client.page(p['link']);page=parse(source)
        if status!=200 or page.canonicals!=[p['link']] or page.title!=article['seo_title'] or page.descriptions!=[article['meta_description']]:
            raise ValueError('Public canonical/title/meta readback mismatch')
        if not html_lang_matches(lang,page.html_lang):raise ValueError('Rendered page language attribute is not '+SPEC[lang]['html_lang'])
        if any(href!=p['link'] for _,href in page.hreflangs):
            raise ValueError('Page declares an hreflang pair that this factory never created')
        if url_language(p['link'])!=lang:raise ValueError('Published URL is outside its language namespace')
        if 'noindex' in str(page.robots).lower() or 'noindex' in str(headers.get('X-Robots-Tag',headers.get('x-robots-tag'))).lower():
            raise ValueError('Published page is noindex')
        if page.schema_errors or not set(page.valid_schema_types)&{'Article','BlogPosting'}:
            raise ValueError('Valid article schema absent in rendered page')
        return {'wp_id':p['id'],'language':lang,'url':p['link'],'status':p['status'],'canonical':page.canonicals[0],
                'category_id':intent['category_id'],'seo_title':page.title,'meta_description':page.descriptions[0],
                'public_html_sha256':digest(source.encode()),'http_status':status,'schema_present':True,
                'html_lang':page.html_lang}


def language_order(topic):
    from .language import LANGUAGES
    return LANGUAGES.index(topic['language'])
