"""Persistent operator-funded preview allowance; deliberately not a billing ledger.

Reserve the one native call durably before handing off to a provider.
Never release it automatically: timeouts and refunds need operator reconciliation.
A restart or replacement browser login cannot replenish the allowance.
"""
from pathlib import Path
import stat
from threading import RLock

from .agent_models import ModelFailure
from .agent_worlds import _int, _shape
from .decision_sessions import _locked, _read, _write
from .jev import validate_request, TypeSafeError


class PreviewAllowanceError(ModelFailure):
    def __init__(self,*,route='TypeSafe'):
        self.route=route
        super().__init__(f'preview_{route.lower()}_allowance_exhausted','not_dispatched')
    def safe_details(self):
        return {'message':f'The operator-funded preview allowance is exhausted or too small for this experiment. Reduce the run, use your own key for the {self.route} route, try local rules, or ask the host for a larger allowance.',
                'remote_outcome':'not_dispatched','scope':'preview_allowance','automatic_retry':False}


class PreviewJevClient:
    allowance_schema='native-preview-allowance.v1'
    allowance_route='TypeSafe'

    def __init__(self,client,*,root,call_limit):
        _int(call_limit,1,100000)
        self.client=client;self.root=Path(root);self.call_limit=call_limit
        self._lock=RLock()
        created=False
        try:self.root.mkdir(mode=0o700);created=True
        except FileExistsError:pass
        if self.root.is_symlink()or not self.root.is_dir()or self.root.stat().st_mode&0o077:
            raise ValueError('owner-only regular allowance directory required')
        with self._lock,_locked(self.root):
            if created:_write(self.root,'allowance.json',{'schema_version':self.allowance_schema,'reserved_calls':0})
            self._state()  # Existing but missing/corrupt files fail closed.

    def __getattr__(self,name):return getattr(self.client,name)

    def _state(self):
        path=self.root/'allowance.json'
        info=path.lstat()
        if not stat.S_ISREG(info.st_mode)or info.st_mode&0o077 or info.st_size>4096:
            raise ValueError('bounded owner-only allowance required')
        value=_read(path)
        _shape(value,{'schema_version','reserved_calls'})
        if value['schema_version']!=self.allowance_schema:raise ValueError('invalid allowance version')
        _int(value['reserved_calls'],0,100000)
        return value

    def budget_status(self):
        with self._lock,_locked(self.root):
            reserved=self._state()['reserved_calls']
        return {'call_limit':self.call_limit,'reserved_calls':reserved,
                'remaining_calls':max(0,self.call_limit-reserved),
                'scope':f'Operator-funded {self.allowance_route} for this reviewer; persists across sign-in and process restart.',
                'basis':'Conservative pre-dispatch reservation, not provider charges or prepaid money. Failed and unknown calls are not automatically released.'}

    def ensure_budget(self,calls):
        _int(calls,0,100000)
        status=self.budget_status()
        if calls>status['remaining_calls']:
            raise PreviewAllowanceError(route=self.allowance_route)
        return status

    def _reserve(self):
        with self._lock,_locked(self.root):
            saved=self._state()
            if saved['reserved_calls']+1>self.call_limit:
                raise PreviewAllowanceError(route=self.allowance_route)
            saved['reserved_calls']+=1
            _write(self.root,'allowance.json',saved,replace=True)

    def get_models(self):return self.client.get_models()

    def evaluate(self,*,state,questions=None,question_set_id=None):
        if question_set_id is not None:raise ValueError('explicit questions required')
        validate_request(state=state,questions=questions,model=self.model)
        delay=getattr(self.client,'retry_after_seconds',0)
        if delay:raise TypeSafeError(429,retry_after_seconds=delay,remote_outcome='not_dispatched',cooldown=True)
        self._reserve()
        return self.client.evaluate(state=state,questions=questions)


class PreviewAuthorClient(PreviewJevClient):
    """Bounds operator-funded text generation: the author route and any Gemini
    decision actor, which delegates to the author client it was given."""
    allowance_schema='author-preview-allowance.v1'
    allowance_route='author'

    def generate(self,messages):
        self._reserve()
        return self.client.generate(messages)
