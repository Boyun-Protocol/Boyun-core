"""Pinned NEAR testnet commitment registry: prepare, relay and verify final receipts.

Only public commitments enter chain calls. No mainnet route, wallet key in a
browser, redirect, model request or automatic submission retry is supported.
Read verification trusts the selected testnet RPC, not a standalone light proof.
"""
import base64
import fcntl
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
from threading import RLock
from urllib.request import Request,build_opener,ProxyHandler
from .integrity import _valid_public,_testnet_account
from .agent_worlds import canonical
from .providers import _NoRedirect,_parse_json
from .io_helpers import _unique_object,_finite_float

RPC='https://rpc.testnet.near.org'
VERSION='decision-lab-commitment-registry.v1'
DEPOSIT='10000000000000000000000'
GAS='30000000000000'
_ALPHABET='123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'


class NearRegistryError(ValueError):
    def __init__(self,code):
        self.code=code
        super().__init__('NEAR testnet operation stopped ('+code+'); no automatic retry.')


def _hash(value):
    if type(value)is not str or not 32<=len(value)<=44 or any(c not in _ALPHABET for c in value):raise ValueError('bounded base58 hash required')
    return value


def code_hash(wasm):
    if type(wasm)is not bytes or len(wasm)>1048576 or not wasm.startswith(b'\0asm'):raise ValueError('bounded Wasm required')
    raw=sha256(wasm).digest();number=int.from_bytes(raw,'big');out=''
    while number:number,digit=divmod(number,58);out=_ALPHABET[digit]+out
    return '1'*(len(raw)-len(raw.lstrip(b'\0')))+out


def _decimal(value,maximum=2**128-1):
    if type(value)is not str or not re.fullmatch(r'0|[1-9][0-9]{0,39}',value)or int(value)>maximum:raise ValueError('bounded unsigned decimal string required')
    return int(value)


def _account(value):
    if not _testnet_account(value):raise ValueError('explicit testnet account required')
    return value


def _transport(*,endpoint,body,timeout_seconds,max_response_bytes):
    if endpoint!=RPC:raise ValueError('pinned testnet RPC required')
    req=Request(endpoint,data=body,headers={'Content-Type':'application/json','Accept':'application/json'},method='POST')
    with build_opener(ProxyHandler({}),_NoRedirect()).open(req,timeout=timeout_seconds)as response:
        raw=response.read(max_response_bytes+1)
        if response.status!=200 or len(raw)>max_response_bytes:raise ValueError('bounded successful RPC response required')
        return raw


def _record(value,commitment,maximum_height):
    if type(value)is not dict or set(value)!={'commitment','signer_id','block_height','block_timestamp_ns'}:raise ValueError('exact registry record required')
    if value['commitment']!=commitment:raise ValueError('different commitment returned')
    _account(value['signer_id']);_decimal(value['block_height'],maximum_height);_decimal(value['block_timestamp_ns'],2**64-1)
    return deepcopy(value)


def _decoded(value):
    if type(value)is not str or len(value)>65536:raise ValueError('bounded base64 payload required')
    return _parse_json(base64.b64decode(value,validate=True))


def _view_json(raw):
    if type(raw)is not bytes or len(raw)>65536:raise ValueError('bounded contract JSON required')
    return json.loads(raw,object_pairs_hook=_unique_object,parse_float=_finite_float,
        parse_constant=lambda _:(_ for _ in ()).throw(ValueError('nonfinite contract JSON')))


