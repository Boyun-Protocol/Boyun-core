import json
import pytest
from decision_lab.product_near import ProductNear
from decision_lab.integrity import verify_commitment


def test_exact_results_salted_prepare_explicit_submit_idempotent_and_private(tmp_path):
    calls=[]
    class Client:
        contract_id='demo.testnet'
        def verify_record(self,public):return {'status':'registered','verified':True,'public':public}
    class Relayer:
        signer_id='demo.testnet';client=Client()
        def register(self,public,allow_submit=False):calls.append(public);assert allow_submit;return self.client.verify_record(public)
    api=ProductNear(tmp_path,Relayer());data=b'{"secret":"scenario"}\n'
    first=api.prepare(data);assert not calls
    assert 'secret'not in json.dumps(first)and 'salt'not in json.dumps(first)
    assert verify_commitment(data,first['public'],api.opening(data))
    assert api.prepare(data)['public']==first['public']
    with pytest.raises(ValueError):api.submit(data,{'allow_submit':True,'commitment':'0'*64})
    request={'allow_submit':True,'commitment':first['public']['commitment']}
    assert api.submit(data,request)['verified']and api.submit(data,request)['verified']and len(calls)==1
    assert api.verify(data)['verified']
    assert api.prepare(data+b' ')['public']!=first['public']
    assert all(p.stat().st_mode&0o777==0o600 for p in tmp_path.glob('*/*.json'))


def test_uncertain_submission_is_never_automatically_repeated(tmp_path):
    calls=[]
    class Relayer:
        def register(self,*args,**kwargs):calls.append(args);raise ValueError('remote outcome unknown')
    api=ProductNear(tmp_path,Relayer());value=api.prepare(b'result')
    request={'allow_submit':True,'commitment':value['public']['commitment']}
    with pytest.raises(ValueError):api.submit(b'result',request)
    with pytest.raises(FileExistsError):api.submit(b'result',request)
    assert len(calls)==1


def test_http_explicit_anchor_origin_and_private_opening(tmp_path):
    import threading
    from decision_lab.web_server import create_server
    from test_web_server import request
    from test_product_history import complete
    from test_product_api import FakeModel
    server=create_server(port=0,output_dir=tmp_path,product_actor_clients={'gemini':FakeModel()})
    thread=threading.Thread(target=server.serve_forever);thread.start()
    try:
        saved=complete(server.product);boot=json.loads(request(server,'GET','/api/product')[2])
        path=f"/api/product/sessions/{saved['id']}/near/prepare"
        valid={'Content-Type':'application/json','X-CSRF-Token':boot['csrf_token']}
        assert request(server,'POST',path,'{}',{'Content-Type':'application/json'})[0]==403
        status,_,raw=request(server,'POST',path,'{}',valid);value=json.loads(raw)
        assert status==200 and value['status']=='prepared_private'and 'salt'not in raw.decode()
        opening=json.loads(request(server,'GET',path.replace('prepare','opening'))[2])
        assert verify_commitment(server.product.download_bytes(saved['id']),value['public'],opening)
        assert request(server,'GET',path.replace('prepare','opening'),headers={'Origin':'https://evil.test'})[0]==403
        assert request(server,'POST',path.replace('prepare','submit'),'{}',valid)[0]==400
    finally:server.shutdown();server.server_close();thread.join(3)


def test_explicit_verify_recovers_uncertain_transaction_without_resubmission(tmp_path):
    calls=[]
    class Client:
        contract_id='demo.testnet'
        def verify_transaction(self,public,**kwargs):
            calls.append(('verify',kwargs))
            return {'verified':True,'status':'final_verified','transaction_hash':kwargs['transaction_hash'],'public':public}
    class Relayer:
        signer_id='demo.testnet';client=Client()
        def register(self,*args,**kwargs):calls.append(('submit',kwargs));raise ValueError('uncertain response')
        def recorded_transaction(self,public):return {'transaction_hash':'2'*44,'signer_id':self.signer_id}
    api=ProductNear(tmp_path,Relayer());prepared=api.prepare(b'exact completed result')
    with pytest.raises(ValueError):api.submit(b'exact completed result',{'allow_submit':True,'commitment':prepared['public']['commitment']})
    assert api.prepare(b'exact completed result')['status']=='submission_attempted_unverified'
    recovered=api.verify(b'exact completed result')
    assert recovered['verified']and recovered['status']=='final_verified'
    assert [c[0]for c in calls]==['submit','verify']


def test_verify_before_first_submit_does_not_permanently_disable_recording(tmp_path):
    calls=[]
    class Client:
        def verify_record(self,public):return {'status':'not_registered','verified':False,'public':public}
    class Relayer:
        client=Client()
        def register(self,public,allow_submit=False):
            assert allow_submit;calls.append(public)
            return {'status':'registered','verified':True,'public':public}
    api=ProductNear(tmp_path,Relayer());prepared=api.prepare(b'recorded result')
    assert api.verify(b'recorded result')['status']=='not_registered'
    assert api.prepare(b'recorded result')['can_submit']
    request={'allow_submit':True,'commitment':prepared['public']['commitment']}
    assert api.submit(b'recorded result',request)['verified']
    assert not api.prepare(b'recorded result')['can_submit']
    assert api.submit(b'recorded result',request)['verified']and len(calls)==1


