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
from .language import LANGUAGES, TOPIC_ID, LEGACY_TOPIC_ID, split_url, topic_language
from .quota import CLOSED_PHASES

SCHEMA = 5


def initial():
    return {'schema':SCHEMA,'version':0,'topics':{},'leases':{},'submissions':{},'qa':{},
            'intents':{},'receipts':{},'research_requests':{},'events':[],
            'controls':{'paused':False,'emergency_stop':False}}


def migrate(state):
    """Schema 4 (English-only) to 5 (bilingual), in place; append-only and idempotent.

    Every pre-existing topic, request and intent was English. Receipts are left
    byte-identical because they are append-only evidence.
    """
    if state.get('schema') == SCHEMA:
        return state
    if state.get('schema') != 4:
        raise ValueError('Unknown state schema')
    for topic in state['topics'].values():
        topic.setdefault('language', 'en')
    for request in state['research_requests'].values():
        request.setdefault('language', 'en')
    for intent in state['intents'].values():
        intent.setdefault('language', 'en')
        # Schema 5 says PUBLISHED where schema 4 said VERIFIED, and has no VERIFY_PENDING (an unknown outcome).
        intent['phase'] = {'VERIFIED': 'PUBLISHED', 'VERIFY_PENDING': 'NEEDS_RECONCILIATION'}.get(intent.get('phase'), intent.get('phase'))
    for topic in state['topics'].values():
        if topic.get('status') == 'VERIFIED':
            topic['status'] = 'PUBLISHED'
    for lease in state['leases'].values():
        lease.setdefault('language', 'en')
    state['schema'] = SCHEMA
    # Deterministic on purpose: the entry takes the timestamp of the last event it follows, so every process that
    # migrates the same schema-4 chain appends the identical entry and the chains stay comparable (ledger.py relies on it).
    at = state['events'][-1]['at'] if state['events'] else '1970-01-01T00:00:00+00:00'
    previous = state['events'][-1]['sha256'] if state['events'] else None
    value = {'at': at, 'action': 'SCHEMA_MIGRATION', 'previous': previous, 'from': 4, 'to': SCHEMA, 'legacy_language': 'en'}
    value['sha256'] = digest(value)
    state['events'].append(value)
    return state


def validate_topic(tid, topic):
    lang = topic.get('language')
    if lang not in LANGUAGES:
        raise ValueError('Topic has no valid language')
    if TOPIC_ID.fullmatch(tid) or LEGACY_TOPIC_ID.fullmatch(tid):
        if topic_language(tid) != lang:
            raise ValueError('Topic ID language does not match topic language')
    if topic.get('proposed_url'):
        url_lang, _ = split_url(topic['proposed_url'])
        if url_lang != lang:
            raise ValueError('Topic URL is outside its language namespace')


