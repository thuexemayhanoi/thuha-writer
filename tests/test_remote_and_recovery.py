import base64
import copy
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from thuha.common import REPO,canonical_json,digest,load,ROOT,now
from thuha.store import GitStore,GitError,LocalStore,initial,event,validate,GitHub
from thuha.coordinator import claim,submit,heartbeat
from thuha.publisher import verify_security
from thuha.cli import main, inventory_for
from thuha.dashboard import report


class MemoryGitHub:
    """REST double with genuine expected-blob-SHA conflict semantics."""
    def __init__(self):self.files={};self.writes=0;self.conflict=False;self.branch=False
    def request(self,method,path,body=None):
        if '/git/ref/heads/main' in path:return {'object':{'sha':'a'*40}}
        if '/git/ref/heads/factory-state' in path:
            if not self.branch:raise GitError(404)
            return {'object':{'sha':'a'*40}}
        if method=='POST' and path.endswith('/git/refs'):
            self.branch=True;return {'ok':True}
        relative=path.split('/contents/',1)[1].split('?',1)[0]
        old=self.files.get(relative)
        if method=='GET':
            if old is None:raise GitError(404)
            return {'sha':digest(old),'encoding':'base64','content':base64.b64encode(canonical_json(old)).decode()}
        if method=='PUT':
            if self.conflict and relative==GitStore.state_path:
                self.conflict=False
                other=copy.deepcopy(old);other['topics']['TH-EN-9999']={'status':'PLANNED','language':'en'};other['version']+=1
                self.files[relative]=other
            old=self.files.get(relative)
            if (old is not None and body.get('sha')!=digest(old)) or (old is None and body.get('sha')):raise GitError(409)
            self.files[relative]=json.loads(base64.b64decode(body['content']));self.writes+=1
            return {'content':{'sha':digest(self.files[relative])}}
        raise AssertionError('Unexpected operation')


class RemoteTests(unittest.TestCase):
    def setUp(self):self.api=MemoryGitHub();self.store=GitStore(self.api)
    def test_read_of_missing_state_does_not_create_anything(self):
        self.assertEqual(self.store.read()['version'],0);self.assertEqual(self.api.writes,0);self.assertFalse(self.api.branch)
    def test_remote_mutation_bootstraps_isolated_branch(self):
        self.store.mutate(lambda s:s['topics'].update({'TH-EN-0001':{'status':'PLANNED','language':'en'}}))
        self.assertTrue(self.api.branch);self.assertEqual(self.store.read()['topics']['TH-EN-0001']['status'],'PLANNED')
    def test_cas_conflict_retries_without_losing_other_session(self):
        self.store.mutate(lambda s:s['topics'].update({'TH-EN-0001':{'status':'PLANNED','language':'en'}}))
        self.api.conflict=True
        self.store.mutate(lambda s:s['topics'].update({'TH-EN-0002':{'status':'PLANNED','language':'en'}}))
        self.assertEqual(set(self.store.read()['topics']),{'TH-EN-0001','TH-EN-0002','TH-EN-9999'})
    def test_content_addressed_remote_checkpoint_roundtrip(self):
        sha=self.store.put_document({'body':'Actual independent document bytes'})
        self.assertEqual(self.store.get_document(sha)['body'],'Actual independent document bytes')
    def test_sustained_writer_conflicts_retry_and_preserve_authoritative_state(self):
        class BusyBranch(MemoryGitHub):
            def __init__(self):
                super().__init__()
                self.conflicts_left = 7

            def request(self, method, path, body=None):
                if method == 'PUT' and '/contents/data/state/factory.json' in path and self.conflicts_left:
                    self.conflicts_left -= 1
                    raise GitError(409)
                return super().request(method, path, body)

        api = BusyBranch()
        store = GitStore(api)
        store.mutate(lambda s: s.update(research_requests={'safe': {'status': 'PLANNED'}}))
        self.assertEqual(api.conflicts_left, 0)
        self.assertEqual(store.read()['research_requests']['safe']['status'], 'PLANNED')

    def test_immutable_document_create_retries_422_without_faking_collision(self):
        class BranchMovedAPI(MemoryGitHub):
            def __init__(self):
                super().__init__()
                self.reject_once = True

            def request(self, method, path, body=None):
                if method == 'PUT' and '/contents/data/documents/' in path and self.reject_once:
                    self.reject_once = False
                    raise GitError(422)  # branch moved, yet target document does not exist
                return super().request(method, path, body)

        api = BranchMovedAPI()
        store = GitStore(api)
        body = {'article': 'unique and immutable Vietnamese draft'}
        sha = store.put_document(body)
        self.assertEqual(store.get_document(sha), body)
        self.assertEqual(api.writes, 1)
        self.assertFalse(api.reject_once)

    def test_runtime_store_cannot_write_code(self):
        with self.assertRaises(ValueError):self.store._put('src/thuha/quality.py',{'fake':True})
    def test_remote_checkpoint_tampering_is_detected(self):
        sha=self.store.put_document({'a':1});self.api.files['data/documents/'+sha+'.json']={'a':2}
        with self.assertRaises(ValueError):self.store.get_document(sha)
    def test_github_client_rejects_other_repository(self):
        with self.assertRaises(ValueError):GitHub('dummy-fixture-token').request('GET','/repos/someone/other/contents/x')


