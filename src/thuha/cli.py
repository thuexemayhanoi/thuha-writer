"""python -m thuha.cli --help; no paid model APIs or implicit WordPress writes."""
import argparse
import ast
import json
import os
import sys
from pathlib import Path
from .common import ROOT,REPO,digest,load,now,save,validate_inventory
from .store import LocalStore,GitStore,event,validate
from . import audit,coordinator,research,quality,dashboard,matrix,quota
from .adapter import AdapterClient
from .http import HTTP,NetworkError
from .language import LANGUAGES,targets as language_targets
from .publisher import Publisher
from . import pipeline


def inventory_for(store,path):
    state=store.read()
    if state.get('inventory_document'):return store.get_document(state['inventory_document'])
    if path and Path(path).exists():return load(path)
    return audit.snapshot_inventory() # Offline planning view only; it is stale by design.


def live_counts(inv):
    """Per-language live counts, or None when the inventory cannot be trusted for languages."""
    try:return quota.published(inv)
    except ValueError:return None


def main(argv=None):
    p=argparse.ArgumentParser(description='ThuHa Writer V4; production is disabled until separately approved')
    p.add_argument('--remote',action='store_true',help='Use authoritative GitHub CAS; required across computers')
    p.add_argument('--state-dir',default=str(ROOT/'.runtime'))
    p.add_argument('--inventory',default=None,help='Inventory JSON; default is the stored remote inventory, else the committed snapshot')
    p.add_argument('--output',default=str(ROOT/'artifacts'))
    sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('audit');sub.add_parser('validate');sub.add_parser('health');sub.add_parser('report')
    sub.add_parser('coordinator');sub.add_parser('recovery');sub.add_parser('refill');sub.add_parser('credentials')
    sub.add_parser('quota');sub.add_parser('adapter-preflight');sub.add_parser('package')
    q=sub.add_parser('claim');q.add_argument('--session',required=True);q.add_argument('--agent-id',required=True);q.add_argument('--slot',default='auto')
    for command in ('heartbeat','release','submit'):
        q=sub.add_parser(command);q.add_argument('--slot',required=True);q.add_argument('--session',required=True);q.add_argument('--fence',required=True)
        if command=='submit':q.add_argument('--file',required=True)
    q=sub.add_parser('source');q.add_argument('--url',required=True)
    q=sub.add_parser('resume');q.add_argument('--topic-id',required=True)
    q=sub.add_parser('brief');q.add_argument('--limit',type=int,default=10);q.add_argument('--language',choices=LANGUAGES)
    q=sub.add_parser('matrix');q.add_argument('action',choices=['validate','next']);q.add_argument('--language',choices=LANGUAGES);q.add_argument('--limit',type=int,default=10)
    q=sub.add_parser('intake');q.add_argument('--file',required=True)
    q=sub.add_parser('review');q.add_argument('--file',required=True);q.add_argument('--topic-id',required=True)
    q=sub.add_parser('qa');q.add_argument('--topic-id')
    q=sub.add_parser('publisher');q.add_argument('--mode',choices=['dry-run','production','reconcile','verify','drain'],default='dry-run');q.add_argument('--topic-id')
    q=sub.add_parser('controls');q.add_argument('--pause',choices=['on','off']);q.add_argument('--emergency-stop',choices=['on','off'])
    args=p.parse_args(argv)
    store=GitStore() if args.remote else LocalStore(args.state_dir)
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
        if os.environ.get('THUHA_WP_USER') and os.environ.get('THUHA_WP_APPLICATION_PASSWORD'):
            client=AdapterClient(HTTP());client.preflight();inv=audit.inventory_bilingual(client)
        else:inv=audit.inventory()
        result=audit.write_audit(inv,args.output)
        if inv['complete'] and args.remote:
            document=store.put_document(inv)
            store.mutate(lambda s:s.update(inventory_document=document))
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
        inv=inventory_for(store,args.inventory);validate_inventory(inv);note=None
        try:research.refill(store,inv,factory['refill_below'],factory['refill_batch_max'])
        except ValueError as exc:note=str(exc) # e.g. inventory not language-authoritative; claiming itself stays possible
        result=dict(coordinator.claim(store,args.session,args.agent_id,args.slot,factory['lease_seconds'],live_counts(inv),language_targets()))
        if note:result['refill_note']=note
    elif args.command=='heartbeat':result=coordinator.heartbeat(store,args.slot,args.session,args.fence,factory['lease_seconds'])
    elif args.command=='release':result=coordinator.release(store,args.slot,args.session,args.fence)
    elif args.command=='submit':result=coordinator.submit(store,args.slot,args.session,args.fence,load(args.file),policy['maximum_repairs'])
    elif args.command=='source':result=research.capture_source(store,args.url)
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
                'languages':quota.status(store.read(),quota.published(inv),language_targets()),
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
            rows=[]
            for l in ([args.language] if args.language else LANGUAGES):
                rows+=sorted((r for r in load(matrix.matrix_path(l))['rows'] if r['kind']=='NEW' and r['writer_state']=='NEEDS_SOURCE'),key=lambda r:r['write_order'])[:args.limit]
            result={'mode':'read-only','wordpress_writes':0,'next_research':[{k:r[k] for k in ('id','language','title','primary_keyword','category_id','proposed_url','source_requirements','writer_state')} for r in rows]}
    elif args.command=='intake':result={'admitted':research.intake(store,load(args.file),inventory_for(store,args.inventory),factory['refill_batch_max'],language_targets())}
    elif args.command=='refill':result=research.refill(store,inventory_for(store,args.inventory),factory['refill_below'],factory['refill_batch_max'],language_targets())
    elif args.command=='review':
        value=load(args.file)
        # Setting a string ID is attribution, not authentication; enforced GitHub
        # path/branch controls and environment review are still required to go live.
        if value.get('reviewer_id') not in policy['trusted_reviewers'] or value.get('reviewer_id')!=os.environ.get('THUHA_REVIEWER_ID'):
            raise ValueError('Authorized independent reviewer identity required')
        if value.get('article_sha')!=store.read()['submissions'][args.topic_id]['article_sha']:raise ValueError('Review references different revision')
        document=store.put_document(value)
        store.mutate(lambda s:s.setdefault('reviews',{}).update({args.topic_id:document}))
        result={'review_document':document}
    elif args.command=='qa':
        inv=inventory_for(store,args.inventory)
        ids=[args.topic_id] if args.topic_id else [k for k,v in store.read()['topics'].items() if v['status'] in ('DRAFT_READY','NEEDS_REPAIR')]
        result={'results':{}}
        for tid in ids:
            try:
                value=quality.run_qa(store,tid,inv,policy,facts)
                result['results'][tid]=value
                if value['status']!='PASS':exit_code=max(exit_code,1)
            except (ValueError,OSError,RuntimeError,KeyError) as exc:
                result['results'][tid]={'status':'BLOCKED','error':str(exc),'kind':'INFRASTRUCTURE' if isinstance(exc,(NetworkError,OSError)) else 'STATE_OR_CONTRACT'}
                exit_code=max(exit_code,2 if isinstance(exc,(NetworkError,OSError)) else 1)
    elif args.command=='publisher':
        pub=Publisher(store,AdapterClient(HTTP(allow_write=args.mode in ('production','drain'))),inventory_for(store,args.inventory),policy,facts)
        if args.mode=='dry-run':result=pub.dry_run()
        elif args.mode=='drain':result=pipeline.drain(pub)
        elif args.mode=='production':
            if not args.topic_id:raise ValueError('Explicit single topic ID required for pilot')
            result=pub.publish(args.topic_id)
        else:
            ids=[args.topic_id] if args.topic_id else list(store.read()['intents'])
            result={'receipts':{tid:pub.reconcile(tid) for tid in ids}}
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
