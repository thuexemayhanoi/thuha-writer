"""Create-only bilingual publisher: durable write-ahead intent, adapter write, WordPress confirmation, reconciliation.

All writes go through the companion adapter (src/thuha/adapter.py). A post is
created as a draft that already carries the ownership/idempotency marker, receives
its language marker and SEO fields, and is only then published, so it never exists
at an English URL first.

Three separate questions, answered in this order and never confused:

1. Did WordPress publish it? WordPress answers with an ID, a status and a permalink. When those are valid and the post
   is the one this intent created, the intent becomes PUBLISHED and a receipt is written. That alone decides whether a
   post counts.
2. Is what WordPress stored what was reviewed? (body, title, SEO fields, category, language marker.) Recorded with
   the receipt. A mismatch raises an alert that stops NEW publications until a person acknowledges it.
3. Does the public page look right? (canonical, title, meta, <html lang>, schema, no noindex.) A crawl after
   publication: retried with back-off, reported as a warning, and it never holds up the queue.

An unknown outcome of the POST is reconciled by idempotency key; the POST is never sent twice. A draft or an
unresolved intent is never counted as a post.
"""
import os
import uuid
from .adapter import NOT_DEPLOYED, build_payload, validate_payload
from .policy import DEFINITIVE_REJECTIONS
from .http import NetworkError
from .audit import inventory_bilingual, parse
from .common import ROOT, REPO, SITE, age, digest, load, now, urlkey
from .coordinator import timestamp
from .language import SPEC, html_lang_matches, split_url, targets as language_targets, url_language
from .quality import evaluate
from . import quota
from .quota import CLOSED_PHASES
from .research import collisions
from .store import GitError,GitHub,event

POST_CHECK_ATTEMPTS=5
POST_CHECK_DELAYS=(600,1800,3600,10800) # seconds before the 2nd, 3rd, 4th and 5th attempt
UNKNOWN_GRACE_SECONDS=3600 # twelve times the plugin's lock time-out: no request can still be creating a post


class PublishBlocked(ValueError):
    """This topic cannot be published now. Nothing was reserved and nothing was sent; other topics are unaffected."""
    def __init__(self,message,hard_fails=()):
        super().__init__(message)
        self.hard_fails=list(hard_fails)


def passed_post_checks(state):
    return sum(1 for v in state['intents'].values() if v.get('phase')=='PUBLISHED' and v.get('post_check',{}).get('status')=='PASSED')


def release_intent_cap(release, state):
    """Graduate the two-post pilot automatically after two verified WordPress readbacks.

    No independent AI review or further human approval is required by this stage.
    Pending, mismatched and draft outcomes never count toward graduation.
    """
    stage = release.get('stage', 'pilot')
    if stage == 'pilot':
        return release['pilot_max_posts']
    if stage == 'auto-scale':
        confirmed = sum(
            1 for tid, receipt in state.get('receipts', {}).items()
            if receipt.get('integrity') == 'MATCH'
            and state.get('intents', {}).get(tid, {}).get('phase') == 'PUBLISHED'
        )
        if confirmed < release['pilot_max_posts']:
            return release['pilot_max_posts']
    return release['approved_capacity']


def release_guard(release,store):
    if not store.durable_remote:raise ValueError('Production requires cross-host durable remote CAS')
    if not release.get('enabled') or not release.get('approved') or release.get('paused') or release.get('emergency_stop'):
        raise ValueError('Production publishing is OFF; separate owner go-live approval required')
    if not release.get('approval_ref'):
        raise ValueError('Owner approval reference missing from repository release configuration')
    if not release.get('cross_publisher_coordination_verified'):
        raise ValueError('Other publishers must be coordinated before pilot')
    if not release.get('languages_enabled'):
        raise ValueError('No language is enabled in the approved release')
    stage=release.get('stage','pilot')
    if stage=='pilot':
        if release.get('pilot_max_posts')!=2:raise ValueError('Initial pilot is restricted to two intents')
    elif stage=='controlled-scale':
        ceiling=sum(language_targets().values())
        if (passed_post_checks(store.read())<2 or release.get('expansion_approval_ref')!=release['approval_ref'] or
            not 2<=release.get('approved_capacity',0)<=ceiling or not 1<=release.get('maximum_daily_posts',0)<=20):
            raise ValueError('Controlled scale requires two pilot posts whose public-page check passed and a separately scoped expansion release')
    elif stage=='auto-scale':
        ceiling=sum(language_targets().values())
        if (release.get('pilot_max_posts')!=2 or
            release.get('expansion_approval_ref')!=release['approval_ref'] or
            not 2<=release.get('approved_capacity',0)<=ceiling or
            not 1<=release.get('maximum_daily_posts',0)<=50):
            raise ValueError('Owner auto-scale requires a two-post pilot, valid capacity and a daily cap')
    else:raise ValueError('Unknown release stage')


