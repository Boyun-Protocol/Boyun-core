"""Staged authoring freezes resources/rules and never fakes missing profiles."""
from copy import deepcopy
import json
from threading import Event,Thread
import time
import pytest
from test_strategic_scale import cast


def plan(count=100):
    return {'mode':'batched','actor_count':count,'batch_size':20,'max_calls':1+(count+19)//20}


def scaffold(count,identity):
    world=cast(count);roster=[]
    for actor in world.pop('actors'):
        item={k:deepcopy(actor[k])for k in ('id','name','role','initial_cash_cents','utility_weights','subscriptions','provenance')}
        item['actions']=[{k:deepcopy(a[k])for k in ('id','label','cost_cents','effects','provenance')}for a in actor['actions']]
        roster.append(item)
    return {'schema_version':'strategic-scaffold.v1','context_sha256':identity,'summary':'A public hypothetical ring-world scaffold.',
        'questions':[],'world':world,'roster':roster,'total_initial_cash_cents':sum(a['initial_cash_cents']for a in roster),
        'limitations':['Hypothetical profiles and rules, not empirical forecasts.']}


def profiles(data):
    return {'schema_version':'strategic-profile-batch.v1','context_sha256':data['context_sha256'],
        'scaffold_sha256':data['scaffold_sha256'],'profiles':[
            {'id':actor['id'],'motivation':'Preserve resources while evaluating the shared project.',
             'goal':'Use explicit evidence and bounded actions.','information':'Only public hypothetical context is supplied.',
             'actions':[{'id':a['id'],'description':'Wait without spending.'if a['id']=='wait'else'Fund the reviewed limited activity.',
                         'message':''if a['id']=='wait'else'I funded a limited activity.'}for a in actor['actions']]}
            for actor in data['assigned_roster']]}


class Author:
    model='gemini-fixture'
    def __init__(self,count=100,mutate=None,fail_at=None):self.count=count;self.calls=[];self.mutate=mutate;self.fail_at=fail_at
    def generate(self,messages):
        from decision_lab.agent_models import ModelFailure
        self.calls.append(deepcopy(messages));data=json.loads(messages[1]['content'])
        if len(self.calls)==self.fail_at:raise ModelFailure('fixture_transport','unknown')
        value=scaffold(self.count,data['context_sha256'])if data['task']=='construct_scaffold'else profiles(data)
        if self.mutate:self.mutate(value,len(self.calls))
        return {'value':value,'receipt':{'transport':'fixture','model_declared':self.model,'request_attempts':1,'cost_usd':None}}


def wait(manager,identifier):
    for _ in range(1000):
        s=manager.snapshot(identifier)
        if s['status']not in ('authoring','running'):return s
        time.sleep(.01)
    raise AssertionError('author worker did not stop')


def create(manager,count=100):
    return manager.create({'mode':'author','example_id':None,'question':'A fictional project needs a reviewed sparse cast.','public_input':True,'authoring_plan':plan(count)})


def test_100_profiles_generate_in_six_real_interface_calls_with_frozen_merge(tmp_path):
    from decision_lab.product_api import ProductManager
    from decision_lab.strategic_worlds import validate_strategic_world
    author=Author();manager=ProductManager(tmp_path,author_client=author)
    try:
        s=create(manager);s=wait(manager,s['id'])
        assert s['status']=='ready',s
        assert len(author.calls)==6==s['authoring_attempts']==s['progress']['completed_calls']
        world=s['proposal']['world'];validate_strategic_world(world)
        assert len(world['actors'])==100
        assert sum(a['initial_cash_cents']for a in world['actors'])==10000
        assert len({a['id']for a in world['actors']})==100
        for messages in author.calls[1:]:
            data=json.loads(messages[1]['content']);assert len(data['assigned_roster'])==20
            assert 'PRIVATE-000'not in json.dumps(data)
        root=tmp_path/s['id']
        receipts=[json.loads(p.read_text())for p in root.glob('author-*.receipt.json')]
        assert len(receipts)==6 and all(r['status']=='response_received'for r in receipts)
        assert all(p.stat().st_mode&0o777==0o600 for p in root.glob('*.json'))
        assert (root/'authoring-scaffold.validated.json').exists()
        assert (root/'authoring-merge.validated.json').exists()
    finally:manager.close()


@pytest.mark.parametrize('mutate',[
 lambda v,n:v['profiles'].pop()if n==2 else None,
 lambda v,n:v['profiles'][0].update(initial_cash_cents=999999)if n==2 else None,
 lambda v,n:v['profiles'][0]['actions'][1].update(effects={'readiness':1000})if n==2 else None,
 lambda v,n:v.update(scaffold_sha256='0'*64)if n==2 else None,
])
def test_invalid_partial_batch_stops_without_publishing_or_retrying(tmp_path,mutate):
    from decision_lab.product_api import ProductManager
    author=Author(21,mutate=mutate);manager=ProductManager(tmp_path,author_client=author)
    try:
        s=create(manager,21);s=wait(manager,s['id'])
        assert s['status']=='failed'and s['proposal']is None and len(author.calls)==2
        assert not (tmp_path/s['id']/'authoring-merge.validated.json').exists()
        assert (tmp_path/s['id']/'author-2.response.json').exists()
    finally:manager.close()


def test_budget_and_public_confirmation_are_checked_before_dispatch(tmp_path):
    from decision_lab.product_api import ProductManager
    author=Author();manager=ProductManager(tmp_path,author_client=author)
    data={'mode':'author','example_id':None,'question':'A fictional project','public_input':True,'authoring_plan':plan()}
    try:
        for invalid in ({**plan(),'max_calls':5},{**plan(),'batch_size':100},{**plan(),'actor_count':101}):
            with pytest.raises(ValueError):manager.create({**data,'authoring_plan':invalid})
        with pytest.raises(ValueError):manager.create({**data,'public_input':False})
        assert not author.calls and not list(tmp_path.iterdir())
    finally:manager.close()


def test_failed_inflight_call_has_uncertain_receipt_and_restart_never_redispatches(tmp_path):
    from decision_lab.product_api import ProductManager
    author=Author(21,fail_at=2);manager=ProductManager(tmp_path,author_client=author)
    s=create(manager,21);s=wait(manager,s['id']);manager.close()
    assert s['status']=='failed'and s['progress']['attempted_calls']==2
    marker=json.loads((tmp_path/s['id']/'author-2.receipt.json').read_text())
    assert marker['status']=='failed'and marker['remote_outcome']=='unknown'
    restarted=ProductManager(tmp_path,author_client=author)
    try:
        assert restarted.snapshot(s['id'])['status']=='failed'and len(author.calls)==2
        with pytest.raises(ValueError):restarted.say(s['id'],{'message':'Try again','public_input':True})
        assert len(author.calls)==2
    finally:restarted.close()


def test_cancellation_preserves_inflight_response_and_stops_before_next_batch(tmp_path):
    from decision_lab.product_api import ProductManager
    entered=Event();release=Event()
    class Blocking(Author):
        def generate(self,messages):
            if len(self.calls)==1:entered.set();assert release.wait(3)
            return super().generate(messages)
    author=Blocking(21);manager=ProductManager(tmp_path,author_client=author)
    try:
        s=create(manager,21);assert entered.wait(3)
        manager.cancel_author(s['id'],{})
        release.set();s=wait(manager,s['id'])
        assert s['status']=='failed'and s['error']=='authoring_cancelled'
        assert len(author.calls)==2 and (tmp_path/s['id']/'author-2.response.json').exists()
        assert not (tmp_path/s['id']/'author-3.request.json').exists()
    finally:release.set();manager.close()


def test_reviewed_creator_capital_is_checked_before_profile_dispatch(tmp_path):
    from decision_lab.product_api import ProductManager
    author=Author(21);manager=ProductManager(tmp_path,author_client=author)
    try:
        data={'mode':'author','example_id':None,'question':'Creator has $10,000.','public_input':True,
            'authoring_plan':{**plan(21),'creator_capital_cents':1000000}}
        s=manager.create(data);s=wait(manager,s['id'])
        assert s['status']=='failed'and s['proposal']is None and len(author.calls)==1
    finally:manager.close()


def test_request_or_uncertain_marker_write_failure_prevents_network_call(tmp_path,monkeypatch):
    from decision_lab import product_api
    original=product_api._write;author=Author(21)
    def fail(root,name,value,**kwargs):
        if name.endswith('.receipt.json'):raise OSError('PRIVATE storage detail')
        return original(root,name,value,**kwargs)
    monkeypatch.setattr(product_api,'_write',fail)
    manager=product_api.ProductManager(tmp_path,author_client=author)
    try:
        s=create(manager,21);s=wait(manager,s['id'])
        assert s['status']=='failed'and not author.calls
        assert 'PRIVATE'not in json.dumps(s)
    finally:manager.close()


def test_missing_information_stops_after_scaffold_without_fake_profiles(tmp_path):
    from decision_lab.product_api import ProductManager
    def missing(value,index):
        if index==1:value.update(world=None,roster=[],total_initial_cash_cents=0,
            questions=[{'id':'goal','prompt':'Which goal?', 'choices':['Learn','Reach'],'required':True}])
    author=Author(21,mutate=missing);manager=ProductManager(tmp_path,author_client=author)
    try:
        s=create(manager,21);s=wait(manager,s['id'])
        assert s['status']=='draft'and s['proposal']['world']is None and len(author.calls)==1
        assert s['proposal']['questions'][0]['id']=='goal'
        assert not (tmp_path/s['id']/'authoring-merge.validated.json').exists()
    finally:manager.close()


def test_completed_batch_cannot_be_used_when_later_batch_fails(tmp_path):
    from decision_lab.product_api import ProductManager
    author=Author(21,fail_at=3);manager=ProductManager(tmp_path,author_client=author)
    try:
        s=create(manager,21);s=wait(manager,s['id'])
        assert s['status']=='failed'and s['proposal']is None and len(author.calls)==3
        partial=json.loads((tmp_path/s['id']/'authoring-batch-1.validated.json').read_text())
        assert len(partial)==20
        assert not (tmp_path/s['id']/'authoring-merge.validated.json').exists()
    finally:manager.close()


def test_merge_revalidates_exact_frozen_actions_without_zip_truncation():
    from decision_lab.batch_authoring import merge_proposal
    s=scaffold(2,'context')
    # Add an unreferenced third action; dropping it must not silently make the
    # remaining two-action world look valid.
    for slot in s['roster']:
        third=deepcopy(slot['actions'][1]);third['id']='other';slot['actions'].append(third)
    data={'context_sha256':'batch','scaffold_sha256':'hash','assigned_roster':s['roster']}
    p=profiles(data)['profiles']
    for profile in p:profile['actions'].pop()
    with pytest.raises(ValueError):merge_proposal(s,p)


def test_shutdown_waits_for_active_call_but_does_not_start_another_batch(tmp_path):
    from decision_lab.product_api import ProductManager
    entered=Event();release=Event()
    class Blocking(Author):
        def generate(self,messages):
            if len(self.calls)==1:entered.set();assert release.wait(3)
            return super().generate(messages)
    author=Blocking(21);manager=ProductManager(tmp_path,author_client=author);closed=None
    try:
        s=create(manager,21);assert entered.wait(3)
        closed=Thread(target=manager.close);closed.start()
        for _ in range(100):
            if manager.snapshot(s['id'])['authoring_cancel_requested']:break
            time.sleep(.005)
        assert manager.snapshot(s['id'])['authoring_cancel_requested']is True
        release.set();closed.join(3)
        assert not closed.is_alive()
        assert manager.snapshot(s['id'])['status']=='failed'and len(author.calls)==2
    finally:
        release.set()
        if closed:closed.join(3)
        else:manager.close()
