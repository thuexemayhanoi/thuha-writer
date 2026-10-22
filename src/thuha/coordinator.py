import datetime as dt
import re
import uuid
from .common import now, digest
from .language import LANGUAGES, locale
from .quota import complete_languages
from .store import event

SLOTS=['W'+str(i) for i in range(1,10)]


def timestamp():return dt.datetime.now(dt.timezone.utc).timestamp()


def recover(state, at=None):
    at=timestamp() if at is None else at
    expired=[]
    for slot,lease in list(state['leases'].items()):
        if lease['expires_at']>at:continue
        topic=state['topics'][lease['topic_id']]
        if topic['status']=='CLAIMED':
            topic['status']='DRAFT_READY' if lease['topic_id'] in state['submissions'] else 'PLANNED'
        del state['leases'][slot];expired.append(slot)
        event(state,'LEASE_EXPIRED',slot=slot,topic_id=lease['topic_id'])
    return expired


def owned(state, slot, session, fence, at=None):
    lease=state['leases'].get(slot)
    if not lease or lease['session']!=session or lease['fence']!=fence or lease['expires_at']<=(timestamp() if at is None else at):
        raise ValueError('Valid owned lease and fencing ID required')
    return lease


def claim_order(topic):
    """Vietnamese first, then English; repairs before fresh topics inside a language."""
    return (LANGUAGES.index(topic['language']),0 if topic['status']=='NEEDS_REPAIR' else 1,topic['topic_id'])


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
        candidates=sorted((x for x in state['topics'].values() if x['status'] in ('NEEDS_REPAIR','PLANNED') and x['language'] not in full),key=claim_order)
        busy={x['topic_id'] for x in state['leases'].values()}
        candidate=next((x for x in candidates if x['topic_id'] not in busy),None)
        if not candidate:raise ValueError('No admissible researched topic; external research required')
        lease={'slot':available,'session':session,'agent_id':agent_id,'topic_id':candidate['topic_id'],
               'language':candidate['language'],'fence':fence,'heartbeat_at':now(),'expires_at':timestamp()+ttl}
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


def submit(store,slot,session,fence,article,max_repairs=3):
    state=store.read();lease=owned(state,slot,session,fence)
    if state['topics'][lease['topic_id']]['status']=='NEEDS_REVIEW':raise ValueError('Held topic requires owner review before another revision')
    if article.get('topic_id')!=lease['topic_id'] or article.get('agent_id')!=lease['agent_id'] or article.get('session')!=session:
        raise ValueError('Submission provenance does not match lease')
    if article.get('language')!=locale(state['topics'][lease['topic_id']]['language']):
        raise ValueError('Submission language does not match the topic language')
    if len(str(article.get('body_html','')))>200_000:raise ValueError('Draft too large')
    sha=store.put_document(article) # Durable BEFORE releasing or changing state.
    def transaction(state):
        lease=owned(state,slot,session,fence)
        tid=lease['topic_id'];old=state['submissions'].get(tid)
        repairs=(old or {}).get('repair_count',0)
        if old and old['article_sha']!=sha:
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
        state['topics'][tid]['status']='DRAFT_READY'
        event(state,'SUBMISSION',topic_id=tid,article_sha=sha,agent_id=lease['agent_id'])
        return value
    return store.mutate(transaction)


def release(store,slot,session,fence):
    def transaction(state):
        lease=owned(state,slot,session,fence)
        tid=lease['topic_id']
        if state['topics'][tid]['status']=='CLAIMED':
            state['topics'][tid]['status']='DRAFT_READY' if tid in state['submissions'] else 'PLANNED'
        del state['leases'][slot]
        event(state,'RELEASE',slot=slot,topic_id=tid)
    return store.mutate(transaction)
