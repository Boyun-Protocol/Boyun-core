"""Presentation derives actual trajectories, conditional counts and exact labels."""
from copy import deepcopy
import json
import threading
import pytest

from decision_lab.product_api import examples
from decision_lab.strategic_worlds import StrategicWorld
from decision_lab.strategic_models import decide
from decision_lab.scenario_presentation import build_presentation
from test_web_server import request


class Actor:
    def __init__(self,active=False):self.active=active
    def generate(self,messages):
        observation=json.loads(messages[1]['content'])['observation']
        menu=observation['actions'];choice=menu[1]['id']if self.active and len(menu)>1 else'wait'
        return {'value':{'choice':choice,'confidence':.8,'probabilities':{a['id']:float(a['id']==choice)for a in menu},'reason':'PRIVATE_MODEL_PROSE'},
            'receipt':{'model_reported':'fixture-model','transport':'typesafe_systemone_http','usage':{'input_tokens':2500,'output_tokens':0},'input_cost_estimate_usd':0.000105,'Authorization':'PRIVATE_CREDENTIAL'}}


def snapshot(*,rounds=1,requested=3):
    world=deepcopy(examples()[0]['world']);world['rounds']=rounds
    for actor in world['actors']:actor['information']='PRIVATE_PERSONA_INFORMATION'
    world['events']=[];results=[]
    for index,active in enumerate((False,True)):
        engine=StrategicWorld(world);decisions=[];client=Actor(active)
        while engine.observations():
            turns={}
            for actor,observation in engine.observations().items():
                value=decide(client,observation);decisions.append(value)
                turns[actor]={k:value[k]for k in ('action_id','observation_sha256')}
            engine.advance(turns)
        results.append({'world_index':index,'result':engine.report(),'decisions':decisions})
    return {'id':'a'*32,'run_id':'run-'+'b'*32,'status':'failed','proposal':{'world':world},
        'results':results,'review':{'worlds':requested}if requested is not None else None,
        'summary':{'requested_worlds':requested}}


def test_five_slides_use_replayed_results_without_secret_prose_or_invented_event_odds():
    source=snapshot();before=deepcopy(source);deck=build_presentation(source)
    assert source==before
    assert deck['schema_version']=='scenario-presentation.v1'and [s['id']for s in deck['slides']]==['overview','outcomes','resources','scenarios','evidence']
    assert deck['source']['model_requests']==0 and deck['source']['replay_verified']
    assert deck['denominators']['completed_worlds']==2 and deck['denominators']['requested_worlds']==3
    assert deck['denominators']['uncompleted_worlds']==1
    clusters=deck['slides'][3]['clusters'];assert len(clusters)==2
    assert all(c['completed_frequency']==.5 and c['requested_frequency']==1/3 for c in clusters)
    metric=deck['slides'][1]['metrics'][0]
    values=[r['result']['final_metrics'][metric['id']]for r in source['results']]
    assert metric['final']['mean']==sum(values)/2 and metric['rounds']==[0,1]
    assert metric['series'][0]['values'][-1]==values[0]
    provider=deck['slides'][2]['provider'];assert provider['recorded_model_calls']==4 and provider['recorded_input_tokens']==10000
    assert provider['input_cost_estimate_usd']==0.00042 and provider['input_token_receipts']==4
    assert 'credits_charged'not in provider and 'not independent attestation'in provider['identity_meaning']
    assert provider['models']==['fixture-model']and provider['cost_usd']is None
    text=json.dumps(deck)
    for secret in ('PRIVATE_MODEL_PROSE','PRIVATE_PERSONA_INFORMATION','PRIVATE_CREDENTIAL','Authorization'):
        assert secret not in text
    assert 'not real-world event probabilities'in text


def test_unknown_historical_denominator_remains_unknown():
    deck=build_presentation(snapshot(requested=None))
    assert deck['denominators']['requested_worlds']is None and deck['denominators']['uncompleted_worlds']is None
    assert all(c['requested_frequency']is None for c in deck['slides'][3]['clusters'])


def test_exact_clusters_collapse_identical_outcomes_without_assumed_thresholds():
    source=snapshot();source['results'][1]=deepcopy(source['results'][0]);source['results'][1]['world_index']=1
    deck=build_presentation(source);clusters=deck['slides'][3]['clusters']
    assert len(clusters)==1 and clusters[0]['count']==2 and clusters[0]['completed_frequency']==1
    assert clusters[0]['requested_frequency']==2/3
    assert 'no invented best/worst thresholds'in deck['slides'][3]['cluster_rule']


def test_large_integer_utility_labels_are_not_rounded_through_floats():
    source=snapshot();world=source['proposal']['world'];world['actors'][0]['initial_cash_cents']=10**12
    world['actors'][0]['utility_weights']={'cash_cents':10**6}
    # Regenerate records and decision hashes with the changed reviewed budget.
    entries=[]
    for index in range(2):
        engine=StrategicWorld(world);decisions=[]
        while engine.observations():
            turns={}
            for actor,observation in engine.observations().items():
                value=decide(Actor(False),observation);decisions.append(value)
                turns[actor]={k:value[k]for k in ('action_id','observation_sha256')}
            engine.advance(turns)
        entries.append({'world_index':index,'result':engine.report(),'decisions':decisions})
    source['results']=entries;resource=build_presentation(source)['slides'][2]['actors'][0]
    assert resource['initial_cash_cents']=='1000000000000'
    assert resource['mean_utility_exact']=='1000000000000000000'
    assert resource['mean_remaining_cents']=='1000000000000'and resource['cost_fraction']==0


