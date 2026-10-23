"""Plain-file view of every stored draft, one JSON per topic under drafts/<language>/.

The ledger is the authority; this export lets a person (or the next session) read a draft, its sources and its state
without a ledger tool, and shows in the repository what exists. It is derived, deterministic and repeatable. A draft is
not a published post and a waiting draft is not QA-passed: the status says exactly where it stands.
"""
from pathlib import Path
from .audit import parse
from .common import norm, save
from .language import LANGUAGES


def record(state,get_document,tid):
    topic=state['topics'][tid];sub=state['submissions'][tid]
    article=get_document(sub['article_sha'])
    evidence={}
    for ref in article.get('sources',[]):
        try:evidence[ref['document']]=get_document(ref['document'])
        except (ValueError,OSError,KeyError):evidence[ref['document']]=None
    qa=state['qa'].get(tid)
    return {'topic_id':tid,'language':topic['language'],'status':topic['status'],'waiting_for':topic.get('waiting_for',[]),
            'article_sha':sub['article_sha'],'submitted_at':sub.get('submitted_at'),'repair_count':sub.get('repair_count',0),
            'agent_id':sub.get('agent_id'),'proposed_url':topic.get('proposed_url'),'category_id':topic.get('category_id'),
            'review_recorded':tid in state.get('reviews',{}),'qa':{'status':qa['status'],'report_sha':qa['report_sha']} if qa else None,
            'receipt':state['receipts'].get(tid),
            'source_documents':[x['document'] for x in article.get('sources',[])],'source_evidence':evidence,'article':article}


def words(article):
    return len(norm(' '.join(parse(article.get('body_html','')).text)).split())


def export(state,get_document,target):
    """Write drafts/<lang>/<ID>.json for every topic that has a stored draft, plus INDEX.md. Returns the relative paths."""
    target=Path(target);written=[];rows=[]
    for lang in LANGUAGES:
        for tid in sorted(t for t,v in state['topics'].items() if v['language']==lang and t in state['submissions']):
            value=record(state,get_document,tid)
            save(target/lang/(tid+'.json'),value)
            written.append(lang+'/'+tid+'.json')
            rows.append((lang,tid,value))
    lines=['# Stored drafts','',
           'Derived from the ledger by `python3 scripts/export_drafts.py`; the ledger is the authority. A draft is **not** a published post, '
           'and a draft that waits for data is **not** READY and has **not** passed QA.','',
           '| Topic | Language | Status | Waiting for | Review | QA | Units | Title |','|---|---|---|---|---|---|---|---|']
    for lang,tid,value in rows:
        article=value['article']
        lines.append('| ['+tid+']('+lang+'/'+tid+'.json) | '+lang+' | '+value['status']+' | '+(', '.join(value['waiting_for']) or '—')+' | '
                     +('recorded' if value['review_recorded'] else 'none')+' | '+(value['qa']['status'] if value['qa'] else 'not run')+' | '
                     +str(words(article))+' | '+str(article.get('title','')).replace('|','/')+' |')
    if not rows:lines.append('| — | — | — | — | — | — | — | no stored draft yet |')
    target.mkdir(parents=True,exist_ok=True)
    (target/'INDEX.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return written
