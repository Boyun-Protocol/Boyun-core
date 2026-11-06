"""A preview allowance bounds repeated operator-funded dispatch, not billing."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest
from decision_lab.agent_models import ModelFailure


class Client:
    model='jev-latest'
    retry_after_seconds=0
    calls=0
    def evaluate(self,**kwargs):
        self.calls+=1
        return {'ok':True}
    def get_models(self):return {'models':[{'id':'jev-latest'}]}


def question():
    return {'action':{'type':'choice','instructions':'Choose a permitted action.',
                     'criteria':{'wait':'Wait.','review':'Review.'}}}


def wrap(tmp_path,limit=3,client=None):
    from decision_lab.preview_budget import PreviewJevClient
    return PreviewJevClient(client or Client(),root=tmp_path/'budget',call_limit=limit)


def test_allowance_is_persistent_and_free_checks_do_not_consume_it(tmp_path):
    client=Client();wrapped=wrap(tmp_path,2,client)
    assert wrapped.budget_status()['remaining_calls']==2
    assert wrapped.get_models()['models']==[{'id':'jev-latest'}]
    wrapped.evaluate(state='public fictional state',questions=question())
    assert client.calls==1
    restored=wrap(tmp_path,2,Client())
    assert restored.budget_status()['remaining_calls']==1
    restored.evaluate(state='public fictional state',questions=question())
    with pytest.raises(ModelFailure,match='preview_typesafe_allowance_exhausted'):
        restored.evaluate(state='public fictional state',questions=question())
    assert restored.client.calls==1
    assert (tmp_path/'budget'/'allowance.json').stat().st_mode&0o777==0o600


def test_each_valid_request_reserves_one_call_regardless_of_state_size(tmp_path):
    wrapped=wrap(tmp_path,2)
    wrapped.evaluate(state='x'*8001,questions=question())
    assert wrapped.budget_status()['reserved_calls']==1
    with pytest.raises(ValueError):wrapped.evaluate(state='x'*48001,questions=question())
    assert wrapped.budget_status()['reserved_calls']==1 and wrapped.client.calls==1


def test_unknown_provider_failure_keeps_reservation_and_does_not_retry(tmp_path):
    class Broken(Client):
        def evaluate(self,**kwargs):
            self.calls+=1;raise ModelFailure('typesafe_transport','unknown')
    wrapped=wrap(tmp_path,1,Broken())
    with pytest.raises(ModelFailure):wrapped.evaluate(state='public',questions=question())
    assert wrapped.client.calls==1 and wrapped.budget_status()['remaining_calls']==0


def test_parallel_reservations_do_not_overspend(tmp_path):
    clients=[wrap(tmp_path,5)for _ in range(3)]
    wrapped=clients[0]
    def attempt(index):
        try:clients[index%len(clients)].evaluate(state='public',questions=question());return 1
        except (ValueError,ModelFailure):return 0
    with ThreadPoolExecutor(max_workers=8)as pool:results=list(pool.map(attempt,range(25)))
    status=wrapped.budget_status()
    assert 0<sum(results)<=5 and sum(c.client.calls for c in clients)==sum(results)
    assert status['reserved_calls']==sum(results)


@pytest.mark.parametrize('kind',['corrupt','symlink','permissions'])
def test_unsafe_or_corrupt_allowance_fails_closed(tmp_path,kind):
    wrapped=wrap(tmp_path)
    target=tmp_path/'budget'/'allowance.json'
    if kind=='corrupt':target.write_text('{')
    elif kind=='permissions':target.chmod(0o644)
    else:
        target.unlink();target.symlink_to(tmp_path/'other')
    with pytest.raises((OSError,ValueError)):
        wrapped.evaluate(state='public',questions=question())
    assert wrapped.client.calls==0


@pytest.mark.parametrize('limit',[0,-1,True,100001])
def test_allowance_requires_a_bounded_explicit_integer(tmp_path,limit):
    with pytest.raises(ValueError):wrap(tmp_path,limit)


def test_review_rechecks_allowance_at_run_and_real_typed_worker_replays(tmp_path):
    import json,time
    from decision_lab.jev import TypeSafeClient
    from decision_lab.product_api import ProductManager,estimate_typesafe_usage
    from decision_lab.strategic_worlds import replay_strategic_world
    calls=[]
    def wire(**request):
        payload=json.loads(request['body']);calls.append(payload)
        options=list(payload['questions']['action']['criteria'])
        return json.dumps({'model':'jev-1.14.0',
            'answers':{'action':{'type':'choice','choice':options[0],'confidence':1,
                'probabilities':{key:float(key==options[0])for key in options}}},
            'usage':{'input_tokens':100,'output_tokens':0}}).encode()
    from decision_lab.preview_budget import PreviewJevClient
    station=TypeSafeClient(api_key='FIXTURE_SECRET',model='jev-latest',transport=wire)
    # Deliberately allow one small run and test that a later review cannot bypass it.
    manager=ProductManager(tmp_path/'product')
    ex=manager.bootstrap()['examples'][0]
    world=ex['world'];ceiling=estimate_typesafe_usage(world)['actor_call_ceiling']
    wrapped=PreviewJevClient(station,root=tmp_path/'budget',call_limit=ceiling)
    manager.actors={'typesafe':wrapped}
    def review(s):return manager.review(s['id'],{'world':s['proposal']['world'],'actor_route':'typesafe',
        'mode':'argmax','worlds':1,'seed':42,'max_calls':800,'max_credits':0})
    try:
        state=manager.create({'mode':'example','example_id':ex['id'],'question':ex['question'],'public_input':False})
        state=review(state)
        assert state['review']['preview_allowance']['remaining_calls']==ceiling
        manager.run(state['id'],{'review_sha256':state['review']['sha256'],'public_input':False})
        for _ in range(300):
            state=manager.snapshot(state['id'])
            if state['status']!='running':break
            time.sleep(.01)
        assert state['status']=='completed',state
        report=state['results'][0]['result']
        assert replay_strategic_world(report)==report
        assert len(calls)==state['progress']['completed_calls']>0
        assert 'FIXTURE_SECRET'not in json.dumps(state)
        # Exhaust any conservative slack to model another authorized caller.
        while wrapped.budget_status()['remaining_calls']:
            wrapped.evaluate(state='public',questions=question())
        count=len(calls)
        with pytest.raises(ModelFailure):review(state)
        assert len(calls)==count
    finally:manager.close()


def test_reservation_write_failure_does_not_dispatch(tmp_path,monkeypatch):
    import decision_lab.preview_budget as module
    wrapped=wrap(tmp_path,3)
    def fail(*args,**kwargs):raise OSError('disk unavailable')
    monkeypatch.setattr(module,'_write',fail)
    with pytest.raises(OSError):wrapped.evaluate(state='public',questions=question())
    assert wrapped.client.calls==0


def test_invalid_input_and_client_cooldown_do_not_reserve(tmp_path):
    from decision_lab.jev import TypeSafeError
    wrapped=wrap(tmp_path,3)
    with pytest.raises(ValueError):wrapped.evaluate(state='public',questions={})
    wrapped.client.retry_after_seconds=30
    with pytest.raises(ModelFailure):wrapped.evaluate(state='public',questions=question())
    assert wrapped.budget_status()['reserved_calls']==0 and wrapped.client.calls==0


def test_approved_run_rechecks_allowance_before_creating_run_artifacts(tmp_path):
    from decision_lab.product_api import ProductManager,estimate_typesafe_usage
    from decision_lab.preview_budget import PreviewJevClient
    manager=ProductManager(tmp_path/'product')
    try:
        ex=manager.bootstrap()['examples'][0]
        ceiling=estimate_typesafe_usage(ex['world'])['actor_call_ceiling']
        wrapped=PreviewJevClient(Client(),root=tmp_path/'budget',call_limit=ceiling)
        manager.actors={'typesafe':wrapped}
        state=manager.create({'mode':'example','example_id':ex['id'],'question':ex['question'],'public_input':False})
        state=manager.review(state['id'],{'world':state['proposal']['world'],'actor_route':'typesafe',
            'mode':'argmax','worlds':1,'seed':42,'max_calls':800,'max_credits':0})
        wrapped.evaluate(state='another authorized request',questions=question())
        with pytest.raises(ModelFailure):manager.run(state['id'],{'review_sha256':state['review']['sha256'],'public_input':False})
        assert manager.snapshot(state['id'])['status']=='ready'
        assert not list((manager.root/state['id']).glob('run-*'))
        assert wrapped.client.calls==1
    finally:manager.close()


def test_old_credit_allowance_cannot_be_reinterpreted_as_native_calls(tmp_path):
    import json
    wrapped=wrap(tmp_path)
    (tmp_path/'budget'/'allowance.json').write_text(json.dumps({'schema_version':'preview-allowance.v1','reserved_credits':0}))
    with pytest.raises(ValueError):wrap(tmp_path)
    assert wrapped.client.calls==0


class Author:
    """Text client standing in for the operator-funded author route."""
    model='gemini-author-fixture'
    def __init__(self):self.calls=[]
    def generate(self,messages):
        self.calls.append(messages)
        return {'value':{'choice':'wait','confidence':.8,
                'probabilities':{'wait':1.0,'review':0.0},'reason':'Keep resources.'},
                'receipt':{'transport':'test_fixture'}}
    def get_models(self):return {'models':[{'id':self.model}]}


class DecisionAuthor(Author):
    """Answers in the Jev-compatible shape GeminiDecisions validates."""
    def generate(self,messages):
        self.calls.append(messages)
        return {'value':{'answers':{'action':{'type':'choice','choice':'wait','confidence':1.0,
                'probabilities':{'wait':1.0,'review':0.0}}}},'receipt':{'transport':'test_fixture'}}


def wrap_author(tmp_path,client,limit=3):
    from decision_lab.preview_budget import PreviewAuthorClient
    return PreviewAuthorClient(client,root=tmp_path/'author-budget',call_limit=limit)


def test_author_generation_reserves_one_call_and_persists(tmp_path):
    author=Author();wrapped=wrap_author(tmp_path,author,2)
    messages=[{'role':'system','content':'contract'},{'role':'user','content':'{}'}]
    wrapped.generate(messages)
    assert len(author.calls)==1
    assert wrapped.budget_status()['reserved_calls']==1
    restored=wrap_author(tmp_path,Author(),2)
    assert restored.budget_status()['remaining_calls']==1
    assert (tmp_path/'author-budget'/'allowance.json').stat().st_mode&0o777==0o600


def test_author_allowance_exhaustion_never_dispatches(tmp_path):
    author=Author();wrapped=wrap_author(tmp_path,author,1)
    messages=[{'role':'system','content':'contract'},{'role':'user','content':'{}'}]
    wrapped.generate(messages)
    with pytest.raises(ModelFailure,match='preview_author_allowance_exhausted') as failure:
        wrapped.generate(messages)
    assert len(author.calls)==1
    assert failure.value.remote_outcome=='not_dispatched'
    assert failure.value.safe_details()['automatic_retry']is False


def test_author_allowance_frees_catalog_checks_but_not_generation(tmp_path):
    author=Author();wrapped=wrap_author(tmp_path,author,1)
    assert wrapped.get_models()['models']==[{'id':'gemini-author-fixture'}]
    assert wrapped.budget_status()['reserved_calls']==0
    wrapped.generate([{'role':'system','content':'c'},{'role':'user','content':'{}'}])
    assert wrapped.budget_status()['reserved_calls']==1


def test_author_and_jev_counters_are_separate(tmp_path):
    client=Client();jev=wrap(tmp_path,1,client)
    author=Author();wrapped=wrap_author(tmp_path,author,1)
    wrapped.generate([{'role':'system','content':'c'},{'role':'user','content':'{}'}])
    assert wrapped.budget_status()['reserved_calls']==1
    assert jev.budget_status()['reserved_calls']==0
    jev.evaluate(state='public fictional state',questions=question())
    assert client.calls==1 and len(author.calls)==1


def test_jev_allowance_file_cannot_be_read_as_an_author_one(tmp_path):
    """Each route has its own schema, so a counter cannot be carried across."""
    import json
    wrap_author(tmp_path,Author(),1)
    text=(tmp_path/'author-budget'/'allowance.json').read_text()
    (tmp_path/'budget').mkdir()
    (tmp_path/'budget'/'allowance.json').write_text(text)
    with pytest.raises(ValueError):
        from decision_lab.preview_budget import PreviewJevClient
        PreviewJevClient(Client(),root=tmp_path/'budget',call_limit=1)


def test_gemini_decisions_draw_on_the_author_allowance(tmp_path):
    from decision_lab.gemini_decisions import GeminiDecisions
    author=DecisionAuthor();wrapped=wrap_author(tmp_path,author,1)
    actor=GeminiDecisions(wrapped)
    actor.evaluate(state='public fictional state',questions=question())
    assert len(author.calls)==1
    assert wrapped.budget_status()['reserved_calls']==1
    with pytest.raises(ModelFailure,match='preview_author_allowance_exhausted'):
        actor.evaluate(state='public fictional state',questions=question())
    assert len(author.calls)==1


def test_parallel_author_reservations_do_not_overspend(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    author=Author();wrapped=wrap_author(tmp_path,author,5)
    messages=[{'role':'system','content':'c'},{'role':'user','content':'{}'}]
    def call():
        try:wrapped.generate(messages);return 1
        except ModelFailure:return 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        results=list(pool.map(lambda _:call(),range(8)))
    assert sum(results)==5 and len(author.calls)==5
    assert wrapped.budget_status()['reserved_calls']==5


def test_product_authoring_consumes_the_operator_author_allowance(tmp_path):
    """The gap this closes: authoring dispatched straight through the raw client."""
    import json
    from decision_lab.product_api import ProductManager
    from decision_lab.preview_budget import PreviewAuthorClient

    class ClarifyingAuthor:
        model='gemini-author-fixture'
        def __init__(self):self.calls=[]
        def generate(self,messages):
            self.calls.append(messages);data=json.loads(messages[1]['content'])
            return {'value':{'schema_version':'strategic-proposal.v1','context_sha256':data['context_sha256'],
                'summary':'Need objective','questions':[{'id':'goal','prompt':'Goal?','choices':['Reach','Runway'],'required':True}],
                'world':None,'limitations':['Insufficient detail']},'receipt':{'transport':'test_fixture'}}

    author=ClarifyingAuthor()
    wrapped=PreviewAuthorClient(author,root=tmp_path/'author-budget',call_limit=2)
    manager=ProductManager(tmp_path/'product',author_client=wrapped)
    try:
        def author_once():
            from time import sleep
            state=manager.create({'mode':'author','example_id':None,'question':'Choose a ticker','public_input':True})
            for _ in range(300):
                state=manager.snapshot(state['id'])
                if state['status']!='authoring':break
                sleep(.01)
            return state
        assert author_once()['status']=='draft'
        assert wrapped.budget_status()['reserved_calls']==1
        assert author_once()['status']=='draft'
        assert wrapped.budget_status()['reserved_calls']==2
        # Exhausted allowance must fail the session without reaching the provider.
        assert author_once()['status']=='failed'
        assert author_once()['error']=='preview_author_allowance_exhausted'
        assert len(author.calls)==2
    finally:manager.close()
