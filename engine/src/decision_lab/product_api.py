"""Bounded local product workflow: author, review, dispatch, replay, summarize.

No request is made on startup. Clients and the explicitly named secret are
configured by the server operator, never supplied by the browser. This is a
local development product, not a hosted multi-user service.
"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from importlib.resources import files
import json
from pathlib import Path
import re
from statistics import mean, median
from threading import RLock,Event
from uuid import uuid4

from .agent_models import ModelFailure
from .agent_worlds import canonical, digest, _int, _shape, _text
from .decision_sessions import _write, _read
from .strategic_models import authoring_messages, validate_proposal, decide, decision_request, PROBABILITY_MEANING
from .strategic_worlds import StrategicWorld, validate_strategic_world, replay_strategic_world, strategic_game, MAX_ACTORS

from .product_insights import DECISION_RECORD_SCOPE

MAX_CALLS = 800
LIMITATIONS = [
    'This is an explicit hypothetical strategic game, not an empirically calibrated market forecast.',
    'Cash is spent only on declared action costs. Utility and shared metric points are not token-sale profit.',
    PROBABILITY_MEANING,
    DECISION_RECORD_SCOPE,
    'Local artifacts contain full scenario details. Remote models see their supplied inputs; no on-chain publication occurs.',
    'The Gemini CLI route is public development input only. No secret or confidential scenario should be submitted to that route.',
    'No automatic retry or route fallback. A provider failure stops the experiment and preserves its denominator.',
]


def examples():
    value = json.loads(files('decision_lab').joinpath('data/strategic_examples.json').read_text())
    for example in value: validate_strategic_world(example['world'])
    return value


def _route_identity(client):
    # Secret values never enter this identity or any artifact. Instance identity
    # also prevents swapping clients with otherwise identical declared settings.
    return digest({'instance':id(client),'class':type(client).__name__,
        **{key:getattr(client,key,None)for key in ('model','endpoint','protocol','timeout','binary','http_client')}})


def _future_observations(world,*,character_bound=False):
    """Bound worst future prompt growth without revealing it to any actor.

    This is a conservative size estimate, not a future observation dispatched to
    a model. It includes all own visible events, maximum subscribed publications,
    own history and every action, even when that combination is not reachable.
    """
    maximum_metrics={m['id']:-max(abs(m['min']),abs(m['max'])) for m in world['metrics']}
    actors={a['id']:a for a in world['actors']}
    text_size=(lambda value:len(json.dumps(value,ensure_ascii=False,separators=(',',':')).encode('utf-16-le'))//2)if character_bound else(lambda value:len(canonical(value)))
    for identifier,obs in StrategicWorld(world).observations().items():
        actor=actors[identifier];future=deepcopy(obs);future.pop('observation_sha256')
        future.update(round=world['rounds'],metrics=maximum_metrics,actions=deepcopy(actor['actions']),
            events=[{key:deepcopy(e[key])for key in ('id','text','round')}for e in world['events']if identifier in e['visible_to']])
        future['messages']=[]
        future['own_history']=[]
        biggest_action=max(actor['actions'],key=lambda a:len(a['id']))
        for r in range(1,world['rounds']):
            future['own_history'].append({'round':r,'action_id':biggest_action['id'],
                'cost_cents':max(a['cost_cents']for a in actor['actions']),'metrics_after':maximum_metrics})
            for source in actor['subscriptions']:
                message=max((a['message']for a in actors[source]['actions']),key=text_size)
                if message:future['messages'].append({'id':f'round-{r}-{source}','source':source,'round':r,'text':message})
        future['observation_sha256']=digest(future)
        yield future


def estimate_typesafe_usage(world,worlds=1):
    """Conservative byte-based input estimate; never a tokenizer or billing cap."""
    from decimal import Decimal
    from .jev import validate_request, PRICE_INPUT_USD_PER_MILLION
    _int(worlds,1,4)
    maximum=0
    for future in _future_observations(world):
        request=decision_request(future)
        payload=validate_request(state=future,questions=request['questions'],model='jev-latest')
        maximum+=len(canonical(payload))*world['rounds']*worlds
    count=len(world['actors'])*world['rounds']*worlds
    return {'actor_call_ceiling':count,'input_tokens_upper_bound':maximum,
        'input_cost_upper_estimate_usd':float(Decimal(maximum)*Decimal(PRICE_INPUT_USD_PER_MILLION)/Decimal(1000000)),
        'basis':'Estimate using one input token per canonical UTF-8 request byte and maximum future prompt growth, at the published input list price. No tokenizer or billing guarantee; provider framing may differ. Forced single-action turns skip inference. The call cap controls dispatch; this is not a dollar cap.',
        'includes_authoring':False,'estimate_only':True}


def _preflight_world(world, route):
    from .jev import validate_request
    result_bound=len(canonical(world))+16384
    for future in _future_observations(world):
        request=decision_request(future)
        validate_request(state=future,questions=request['questions'],model='jev-latest')
        result_bound+=world['rounds']*(len(canonical(future))+8192)
    return result_bound


class ProductManager:
    def __init__(self, output_dir, *, author_client=None, actor_clients=None, route_status=None,hosted=False):
        self.root = Path(output_dir)
        if self.root.is_symlink(): raise ValueError('private regular output directory required')
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.author = author_client
        self.actors = dict(actor_clients or {})
        if not set(self.actors) <= {'gemini','typesafe'}: raise ValueError('unsupported configured route')
        self.route_status = dict(route_status or {})
        self._operator_author=author_client;self._operator_actors=dict(self.actors)
        self._access={'completed':False,'mode':'operator','hosted':bool(hosted),'storage':'process_memory_only'}
        self._typesafe_health=None
        self._imported_author=False
        self._closing=Event();self._access_revoked=Event()
        self._sessions = {}; self._lock = RLock(); self._busy = False
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='strategic-product')

    def close(self):
        self._closing.set()  # Prevent the next actor dispatch before waiting.
        with self._lock:
            for state in self._sessions.values():
                if state['status']=='authoring'and state.get('authoring_plan'):
                    state['authoring_cancel_requested']=True
                    state['progress']['phase']='Server stopping after the active author call; no further batch dispatch'
                    try:self._save(state)
                    except (OSError,ValueError):pass
        self._executor.shutdown(wait=True, cancel_futures=False)
        self.actors.clear();self.author=None;self._operator_actors.clear();self._operator_author=None

    def bootstrap(self):
        return {'examples': examples(), 'access':self.access_status(), 'routes': {
            'author': self.author_status(),
            'actors': [{'id':key,'label':{'gemini':'Gemini / Antigravity','typesafe':'Jev / TypeSafe','offline':'Offline rules'}[key],
                'enabled':key in self.actors,'model':getattr(self.actors.get(key),'model',None),
                'public_only':key=='gemini','decision_contract':'jev-choice-noul.v1' if getattr(self.actors.get(key),'protocol',None)=='gemini-jev-choice-noul.v1' else None,'status':self.route_status.get(key,'Configured, not an inference verification' if key in self.actors else 'Not configured')}
                for key in ('gemini','typesafe','offline')]},
            'limits':{'max_worlds':4,'max_actors':MAX_ACTORS,'max_calls':MAX_CALLS,'max_credits':0,'max_author_calls':6,'author_batch_size':20},
            'limitations':list(LIMITATIONS),'typesafe_health':deepcopy(self._typesafe_health)}

    def access_status(self):
        with self._lock:return {**self._access,'operator_available':bool(self._operator_actors),'import_available':True,
            'offline_policy':'Deterministic own-action utility; no AI, narrative interpretation or calibrated odds.'}

    def release_imported_access(self):
        """Revoke future dispatches; an in-flight provider request cannot be undone."""
        with self._lock:
            if self._access['mode']!='typesafe'and not self._imported_author:return
            self._access_revoked.set()
            self.actors={};self.author=None;self._imported_author=False;self._typesafe_health=None
            self._access.update(mode='unconfigured',completed=False)
            for state in self._sessions.values():
                if state['status']not in ('running','authoring'):state['review']=None

    def configure_access(self,data):
        """No persistence or provider request; call only through a trusted boundary."""
        _shape(data,{'mode','api_key','accept_host_access'})
        if data['mode']not in ('offline','typesafe','operator')or type(data['accept_host_access'])is not bool:raise ValueError('explicit access mode required')
        with self._lock:
            if self._busy or any(s['status']in ('authoring','running')for s in self._sessions.values()):raise ValueError('wait for active work before changing credentials')
            if data['mode']=='typesafe':
                if self._access['hosted']and data['accept_host_access']is not True:raise ValueError('explicit host trust acknowledgment required')
                from .jev import TypeSafeClient
                actors={'typesafe':TypeSafeClient(api_key=data['api_key'],model='jev-latest',http_client='curl',timeout_seconds=180)}
                author=self.author if self._imported_author else None
            else:
                if data['api_key']!='':raise ValueError('key only accepted for imported TypeSafe access')
                if data['mode']=='offline':
                    from .offline_decisions import OfflineDecisions
                    actors={'offline':OfflineDecisions()};author=None
                else:
                    if not self._operator_actors:raise ValueError('operator route unavailable')
                    actors=dict(self._operator_actors);author=self.author if self._imported_author else self._operator_author
            # Persist invalidation before accepting the new route. A failed save
            # cannot leave a previously reviewed dispatch valid for a new key.
            for state in self._sessions.values():
                state['review']=None;self._save(state)
            self.actors=actors;self.author=author;self._typesafe_health=None
            if data['mode']=='offline':self._imported_author=False
            self._access_revoked=Event()
            self._access.update(completed=True,mode=data['mode'])
            return self.access_status()

    def author_status(self):
        client=self.author
        provider=getattr(client,'provider','gemini' if client is not None else None)
        return {'enabled':client is not None,'provider':provider,'model':getattr(client,'model',None),
            'public_only':getattr(client,'public_only',True),
            'imported':self._imported_author,'storage':'process_memory_only',
            'privacy_status':'UNVERIFIED',
            'disclosure':'The selected provider receives the world brief and proposed world. The host sees plaintext. No confidential-inference attestation is verified.'}

    def configure_author(self,data):
        """Independent author credential, never persisted and never checked on import."""
        _shape(data,{'mode','api_key','model','accept_host_access'})
        if data['mode']not in ('near_ai','operator','none')or type(data['accept_host_access'])is not bool:
            raise ValueError('explicit author mode required')
        with self._lock:
            if self._busy or any(s['status']in ('authoring','running')for s in self._sessions.values()):
                raise ValueError('wait for active work before changing author')
            if self._access['mode']=='offline'and data['mode']!='none':raise ValueError('offline mode disables external authoring')
            if data['mode']=='near_ai':
                if self._access['hosted']and not data['accept_host_access']:raise ValueError('explicit host trust acknowledgment required')
                from .near_ai import NearAITextModel
                client=NearAITextModel(api_key=data['api_key'],model=data['model'])
            else:
                if data['api_key']!='':raise ValueError('only imported author accepts a key')
                client=self._operator_author if data['mode']=='operator'else None
                if data['mode']=='operator'and client is None:raise ValueError('operator author unavailable')
            for state in self._sessions.values():
                state['review']=None;self._save(state)
            self.author=client;self._imported_author=data['mode']=='near_ai'
            self._access_revoked=Event()
            return self.author_status()

    def _authorize_author(self,client):
        with self._lock:
            if self._closing.is_set()or self._access_revoked.is_set()or self.author is not client:
                raise ModelFailure('author_access_revoked','not_dispatched')
        # This authorizes one operation. Revocation cannot undo an in-flight call.

    def author_models(self):
        with self._lock:
            client=self.author
            if client is None or not callable(getattr(client,'get_models',None)):raise ValueError('Cloud author not configured')
            if self._busy:raise ValueError('another model operation is active')
            self._busy=True
        try:
            self._authorize_author(client)
            result=client.get_models()
        finally:
            with self._lock:self._busy=False
        with self._lock:
            if self.author is not client:raise ValueError('author access changed')
        return result

    def check_typesafe_access(self):
        """Explicit free provider request. Startup and ordinary polling never call it."""
        with self._lock:
            client=self.actors.get('typesafe')
            if client is None or not callable(getattr(client,'get_models',None)):raise ValueError('TypeSafe not configured')
            if self._busy:raise ValueError('another model operation is active')
            self._busy=True
        try:
            with self._lock:
                if self._access_revoked.is_set()or self.actors.get('typesafe')is not client:
                    return {'status':'revoked','error':'access_changed'}
            value=client.get_models()
            result={'status':'ready',**value}
        except ModelFailure as error:
            result={'status':'failed','error':error.code}
            if callable(getattr(error,'safe_details',None)):result['details']=error.safe_details()
        finally:
            with self._lock:self._busy=False
        with self._lock:
            if self.actors.get('typesafe')is not client:return {'status':'revoked','error':'access_changed'}
            self._typesafe_health=deepcopy(result)
        return result

    def _save(self, state):
        _write(self.root/state['id'],'state.json',state,replace=True)

    def saved_results(self):
        from .product_history import list_saved_results
        with self._lock:return list_saved_results(self.root)

    def saved_result(self,identifier,run_id):
        from .product_history import saved_result
        with self._lock:return saved_result(self.root,identifier,run_id)

    def saved_result_bytes(self,identifier,run_id):
        from .product_history import saved_result_bytes
        with self._lock:return saved_result_bytes(self.root,identifier,run_id)

    def presentation(self,identifier):
        from .scenario_presentation import build_presentation
        return build_presentation(self.snapshot(identifier))

    def saved_presentation(self,identifier,run_id):
        from .scenario_presentation import build_presentation
        return build_presentation(self.saved_result(identifier,run_id))

    def report(self,identifier,format,run_id=None):
        from .product_reports import render_report
        with self._lock:
            run_id=run_id or self.snapshot(identifier).get('run_id')
            if not run_id:raise ValueError('a recorded run is required')
            from .product_history import _folder,summarize_provider_receipts
            folder=_folder(self.root,identifier,run_id)
            from .product_history import _review
            review=_review(folder,{})
            if review is None:raise ValueError('frozen run review required')
            results=[_read(folder/f'world-{i}.json')for i in range(4)if (folder/f'world-{i}.json').exists()]
            world=_read(folder/'world.json')if (folder/'world.json').exists()else results[0]['result']['world']
            if digest(world)!=review['world_sha256']:raise ValueError('frozen report world mismatch')
            context=_read(folder/'context.json')if (folder/'context.json').exists()else{}
            if context and context.get('world_sha256')!=review['world_sha256']:raise ValueError('frozen question mismatch')
            status=_read(folder/'status.json')['status']if (folder/'status.json').exists()else 'completed'if len(results)==review['worlds']else'partial'
            snapshot={'proposal':{'world':world},'results':results,'status':status,'question':context.get('question'),'review':review}
            snapshot['review']=review
            responses=[_read(p)for p in sorted(folder.glob('call-*.response.json'))]
            receipts=[v.get('receipt')for v in responses if type(v)is dict and type(v.get('receipt'))is dict]
            remote=[r for r in receipts if r.get('local_decision')is not True]
            evidence=summarize_provider_receipts(remote)
            attempts=len(list(folder.glob('call-*.request.json')))
            local=review['actor_route']=='offline'
            accounting={'route':review['actor_route'],'attempted_provider_calls':0 if local else attempts,
                'recorded_provider_responses':len(remote),
                'recorded_input_tokens':0 if local else evidence['recorded_input_tokens'],
                'native_typesafe_receipts':evidence['native_typesafe_receipts'],
                'input_token_receipts':evidence['input_token_receipts'],
                'recorded_models':', '.join(evidence['models'])or None,
                'identity_meaning':evidence['identity_meaning'],
                'acceptance_meaning':'Saved receipts preserve their recorded provider identity. They do not independently establish direct TypeSafe live acceptance.',
                'cost_usd':None,
                'unknown_remote_outcomes':0 if local else attempts-len(remote),
                'local_rule_turns':len(receipts)if local else 0,
                'estimate_scope':'All saved actor responses in this run, including incomplete worlds; authoring excluded. Native TypeSafe token and input-cost totals cover only native receipts with those recorded fields. Published list-price estimates are not provider billing.',
                'reviewed_call_ceiling':review['max_calls'],
                'input_cost_estimate_usd':0 if local else evidence['input_cost_estimate_usd']}
            return render_report(snapshot,format,accounting)

    def snapshot(self, identifier):
        with self._lock:
            if type(identifier) is not str or not re.fullmatch(r'[0-9a-f]{32}',identifier):
                raise KeyError('session not found')
            if identifier not in self._sessions: self._restore(identifier)
            return deepcopy(self._sessions[identifier])

    def download_bytes(self, identifier):
        # Serialize integers on the server; browser Number/JSON round trips can
        # otherwise corrupt large exact utility values in an exported replay.
        state=self.snapshot(identifier)
        if not state['results']:raise ValueError('no completed world results')
        return canonical(state['results'])+b'\n'

    def _restore(self, identifier):
        if len(self._sessions)>=32:raise ValueError('local session capacity reached')
        path=self.root/identifier
        if path.is_symlink():raise ValueError('regular private session directory required')
        state=_read(path/'state.json')
        required={'id','status','question','proposal','review','progress','error','results','history','authoring_attempts','summary'}
        if type(state) is not dict or not required<=set(state) or not set(state)<=required|{'game_analysis','run_id','error_details','authoring_plan','authoring_cancel_requested'}:
            raise ValueError('invalid saved session shape')
        if state['id']!=identifier or state['status'] not in ('draft','ready','authoring','running','completed','failed'):
            raise ValueError('invalid saved session identity or status')
        _text(state['question'],8000);_int(state['authoring_attempts'],0,6)
        if 'authoring_plan'in state:
            from .batch_authoring import validate_plan
            validate_plan(state['authoring_plan'])
            if type(state.get('authoring_cancel_requested'))is not bool:raise ValueError('explicit cancellation flag required')
        if type(state['results']) is not list or len(state['results'])>4:raise ValueError('bounded saved results required')
        if state['proposal'] is not None:
            validate_proposal(state['proposal'],state['proposal']['context_sha256'])
        for item in state['results']:
            _shape(item,{'world_index','result','decisions'})
            replay_strategic_world(item['result'])
            if state['proposal'] is None or item['result']['world']!=state['proposal']['world']:
                raise ValueError('saved result differs from reviewed world')
        state['review']=None  # New process/config always requires a fresh review.
        if state['status'] in ('running','authoring'):
            state.update(status='failed',error='interrupted_no_automatic_retry')
            state['progress']['phase']='Interrupted. Inspect receipts before explicitly authorizing another run.'
        self._sessions[identifier]=state
        self._save(state)

    def _new(self, question):
        if len(self._sessions) >= 32: raise ValueError('local session capacity reached')
        identifier = uuid4().hex
        (self.root/identifier).mkdir(mode=0o700)
        state = {'id':identifier,'status':'draft','question':question,'proposal':None,'review':None,
            'progress':{'phase':'Draft','attempted_calls':0,'completed_calls':0,'total_calls':0,'completed_worlds':0},
            'error':None,'results':[],'history':[],'authoring_attempts':0,'summary':None}
        self._sessions[identifier] = state; self._save(state)
        return state

    def _dispatch(self, callback, *args):
        if self._busy: raise ValueError('another model operation is still running')
        self._busy = True
        try: self._executor.submit(self._worker, callback, args)
        except BaseException:
            self._busy = False; raise

    def _worker(self, callback, args):
        try: callback(*args)
        except Exception:
            # Includes pre-dispatch artifact failures. Never leave a false
            # indefinitely-running state when the background worker has exited.
            with self._lock:
                state=self._sessions[args[0]]
                state.update(status='failed',error='local_worker_failed')
                state['progress']['phase']='Stopped; local worker failed, no automatic retry'
                try:self._save(state)
                except (OSError,ValueError):pass
        finally:
            with self._lock: self._busy = False

    def import_world(self,world,question):
        """Explicit inert world from a caller's own agent; never interpret prose."""
        world=validate_strategic_world(world);_text(question,8000)
        with self._lock:
            if self._busy:raise ValueError('idle worker required')
            state=self._new(question)
            state['proposal']={'schema_version':'strategic-proposal.v1','context_sha256':digest(world),
                'summary':'Caller-imported validated rules and profiles; no author inference or empirical endorsement.',
                'questions':[],'world':deepcopy(world),'limitations':list(LIMITATIONS)}
            state['status']='ready';self._save(state);return deepcopy(state)

    def create(self, data):
        extra={key for key in ('authoring_plan','persona_options')if type(data)is dict and key in data}
        _shape(data, {'mode','example_id','question','public_input'}|extra)
        plan=None
        persona_options=None
        if 'persona_options'in extra:
            from .persona_controls import validate_options
            persona_options=validate_options(data['persona_options'])
            if data['mode']!='example':raise ValueError('profile controls adapt reviewed examples; author requests use their brief')
        if 'authoring_plan'in extra:
            from .batch_authoring import validate_plan
            plan=validate_plan(data['authoring_plan'])
            if data['mode']!='author':raise ValueError('batched authoring requires explicit author mode')
        _text(data['question'],8000)
        if type(data['public_input']) is not bool: raise ValueError('public input flag required')
        with self._lock:
            if data['mode']=='example':
                template = next((e for e in examples() if e['id']==data['example_id']),None)
                if template is None: raise ValueError('known authored example required')
                # The typed question is retained, but is not silently interpreted.
                # The proposal explicitly identifies what example actually runs.
                state = self._new(data['question'])
                state['proposal'] = {'schema_version':'strategic-proposal.v1','context_sha256':digest(data),
                    'summary':'Authored example: '+template['title']+'. Your question has not been interpreted by a model. Edit this world or use live construction to adapt it.',
                    'questions':[],'world':deepcopy(template['world']),'limitations':list(LIMITATIONS)}
                if persona_options:
                    from .persona_controls import adapt_personas
                    state['proposal']['world']=adapt_personas(state['proposal']['world'],persona_options)
                    state['proposal']['summary']+=' Reviewed profile emphasis applied; numeric rules and capital are unchanged.'
                state['status']='ready'; self._save(state); return deepcopy(state)
            if data['mode']!='author' or self.author is None or data['public_input'] is not True or self._busy:
                raise ValueError('explicit configured public authoring required; worker must be idle')
            if data['example_id'] is not None and data['example_id'] not in {e['id']for e in examples()}:
                raise ValueError('known example or null required')
            state = self._new(data['question']); state['status']='authoring'
            if plan:state.update(authoring_plan=plan,authoring_cancel_requested=False)
            state['progress']['phase']='Constructing players, incentives and rules'
            self._save(state); self._dispatch(self._author, state['id'], None)
            return deepcopy(state)

    def say(self, identifier, data):
        _shape(data, {'message','public_input'}); _text(data['message'],8000)
        with self._lock:
            state = self._sessions[identifier]
            if state.get('authoring_plan'):raise ValueError('Batched revisions require a new reviewed authoring plan; start a new question with the clarification or change.')
            if self.author is None or data['public_input'] is not True or state['status'] in ('running','authoring') or self._busy:
                raise ValueError('explicit public authoring and idle worker required')
            if state['authoring_attempts']>=6: raise ValueError('authoring call limit reached')
            state.update(status='authoring',error=None,error_details=None,review=None,results=[],summary=None)
            state['progress']['phase']='Updating world and persona choices'
            self._save(state); self._dispatch(self._author,identifier,data['message'])
            return deepcopy(state)

    def _author(self, identifier, message):
        if self._sessions[identifier].get('authoring_plan'):
            return self._author_batched(identifier)
        state=self._sessions[identifier]
        try:
            with self._lock:
                client=self.author
                if message is not None:state['history'].append({'role':'user','content':message})
                current=state['proposal']['world']if state['proposal']else None
                question=state['question'];history=deepcopy(state['history'])
                state['authoring_attempts']+=1;index=state['authoring_attempts']
                self._save(state)
            messages,identity=authoring_messages(question,history,current or examples()[0]['world'])
            _write(self.root/identifier,f'author-{index}.request.json',messages)
            with self._lock:
                state['progress']={'phase':'Constructing players, incentives and rules','attempted_calls':1,
                    'completed_calls':0,'total_calls':1,'completed_worlds':0}
                self._save(state)
            self._authorize_author(client)
            response=client.generate(messages)
            _write(self.root/identifier,f'author-{index}.response.json',response)
            proposal=validate_proposal(response['value'],identity)
            with self._lock:
                state['progress']['completed_calls']=1
                state['proposal']=proposal
                state['history'].append({'role':'assistant','content':proposal['summary']})
                state['status']='draft'if proposal['world']is None or any(q['required']for q in proposal['questions'])else'ready'
                state['progress']['phase']='Review the proposed world'if state['status']=='ready'else'Answer the material questions'
                self._save(state)
        except Exception as error:
            with self._lock:
                state.update(status='failed',error=error.code if isinstance(error,ModelFailure)else'authoring_validation_failed')
                if callable(getattr(error,'safe_details',None)):state['error_details']=error.safe_details()
                state['progress']['phase']='Stopped; no automatic retry';self._save(state)

    def cancel_author(self,identifier,data):
        """Stop after the in-flight author call, without claiming remote cancel."""
        _shape(data,set())
        with self._lock:
            state=self._sessions[identifier]
            if state['status']!='authoring'or not state.get('authoring_plan'):
                raise ValueError('only an active staged author plan can stop between batches')
            state['authoring_cancel_requested']=True
            state['progress']['phase']='Stopping after the active call; remote cancellation or refund is not guaranteed'
            self._save(state)
            return deepcopy(state)

    def _batched_author_call(self,identifier,messages,purpose,author_route):
        from .agent_models import _messages
        _messages(messages)
        with self._lock:
            state=self._sessions[identifier]
            if state['authoring_cancel_requested']:raise ModelFailure('authoring_cancelled','not_dispatched')
            if _route_identity(self.author)!=author_route:raise ValueError('author route changed during staged authoring')
            if state['authoring_attempts']>=state['authoring_plan']['max_calls']:raise ValueError('reviewed authoring budget exhausted')
            index=state['authoring_attempts']+1;root=self.root/identifier
            receipt={'schema_version':'staged-author-call.v1','index':index,'purpose':purpose,
                'status':'dispatching','remote_outcome':'unknown','request_sha256':digest(messages),
                'authoring_plan_sha256':digest(state['authoring_plan']),'route_identity':author_route,
                'model_declared':self.author.model,'automatic_retry':False}
            _write(root,f'author-{index}.request.json',messages)
            _write(root,f'author-{index}.receipt.json',receipt)
            state['authoring_attempts']=index;state['progress']['attempted_calls']+=1
            state['progress']['phase']=purpose;self._save(state)
        client=self.author
        self._authorize_author(client)
        try:response=client.generate(messages)
        except Exception as error:
            receipt.update(status='failed',error=error.code if isinstance(error,ModelFailure)else'author_client_failed',
                remote_outcome=error.remote_outcome if isinstance(error,ModelFailure)else'unknown')
            _write(root,f'author-{index}.receipt.json',receipt,replace=True)
            if isinstance(error,ModelFailure):raise
            raise ModelFailure('author_client_failed','unknown')from None
        _write(root,f'author-{index}.response.json',response)
        receipt.update(status='response_received',remote_outcome='response_received',receipt=deepcopy(response.get('receipt'))if type(response)is dict else None)
        _write(root,f'author-{index}.receipt.json',receipt,replace=True)
        with self._lock:
            state['progress']['completed_calls']+=1;self._save(state)
            if state['authoring_cancel_requested']:raise ModelFailure('authoring_cancelled','response_received')
        return response

    def _author_batched(self,identifier):
        from .batch_authoring import (scaffold_messages,validate_scaffold,profile_batches,batch_messages,
            validate_profiles,merge_proposal,clarification_proposal,required_calls)
        state=self._sessions[identifier];root=self.root/identifier
        try:
            plan=deepcopy(state['authoring_plan']);author_route=_route_identity(self.author)
            with self._lock:
                state['progress']={'phase':'Constructing the frozen world scaffold','attempted_calls':0,
                    'completed_calls':0,'total_calls':required_calls(plan),'completed_worlds':0}
                self._save(state)
            messages,identity=scaffold_messages(state['question'],plan,examples()[0]['world'])
            response=self._batched_author_call(identifier,messages,'Constructing the frozen world scaffold',author_route)
            scaffold=validate_scaffold(response['value'],identity,plan)
            _write(root,'authoring-scaffold.validated.json',scaffold)
            if scaffold['world']is None:proposal=clarification_proposal(scaffold)
            else:
                profiles=[];batches=profile_batches(scaffold)
                for batch_number,assigned in enumerate(batches,1):
                    messages,identity=batch_messages(state['question'],scaffold,assigned)
                    response=self._batched_author_call(identifier,messages,
                        f'Constructing persona batch {batch_number}/{len(batches)} ({len(assigned)} profiles)',author_route)
                    batch=validate_profiles(response['value'],identity,scaffold,assigned)
                    _write(root,f'authoring-batch-{batch_number}.validated.json',batch);profiles.extend(batch)
                proposal=merge_proposal(scaffold,profiles)
                if _preflight_world(proposal['world'],'gemini')>6*1024*1024:
                    raise ValueError('merged world can exceed single-world private session budget')
                _write(root,'authoring-merge.validated.json',proposal)
            with self._lock:
                if state['authoring_cancel_requested']:raise ModelFailure('authoring_cancelled','response_received')
                state['proposal']=proposal;state['history'].append({'role':'assistant','content':proposal['summary']})
                state['status']='draft'if proposal['world']is None or any(q['required']for q in proposal['questions'])else'ready'
                state['progress']['phase']='Review the complete merged cast and frozen rules'if state['status']=='ready'else'Clarification needed; start a new reviewed authoring plan with these answers'
                self._save(state)
        except Exception as error:
            with self._lock:
                state.update(status='failed',error=error.code if isinstance(error,ModelFailure)else'batched_authoring_validation_failed')
                if callable(getattr(error,'safe_details',None)):state['error_details']=error.safe_details()
                state['progress']['phase']='Stopped; partial batches are private, no automatic retry or ready world'
                self._save(state)

    def review(self, identifier, data):
        _shape(data, {'world','actor_route','mode','worlds','seed','max_calls','max_credits'})
        with self._lock:
            state=self._sessions[identifier]
            if state['status'] in ('authoring','running') or self._busy: raise ValueError('idle world required')
            if not state['proposal'] or any(q['required']for q in state['proposal']['questions']):
                raise ValueError('required authoring questions remain')
            world=validate_strategic_world(data['world'])
            _int(data['worlds'],1,4);_int(data['seed'],0,10**9);_int(data['max_calls'],1,MAX_CALLS);_int(data['max_credits'],0,0)
            if data['mode'] not in ('argmax','sample') or data['actor_route'] not in self.actors:
                raise ValueError('configured actor route and declared mode required')
            result_bound=_preflight_world(world,data['actor_route'])
            if result_bound*data['worlds']>6*1024*1024:
                raise ValueError('aggregate private session can exceed artifact budget; reduce world size or count')
            required=len(world['actors'])*world['rounds']*data['worlds']
            estimate=estimate_typesafe_usage(world,data['worlds'])if data['actor_route']=='typesafe'else None
            if required>data['max_calls']: raise ValueError('complete experiment exceeds explicit budget')
            # Identity binds the rules, actual configured route, policy and budget.
            route=self.actors[data['actor_route']]
            from .game_construction import game_construction_summary
            from .strategic_models import DECISION_PROMPT_VERSION
            review={'id':uuid4().hex,'world_sha256':digest(world),'actor_route':data['actor_route'],'model':route.model,
                'route_identity':_route_identity(route),
                'endpoint':getattr(route,'endpoint',None),'protocol':getattr(route,'protocol','antigravity_cli_development'),
                'mode':data['mode'],'worlds':data['worlds'],'seed':data['seed'],'required_calls':required,
                'max_calls':data['max_calls'],'max_credits':0,
                'decision_policy':DECISION_PROMPT_VERSION,'construction_summary':game_construction_summary(world),
                'limitations':list(LIMITATIONS)}
            if estimate:review['typesafe_estimate']=estimate
            if callable(getattr(route,'ensure_budget',None)):
                review['preview_allowance']=route.ensure_budget(required)
            review['sha256']=digest(review)
            state['proposal']['world']=world;state.update(review=review,status='ready',error=None,error_details=None,results=[],summary=None)
            state['game_analysis']=strategic_game(world)
            self._save(state);return deepcopy(state)

    def run(self, identifier, data):
        _shape(data,{'review_sha256','public_input'})
        with self._lock:
            state=self._sessions[identifier];review=state['review']
            if (state['status']!='ready' or review is None or self._busy or
                data['review_sha256']!=review['sha256'] or digest(state['proposal']['world'])!=review['world_sha256']):
                raise ValueError('current unused reviewed world required')
            route=self.actors.get(review['actor_route'])
            if route is None or _route_identity(route)!=review['route_identity']:
                raise ValueError('model route changed since review')
            if type(data['public_input']) is not bool or (review['actor_route']=='gemini' and not data['public_input']):
                raise ValueError('public development input acknowledgment required')
            if callable(getattr(route,'ensure_budget',None)):
                route.ensure_budget(review['required_calls'])
            run_id='run-'+uuid4().hex
            (self.root/identifier/run_id).mkdir(mode=0o700)
            _write(self.root/identifier/run_id,'review.json',review)
            _write(self.root/identifier/run_id,'context.json',{'question':state['question'],'world_sha256':review['world_sha256']})
            _write(self.root/identifier/run_id,'world.json',state['proposal']['world'])
            state.update(status='running',error=None,error_details=None,results=[],summary=None,run_id=run_id)
            state['progress']={'phase':'Loading world','attempted_calls':0,'completed_calls':0,
                'total_calls':review['required_calls'],'completed_worlds':0}
            self._save(state);self._dispatch(self._execute,identifier)
            return deepcopy(state)

    def _summarize(self, state):
        metrics={}
        for metric in state['proposal']['world']['metrics']:
            values=[r['result']['final_metrics'][metric['id']]for r in state['results']]
            metrics[metric['id']]={'label':metric['label'],'unit':metric['unit'],'mean':mean(values)if values else None,
                'median':median(values)if values else None,'min':min(values)if values else None,'max':max(values)if values else None}
        return {'requested_worlds':state['review']['worlds'],'completed_worlds':len(state['results']),
            'metrics':metrics,'probability_meaning':PROBABILITY_MEANING,
            'limitations':['Descriptive statistics over completed conditional model runs only. Failed and unattempted worlds remain in the requested denominator.',
                'A sampling seed controls our action draws, not remote model generation. Repeated argmax runs may be identical.',
                'No sampling frequency is claimed as a calibrated real-world forecast.']}

    def _execute(self, identifier):
        state=self._sessions[identifier];review=deepcopy(state['review'])
        client=self.actors[review['actor_route']]; index=0
        revoked=self._access_revoked;manager=self
        class DispatchGuard:
            def __getattr__(self,name):
                target=getattr(client,name)
                if name not in ('evaluate','generate'):return target
                def dispatch(*args,**kwargs):
                    # Recheck after state/question preparation and file writes,
                    # at the authorization boundary of the provider operation.
                    with manager._lock:
                        if manager._closing.is_set()or revoked.is_set()or manager.actors.get(review['actor_route'])is not client:
                            raise ModelFailure('access_revoked_before_dispatch','not_dispatched')
                    return target(*args,**kwargs)
                return dispatch
        guarded=DispatchGuard()
        path=self.root/identifier/state['run_id']
        try:
            for w in range(review['worlds']):
                engine=StrategicWorld(state['proposal']['world'],seed=review['seed'])
                decisions=[]
                while engine.observations():
                    turns={}
                    for actor,obs in engine.observations().items():
                        if self.actors.get(review['actor_route'])is not client or _route_identity(client)!=review['route_identity']:
                            raise ValueError('model route changed during run')
                        request=decision_request(obs)
                        # Validate state before recording a model dispatch attempt.
                        # There is no silent truncation to fit provider limits.
                        attempted=len(obs['actions'])>1
                        if attempted:
                            if state['progress']['attempted_calls']>=review['max_calls']: raise ValueError('model call cap exceeded')
                            index+=1
                            _write(path,f'call-{index}.request.json',request)
                            with self._lock:
                                state['progress']['attempted_calls']+=1
                                state['progress']['phase']=f"World {w+1}/{review['worlds']} · round {obs['round']} · {actor} deciding"
                                self._save(state)
                        value=decide(guarded,obs,mode=review['mode'],seed=review['seed']+w)
                        if attempted:
                            _write(path,f'call-{index}.response.json',value)
                            with self._lock:
                                state['progress']['completed_calls']+=1;self._save(state)
                        turns[actor]={key:value[key]for key in ('action_id','observation_sha256')}
                        decisions.append(value)
                    engine.advance(turns)
                result=engine.report();replay_strategic_world(result)
                completed={'world_index':w,'result':result,'decisions':decisions}
                _write(path,f'world-{w}.json',completed)
                with self._lock:
                    state['results'].append(completed);state['progress']['completed_worlds']+=1
                    state['summary']=self._summarize(state);self._save(state)
            with self._lock:
                state['status']='completed';state['progress']['phase']='Completed and replay verified'
                state['summary']=self._summarize(state);self._save(state)
                _write(path,'status.json',{'status':state['status'],'error':None})
        except Exception as error:
            with self._lock:
                state['status']='failed';state['error']=error.code if isinstance(error,ModelFailure)else 'strategic_run_validation_failed'
                state['error_details']=error.safe_details()if callable(getattr(error,'safe_details',None))else None
                state['progress']['phase']='Stopped; no automatic retry or fallback'
                state['summary']=self._summarize(state);self._save(state)
                _write(path,'status.json',{'status':state['status'],'error':state['error']})