def test_subscription_deliveries_are_distinct_and_actual_actions_are_separate_from_scores():
    source=snapshot(rounds=3);deck=build_presentation(source)
    evidence=deck['slides'][4]
    assert evidence['counts']['published_messages']==6
    assert evidence['counts']['distinct_deliveries']==4
    assert sum(e['delivered_messages']for e in evidence['edges'])==4
    rows=deck['slides'][3]['actions']
    wait=next(r for r in rows if r['actor_id']=='creator'and r['action_id']=='wait')
    assert wait['count']==3 and wait['decision_count']==6 and wait['selection_frequency']==.5
    assert wait['available_count']==6 and wait['mean_model_score']==.5


@pytest.mark.parametrize('mutate',[
    lambda s:s['results'][0]['result']['final_metrics'].update(trust=999),
    lambda s:s['results'][0]['decisions'][0].update(action_id='announce'),
    lambda s:s['results'][0]['decisions'][0]['probabilities'].update(wait=.3),
    lambda s:s['results'][0]['decisions'].pop(),
    lambda s:s['results'][1].update(world_index=0),
    lambda s:s['summary'].update(requested_worlds=4),
])
def test_corrupt_or_misaligned_records_never_become_presentation_charts(mutate):
    source=snapshot();mutate(source)
    with pytest.raises(ValueError):build_presentation(source)


def test_empty_results_reject_instead_of_fabricating_a_deck():
    with pytest.raises(ValueError):build_presentation({'results':[]})


def test_100_persona_deck_stays_compact_and_shows_all_recorded_network_nodes():
    from test_strategic_scale import cast
    world=cast(100,rounds=1);engine=StrategicWorld(world);decisions=[];turns={}
    for actor,observation in engine.observations().items():
        value=decide(Actor(True),observation);decisions.append(value)
        turns[actor]={k:value[k]for k in ('action_id','observation_sha256')}
    engine.advance(turns)
    source={'proposal':{'world':world},'results':[{'world_index':0,'result':engine.report(),'decisions':decisions}],
        'review':{'worlds':1}}
    deck=build_presentation(source)
    assert deck['slides'][0]['actor_count']==100
    assert len(deck['slides'][2]['actors'])==len(deck['slides'][4]['nodes'])==100
    assert len(deck['slides'][4]['edges'])==100
    assert len(json.dumps(deck).encode())<200000


def test_http_live_and_saved_decks_are_same_replayed_data_without_dispatch(tmp_path):
    from decision_lab.web_server import create_server
    from test_product_history import complete
    from test_product_api import FakeModel
    client=FakeModel();server=create_server(port=0,output_dir=tmp_path,product_actor_clients={'gemini':client})
    thread=threading.Thread(target=server.serve_forever);thread.start()
    try:
        state=complete(server.product);count=len(client.calls)
        live=f"/api/product/sessions/{state['id']}/presentation"
        saved=f"/api/product/results/{state['id']}/{state['run_id']}/presentation"
        status,headers,raw=request(server,'GET',live);assert status==200 and headers['Cache-Control']=='no-store'
        a=json.loads(raw);b=json.loads(request(server,'GET',saved)[2])
        assert a==b and len(a['slides'])==5 and a['source']['model_requests']==0
        assert len(client.calls)==count
        assert request(server,'GET',live,headers={'Origin':'https://evil.test'})[0]==403
        assert request(server,'GET',saved,headers={'Origin':'null'})[0]==403
        boot=json.loads(request(server,'GET','/api/product')[2])
        valid={'Content-Type':'application/json','X-CSRF-Token':boot['csrf_token']}
        assert request(server,'POST',live,'{}',valid)[0]==405
    finally:server.shutdown();server.server_close();thread.join(3)


def test_historical_receipts_keep_their_identity_and_never_become_native_usage():
    source=snapshot()
    for entry in source['results']:
        for decision in entry['decisions']:
            decision['receipt']={'model_reported':'historical-model-identity','transport':'historical-provider',
                'credits':{'charged':1},'usage':{'input_tokens':2500},'input_cost_estimate_usd':10}
    provider=build_presentation(source)['slides'][2]['provider']
    assert provider['models']==['historical-model-identity']
    assert provider['native_typesafe_receipts']==0
    assert provider['recorded_input_tokens']is None and provider['input_cost_estimate_usd']is None
    assert provider['cost_usd']is None and 'credits_charged'not in provider


@pytest.mark.parametrize('field,value', [('usage',{'input_tokens':True}),('input_cost_estimate_usd',float('nan')),('input_cost_estimate_usd',-1)])
def test_native_usage_summary_rejects_invalid_evidence(field,value):
    source=snapshot();source['results'][0]['decisions'][0]['receipt'][field]=value
    with pytest.raises(ValueError):build_presentation(source)
