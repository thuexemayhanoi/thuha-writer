import datetime as dt
import re
import uuid
from .common import ROOT, load, now, digest, validate_inventory
from .language import LANGUAGES, locale, screen_alt
from .policy import LIMITS
from .quota import SOURCES, complete_languages
from .research import item_language
from .store import event

SLOTS=['W'+str(i) for i in range(1,10)]

# What a finished draft can still lack. A draft that waits is stored, visible and never READY; it is claimed again only
# when the data exists (`clear_satisfied`), and finishing it is a completion, not a repair.
WAIT_CODES=('FEATURED_MEDIA','INTERNAL_LINKS','AUTHORITATIVE_INVENTORY')


def timestamp():return dt.datetime.now(dt.timezone.utc).timestamp()


def recover(state, at=None):
    at=timestamp() if at is None else at
    expired=[]
    for slot,lease in list(state['leases'].items()):
        if lease['expires_at']>at:continue
        topic=state['topics'][lease['topic_id']]
        if topic['status']=='CLAIMED':topic['status']=unclaimed_status(state,lease['topic_id'])
        del state['leases'][slot];expired.append(slot)
        event(state,'LEASE_EXPIRED',slot=slot,topic_id=lease['topic_id'])
    return expired


def unclaimed_status(state,tid):
    """Where a topic goes when its writer lease ends without a submission."""
    if state['topics'][tid].get('completion_pending'):return 'WAITING_DATA' # an incomplete draft stays waiting, never DRAFT_READY
    return 'DRAFT_READY' if tid in state['submissions'] else 'PLANNED'


def owned(state, slot, session, fence, at=None):
    lease=state['leases'].get(slot)
    if not lease or lease['session']!=session or lease['fence']!=fence or lease['expires_at']<=(timestamp() if at is None else at):
        raise ValueError('Valid owned lease and fencing ID required')
    return lease


def claim_order(topic):
    """Vietnamese first, then English; repairs before fresh topics inside a language."""
    return (LANGUAGES.index(topic['language']),0 if topic['status'] in ('NEEDS_REPAIR','WAITING_DATA') else 1,topic['topic_id'])


def claimable(topic):
    """Repairs, fresh topics, and waiting drafts whose missing data has arrived."""
    return topic['status'] in ('NEEDS_REPAIR','PLANNED') or (topic['status']=='WAITING_DATA' and not topic.get('waiting_for'))


def claim(store,session,agent_id,slot='auto',ttl=1800,counts=None,targets=None):
    if not re.fullmatch('[a-zA-Z0-9_-]{4,80}',session) or not agent_id.strip():
        raise ValueError('Stable session and explicit external agent attribution required')
    if slot!='auto' and slot not in SLOTS:raise ValueError('Unknown writer slot')
    fence=uuid.uuid4().hex
    def transaction(state):
        recover(state)
        if any(state['controls'].values()):raise ValueError('Factory paused or emergency stop active')
        mine=[v for v in state['leases'].values() if v['session']==session]
        if mine:
            if mine[0]['agent_id']!=agent_id:raise ValueError('Session already belongs to another declared agent')
            return mine[0]
        available=next((x for x in SLOTS if x not in state['leases']),None) if slot=='auto' else slot
        if available is None or available in state['leases']:raise ValueError('No free slot')
        # A language already at its ceiling (live posts + unresolved intents) takes no more writers.
        full=complete_languages(state,counts,targets) if counts is not None and targets is not None else set()
        candidates=sorted((x for x in state['topics'].values() if claimable(x) and x['language'] not in full),key=claim_order)
        busy={x['topic_id'] for x in state['leases'].values()}
        candidate=next((x for x in candidates if x['topic_id'] not in busy),None)
        if not candidate:raise ValueError('No admissible researched topic; external research required')
        lease={'slot':available,'session':session,'agent_id':agent_id,'topic_id':candidate['topic_id'],
               'language':candidate['language'],'fence':fence,'heartbeat_at':now(),'expires_at':timestamp()+ttl}
        if candidate['status']=='WAITING_DATA':candidate['completion_pending']=True # the next submission completes the stored draft
        state['leases'][available]=lease;candidate['status']='CLAIMED'
        event(state,'CLAIM',**lease)
        return lease
    return store.mutate(transaction)


def heartbeat(store,slot,session,fence,ttl=1800):
    def transaction(state):
        lease=owned(state,slot,session,fence)
        lease.update(heartbeat_at=now(),expires_at=timestamp()+ttl)
        return lease
    return store.mutate(transaction)


