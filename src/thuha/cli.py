"""python -m thuha.cli --help; no paid model APIs or implicit WordPress writes."""
import argparse
import ast
import json
import os
import sys
from pathlib import Path
from .common import ROOT,REPO,age,digest,fresh,load,now,save,validate_inventory
from .store import LocalStore,GitStore,GitBranchStore,event,validate
from . import audit,coordinator,research,quality,dashboard,matrix,quota,ledger
from .adapter import AdapterClient
from .http import HTTP,NetworkError
from .language import LANGUAGES,targets as language_targets
from .publisher import Publisher
from . import pipeline
from . import runtime, writing

def dispatch_qa_ready(store, topic_ids):
    """Signal a successful QA revision without waiting for cron or AI review.

    Only the shared ledger (`--remote`, which has an API client) is read by Actions, so only it dispatches: a session ledger in a
    branch reaches the queue through `promote` after the merge. The GitHub API returns 204 on acceptance; publication still remains
    independently gated by live QA, WordPress readback and release controls.
    """
    if not getattr(store,'durable_remote',False) or not hasattr(store,'api') or not topic_ids:
        return {'status':'LOCAL_ONLY','topics':topic_ids}
    try:
        store.api.request('POST','/repos/'+REPO+'/dispatches',{
            'event_type':'thuha-qa-ready',
            'client_payload':{'topic_ids':topic_ids[:10]}
        })
        return {'status':'DISPATCH_ACCEPTED','topics':topic_ids[:10]}
    except (ValueError,OSError,RuntimeError) as exc:
        # READY remains safely queued; the hourly workflow is a fallback.
        return {'status':'DISPATCH_FAILED','topics':topic_ids[:10],
                'reason':type(exc).__name__}


def inventory_for(store,path,max_age=None):
    """Refresh expired live WordPress evidence for write-capable operations.

    This uses public GET requests only. Read-only health/dry-run workflows
    deliberately pass max_age=None and do not mutate durable remote state.
    """
    state=store.read()
    chosen=None
    if path is None and state.get('inventory_document'): # an inventory named with --inventory is what the caller asked for; only the default is the stored one
        stored=store.get_document(state['inventory_document'])
        # An inventory recorded before languages existed carries no label and cannot count anything; an honestly
        # labelled one (even the public-only one) is kept as it is.
        if stored.get('language_source'):chosen=stored
    if chosen is None:
        chosen=load(path) if path and Path(path).exists() else audit.snapshot_inventory() # the snapshot is an offline planning view; it is stale by design
    limit=max_age(chosen) if callable(max_age) else max_age
    if limit is not None and getattr(store,'durable_remote',False):
        try:validate_inventory(chosen,limit)
        except ValueError:
            try:
                fresh_inv=audit.inventory() # live public GET; never a WordPress POST
                validate_inventory(fresh_inv,limit)
            except (NetworkError,OSError,ValueError):return chosen # cannot reach the site: the caller's own check refuses the old one clearly
            document=store.put_document(fresh_inv)
            store.mutate(lambda st:st.update(inventory_document=document))
            return fresh_inv
    return chosen


def inventory_max_age(inv,policy,factory):
    """How old an inventory may be for the work at hand.

    The committed authenticated snapshot may feed planning (topic admission, writer claims, quota and dashboard) for a
    week; everything that publishes or passes QA keeps the strict policy age, and the snapshot never satisfies that.
    """
    if inv.get('language_source')=='authenticated-snapshot':return factory['planning_inventory_max_age_seconds']
    return policy['inventory_max_age_seconds']


def live_counts(inv,state=None):
    """Per-language live counts (plus factory posts published since the inventory), or None when the inventory cannot be trusted."""
    try:counts=quota.published(inv)
    except ValueError:return None
    return quota.effective(state,counts,{x['id'] for x in inv.get('items',[])}) if state is not None else counts


