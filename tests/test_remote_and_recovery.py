import base64
import copy
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from thuha.common import REPO,canonical_json,digest,load,ROOT
from thuha.store import GitStore,GitError,LocalStore,initial,event,validate,GitHub
from thuha.coordinator import claim,submit,heartbeat
from thuha.publisher import verify_security
from thuha.cli import main


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
                other=copy.deepcopy(old);other['topics']['TH-OTHER']={'status':'PLANNED'};other['version']+=1
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
        self.store.mutate(lambda s:s['topics'].update({'TH-000001':{'status':'PLANNED'}}))
        self.assertTrue(self.api.branch);self.assertEqual(self.store.read()['topics']['TH-000001']['status'],'PLANNED')
    def test_cas_conflict_retries_without_losing_other_session(self):
        self.store.mutate(lambda s:s['topics'].update({'TH-000001':{'status':'PLANNED'}}))
        self.api.conflict=True
        self.store.mutate(lambda s:s['topics'].update({'TH-000002':{'status':'PLANNED'}}))
        self.assertEqual(set(self.store.read()['topics']),{'TH-000001','TH-000002','TH-OTHER'})
    def test_content_addressed_remote_checkpoint_roundtrip(self):
        sha=self.store.put_document({'body':'Actual independent document bytes'})
        self.assertEqual(self.store.get_document(sha)['body'],'Actual independent document bytes')
    def test_runtime_store_cannot_write_code(self):
        with self.assertRaises(ValueError):self.store._put('src/thuha/quality.py',{'fake':True})
    def test_remote_checkpoint_tampering_is_detected(self):
        sha=self.store.put_document({'a':1});self.api.files['data/documents/'+sha+'.json']={'a':2}
        with self.assertRaises(ValueError):self.store.get_document(sha)
    def test_github_client_rejects_other_repository(self):
        with self.assertRaises(ValueError):GitHub('dummy-fixture-token').request('GET','/repos/someone/other/contents/x')


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.store=LocalStore(self.temp.name)
        self.store.mutate(lambda s:s['topics'].update({'TH-000001':{'topic_id':'TH-000001','status':'PLANNED'}}))
        self.lease=claim(self.store,'session-fixture','agent-fixture')
        self.article={'topic_id':'TH-000001','agent_id':'agent-fixture','session':'session-fixture','body_html':'<p>first draft</p>'}
    def send(self):return submit(self.store,self.lease['slot'],self.lease['session'],self.lease['fence'],self.article,max_repairs=2)
    def test_identical_submission_does_not_consume_repair(self):
        a=self.send();b=self.send();self.assertEqual(a['repair_count'],b['repair_count'])
    def test_repair_limit_keeps_latest_held_draft(self):
        self.send()
        for i in range(3):self.article['body_html']='<p>revision '+str(i)+'</p>';result=self.send()
        self.assertEqual(result['status'],'NEEDS_REVIEW')
        state=self.store.read();sha=state['topics']['TH-000001']['held_article_sha']
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
    def test_qa_batch_continues_after_one_contract_failure(self):
        output=io.StringIO()
        with tempfile.TemporaryDirectory() as temp:
            store=LocalStore(temp)
            store.mutate(lambda s:s['topics'].update({'TH-000001':{'status':'DRAFT_READY'},'TH-000002':{'status':'DRAFT_READY'}}))
            inv=Path(temp)/'inventory.json';inv.write_text('{}')
            with patch('thuha.quality.run_qa',side_effect=[ValueError('isolated broken topic'),{'status':'PASS'}]) as mock,patch('sys.stdout',output):
                code=main(['--state-dir',temp,'--inventory',str(inv),'qa'])
            self.assertEqual(mock.call_count,2);self.assertEqual(code,1)
            self.assertEqual(json.loads(output.getvalue())['results']['TH-000002']['status'],'PASS')
    def test_missing_external_controls_blocks_go_live(self):
        class API:
            def request(self,*args):return {}
        with self.assertRaises(ValueError):verify_security(API())
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
    def test_production_config_is_off(self):
        value=load(ROOT/'config/release.json');self.assertFalse(value['enabled']);self.assertFalse(value['approved']);self.assertTrue(value['paused'])


if __name__=='__main__':unittest.main()
