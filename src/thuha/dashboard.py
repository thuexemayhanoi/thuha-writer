from collections import Counter
from pathlib import Path
from .common import ROOT,REPO,now,age,save,load
from .coordinator import SLOTS,timestamp
from .language import LANGUAGES,screen_alt,targets as language_targets
from . import ledger,quota

STATUSES=('RESEARCH','PLANNED','CLAIMED','DRAFT_READY','WAITING_DATA','READY','NEEDS_REPAIR','NEEDS_REVIEW','BLOCKED','HELD','PUBLISHING','PUBLISHED')


def language_view(s,inv,targets):
    """Per-language progress. Counts come only from an authoritative inventory; otherwise they are unknown, not zero."""
    try:counts=quota.published(inv)
    except ValueError as exc:return None,str(exc)
    counts=quota.effective(s,counts,{x['id'] for x in inv.get('items',[])}) # factory posts WordPress confirmed after the inventory was read
    state=quota.status(s,counts,targets)
    out={}
    for lang in LANGUAGES:
        topics=[t for t in s['topics'].values() if t['language']==lang]
        states=Counter(t['status'] for t in topics)
        for name in STATUSES:states.setdefault(name,0)
        receipts=[r for k,r in s['receipts'].items() if s['topics'].get(k,{}).get('language')==lang]
        out[lang]={**state[lang],'factory_published_receipts':len(receipts),'states':dict(states),
                   'needs_source_or_research':[r for r in s['research_requests'].values() if r.get('language')==lang and r['status']=='AWAITING_EXTERNAL_RESEARCH']}
    return out,None


QUEUE_COLUMNS=('waiting_data','awaiting_review','awaiting_qa','qa_pass','publishing','published','needs_repair','held_or_unknown')


def queue_view(s):
    """What sits where in the shared queue, per language. Nothing here is a count of published posts."""
    out={}
    for lang in LANGUAGES:
        rows={c:[] for c in QUEUE_COLUMNS}
        for tid,t in sorted(s['topics'].items()):
            if t['language']!=lang or tid not in s['submissions']:continue
            status=t['status']
            if status=='WAITING_DATA':rows['waiting_data'].append(tid) # stored, complete but for data that does not exist yet; never QA pass
            elif status=='DRAFT_READY':rows['awaiting_qa' if tid in s.get('reviews',{}) else 'awaiting_review'].append(tid)
            elif status=='READY':rows['qa_pass'].append(tid)
            elif status=='PUBLISHING':rows['publishing'].append(tid)
            elif status=='PUBLISHED':rows['published'].append(tid)
            elif status in ('NEEDS_REPAIR','NEEDS_REVIEW'):rows['needs_repair'].append(tid)
            elif status in ('BLOCKED','HELD'):rows['held_or_unknown'].append(tid)
        out[lang]=rows
    return out


def post_checks(s):
    rows={}
    for tid,intent in s['intents'].items():
        if intent.get('phase')=='PUBLISHED':rows[tid]=intent.get('post_check',{'status':'PENDING','attempts':0})
    return {'counts':dict(Counter(v['status'] for v in rows.values())),
            'warnings':{k:{'attempts':v['attempts'],'problem':v.get('problem')} for k,v in rows.items() if v['status'] in ('WARNING','FAILED_FINAL')},
            'note':'Public-page checks run after publication, back off and retry; they never stop the queue.'}


def handoff(store,live=None):
    """Is the session ledger committed in this checkout already part of the shared ledger?

    `live` is a raw shared ledger to compare against (an offline snapshot); by default the store's own ledger is used.
    """
    path=ROOT/'data/state/factory.json'
    if not path.exists() or (live is None and not hasattr(store,'raw')):return None
    try:
        raw=live if live is not None else store.raw()[0]
        verdict=ledger.plan(raw,load(path))
    except Exception as exc:return {'status':'UNKNOWN','reason':str(exc)[:200]}
    return {'status':verdict['status'],'session_ledger_version':verdict.get('handoff_version'),'shared_ledger_version':verdict.get('live_version'),
            'reasons':verdict['reasons']}


def media_blockers(inv):
    out=[]
    for lang in LANGUAGES:
        usable=[m for m in inv.get('media',[]) if str(m.get('alt_text','')).strip() and not screen_alt(lang,str(m['alt_text']))]
        if not usable:out.append('NEEDS_MEDIA: no image in the media library has '+lang+' alt text, so no '+lang+' article can pass QA (featured image rule)')
    return out


