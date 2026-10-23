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
from .language import LANGUAGES, url_language


class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text, self.links, self.images, self.headings = [], [], [], []
        self.canonicals, self.robots, self.descriptions, self.schema = [], [], [], []
        self.html_lang, self.hreflangs, self.rels = None, [], {}
        self.valid_schema_types=[]
        self.schema_errors=0
        self._ld=False
        self._ld_raw=[]
        self.title, self.heading, self.tag, self.hidden = '', None, '', 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'html' and attrs.get('lang'):
            self.html_lang = attrs['lang']
        if tag == 'link' and 'alternate' in attrs.get('rel','').split() and attrs.get('hreflang'):
            self.hreflangs.append((attrs['hreflang'], attrs.get('href')))
        if tag in ('link','a') and attrs.get('href'):
            for rel in attrs.get('rel','').split():
                if rel in ('next','prev'):self.rels.setdefault(rel,[]).append(attrs['href'])
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
            self._ld=True
            self._ld_raw=[]

    def handle_endtag(self, tag):
        if tag=='script' and self._ld:
            try:
                obj=json.loads(''.join(self._ld_raw))
                if not isinstance(obj,dict) or not obj.get('@context'):raise ValueError('Missing schema context')
                nodes=obj.get('@graph',[obj])
                for node in nodes:
                    types=node.get('@type',[])
                    self.valid_schema_types.extend(types if isinstance(types,list) else [types])
            except (ValueError,TypeError,AttributeError):self.schema_errors+=1
            self._ld=False
        if tag in ('script','style'):
            self.hidden = max(0,self.hidden-1)
        if tag == 'title':
            self.tag = ''
        if self.heading and tag == self.heading[0]:
            self.headings.append(self.heading)
            self.heading = None

    def handle_data(self, data):
        if self._ld:
            self._ld_raw.append(data)
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


def media_library(client, items):
    """Every image of the media library plus the featured images of existing posts, one row per attachment.

    A new article may only use an existing image that already has alt text in its own language, and nothing but a
    listing of the whole library can show a Vietnamese-alt image that no post uses yet.
    """
    rows = {}
    for row in client.collection('media', _fields='id,alt_text,source_url,media_type'):
        if row.get('media_type', 'image') == 'image':
            rows[row['id']] = {k: row.get(k) for k in ('id', 'alt_text', 'source_url')}
    wanted = sorted({x['featured_media'] for x in items if x['featured_media'] and x['featured_media'] not in rows})
    for start in range(0, len(wanted), 100):
        for row in client.collection('media', include=','.join(map(str, wanted[start:start+100])), _fields='id,alt_text,source_url'):
            rows[row['id']] = {k: row.get(k) for k in ('id', 'alt_text', 'source_url')}
    return [rows[k] for k in sorted(rows)]


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
        result['media'] = media_library(client, result['items'])
        result['media_library'] = 'complete'  # every image of the library, not only the featured ones
        if check_pages:
            def check(item):
                try:
                    source, headers, status = client.page(item['url'])
                    p = parse(source)
                    return {'http_status':status,'canonicals':p.canonicals,'robots':p.robots,
                            'x_robots_tag':headers.get('X-Robots-Tag',headers.get('x-robots-tag')),
                            'title':p.title,'descriptions':p.descriptions,'h1_count':sum(x[0]=='h1' for x in p.headings),
                            'schema_present':bool(p.schema),'schema_types':p.valid_schema_types,'schema_json_errors':p.schema_errors,
                            'html_sha256':digest(source.encode()),'checked_at':now()}
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
    for item in result['items']:
        item['language'] = url_language(item['url']) or 'en'
    for category in result['categories']:
        # The URL namespace is all the public collection offers; the adapter inventory carries the verified label.
        category['language'] = url_language(category.get('link') or '') or 'en'
    result['language_source'] = 'public-rest-unverified'  # the public collection can hide native VI posts
    result['counts'] = counts(result['items'])
    return result


def counts(items):
    """Published posts by language; pages, drafts and trash never count toward a target."""
    posts = [x for x in items if x['type'] == 'posts' and x['status'] == 'publish']
    out = {k:sum(x['type']==k for x in items) for k in ('posts','pages')}
    out['posts'] = len(posts)
    out['posts_by_language'] = {lang:sum(x['language'] == lang for x in posts) for lang in LANGUAGES}
    out['pages_by_language'] = {lang:sum(x['language'] == lang for x in items if x['type'] == 'pages') for lang in LANGUAGES}
    out['live_verified_posts'] = sum(x['type']=='posts' and x.get('public_check',{}).get('http_status')==200 and
          x.get('public_check',{}).get('canonicals')==[x['url']] for x in items)
    return out


