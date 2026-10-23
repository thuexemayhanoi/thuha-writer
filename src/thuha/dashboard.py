from collections import Counter
from pathlib import Path
from .common import ROOT,REPO,now,age,save,load
from .coordinator import SLOTS,timestamp


def report(store,inv,release):
    s=store.read();counts=Counter(t['status'] for t in s['topics'].values())
    for status in ('RESEARCH','PLANNED','CLAIMED','DRAFT_READY','READY','NEEDS_REPAIR','NEEDS_REVIEW','BLOCKED','PUBLISHING','VERIFIED'):
        counts.setdefault(status,0)
    verified=inv.get('counts',{}).get('live_verified_posts',0)
    result={'generated_at':now(),'wordpress_published':inv.get('counts',{}).get('posts'),
       'state_backend':('git-branch:'+store.branch if hasattr(store,'root') else 'github-factory-state') if store.durable_remote else 'local-offline-snapshot',
       'wordpress_pages':inv.get('counts',{}).get('pages'),'inventory_complete':inv.get('complete',False),
       'inventory_age_seconds':round(age(inv['captured_at'])), 'site_live_verified_posts':verified,
       'remaining_to_2000_site_verified':max(0,2000-verified),'factory_verified_receipts':len(s['receipts']),
       'factory_remaining_to_2000':max(0,2000-len(s['receipts'])),
       'states':dict(counts),'production_enabled':release['enabled'],
       'research_requests':list(s['research_requests'].values()),'published_articles':list(s['receipts'].values()),
       'slots':{slot:{'status':'LEASE_PRESENT' if slot in s['leases'] and s['leases'][slot]['expires_at']>timestamp() else 'AVAILABLE',
                'ai_execution':'NOT_OBSERVED',**({'lease':s['leases'][slot]} if slot in s['leases'] else {})} for slot in SLOTS},
       'qa':dict(Counter(x['status'] for x in s['qa'].values())),
       'publisher_uncertain':[k for k,v in s['intents'].items() if v['phase']!='VERIFIED'],
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
    text='# ThuHa Writer V4 dashboard\n\n'
    text+='Generated: '+value['generated_at']+'\n\n'
    for key in ('wordpress_published','site_live_verified_posts','factory_verified_receipts','remaining_to_2000_site_verified','production_enabled'):
        text+='- '+key+': '+str(value[key])+'\n'
    text+='\n## Writer slots\n\n| Slot | Lease state | AI execution |\n|---|---|---|\n'
    for slot,value_slot in value['slots'].items():text+='| '+slot+' | '+value_slot['status']+' | NOT_OBSERVED |\n'
    text+='\n## Blockers\n\n'+''.join('- '+x+'\n' for x in value['blockers'])
    text+='\nExisting articles are not attributed to ChatGPT or Claude without provenance. Live URL verification is not Google index verification.\n'
    text+='\n## GitHub Actions\n\nStatus: '+value['github_actions']['status']+'\n\n'
    for run in value['github_actions']['runs']:
        text+='- '+str(run['id'])+': '+str(run['status'])+' / '+str(run['conclusion'])+'\n'
    (directory/'dashboard.md').write_text(text.rstrip()+'\n')
