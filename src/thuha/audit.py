"""Public WordPress inventory and evidence-based, non-destructive SEO triage."""
import concurrent.futures
import csv
import html
import io
import json
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit
from .common import SITE, now, norm, urlkey, digest, signature, category_path, save
from .http import WordPress


class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text, self.links, self.images, self.headings = [], [], [], []
        self.canonicals, self.robots, self.descriptions, self.schema = [], [], [], []
        self.title, self.heading, self.tag, self.hidden = '', None, '', 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ('script','style'):
            self.hidden += 1
        if tag == 'title':
            self.tag = 'title'
        if re.fullmatch('h[1-3]', tag):
            self.heading = [tag, '']
        if tag == 'a' and attrs.get('href'):
            self.links.append(attrs['href'])
        if tag == 'img':
            self.images.append({'src':attrs.get('src'), 'alt':attrs.get('alt')})
        if tag == 'link' and 'canonical' in attrs.get('rel','').split():
            self.canonicals.append(attrs.get('href'))
        if tag == 'meta' and attrs.get('name','').lower() == 'robots':
            self.robots.append(attrs.get('content',''))
        if tag == 'meta' and attrs.get('name','').lower() == 'description':
            self.descriptions.append(attrs.get('content',''))
        if tag == 'script' and attrs.get('type') == 'application/ld+json':
            self.schema.append(True)

    def handle_endtag(self, tag):
        if tag in ('script','style'):
            self.hidden = max(0,self.hidden-1)
        if tag == 'title':
            self.tag = ''
        if self.heading and tag == self.heading[0]:
            self.headings.append(self.heading)
            self.heading = None

    def handle_data(self, data):
        if self.hidden:
            return
        if self.tag == 'title':
            self.title += data
        if self.heading:
            self.heading[1] += data
        self.text.append(data)


def parse(source):
    p = Page()
    p.feed(source)
    return p


def summarize(post, kind):
    p = parse(post.get('content',{}).get('rendered',''))
    seo, meta = post.get('yoast_head_json',{}), post.get('meta',{})
    links = sorted({urlkey(urljoin(post['link'],x)) for x in p.links
                    if urlsplit(urljoin(post['link'],x)).netloc == urlsplit(SITE).netloc
                    and urlsplit(urljoin(post['link'],x)).scheme == 'https'})
    text = ' '.join(p.text)
    return {'id':post['id'], 'type':kind, 'url':post['link'], 'slug':post['slug'],
            'status':post['status'], 'title':html.unescape(post.get('title',{}).get('rendered','')),
            'modified':post.get('modified_gmt',post.get('modified')), 'categories':post.get('categories',[]),
            'featured_media':post.get('featured_media',0), 'focus_keyword':meta.get('_yoast_wpseo_focuskw'),
            'focus_keyword_visibility':'EXPOSED' if '_yoast_wpseo_focuskw' in meta else 'UNKNOWN',
            'seo_title':seo.get('title'), 'meta_description':seo.get('description'),
            'canonical':seo.get('canonical'), 'robots':seo.get('robots'),
            'schema_types':[x.get('@type') for x in seo.get('schema',{}).get('@graph',[])],
            'declared_language':seo.get('og_locale'), 'body_headings':p.headings,
            'body_internal_links':links, 'external_sources':sorted({urljoin(post['link'],x) for x in p.links
                 if urlsplit(urljoin(post['link'],x)).scheme=='https' and urlsplit(urljoin(post['link'],x)).netloc!=urlsplit(SITE).netloc}),
            'body_images':p.images, 'word_count':len(re.findall(r'\b[\w-]+\b',text)),
            'content_sha256':digest(post.get('content',{}).get('rendered','').encode()),
            'content_signature':signature(text), 'semantic_factual_review':'NOT_PERFORMED',
            'search_intent':'UNREVIEWED', 'agent_attribution':'UNKNOWN'}


def inventory(client=None, check_pages=True):
    client = client or WordPress()
    result = {'site':SITE,'started_at':now(),'complete':False,'errors':[], 'items':[], 'categories':[], 'media':[]}
    try:
        fields = 'id,link,slug,status,title,content,modified_gmt,categories,featured_media,meta,yoast_head_json'
        for kind in ('posts','pages'):
            rows = client.collection(kind,status='publish',orderby='id',order='asc',_fields=fields)
            result['items'].extend(summarize(x,kind) for x in rows)
        result['categories'] = client.collection('categories',hide_empty='false',_fields='id,slug,name,parent,link')
        for item in result['items']:
            item['category_paths'] = [category_path(x,result['categories']) for x in item['categories']]
        media_ids = sorted({x['featured_media'] for x in result['items'] if x['featured_media']})
        for start in range(0,len(media_ids),100):
            rows = client.collection('media',include=','.join(map(str,media_ids[start:start+100])),_fields='id,alt_text,source_url')
            result['media'].extend(rows)
        if check_pages:
            def check(item):
                try:
                    source, headers, status = client.page(item['url'])
                    p = parse(source)
                    return {'http_status':status,'canonicals':p.canonicals,'robots':p.robots,
                            'x_robots_tag':headers.get('X-Robots-Tag',headers.get('x-robots-tag')),
                            'title':p.title,'descriptions':p.descriptions,'h1_count':sum(x[0]=='h1' for x in p.headings),
                            'schema_present':bool(p.schema),'html_sha256':digest(source.encode()),'checked_at':now()}
                except Exception as exc:
                    return {'http_status':None,'error':str(exc),'checked_at':now()}
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                checks = list(pool.map(check,result['items']))
            for item, check_result in zip(result['items'],checks):
                item['public_check'] = check_result
                if check_result.get('error'):
                    result['errors'].append({'id':item['id'],'stage':'public-page','error':check_result['error']})
        result['collection_complete'] = True
        result['complete'] = not result['errors']
    except Exception as exc:
        result['errors'].append({'stage':'inventory','error':str(exc)})
    result['captured_at'] = now()
    result['counts'] = {k:sum(x['type']==k for x in result['items']) for k in ('posts','pages')}
    result['counts']['live_verified_posts'] = sum(x['type']=='posts' and x.get('public_check',{}).get('http_status')==200 and
          x.get('public_check',{}).get('canonicals')==[x['url']] for x in result['items'])
    return result


