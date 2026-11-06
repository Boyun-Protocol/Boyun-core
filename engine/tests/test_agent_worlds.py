"""Data-only live-agent execution contracts, injected decisions never inference."""
from copy import deepcopy
import pytest
from decision_lab.agent_worlds import AgentWorld, validate_agent_world, replay_agent_world


def spec():
    return {'schema_version':'agent-world.v1','id':'public-network','event_description':'Fictional NEAR launch','network':'near','rounds':2,
      'market':{'project_capital_cents':1000000,'launch_cost_cents':100000,'lp_cash_cents':400000,'project_token_units':3000000,'lp_token_units':1000000,'fee_bps':30,'max_slippage_bps':500},
      'agents':[{'id':actor,'name':actor.title(),'role':role,'description':'Explicit fictional role','goal':'Use personally observed evidence','initial_cash_cents':cash,'position_limit_cents':cash,'allowed_actions':actions,'attention_capacity':8,'subscriptions':sources}
        for actor,role,cash,actions,sources in [('analyst','analyst',0,['hold','publish'],['news','whale']),('retail','retail',50000,['hold','buy','sell','publish'],['analyst']),('whale','large_holder',200000,['hold','buy','sell','publish'],['news','analyst'])]],
      'events':[{'id':'launch-update','round':1,'text':'Fictional pool is open. This does not guarantee buyers.','provenance':'assumed public pilot event'},{'id':'future-secret','round':2,'text':'Later event','provenance':'assumed'}],
      'assumptions':['Synthetic balances and venue; not real market odds.']}


def proposal(obs,kind='hold',amount=0,text=None):
    citations=[m['id'] for m in obs['messages']][:1]
    return {'schema_version':'agent-turn.v1','actor_id':obs['actor']['id'],'round':obs['round'],'observation_sha256':obs['observation_sha256'],
      'action':{'kind':kind,'amount':amount,'evidence_ids':citations},'message':None if text is None else {'text':text,'stance':'uncertain','citations':citations},'reason':'Supplied test decision'}


def test_peer_delivery_and_private_information_boundary():
    w=AgentWorld(spec(),seed=42);views=w.observations()
    assert views['retail']['messages']==[]
    assert 'future-secret' not in str(views)
    assert '200000' not in str(views['retail'])
    decisions=[proposal(o,text='Question from '+actor)for actor,o in views.items()]
    decisions[0]=proposal(views['analyst'],text='Public analyst message')
    w.advance(decisions);second=w.observations()
    delivered=second['retail']['messages']
    assert any(m['text']=='Public analyst message' and m['source']=='analyst'for m in delivered)
    assert all(m['source']=='analyst'for m in delivered)
    assert all(m['published_round']<2 for m in delivered)


def test_trades_settle_and_replay_exactly_with_conservation():
    w=AgentWorld(spec(),seed=42);views=w.observations()
    w.advance([proposal(o,kind='buy' if actor=='whale'else'hold',amount=10000 if actor=='whale'else 0,text='Observed update')for actor,o in views.items()])
    first=w.report();assert first['settlements'][0]['round']==1
    assert any(t['status']=='executed' and t['kind']=='buy'for t in first['settlements'])
    assert first['initial_totals']==first['ending_totals']
    assert first['balances']['whale']['token_units']>0
    views=w.observations();w.advance([proposal(o,kind='sell' if actor=='whale'else'hold',amount=100 if actor=='whale'else 0)for actor,o in views.items()])
    result=w.report();assert result['status']=='completed'
    assert replay_agent_world(result)==result
    altered=deepcopy(result);altered['balances']['retail']['cash_cents']+=1
    with pytest.raises(ValueError):replay_agent_world(altered)


@pytest.mark.parametrize('change',[lambda p:p.update(actor_id='someone-else'),lambda p:p.update(observation_sha256='0'*64),lambda p:p['action'].update(evidence_ids=['not-observed']),lambda p:p.update(message={'text':'forged','stance':'uncertain','citations':['not-observed']})])
def test_malformed_turn_is_atomic(change):
    w=AgentWorld(spec());before=w.report();views=w.observations();turns=[proposal(o)for o in views.values()];change(turns[-1])
    with pytest.raises(ValueError):w.advance(turns)
    assert w.report()==before


def test_budget_and_capabilities_reject_without_moving_money():
    w=AgentWorld(spec());views=w.observations()
    turns=[proposal(o,kind='buy'if actor=='whale'else'hold',amount=999999 if actor=='whale'else 0)for actor,o in views.items()]
    w.advance(turns);r=w.report();assert r['initial_totals']==r['ending_totals']
    assert any(s['status']=='rejected' and s['reason']=='budget_or_position_limit'for s in r['settlements'])
    w=AgentWorld(spec());views=w.observations();turns=[proposal(o)for o in views.values()];turns[0]=proposal(views['analyst'],'buy',1)
    with pytest.raises(ValueError):w.advance(turns)
    assert w.round==1


def test_attention_and_memory_are_bounded():
    p=spec();p['agents'][1]['attention_capacity']=0
    w=AgentWorld(p);views=w.observations();w.advance([proposal(o,text='not delivered to zero-attention reader')for o in views.values()])
    assert w.observations()['retail']['messages']==[]


@pytest.mark.parametrize('mutate',[lambda p:p['agents'].append(deepcopy(p['agents'][0])),lambda p:p['agents'][0].update(subscriptions=['unknown']),lambda p:p['market'].update(lp_cash_cents=99999999),lambda p:p.update(rounds=17),lambda p:p['events'][0].update(id='duplicate')or p['events'][1].update(id='duplicate'),lambda p:p['agents'][0].update(initial_cash_cents=True)])
def test_world_constraints(mutate):
    p=spec();mutate(p)
    with pytest.raises(ValueError):validate_agent_world(p)


def test_completed_round_cannot_advance_and_inputs_are_detached():
    p=spec();w=AgentWorld(p);p['agents'][0]['name']='mutated'
    for _ in range(2):w.advance([proposal(o)for o in w.observations().values()])
    assert w.report()['world']['agents'][0]['name']=='Analyst'
    with pytest.raises(ValueError):w.advance([])


def test_reordered_turn_list_preserves_seeded_execution_and_replay():
    first=AgentWorld(spec());second=AgentWorld(spec())
    turns=[proposal(o)for o in first.observations().values()]
    first.advance(turns);second.advance(list(reversed(turns)))
    assert first.report()==second.report()
    assert replay_agent_world(second.report())==second.report()


def test_world_rejects_conservative_unreplayable_report_expansion():
    p=spec();p['rounds']=8
    template=p['agents'][2]
    p['agents']=[{**deepcopy(template),'id':f'actor-{i}','subscriptions':['news'],'description':'x'*400,'goal':'y'*400,'attention_capacity':16}for i in range(16)]
    p['events']=[{'id':f'event-{i}','round':1,'text':'z'*1600,'provenance':'p'*1600}for i in range(64)]
    with pytest.raises(ValueError,match='report expansion'):validate_agent_world(p)