def submit(store,slot,session,fence,article,max_repairs=3,waiting_for=None):
    """Store a draft. `waiting_for` (WAIT_CODES) says it lacks data that exists nowhere yet: the draft is kept as
    WAITING_DATA, never READY, and the writer slot is freed. Nothing is invented to get past the wait."""
    waiting=sorted(set(waiting_for or ()))
    if any(code not in WAIT_CODES for code in waiting):raise ValueError('Unknown wait code; choose from '+', '.join(WAIT_CODES))
    if 'FEATURED_MEDIA' in waiting and article.get('featured_media') is not None:
        raise ValueError('A draft waiting for FEATURED_MEDIA must leave featured_media empty; no media ID may be invented')
    state=store.read();lease=owned(state,slot,session,fence)
    if state['topics'][lease['topic_id']]['status']=='NEEDS_REVIEW':raise ValueError('Held topic requires owner review before another revision')
    if article.get('topic_id')!=lease['topic_id'] or article.get('agent_id')!=lease['agent_id'] or article.get('session')!=session:
        raise ValueError('Submission provenance does not match lease')
    if article.get('language')!=locale(state['topics'][lease['topic_id']]['language']):
        raise ValueError('Submission language does not match the topic language')
    if len(str(article.get('body_html','')).encode())>LIMITS['content_bytes']-200:raise ValueError('Draft too large for the adapter byte limit')
    sha=store.put_document(article) # Durable BEFORE releasing or changing state.
    def transaction(state):
        lease=owned(state,slot,session,fence)
        tid=lease['topic_id'];old=state['submissions'].get(tid)
        repairs=(old or {}).get('repair_count',0)
        completing=bool(state['topics'][tid].get('completion_pending')) # finishing a stored draft is not a repair
        if old and old['article_sha']!=sha and not completing:
            repairs+=1
        if repairs>max_repairs:
            state['topics'][tid]['status']='NEEDS_REVIEW'
            state['topics'][tid]['held_article_sha']=sha
            event(state,'REPAIR_LIMIT',topic_id=tid,article_sha=sha)
            del state['leases'][slot]
            return {'status':'NEEDS_REVIEW','article_sha':sha}
        value={'article_sha':sha,'session':session,'agent_id':lease['agent_id'],'slot':slot,'fence':fence,
               'submitted_at':now(),'repair_count':repairs,'commit':article.get('source_commit')}
        state['submissions'][tid]=value
        topic=state['topics'][tid];topic.pop('completion_pending',None)
        if waiting:
            topic['status']='WAITING_DATA';topic['waiting_for']=waiting
            del state['leases'][slot] # the draft is stored; the slot is free for another topic
            event(state,'SUBMISSION',topic_id=tid,article_sha=sha,agent_id=lease['agent_id'],waiting_for=waiting)
        else:
            topic['status']='DRAFT_READY';topic.pop('waiting_for',None)
            event(state,'SUBMISSION',topic_id=tid,article_sha=sha,agent_id=lease['agent_id'])
        return value
    return store.mutate(transaction)


def release(store,slot,session,fence):
    def transaction(state):
        lease=owned(state,slot,session,fence)
        tid=lease['topic_id']
        if state['topics'][tid]['status']=='CLAIMED':state['topics'][tid]['status']=unclaimed_status(state,tid)
        del state['leases'][slot]
        event(state,'RELEASE',slot=slot,topic_id=tid)
    return store.mutate(transaction)



def inventory_usable(inv,policy):
    """An inventory that can carry a Vietnamese article through QA: authoritative, complete and fresh."""
    if inv.get('language_source') not in SOURCES:return False
    try:validate_inventory(inv,policy['inventory_max_age_seconds'])
    except ValueError:return False
    return True


def data_available(code,topic,inv,policy):
    """Does the inventory now hold what `code` was waiting for? Only an authoritative, fresh inventory can say yes."""
    if not inventory_usable(inv,policy):return False
    if code=='AUTHORITATIVE_INVENTORY':return True
    lang=topic['language']
    if code=='FEATURED_MEDIA':
        return any(str(m.get('alt_text','')).strip() and not screen_alt(lang,str(m['alt_text'])) for m in inv.get('media',[]))
    if code=='INTERNAL_LINKS':
        live=[x for x in inv['items'] if x.get('public_check',{}).get('http_status')==200 and item_language(x)==lang]
        return len(live)>=policy['minimum_internal_links']
    return False


def clear_satisfied(state,inv,policy=None):
    """Drop the wait codes the inventory now satisfies. Returns {topic_id: [cleared codes]}.

    A cleared topic stays WAITING_DATA with nothing left to wait for: it is then claimable, and its next submission
    completes the stored draft. Nothing here makes a draft READY or runs QA.
    """
    policy=policy or load(ROOT/'config/qa.json')
    cleared={}
    for tid,topic in sorted(state['topics'].items()):
        if topic['status']!='WAITING_DATA':continue
        done=[c for c in topic.get('waiting_for',[]) if data_available(c,topic,inv,policy)]
        if not done:continue
        topic['waiting_for']=[c for c in topic['waiting_for'] if c not in done]
        cleared[tid]=done
        event(state,'DATA_AVAILABLE',topic_id=tid,cleared=done,remaining=topic['waiting_for'])
    return cleared