def test_wallet_plan_separates_public_signer_requires_explicit_attempt_and_checks_exact_bytes(tmp_path):
    from decision_lab.near_registry import NearRegistryClient
    from test_near_registry import Wire,CODE,CONTRACT,SIGNER,HASH
    class Relayer:
        signer_id='operator.testnet'
        client=NearRegistryClient(contract_id=CONTRACT,expected_code_hash=CODE,transport=Wire())
    api=ProductNear(tmp_path,Relayer());result=b'private exact result bytes'
    plan=api.wallet_prepare(result,{'signer_id':SIGNER});descriptor=plan['descriptor']
    assert descriptor['signer_id']==SIGNER and descriptor['network']=='testnet'
    assert descriptor['wallet_request']['actions'][0]['params']['args']=={'commitment':plan['public']['commitment']}
    assert verify_commitment(result,plan['public'],api.wallet_opening(result,plan['plan_id']))
    with pytest.raises(ValueError):api.wallet_verify(result,{'plan_id':plan['plan_id'],'transaction_hash':HASH})
    assert api.wallet_attempt(result,{'plan_id':plan['plan_id'],'allow_wallet_submit':True})['status']=='wallet_confirmation_reserved'
    with pytest.raises(ValueError):api.wallet_attempt(result,{'plan_id':plan['plan_id'],'allow_wallet_submit':True})
    with pytest.raises(FileNotFoundError):api.wallet_opening(result+b' ',plan['plan_id'])
    with pytest.raises(ValueError):api.wallet_prepare(result,{'signer_id':'user.near'})
    # The fixture's transaction committed a different digest; never accept its success.
    with pytest.raises(ValueError):api.wallet_verify(result,{'plan_id':plan['plan_id'],'transaction_hash':HASH})
    assert 'private exact result'not in json.dumps(plan)


def test_wallet_verified_receipt_persists_and_cannot_switch_transaction_hash(tmp_path):
    class Client:
        contract_id='registry.testnet'
        def prepare(self,public,signer_id):return {'network':'testnet','signer_id':signer_id,'contract':{'account_id':self.contract_id}}
        def verify_transaction(self,public,transaction_hash,signer_id):return {'verified':True,'status':'final_verified','transaction_hash':transaction_hash,'signer_id':signer_id,'public':public}
    class Relayer:client=Client();signer_id='operator.testnet'
    api=ProductNear(tmp_path,Relayer());result=b'exact bytes'
    p=api.wallet_prepare(result,{'signer_id':'reviewer.testnet'})
    assert 'opening'not in api.wallet_resume(result,{'plan_id':p['plan_id']})
    api.wallet_attempt(result,{'plan_id':p['plan_id'],'allow_wallet_submit':True})
    receipt=api.wallet_verify(result,{'plan_id':p['plan_id'],'transaction_hash':'2'*44})
    assert receipt['verified']
    resumed=api.wallet_resume(result,{'plan_id':p['plan_id']});assert resumed['attempted']and resumed['receipt']['verified']
    with pytest.raises(ValueError):api.wallet_verify(result,{'plan_id':p['plan_id'],'transaction_hash':'3'*44})


def test_wallet_http_routes_keep_csrf_origin_and_exact_plan_boundaries(tmp_path):
    import threading
    from decision_lab.web_server import create_server
    from test_web_server import request
    from test_product_history import complete
    from test_product_api import FakeModel
    class Client:
        contract_id='registry.testnet'
        def prepare(self,public,signer_id):return {'network':'testnet','signer_id':signer_id,'contract':{'account_id':self.contract_id}}
        def verify_transaction(self,public,transaction_hash,signer_id):return {'verified':True,'status':'final_verified','transaction_hash':transaction_hash,'signer_id':signer_id,'public':public}
    class Relayer:client=Client();signer_id='operator.testnet'
    server=create_server(port=0,output_dir=tmp_path,product_actor_clients={'gemini':FakeModel()},product_near_relayer=Relayer())
    thread=threading.Thread(target=server.serve_forever);thread.start()
    try:
        saved=complete(server.product);boot=json.loads(request(server,'GET','/api/product')[2]);base=f"/api/product/sessions/{saved['id']}/near/"
        assert boot['near']['wallet_enabled']
        body=json.dumps({'signer_id':'reviewer.testnet'})
        assert request(server,'POST',base+'wallet-prepare',body,{'Content-Type':'application/json'})[0]==403
        headers={'Content-Type':'application/json','X-CSRF-Token':boot['csrf_token']}
        assert request(server,'POST',base+'wallet-prepare',body,{**headers,'Origin':'https://evil.test'})[0]==403
        status,_,raw=request(server,'POST',base+'wallet-prepare',body,headers);assert status==200
        plan=json.loads(raw);token=plan['plan_id'];assert 'opening'not in plan
        assert request(server,'GET',base+'wallet-opening')[0]==404
        assert request(server,'POST',base+'wallet-attempt',json.dumps({'plan_id':token,'allow_wallet_submit':True}),headers)[0]==200
        status,_,raw=request(server,'POST',base+'wallet-verify',json.dumps({'plan_id':token,'transaction_hash':'2'*44}),headers)
        assert status==200 and json.loads(raw)['verified']
        status,_,raw=request(server,'POST',base+'wallet-opening',json.dumps({'plan_id':token}),headers)
        assert status==200 and verify_commitment(server.product.download_bytes(saved['id']),plan['public'],json.loads(raw))
    finally:server.shutdown();server.server_close();thread.join(3)