class MigrationTests(unittest.TestCase):
    def legacy(self):
        value=initial();value['schema']=4
        value['topics']={'TH-000001':{'topic_id':'TH-000001','status':'PLANNED','proposed_url':'https://rentbikehanoi.com/ho-chi-minh-museum-hanoi-exhibition-guide/'}}
        value['research_requests']={'research-x':{'status':'FULFILLED','request_id':'research-x'}}
        value['receipts']={'TH-000001':{'wp_id':1,'url':'u'}}
        return value
    def test_schema_four_publication_phases_get_their_schema_five_names(self):
        from thuha.store import migrate
        old=self.legacy()
        old['topics']['TH-000001']['status']='VERIFIED'
        old['intents']={'TH-000001':{'phase':'VERIFIED','article_sha':'a'*64,'wp_id':1},
                        'TH-000002':{'phase':'VERIFY_PENDING','article_sha':'b'*64}}
        old['topics']['TH-000002']={'topic_id':'TH-000002','status':'BLOCKED','proposed_url':'https://rentbikehanoi.com/another-guide/'}
        value=migrate(copy.deepcopy(old));validate(value)
        self.assertEqual((value['intents']['TH-000001']['phase'],value['topics']['TH-000001']['status']),('PUBLISHED','PUBLISHED'))
        self.assertEqual(value['intents']['TH-000002']['phase'],'NEEDS_RECONCILIATION') # still unresolved, still counted
        self.assertEqual(value['receipts'],old['receipts'])
    def test_schema_four_state_becomes_english_schema_five_without_touching_receipts(self):
        from thuha.store import migrate
        old=self.legacy();value=migrate(copy.deepcopy(old));validate(value)
        self.assertEqual(value['schema'],5);self.assertEqual(value['topics']['TH-000001']['language'],'en')
        self.assertEqual(value['receipts'],old['receipts']);self.assertEqual(value['events'][-1]['action'],'SCHEMA_MIGRATION')
    def test_migration_is_idempotent(self):
        from thuha.store import migrate
        value=migrate(self.legacy());again=migrate(copy.deepcopy(value));self.assertEqual(value,again)
    def test_local_store_reads_and_rewrites_a_legacy_file_as_schema_five(self):
        from thuha.common import save
        with tempfile.TemporaryDirectory() as temp:
            save(Path(temp)/'state.json',self.legacy())
            store=LocalStore(temp);self.assertEqual(store.read()['schema'],5)
            store.mutate(lambda s:s['controls'].update(paused=True))
            self.assertEqual(json.loads((Path(temp)/'state.json').read_text())['schema'],5)
    def test_remote_state_is_migrated_on_first_mutation(self):
        api=MemoryGitHub();api.files[GitStore.state_path]=self.legacy();api.branch=True
        store=GitStore(api);store.mutate(lambda s:s['controls'].update(paused=True))
        self.assertEqual(api.files[GitStore.state_path]['schema'],5)
        self.assertEqual(api.files[GitStore.state_path]['topics']['TH-000001']['language'],'en')
    def test_language_url_and_id_must_agree(self):
        value=initial();value['topics']['TH-VI-0001']={'language':'en','status':'PLANNED'}
        with self.assertRaises(ValueError):validate(value)
        value['topics']['TH-VI-0001']={'language':'vi','status':'PLANNED','proposed_url':'https://rentbikehanoi.com/khong-co-vi/'}
        with self.assertRaises(ValueError):validate(value)
    def test_two_topics_cannot_share_one_wordpress_slug_across_languages(self):
        value=initial()
        value['topics']['TH-EN-0001']={'language':'en','status':'PLANNED','proposed_url':'https://rentbikehanoi.com/dat-coc/'}
        value['topics']['TH-VI-0001']={'language':'vi','status':'PLANNED','proposed_url':'https://rentbikehanoi.com/vi/dat-coc/'}
        with self.assertRaises(ValueError):validate(value)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.store=LocalStore(self.temp.name)
        self.store.mutate(lambda s:s['topics'].update({'TH-EN-0001':{'topic_id':'TH-EN-0001','language':'en','status':'PLANNED'}}))
        self.lease=claim(self.store,'session-fixture','agent-fixture')
        self.article={'topic_id':'TH-EN-0001','agent_id':'agent-fixture','session':'session-fixture','language':'en-US','body_html':'<p>first draft</p>','featured_media':50}
    def send(self):return submit(self.store,self.lease['slot'],self.lease['session'],self.lease['fence'],self.article,max_repairs=2)
    def test_identical_submission_does_not_consume_repair(self):
        a=self.send();b=self.send();self.assertEqual(a['repair_count'],b['repair_count'])
    def test_repair_limit_keeps_latest_held_draft(self):
        self.send()
        for i in range(3):self.article['body_html']='<p>revision '+str(i)+'</p>';result=self.send()
        self.assertEqual(result['status'],'NEEDS_REVIEW')
        state=self.store.read();sha=state['topics']['TH-EN-0001']['held_article_sha']
        self.assertEqual(self.store.get_document(sha),self.article)
        self.assertEqual(state['leases'],{})
        with self.assertRaises(ValueError):self.send()
    def test_same_session_cannot_change_declared_agent(self):
        with self.assertRaises(ValueError):claim(self.store,'session-fixture','other-agent')
    def test_corrupt_event_chain_is_never_reset_silently(self):
        value=self.store.read();value['events'][0]['action']='FAKE'
        with self.assertRaises(ValueError):validate(value)
    def test_local_document_write_is_atomic_and_idempotent(self):
        a=self.store.put_document({'body':'one'});b=self.store.put_document({'body':'one'})
        self.assertEqual(a,b)
        self.assertFalse(list((Path(self.temp.name)/'documents').glob('.document-*')))
    def test_partial_receipt_mutation_rolls_back_entire_transaction(self):
        self.store.mutate(lambda s:s['receipts'].update({'a':{'id':1}}))
        def bad(s):s['receipts']['a']={'id':2};s['topics']['new']={'status':'FAKE'}
        with self.assertRaises(ValueError):self.store.mutate(bad)
        self.assertNotIn('new',self.store.read()['topics'])


