from collections import Counter
from pathlib import Path
from .common import now,age,save
from .coordinator import SLOTS,timestamp


def report(store,inv,release):
    s=store.read();counts=Counter(t['status'] for t in s['topics'].values())
    verified=inv.get('counts',{}).get('live_verified_posts',0)
    result={'generated_at':now(),'wordpress_published':inv.get('counts',{}).get('posts'),
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
    if not release['approved']:result['blockers'].append('Separate owner go-live approval outstanding')
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
    (directory/'dashboard.md').write_text(text)
