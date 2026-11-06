"""Larger casts need explicit sparse visibility, bounded work and unchanged accounting."""
from copy import deepcopy
import json
import time
import pytest
from test_strategic_worlds import world,provenance


def cast(count,rounds=2):
    value=world();base=deepcopy(value['actors'][0]);value['schema_version']='strategic-world.v2'
    value['rounds']=rounds;value['events']=[];value['interactions']=[];value['actors']=[]
    value['description']='A ring of hypothetical builders with independently supplied cash.'
    for i in range(count):
        actor=deepcopy(base);actor.update(id=f'actor-{i}',name=f'Builder {i}',information=f'PRIVATE-{i:03}',
            subscriptions=[f'actor-{(i-1)%count}'])
        value['actors'].append(actor)
    return value


@pytest.mark.parametrize('count',[10,20,100])
def test_sparse_cast_filters_information_settles_and_replays(count):
    from decision_lab.strategic_worlds import StrategicWorld,replay_strategic_world,strategic_game
    value=cast(count);engine=StrategicWorld(value)
    first=engine.observations()['actor-0']
    assert first['population']['actor_count']==count
    assert [a['id']for a in first['opponents']]==[f'actor-{count-1}']
    assert 'PRIVATE-001'not in json.dumps(first)
    while engine.observations():
        obs=engine.observations()
        engine.advance({key:{'action_id':'build'if o['round']==1 else'wait','observation_sha256':o['observation_sha256']}for key,o in obs.items()})
    result=engine.report()
    assert result['total_cost_cents']==60*count
    assert sum(a['cash_cents']for a in result['actor_results'].values())+result['total_cost_cents']==100*count
    second=result['rounds'][1]['observations']['actor-0']
    assert [m['source']for m in second['messages']]==[f'actor-{count-1}']
    assert replay_strategic_world(result)==result
    if count>4:assert strategic_game(value)['status']=='not_computed'


def test_large_dense_graph_and_oversized_cast_are_rejected():
    from decision_lab.strategic_worlds import validate_strategic_world
    value=cast(20);value['actors'][0]['subscriptions']=[f'actor-{i}'for i in range(1,14)]
    with pytest.raises(ValueError):validate_strategic_world(value)
    value=cast(101)
    with pytest.raises(ValueError):validate_strategic_world(value)
    value=cast(100);value['schema_version']='strategic-world.v1'
    with pytest.raises(ValueError):validate_strategic_world(value)
    value=cast(20)
    for actor in value['actors'][1:]:actor['subscriptions']=['actor-0']
    with pytest.raises(ValueError,match='fanout'):validate_strategic_world(value)
    value=cast(20)
    value['interactions']=[{'id':'dense-rule','when':{a['id']:'build'for a in value['actors']},
        'effects':{},'description':'Explicit but unbounded neighborhood','provenance':provenance()}]
    with pytest.raises(ValueError,match='neighborhood'):validate_strategic_world(value)


def test_legacy_engine_hash_replays_only_known_v1_semantics():
    from decision_lab.strategic_worlds import StrategicWorld,replay_strategic_world,LEGACY_ENGINE_SHA256
    engine=StrategicWorld(world());report=engine.report();report['engine_sha256']=next(iter(LEGACY_ENGINE_SHA256))
    assert replay_strategic_world(report)==report
    report['engine_sha256']='0'*64
    with pytest.raises(ValueError):replay_strategic_world(report)
    report=StrategicWorld(cast(20)).report();report['engine_sha256']=next(iter(LEGACY_ENGINE_SHA256))
    with pytest.raises(ValueError):replay_strategic_world(report)


