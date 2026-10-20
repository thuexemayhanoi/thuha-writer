"""Source-backed admission; refill requests never pretend to be researched prose."""
import re
from .common import SITE, ROOT, age, digest, now, norm, urlkey, category_path, validate_inventory
from .http import HTTP, safe_public_url
from .store import event


def capture_source(store,url):
    safe_public_url(url)
    data,headers,status=HTTP().request(url)
    from .audit import parse
    page=parse(data.decode('utf-8',errors='replace'))
    # Keep only bounded evidence snapshots, not entire copyrighted websites.
    snapshot={'url':url,'checked_at':now(),'http_status':status,'response_sha256':digest(data),
              'excerpt':' '.join(' '.join(page.text).split()[:20]),'page_title':page.title,
              'content_type':headers.get('Content-Type',headers.get('content-type'))}
    return {'document':store.put_document(snapshot),'url':url}


def collisions(topic,inv,queue):
    hits=[]
    for old in inv['items']+list(queue):
        sameurl=any(urlkey(x)==urlkey(topic['proposed_url']) for x in [old.get('url'),old.get('canonical'),old.get('proposed_url')] if x)
        same_slug=bool(old.get('slug') and old['slug']==topic['proposed_url'].removeprefix(SITE+'/').rstrip('/'))
        exact_intent=bool(old.get('search_intent') not in (None,'UNREVIEWED') and norm(old['search_intent'])==norm(topic['search_intent']))
        a=set(norm(topic['proposed_title']).split());b=set(norm(old.get('title',old.get('proposed_title',''))).split())
        similar=len(a&b)/max(1,len(a|b))>=.72
        if sameurl or same_slug or exact_intent or similar:
            hits.append({'id':old.get('id',old.get('topic_id')),'url':old.get('url',old.get('proposed_url')),
                         'reason':'URL' if sameurl else 'SLUG' if same_slug else 'INTENT' if exact_intent else 'TITLE_REVIEW'})
    return hits


def validate_candidate(candidate,inv,queue,store,max_age=2592000):
    validate_inventory(inv)
    required=['topic_id','primary_keyword','search_intent','proposed_title','category_id','category_path',
              'cluster','proposed_url','sources','intent_review']
    if any(not candidate.get(k) for k in required):raise ValueError('Incomplete topic contract')
    if not re.fullmatch(r'TH-\d{6}',candidate['topic_id']):raise ValueError('Invalid topic ID')
    if category_path(candidate['category_id'],inv['categories'])!=candidate['category_path']:
        raise ValueError('Category ancestry must match live taxonomy exactly')
    slug=candidate['proposed_url'].removeprefix(SITE+'/').rstrip('/')
    if candidate['proposed_url']!=SITE+'/'+slug+'/' or not re.fullmatch('[a-z0-9]+(?:-[a-z0-9]+)*',slug):
        raise ValueError('Proposed URL must be a clean English slug on the exact site')
    sources=candidate['sources']
    if not 1<=len(sources)<=10:raise ValueError('Require bounded primary-source evidence')
    for ref in sources:
        evidence=store.get_document(ref['document'])
        if evidence.get('url')!=ref['url'] or evidence.get('http_status')!=200 or not 0<=age(evidence['checked_at'])<=max_age:
            raise ValueError('Source capture missing, stale or unsuccessful')
        if not ref.get('supports') or len(ref['supports'])<20:raise ValueError('Explain which claim the source supports')
    verdict=candidate['intent_review']
    if verdict.get('verdict')!='DISTINCT' or verdict.get('inventory_sha256')!=digest(inv) or not verdict.get('reviewer_id') or not verdict.get('rationale'):
        raise ValueError('Fresh semantic intent review required; keyword matching alone is insufficient')
    if collisions(candidate,inv,queue):raise ValueError('Duplicate or cannibalization review required')
    return True


def intake(store,candidates,inv,batch_max=100):
    if not 1<=len(candidates)<=batch_max:raise ValueError('Research batch size out of range')
    def transaction(state):
        if len(state['topics'])+len(candidates)>2000:raise ValueError('Topic capacity reached')
        admitted=[]
        for candidate in candidates:
            tid=candidate['topic_id']
            if tid in state['topics']:raise ValueError('Topic ID already exists')
            validate_candidate(candidate,inv,state['topics'].values(),store)
            state['topics'][tid]={**candidate,'status':'PLANNED','admitted_at':now()}
            admitted.append(tid)
        for request in state['research_requests'].values():
            if request['status']=='AWAITING_EXTERNAL_RESEARCH':
                request.update(status='FULFILLED',admitted_topic_ids=admitted,completed_at=now())
        event(state,'RESEARCH_INTAKE',topic_ids=admitted)
        return admitted
    return store.mutate(transaction)


def refill(store,inv,below=30,batch_max=100):
    validate_inventory(inv)
    def transaction(state):
        planned=sum(x['status']=='PLANNED' for x in state['topics'].values())
        if planned>=below:return {'needed':False,'planned':planned}
        outstanding=[r for r in state['research_requests'].values() if r['status']=='AWAITING_EXTERNAL_RESEARCH']
        if outstanding:return outstanding[0]
        queued=sum(x['status']!='VERIFIED' for x in state['topics'].values())
        capacity=min(batch_max,2000-len(state['topics']),max(0,2000-inv['counts']['posts']-queued))
        if capacity<=0:return {'needed':False,'reason':'CAPACITY'}
        request={'request_id':'research-'+digest([digest(inv),len(state['topics'])])[:16],
                 'created_at':now(),'status':'AWAITING_EXTERNAL_RESEARCH','maximum_topics':capacity,
                 'inventory_sha256':digest(inv),'planned':planned,'runtime':'External authorized AI session required'}
        state['research_requests'][request['request_id']]=request
        event(state,'REFILL_REQUEST',request_id=request['request_id'])
        return request
    return store.mutate(transaction)