class SecurityTests(unittest.TestCase):
    def test_actions_read_failure_stays_unknown(self):
        with tempfile.TemporaryDirectory() as temp:
            store=LocalStore(temp);store.durable_remote=True
            class API:
                def request(self,*args):raise GitError(403)
            store.api=API()
            inv={'captured_at':now(),'language_source':'adapter','counts':{'posts':0,'pages':0,'live_verified_posts':0,'posts_by_language':{'vi':0,'en':0}},'complete':True}
            value=report(store,inv,load(ROOT/'config/release.json'))
            self.assertEqual(value['github_actions']['status'],'UNKNOWN');self.assertEqual(value['github_actions']['runs'],[])
    def test_qa_batch_continues_after_one_contract_failure(self):
        output=io.StringIO()
        with tempfile.TemporaryDirectory() as temp:
            store=LocalStore(temp)
            store.mutate(lambda s:s['topics'].update({'TH-EN-0001':{'status':'DRAFT_READY','language':'en'},'TH-EN-0002':{'status':'DRAFT_READY','language':'en'}}))
            inv=Path(temp)/'inventory.json';inv.write_text('{}')
            with patch('thuha.quality.run_qa',side_effect=[ValueError('isolated broken topic'),{'status':'PASS'}]) as mock,patch('sys.stdout',output):
                code=main(['--state-dir',temp,'--inventory',str(inv),'qa'])
            self.assertEqual(mock.call_count,2);self.assertEqual(code,1)
            self.assertEqual(json.loads(output.getvalue())['results']['TH-EN-0002']['status'],'PASS')
    def test_github_dispatch_http_204_is_success(self):
        class EmptyResponse:
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def read(self):return b''
        with patch('thuha.store.urllib.request.urlopen',return_value=EmptyResponse()):
            result=GitHub('fixture-token').request('POST','/repos/'+REPO+'/dispatches',
                {'event_type':'thuha-qa-ready','client_payload':{'topic_ids':['TH-000001']}})
        self.assertEqual(result,{})
    def test_security_accepts_valid_refs_without_manual_reviewer(self):
        class API:
            def request(self,method,path):
                if path.endswith('/git/ref/heads/main'):
                    return {'ref':'refs/heads/main','object':{'sha':'a'*40}}
                if path.endswith('/git/ref/heads/factory-state'):
                    return {'ref':'refs/heads/factory-state','object':{'sha':'b'*40}}
                raise AssertionError(path)
        with patch.dict(os.environ,{'GITHUB_REF':'refs/heads/main'}):
            self.assertTrue(verify_security(API())['automated_qa_required'])
    def test_security_rejects_non_main_execution(self):
        class API:
            def request(self,*args):raise AssertionError('should fail before API')
        with patch.dict(os.environ,{'GITHUB_REF':'refs/heads/untrusted'}):
            with self.assertRaisesRegex(ValueError,'trusted main'):
                verify_security(API())
    def test_missing_external_controls_blocks_go_live(self):
        class API:
            def request(self,*args):return {}
        with self.assertRaises(ValueError):verify_security(API())
    def test_expired_remote_inventory_refreshes_from_wordpress_get(self):
        from thuha.common import SITE
        with tempfile.TemporaryDirectory() as temp:
            store=LocalStore(temp)
            store.durable_remote=True
            stale={'site':SITE,'captured_at':'2020-01-01T00:00:00+00:00','complete':True,'errors':[]}
            fresh={'site':SITE,'captured_at':now(),'complete':True,'errors':[],
                   'items':[],'categories':[],'counts':{'posts':0,'pages':0,'live_verified_posts':0}}
            path=Path(temp)/'inventory.json'
            path.write_text(json.dumps(stale))
            with patch('thuha.cli.audit.inventory',return_value=fresh) as fetch:
                out=inventory_for(store,path,21600)
            self.assertEqual(out,fresh)
            self.assertEqual(fetch.call_count,1)
            self.assertEqual(store.get_document(store.read()['inventory_document']),fresh)
    def test_fresh_inventory_does_not_make_external_requests(self):
        from thuha.common import SITE
        with tempfile.TemporaryDirectory() as temp:
            store=LocalStore(temp)
            store.durable_remote=True
            fresh={'site':SITE,'captured_at':now(),'complete':True,'errors':[]}
            path=Path(temp)/'inventory.json'
            path.write_text(json.dumps(fresh))
            with patch('thuha.cli.audit.inventory') as fetch:
                self.assertEqual(inventory_for(store,path,21600),fresh)
            fetch.assert_not_called()
    def test_credential_presence_command_never_prints_secret_values(self):
        output=io.StringIO()
        with tempfile.TemporaryDirectory() as temp,patch.dict(os.environ,THUHA_WP_USER='private-fixture-user',THUHA_WP_APPLICATION_PASSWORD='private-fixture-password'),patch('sys.stdout',output):
            self.assertEqual(main(['--state-dir',temp,'credentials']),0)
        self.assertNotIn('private-fixture',output.getvalue());self.assertIn('wordpress_password_configured',output.getvalue())
    def test_workflows_pin_actions_and_never_use_pull_request_target(self):
        import re
        for file in (ROOT/'.github/workflows').glob('*.yml'):
            source=file.read_text();self.assertNotIn('pull_request_target:',source)
            for action in re.findall(r'uses: (\S+)',source):self.assertRegex(action,r'@[a-f0-9]{40}$')
            self.assertIn('persist-credentials: false',source)
    def test_production_configuration_requires_explicit_owner_approval(self):
        value=load(ROOT/'config/release.json')
        if value['enabled']:
            self.assertTrue(value['approved'])
            self.assertFalse(value['paused'])
            self.assertTrue(value['approval_ref'])
            self.assertTrue(value['cross_publisher_coordination_verified'])
        else:
            self.assertFalse(value['approved'])


if __name__=='__main__':unittest.main()
