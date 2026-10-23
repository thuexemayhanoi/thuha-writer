"""Automatic bilingual QA. Scores never override hard failures.

This deterministic screen checks evidence and language signals; it does not
claim human factual or native-language judgment. Historical reviews are kept
for attribution but are neither a prerequisite nor a source of score points.
"""
import re
import unicodedata
from urllib.parse import urljoin,urlsplit
from .audit import parse
from . import htmlpolicy
from .common import SITE, age, digest, now, norm, urlkey, signature, category_path, validate_inventory
from .language import locale, screen, screen_alt, url_language
from . import datawait
from .research import collisions, evidence_current, item_language
from .quota import CLOSED_PHASES
from .store import event
from .coordinator import timestamp

REVIEW_CHECKS=('intent','factual_accuracy','native_language','originality','business_facts','image_relevance','no_machine_translation')


def review_language(review):
    """The language a review names. Reviews recorded before schema 5 carry no label but attest `english`."""
    if review.get('language'):return review['language']
    return 'en' if 'english' in review.get('checks',{}) else None


def review_checks_ok(review,lang):
    """Vietnamese: native language AND no machine translation. English: `english` (the attestation recorded by
    reviews that predate schema 5) or `native_language`; English articles are written in English, so there is no
    translation step to attest. Every language also needs the five factual/editorial checks."""
    checks=(review or {}).get('checks',{})
    common=all(checks.get(k) is True for k in ('intent','factual_accuracy','originality','business_facts','image_relevance'))
    if lang=='vi':return common and checks.get('native_language') is True and checks.get('no_machine_translation') is True
    return common and (checks.get('native_language') is True or checks.get('english') is True)
REGULATED={'en':r'\b(licen[cs]e|permit|registration|legal|law|visa|embass(?:y|ies))\b',
           'vi':r'(giấy phép|bằng lái|gplx|nghị định|thông tư|\bluật\b|mức phạt|xử phạt|csgt|cảnh sát giao thông|\bvisa\b|đại sứ quán|đăng kiểm|bảo hiểm bắt buộc)'}
FIRSTHAND={'en':r'\b(no deposit|deposit.free|guaranteed refund|we personally tested|we have tested)\b',
           'vi':r'(không (cần )?đặt cọc|miễn (đặt )?cọc|không cọc|đảm bảo hoàn (lại )?(tiền|cọc)|chúng tôi đã (tự |trực tiếp )?(thử|chạy thử|kiểm tra)|tôi đã (trực tiếp|tự) )'}
DISCLAIMER={'en':r'reference prices?|confirm.*(?:rate|price|booking)',
            'vi':r'giá tham khảo|xác nhận (lại )?(giá|mức giá|báo giá|xe|đặt xe)|reference prices?'}


def nfc(text):
    return unicodedata.normalize('NFC',str(text or ''))