class NearRegistryClient:
    def __init__(self,*,contract_id,expected_code_hash,rpc_url=RPC,timeout_seconds=20,transport=None):
        self.contract_id=_account(contract_id);self.expected_code_hash=_hash(expected_code_hash)
        if rpc_url!=RPC or type(timeout_seconds)is not int or not 1<=timeout_seconds<=60:raise ValueError('pinned bounded testnet RPC required')
        self.rpc_url=rpc_url;self.timeout_seconds=timeout_seconds;self.transport=transport or _transport

    def _rpc(self,method,params):
        try:
            payload={'jsonrpc':'2.0','id':'decision-lab-near-registry','method':method,'params':params}
            raw=self.transport(endpoint=self.rpc_url,body=canonical(payload),timeout_seconds=self.timeout_seconds,max_response_bytes=1048576)
            if type(raw)is not bytes or len(raw)>1048576:raise ValueError('bounded response required')
            value=_parse_json(raw)
            if (type(value)is not dict or value.get('jsonrpc')!='2.0'or value.get('id')!=payload['id']
                or 'error'in value or 'result'not in value):raise ValueError('RPC result required')
            return value['result']
        except NearRegistryError:raise
        except Exception:raise NearRegistryError('rpc_or_response_failed')from None

    def _view(self,method,args,block):
        value=self._rpc('query',{'request_type':'call_function','block_id':block['block_hash'],
            'account_id':self.contract_id,'method_name':method,'args_base64':base64.b64encode(canonical(args)).decode()})
        try:
            if value['block_hash']!=block['block_hash']or value['block_height']!=block['block_height']:raise ValueError('view block differs')
            data=value['result']
            if type(data)is not list or len(data)>65536 or any(type(v)is not int or not 0<=v<=255 for v in data):raise ValueError('bounded view bytes required')
            return _view_json(bytes(data))
        except Exception:raise NearRegistryError('invalid_contract_view')from None

    def inspect_contract(self):
        status=self._rpc('status',[])
        if type(status)is not dict or status.get('chain_id')!='testnet':raise NearRegistryError('wrong_network')
        block=self._rpc('query',{'request_type':'view_account','finality':'final','account_id':self.contract_id})
        try:
            if block['code_hash']!=self.expected_code_hash:raise ValueError('code changed')
            _hash(block['block_hash'])
            if type(block['block_height'])is not int or not 0<=block['block_height']<=2**64-1:raise ValueError('invalid block height')
        except Exception:raise NearRegistryError('contract_code_or_final_block_mismatch')from None
        if self._view('contract_version',{},block)!=VERSION:raise NearRegistryError('contract_version_mismatch')
        return {'account_id':self.contract_id,'code_hash':self.expected_code_hash,'version':VERSION,
            'block_hash':block['block_hash'],'block_height':block['block_height'],'network':'testnet'}

    def prepare(self,public,*,signer_id):
        if not _valid_public(public):raise ValueError('exact public commitment required')
        _account(signer_id);contract=self.inspect_contract()
        return {'schema_version':'near-registry-wallet-request.v1','network':'testnet','status':'unsigned_verified_contract',
            'signer_id':signer_id,'contract':contract,'wallet_request':{'receiverId':self.contract_id,'actions':[
                {'type':'FunctionCall','params':{'methodName':'register_commitment','args':{'commitment':public['commitment']},'gas':GAS,'deposit':DEPOSIT}}]},
            'limitations':['The signer and registry are public. This does not establish creator identity, predictive accuracy or anonymity.',
                'Attached testNEAR funds record storage; excess is refunded by the contract. Gas is separate. Contract owner can upgrade unless its keys are removed.']}

    def verify_record(self,public):
        if not _valid_public(public):raise ValueError('exact public commitment required')
        contract=self.inspect_contract()
        value=self._view('get_commitment',{'commitment':public['commitment']},contract)
        try:record=None if value is None else _record(value,public['commitment'],contract['block_height'])
        except Exception:raise NearRegistryError('invalid_registry_record')from None
        return {'schema_version':'near-registry-verification.v1','network':'testnet','status':'registered'if record else'not_registered',
            'verified':record is not None,'public':deepcopy(public),'record':record,'contract':contract,
            'verification_scope':'Final RPC state and pinned current contract code/version; not a standalone cryptographic light-client proof.'}

    def verify_transaction(self,public,*,transaction_hash,signer_id):
        if not _valid_public(public):raise ValueError('exact public commitment required')
        _hash(transaction_hash);_account(signer_id)
        tx=self._rpc('tx',{'tx_hash':transaction_hash,'sender_account_id':signer_id,'wait_until':'FINAL'})
        try:
            transaction=tx['transaction']
            if (tx['final_execution_status']!='FINAL'or transaction['hash']!=transaction_hash
                or transaction['signer_id']!=signer_id or transaction['receiver_id']!=self.contract_id):raise ValueError('transaction intent differs')
            actions=transaction['actions']
            if type(actions)is not list or len(actions)!=1 or set(actions[0])!={'FunctionCall'}:raise ValueError('one function call required')
            call=actions[0]['FunctionCall']
            if call['method_name']!='register_commitment'or _decoded(call['args'])!={'commitment':public['commitment']}:raise ValueError('different call arguments')
            if _decimal(call['deposit'])>int(DEPOSIT)or str(call['gas'])!=GAS:raise ValueError('unexpected deposit or gas ceiling')
            if type(tx['status'])is not dict or set(tx['status'])!={'SuccessValue'}:raise ValueError('successful final execution required')
            returned=_decoded(tx['status']['SuccessValue'])
            receipts=tx['receipts_outcome']
            if type(receipts)is not list or not 1<=len(receipts)<=32:raise ValueError('bounded receipt outcomes required')
            outcomes=[tx['transaction_outcome']]+receipts
            if tx['transaction_outcome']['id']!=transaction_hash:raise ValueError('transaction outcome identity differs')
            ids={o['id']for o in outcomes};required=set();burnt=0;matched=False
            if len(ids)!=len(outcomes):raise ValueError('duplicate receipt outcomes')
            for item in outcomes:
                _hash(item['id']);outcome=item['outcome'];status=outcome['status']
                if type(status)is not dict or len(status)!=1 or not set(status)<={'SuccessValue','SuccessReceiptId'}:raise ValueError('failed/unknown receipt')
                if type(outcome['receipt_ids'])is not list or len(outcome['receipt_ids'])>32:raise ValueError('bounded child receipts required')
                required.update(outcome['receipt_ids']);burnt+=_decimal(outcome['tokens_burnt'])
                if outcome['executor_id']==self.contract_id and 'SuccessValue'in status:
                    try:matched=matched or _decoded(status['SuccessValue'])==returned
                    except Exception:pass
            if not required<=ids or not matched:raise ValueError('missing contract execution or receipt outcome')
        except Exception:raise NearRegistryError('transaction_not_final_or_intent_receipts_mismatch')from None
        verified=self.verify_record(public)
        try:
            if not verified['record']or verified['record']!=returned or returned['signer_id']!=signer_id:raise ValueError('stored registration differs')
        except Exception:raise NearRegistryError('transaction_registry_record_mismatch')from None
        return {**verified,'schema_version':'near-registry-transaction-verification.v1','status':'final_verified','verified':True,
            'transaction_hash':transaction_hash,'signer_id':signer_id,'tokens_burnt_yocto':str(burnt),
            'explorer_url':'https://testnet.nearblocks.io/txns/'+transaction_hash}