def check_item(client, item):
    try:
        source, headers, status = client.page(item['url'])
        p = parse(source)
        return {'http_status':status,'canonicals':p.canonicals,'robots':p.robots,
                'x_robots_tag':headers.get('X-Robots-Tag',headers.get('x-robots-tag')),
                'title':p.title,'descriptions':p.descriptions,'h1_count':sum(x[0]=='h1' for x in p.headings),
                'html_lang':p.html_lang,'hreflangs':p.hreflangs,
                'schema_present':bool(p.schema),'schema_types':p.valid_schema_types,'schema_json_errors':p.schema_errors,
                'html_sha256':digest(source.encode()),'checked_at':now()}
    except Exception as exc:
        return {'http_status':None,'error':str(exc),'checked_at':now()}


def inventory_bilingual(adapter, client=None, check_pages=True):
    """Complete EN+VI inventory read through the companion adapter, never the public collection."""
    result = {'site':SITE,'schema':'bilingual-1','language_source':'adapter','started_at':now(),
              'complete':False,'errors':[],'items':[],'categories':[],'media':[]}
    try:
        for kind, label in (('post','posts'),('page','pages')):
            for raw in adapter.inventory_rows(kind):
                if raw.get('language') not in LANGUAGES:
                    raise ValueError('Adapter row without a verified language: '+str(raw.get('id')))
                post = {'id':raw['id'],'link':raw['link'],'slug':raw['slug'],'status':raw['status'],
                        'title':{'rendered':raw['title']},'content':{'rendered':raw['content']},
                        'modified_gmt':raw.get('modified_gmt'),'categories':raw.get('categories',[]),
                        'featured_media':raw.get('featured_media',0),'meta':raw.get('meta',{}),
                        'yoast_head_json':{'title':raw.get('meta',{}).get('_yoast_wpseo_title'),
                                           'description':raw.get('meta',{}).get('_yoast_wpseo_metadesc'),
                                           'canonical':raw['link']}}
                item = summarize(post, label)
                item['language'] = raw['language']
                result['items'].append(item)
        result['categories'] = adapter.categories()
        for item in result['items']:
            item['category_paths'] = [category_path(x,result['categories']) for x in item['categories']]
        result['media'] = media_library(client or adapter, result['items'])
        result['media_library'] = 'complete'
        if check_pages:
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                checks = list(pool.map(lambda i: check_item(client or adapter, i), result['items']))
            for item, check_result in zip(result['items'],checks):
                item['public_check'] = check_result
                if check_result.get('error'):
                    result['errors'].append({'id':item['id'],'stage':'public-page','error':check_result['error']})
        result['collection_complete'] = True
        result['complete'] = not result['errors']
    except Exception as exc:
        result['errors'].append({'stage':'inventory','error':str(exc)})
    result['captured_at'] = now()
    result['counts'] = counts(result['items'])
    return result


def snapshot_inventory(root=None):
    """Offline view of the committed 2026-10-22 authenticated snapshot (275 EN, 0 VI).

    It lacks article bodies and live page checks, so it feeds planning and the
    dashboard only: publishing needs a fresh adapter inventory.
    """
    from pathlib import Path
    from .common import ROOT, load
    base = Path(root or ROOT) / 'data/bilingual'
    posts = load(base / 'live-posts-2026-10-22.json')
    manifest = load(base / 'live-categories-2026-10-22.json')
    items = [{'id':p['id'],'type':'posts','url':p['link'],'slug':p['slug'],'status':p['status'],
              'title':html.unescape(p['title']['rendered']),'categories':p['categories'],'language':'en',
              'content_signature':[]} for p in posts['posts']]
    cats = [{'id':c['id'],'parent':c['parent'],'name':html.unescape(c['name']),'slug':c['slug'],'link':c['link'],
             'language':c['language']} for c in manifest['categories']]
    return {'site':SITE,'schema':'bilingual-1','language_source':'authenticated-snapshot','complete':True,'errors':[],
            'captured_at':posts['captured_at'].replace('Z','+00:00'),'items':items,'categories':cats,'media':[],
            'counts':counts(items)}


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
        if c.get('http_status')==200 and c.get('title')!=item.get('seo_title'):flag('P1','RENDERED_SEO_TITLE_MISMATCH','Rendered title differs from REST Yoast title')
        if c.get('http_status')==200 and c.get('descriptions')!=[item.get('meta_description')]:flag('P1','RENDERED_META_DESCRIPTION_MISMATCH','Rendered meta description differs from REST Yoast description')
        if c.get('schema_json_errors'):flag('P1','INVALID_SCHEMA_JSON',str(c['schema_json_errors'])+' invalid JSON-LD blocks')
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
