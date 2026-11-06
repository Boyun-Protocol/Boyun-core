"""Pinned testnet registry views verify code, finality, calls and immutable records."""
import base64
from copy import deepcopy
import json
import pytest

CONTRACT='registry.testnet';SIGNER='alice.testnet';HASH='2'*44;CODE='3'*44;BLOCK='4'*44
PUBLIC={'schema_version':'artifact-commitment.v1','commitment':'a'*64}
RECORD={'commitment':'a'*64,'signer_id':SIGNER,'block_height':'100','block_timestamp_ns':'100000000000'}


def encoded(value):return list(json.dumps(value).encode())


class Wire:
    def __init__(self,mutate=None):self.calls=[];self.mutate=mutate
    def __call__(self,**request):
        p=json.loads(request['body']);self.calls.append(p)
        if p['method']=='status':r={'chain_id':'testnet'}
        elif p['method']=='query':
            if p['params']['request_type']=='view_account':r={'code_hash':CODE,'block_hash':BLOCK,'block_height':200}
            elif p['params']['method_name']=='contract_version':r={'result':encoded('decision-lab-commitment-registry.v1'),'block_hash':BLOCK,'block_height':200}
            else:r={'result':encoded(RECORD),'block_hash':BLOCK,'block_height':200}
        else:
            call={'FunctionCall':{'method_name':'register_commitment','args':base64.b64encode(json.dumps({'commitment':'a'*64}).encode()).decode(),
                'gas':30000000000000,'deposit':'10000000000000000000000'}}
            result={'SuccessValue':base64.b64encode(json.dumps(RECORD).encode()).decode()}
            r={'final_execution_status':'FINAL','status':result,
                'transaction':{'hash':HASH,'signer_id':SIGNER,'receiver_id':CONTRACT,'actions':[call]},
                'transaction_outcome':{'id':HASH,'outcome':{'executor_id':SIGNER,'receipt_ids':['5'*44],'gas_burnt':1,'tokens_burnt':'1','status':{'SuccessReceiptId':'5'*44}}},
                'receipts_outcome':[{'id':'5'*44,'outcome':{'executor_id':CONTRACT,'receipt_ids':[],'gas_burnt':2,'tokens_burnt':'2','status':result}}]}
        if self.mutate:self.mutate(p,r)
        return json.dumps({'jsonrpc':'2.0','id':p['id'],'result':r}).encode()


def client(wire=None):
    from decision_lab.near_registry import NearRegistryClient
    return NearRegistryClient(contract_id=CONTRACT,expected_code_hash=CODE,transport=wire or Wire())


def test_prepared_wallet_call_discloses_only_salted_commitment_and_testnet_funding():
    wire=Wire();value=client(wire).prepare(PUBLIC,signer_id=SIGNER)
    assert value['network']=='testnet'and value['status']=='unsigned_verified_contract'
    p=value['wallet_request']['actions'][0]['params']
    assert p['args']=={'commitment':'a'*64}and p['deposit']=='10000000000000000000000'
    assert value['wallet_request']['receiverId']==CONTRACT
    assert all(c['method']in ('status','query')for c in wire.calls)
    assert 'salt'not in json.dumps(value)and 'artifact_sha256'not in json.dumps(value)


def test_final_transaction_and_matching_current_code_and_record_are_verified():
    wire=Wire();value=client(wire).verify_transaction(PUBLIC,transaction_hash=HASH,signer_id=SIGNER)
    assert value['verified']is True and value['status']=='final_verified'
    assert value['record']==RECORD and value['transaction_hash']==HASH
    assert value['tokens_burnt_yocto']=='3'
    tx=next(p for p in wire.calls if p['method']=='tx')
    assert tx['params']['wait_until']=='FINAL'
    assert all(p['params'].get('block_id')==BLOCK for p in wire.calls if p['method']=='query'and p['params']['request_type']=='call_function')


