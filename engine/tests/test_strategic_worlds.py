"""Formal discrete decision worlds keep strategic assumptions and information explicit."""
from copy import deepcopy
import pytest


def provenance():
    return {'status':'assumed','rationale':'Explicit hypothetical rule, not measured behavior.','source_refs':[]}


def world():
    return {'schema_version':'strategic-world.v1','id':'small-coordination','title':'Coordination test',
        'description':'Two participants choose whether to fund a shared prototype.','rounds':2,
        'metrics':[{'id':'readiness','label':'Readiness','unit':'points','initial':1,'min':0,'max':10,'provenance':provenance()}],
        'actors':[{'id':i,'name':i.title(),'role':'Builder','motivation':'Learn safely','goal':'Improve readiness while retaining cash.',
            'information':f'PRIVATE-{i}','initial_cash_cents':100,'utility_weights':{'readiness':10,'cash_cents':1},
            'actions':[{'id':'wait','label':'Wait','description':'Do nothing.','cost_cents':0,'effects':{},'message':'','provenance':provenance()},
                {'id':'build','label':'Build','description':'Commit resources.','cost_cents':60,'effects':{'readiness':6},'message':'I supported the prototype.','provenance':provenance()}],
            'subscriptions':[other],'provenance':provenance()}for i,other in [('alice','bob'),('bob','alice')]],
        'events':[{'id':'early','round':1,'text':'PRIVATE-EARLY','effects':{'readiness':1},'visible_to':['alice'],'provenance':provenance()},
            {'id':'later','round':2,'text':'SECRET-FUTURE','effects':{'readiness':-1},'visible_to':['bob'],'provenance':provenance()}],
        'interactions':[],
        'assumptions':['Utility weights are hypothetical points per unit, not monetary valuations.'],
        'limitations':['No calibrated event odds or real financial settlement.']}


def engine(value=None):
    from decision_lab.strategic_worlds import StrategicWorld
    return StrategicWorld(world()if value is None else value,seed=42)


def decisions(e,action='wait'):
    return {i:{'action_id':action,'observation_sha256':o['observation_sha256']}for i,o in e.observations().items()}


def test_own_private_information_and_future_event_boundary():
    e=engine();obs=e.observations();serialized=str(obs['alice'])
    assert obs['alice']['actor']['information']=='PRIVATE-alice'
    assert 'PRIVATE-bob'not in serialized and 'SECRET-FUTURE'not in serialized
    assert obs['alice']['metrics']=={'readiness':2}
    assert obs['alice']['events']==[{'id':'early','text':'PRIVATE-EARLY','round':1}]
    assert obs['bob']['events']==[]
    assert obs==e.observations()


def test_simultaneous_clamp_costs_affordability_and_next_round_messages():
    e=engine();e.advance(decisions(e,'build'));obs=e.observations()
    assert obs['alice']['cash_cents']==40
    assert [a['id']for a in obs['alice']['actions']]==['wait']
    assert obs['alice']['metrics']['readiness']==9  # aggregate 2+12 clamp10, then round2 event-1
    assert obs['alice']['messages'][0]['source']=='bob'
    assert obs['alice']['messages'][0]['text']=='I supported the prototype.'
    assert obs['alice']['events'][0]['id']=='early' and len(obs['alice']['events'])==1
    assert obs['bob']['events'][0]['text']=='SECRET-FUTURE'
    e.advance(decisions(e));r=e.report()
    assert r['status']=='completed' and r['total_cost_cents']==120
    assert r['actor_results']['alice']=={'initial_cash_cents':100,'cash_cents':40,'cost_cents':60,'utility':130,'initial_utility':110,'utility_delta':20}
    assert e.observations()=={}


def test_atomic_invalid_or_stale_decision_never_changes_state():
    for mutate in (lambda d:d.pop('bob'),lambda d:d['bob'].update(action_id='invent'),
                   lambda d:d['bob'].update(observation_sha256='0'*64),lambda d:d['bob'].update(extra=True)):
        e=engine();before=e.report();d=decisions(e,'build');mutate(d)
        with pytest.raises(ValueError):e.advance(d)
        assert e.report()==before
    e=engine();e.advance(decisions(e,'build'));before=e.report()
    with pytest.raises(ValueError):e.advance(decisions(e,'build'))
    assert e.report()==before


def test_aggregate_metric_effects_order_independent_and_zero_cost_conserved():
    w=world();w['actors'][1]['actions'][1]['effects']={'readiness':-9};w['events']=[]
    one=engine(w);one.advance(decisions(one,'build'))
    w['actors'].reverse();two=engine(w);two.advance(decisions(two,'build'))
    assert one.report()['final_metrics']==two.report()['final_metrics']=={'readiness':0}
    assert sum(a['cash_cents']for a in one.report()['actor_results'].values())+one.report()['total_cost_cents']==200


def test_exact_replay_tamper_rejected_and_deep_detachment():
    from decision_lab.strategic_worlds import replay_strategic_world
    w=world();before=deepcopy(w);e=engine(w);e.advance(decisions(e,'build'));e.advance(decisions(e))
    r=e.report();assert replay_strategic_world(r)==r and w==before
    for mutate in (lambda r:r['final_metrics'].update(readiness=4),lambda r:r['rounds'][0]['decisions']['alice'].update(action_id='wait'),lambda r:r.update(engine_sha256='0'*64)):
        bad=deepcopy(r);mutate(bad)
        with pytest.raises(ValueError):replay_strategic_world(bad)
    obs=engine().observations();obs['alice']['actor']['utility_weights']['readiness']=999
    assert engine().observations()['alice']['actor']['utility_weights']['readiness']==10


