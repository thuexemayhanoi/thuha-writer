"""V5 writer-session runtime helpers: read-only kits, non-mutating prechecks,
source-backed candidate admission and the cycle report.

An authorized Claude session is the AI runtime. These helpers only package
state the session needs and run the *same* QA policy before a submission so a
writer does not burn bounded repairs on mechanical faults. Nothing here writes
to WordPress or lowers a gate.
"""
import re
from collections import Counter
from .common import SITE, ROOT, digest, load, now, norm, urlkey, category_path, validate_inventory
from .coordinator import SLOTS, timestamp
from .quality import evaluate, REVIEW_CHECKS
from .research import capture_external_source, collisions, intake

ARTICLE_FIELDS=('topic_id','session','agent_id','source_commit','language','title','body_html','seo_title',
                'meta_description','focus_keyword','canonical','category_id','featured_media','sources','business_claims')


def link_catalogue(inv,limit=None):
    """Live-verified same-site URLs a writer may link to; nothing else passes QA."""
    rows=[]
    for item in inv['items']:
        check=item.get('public_check',{})
        if check.get('http_status')!=200 or check.get('canonicals') not in (None,[item['url']]):continue
        rows.append({'id':item['id'],'type':item['type'],'url':urlkey(item['url'])+'/','title':item.get('title'),
                     'categories':item.get('categories',[]),'words':item.get('word_count')})
    rows.sort(key=lambda r:(r['type']!='posts',r['id']))
    return rows[:limit] if limit else rows


def media_catalogue(inv):
    return [m for m in inv.get('media',[]) if str(m.get('alt_text','')).strip()]


def kit(state,inv,topic_id,policy,business):
    """Read-only handoff for one topic: facts a writer must respect, nothing generated."""
    topic=state['topics'][topic_id]
    lease=next((l for l in state['leases'].values() if l['topic_id']==topic_id),None)
    names={c['id']:c for c in inv['categories']}
    return {'mode':'read-only-writer-kit','wordpress_writes':0,'topic':topic,
            'lease':lease,'inventory_sha256':digest(inv),'inventory_captured_at':inv['captured_at'],
            'category_ancestry':[{'id':i,'slug':names[i]['slug'],'name':names[i].get('name')} for i in topic['category_path']],
            'existing_titles_same_category':[x['title'] for x in inv['items'] if topic['category_id'] in x.get('categories',[])],
            'internal_link_targets':link_catalogue(inv),'featured_media_options':media_catalogue(inv),
            'business_facts':business,'qa_policy':{k:policy[k] for k in ('score_threshold','minimum_internal_links','maximum_repairs')},
            'article_fields':list(ARTICLE_FIELDS),'review_checks':list(REVIEW_CHECKS),
            'rules':['Original English prose; no copied passages; cite captured sources by document address',
                     'No body <h1>; two or more <h2>; no script/style/meta/iframe/form; no provenance marker',
                     'Only reference prices from business facts, declared in business_claims with a disclaimer sentence',
                     'Regulated claims (licence, law, visa, registration) need an official .gov/.gov.vn source',
                     'Never promise no deposit, refunds, delivery policy or firsthand testing',
                     'Internal links only to internal_link_targets; featured_media only from featured_media_options']}


def precheck(store,state,inv,topic_id,article,policy,business,review=None):
    """Run the production QA function without touching state, leases or repair counts."""
    topic=state['topics'][topic_id]
    missing=[k for k in ARTICLE_FIELDS if k not in article]
    submission={'article_sha':digest(article),'session':article.get('session'),'agent_id':article.get('agent_id')}
    result=evaluate(article,topic,submission,inv,policy,store,review,business)
    words=len(norm(' '.join(_text(article.get('body_html','')))).split())
    result.update(mode='non-mutating-precheck',wordpress_writes=0,missing_fields=missing,word_count=words,
                  hard_fails_excluding_review=[x for x in result['hard_fails'] if x!='INDEPENDENT_SEMANTIC_REVIEW_REQUIRED'])
    result['would_pass_after_review']=not result['hard_fails_excluding_review'] and result['score']+(0 if review else 10)>=policy['score_threshold']
    return result


def _text(html):
    from .audit import parse
    return parse(html).text


def admit(store,inv,batch,reviewer_id,fetch_records,batch_max=100,extra_queue=()):
    """Capture every declared source through its external fetch record, attach the
    fresh inventory digest to each DISTINCT verdict and admit atomically.

    `batch` items carry `sources` with url/supports and a `fetch` key naming the
    record in `fetch_records`. A missing or failed record blocks the candidate; the
    batch is rejected as a whole, which is the existing intake contract.
    """
    validate_inventory(inv)
    if not reviewer_id:raise ValueError('Intent reviewer identity required')
    prepared=[];queue=list(extra_queue)
    for candidate in batch:
        candidate=dict(candidate);sources=[]
        for ref in candidate.get('sources',[]):
            record=fetch_records.get(ref.get('fetch') or ref['url'])
            if record is None:raise ValueError('No external fetch record for '+ref['url'])
            captured=capture_external_source(store,ref['url'],record)
            sources.append({'url':ref['url'],'document':captured['document'],'supports':ref['supports']})
        candidate['sources']=sources
        review=dict(candidate.get('intent_review',{}))
        review.update(inventory_sha256=digest(inv),reviewer_id=reviewer_id)
        if review.get('verdict')!='DISTINCT' or not review.get('rationale'):raise ValueError('Each candidate needs a DISTINCT verdict with rationale')
        candidate['intent_review']=review
        if collisions(candidate,inv,queue):raise ValueError('Candidate collides with inventory or queue: '+candidate['topic_id'])
        prepared.append(candidate);queue.append(candidate)
    return intake(store,prepared,inv,batch_max)


def cycle(state,inv,release,live_total=None):
    """LIVE TOTAL | FACTORY VERIFIED | PLANNED | WRITING | QA PASS | QA FAIL | PUBLISHED | BLOCKED | REMAINING"""
    counts=Counter(t['status'] for t in state['topics'].values())
    live=inv.get('counts',{}).get('posts') if live_total is None else live_total
    writing=counts['CLAIMED']+counts['DRAFT_READY']
    row={'LIVE TOTAL':live,'FACTORY VERIFIED':len(state['receipts']),'PLANNED':counts['PLANNED'],'WRITING':writing,
         'QA PASS':counts['READY'],'QA FAIL':counts['NEEDS_REPAIR']+counts['NEEDS_REVIEW'],
         'PUBLISHED':counts['VERIFIED'],'BLOCKED':counts['BLOCKED']+counts['PUBLISHING'],
         'REMAINING':max(0,2000-(live or 0))}
    active=[s for s,l in state['leases'].items() if l['expires_at']>timestamp()]
    return {'generated_at':now(),'row':row,'line':' | '.join(f'{k} {v}' for k,v in row.items()),
            'live_total_source':'inventory captured '+inv.get('captured_at','UNKNOWN'),
            'active_writer_slots':active,'production_enabled':bool(release.get('enabled')),
            'states':dict(counts),'research_requests_open':[r['request_id'] for r in state['research_requests'].values() if r['status']=='AWAITING_EXTERNAL_RESEARCH']}