def report(store,inv,release,targets=None,live_ledger=None):
    s=store.read();counts=Counter(t['status'] for t in s['topics'].values())
    for status in STATUSES:counts.setdefault(status,0)
    targets=targets or language_targets()
    languages,language_error=language_view(s,inv,targets)
    verified=inv.get('counts',{}).get('live_verified_posts',0)
    result={'generated_at':now(),'wordpress_published':inv.get('counts',{}).get('posts'),
       'targets':targets,'priority':list(LANGUAGES),'languages':languages,
       'inventory_language_source':inv.get('language_source','UNKNOWN'),
       'state_backend':('git-branch:'+store.branch if hasattr(store,'root') else 'github-factory-state') if store.durable_remote else 'local-offline-snapshot',
       'wordpress_pages':inv.get('counts',{}).get('pages'),'inventory_complete':inv.get('complete',False),
       'inventory_age_seconds':round(age(inv['captured_at'])), 'site_live_verified_posts':verified,
       'factory_published_receipts':len(s['receipts']),
       'queue':queue_view(s),'waiting_data':{k:v.get('waiting_for',[]) for k,v in sorted(s['topics'].items()) if v['status']=='WAITING_DATA'},
       'held':{k:v['held']['reason'] for k,v in sorted(s['topics'].items()) if v['status']=='HELD' and v.get('held')},'post_checks':post_checks(s),'open_alerts':[a for a in s.get('alerts',[]) if not a.get('acknowledged')],
       'handoff':handoff(store,live_ledger),
       'states':dict(counts),'production_enabled':release['enabled'],'languages_enabled':release.get('languages_enabled',[]),
       'adapter':s.get('adapter') or {'status':'NOT_VERIFIED','code':'BLOCKED_ADAPTER_NOT_DEPLOYED'},
       'research_requests':list(s['research_requests'].values()),'published_articles':list(s['receipts'].values()),
       'slots':{slot:{'status':'LEASE_PRESENT' if slot in s['leases'] and s['leases'][slot]['expires_at']>timestamp() else 'AVAILABLE',
                'ai_execution':'NOT_OBSERVED',**({'lease':s['leases'][slot]} if slot in s['leases'] else {})} for slot in SLOTS},
       'qa':dict(Counter(x['status'] for x in s['qa'].values())),
       'publisher_uncertain':[k for k,v in s['intents'].items() if v['phase'] not in ('PUBLISHED',)+quota.CLOSED_PHASES],
       'closed_intents':{k:v['phase'] for k,v in s['intents'].items() if v['phase'] in quota.CLOSED_PHASES},
       'agent_attribution':dict(Counter(x.get('agent_id','UNKNOWN') for x in s['receipts'].values())),
       'attribution_note':'Existing WordPress articles have UNKNOWN creator attribution unless a matching factory receipt exists.',
       'blockers':[]}
    result['github_actions']={'status':'UNKNOWN','runs':[]}
    if store.durable_remote and hasattr(store,'api'):
        try:
            runs=store.api.request('GET','/repos/'+REPO+'/actions/runs?per_page=10').get('workflow_runs',[])
            result['github_actions']={'status':'READBACK','runs':[
                {k:x.get(k) for k in ('id','name','head_sha','status','conclusion','html_url')} for x in runs]}
        except Exception:
            result['github_actions']={'status':'UNKNOWN','runs':[],'reason':'Actions metadata read was unavailable; no success inferred'}
    if not release['approved']:result['blockers'].append('Separate owner go-live approval outstanding')
    if not release.get('languages_enabled'):result['blockers'].append('No language enabled in the release (production stays OFF)')
    if result['adapter'].get('status')!='VERIFIED':result['blockers'].append('BLOCKED_ADAPTER_NOT_DEPLOYED: no successful live adapter preflight is recorded')
    if language_error:result['blockers'].append('Language counts unknown: '+language_error)
    if not load(ROOT/'config/qa.json')['trusted_reviewers']:result['blockers'].append('No independent reviewer roster configured')
    if not release.get('cross_publisher_coordination_verified'):result['blockers'].append('Other publisher coordination not verified')
    if not s['leases']:result['blockers'].append('No external AI session lease; Actions do not generate prose')
    if not inv.get('complete'):result['blockers'].append('Inventory incomplete; new topics and publisher blocked')
    if age(inv['captured_at'])>21600:result['blockers'].append('Inventory stale; run fresh audit')
    if result['publisher_uncertain']:result['blockers'].append('Unknown publication outcomes need read-only reconciliation')
    if result['open_alerts']:result['blockers'].append('Integrity alert(s) open: '+', '.join(sorted({a['topic_id'] for a in result['open_alerts']}))+'; new publications stop until acknowledged')
    if result['handoff'] and result['handoff']['status']=='FAST_FORWARD':result['blockers'].append('The session ledger in this checkout is not in the shared ledger yet: the queue job (or `promote --apply`) hands it over')
    if result['handoff'] and result['handoff']['status'] in ('DIVERGED','INCONSISTENT','INVALID_LEDGER'):result['blockers'].append('Session ledger cannot be handed over ('+result['handoff']['status']+'): sync the session branch from the shared ledger')
    if inv.get('media_library')=='complete':result['blockers'].extend(media_blockers(inv)) # an inventory that listed only featured images says nothing about the library
    if result['waiting_data']:
        by_code=Counter(c for codes in result['waiting_data'].values() for c in codes)
        ready=[k for k,v in result['waiting_data'].items() if not v]
        result['blockers'].append(str(len(result['waiting_data']))+' draft(s) wait for data ('+', '.join(c+' x'+str(n) for c,n in sorted(by_code.items()))+')'
                                  +('; '+str(len(ready))+' now have it and wait for a writer to finish them' if ready else '')+': '+', '.join(list(result['waiting_data'])[:12]))
    awaiting=[t for lang in LANGUAGES for t in result['queue'][lang]['awaiting_review']]
    if awaiting:result['blockers'].append(str(len(awaiting))+' draft(s) wait for an independent review before QA: '+', '.join(awaiting[:12]))
    return result


