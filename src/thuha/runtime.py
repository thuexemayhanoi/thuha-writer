"""V5 writer-session runtime helpers: read-only kits, non-mutating prechecks,
source-backed candidate admission and the cycle report.

An authorized Claude session is the AI runtime. These helpers only package
state the session needs and run the *same* QA policy before a submission so a
writer does not burn bounded repairs on mechanical faults. Nothing here writes
to WordPress or lowers a gate.
"""
from collections import Counter
from .common import digest, now, norm, urlkey, validate_inventory
from .coordinator import WAIT_CODES, timestamp
from .datawait import DATA_WAIT_FAILS, media_catalogue, planned_urls, potential_score, qa_blocked, split, unknown_internal_links  # shared with QA
from .language import LANGUAGES, locale, targets as language_targets
from . import quota
from .quality import evaluate
from .research import capture_external_source, collisions, intake, item_language

ARTICLE_FIELDS=('topic_id','session','agent_id','source_commit','language','title','body_html','seo_title',
                'meta_description','focus_keyword','canonical','category_id','featured_media','sources','business_claims')


def link_catalogue(inv,language=None,limit=None):
    """Live-verified same-site URLs of ONE language a writer may link to; nothing else passes QA.

    A body link to the other language is a hard QA failure, so the catalogue never offers one.
    """
    rows=[]
    for item in inv['items']:
        if language and item_language(item)!=language:continue
        check=item.get('public_check',{})
        if check.get('http_status')!=200 or check.get('canonicals') not in (None,[item['url']]):continue
        rows.append({'id':item['id'],'type':item['type'],'url':urlkey(item['url'])+'/','title':item.get('title'),
                     'categories':item.get('categories',[]),'words':item.get('word_count')})
    rows.sort(key=lambda r:(r['type']!='posts',r['id']))
    return rows[:limit] if limit else rows


RULES={
 'en':['Original English prose; no copied passages; cite captured sources by document address',
       'No body <h1>; two or more <h2>; only the allow-listed HTML (no script/style/meta/iframe/form, no comments, no provenance marker)',
       'Only reference prices from business facts, declared in business_claims with a disclaimer sentence',
       'Regulated claims (licence, law, visa, registration) need an official .gov/.gov.vn source',
       'Never promise no deposit, refunds, delivery policy or firsthand testing',
       'Internal links only to internal_link_targets (English, live-verified); featured_media only from featured_media_options'],
 'vi':['Văn xuôi tiếng Việt gốc, viết cho người đọc Việt; không dịch máy, không dịch từ bài tiếng Anh; dẫn nguồn đã chụp bằng địa chỉ tài liệu',
       'Không có <h1> trong thân bài; từ hai <h2> trở lên; chỉ dùng HTML trong danh sách cho phép (không script/style/meta/iframe/form, không chú thích HTML, không dấu nhận diện)',
       'Chỉ nêu giá tham khảo lấy từ business facts, khai trong business_claims và có câu "giá tham khảo", nhắc xác nhận trước khi đặt xe',
       'Nội dung về giấy phép, bằng lái, luật, mức phạt, visa, đăng kiểm phải có nguồn chính thống (.gov.vn hoặc cơ quan nhà nước)',
       'Không hứa "không cọc", hoàn tiền, chính sách giao xe hay trải nghiệm trực tiếp chưa được xác thực',
       'Link nội bộ chỉ tới internal_link_targets tiếng Việt đã xác thực còn sống; featured_media chỉ từ featured_media_options (alt text tiếng Việt)']}


