"""Source-backed admission; refill requests never pretend to be researched prose."""
from .common import age, digest, now, norm, urlkey, category_path, validate_inventory
from .http import HTTP, safe_public_url, safe_url_shape
from .language import LANGUAGES, TOPIC_ID, check, post_url, split_url, url_language, targets as language_targets
from .quota import published, topics_needed
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


EXTERNAL_FETCHERS=('parallel-web-fetch','claude-webfetch','github-actions-runner')


def capture_external_source(store,url,record,max_record_age=86400):
    """Record evidence fetched by an authorized external fetcher.

    The writer container may be denied direct egress to research origins. A
    fetcher such as the Parallel web_fetch tool performs the real HTTP request;
    its result is saved as a record and converted into a source snapshot here.
    The snapshot is labelled with its capture method; nothing is inferred from
    an empty, failed or mismatched record and no content verdict is fabricated.
    """
    safe_url_shape(url) # The external fetcher resolved the host; this container may have no DNS.
    if record.get('url')!=url:raise ValueError('External fetch record is for a different URL')
    if record.get('fetcher') not in EXTERNAL_FETCHERS:raise ValueError('Unknown external fetcher')
    if record.get('status')!='ok' or record.get('error'):raise ValueError('External fetch did not succeed; mark the source blocked')
    content=str(record.get('content') or '')
    if len(content.split())<40:raise ValueError('External fetch content too thin to count as evidence')
    if not 0<=age(record['fetched_at'])<=max_record_age:raise ValueError('External fetch record is stale or future-dated')
    snapshot={'url':url,'checked_at':now(),'http_status':200,'response_sha256':digest(content.encode()),
              'excerpt':' '.join(content.split()[:20]),'page_title':str(record.get('title') or ''),
              'content_type':'text/markdown; external fetch','capture_method':'external-fetcher',
              'fetcher':record['fetcher'],'fetched_at':record['fetched_at'],
              'http_status_basis':'successful external fetch returned document content'}
    return {'document':store.put_document(snapshot),'url':url,'capture_method':'external-fetcher'}


def item_language(item):
    """Language of an inventory item or queued topic; URL namespace when untagged."""
    if item.get('language') in LANGUAGES:
        return item['language']
    for key in ('url','canonical','proposed_url'):
        if item.get(key):
            try:return url_language(item[key]) or 'en'
            except ValueError:continue
    return 'en'


def collisions(topic,inv,queue):
    """Duplicates by URL/slug across both languages; intent and title only within one language."""
    hits=[]
    lang=topic['language']
    slug=split_url(topic['proposed_url'])[1]
    for old in inv['items']+list(queue):
        sameurl=any(urlkey(x)==urlkey(topic['proposed_url']) for x in [old.get('url'),old.get('canonical'),old.get('proposed_url')] if x)
        # A WordPress post slug is unique across languages even when /vi/ keeps the URLs apart.
        same_slug=bool(old.get('slug') and old['slug']==slug)
        if not same_slug and old.get('proposed_url'):
            try:same_slug=split_url(old['proposed_url'])[1]==slug
            except ValueError:pass
        same_language=item_language(old)==lang
        exact_intent=bool(same_language and old.get('search_intent') not in (None,'UNREVIEWED') and norm(old['search_intent'])==norm(topic['search_intent']))
        a=set(norm(topic['proposed_title']).split());b=set(norm(old.get('title',old.get('proposed_title',''))).split())
        similar=bool(same_language and len(a&b)/max(1,len(a|b))>=.72)
        if sameurl or same_slug or exact_intent or similar:
            hits.append({'id':old.get('id',old.get('topic_id')),'url':old.get('url',old.get('proposed_url')),
                         'reason':'URL' if sameurl else 'SLUG' if same_slug else 'INTENT' if exact_intent else 'TITLE_REVIEW'})
    return hits