def test_product_executes_100_typed_personas_without_equilibrium_enumeration(tmp_path):
    from decision_lab.product_api import ProductManager
    from decision_lab.jev import TypeSafeClient
    calls=[]
    def wire(**request):
        p=json.loads(request['body']);calls.append(p)
        q=p['questions']['action'];keys=list(q['criteria'])
        return json.dumps({'model':'jev-1.14.0','answers':{'action':{
            'type':'choice','choice':keys[0],'confidence':.8,'probabilities':{key:float(key==keys[0])for key in keys}}},
            'usage':{'input_tokens':100,'output_tokens':0}}).encode()
    manager=ProductManager(tmp_path,actor_clients={'typesafe':TypeSafeClient(api_key='fixture',transport=wire)})
    try:
        boot=manager.bootstrap();assert boot['limits']['max_actors']==100 and boot['limits']['max_calls']>=200
        ex=boot['examples'][0]
        s=manager.create({'mode':'example','example_id':ex['id'],'question':ex['question'],'public_input':False})
        s=manager.review(s['id'],{'world':cast(100),'actor_route':'typesafe','mode':'argmax','worlds':1,'seed':42,'max_calls':200,'max_credits':0})
        assert s['game_analysis']['status']=='not_computed'
        assert s['review']['required_calls']==200
        assert s['review']['typesafe_estimate']['actor_call_ceiling']==200
        assert s['review']['typesafe_estimate']['input_tokens_upper_bound']>200
        assert s['review']['max_credits']==0
        manager.run(s['id'],{'review_sha256':s['review']['sha256'],'public_input':False})
        for _ in range(2000):
            s=manager.snapshot(s['id'])
            if s['status']not in ('running','authoring'):break
            time.sleep(.01)
        assert s['status']=='completed',s.get('error')
        assert len(calls)==200 and len(s['results'])==1
        assert s['summary']['completed_worlds']==1
        assert all(len(p['state']['opponents'])==1 for p in calls)
    finally:manager.close()


def test_native_usage_estimate_scales_with_reviewed_worlds_without_provider_calls(monkeypatch):
    from decision_lab.product_api import estimate_typesafe_usage
    from decision_lab.jev import TypeSafeClient
    def no_dispatch(*args,**kwargs):raise AssertionError('offline estimate must not contact a provider')
    monkeypatch.setattr(TypeSafeClient,'evaluate',no_dispatch)
    one=estimate_typesafe_usage(cast(100),worlds=1)
    two=estimate_typesafe_usage(cast(100),worlds=2)
    assert one['actor_call_ceiling']==200 and two['actor_call_ceiling']==400
    assert two['input_tokens_upper_bound']==2*one['input_tokens_upper_bound']
    assert two['input_cost_upper_estimate_usd']==2*one['input_cost_upper_estimate_usd']
    assert two['includes_authoring']is False and two['estimate_only']is True


def test_native_prompt_estimate_covers_largest_canonical_byte_publication():
    from decision_lab.product_api import _future_observations,estimate_typesafe_usage
    value=cast(2,8)
    for actor in value['actors']:
        actor['actions'][1]['message']='x'*1200
        other=deepcopy(actor['actions'][1]);other.update(id='short-unicode',message='漢'*400)
        actor['actions'].append(other)
    # The native request uses canonical escaped JSON bytes. Seven delivered
    # Unicode publications must be covered even though they use fewer characters.
    for future in _future_observations(value):
        assert len(future['messages'])==7
        assert all(message['text']=='漢'*400 for message in future['messages'])
    unicode_estimate=estimate_typesafe_usage(value)
    for actor in value['actors']:actor['actions'].pop()
    ascii_estimate=estimate_typesafe_usage(value)
    assert unicode_estimate['actor_call_ceiling']==ascii_estimate['actor_call_ceiling']==16
    assert unicode_estimate['input_tokens_upper_bound']>ascii_estimate['input_tokens_upper_bound']


def test_future_byte_budget_accounts_for_json_escaped_message_text():
    from decision_lab.product_api import _future_observations
    value=cast(2,2)
    for actor in value['actors']:
        actor['actions'][1]['message']='"'*600
        other=deepcopy(actor['actions'][1]);other.update(id='plain',message='a'*900)
        actor['actions'].append(other)
    # Provider state is an object: serializing 600 quotes takes more bytes
    # than 900 plain letters. The bound must cover that permitted publication.
    for future in _future_observations(value):
        assert future['messages'][0]['text']=='"'*600
