from copy import deepcopy
import json
import pytest
from decision_lab import jev
from decision_lab.agent_models import ModelFailure
from decision_lab.agent_worlds import AgentWorld,replay_agent_world
from test_agent_worlds import spec


def response(payload,choice='hold',confidence=.9):
    answers={}
    for key,q in payload['questions'].items():
        if q['type']=='noul':answers[key]={'type':'noul','noul':.7}
        else:
            selected=choice if key=='action' else 'silent'
            if selected not in q['criteria']:selected=next(iter(q['criteria']))
            answers[key]={'type':'choice','choice':selected,'confidence':confidence,
                'probabilities':{k:1.0 if k==selected else 0.0 for k in q['criteria']}}
    return {'model':'jev-1.14.0','answers':answers,'usage':{'input_tokens':1000,'output_tokens':20}}


class Transport:
    def __init__(self,choice='hold',confidence=.9,mutate=None):self.calls=[];self.choice=choice;self.confidence=confidence;self.mutate=mutate
    def __call__(self,**kwargs):
        self.calls.append(kwargs)
        payload=json.loads(kwargs['body']);r=response(payload,self.choice,self.confidence)
        if self.mutate:self.mutate(r)
        return json.dumps(r).encode()


def client(transport):return jev.TypeSafeClient(model='jev-1.14.0',endpoint='https://api.typesafe.ai/v1/systemone',api_key='test-private-key',transport=transport)


def obs():return AgentWorld(spec()).observations()['whale']


def test_native_systemone_wire_receipt_and_no_key_in_artifacts():
    transport=Transport();c=client(transport)
    payload={'context':'Explicit fictional case.'}
    result=c.evaluate(state=payload,questions={'action':{'type':'choice','instructions':'Choose','criteria':{'hold':'Hold','buy':'Buy'}},'relevant':{'type':'noul','instructions':'Is it relevant?'}})
    assert len(transport.calls)==1
    call=transport.calls[0];body=json.loads(call['body'])
    assert body=={'model':'jev-1.14.0','state':payload,'questions':{'action':{'type':'choice','instructions':'Choose','criteria':{'hold':'Hold','buy':'Buy'}},'relevant':{'type':'noul','instructions':'Is it relevant?'}}}
    assert call['headers']['Authorization']=='Bearer test-private-key'
    assert result['answers']['action']['choice']=='hold'
    assert result['receipt']['model_reported']=='jev-1.14.0'
    assert result['receipt']['input_cost_estimate_usd']==.000042
    assert result['receipt']['cost_usd'] is None
    assert 'test-private-key'not in json.dumps(result)


@pytest.mark.parametrize('mutate',[
 lambda r:r['answers']['action']['probabilities'].update(hold=.5),
 lambda r:r['answers']['action'].update(choice='steal'),
 lambda r:r['answers']['action'].update(confidence=True),
 lambda r:r['answers']['action']['probabilities'].update(hold=float('nan')),
 lambda r:r.update(model='not-jev'),
 lambda r:r['answers'].update(extra={'type':'noul','noul':.1}),
 lambda r:r['usage'].update(input_tokens=-1),
])
def test_malformed_structured_probabilities_fail_closed_without_retry(mutate):
    transport=Transport(mutate=mutate)
    with pytest.raises(ModelFailure):client(transport).evaluate(state='test',questions={'action':{'type':'choice','instructions':'Choose','criteria':{'hold':'Wait','buy':'Buy'}}})
    assert len(transport.calls)==1


def test_wrong_endpoint_or_request_rejected_before_dispatch():
    transport=Transport()
    with pytest.raises(ValueError):jev.TypeSafeClient(model='jev-1.14.0',endpoint='http://remote.test/v1/systemone',api_key='a')
    with pytest.raises(ValueError):client(transport).evaluate(state='x',questions={'bad':{'type':'chat','instructions':'invent'}})
    assert not transport.calls


def test_actor_menu_uses_only_own_affordable_actions_and_bound_observation():
    observation=obs();before=deepcopy(observation)
    request=jev.prepare_actor_request(observation)
    assert observation==before
    assert request['observation_sha256']==observation['observation_sha256']
    menu=request['actions']
    assert menu['hold']['amount']==0
    for action in menu.values():
        if action['kind']=='buy':
            assert action['amount']<=observation['balance']['cash_cents']
            assert action['amount']<=observation['actor']['position_limit_cents']-observation['cost_basis_cents']
            assert action['evidence_ids']
        if action['kind']=='sell':assert action['amount']<=observation['balance']['token_units']
    missing=deepcopy(observation);missing['messages']=[];missing['new_message_ids']=[];missing.pop('observation_sha256')
    from decision_lab.agent_worlds import digest
    missing['observation_sha256']=digest(missing)
    assert set(jev.prepare_actor_request(missing)['actions'])=={'hold'}


def test_jev_choice_executes_in_actual_ledger_and_replays():
    world=spec();engine=AgentWorld(world);transport=Transport(choice='buy_10000bps')
    adapter=jev.JevActorModel(client=client(transport))
    from decision_lab.agent_orchestration import turn_messages
    turns=[adapter.generate(turn_messages(o))['value']for o in engine.observations().values()]
    engine.advance(turns)
    report=engine.report()
    assert any(x['status']=='executed'and x['kind']=='buy' for x in report['settlements'])
    assert report['initial_totals']==report['ending_totals']
    assert replay_agent_world(report)==report
    assert len(transport.calls)==len(world['agents'])


