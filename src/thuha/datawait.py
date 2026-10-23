"""Which automatic-QA failures mean "the data does not exist yet" and which mean "the article is wrong".

One classifier serves the writer's non-mutating precheck and the real QA, so they give the same answer: a writer is never
told to wait for something only an edit can fix, and a draft is never sent back to be edited for something only the site
can supply. Nothing here lowers a gate or invents data; it only decides where a failing draft goes next.
"""
from urllib.parse import urljoin, urlsplit
from .audit import parse
from .common import SITE, load, urlkey
from .language import screen_alt, url_language
from .matrix import matrix_path
from .research import item_language

# Hard-fail codes that can mean "the data does not exist yet". Whether they do depends on the article too (see `split`).
DATA_WAIT_FAILS={'FEATURED_MEDIA':('FEATURED_MEDIA_OR_ALT_NOT_VERIFIED',),
                 'INTERNAL_LINKS':('INTERNAL_LINK_NOT_LIVE_VERIFIED','INSUFFICIENT_REAL_INTERNAL_LINKS'),
                 'AUTHORITATIVE_INVENTORY':('Inventory is stale or future-dated','Complete inventory for the exact production site is required')}
# Raw automatic points (of 80) that arrive with the data: the link rule and the verified featured image.
DATA_POINTS={'INTERNAL_LINKS':20,'FEATURED_MEDIA':10}


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


def media_catalogue(inv,language=None):
    """Existing media whose alt text is written in the article's language (QA screens the alt text)."""
    return [m for m in inv.get('media',[]) if str(m.get('alt_text','')).strip()
            and (language is None or not screen_alt(language,str(m['alt_text'])))]


def planned_urls(state,language):
    """Every same-site URL a draft may legitimately point to before it is live: the ledger's topics and the language's matrix plan."""
    urls={urlkey(t['proposed_url']) for t in state['topics'].values() if t.get('proposed_url')}
    try:urls|={urlkey(r['proposed_url']) for r in load(matrix_path(language))['rows'] if r.get('proposed_url')}
    except (OSError,ValueError,KeyError):pass
    return urls


def body_links(html):
    return parse(html).links


def own_links(article,topic):
    """Distinct same-site, same-language https links of the body, as URL keys; other links are separate QA faults."""
    out=set()
    for link in body_links(article.get('body_html','')):
        if link.startswith('#'):continue
        url=urljoin(topic['proposed_url'],link);parts=urlsplit(url)
        if parts.scheme!='https' or parts.username or parts.password or parts.netloc!=urlsplit(SITE).netloc:continue
        try:
            if url_language(url)==topic['language']:out.add(urlkey(url))
        except ValueError:continue
    return out


def unknown_internal_links(article,topic,inv,state):
    """Same-site links that are neither live (inventory item or category archive) nor planned: a typo, not a data wait."""
    known={urlkey(x['url']) for x in inv['items']}|{urlkey(c['link']) for c in inv['categories'] if c.get('link')}|planned_urls(state,topic['language'])
    out=[]
    for link in body_links(article.get('body_html','')):
        if link.startswith('#'):continue
        url=urljoin(topic['proposed_url'],link);parts=urlsplit(url)
        if parts.scheme!='https' or parts.netloc!=urlsplit(SITE).netloc:continue
        try:
            if urlkey(url) not in known:out.append(url)
        except ValueError:out.append(url)
    return out


def links_can_wait(article,topic,inv,state,policy,declared=False):
    """True when missing live pages, not the draft's own links, are what stops the link rule.

    Every same-site link must point at something that exists or is planned (no typo). Then either the links the draft
    already has would satisfy the policy once their targets are live, or (`declared`, the writer's view of an unfinished
    draft) the inventory cannot offer enough live same-language targets for ANY draft yet, so links can only be completed
    later. A draft with too few links while the site has plenty to link to needs another link, not more time.
    """
    if unknown_internal_links(article,topic,inv,state):return False
    lang=topic['language'];targets=own_links(article,topic)
    content={urlkey(x['url']) for x in inv['items'] if item_language(x)==lang}|planned_urls(state,lang)
    if len(targets)>=policy['minimum_internal_links'] and len(targets&content)>=policy['minimum_internal_content_links']:return True
    if not declared:return False
    live=[x for x in inv['items'] if item_language(x)==lang and x.get('public_check',{}).get('http_status')==200]
    archives=[c for c in inv['categories'] if c.get('language')==lang and c.get('link')]
    return len(live)<policy['minimum_internal_content_links'] or len(live)+len(archives)<policy['minimum_internal_links']


def split(failures,article,topic,inv,state,policy,declared=False):
    """Divide hard failures into the data the site lacks (WAIT_CODES) and the faults only an edit can fix.

    `declared` is the writer's question ("may I store this draft with --waiting-for?"): an unfinished draft may wait for
    an image that does not exist or for live pages it will be completed with. The automatic QA asks without it and only
    waits for a draft that would pass exactly as written once the pages are live; an image never qualifies, because
    someone must still choose it.
    """
    failures=list(failures);waits=set()
    hit=lambda code:any(x in DATA_WAIT_FAILS[code] for x in failures)
    if declared and hit('FEATURED_MEDIA') and article.get('featured_media') is None and not media_catalogue(inv,topic['language']):waits.add('FEATURED_MEDIA')
    if hit('INTERNAL_LINKS') and links_can_wait(article,topic,inv,state,policy,declared):waits.add('INTERNAL_LINKS')
    if hit('AUTHORITATIVE_INVENTORY'):waits.add('AUTHORITATIVE_INVENTORY')
    faults=[x for x in failures if not any(x in DATA_WAIT_FAILS[c] for c in waits)]
    return sorted(waits),faults


def potential_score(result,waits):
    """The score the article would reach once the data it waits for exists; below the threshold it needs an edit, not time."""
    return round((result['raw_score']+sum(DATA_POINTS.get(code,0) for code in waits))*100/result['raw_maximum'],2)


def qa_blocked(state):
    """Finished drafts whose QA is waiting for data the site lacks, with what each lacks. Not QA-passed, and no repair is spent."""
    out={}
    for tid,record in state['qa'].items():
        topic=state['topics'].get(tid);sub=state['submissions'].get(tid)
        if record.get('status')=='BLOCKED_DATA' and topic and sub and topic['status']=='DRAFT_READY' and record.get('article_sha')==sub['article_sha']:
            out[tid]=list(record.get('waiting_for',[]))
    return out