def matrix(inv):
    issues, incoming = [], {}
    for item in inv['items']:
        for link in item['body_internal_links']:
            incoming.setdefault(link,set()).add(item['id'])
    categories = {x['id']:x for x in inv['categories']}
    canonicals = {}
    for item in inv['items']:
        def flag(priority,code,evidence):
            issues.append({'priority':priority,'post_id':item['id'],'url':item['url'],'issue':code,'evidence':evidence,'action':'REVIEW_ONLY'})
        if item['type']=='posts' and not item['featured_media']:flag('P1','MISSING_FEATURED_IMAGE','featured_media=0')
        if item['focus_keyword_visibility']=='EXPOSED' and not item['focus_keyword']:flag('P2','EMPTY_FOCUS_KEYWORD','exposed Yoast focus keyword is empty; not a Google indexing factor')
        if item['focus_keyword_visibility']=='UNKNOWN':flag('P2','FOCUS_KEYWORD_UNKNOWN','field is not exposed; authenticated read required')
        if not item['seo_title']:flag('P1','MISSING_SEO_TITLE','Yoast title absent')
        if not item['meta_description']:flag('P1','MISSING_META_DESCRIPTION','Yoast description absent')
        if not item['body_internal_links']:flag('P1','NO_BODY_INTERNAL_LINKS','No same-origin anchor found in REST article body')
        if not incoming.get(urlkey(item['url'])):flag('P2','NO_INBOUND_BODY_LINKS','Potential orphan in captured body-link graph; menus/footer not included')
        targets={urlkey(x['url']) for x in inv['items']}
        for link in item['body_internal_links']:
            if link not in targets:flag('P2','INTERNAL_TARGET_NOT_IN_INVENTORY',link+'; may be category, media, or other resource, not proven broken')
        if item['word_count']<300:flag('P2','SHORT_BODY_REVIEW',str(item['word_count'])+' words; length alone is not a quality verdict')
        if len([x for x in item['body_headings'] if x[0]=='h2'])<2:flag('P2','HEADING_STRUCTURE_REVIEW','Fewer than two body H2 headings')
        c=item.get('public_check',{})
        if c.get('error'):flag('P1','PUBLIC_FETCH_UNKNOWN',c['error'])
        if c.get('http_status')==200 and c.get('canonicals')!=[item['url']]:flag('P1','CANONICAL_REVIEW',json.dumps(c.get('canonicals')))
        if c.get('http_status')==200 and c.get('h1_count')!=1:flag('P2','H1_COUNT_REVIEW',str(c.get('h1_count')))
        if 'noindex' in str(c.get('robots',[])).lower() or 'noindex' in str(c.get('x_robots_tag')).lower():flag('P1','NOINDEX_DIRECTIVE','Rendered robots or HTTP header; no Google index-status inference')
        canonical=item.get('canonical')
        if canonical:canonicals.setdefault(canonical,[]).append(item)
    for canonical,items in canonicals.items():
        if len(items)>1:
            for item in items:issues.append({'priority':'P1','post_id':item['id'],'url':item['url'],'issue':'SHARED_CANONICAL','evidence':canonical,'action':'REVIEW_ONLY'})
    for i,a in enumerate(inv['items']):
        for b in inv['items'][i+1:]:
            sa,sb=set(a['content_signature']),set(b['content_signature'])
            overlap=len(sa&sb)/max(1,min(len(sa),len(sb)))
            if a['content_sha256']==b['content_sha256'] or overlap>.75:
                issues.append({'priority':'P1','post_id':a['id'],'url':a['url'],'issue':'CONTENT_OVERLAP_REVIEW','evidence':str(b['id'])+' overlap='+str(round(overlap,3)),'action':'HUMAN_INTENT_REVIEW'})
    return issues


def write_audit(inv, directory):
    from pathlib import Path
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    save(directory/'inventory.json',inv)
    issues=matrix(inv)
    save(directory/'seo-matrix.json',issues)
    save(directory/'protected-urls.json',{'site':SITE,'captured_at':inv['captured_at'],'urls':[{'id':x['id'],'url':x['url'],'slug':x['slug'],'canonical':x['canonical']} for x in inv['items']]})
    with (directory/'seo-matrix.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['priority','post_id','url','issue','evidence','action']);w.writeheader();w.writerows(issues)
    summary={'site':SITE,'captured_at':inv['captured_at'],'complete':inv['complete'],'counts':inv['counts'],
             'matrix_rows':len(issues),'errors':inv['errors'],'factual_english_semantic_review':'NOT_PERFORMED',
             'google_index_status':'UNKNOWN — no Search Console evidence', 'production_writes':0}
    save(directory/'audit-summary.json',summary)
    return summary