@pytest.mark.parametrize('mutation',[
 lambda p,r:r.update(chain_id='mainnet')if p['method']=='status'else None,
 lambda p,r:r.update(code_hash='6'*44)if p['method']=='query'and p['params']['request_type']=='view_account'else None,
 lambda p,r:r.update(final_execution_status='EXECUTED_OPTIMISTIC')if p['method']=='tx'else None,
 lambda p,r:r['transaction'].update(receiver_id='other.testnet')if p['method']=='tx'else None,
 lambda p,r:r['transaction'].update(signer_id='other.testnet')if p['method']=='tx'else None,
 lambda p,r:r['transaction']['actions'][0]['FunctionCall'].update(args=base64.b64encode(b'{"commitment":"wrong"}').decode())if p['method']=='tx'else None,
 lambda p,r:r.update(status={'Failure':{'PRIVATE':'error'}})if p['method']=='tx'else None,
 lambda p,r:r['receipts_outcome'][0]['outcome'].update(status={'Failure':{'PRIVATE':'error'}})if p['method']=='tx'else None,
 lambda p,r:r.update(receipts_outcome=[])if p['method']=='tx'else None,
])
def test_wrong_chain_code_intent_or_failed_nonfinal_receipts_are_not_success(mutation):
    from decision_lab.near_registry import NearRegistryError
    wire=Wire(mutation)
    with pytest.raises(NearRegistryError)as e:client(wire).verify_transaction(PUBLIC,transaction_hash=HASH,signer_id=SIGNER)
    assert 'PRIVATE'not in str(e.value)


def test_unregistered_record_and_inconsistent_receipt_are_rejected():
    from decision_lab.near_registry import NearRegistryError
    def mutate(p,r):
        if p['method']=='query'and p['params'].get('method_name')=='get_commitment':r['result']=encoded(None)
    assert client(Wire(mutate)).verify_record(PUBLIC)['status']=='not_registered'
    with pytest.raises(NearRegistryError):client(Wire(mutate)).verify_transaction(PUBLIC,transaction_hash=HASH,signer_id=SIGNER)


def test_mainnet_or_unpinned_rpc_never_dispatches():
    from decision_lab.near_registry import NearRegistryClient
    wire=Wire()
    for endpoint in ('https://rpc.mainnet.near.org','https://evil.test','http://rpc.testnet.near.org'):
        with pytest.raises(ValueError):NearRegistryClient(contract_id=CONTRACT,expected_code_hash=CODE,rpc_url=endpoint,transport=wire)
    with pytest.raises(ValueError):client(wire).prepare(PUBLIC,signer_id='alice.near')
    assert not wire.calls


def dedicated_relayer(tmp_path):
    from decision_lab.near_registry import NearRegistryClient, NearRegistryRelayer
    credential=tmp_path/'credential.private.json'
    credential.write_text(json.dumps({'network':'testnet','account_id':'csl-registry-123456789abc.testnet'}))
    credential.chmod(0o600)
    script=tmp_path/'submit.mjs';script.write_text('// fixture; never executed')
    route=NearRegistryClient(contract_id='csl-registry-123456789abc.testnet',expected_code_hash=CODE,transport=Wire())
    return NearRegistryRelayer(route,credential_file=credential,output_dir=tmp_path/'submissions',script_path=script,node_binary='node')


def test_shared_credential_lock_stops_second_process_before_any_chain_request(tmp_path):
    import fcntl
    from decision_lab.near_registry import NearRegistryError
    relay=dedicated_relayer(tmp_path)
    lock=relay.credential_file.with_name(relay.credential_file.name+'.relay.lock')
    lock.touch(mode=0o600)
    with lock.open('r+')as held:
        fcntl.flock(held.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        with pytest.raises(NearRegistryError,match='relayer_busy_no_submit'):
            relay.register(PUBLIC,allow_submit=True)
    assert not relay.client.transport.calls
    assert not list(relay.root.iterdir())


def test_recover_prebroadcast_transaction_identity_is_read_only_and_validated(tmp_path):
    relay=dedicated_relayer(tmp_path)
    assert relay.recorded_transaction(PUBLIC)is None
    folder=relay.root/PUBLIC['commitment']/'operation';folder.mkdir(parents=True)
    marker=folder/'submission.json'
    marker.write_text(json.dumps({'network':'testnet','signer_id':relay.signer_id,'transaction_hash':HASH}))
    assert relay.recorded_transaction(PUBLIC)=={'transaction_hash':HASH,'signer_id':relay.signer_id}
    assert not relay.client.transport.calls
    marker.write_text(json.dumps({'network':'mainnet','signer_id':relay.signer_id,'transaction_hash':HASH}))
    with pytest.raises(ValueError):relay.recorded_transaction(PUBLIC)