def kit(state,inv,topic_id,policy,business):
    """Read-only handoff for one topic: facts a writer must respect, nothing generated."""
    topic=state['topics'][topic_id]
    lang=topic['language']
    lease=next((l for l in state['leases'].values() if l['topic_id']==topic_id),None)
    names={c['id']:c for c in inv['categories']}
    media=media_catalogue(inv,lang)
    return {'mode':'read-only-writer-kit','wordpress_writes':0,'topic':topic,'language':lang,
            'article_language_value':locale(lang),
            'lease':lease,'inventory_sha256':digest(inv),'inventory_captured_at':inv['captured_at'],
            'category_ancestry':[{'id':i,'slug':names[i]['slug'],'name':names[i].get('name'),'language':names[i].get('language')} for i in topic['category_path']],
            'existing_titles_same_category':[x['title'] for x in inv['items'] if topic['category_id'] in x.get('categories',[])],
            'internal_link_targets':link_catalogue(inv,lang),'featured_media_options':media,
            'blockers':([] if media else ['NEEDS_MEDIA: no existing image has '+lang+' alt text, so this article cannot pass QA until one is added in WordPress']),
            'business_facts':business,'qa_policy':{k:policy[k] for k in ('score_threshold','minimum_internal_links','minimum_internal_content_links','maximum_repairs')},
            'minimum_length':{'unit':'syllables' if lang=='vi' else 'words','value':policy['substantial_length'][lang]},
            'article_fields':list(ARTICLE_FIELDS),'review_mode':'automated','waiting_for_choices':list(WAIT_CODES),
            'rules':RULES[lang]}


def precheck(store,state,inv,topic_id,article,policy,business,review=None):
    """Run the production QA function without touching state, leases or repair counts."""
    topic=state['topics'][topic_id]
    missing=[k for k in ARTICLE_FIELDS if k not in article]
    submission={'article_sha':digest(article),'session':article.get('session'),'agent_id':article.get('agent_id')}
    result=evaluate(article,topic,submission,inv,policy,store,review,business)
    words=len(norm(' '.join(_text(article.get('body_html','')))).split())
    failures=list(result['hard_fails'])
    unknown=unknown_internal_links(article,topic,inv,state)
    if unknown:failures.append('INTERNAL_LINK_TARGET_UNKNOWN')
    if missing:failures.append('ARTICLE_FIELDS_MISSING')
    # The writer's view of the QA split: a wait only where no edit could clear it, and only if the article would pass with the data
    # (an unfinished draft may wait for what it will be completed with; the automatic QA is stricter, see datawait.split).
    waits,faults=split(failures,article,topic,inv,state,policy,declared=True)
    potential=potential_score(result,waits)
    if waits and not faults and potential<policy['score_threshold']:faults.append('SCORE_BELOW_THRESHOLD_EVEN_WITH_THE_DATA')
    result.update(mode='non-mutating-precheck',wordpress_writes=0,missing_fields=missing,word_count=words,
                  hard_fails=sorted(set(failures)),data_waits=waits,unknown_internal_links=unknown,content_fails=faults,potential_score=potential)
    result['would_pass_qa']=not failures and result['score']>=policy['score_threshold']
    result['status']='PASS' if result['would_pass_qa'] else 'FAIL'
    return result


def _text(html):
    from .audit import parse
    return parse(html).text


def admit(store,inv,batch,reviewer_id,fetch_records,batch_max=100,extra_queue=(),targets=None,inventory_max_age=None):
    """Capture every declared source through its external fetch record, stamp the current
    inventory digest on any verdict a researcher supplied (none is required) and admit atomically.

    `batch` items carry `sources` with url/supports and a `fetch` key naming the
    record in `fetch_records`. A missing or failed record blocks the candidate; the
    batch is rejected as a whole, which is the existing intake contract.
    """
    validate_inventory(inv,**({} if inventory_max_age is None else {'max_age':inventory_max_age}))
    prepared=[];queue=list(extra_queue)
    for candidate in batch:
        candidate=dict(candidate);sources=[]
        for ref in candidate.get('sources',[]):
            record=fetch_records.get(ref.get('fetch') or ref['url'])
            if record is None:raise ValueError('No external fetch record for '+ref['url'])
            captured=capture_external_source(store,ref['url'],record)
            sources.append({'url':ref['url'],'document':captured['document'],'supports':ref['supports']})
        candidate['sources']=sources
        # Owner update: no AI or human intent reviewer is needed. A verdict a researcher supplies is stamped with the current inventory
        # digest and, if it is not DISTINCT, still blocks; the automatic collision checks here and in `intake` are the gate.
        review=dict(candidate.get('intent_review') or {})
        if review:
            if review.get('verdict') not in (None,'DISTINCT'):raise ValueError('Candidate declares a non-distinct intent: '+candidate['topic_id'])
            review.update(inventory_sha256=digest(inv),**({'reviewer_id':reviewer_id} if reviewer_id else {}))
            candidate['intent_review']=review
        if collisions(candidate,inv,queue):raise ValueError('Candidate collides with inventory or queue: '+candidate['topic_id'])
        prepared.append(candidate);queue.append(candidate)
    return intake(store,prepared,inv,batch_max,targets,inventory_max_age=inventory_max_age)


