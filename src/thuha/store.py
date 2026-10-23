"""Local flock transactions and cross-host GitHub compare-and-swap transactions.

The remote store is the only valid production coordinator. A local checkout's
flock does NOT coordinate other computers. Immutable documents are separate
from the small mutable registry, so article bodies never bloat the CAS file.
"""
import base64
import copy
import fcntl
import json
import os
import re
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from .common import ROOT, REPO, canonical_json, digest, load, now, save


def initial():
    return {'schema':4,'version':0,'topics':{},'leases':{},'submissions':{},'qa':{},
            'intents':{},'receipts':{},'research_requests':{},'events':[],
            'controls':{'paused':False,'emergency_stop':False}}


def validate(state, previous=None):
    if state.get('schema') != 4:
        raise ValueError('Unknown state schema')
    seen = set()
    previous_event=None
    for entry in state['events']:
        unsigned={k:v for k,v in entry.items() if k!='sha256'}
        if entry.get('previous')!=previous_event or digest(unsigned)!=entry.get('sha256'):
            raise ValueError('State event hash chain is invalid')
        previous_event=entry['sha256']
    for slot, lease in state['leases'].items():
        if slot not in ['W'+str(i) for i in range(1,10)] or lease['topic_id'] in seen:
            raise ValueError('Invalid or duplicate topic lease')
        seen.add(lease['topic_id'])
        if lease['topic_id'] not in state['topics']:
            raise ValueError('Lease references missing topic')
    if previous:
        if state['events'][:len(previous['events'])]!=previous['events']:
            raise ValueError('Existing state events cannot be rewritten')
        for key, value in previous['receipts'].items():
            if state['receipts'].get(key) != value:
                raise ValueError('Publication receipts are append-only')
        for key, value in previous['intents'].items():
            if key not in state['intents'] or state['intents'][key]['article_sha'] != value['article_sha']:
                raise ValueError('Publication intents cannot disappear or change source')


def event(state, action, **fields):
    previous = state['events'][-1]['sha256'] if state['events'] else None
    value={'at':now(),'action':action,'previous':previous,**fields}
    value['sha256']=digest(value)
    state['events'].append(value)