def write_report(value,directory):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    save(directory/'dashboard.json',value)
    text='# ThuHa Writer bilingual dashboard\n\n'
    text+='Generated: '+value['generated_at']+'\n\n'
    for key in ('wordpress_published','site_live_verified_posts','factory_published_receipts','inventory_language_source','production_enabled','state_backend'):
        text+='- '+key+': '+str(value[key])+'\n'
    text+='\n## Languages (Vietnamese first)\n\n| Language | Target | Live published | Unresolved intents | Remaining | Receipts |\n|---|---|---|---|---|---|\n'
    for lang in value['priority']:
        row=(value['languages'] or {}).get(lang)
        text+='| '+lang+' | '+str(value['targets'][lang])+' | '+(' | '.join(str(row[k]) for k in ('published_live','unresolved_intents','remaining','factory_published_receipts')) if row else 'UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN')+' |\n'
    text+='\n## Shared queue (not published posts)\n\n| Language | Waiting for data | Awaiting review | Awaiting QA | QA pass | Publishing | Published | Needs repair | Held / unknown |\n|---|---|---|---|---|---|---|---|---|\n'
    for lang in value['priority']:
        q=value['queue'][lang]
        text+='| '+lang+' | '+' | '.join(str(len(q[k])) for k in QUEUE_COLUMNS)+' |\n'
    checks=value['post_checks']
    text+='\nPublic-page checks after publication: '+(', '.join(k+' '+str(v) for k,v in sorted(checks['counts'].items())) or 'none yet')+'. '+checks['note']+'\n'
    for tid,w in checks['warnings'].items():text+='- warning '+tid+' (attempt '+str(w['attempts'])+'): '+str(w['problem'])+'\n'
    if value['handoff']:text+='\nSession ledger hand-over: '+value['handoff']['status']+' (session v'+str(value['handoff']['session_ledger_version'])+', shared v'+str(value['handoff']['shared_ledger_version'])+')\n'
    text+='\nAdapter: '+str(value['adapter'].get('status'))+' (live status is PENDING until a credentialed preflight succeeds)\n'
    text+='\n## Writer slots\n\n| Slot | Lease state | AI execution |\n|---|---|---|\n'
    for slot,value_slot in value['slots'].items():text+='| '+slot+' | '+value_slot['status']+' | NOT_OBSERVED |\n'
    text+='\n## Blockers\n\n'+''.join('- '+x+'\n' for x in value['blockers'])
    text+='\nExisting articles are not attributed to ChatGPT or Claude without provenance. Live URL verification is not Google index verification.\n'
    text+='\n## GitHub Actions\n\nStatus: '+value['github_actions']['status']+'\n\n'
    for run in value['github_actions']['runs']:
        text+='- '+str(run['id'])+': '+str(run['status'])+' / '+str(run['conclusion'])+'\n'
    (directory/'dashboard.md').write_text(text.rstrip()+'\n')
