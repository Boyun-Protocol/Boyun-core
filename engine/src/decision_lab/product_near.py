"""Explicit salted result anchoring for the bounded testnet submission demo."""
from hashlib import sha256
from pathlib import Path
from threading import RLock
import secrets
import time
import re
from .integrity import _testnet_account
from .decision_sessions import _read,_write
from .integrity import create_commitment,verify_commitment


class ProductNear:
    def __init__(self,root,relayer=None):
        self.root=Path(root);self.relayer=relayer;self._lock=RLock()
        if self.root.is_symlink():raise ValueError('regular private anchor directory required')
        self.root.mkdir(mode=0o700,parents=True,exist_ok=True)
    def capabilities(self):
        return {'enabled':self.relayer is not None,'network':'testnet','contract_id':getattr(getattr(self.relayer,'client',None),'contract_id',None),
            'signer_id':getattr(self.relayer,'signer_id',None),'public_data':'Salted commitment only; signer, contract and transaction metadata are public.',
            'max_attached_testnear':'0.01','automatic_submit':False,'mainnet':False,'wallet_enabled':self.relayer is not None,'wallet':'intear','wallet_network':'testnet'}
    def _folder(self,data):
        if type(data)is not bytes or not 1<=len(data)<=8*1024*1024:raise ValueError('bounded exact recorded bytes required')
        return self.root/sha256(data).hexdigest()
    def prepare(self,data):
        with self._lock:
            folder=self._folder(data)
            if not folder.exists():
                folder.mkdir(mode=0o700);public,opening=create_commitment(data)
                _write(folder,'public.json',public);_write(folder,'opening.private.json',opening)
            public=_read(folder/'public.json');opening=_read(folder/'opening.private.json')
            if folder.is_symlink()or not verify_commitment(data,public,opening):raise ValueError('anchor opening differs from exact result bytes')
            value={'schema_version':'product-near-anchor.v1','status':'prepared_private','public':public,'capabilities':self.capabilities(),
                'opening_available':True,'verified':False,'model_requests':0}
            receipt=folder/'receipt.json'
            if receipt.exists():value['receipt']=_read(receipt);value['verified']=value['receipt'].get('verified')is True
            elif (folder/'submission-attempt.json').exists():value['status']='submission_attempted_unverified'
            value['can_submit']=self.relayer is not None and not (folder/'submission-attempt.json').exists() and not value['verified']
            return value
    def opening(self,data):
        with self._lock:
            self.prepare(data)
            return _read(self._folder(data)/'opening.private.json')
    def submit(self,data,request):
        if type(request)is not dict or set(request)!={'allow_submit','commitment'}or request['allow_submit']is not True:raise ValueError('explicit reviewed testnet submit required')
        if self.relayer is None:raise ValueError('demo testnet relayer not configured')
        with self._lock:
            prepared=self.prepare(data);public=prepared['public']
            if request['commitment']!=public['commitment']:raise ValueError('reviewed exact commitment required')
            folder=self._folder(data);receipt_path=folder/'receipt.json'
            if receipt_path.exists() and prepared['verified']:return self._response(prepared,_read(receipt_path))
            _write(folder,'submission-attempt.json',{'status':'dispatching','automatic_retry':False,'public':public})
            result=self.relayer.register(public,allow_submit=True)
            _write(folder,'receipt.json',result,replace=receipt_path.exists())
            return self._response({**prepared,'can_submit':False},result)
    def verify(self,data):
        if self.relayer is None:raise ValueError('testnet verification route not configured')
        with self._lock:
            prepared=self.prepare(data);folder=self._folder(data);path=folder/'receipt.json'
            old=_read(path)if path.exists()else{}
            if not old.get('transaction_hash')and (folder/'submission-attempt.json').exists()and callable(getattr(self.relayer,'recorded_transaction',None)):
                recorded=self.relayer.recorded_transaction(prepared['public'])
                if recorded:old.update(recorded)
            if old.get('transaction_hash'):
                result=self.relayer.client.verify_transaction(prepared['public'],transaction_hash=old['transaction_hash'],signer_id=old.get('signer_id',self.relayer.signer_id))
            else:result=self.relayer.client.verify_record(prepared['public'])
            _write(folder,'receipt.json',result,replace=path.exists())
            return self._response(prepared,result)
    def wallet_prepare(self,data,request):
        if type(request)is not dict or set(request)!={'signer_id'}or not _testnet_account(request['signer_id']):raise ValueError('explicit testnet signer required')
        if self.relayer is None:raise ValueError('testnet registry not configured')
        with self._lock:
            prepared=self.prepare(data);folder=self._folder(data)/'wallet-plans';folder.mkdir(mode=0o700,exist_ok=True)
            if len(list(folder.glob('*.json')))>=50:raise ValueError('wallet plan limit reached for this result')
            public,opening=create_commitment(data)
            # Fresh salt per wallet plan; an existing operator receipt never
            # masquerades as this wallet's authorship or signature.
            descriptor=self.relayer.client.prepare(public,signer_id=request['signer_id'])
            token=secrets.token_hex(32)
            saved={'plan_id':token,'created_at':int(time.time()),'public':public,'opening':opening,'descriptor':descriptor,'attempted':False,'receipt':None}
            _write(folder,token+'.json',saved)
            return {'plan_id':token,'public':public,'descriptor':descriptor,'expires_in_seconds':900,'status':'wallet_review_required','model_requests':0}
    def _wallet_plan(self,data,token):
        if type(token)is not str or not re.fullmatch(r'[0-9a-f]{64}',token):raise ValueError('bounded wallet plan identity required')
        folder=self._folder(data)/'wallet-plans';path=folder/(token+'.json');plan=_read(path)
        if not verify_commitment(data,plan['public'],plan['opening']):raise ValueError('wallet plan does not open this exact result')
        return folder,plan
    def wallet_resume(self,data,request):
        if type(request)is not dict or set(request)!={'plan_id'}:raise ValueError('exact wallet plan identity required')
        with self._lock:
            _,plan=self._wallet_plan(data,request['plan_id'])
            return {'plan_id':plan['plan_id'],'public':plan['public'],'descriptor':plan['descriptor'],'attempted':plan['attempted'],'transaction_hash':plan.get('transaction_hash'),'receipt':plan.get('receipt'),'model_requests':0}
    def wallet_attempt(self,data,request):
        if type(request)is not dict or set(request)!={'plan_id','allow_wallet_submit'}or request['allow_wallet_submit']is not True:raise ValueError('explicit wallet confirmation required')
        with self._lock:
            folder,plan=self._wallet_plan(data,request['plan_id'])
            if plan['attempted']or time.time()-plan['created_at']>900:raise ValueError('wallet plan expired or already attempted; inspect activity before another submission')
            plan['attempted']=True;_write(folder,plan['plan_id']+'.json',plan,replace=True)
            return {'status':'wallet_confirmation_reserved','plan_id':plan['plan_id'],'automatic_retry':False}
    def wallet_verify(self,data,request):
        from .near_registry import _hash
        if self.relayer is None or type(request)is not dict or set(request)!={'plan_id','transaction_hash'}:raise ValueError('exact wallet verification request required')
        _hash(request['transaction_hash'])
        with self._lock:
            folder,plan=self._wallet_plan(data,request['plan_id'])
            if not plan['attempted']:raise ValueError('wallet submission was not explicitly confirmed')
            if plan.get('transaction_hash')and plan['transaction_hash']!=request['transaction_hash']:raise ValueError('wallet transaction identity changed')
            plan['transaction_hash']=request['transaction_hash'];_write(folder,plan['plan_id']+'.json',plan,replace=True)
            receipt=self.relayer.client.verify_transaction(plan['public'],transaction_hash=request['transaction_hash'],signer_id=plan['descriptor']['signer_id'])
            plan['receipt']=receipt;_write(folder,plan['plan_id']+'.json',plan,replace=True)
            return {'status':receipt['status'],'verified':receipt['verified'],'plan_id':plan['plan_id'],'public':plan['public'],'receipt':receipt,'model_requests':0}
    def wallet_opening(self,data,token):
        with self._lock:return self._wallet_plan(data,token)[1]['opening']
    @staticmethod
    def _response(prepared,receipt):return {**prepared,'status':receipt.get('status','unknown'),'verified':receipt.get('verified')is True,'receipt':receipt,'can_submit':prepared.get('can_submit')is True and receipt.get('verified')is not True}