def verify_security(api):
    """Check trusted main/state refs without requiring a human approval queue.

    The workflow reruns deterministic QA 85 on main before any WordPress POST.
    Repository Actions secrets, explicit owner release, CAS, and readback remain required.
    No GitHub Environment reviewer or separate go-live variable is required.
    """
    if os.environ.get('GITHUB_REF') not in (None,'','refs/heads/main'):
        raise ValueError('Publisher must run from the trusted main branch')
    main=api.request('GET','/repos/'+REPO+'/git/ref/heads/main')
    state_branch=api.request('GET','/repos/'+REPO+'/git/ref/heads/factory-state')
    if main.get('ref')!='refs/heads/main' or not main.get('object',{}).get('sha'):
        raise ValueError('Main branch identity cannot be verified')
    if state_branch.get('ref')!='refs/heads/factory-state' or not state_branch.get('object',{}).get('sha'):
        raise ValueError('Durable factory-state branch identity cannot be verified')
    return {'trusted_main_ref':True,'durable_state_ref':True,'automated_qa_required':True,'checked_at':now()}


def idempotency_key(topic_id,article_sha):
    return digest({'topic_id':topic_id,'article_sha':article_sha})


def open_alerts(state):
    return [a for a in state.get('alerts',[]) if not a.get('acknowledged')]


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
        if topic['status']!='READY':raise PublishBlocked('Topic is not READY')
        recorded=s['qa'].get(topic_id,{})
        try:report=self.store.get_document(recorded.get('report_sha',''))
        except (ValueError,OSError,KeyError):raise PublishBlocked('QA report is missing') from None
        if report['status']!='PASS' or report['article_sha']!=sub['article_sha'] or report['policy_sha256']!=digest(self.policy):
            raise PublishBlocked('QA evidence/source/policy mismatch: run QA again')
        article=self.store.get_document(sub['article_sha'])
        current=live or self.inv
        qa=evaluate(article,topic,sub,current,self.policy,self.store,business=self.business)
        if qa['status']!='PASS':raise PublishBlocked('Fresh QA failed: '+','.join(qa['hard_fails']),qa['hard_fails'])
        if collisions(topic,current,[]):raise PublishBlocked('Live duplicate detected',['DUPLICATE_OR_CANNIBALIZATION'])
        return topic,sub,article,qa

    def dry_run(self):
        s=self.store.read();rows=[]
        for tid,t in sorted(s['topics'].items(),key=lambda kv:(language_order(kv[1]),kv[0])):
            if t['status']!='READY':continue
            try:
                _,sub,_,qa=self.prepare(tid)
                rows.append({'topic_id':tid,'language':t['language'],'status':'DRY_RUN_READY','article_sha':sub['article_sha'],'score':qa['score']})
            except Exception as exc:rows.append({'topic_id':tid,'language':t['language'],'status':'BLOCKED','error':str(exc)})
        return {'mode':'dry-run','wordpress_writes':0,'ready':rows,'publishing_enabled':self.release_loader()['enabled'],
                'open_alerts':len(open_alerts(s)),'unresolved':quota_unresolved(s)}

    def fresh_inventory(self):
        live=inventory_bilingual(self.client,check_pages=False)
        if not live['complete']:raise ValueError('Live WordPress inventory is incomplete')
        previous={x['id']:x for x in self.inv['items']}
        for item in live['items']:
            old=previous.get(item['id'])
            if old and old.get('content_sha256')==item['content_sha256']:
                item['public_check']=old.get('public_check',{})
        return live

    # ---------------------------------------------------------------- publishing

    def publish(self,topic_id):
        release=self.release_loader();release_guard(release,self.store)
        state=self.store.read();lang=state['topics'][topic_id]['language']
        if lang not in release['languages_enabled']:raise ValueError('Language '+lang+' is not enabled in the approved release')
        prior=state['intents'].get(topic_id)
        if prior and prior['phase'] not in CLOSED_PHASES:
            return self.resolve(topic_id) # Read-only. Never send the POST again.
        if open_alerts(state):
            raise ValueError('Unacknowledged integrity alert: a published post differs from what was reviewed. Check it, then acknowledge it')
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
        try:validate_payload(payload) # a payload the plugin would refuse must fail BEFORE it costs a publication slot
        except ValueError as exc:raise PublishBlocked('Payload would be refused by the adapter: '+str(exc),['ADAPTER_PAYLOAD_INVALID']) from None
        fence=uuid.uuid4().hex
        def reserve(s):
            if any(s['controls'].values()):raise ValueError('Factory is paused')
            old=s['intents'].get(topic_id)
            if old and old['phase'] not in CLOSED_PHASES:raise ValueError('Intent already reserved')
            quota.reserve(s,counts,self.targets,lang,topic_id,live_ids) # 499 -> 500 passes, 500 -> 501 never
            active=quota.active_intents(s)
            active.pop(topic_id,None)
            limit=release_intent_cap(release,s)
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
            if open_alerts(s):raise ValueError('Unacknowledged integrity alert')
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
        sent=False;outcome=None
        try:
            release_guard(self.release_loader(),self.store)
            current=self.store.read()
            if any(current['controls'].values()) or current['publisher_lease']['fence']!=fence or current['publisher_lease']['expires_at']<=timestamp():
                raise ValueError('Stopped after durable intent; reconcile required')
            sent=True # from here on the outcome of the POST can be unknown
            created=self.client.create(payload) # EXACTLY ONE HTTP attempt.
            post=created.get('post') if isinstance(created,dict) else None
            if not isinstance(post,dict):raise ValueError('The adapter answered without a post; reconcile by idempotency key')
            outcome=self.finish(topic_id,post,'adapter-create-response')
        except Exception as exc:
            closing=None
            if not sent:
                closing=('NOT_SENT',None)
            elif isinstance(exc,NetworkError) and getattr(exc,'not_sent',False):
                closing=('NOT_SENT','The connection to WordPress could not be opened; nothing was transmitted')
            elif isinstance(exc,NetworkError) and exc.code in DEFINITIVE_REJECTIONS:
                try: # An authoritative refusal from the plugin; only a read-back proving nothing exists closes the intent.
                    if not self.client.reconcile(key).get('found'):closing=('REJECTED',exc.code)
                except Exception:closing=None
            def settle(s):
                intent=s['intents'][topic_id]
                if intent['phase'] in ('PUBLISHED','DRAFT_HELD'):return # a lost response must never undo a recorded outcome
                if s.get('publisher_lease',{}).get('fence')==fence:s.pop('publisher_lease',None)
                if closing:
                    intent['phase']=closing[0];intent['closed_reason']=closing[1] or str(exc)[:200]
                    s['topics'][topic_id]['status']='READY' if closing[0]=='NOT_SENT' else 'NEEDS_REPAIR'
                    event(s,'PUBLICATION_INTENT_CLOSED',topic_id=topic_id,phase=closing[0])
                else:
                    intent['phase']='NEEDS_RECONCILIATION';s['topics'][topic_id]['status']='BLOCKED'
                    event(s,'PUBLISH_OUTCOME_UNCERTAIN',topic_id=topic_id)
            self.store.mutate(settle)
            if closing:raise
            # Unknown outcome: ask WordPress once, read-only. A post that was in fact created is recorded now;
            # anything else stays unresolved and the next run reconciles it. The POST is never repeated.
            try:recovered=self.reconcile(topic_id)
            except Exception:recovered=None
            if not recovered or recovered['status']!='PUBLISHED':raise
            outcome=recovered
        if outcome['status']!='PUBLISHED':
            raise ValueError('WordPress did not confirm a published post ('+outcome['status']+': '+str(outcome.get('reason'))+'); the intent stays unresolved and is never re-sent')
        return self.after_publication(topic_id,outcome['receipt'])

    def after_publication(self,topic_id,receipt):
        """First public-page check right after publication. Its result is a warning at most and never raises."""
        try:check=self.post_check(topic_id)['status']
        except Exception:check='WARNING'
        return {**receipt,'post_check':check}

    # ------------------------------------------------------------ WordPress proof

    def judge(self,p,intent):
        """('PUBLISHED'|'DRAFT_HELD'|'INCONSISTENT', reason). Only WordPress's own answer is used: ID, status, permalink."""
        slug=split_url(intent['expected_url'])[1]
        if not isinstance(p.get('id'),int) or isinstance(p['id'],bool) or p['id']<1:return 'INCONSISTENT','WordPress returned no valid post ID'
        if p['id'] in intent.get('preexisting_wp_ids',[]):return 'INCONSISTENT','The ID belongs to a protected existing WordPress post'
        if p.get('owner')!='thuha-writer' or p.get('idempotency_key')!=intent['idempotency_key'] or not p.get('marker_present'):
            return 'INCONSISTENT','The post is not owned by this factory intent'
        if intent.get('wp_id') and p['id']!=intent['wp_id']:return 'INCONSISTENT','The post ID differs from the one recorded earlier'
        if p.get('status')!='publish':return 'DRAFT_HELD','WordPress holds the post with status '+str(p.get('status'))
        if p.get('link')!=intent['expected_url'] or p.get('slug')!=slug or url_language(p['link'])!=intent['language']:
            return 'INCONSISTENT','The permalink is not the planned one in the right language namespace'
        return 'PUBLISHED',None

    def integrity(self,p,intent,article):
        """What WordPress stored against what was reviewed (adapter read-back, no public page involved)."""
        lang=intent['language'];problems=[]
        marks=p.get('language_markers',{})
        if p.get('language')!=lang:problems.append('language registered as '+str(p.get('language')))
        if marks.get('taxonomy_vi')!=(lang=='vi') or marks.get('is_vi')!=(lang=='vi'):problems.append('native language marker')
        if p.get('categories')!=[intent['category_id']] or p.get('category_languages')!=[lang]:problems.append('category or its language')
        if (p.get('featured_media') or 0)!=(article.get('featured_media') or 0):problems.append('featured image')
        if intent['marker'] not in p.get('content_raw',''):problems.append('ownership marker in the body')
        if ' '.join(parse(p.get('content_raw','')).text).split()!=' '.join(parse(article['body_html']).text).split():problems.append('visible body text')
        if p.get('title')!=article['title']:problems.append('title')
        meta=p.get('meta',{})
        if (meta.get('_yoast_wpseo_focuskw')!=article['focus_keyword'] or meta.get('_yoast_wpseo_title')!=article['seo_title'] or
            meta.get('_yoast_wpseo_metadesc')!=article['meta_description']):problems.append('Yoast SEO fields')
        return {'status':'MATCH' if not problems else 'MISMATCH','problems':problems}

    def finish(self,topic_id,post,source):
        intent=self.store.read()['intents'][topic_id]
        verdict,reason=self.judge(post,intent)
        if verdict=='PUBLISHED':return self.record_published(topic_id,intent,post,source)
        return self.record_unresolved(topic_id,intent,post,verdict,reason)

    def record_published(self,topic_id,intent,post,source):
        article=self.store.get_document(intent['article_sha'])
        integrity=self.integrity(post,intent,article)
        receipt={'topic_id':topic_id,'language':intent['language'],'article_sha':intent['article_sha'],'published_at':now(),
                 'agent_id':intent['agent_id'],'agent_identity_status':'declared external-session attribution',
                 'session':intent['session'],'source_commit':intent['commit'],'run_id':intent['run_id'],
                 'wp_id':post['id'],'url':post['link'],'slug':post['slug'],'status':post['status'],
                 'category_id':intent['category_id'],'proof':source,'integrity':integrity}
        receipt_sha=self.store.put_document(receipt)
        def transaction(s):
            if topic_id in s['receipts']:return s['receipts'][topic_id]
            s['receipts'][topic_id]={'document':receipt_sha,'language':intent['language'],'wp_id':post['id'],'url':post['link'],
                 'article_sha':intent['article_sha'],'agent_id':intent['agent_id'],'published_at':receipt['published_at'],
                 'integrity':integrity['status']}
            s['intents'][topic_id].update(phase='PUBLISHED',wp_id=post['id'],published_at=receipt['published_at'],
                 post_check={'status':'PENDING','attempts':0,'next_attempt_after':0})
            s['topics'][topic_id]['status']='PUBLISHED'
            if s.get('publisher_lease',{}).get('fence')==intent['fence']:s.pop('publisher_lease',None)
            event(s,'PUBLICATION_PUBLISHED',topic_id=topic_id,language=intent['language'],receipt_sha=receipt_sha,integrity=integrity['status'])
            if integrity['status']!='MATCH':
                s.setdefault('alerts',[]).append({'id':'integrity-'+topic_id,'topic_id':topic_id,'code':'INTEGRITY_MISMATCH',
                     'problems':integrity['problems'],'at':now(),'acknowledged':False})
                event(s,'INTEGRITY_ALERT',topic_id=topic_id,problems=integrity['problems'])
            return s['receipts'][topic_id]
        return {'status':'PUBLISHED','receipt':self.store.mutate(transaction)}

    def record_unresolved(self,topic_id,intent,post,verdict,reason):
        """WordPress holds a post for this key but it is not (yet) a valid published one. Never counted, never re-sent."""
        phase='DRAFT_HELD' if verdict=='DRAFT_HELD' else 'NEEDS_RECONCILIATION'
        def transaction(s):
            current=s['intents'][topic_id]
            if current['phase']=='PUBLISHED':return
            if current['phase']==phase and current.get('unresolved_reason')==reason:return # already recorded: no new event on every run
            current['phase']=phase;current['unresolved_reason']=reason
            if isinstance(post.get('id'),int) and not isinstance(post['id'],bool) and post['id']>0 and verdict=='DRAFT_HELD':current['wp_id']=post['id']
            s['topics'][topic_id]['status']='BLOCKED'
            if s.get('publisher_lease',{}).get('fence')==intent['fence']:s.pop('publisher_lease',None)
            event(s,'PUBLICATION_'+phase,topic_id=topic_id,reason=reason)
            if verdict=='INCONSISTENT' and not any(a['id']=='inconsistent-'+topic_id for a in s.get('alerts',[])):
                s.setdefault('alerts',[]).append({'id':'inconsistent-'+topic_id,'topic_id':topic_id,'code':'POST_INCONSISTENT',
                     'problems':[reason],'at':now(),'acknowledged':False})
        self.store.mutate(transaction)
        return {'status':phase,'reason':reason}

    # ------------------------------------------------------------ reconciliation

    def resolve(self,topic_id):
        """For publish(): the receipt of an already published topic, or an error while the outcome is unresolved."""
        outcome=self.reconcile(topic_id)
        if outcome['status']=='PUBLISHED':return outcome['receipt']
        raise ValueError('Publication outcome is unresolved ('+outcome['status']+': '+str(outcome.get('reason',outcome.get('phase')))+'); the POST is never repeated')

    def reconcile(self,topic_id):
        """Read-only: ask the adapter what exists for this intent's idempotency key and record what is found."""
        s=self.store.read();intent=s['intents'].get(topic_id)
        if not intent:raise ValueError('No publication intent for this topic')
        if intent['phase'] in CLOSED_PHASES:return {'status':'CLOSED','phase':intent['phase']}
        if intent['phase']=='PUBLISHED':return {'status':'PUBLISHED','receipt':s['receipts'][topic_id]}
        found=self.client.reconcile(intent['idempotency_key']) # an unreachable adapter raises: nothing is concluded
        if not found.get('found'):
            grace=self.release_loader().get('unknown_outcome_grace_seconds',UNKNOWN_GRACE_SECONDS)
            if age(intent['reserved_at'])<=grace:
                return {'status':'UNRESOLVED','reason':'No post carries the idempotency key yet; the POST is never repeated while this may still arrive'}
            def close(s):
                current=s['intents'][topic_id]
                if current['phase']=='PUBLISHED' or current['phase'] in CLOSED_PHASES:return False
                current['phase']='REJECTED';current['closed_reason']='absent_after_grace' # also ends a held draft that a person deleted
                s['topics'][topic_id]['status']='READY'
                if s.get('publisher_lease',{}).get('fence')==current.get('fence'):s.pop('publisher_lease',None)
                event(s,'PUBLICATION_INTENT_CLOSED',topic_id=topic_id,phase='REJECTED')
                return True
            if self.store.mutate(close):return {'status':'CLOSED','phase':'REJECTED','reason':'absent_after_grace'}
            return self.reconcile(topic_id) # something else resolved it in the meantime: report what the ledger says now
        return self.finish(topic_id,found['post'],'adapter-reconcile')

    def reconcile_all(self):
        """Every intent that is neither published nor closed. Returns {topic: outcome}; unreachable adapters are reported."""
        out={}
        for tid in list(quota_unresolved(self.store.read())):
            try:out[tid]=self.reconcile(tid)
            except (NetworkError,OSError) as exc:out[tid]={'status':'UNREACHABLE','reason':str(exc)}
        return out

    # --------------------------------------------------------- public-page check

    def crawl(self,intent):
        """The public page against what was reviewed. Raises ValueError with the reason when it does not hold."""
        lang=intent['language']
        article=self.store.get_document(intent['article_sha'])
        link=intent['expected_url']
        source,headers,status=self.client.page(link);page=parse(source)
        if status!=200 or page.canonicals!=[link] or page.title!=article['seo_title'] or page.descriptions!=[article['meta_description']]:
            raise ValueError('Public canonical/title/meta mismatch (HTTP '+str(status)+')')
        if not html_lang_matches(lang,page.html_lang):raise ValueError('Rendered page language attribute is not '+SPEC[lang]['html_lang'])
        if any(href!=link for _,href in page.hreflangs):raise ValueError('Page declares an hreflang pair that this factory never created')
        if 'noindex' in str(page.robots).lower() or 'noindex' in str(headers.get('X-Robots-Tag',headers.get('x-robots-tag'))).lower():
            raise ValueError('Published page is noindex')
        if page.schema_errors or not set(page.valid_schema_types)&{'Article','BlogPosting'}:
            raise ValueError('Valid article schema absent in rendered page')
        return {'url':link,'canonical':page.canonicals[0],'seo_title':page.title,'meta_description':page.descriptions[0],
                'public_html_sha256':digest(source.encode()),'http_status':status,'html_lang':page.html_lang}

    def post_check(self,topic_id):
        """One attempt of the public-page check. Records PASSED, or WARNING (retries remain) or FAILED_FINAL; never raises
        for a page problem and never touches the queue."""
        s=self.store.read();intent=s['intents'].get(topic_id)
        if not intent or intent['phase']!='PUBLISHED':raise ValueError('Only a published topic has a public-page check')
        previous=intent.get('post_check',{});attempts=previous.get('attempts',0)+1
        evidence=None
        try:
            proof=self.crawl(intent)
            result={'status':'PASSED','problem':None};evidence=proof
        except (ValueError,KeyError,OSError,NetworkError) as exc:
            result={'status':'FAILED_FINAL' if attempts>=POST_CHECK_ATTEMPTS else 'WARNING','problem':str(exc)[:300]}
        document=self.store.put_document({'topic_id':topic_id,'wp_id':intent['wp_id'],'attempt':attempts,'checked_at':now(),**result,
                                          'evidence':evidence}) if evidence else None
        def transaction(s):
            current=s['intents'][topic_id]
            delay=POST_CHECK_DELAYS[min(attempts-1,len(POST_CHECK_DELAYS)-1)]
            current['post_check']={**result,'attempts':attempts,'last_attempt_at':now(),'document':document,
                                   'next_attempt_after':0 if result['status']!='WARNING' else timestamp()+delay}
            event(s,'POST_CHECK',topic_id=topic_id,status=result['status'],attempt=attempts)
            return current['post_check']
        return self.store.mutate(transaction)

    def due_post_checks(self,state=None,at=None):
        state=state or self.store.read();at=timestamp() if at is None else at
        return sorted(k for k,v in state['intents'].items() if v.get('phase')=='PUBLISHED'
                      and v.get('post_check',{}).get('status') in ('PENDING','WARNING')
                      and v.get('post_check',{}).get('next_attempt_after',0)<=at)

    def run_post_checks(self,topic_id=None):
        out={}
        for tid in ([topic_id] if topic_id else self.due_post_checks()):
            try:out[tid]=self.post_check(tid)['status']
            except Exception as exc:out[tid]='ERROR: '+str(exc)[:120]
        return out

    # ------------------------------------------------------------------ alerts

    def acknowledge(self,topic_id,note):
        if not note or len(note.strip())<10:raise ValueError('A note of at least ten characters saying what was checked is required')
        def transaction(s):
            hit=[a for a in s.get('alerts',[]) if a['topic_id']==topic_id and not a.get('acknowledged')]
            if not hit:raise ValueError('No open alert for this topic')
            for alert in hit:alert.update(acknowledged=True,acknowledged_at=now(),note=note.strip()[:500])
            event(s,'ALERT_ACKNOWLEDGED',topic_id=topic_id)
            return len(hit)
        return self.store.mutate(transaction)


def quota_unresolved(state):
    return [k for k,v in state['intents'].items() if v['phase'] not in ('PUBLISHED',)+CLOSED_PHASES]


def language_order(topic):
    from .language import LANGUAGES
    return LANGUAGES.index(topic['language'])