class LocalStore:
    durable_remote = False

    def __init__(self, directory=None):
        self.directory=Path(directory or ROOT/'.runtime')
        self.directory.mkdir(parents=True,exist_ok=True)
        self.path=self.directory/'state.json'

    def read(self):
        value=load(self.path) if self.path.exists() else initial()
        validate(value)
        return value

    def mutate(self, callback):
        with (self.directory/'state.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            state=self.read();old=copy.deepcopy(state)
            result=callback(state)
            validate(state,old)
            state['version']+=1
            save(self.path,state)
            return result

    def put_document(self, value):
        sha=digest(value);path=self.directory/'documents'/(sha+'.json')
        path.parent.mkdir(exist_ok=True)
        fd,temp=tempfile.mkstemp(prefix='.document-',dir=path.parent)
        try:
            with os.fdopen(fd,'wb') as f:
                f.write(canonical_json(value));f.flush();os.fsync(f.fileno())
            try:os.link(temp,path) # Atomic create, never replace an existing address.
            except FileExistsError:
                if self.get_document(sha)!=value:raise ValueError('Immutable document collision')
            directory=os.open(path.parent,os.O_DIRECTORY)
            try:os.fsync(directory)
            finally:os.close(directory)
        finally:
            if os.path.exists(temp):os.unlink(temp)
        return sha

    def get_document(self, sha):
        if not re.fullmatch('[a-f0-9]{64}',sha):raise ValueError('Invalid document address')
        value=load(self.directory/'documents'/(sha+'.json'))
        if digest(value)!=sha:raise ValueError('Document changed after checkpoint')
        return value


class GitHub:
    def __init__(self, token=None):
        self.token=token or os.environ.get('THUHA_GITHUB_TOKEN')
        if not self.token:raise ValueError('GitHub state credential is missing')

    def request(self, method, path, body=None):
        if not path.startswith('/repos/'+REPO+'/'):
            raise ValueError('GitHub access is confined to the destination repository')
        headers={'Authorization':'Bearer '+self.token,'Accept':'application/vnd.github+json',
                 'X-GitHub-Api-Version':'2022-11-28','User-Agent':'ThuHa-Writer/4'}
        req=urllib.request.Request('https://api.github.com'+path,
                 None if body is None else canonical_json(body),headers,method=method)
        try:
            with urllib.request.urlopen(req,timeout=25) as r:
                raw=r.read()
                return json.loads(raw) if raw else {} # repository_dispatch responds HTTP 204
        except urllib.error.HTTPError as e:
            # Expose a status code only, never the request, headers or token.
            raise GitError(e.code) from None


class GitError(RuntimeError):
    def __init__(self,status):
        self.status=status;super().__init__('GitHub HTTP '+str(status))


class GitStore:
    durable_remote=True
    branch='factory-state'
    state_path='data/state/factory.json'

    def __init__(self, api=None):self.api=api or GitHub()

    def _get(self,path):
        r=self.api.request('GET','/repos/'+REPO+'/contents/'+path+'?ref='+self.branch)
        if r.get('encoding')=='base64' and r.get('content'):
            raw=base64.b64decode(r['content'])
        else:
            blob=self.api.request('GET','/repos/'+REPO+'/git/blobs/'+r['sha'])
            raw=base64.b64decode(blob['content'])
        return json.loads(raw),r['sha']

    def _state(self):
        try:return self._get(self.state_path)
        except GitError as e:
            if e.status==404:return initial(),None
            raise

    def read(self):
        state,_=self._state();validate(state);return state

    def _put(self,path,value,sha=None):
        if path!=self.state_path and not re.fullmatch(r'data/documents/[a-f0-9]{64}\.json',path):
            raise ValueError('Runtime state adapter cannot write code/config/workflows')
        self.ensure_branch()
        payload={'branch':self.branch,'message':'factory checkpoint [skip ci]',
                 'content':base64.b64encode(canonical_json(value)).decode()}
        if sha:payload['sha']=sha
        return self.api.request('PUT','/repos/'+REPO+'/contents/'+path,payload)

    def ensure_branch(self):
        prefix='/repos/'+REPO+'/git/'
        try:self.api.request('GET',prefix+'ref/heads/'+self.branch)
        except GitError as error:
            if error.status!=404:raise
            main=self.api.request('GET',prefix+'ref/heads/main')
            try:self.api.request('POST',prefix+'refs',{'ref':'refs/heads/'+self.branch,'sha':main['object']['sha']})
            except GitError as race:
                if race.status!=422:raise
                self.api.request('GET',prefix+'ref/heads/'+self.branch)

    def mutate(self,callback):
        for attempt in range(5):
            state,sha=self._state();old=copy.deepcopy(state)
            validate(state)
            result=callback(state)
            validate(state,old);state['version']+=1
            if len(canonical_json(state))>15_000_000:
                raise ValueError('Registry size guard reached; archive events before scaling')
            try:
                self._put(self.state_path,state,sha)
                return result
            except GitError as e:
                if e.status not in (409,422) or attempt==4:raise
        raise ValueError('CAS retry limit reached')

    def put_document(self,value):
        sha=digest(value);path='data/documents/'+sha+'.json'
        try:
            old,_=self._get(path)
            if old!=value:raise ValueError('Immutable remote document collision')
        except GitError as e:
            if e.status!=404:raise
            try:self._put(path,value)
            except GitError as race:
                if race.status not in (409,422):raise
                old,_=self._get(path)
                if old!=value:raise ValueError('Document CAS conflict')
        return sha

    def get_document(self,sha):
        if not re.fullmatch('[a-f0-9]{64}',sha):raise ValueError('Invalid document address')
        value,_=self._get('data/documents/'+sha+'.json')
        if digest(value)!=sha:raise ValueError('Immutable remote document altered')
        return value