def validate_candidate(candidate,inv,queue,store,max_age=2592000):
    validate_inventory(inv)
    required=['topic_id','language','primary_keyword','search_intent','proposed_title','category_id','category_path',
              'cluster','proposed_url','sources','intent_review']
    if any(not candidate.get(k) for k in required):raise ValueError('Incomplete topic contract')
    lang=check(candidate['language'])
    match=TOPIC_ID.fullmatch(candidate['topic_id'])
    if not match or match.group(1).lower()!=lang:raise ValueError('Topic ID must be TH-VI-#### or TH-EN-#### and match the language')
    if category_path(candidate['category_id'],inv['categories'])!=candidate['category_path']:
        raise ValueError('Category ancestry must match live taxonomy exactly')
    by_id={c['id']:c for c in inv['categories']}
    if any(by_id[i].get('language')!=lang for i in candidate['category_path']):
        raise ValueError('Every category in the path must be verified as '+lang+'; a category of another language is not a substitute')
    url_lang,slug=split_url(candidate['proposed_url'])
    if url_lang!=lang or candidate['proposed_url']!=post_url(lang,slug):
        raise ValueError('Proposed URL must be a clean slug inside the '+lang+' URL namespace of the exact site')
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


def intake(store,candidates,inv,batch_max=100,targets=None):
    if not 1<=len(candidates)<=batch_max:raise ValueError('Research batch size out of range')
    targets=targets or language_targets()
    counts=published(inv)
    def transaction(state):
        added={lang:sum(c.get('language')==lang for c in candidates) for lang in LANGUAGES}
        for lang,n in added.items():
            if n>topics_needed(state,counts,targets,lang):raise ValueError('Topic capacity reached for '+lang+' (target minus live posts minus open topics)')
        admitted=[]
        for candidate in candidates:
            tid=candidate['topic_id']
            if tid in state['topics']:raise ValueError('Topic ID already exists')
            validate_candidate(candidate,inv,state['topics'].values(),store)
            state['topics'][tid]={**candidate,'status':'PLANNED','admitted_at':now()}
            admitted.append(tid)
        for request in state['research_requests'].values():
            ids=[t for t in admitted if state['topics'][t]['language']==request.get('language')]
            if request['status']=='AWAITING_EXTERNAL_RESEARCH' and ids:
                request.update(status='FULFILLED',admitted_topic_ids=ids,completed_at=now())
        event(state,'RESEARCH_INTAKE',topic_ids=admitted)
        return admitted
    return store.mutate(transaction)


def refill(store,inv,below=30,batch_max=100,targets=None):
    """One outstanding research request at a time, Vietnamese before English.

    English is asked for only when Vietnamese needs nothing more (its open topics
    already cover the ceiling or it holds enough PLANNED topics).
    """
    validate_inventory(inv)
    targets=targets or language_targets()
    counts=published(inv)
    def transaction(state):
        reasons={}
        # Priority order decides which language is served; an outstanding English request (for example one
        # migrated from schema 4) must not stop a Vietnamese request from being opened first.
        for lang in LANGUAGES:
            waiting=[r for r in state['research_requests'].values() if r['status']=='AWAITING_EXTERNAL_RESEARCH' and r.get('language')==lang]
            if waiting:return waiting[0]
            planned=sum(x['status']=='PLANNED' and x['language']==lang for x in state['topics'].values())
            if planned>=below:reasons[lang]={'needed':False,'planned':planned};continue
            capacity=min(batch_max,topics_needed(state,counts,targets,lang))
            if capacity<=0:reasons[lang]={'needed':False,'reason':'CAPACITY','planned':planned};continue
            request={'request_id':'research-'+lang+'-'+digest([digest(inv),lang,len(state['topics'])])[:16],
                     'language':lang,'created_at':now(),'status':'AWAITING_EXTERNAL_RESEARCH','maximum_topics':capacity,
                     'inventory_sha256':digest(inv),'planned':planned,'runtime':'External authorized AI session required'}
            state['research_requests'][request['request_id']]=request
            event(state,'REFILL_REQUEST',request_id=request['request_id'],language=lang)
            return request
        return {'needed':False,'languages':reasons}
    return store.mutate(transaction)