def evaluate(article,topic,submission,inv,policy,store,review=None,business=None):
    errors=[];score=0
    lang=topic['language']
    sha=digest(article)
    try:validate_inventory(inv,policy['inventory_max_age_seconds'])
    except ValueError as e:errors.append(str(e))
    if submission.get('article_sha')!=sha:errors.append('SUBMISSION_HASH_MISMATCH')
    for k in ('topic_id','session','agent_id'):
        expected=topic.get(k) if k=='topic_id' else submission.get(k)
        if not article.get(k) or article[k]!=expected:errors.append('PROVENANCE_'+k.upper())
    if article.get('language')!=locale(lang):errors.append('ARTICLE_LANGUAGE_MISMATCH')
    if article.get('canonical')!=topic['proposed_url']:errors.append('CANONICAL_MISMATCH')
    try:
        if article.get('category_id')!=topic['category_id'] or category_path(topic['category_id'],inv['categories'])!=topic['category_path']:
            errors.append('TAXONOMY_MISMATCH')
        by_id={c['id']:c for c in inv['categories']}
        # A category of the other language, or an unverified one, never makes a post belong to this language.
        if any(by_id[i].get('language')!=lang for i in topic['category_path']):errors.append('CATEGORY_LANGUAGE_MISMATCH')
    except (ValueError,KeyError):errors.append('TAXONOMY_UNKNOWN')
    if collisions(topic,inv,[]):errors.append('DUPLICATE_OR_CANNIBALIZATION')
    body=article.get('body_html','');page=parse(body);text=nfc(' '.join(page.text))
    if not body or not re.search(r'<p[ >]',body):errors.append('ARTICLE_BODY_MISSING')
    # Canonical-form allow-list shared with the plugin; anything exotic is refused rather than interpreted.
    if htmlpolicy.violations(body):errors.append('UNSAFE_OR_DUPLICATE_SCHEMA_HTML')
    if '<!-- thuha:' in body.lower():errors.append('RESERVED_PROVENANCE_MARKER')
    if any(h[0]=='h1' for h in page.headings):errors.append('BODY_H1_DUPLICATES_TEMPLATE')
    score+=10 if sum(h[0]=='h2' for h in page.headings)>=2 else 0
    # Syllables for Vietnamese, words for English: the floors are set per language.
    score+=10 if len(norm(text).split())>=policy['substantial_length'][lang] else 5
    if len(text.split())>=30:
        errors.extend('BODY_'+x for x in screen(lang,text))
    for field in ('title','seo_title','meta_description','focus_keyword'):
        errors.extend(field.upper()+'_'+x for x in screen(lang,nfc(article.get(field,'')),short=True))
    score+=10 if 35<=len(nfc(article.get('seo_title','')))<=75 else 0
    score+=10 if 110<=len(nfc(article.get('meta_description','')))<=180 else 0
    if not article.get('focus_keyword'):errors.append('FOCUS_KEYWORD_MISSING')
    # SEO plugins re-sanitise these fields; text that would not survive unchanged breaks the exact read-back later.
    for field in ('title','seo_title','meta_description','focus_keyword'):
        value=nfc(article.get(field,''))
        if value and (value!=' '.join(value.split()) or re.search(r'[<>]',value)):errors.append(field.upper()+'_NOT_CANONICAL_PLAIN_TEXT')
    if re.search(r'["\'`]',nfc(article.get('focus_keyword',''))):errors.append('FOCUS_KEYWORD_HAS_QUOTES')
    live={urlkey(x['url']):x for x in inv['items'] if x.get('public_check',{}).get('http_status')==200 and item_language(x)==lang}
    archives={urlkey(c['link']) for c in inv['categories'] if c.get('language')==lang and c.get('link')}
    internal=set();content_links=set()
    for link in page.links:
        if link.startswith('#'):continue
        u=urljoin(topic['proposed_url'],link);p=urlsplit(u)
        if p.scheme in ('tel','mailto'):continue
        if p.scheme!='https' or p.username or p.password:errors.append('UNSAFE_LINK');continue
        if p.netloc==urlsplit(SITE).netloc:
            other=url_language(u)
            if other!=lang:errors.append('CROSS_LANGUAGE_BODY_LINK');continue
            key=urlkey(u)
            if key not in live and key not in archives:errors.append('INTERNAL_LINK_NOT_LIVE_VERIFIED')
            else:
                internal.add(key)
                if key in live:content_links.add(key)
    if len(internal)<policy['minimum_internal_links'] or len(content_links)<policy['minimum_internal_content_links']:
        errors.append('INSUFFICIENT_REAL_INTERNAL_LINKS')
    else:score+=20
    media=next((m for m in inv.get('media',[]) if m['id']==article.get('featured_media')),None)
    if not media or not str(media.get('alt_text','')).strip():errors.append('FEATURED_MEDIA_OR_ALT_NOT_VERIFIED')
    else:
        score+=10
        errors.extend('FEATURED_ALT_'+x for x in screen_alt(lang,nfc(media['alt_text'])))
    if any(not str(img.get('alt') or '').strip() for img in page.images):errors.append('BODY_IMAGE_ALT_MISSING')
    for img in page.images:
        errors.extend('BODY_IMAGE_ALT_'+x for x in screen_alt(lang,nfc(img.get('alt') or '')) if img.get('alt'))
    sources=article.get('sources',[]);source_hosts=[]
    if not sources:errors.append('RESEARCH_EVIDENCE_MISSING')
    for ref in sources:
        try:
            evidence=store.get_document(ref['document'])
            if evidence['url']!=ref['url'] or evidence['http_status']!=200 or not 0<=age(evidence['checked_at'])<=policy['research_max_age_seconds']:
                errors.append('SOURCE_STALE_OR_UNVERIFIED')
            if not evidence_current(evidence):errors.append('SOURCE_STALE_OR_UNVERIFIED') # a first-party file changed after capture
            if len(ref.get('supports',''))<20:errors.append('SOURCE_SUPPORT_UNSPECIFIED')
            source_hosts.append('' if evidence.get('capture_method')=='repository-file' else urlsplit(ref['url']).hostname or '') # first-party files are no official host
        except (ValueError,KeyError,OSError):errors.append('SOURCE_SNAPSHOT_MISSING')
    if sources:score+=10
    if re.search(REGULATED[lang],text,re.I):
        official=lambda h:h.endswith(('.gov.vn','.gov.uk','.gov','.gouv.fr')) or h in ('unece.org','www.unece.org')
        if not any(official(h) for h in source_hosts):errors.append('REGULATED_CLAIM_NEEDS_OFFICIAL_SOURCE')
    if re.search(FIRSTHAND[lang],text,re.I):
        errors.append('UNVERIFIED_BUSINESS_OR_FIRSTHAND_CLAIM')
    if business:
        for claim in article.get('business_claims',[]):
            if claim.get('kind')!='reference_price':errors.append('UNAPPROVED_BUSINESS_POLICY');continue
            interval=business['reference_prices_vnd'].get(claim.get('vehicle'),{}).get(claim.get('period'))
            if not interval or not interval[0]<=claim.get('value_vnd',-1)<=interval[1]:errors.append('UNAPPROVED_PRICE')
        if article.get('business_claims') and not re.search(DISCLAIMER[lang],text,re.I):
            errors.append('REFERENCE_PRICE_DISCLAIMER_MISSING')
    new_sig=set(signature(text))
    for old in (x for x in inv['items'] if item_language(x)==lang):
        sig=set(old['content_signature'])
        if len(new_sig&sig)/max(1,min(len(new_sig),len(sig)))>.75:errors.append('CONTENT_OVERLAP_REVIEW')
    # Eight ten-point units are available from automatic checks (links carry two).
    # Normalize these to 100 explicitly; never award points for a review attestation.
    raw_score=score
    score=round(raw_score*100/80,2)
    return {'status':'PASS' if not errors and score>=policy['score_threshold'] else 'FAIL','language':lang,
            'score':score,'raw_score':raw_score,'raw_maximum':80,'score_maximum':100,
            'threshold':policy['score_threshold'],'hard_fails':sorted(set(errors)),
            'article_sha':sha,'policy_sha256':digest(policy),'inventory_sha256':digest(inv),
            'checked_at':now(),'review_mode':'automated','semantic_review':None,
            'disclaimer':'Automatic technical and evidence QA; no independent semantic review performed; not a ranking or indexing guarantee'}