def qa_one(store,tid,inv,policy,facts):
    """One automatic QA run. Vietnamese needs an authoritative inventory: a public-only one cannot see Vietnamese posts or categories."""
    if store.read()['topics'][tid]['language']!='en' and inv.get('language_source') not in quota.SOURCES:
        raise quality.InventoryUnusable('Vietnamese QA needs an adapter or authenticated inventory; this one is '+str(inv.get('language_source')))
    return quality.run_qa(store,tid,inv,policy,facts)


def submit_guard(store,args,article,policy,facts):
    """Run the writer's precheck on the exact file about to be stored, without changing anything, and refuse a draft that is known to fail.

    A draft with a known fault, or one that waits for data it did not declare (or declares data that exists), would only be
    sent back for repair; refusing it spends no repair. `--allow-faults` stores it anyway; the wait rules still hold.
    """
    state=store.read()
    if article.get('topic_id') not in state['topics']:return {'status':'OK','waiting_for':[c for c in (args.waiting_for or []) if c!='auto']} # the lease check names the real error
    try:result=runtime.precheck(store,state,inventory_for(store,args.inventory),article['topic_id'],article,policy,facts)
    except (ValueError,OSError,KeyError) as exc:
        # The check itself cannot run (e.g. an unreadable inventory): the draft is stored as it was before this guard existed.
        return {'status':'OK','waiting_for':[c for c in (args.waiting_for or []) if c!='auto'],'notes':['precheck could not run ('+str(exc)+'): the draft was stored without it']}
    ok,problems,declared=writing.submission_check(result,args.waiting_for,args.allow_faults)
    if ok:return {'status':'OK','waiting_for':declared}
    return {'status':'NOT_SUBMITTED','ledger_writes':0,'problems':problems,'data_waits':result['data_waits'],'content_fails':result['content_fails'],
            'lint':[f for f in result['lint'] if f['severity']=='fix'],'fixes':writing.hints(result['content_fails']),
            'next':'Fix the text, run `precheck` (or `build`) again, then submit; --allow-faults stores it as it is.'}