def cycle(state,inv,release,targets=None):
    """Per-language progress. Live totals need an adapter inventory; otherwise they are UNKNOWN, never 0."""
    targets=targets or language_targets()
    counts=Counter(t['status'] for t in state['topics'].values())
    blocked=qa_blocked(state) # DRAFT_READY drafts whose QA waits for data: neither "writing" nor a pass nor a failure
    try:live=quota.effective(state,quota.published(inv),{x['id'] for x in inv.get('items',[])});live_error=None
    except ValueError as exc:live,live_error=None,str(exc)
    languages={}
    for lang in LANGUAGES:
        topics=[t for t in state['topics'].values() if t['language']==lang]
        c=Counter(t['status'] for t in topics)
        unresolved=sum(1 for k,i in state['intents'].items() if i.get('language')==lang and i['phase'] not in ('PUBLISHED',)+quota.CLOSED_PHASES)
        languages[lang]={'target':targets[lang],'live':None if live is None else live[lang],
                         'remaining':None if live is None else max(0,targets[lang]-live[lang]-unresolved),
                         'planned':c['PLANNED'],'writing':c['CLAIMED']+c['DRAFT_READY']-sum(state['topics'][k]['language']==lang for k in blocked),
                         'waiting_data':c['WAITING_DATA'],'qa_pass':c['READY'],'qa_blocked_data':sum(state['topics'][k]['language']==lang for k in blocked),
                         'qa_fail':c['NEEDS_REPAIR']+c['NEEDS_REVIEW'],'published':c['PUBLISHED'],
                         'blocked':c['BLOCKED']+c['PUBLISHING'],'held':c['HELD']}
    row={'FACTORY PUBLISHED':len(state['receipts']),'PLANNED':counts['PLANNED'],'WRITING':counts['CLAIMED']+counts['DRAFT_READY']-len(blocked),
         'WAITING DATA':counts['WAITING_DATA'],'QA PASS':counts['READY'],'QA FAIL':counts['NEEDS_REPAIR']+counts['NEEDS_REVIEW'],
         'QA BLOCKED DATA':len(blocked),'PUBLISHED':counts['PUBLISHED'],
         'BLOCKED':counts['BLOCKED']+counts['PUBLISHING'],'HELD':counts['HELD']}
    for lang in LANGUAGES:
        row['LIVE '+lang.upper()]='UNKNOWN' if live is None else live[lang]
        row['REMAINING '+lang.upper()]='UNKNOWN' if live is None else languages[lang]['remaining']
    active=[s for s,l in state['leases'].items() if l['expires_at']>timestamp()]
    return {'generated_at':now(),'row':row,'line':' | '.join(f'{k} {v}' for k,v in row.items()),'languages':languages,
            'live_total_source':'inventory captured '+inv.get('captured_at','UNKNOWN')+' ('+str(inv.get('language_source'))+')',
            'live_counts_error':live_error,'priority':list(LANGUAGES),
            'active_writer_slots':active,'production_enabled':bool(release.get('enabled')),
            'states':dict(counts),'research_requests_open':[r['request_id'] for r in state['research_requests'].values() if r['status']=='AWAITING_EXTERNAL_RESEARCH']}