class InventoryUnusable(ValueError):
    """The inventory cannot carry a verdict (stale, incomplete, wrong site). That says nothing about the article."""


def run_qa(store,topic_id,inv,policy,business):
    state=store.read();sub=state['submissions'][topic_id];topic=state['topics'][topic_id]
    if topic['status']=='WAITING_DATA':
        raise ValueError('Topic waits for data ('+', '.join(topic.get('waiting_for') or ['finish the draft'])+'); it cannot be evaluated or made READY until the draft is complete')
    if topic['status']=='HELD':raise ValueError('Topic is HELD; resolve its hold before QA')
    # A verdict on an unusable inventory would send every draft to repair for something no writer can fix: record nothing.
    try:validate_inventory(inv,policy['inventory_max_age_seconds'])
    except ValueError as exc:raise InventoryUnusable('Inventory unusable for QA ('+str(exc)+'); nothing was evaluated, recorded or changed') from None
    article=store.get_document(sub['article_sha'])
    result=evaluate(article,topic,sub,inv,policy,store,business=business)
    waits=[]
    if result['status']=='FAIL' and result['hard_fails']:
        waits,faults=datawait.split(result['hard_fails'],article,topic,inv,state,policy)
        potential=datawait.potential_score(result,waits)
        # Only missing data, and the article would pass with it: the draft waits and keeps its repairs; it is not QA-passed.
        if not waits or faults or potential<policy['score_threshold']:waits=[]
    if waits:
        record={'article_sha':sub['article_sha'],'status':'BLOCKED_DATA','waiting_for':waits,'policy_sha256':digest(policy)}
        previous=state['qa'].get(topic_id) or {}
        result=dict(result,status='BLOCKED_DATA',waiting_for=waits,potential_score=potential)
        if topic['status']=='DRAFT_READY' and all(previous.get(k)==v for k,v in record.items()):return result # already recorded; no noise
    else:record=None
    report_sha=store.put_document(result)
    def transaction(state):
        if state['submissions'][topic_id]['article_sha']!=sub['article_sha']:raise ValueError('Draft changed during QA')
        if state['topics'][topic_id]['status'] in ('WAITING_DATA','HELD'):raise ValueError('Topic put on hold or waiting for data during QA')
        if any(l['topic_id']==topic_id and l['fence']!=sub['fence'] and l['expires_at']>timestamp() for l in state['leases'].values()):
            raise ValueError('Another live writer is repairing this checkpoint; do not close their lease')
        intent=state['intents'].get(topic_id)
        if intent and intent['phase'] not in CLOSED_PHASES:raise ValueError('Publication pending; reconcile before QA mutation') # a closed intent never reached WordPress
        if record:
            # READY meant "passed under the current policy"; a check that cannot be renewed no longer shows it. No repair is spent.
            state['qa'][topic_id]={'report_sha':report_sha,**record}
            if state['topics'][topic_id]['status'] in ('READY','NEEDS_REPAIR'):state['topics'][topic_id]['status']='DRAFT_READY'
            # The draft is stored and complete: like a draft stored with --waiting-for, it frees its writer's slot.
            state['leases']={s:l for s,l in state['leases'].items() if l['topic_id']!=topic_id}
            event(state,'QA',topic_id=topic_id,report_sha=report_sha,status='BLOCKED_DATA',waiting_for=record['waiting_for'])
            return result
        state['qa'][topic_id]={'report_sha':report_sha,'article_sha':sub['article_sha'],'status':result['status']}
        state['topics'][topic_id]['status']='READY' if result['status']=='PASS' else 'NEEDS_REPAIR'
        if sub['repair_count']>=policy['maximum_repairs'] and result['status']!='PASS':state['topics'][topic_id]['status']='NEEDS_REVIEW'
        if result['status']=='PASS' or state['topics'][topic_id]['status']=='NEEDS_REVIEW':
            state['leases']={s:l for s,l in state['leases'].items() if l['topic_id']!=topic_id}
        event(state,'QA',topic_id=topic_id,report_sha=report_sha,status=result['status'])
        return result
    return store.mutate(transaction)


def pending_qa(store,policy,languages=None):
    """Drafts that a scheduled QA run should evaluate.

    Every completed draft is eligible without a reviewer. A READY draft whose
    report was produced under an older policy or revision is evaluated again.
    WAITING_DATA, HELD and incomplete drafts remain excluded.
    """
    state=store.read();out=[]
    for tid,topic in sorted(state['topics'].items()):
        sub=state['submissions'].get(tid)
        if not sub or (languages and topic['language'] not in languages):continue
        if topic['status']=='DRAFT_READY':out.append(tid)
        elif topic['status']=='READY':
            record=state['qa'].get(tid)
            try:
                report=store.get_document(record['report_sha']) if record else None
            except (ValueError,OSError,KeyError):report=None
            if not report or report.get('policy_sha256')!=digest(policy) or report.get('article_sha')!=sub['article_sha']:out.append(tid)
    return out