def main(argv=None):
    p=argparse.ArgumentParser(description='ThuHa Writer V4; production is disabled until separately approved')
    p.add_argument('--remote',action='store_true',help='Use authoritative GitHub CAS; required across computers')
    p.add_argument('--git-branch',action='store_true',help='Durable state via git commits/pushes on the current session branch (when REST writes are closed)')
    p.add_argument('--state-dir',default=str(ROOT/'.runtime'))
    p.add_argument('--inventory',default=None,help='Inventory JSON; default is the stored remote inventory, else the committed snapshot')
    p.add_argument('--output',default=str(ROOT/'artifacts'))
    sub=p.add_subparsers(dest='command',required=True)
    q=sub.add_parser('audit');q.add_argument('--max-age',type=int,default=0,help='Skip when the stored inventory is younger than this many seconds')
    sub.add_parser('validate');sub.add_parser('health');sub.add_parser('report')
    sub.add_parser('coordinator');sub.add_parser('recovery');sub.add_parser('refill');sub.add_parser('credentials')
    sub.add_parser('quota');sub.add_parser('adapter-preflight');sub.add_parser('package')
    q=sub.add_parser('claim');q.add_argument('--session',required=True);q.add_argument('--agent-id',required=True);q.add_argument('--slot',default='auto')
    q.add_argument('--revise',metavar='TOPIC_ID',help='Claim a stored WAITING_DATA draft, or a finished one whose QA is BLOCKED_DATA, to revise it (not a repair)')
    q.add_argument('--topic-id',metavar='TOPIC_ID',help='Claim this claimable topic instead of the next one in order (see `next`); the claim records that it was picked')
    for command in ('heartbeat','release','submit'):
        q=sub.add_parser(command);q.add_argument('--slot',required=True);q.add_argument('--session',required=True);q.add_argument('--fence',required=True)
        if command=='submit':
            q.add_argument('--file',required=True)
            q.add_argument('--waiting-for',nargs='+',choices=coordinator.WAIT_CODES+('auto',),help='Store the draft as WAITING_DATA: what it still lacks (never READY, never QA). `auto` waits for exactly what the check says is missing')
            q.add_argument('--allow-faults',action='store_true',help='Store the draft although the precheck knows of faults in it (they will come back as a repair)')
    q=sub.add_parser('source');q.add_argument('--url');q.add_argument('--external-fetch',help='JSON record written from an authorized external fetcher result')
    q.add_argument('--repository-file',choices=research.FIRST_PARTY_FILES,help='Capture the owner facts file as labelled first-party evidence (not a web page)')
    q=sub.add_parser('resume');q.add_argument('--topic-id',required=True)
    q=sub.add_parser('kit');q.add_argument('--topic-id',required=True)
    q=sub.add_parser('precheck');q.add_argument('--topic-id',required=True);q.add_argument('--file',required=True);q.add_argument('--review')
    q=sub.add_parser('pack',help='Read-only writing pack for one topic, assembled from the repository');q.add_argument('--topic-id',required=True);q.add_argument('--out')
    q=sub.add_parser('build',help='Compose an article from the pack, a body and a small meta file, save it and run the precheck');q.add_argument('--topic-id',required=True)
    q.add_argument('--body',required=True,help='HTML file with the article body');q.add_argument('--meta',required=True,help='JSON file: seo_title, meta_description, featured_media, claims (shorthand such as "manual:month"), business_claims, extra_sources')
    q.add_argument('--out');q.add_argument('--session');q.add_argument('--agent-id')
    q=sub.add_parser('next',help='Read-only ranking of what can be written now');q.add_argument('--language',choices=LANGUAGES);q.add_argument('--limit',type=int,default=10)
    q=sub.add_parser('admit');q.add_argument('--file',required=True);q.add_argument('--fetch-records',required=True);q.add_argument('--reviewer-id',help='Optional attribution; no reviewer is needed');q.add_argument('--extra-queue')
    sub.add_parser('cycle');sub.add_parser('recheck-data')
    q=sub.add_parser('hold');q.add_argument('--topic-id',required=True);q.add_argument('--reason',required=True)
    q=sub.add_parser('unhold');q.add_argument('--topic-id',required=True)
    q=sub.add_parser('brief');q.add_argument('--limit',type=int,default=10);q.add_argument('--language',choices=LANGUAGES)
    q=sub.add_parser('matrix');q.add_argument('action',choices=['validate','next']);q.add_argument('--language',choices=LANGUAGES);q.add_argument('--limit',type=int,default=10)
    q=sub.add_parser('intake',help='Admit topics: candidates from --file, or matrix rows that need only the shop facts or no source (--matrix-ids)');q.add_argument('--file')
    q.add_argument('--matrix-ids',nargs='+',metavar='TOPIC_ID',help='Matrix rows asking only for first-party facts or no source: the owner facts file is captured and attached; any other row is refused by name')
    q=sub.add_parser('review');q.add_argument('--file',required=True);q.add_argument('--topic-id',required=True)
    q=sub.add_parser('qa');q.add_argument('--topic-id');q.add_argument('--pending',action='store_true',help='All completed drafts without a reviewer gate, and READY drafts whose QA report predates the current policy');q.add_argument('--language',choices=LANGUAGES)
    q=sub.add_parser('promote');q.add_argument('--source-state',default='data/state/factory.json');q.add_argument('--source-docs',default='data/documents');q.add_argument('--apply',action='store_true')
    q=sub.add_parser('sync');q.add_argument('--apply',action='store_true');q.add_argument('--discard-unpromoted',action='store_true')
    q=sub.add_parser('publisher');q.add_argument('--mode',choices=['dry-run','production','reconcile','verify','drain','acknowledge'],default='dry-run');q.add_argument('--topic-id');q.add_argument('--note')
    q=sub.add_parser('controls');q.add_argument('--pause',choices=['on','off']);q.add_argument('--emergency-stop',choices=['on','off'])
    args=p.parse_args(argv)
    if args.remote and args.git_branch:raise ValueError('Choose one state backend')
    store=GitStore() if args.remote else GitBranchStore() if args.git_branch else LocalStore(args.state_dir)
    policy=load(ROOT/'config/qa.json');facts=load(ROOT/'config/business-facts.json');factory=load(ROOT/'config/factory.json')
    release=load(ROOT/'config/release.json')
    result={}
    exit_code=0
    if args.command=='validate':
        for file in (ROOT/'config').glob('*.json'):load(file)
        for file in (ROOT/'src').rglob('*.py'):ast.parse(file.read_text())
        validate(store.read())
        project=load(ROOT/'config/project.json')
        if project['quality']['policy_file']!='config/qa.json':raise ValueError('QA policy pointer drift')
        if not policy['hard_fail_overrides_score']:raise ValueError('Hard-fail policy disabled')
        if policy.get('review_mode')!='automated' or policy.get('semantic_review_required') is not False or policy['score_threshold']!=75:
            raise ValueError('Owner policy: automated QA >=75, no independent AI review gate')
        if language_targets(project)!={'vi':500,'en':500} or factory['topic_capacity_by_language']!={'vi':500,'en':500}:
            raise ValueError('Goal drift: the owner goal is 500 published posts per language')
        problems={l:matrix.validate(load(matrix.matrix_path(l)),l) for l in LANGUAGES}
        if any(problems.values()):raise ValueError('Matrix validation failed: '+json.dumps({l:len(v) for l,v in problems.items()}))
        from . import package
        result={'status':'PASS','qa_policy_sha256':digest(policy),'source':'single config/qa.json',
                'matrices':{l:matrix.summary(load(matrix.matrix_path(l))) for l in LANGUAGES},'adapter_package':package.verify()}
    elif args.command=='audit':
        # Vietnamese posts can be hidden from the public REST collection, so a complete
        # inventory needs the authenticated adapter. Without credentials this is public-only
        # and is labelled unverified; quota and publishing refuse to trust it.
        stored=store.read().get('inventory_document')
        current=store.get_document(stored) if stored else None
        if args.max_age and current and fresh(current['captured_at'],args.max_age):
            print(json.dumps({'status':'SKIPPED','reason':'stored inventory is fresh','age_seconds':round(age(current['captured_at'])),
                              'language_source':current.get('language_source')}));return 0
        if os.environ.get('THUHA_WP_USER') and os.environ.get('THUHA_WP_APPLICATION_PASSWORD'):
            client=AdapterClient(HTTP());client.preflight();inv=audit.inventory_bilingual(client)
        else:inv=audit.inventory()
        result=audit.write_audit(inv,args.output)
        # A public-only read never replaces a still-fresh adapter inventory: the publisher refuses the public one.
        keep=bool(current and current.get('language_source')=='adapter' and inv.get('language_source')!='adapter' and age(current['captured_at'])<policy['inventory_max_age_seconds'])
        if inv['complete'] and args.remote and not keep:
            document=store.put_document(inv)
            store.mutate(lambda s:s.update(inventory_document=document))
        result['stored']=bool(inv['complete'] and args.remote and not keep)
        if not inv['complete']:
            print(json.dumps(result));return 2
    elif args.command=='credentials':
        result={'github_token_configured':bool(os.environ.get('THUHA_GITHUB_TOKEN')),
                'github_security_read_token_configured':bool(os.environ.get('THUHA_GITHUB_SECURITY_TOKEN')),
                'wordpress_user_configured':bool(os.environ.get('THUHA_WP_USER')),
                'wordpress_password_configured':bool(os.environ.get('THUHA_WP_APPLICATION_PASSWORD')),
                'wordpress_writes':0,'production_enabled':release['enabled'],'languages_enabled':release.get('languages_enabled',[])}
    elif args.command in ('coordinator','recovery'):
        result={'expired_slots':store.mutate(coordinator.recover),'ai_runtime':'External session required; no AI launched'}
    elif args.command=='claim':
        inv=inventory_for(store,args.inventory,lambda i:inventory_max_age(i,policy,factory));planning=inventory_max_age(inv,policy,factory);validate_inventory(inv,planning);note=None
        try:research.refill(store,inv,factory['refill_below'],factory['refill_batch_max'],inventory_max_age=planning)
        except ValueError as exc:note=str(exc) # e.g. inventory not language-authoritative; claiming itself stays possible
        result=dict(coordinator.claim(store,args.session,args.agent_id,args.slot,factory['lease_seconds'],live_counts(inv,store.read()),language_targets(),args.revise,args.topic_id))
        if note:result['refill_note']=note
    elif args.command=='heartbeat':result=coordinator.heartbeat(store,args.slot,args.session,args.fence,factory['lease_seconds'])
    elif args.command=='release':result=coordinator.release(store,args.slot,args.session,args.fence)
    elif args.command=='submit':
        article=load(args.file)
        guard=submit_guard(store,args,article,policy,facts)
        if guard['status']!='OK':
            print(json.dumps(guard,ensure_ascii=False,indent=2));return 1 # nothing was stored and no repair was spent
        result={'submission':coordinator.submit(store,args.slot,args.session,args.fence,article,policy['maximum_repairs'],guard['waiting_for'] or None)}
        if guard.get('notes'):result['submit_notes']=guard['notes']
        tid=article['topic_id']
        if store.read()['topics'][tid]['status']=='DRAFT_READY':
            # A completed draft goes straight to automatic QA, with no reviewer. A draft stored with --waiting-for, or one over its
            # repair limit, is not evaluated and dispatches nothing.
            try:result['qa']=qa_one(store,tid,inventory_for(store,args.inventory,policy['inventory_max_age_seconds']),policy,facts)
            except (ValueError,OSError,RuntimeError,KeyError) as exc:
                # The draft is stored; an unusable inventory only means QA cannot run now (the scheduled run evaluates it).
                result['qa']={'status':'BLOCKED','error':str(exc),'kind':'INFRASTRUCTURE' if isinstance(exc,(NetworkError,OSError,quality.InventoryUnusable)) else 'STATE_OR_CONTRACT'}
            if result['qa']['status']=='PASS':result['publisher_trigger']=dispatch_qa_ready(store,[tid])
            elif result['qa']['status']=='FAIL':exit_code=1 # repair and resubmit
    elif args.command=='source':
        if bool(args.repository_file)==bool(args.url):raise ValueError('Name exactly one source: --url (web page) or --repository-file (first-party facts)')
        result=(research.capture_repository_file(store,args.repository_file) if args.repository_file
                else research.capture_external_source(store,args.url,load(args.external_fetch)) if args.external_fetch
                else research.capture_source(store,args.url))
    elif args.command=='kit':
        inv=inventory_for(store,args.inventory);validate_inventory(inv,inventory_max_age(inv,policy,factory))
        result=runtime.kit(store.read(),inv,args.topic_id,policy,facts)
    elif args.command=='precheck':
        inv=inventory_for(store,args.inventory)
        review=load(args.review) if args.review else None
        result=runtime.precheck(store,store.read(),inv,args.topic_id,load(args.file),policy,facts,review)
        if result['content_fails'] or any(f['severity']=='fix' for f in result['lint']):exit_code=1 # a fault in the article itself
        elif result['data_waits']:exit_code=3 # only data is missing: store the draft with --waiting-for auto
        elif not result['would_pass_qa']:exit_code=1 # a low score also needs repair, even without hard failures
    elif args.command=='pack':
        inv=inventory_for(store,args.inventory);validate_inventory(inv,inventory_max_age(inv,policy,factory))
        result=writing.pack(store,store.read(),inv,args.topic_id,policy,facts)
        if args.out:save(Path(args.out),result)
    elif args.command=='build':
        inv=inventory_for(store,args.inventory);validate_inventory(inv,inventory_max_age(inv,policy,factory))
        state=store.read()
        data=writing.pack(store,state,inv,args.topic_id,policy,facts)
        article=writing.compose(data,Path(args.body).read_text(encoding='utf-8'),load(args.meta),args.session,args.agent_id)
        target=Path(args.out) if args.out else Path(args.output)/('article-'+args.topic_id+'.json')
        save(target,article)
        result=runtime.precheck(store,state,inv,args.topic_id,article,policy,facts)
        result['article_file']=str(target)
        result['left_out_stale_sources']=writing.stale_sources(data)
        if result['content_fails'] or any(f['severity']=='fix' for f in result['lint']):exit_code=1
        elif result['data_waits']:exit_code=3
        elif not result['would_pass_qa']:exit_code=1
    elif args.command=='next':
        inv=inventory_for(store,args.inventory);validate_inventory(inv,inventory_max_age(inv,policy,factory))
        result=writing.readiness(store,store.read(),inv,policy,facts,args.language,args.limit)
    elif args.command=='admit':
        inv=inventory_for(store,args.inventory,lambda i:inventory_max_age(i,policy,factory))
        extra=load(args.extra_queue) if args.extra_queue else []
        result={'admitted':runtime.admit(store,inv,load(args.file),args.reviewer_id,load(args.fetch_records),factory['refill_batch_max'],extra,
                                         inventory_max_age=inventory_max_age(inv,policy,factory))}
    elif args.command=='cycle':
        result=runtime.cycle(store.read(),inventory_for(store,args.inventory),release)
    elif args.command=='hold':result={'held':coordinator.hold(store,args.topic_id,args.reason)}
    elif args.command=='unhold':result={'restored_status':coordinator.unhold(store,args.topic_id)}
    elif args.command=='recheck-data':
        # Only an authoritative, fresh inventory can show that the image or the live links now exist. Nothing becomes READY.
        inv=inventory_for(store,args.inventory)
        result={'inventory_language_source':inv.get('language_source'),'cleared':store.mutate(lambda s:coordinator.clear_satisfied(s,inv,policy)),
                'still_waiting':{k:v['waiting_for'] for k,v in store.read()['topics'].items() if v['status']=='WAITING_DATA' and v.get('waiting_for')}}
    elif args.command=='resume':
        state=store.read();submission=state['submissions'].get(args.topic_id)
        result={'topic':state['topics'][args.topic_id],'submission':submission,
                'draft':store.get_document(submission['article_sha']) if submission else None,
                'held_draft':store.get_document(state['topics'][args.topic_id]['held_article_sha']) if state['topics'][args.topic_id].get('held_article_sha') else None,
                'qa':store.get_document(state['qa'][args.topic_id]['report_sha']) if args.topic_id in state['qa'] else None,
                'leases':[v for v in state['leases'].values() if v['topic_id']==args.topic_id]}
    elif args.command=='brief':result=pipeline.brief(store.read(),args.limit,args.language)
    elif args.command=='quota':
        inv=inventory_for(store,args.inventory)
        result={'inventory_language_source':inv.get('language_source'),'inventory_captured_at':inv['captured_at'],
                'languages':quota.status(store.read(),live_counts(inv,store.read()) or quota.published(inv),language_targets()),
                'note':'Snapshots and non-adapter inventories are not live counters; the publisher recounts before each reservation.'}
    elif args.command=='adapter-preflight':
        # Live check, run only by the credentialed publisher. Nothing is recorded unless it passes.
        info=AdapterClient(HTTP()).preflight()
        def record(s):
            s['adapter']={'status':'VERIFIED','verified_at':now(),**info}
            event(s,'ADAPTER_PREFLIGHT',**info)
        store.mutate(record);result=info
    elif args.command=='package':
        from . import package
        result=package.verify()
    elif args.command=='matrix':
        if args.action=='validate':
            result={l:matrix.validate(load(matrix.matrix_path(l)),l) for l in ([args.language] if args.language else LANGUAGES)}
            if any(result.values()):exit_code=1
        else:
            rows=[];admitted=set(store.read()['topics']) # a row already admitted to the ledger is not "next"
            for l in ([args.language] if args.language else LANGUAGES):
                rows+=sorted((r for r in load(matrix.matrix_path(l))['rows'] if r['kind']=='NEW' and r['writer_state']=='NEEDS_SOURCE' and r['id'] not in admitted),key=lambda r:r['write_order'])[:args.limit]
            result={'mode':'read-only','wordpress_writes':0,'next_research':[{k:r[k] for k in ('id','language','title','primary_keyword','category_id','proposed_url','source_requirements','writer_state')} for r in rows]}
    elif args.command=='intake':
        inv=inventory_for(store,args.inventory,lambda i:inventory_max_age(i,policy,factory))
        if bool(args.file)==bool(args.matrix_ids):raise ValueError('Give --file or --matrix-ids (one of the two)')
        candidates=load(args.file) if args.file else writing.matrix_candidates(store,args.matrix_ids)
        result={'admitted':research.intake(store,candidates,inv,factory['refill_batch_max'],language_targets(),inventory_max_age=inventory_max_age(inv,policy,factory))}
    elif args.command=='refill':
        inv=inventory_for(store,args.inventory,lambda i:inventory_max_age(i,policy,factory))
        result=research.refill(store,inv,factory['refill_below'],factory['refill_batch_max'],language_targets(),inventory_max_age=inventory_max_age(inv,policy,factory))
    elif args.command=='review':
        value=load(args.file)
        # Setting a string ID is attribution, not authentication; enforced GitHub
        # path/branch controls and environment review are still required to go live.
        if value.get('reviewer_id') not in policy['trusted_reviewers'] or value.get('reviewer_id')!=os.environ.get('THUHA_REVIEWER_ID'):
            raise ValueError('Authorized independent reviewer identity required')
        if value.get('article_sha')!=store.read()['submissions'][args.topic_id]['article_sha']:raise ValueError('Review references different revision')
        document=store.put_document(value)
        def record(s):
            s.setdefault('reviews',{})[args.topic_id]=document
            event(s,'REVIEW',topic_id=args.topic_id,review_document=document,reviewer_id=value['reviewer_id']) # an event, so the hand-over sees it
        store.mutate(record)
        result={'review_document':document}
    elif args.command=='qa':
        inv=inventory_for(store,args.inventory,policy['inventory_max_age_seconds']) # an expired inventory is refreshed from the public site (GET only) before QA
        languages=[args.language] if args.language else None
        ids=[args.topic_id] if args.topic_id else quality.pending_qa(store,policy,languages) if args.pending else [k for k,v in store.read()['topics'].items() if v['status'] in ('DRAFT_READY','NEEDS_REPAIR') and (not languages or v['language'] in languages)]
        result={'results':{}}
        passed=[]
        for tid in ids:
            try:
                if store.read()['topics'][tid]['language']!='en' and inv.get('language_source') not in quota.SOURCES:
                    # A public-only inventory cannot see Vietnamese posts or categories: that is a missing input, not a failed article.
                    raise quality.InventoryUnusable('Vietnamese QA needs an adapter or authenticated inventory; this one is '+str(inv.get('language_source')))
                value=quality.run_qa(store,tid,inv,policy,facts)
                result['results'][tid]=value
                # A scheduled batch reports FAIL / BLOCKED_DATA in the ledger, not as a red step; asking for one topic says so in the exit code.
                if value['status']=='PASS':passed.append(tid)
                elif value['status']=='BLOCKED_DATA':exit_code=max(exit_code,0 if args.pending else 3)
                elif not args.pending:exit_code=max(exit_code,1)
            except (ValueError,OSError,RuntimeError,KeyError) as exc:
                # An unusable inventory (stale audit, wrong site, public-only for Vietnamese) is infrastructure: the run is red, no draft is touched.
                infra=isinstance(exc,(NetworkError,OSError,quality.InventoryUnusable))
                result['results'][tid]={'status':'BLOCKED','error':str(exc),'kind':'INFRASTRUCTURE' if infra else 'STATE_OR_CONTRACT'}
                exit_code=max(exit_code,2 if infra else 1)
        if passed:result['publisher_trigger']=dispatch_qa_ready(store,passed) # the queue is drained now; the hourly run is only the fallback
    elif args.command=='publisher':
        pub=Publisher(store,AdapterClient(HTTP(allow_write=args.mode in ('production','drain'))),
                      inventory_for(store,args.inventory,policy['inventory_max_age_seconds'] if args.mode in ('production','drain') else None),policy,facts)
        if args.mode=='dry-run':result=pub.dry_run()
        elif args.mode=='drain':
            result=pipeline.drain(pub)
            if result['halted']:exit_code=2 # the run is red so the stop is seen; the JSON above says why
        elif args.mode=='production':
            if not args.topic_id:raise ValueError('Explicit single topic ID required for pilot')
            result=pub.publish(args.topic_id)
        elif args.mode=='reconcile':
            result={'reconciled':{args.topic_id:pub.reconcile(args.topic_id)} if args.topic_id else pub.reconcile_all()}
            if any(v['status'] not in ('PUBLISHED','CLOSED') for v in result['reconciled'].values()):exit_code=2
        elif args.mode=='verify':result={'post_checks':pub.run_post_checks(args.topic_id)}
        else:
            if not args.topic_id:raise ValueError('Name the topic whose alert you checked')
            result={'acknowledged_alerts':pub.acknowledge(args.topic_id,args.note)}
    elif args.command=='promote':
        if args.apply and not args.remote:raise ValueError('Promotion writes the shared ledger: run it with --remote')
        source=ROOT/args.source_state
        result=ledger.promote(store,load(source),ledger.read_documents(ROOT/args.source_docs),args.source_state,apply=args.apply)
        if result['status'] not in ('FAST_FORWARD','ALREADY_INCLUDED'):exit_code=1
    elif args.command=='sync':
        if args.remote:raise ValueError('Sync copies the shared ledger into a session branch: use --git-branch')
        result=ledger.sync(store,GitStore(),apply=args.apply,discard_unpromoted=args.discard_unpromoted)
        if result['status'] not in ('FAST_FORWARD','ALREADY_INCLUDED','REPLACED'):exit_code=1
    elif args.command=='controls':
        def controls(s):
            for key,arg in [('paused',args.pause),('emergency_stop',args.emergency_stop)]:
                if arg is not None:s['controls'][key]=arg=='on'
            event(s,'CONTROL_CHANGE',controls=s['controls'])
            return s['controls']
        result=store.mutate(controls)
    elif args.command in ('health','report'):
        result=dashboard.report(store,inventory_for(store,args.inventory),release)
        dashboard.write_report(result,args.output)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return exit_code


if __name__=='__main__':
    try:sys.exit(main())
    except NetworkError as exc:
        print(json.dumps({'status':'NETWORK_BLOCKED','error':str(exc)}));sys.exit(2)
    except (ValueError,KeyError,OSError,RuntimeError) as exc:
        print(json.dumps({'status':'BLOCKED','error':str(exc)}));sys.exit(1)