def test_low_confidence_abstention_is_explicit_and_not_a_hidden_model_retry():
    transport=Transport(choice='buy_10000bps',confidence=.1)
    adapter=jev.JevActorModel(client=client(transport),min_confidence=.6)
    from decision_lab.agent_orchestration import turn_messages
    result=adapter.generate(turn_messages(obs()))
    assert result['value']['action']['kind']=='hold'
    assert result['receipt']['decision_policy']['action_abstained'] is True
    assert len(transport.calls)==1
    assert 'real_world_event_probability'not in result['receipt']


def test_jev_never_authors_worlds_or_fake_free_text_and_rejects_tampered_observation():
    transport=Transport();adapter=jev.JevActorModel(client=client(transport))
    from decision_lab.agent_orchestration import construction_messages
    from test_agent_orchestration import brief
    with pytest.raises(ValueError):adapter.generate(construction_messages(brief()))
    observation=obs();observation['balance']['cash_cents']+=1
    with pytest.raises(ValueError):jev.prepare_actor_request(observation)
    assert not transport.calls


def test_transport_failure_is_one_uncertain_attempt_without_secret():
    calls=[]
    def broken(**kwargs):calls.append(kwargs);raise RuntimeError('SECRET internal error')
    with pytest.raises(ModelFailure)as error:client(broken).evaluate(state='x',questions={'x':{'type':'noul','instructions':'true?'}})
    assert len(calls)==1 and error.value.remote_outcome=='unknown' and 'SECRET'not in str(error.value)


def test_jev_templates_become_real_next_round_messages_with_original_citations():
    world=spec();engine=AgentWorld(world)
    def publish_bullish(r):
        if 'communication'in r['answers']:
            a=r['answers']['communication'];a['choice']='bullish';a['probabilities']={k:1.0 if k=='bullish'else 0.0 for k in a['probabilities']}
    transport=Transport(mutate=publish_bullish);adapter=jev.JevActorModel(client=client(transport))
    from decision_lab.agent_orchestration import turn_messages
    engine.advance([adapter.generate(turn_messages(o))['value']for o in engine.observations().values()])
    retail=engine.observations()['retail']
    assert any(m['id']=='agent:1:analyst'and m['stance']=='bullish' for m in retail['messages'])
    analyst=next(m for m in retail['messages']if m['source']=='analyst')
    assert analyst['citations']==['event:launch-update']
    assert 'unverified agent opinion'in analyst['text']


def test_equal_probability_ties_are_valid_but_low_probability_selected_choice_is_not():
    def tie(r):r['answers']['action']['probabilities']={'hold':.5,'buy':.5}
    transport=Transport(mutate=tie)
    assert client(transport).evaluate(state='x',questions={'action':{'type':'choice','instructions':'choose','criteria':{'hold':'Hold','buy':'Buy'}}})['answers']['action']['choice']=='hold'
    def wrong(r):r['answers']['action']['probabilities']={'hold':.1,'buy':.9}
    with pytest.raises(ModelFailure):client(Transport(mutate=wrong)).evaluate(state='x',questions={'action':{'type':'choice','instructions':'choose','criteria':{'hold':'Hold','buy':'Buy'}}})


def test_state_cap_and_alias_pin_are_explicit():
    transport=Transport()
    with pytest.raises(ValueError):client(transport).evaluate(state='x'*(jev.MAX_STATE_BYTES+1),questions={'x':{'type':'noul','instructions':'True?'}})
    assert not transport.calls
    def wrong_version(r):r['model']='jev-1.13.0'
    with pytest.raises(ModelFailure):client(Transport(mutate=wrong_version)).evaluate(state='x',questions={'x':{'type':'noul','instructions':'True?'}})


def test_native_injected_http_settlement_and_replay_is_fixture_not_live_jev(tmp_path):
    from decision_lab.agent_orchestration import run_live
    wire=Transport(choice='buy_10000bps')
    c=jev.TypeSafeClient(model='jev-1.14.0',api_key='fixture-test-key',transport=wire)
    manifest=run_live(world=spec(),client=jev.JevActorModel(client=c),output_dir=tmp_path/'run',max_calls=6)
    assert manifest['status']=='completed' and len(wire.calls)==6
    assert all(call['endpoint']=='https://api.typesafe.ai/v1/systemone' and call['method']=='POST' for call in wire.calls)
    report=json.loads((tmp_path/'run/result.json').read_text())
    assert replay_agent_world(report)==report
    assert any(s['status']=='executed' and s['kind']=='buy' for s in report['settlements'])
    assert all('fixture-test-key' not in p.read_text() for p in (tmp_path/'run').glob('*.json'))


def test_jev_accepts_valid_observed_cash_above_initial_actor_cap_without_raising_action_cap():
    from test_agent_worlds import proposal
    world=spec();world['rounds']=3;world['agents']=world['agents'][:2]
    for a in world['agents']:
        a['initial_cash_cents']=10**12;a['position_limit_cents']=10**12
        a['allowed_actions']=['hold','buy','sell','publish'];a['subscriptions']=['news']
    engine=AgentWorld(world)
    engine.advance([proposal(o,kind='buy'if a=='analyst'else'hold',amount=10**11 if a=='analyst'else 0)for a,o in engine.observations().items()])
    engine.advance([proposal(o,kind='buy'if a=='retail'else'hold',amount=10**12 if a=='retail'else 0)for a,o in engine.observations().items()])
    observations=engine.observations()
    assert observations['analyst']['public_market']['cash_cents']>10**12
    prepared=jev.prepare_actor_request(observations['analyst'])
    for action in prepared['actions'].values():assert action['amount']<=10**12