class NearRegistryRelayer:
    """Dedicated local testnet key; one reserved submission per commitment."""
    def __init__(self,client,*,credential_file,output_dir,node_binary=None,script_path=None,runner=None):
        self._submit_lock=RLock()
        self.client=client;self.credential_file=Path(credential_file).resolve();self.root=Path(output_dir)
        fd=os.open(credential_file,os.O_RDONLY|os.O_NONBLOCK|getattr(os,'O_NOFOLLOW',0))
        with os.fdopen(fd,'rb')as handle:
            info=os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode)or info.st_mode&0o077 or info.st_size>8192:raise ValueError('owner-only regular demo credential required')
            credential=_parse_json(handle.read(8193))
        self.signer_id=credential.get('account_id')
        if credential.get('network')!='testnet'or not re.fullmatch(r'csl-registry-[0-9a-f]{12}\.testnet',self.signer_id or'')or self.signer_id!=client.contract_id:
            raise ValueError('fresh dedicated testnet registry relayer credential required')
        self.node=node_binary or shutil.which('node')
        if not self.node:raise ValueError('configured Node runtime required for testnet relayer')
        self.script=Path(script_path)if script_path else Path(__file__).resolve().parents[3]/'tools/near-mvp/submit-testnet.mjs'
        if not self.script.is_file():raise ValueError('explicit installed relayer script required')
        self.runner=runner or subprocess.run
        if self.root.is_symlink():raise ValueError('private regular submission directory required')
        self.root.mkdir(mode=0o700,parents=True,exist_ok=True)

    def register(self,public,*,allow_submit=False):
        with self._submit_lock:
            lock=self.credential_file.with_name(self.credential_file.name+'.relay.lock')
            fd=os.open(lock,os.O_RDWR|os.O_CREAT|getattr(os,'O_NOFOLLOW',0),0o600)
            try:
                info=os.fstat(fd)
                if not stat.S_ISREG(info.st_mode)or info.st_mode&0o077:raise ValueError('private regular relay lock required')
                try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
                except BlockingIOError:raise NearRegistryError('relayer_busy_no_submit')from None
                return self._register(public,allow_submit=allow_submit)
            finally:os.close(fd)

    def recorded_transaction(self,public):
        """Read a pre-broadcast transaction identity; never signs or submits."""
        if not _valid_public(public):raise ValueError('exact public commitment required')
        path=self.root/public['commitment']/'operation/submission.json'
        try:fd=os.open(path,os.O_RDONLY|os.O_NONBLOCK|getattr(os,'O_NOFOLLOW',0))
        except FileNotFoundError:return None
        with os.fdopen(fd,'rb')as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):raise ValueError('regular submission receipt required')
            raw=handle.read(16385)
        if len(raw)>16384:raise ValueError('bounded submission receipt required')
        value=_parse_json(raw)
        if value.get('network')!='testnet'or value.get('signer_id')!=self.signer_id:raise ValueError('different submission route')
        transaction_hash=value.get('transaction_hash')
        return {'transaction_hash':_hash(transaction_hash),'signer_id':self.signer_id}if transaction_hash else None

    def _register(self,public,*,allow_submit=False):
        if not allow_submit or not _valid_public(public):raise ValueError('explicit public commitment submission required')
        # Read checks are safe to repeat. A reserved submission is never retried.
        existing=self.client.verify_record(public)
        if existing['verified']:return existing
        folder=self.root/public['commitment']
        try:folder.mkdir(mode=0o700)
        except FileExistsError:raise NearRegistryError('submission_already_attempted_inspect_receipt')from None
        target=folder/'operation';env={key:os.environ[key]for key in ('PATH','LANG','LC_ALL')if key in os.environ}
        command=[self.node,str(self.script),'register',str(self.credential_file),str(target),public['commitment'],self.client.expected_code_hash]
        try:
            result=self.runner(command,capture_output=True,text=True,timeout=80,env=env,check=False)
            marker=_parse_json((target/'submission.json').read_bytes())
            tx_hash=marker.get('transaction_hash')
            if tx_hash:
                _hash(tx_hash)
                try:return self.client.verify_transaction(public,transaction_hash=tx_hash,signer_id=self.signer_id)
                except NearRegistryError:return {'status':'submitted_unverified','verified':False,'network':'testnet','transaction_hash':tx_hash,
                    'signer_id':self.signer_id,'public':deepcopy(public),'automatic_retry':False,
                    'message':'Submission may have executed. Check the recorded transaction; no automatic retry.'}
            return {'status':'not_dispatched','verified':False,'network':'testnet','public':deepcopy(public),'automatic_retry':False}
        except Exception:raise NearRegistryError('submission_outcome_unknown_inspect_private_receipt')from None
