from collections import Counter
from pathlib import Path
from .common import ROOT,REPO,now,age,save,load
from .coordinator import SLOTS,timestamp
from .language import LANGUAGES,targets as language_targets
from . import quota

STATUSES=('RESEARCH','PLANNED','CLAIMED','DRAFT_READY','READY','NEEDS_REPAIR','NEEDS_REVIEW','BLOCKED','PUBLISHING','VERIFIED')


def language_view(s,inv,targets):
    """Per-language progress. Counts come only from an authoritative inventory; otherwise they are unknown, not zero."""
    try:counts=quota.published(inv)
    except ValueError as exc:return None,str(exc)
    state=quota.status(s,counts,targets)
    out={}
    for lang in LANGUAGES:
        topics=[t for t in s['topics'].values() if t['language']==lang]
        states=Counter(t['status'] for t in topics)
        for name in STATUSES:states.setdefault(name,0)
        receipts=[r for k,r in s['receipts'].items() if s['topics'].get(k,{}).get('language')==lang]
        out[lang]={**state[lang],'factory_verified_receipts':len(receipts),'states':dict(states),
                   'needs_source_or_research':[r for r in s['research_requests'].values() if r.get('language')==lang and r['status']=='AWAITING_EXTERNAL_RESEARCH']}
    return out,None


def report(store,inv,release,targets=None):
    s=store.read();counts=Counter(t['status'] for t in s['topics'].values())
    for status in STATUSES:counts.setdefault(status,0)
    targets=targets or language_targets()
    languages,language_error=language_view(s,inv,targets)
    verified=inv.get('counts',{}).get('live_verified_posts',0)
    result={'generated_at':now(),'wordpress_published':inv.get('counts',{}).get('posts'),
       'targets':targets,'priority':list(LANGUAGES),'languages':languages,
       'inventory_language_source':inv.get('language_source','UNKNOWN'),
       'state_backend':'github-factory-state' if store.durable_remote else 'local-offline-snapshot',
       'wordpress_pages':inv.get('counts',{}).get('pages'),'inventory_complete':inv.get('complete',False),
       'inventory_age_seconds':round(age(inv['captured_at'])), 'site_live_verified_posts':verified,
       'factory_verified_receipts':len(s['receipts']),
       'states':dict(counts),'production_enabled':release['enabled'],'languages_enabled':release.get('languages_enabled',[]),
       'adapter':s.get('adapter') or {'status':'NOT_VERIFIED','code':'BLOCKED_ADAPTER_NOT_DEPLOYED'},
       'research_requests':list(s['research_requests'].values()),'published_articles':list(s['receipts'].values()),
       'slots':{slot:{'status':'LEASE_PRESENT' if slot in s['leases'] and s['leases'][slot]['expires_at']>timestamp() else 'AVAILABLE',
                'ai_execution':'NOT_OBSERVED',**({'lease':s['leases'][slot]} if slot in s['leases'] else {})} for slot in SLOTS},
       'qa':dict(Counter(x['status'] for x in s['qa'].values())),
       'publisher_uncertain':[k for k,v in s['intents'].items() if v['phase'] not in ('VERIFIED',)+quota.CLOSED_PHASES],
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
    return result


def write_report(value,directory):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    save(directory/'dashboard.json',value)
    text='# ThuHa Writer bilingual dashboard\n\n'
    text+='Generated: '+value['generated_at']+'\n\n'
    for key in ('wordpress_published','site_live_verified_posts','factory_verified_receipts','inventory_language_source','production_enabled'):
        text+='- '+key+': '+str(value[key])+'\n'
    text+='\n## Languages (Vietnamese first)\n\n| Language | Target | Live published | Unresolved intents | Remaining | Receipts |\n|---|---|---|---|---|---|\n'
    for lang in value['priority']:
        row=(value['languages'] or {}).get(lang)
        text+='| '+lang+' | '+str(value['targets'][lang])+' | '+(' | '.join(str(row[k]) for k in ('published_live','unresolved_intents','remaining','factory_verified_receipts')) if row else 'UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN')+' |\n'
    text+='\nAdapter: '+str(value['adapter'].get('status'))+' (live status is PENDING until a credentialed preflight succeeds)\n'
    text+='\n## Writer slots\n\n| Slot | Lease state | AI execution |\n|---|---|---|\n'
    for slot,value_slot in value['slots'].items():text+='| '+slot+' | '+value_slot['status']+' | NOT_OBSERVED |\n'
    text+='\n## Blockers\n\n'+''.join('- '+x+'\n' for x in value['blockers'])
    text+='\nExisting articles are not attributed to ChatGPT or Claude without provenance. Live URL verification is not Google index verification.\n'
    text+='\n## GitHub Actions\n\nStatus: '+value['github_actions']['status']+'\n\n'
    for run in value['github_actions']['runs']:
        text+='- '+str(run['id'])+': '+str(run['status'])+' / '+str(run['conclusion'])+'\n'
    (directory/'dashboard.md').write_text(text.rstrip()+'\n')