@pytest.mark.parametrize('mutate',[
    lambda w:w.update(extra=True),lambda w:w.update(rounds=True),lambda w:w.update(rounds=9),
    lambda w:w['actors'].pop(),lambda w:w['actors'][0].update(subscriptions=['unknown']),
    lambda w:w['actors'][0].update(subscriptions=['alice']),lambda w:w['actors'][0]['actions'][0].update(cost_cents=1),
    lambda w:w['actors'][0]['actions'][0].update(message='not wait'),lambda w:w['actors'][0]['actions'][1]['effects'].update(unknown=1),
    lambda w:w['actors'][0]['utility_weights'].update(unknown=1),lambda w:w['events'][0].update(visible_to=['unknown']),
    lambda w:w['events'][0].update(round=3),lambda w:w['metrics'][0].update(initial=11),
    lambda w:w['actors'][0]['provenance'].update(status='fact'),lambda w:w['actors'][0]['actions'][1].update(cost_cents=-1),
    lambda w:w['actors'][0]['actions'][1].update(id='wait'),lambda w:w['metrics'].append(deepcopy(w['metrics'][0])),
    lambda w:w['actors'][0].update(initial_cash_cents=10**12+1),lambda w:w['actors'][0]['utility_weights'].update(readiness=True),
])
def test_strict_shapes_funding_references_provenance_and_bounds(mutate):
    from decision_lab.strategic_worlds import validate_strategic_world
    w=world();mutate(w)
    with pytest.raises(ValueError):validate_strategic_world(w)


def test_first_round_finite_game_matches_engine_utility_and_explains_limits():
    from decision_lab.strategic_worlds import strategic_game
    w=world();result=strategic_game(w)
    assert result['status']=='computed' and result['analysis']['profile_count']==4
    for p in result['game']['profiles']:
        e=engine(w);d=decisions(e)
        for i,a in p['actions'].items():d[i]['action_id']=a
        e.advance(d)
        # First-round game excludes round2 scheduled events, even though active engine prepares round2.
        for i,utility in p['payoffs'].items():
            r=e.report()['actor_results'][i]
            assert utility==r['utility']+10
    w['actors'][0]['initial_cash_cents']=0
    assert strategic_game(w)['status']=='not_computed'


def test_joint_interaction_rules_change_strategic_equilibria_and_same_execution():
    from decision_lab.strategic_worlds import strategic_game
    w=world();w['events']=[]
    for a in w['actors']:
        a['actions'][1]['effects']={}
        a['utility_weights']={'readiness':100,'cash_cents':1}
    w['interactions']=[{'id':'joint-build','when':{'alice':'build','bob':'build'},
        'effects':{'readiness':3},'description':'Both commitments are required for the shared prototype.','provenance':provenance()}]
    e=engine(w);assert e.observations()['alice']['interactions']==w['interactions']
    table=strategic_game(w)['analysis']
    assert {'alice':'build','bob':'build'}in table['pure_nash_profiles']
    assert {'alice':'wait','bob':'wait'}in table['pure_nash_profiles']
    e.advance(decisions(e,'build'));assert e.report()['final_metrics']=={'readiness':4}
    assert e.report()['rounds'][0]['matched_interaction_ids']==['joint-build']
    w['interactions']=[]
    assert strategic_game(w)['analysis']['pure_nash_profiles']==[{'alice':'wait','bob':'wait'}]


@pytest.mark.parametrize('when',[{'alice':'build'},{'alice':'invent','bob':'wait'},
                                  {'alice':'wait','unknown':'build'}])
def test_joint_interaction_conditions_require_known_actions_of_multiple_actors(when):
    from decision_lab.strategic_worlds import validate_strategic_world
    w=world();w['interactions']=[{'id':'invalid','when':when,'effects':{},'description':'Invalid test','provenance':provenance()}]
    with pytest.raises(ValueError):validate_strategic_world(w)


def test_serialized_replay_does_not_depend_on_decision_mapping_insertion_order():
    import json
    from decision_lab.strategic_worlds import replay_strategic_world
    e=engine();d=decisions(e,'build');e.advance(dict(reversed(list(d.items()))));e.advance(decisions(e))
    stored=json.loads(json.dumps(e.report(),sort_keys=True))
    assert replay_strategic_world(stored)==stored


def test_report_expansion_budget_is_rejected_before_large_world_execution():
    from decision_lab.strategic_worlds import validate_strategic_world
    w=world();w['rounds']=8;w['events']=[];base=w['actors'][0];w['actors']=[]
    for i in range(12):
        a=deepcopy(base);a['id']=f'a-{i}';a['information']='x'*1600
        a['actions'][1]['message']='m'*1200
        a['actions'][1]['cost_cents']=0
        a['subscriptions']=[f'a-{j}'for j in range(12)if j!=i]
        w['actors'].append(a)
    with pytest.raises(ValueError,match='report'):
        validate_strategic_world(w)


def test_public_world_definitions_and_own_history_without_peer_private_receipts():
    e=engine();first=e.observations()['alice']
    assert first['world']['title']=='Coordination test'
    assert first['world']['metric_definitions']==[{'id':'readiness','label':'Readiness','unit':'points','min':0,'max':10}]
    assert first['own_history']==[]
    e.advance(decisions(e,'build'));o=e.observations()['alice']
    assert o['own_history']==[{'round':1,'action_id':'build','cost_cents':60,'metrics_after':{'readiness':10}}]
    assert 'PRIVATE-bob'not in str(o) and 'initial_cash_cents'not in str(o['opponents'])