def validate(state, previous=None):
    if state.get('schema') != SCHEMA:
        raise ValueError('Unknown state schema')
    slugs = {}
    for tid, topic in state['topics'].items():
        validate_topic(tid, topic)
        if topic.get('proposed_url'):
            # WordPress post slugs are unique across languages even though URLs differ.
            slug = split_url(topic['proposed_url'])[1]
            if slugs.setdefault(slug, tid) != tid:
                raise ValueError('Two topics share one WordPress slug')
    for tid, intent in state['intents'].items():
        if intent.get('language') != state['topics'].get(tid, {}).get('language'):
            raise ValueError('Publication intent language does not match its topic')
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
        if lease.get('language') != state['topics'][lease['topic_id']]['language']:
            raise ValueError('Lease language does not match its topic')
    if previous:
        if state['events'][:len(previous['events'])]!=previous['events']:
            raise ValueError('Existing state events cannot be rewritten')
        for key, value in previous['receipts'].items():
            if state['receipts'].get(key) != value:
                raise ValueError('Publication receipts are append-only')
        for key, value in previous['intents'].items():
            if value.get('phase') in CLOSED_PHASES:
                continue  # never reached WordPress: may be replaced by a fresh reservation for a repaired article
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
        value=migrate(load(self.path)) if self.path.exists() else initial()
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

    def raw(self):
        """The stored ledger exactly as written (possibly schema 4) and its revision; no migration, no validation."""
        return (load(self.path) if self.path.exists() else initial()),None

    def adopt(self, builder):
        """Replace the whole ledger with `builder(raw)`, or keep it when the builder returns None."""
        with (self.directory/'state.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            current,_=self.raw()
            new=builder(copy.deepcopy(current))
            if new is None:return None
            validate(new);new['version']=max(current.get('version',0),new.get('version',0))+1
            save(self.path,new)
            return new

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


class StateConflict(RuntimeError):
    """The branch moved under a ledger commit; the commit was dropped and the caller starts again from the new ledger."""


class GitBranchStore:
    """Durable state through ordinary git commits and pushes on one branch.

    Used when a session may push only to its designated branch and the GitHub
    REST write endpoints are closed by the environment. The same paths as the
    factory-state adapter are used (data/state/factory.json, data/documents/),
    so a trusted Actions task can later promote the ledger to factory-state.
    Every mutation is committed with an explicit pathspec, so unrelated working
    tree changes are never swept into a checkpoint, and pushed before it is
    reported durable.

    A rejected push of the ledger is a compare-and-swap conflict: our commit is dropped, the branch is brought to the
    remote tip and the mutation runs again on the new ledger (a rebase would leave conflict markers in the JSON).
    Documents are separate content-addressed files, so a rejected push of a document is simply rebased.
    """
    durable_remote=True
    state_path='data/state/factory.json'

    def __init__(self,root=None,branch=None,remote='origin',runner=None):
        import subprocess
        self.root=Path(root or ROOT);self.remote=remote
        self._run=runner or (lambda args,**kw:subprocess.run(['git','-C',str(self.root)]+args,check=True,capture_output=True,text=True,**kw))
        self.branch=branch or self._run(['rev-parse','--abbrev-ref','HEAD']).stdout.strip()
        if self.branch in ('HEAD','main','master'):raise ValueError('Git branch store needs a non-default session branch')
        self.lock=self.root/'.git'/'thuha-state.lock'

    def read(self):
        path=self.root/self.state_path
        value=migrate(load(path)) if path.exists() else initial()
        validate(value);return value

    def _dirty(self,relative):
        return bool(self._run(['status','--porcelain','--',relative]).stdout.strip())

    def _untracked(self,relative):
        return self._run(['status','--porcelain','--',relative]).stdout.startswith('??')

    def _commit(self,paths,message):
        self._run(['add','--']+paths)
        self._run(['commit','-q','-m',message,'--']+paths)

    def _push(self,rebase):
        for attempt in range(5):
            try:
                self._run(['push','-q',self.remote,'HEAD:refs/heads/'+self.branch]);return
            except Exception:
                if attempt==4:raise RuntimeError('Checkpoint committed locally but push rejected; retry push before continuing') from None
                self._run(['fetch','-q',self.remote,self.branch])
                if not rebase:break
                try:self._run(['rebase','-q',self.remote+'/'+self.branch])
                except Exception:
                    self._run(['rebase','--abort']) # never leave the checkout half-way through a rebase
                    raise RuntimeError('Rebase of a checkpoint failed and was abandoned; the checkout is unchanged') from None
        raise RuntimeError('push rejected')

    def _publish_state(self,paths,message):
        self._commit(paths,message)
        try:self._push(rebase=False)
        except RuntimeError:
            # Drop our commit and our edit of the ledger, then move to the remote tip; the caller redoes the mutation.
            self._run(['reset','-q','--soft','HEAD~1']);self._run(['reset','-q','HEAD','--']+paths)
            for relative in paths:
                try:self._run(['checkout','--',relative])
                except Exception:(self.root/relative).unlink(missing_ok=True) # the ledger did not exist before this commit
            try:self._run(['merge','-q','--ff-only',self.remote+'/'+self.branch])
            except Exception:raise RuntimeError('The branch has local commits the remote lacks; push or discard them before continuing') from None
            raise StateConflict('The branch moved; the ledger change was dropped and will be redone') from None

    def _write(self,state,message):
        save(self.root/self.state_path,state)
        self._publish_state([self.state_path],message)

    def mutate(self,callback):
        with self.lock.open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            for _ in range(5):
                state=self.read();old=copy.deepcopy(state)
                result=callback(state)
                validate(state,old);state['version']+=1
                if len(canonical_json(state))>15_000_000:raise ValueError('Registry size guard reached; archive events before scaling')
                try:self._write(state,'factory checkpoint v'+str(state['version'])+' [skip ci]');return result
                except StateConflict:continue
            raise RuntimeError('CAS retry limit reached')

    def raw(self):
        path=self.root/self.state_path
        return (load(path) if path.exists() else initial()),None

    def adopt(self,builder):
        with self.lock.open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            for _ in range(5):
                current,_=self.raw()
                new=builder(copy.deepcopy(current))
                if new is None:return None
                validate(new);new['version']=max(current.get('version',0),new.get('version',0))+1
                try:self._write(new,'factory checkpoint v'+str(new['version'])+' [skip ci]');return new
                except StateConflict:continue
            raise RuntimeError('CAS retry limit reached')

    def put_document(self,value):
        sha=digest(value);relative='data/documents/'+sha+'.json';path=self.root/relative
        with self.lock.open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            if path.exists():
                try:same=load(path)==value
                except ValueError:same=False
                if same:
                    if self._dirty(relative):self._commit([relative],'factory document '+sha[:12]+' [skip ci]');self._push(rebase=True) # an earlier run stopped before its commit
                    return sha
                if not self._untracked(relative):raise ValueError('Immutable document collision') # a committed document never changes
                # An untracked file at this address that is not this document is a cut-off write: replace it.
            path.parent.mkdir(parents=True,exist_ok=True)
            fd,temp=tempfile.mkstemp(prefix='.document-',dir=path.parent)
            try:
                with os.fdopen(fd,'wb') as f:
                    f.write(canonical_json(value));f.flush();os.fsync(f.fileno())
                os.replace(temp,path)
            finally:
                if os.path.exists(temp):os.unlink(temp)
            self._commit([relative],'factory document '+sha[:12]+' [skip ci]');self._push(rebase=True)
        return sha

    def get_document(self,sha):
        if not re.fullmatch('[a-f0-9]{64}',sha):raise ValueError('Invalid document address')
        value=json.loads((self.root/'data/documents'/(sha+'.json')).read_bytes())
        if digest(value)!=sha:raise ValueError('Document changed after checkpoint')
        return value


class GitHub:
    def __init__(self, token=None):
        # An authorized session may only hold the harness-provided GITHUB_TOKEN;
        # it is used for the same destination-only repository with the same path guard.
        self.token=token or os.environ.get('THUHA_GITHUB_TOKEN') or os.environ.get('GITHUB_TOKEN')
        if not self.token:raise ValueError('GitHub state credential is missing')

    def request(self, method, path, body=None):
        if not path.startswith('/repos/'+REPO+'/'):
            raise ValueError('GitHub access is confined to the destination repository')
        headers={'Authorization':'Bearer '+self.token,'Accept':'application/vnd.github+json',
                 'X-GitHub-Api-Version':'2022-11-28','User-Agent':'ThuHa-Writer/4'}
        if body is not None:headers['Content-Type']='application/json' # GitHub returns 415 for form-encoded JSON bodies
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
        state,_=self._state();migrate(state);validate(state);return state

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
            state,sha=self._state();migrate(state);old=copy.deepcopy(state)
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

    def raw(self):
        return self._state()

    def adopt(self,builder):
        """Replace the whole ledger with `builder(raw)` in one compare-and-swap; the builder is re-run on a conflict."""
        for attempt in range(5):
            current,sha=self._state()
            new=builder(copy.deepcopy(current))
            if new is None:return None
            validate(new);new['version']=max(current.get('version',0),new.get('version',0))+1
            if len(canonical_json(new))>15_000_000:
                raise ValueError('Registry size guard reached; archive events before scaling')
            try:
                self._put(self.state_path,new,sha)
                return new
            except GitError as e:
                if e.status not in (409,422) or attempt==4:raise
        raise ValueError('CAS retry limit reached')

    def put_document(self,value):
        sha=digest(value);path='data/documents/'+sha+'.json'
        # A concurrent state writer may move the branch between a missing-file
        # GET and an immutable-file PUT. 409/422 does not prove the document
        # exists: another writer might only have moved the branch. Re-read and
        # retry with bounded CAS; never replace or overwrite an existing file.
        for attempt in range(6):
            try:
                old,_=self._get(path)
                if old!=value:raise ValueError('Immutable remote document collision')
                return sha
            except GitError as exc:
                if exc.status!=404:raise
            try:
                self._put(path,value)
                return sha
            except GitError as exc:
                if exc.status not in (409,422):raise
                if attempt==5:raise
        raise RuntimeError('Immutable document CAS retry limit reached')

    def get_document(self,sha):
        if not re.fullmatch('[a-f0-9]{64}',sha):raise ValueError('Invalid document address')
        value,_=self._get('data/documents/'+sha+'.json')
        if digest(value)!=sha:raise ValueError('Immutable remote document altered')
        return value
