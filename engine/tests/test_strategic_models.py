from copy import deepcopy
import json
import pytest

from decision_lab.agent_worlds import digest


def observation():
    value = {'schema_version':'strategic-observation.v1','world_id':'test','actor_id':'builder','round':1,
        'actor':{'id':'builder','name':'Builder','role':'founder','motivation':'Preserve runway',
                 'goal':'Learn before spending','information':'Private cost estimate','utility_weights':{'cash_cents':1}},
        'cash_cents':100,'metrics':{'trust':10},
        'actions':[{'id':'wait','label':'Wait','description':'Keep cash','cost_cents':0,'effects':{},'message':'','provenance':'assumed'},
                   {'id':'run-pilot','label':'Pilot','description':'Small test','cost_cents':10,'effects':{'trust':1},'message':'Testing','provenance':'assumed'}],
        'opponents':[],'events':[],'messages':[],'limitations':['Hypothetical']}
    value['observation_sha256']=digest(value)
    return value


class ChoiceClient:
    model='jev-latest'
    def __init__(self): self.calls=[]
    def evaluate(self, **kwargs):
        self.calls.append(kwargs)
        return {'answers':{'action':{'type':'choice','choice':'option_1','confidence':.8,
                                    'probabilities':{'option_0':.2,'option_1':.8}}},'receipt':{'test':True}}


def test_own_information_and_affordable_menu_reach_actual_choice_interface():
    from decision_lab.strategic_models import decide
    client=ChoiceClient(); obs=observation()
    result=decide(client,obs,mode='argmax',seed=42)
    assert client.calls[0]['state']==obs
    assert 'motivation' in json.dumps(client.calls[0]['state'])
    assert result['action_id']=='run-pilot'
    assert result['probabilities']=={'wait':.2,'run-pilot':.8}
    assert result['receipt']=={'test':True}
    assert result['observation_sha256']==obs['observation_sha256']


def test_sampling_is_reproducible_but_argmax_is_not_called_an_event_probability():
    from decision_lab.strategic_models import decide
    obs=observation()
    a=decide(ChoiceClient(),obs,mode='sample',seed=3)
    assert a==decide(ChoiceClient(),obs,mode='sample',seed=3)
    assert 'not calibrated' in a['probability_meaning']


def test_sampling_does_not_depend_on_provider_json_key_order():
    from decision_lab.strategic_models import decide
    class Reversed(ChoiceClient):
        def evaluate(self,**kwargs):
            value=super().evaluate(**kwargs)
            value['answers']['action']['probabilities']={'option_1':.8,'option_0':.2}
            return value
    for seed in range(10):
        assert decide(ChoiceClient(),observation(),mode='sample',seed=seed)['action_id']==decide(Reversed(),observation(),mode='sample',seed=seed)['action_id']


def test_invalid_distribution_and_stale_identity_rejected():
    from decision_lab.strategic_models import decide
    class Bad(ChoiceClient):
        def evaluate(self,**kwargs):
            r=super().evaluate(**kwargs);r['answers']['action']['probabilities']['option_0']=.5;return r
    with pytest.raises(ValueError):decide(Bad(),observation(),mode='argmax',seed=1)
    obs=observation();obs['cash_cents']=900
    client=ChoiceClient()
    with pytest.raises(ValueError):decide(client,obs,mode='argmax',seed=1)
    assert not client.calls


def test_single_affordable_wait_never_calls_a_provider():
    from decision_lab.strategic_models import decide
    obs=observation();obs['actions']=obs['actions'][:1];obs.pop('observation_sha256');obs['observation_sha256']=digest(obs)
    client=ChoiceClient();value=decide(client,obs,mode='argmax',seed=1)
    assert value['probabilities']=={'wait':1.0} and value['receipt'] is None
    assert not client.calls


def test_frontier_route_has_same_exact_distribution_contract_and_no_hidden_state():
    from decision_lab.strategic_models import decide
    class Text:
        def generate(self,messages):
            self.messages=messages
            return {'value':{'choice':'run-pilot','confidence':.75,'probabilities':{'wait':.3,'run-pilot':.7},
                             'reason':'Prefer a small experiment.'},'receipt':{'transport':'fake'}}
    client=Text();obs=observation();result=decide(client,obs,mode='argmax',seed=1)
    assert json.loads(client.messages[1]['content'])['observation']==obs
    assert result['reason']=='Prefer a small experiment.'


def test_authoring_context_identity_and_unknown_fields():
    from decision_lab.strategic_models import authoring_messages, validate_proposal
    messages, context_hash=authoring_messages('Choose a launch plan',[],None)
    assert json.loads(messages[1]['content'])['context_sha256']==context_hash
    p={'schema_version':'strategic-proposal.v1','context_sha256':context_hash,'summary':'Need a budget',
       'questions':[{'id':'budget','prompt':'Budget?','choices':['$1000','$5000'],'required':True}],
       'world':None,'limitations':['Missing budget']}
    assert validate_proposal(p,context_hash)['world'] is None
    p['context_sha256']='0'*64
    with pytest.raises(ValueError):validate_proposal(p,context_hash)


def projection_observation():
    obs = observation()
    obs['world'] = {'rounds': 3, 'metric_definitions': [
        {'id': 'trust', 'min': 0, 'max': 12}, {'id': 'risk', 'min': -5, 'max': 5}]}
    obs['metrics'] = {'trust': 10, 'risk': -4}
    obs['actor']['utility_weights'] = {'cash_cents': 2, 'trust': 3, 'risk': -4}
    obs['actions'][1]['effects'] = {'trust': 8, 'risk': -7}
    obs['interactions'] = [{'when': {'builder': 'run-pilot', 'other': 'join'},
                            'effects': {'trust': -10}}]
    obs['events'] = [{'text': 'Visible narrative only, not an executable forecast.'}]
    obs.pop('observation_sha256'); obs['observation_sha256'] = digest(obs)
    return obs


def test_criteria_contain_exact_clamped_signed_own_action_accounting_only():
    from decision_lab.strategic_models import decision_request
    obs = projection_observation(); original = deepcopy(obs)
    request = decision_request(obs)
    assert request['state'] == obs == original
    criteria = {key: json.loads(value) for key, value in request['questions']['action']['criteria'].items()}
    assert criteria['option_1'] == {'action_id': 'run-pilot', 'own_action_projection': {
        'status': 'available', 'scope': 'current_stage_unilateral', 'cash_after_cents': 90,
        'metrics_after': {'trust': 12, 'risk': -5}, 'utility_before': 246,
        'utility_after': 236, 'utility_delta': -10}}
    assert criteria['option_0']['own_action_projection'] == {
        'status': 'available', 'scope': 'current_stage_unilateral', 'cash_after_cents': 100,
        'metrics_after': {'trust': 10, 'risk': -4}, 'utility_before': 246,
        'utility_after': 246, 'utility_delta': 0}
    # No duplicated biographies, action descriptions or peer content in criteria.
    serialized = json.dumps(criteria)
    for text in ('Preserve runway', 'Small test', 'Testing', 'Visible narrative'):
        assert text not in serialized
    assert all(len(value) < 600 for value in request['questions']['action']['criteria'].values())


def test_partial_projection_does_not_force_a_greedy_choice_or_add_model_calls():
    from decision_lab.strategic_models import decide, DECISION_PROMPT_VERSION, DECISION_CRITERIA_VERSION
    client = ChoiceClient(); obs = projection_observation()
    result = decide(client, obs)
    assert len(client.calls) == 1 and set(client.calls[0]['questions']) == {'action'}
    # The fixture prefers a negative own-action delta; model strategy remains authoritative.
    assert result['action_id'] == 'run-pilot'
    assert result['decision_contract'] == {'prompt_version': DECISION_PROMPT_VERSION,
        'criteria_version': DECISION_CRITERIA_VERSION, 'request_sha256': digest(client.calls[0])}
    assert result['receipt'] == {'test': True}


def test_prompt_bounds_information_and_uses_code_arithmetic_for_both_routes():
    from decision_lab.strategic_models import decision_request, decide, DECISION_INSTRUCTIONS
    instructions = decision_request(projection_observation())['questions']['action']['instructions']
    for text in ('maximize expected own', 'terminal utility', 'reviewed utility_weights',
                 'private goals', 'future events', 'unverified claim', 'excludes all other actions',
                 'current-stage utility', 'not a terminal rollout', 'do not redo this arithmetic',
                 'largest baseline delta', 'not calibrated event odds'):
        assert text in instructions
    class Text:
        def generate(self, messages):
            self.messages = messages
            return {'value': {'choice': 'wait', 'confidence': 1,
                'probabilities': {'wait': 1, 'run-pilot': 0}, 'reason': 'Keep options open.'}, 'receipt': {}}
    client = Text(); obs = projection_observation(); decide(client, obs)
    assert DECISION_INSTRUCTIONS in client.messages[0]['content']
    data = json.loads(client.messages[1]['content'])
    assert data['observation'] == obs
    assert data['questions'] == decision_request(obs)['questions']


def test_legacy_observation_missing_bounds_is_explicitly_unprojected():
    from decision_lab.strategic_models import decision_request
    criterion = json.loads(decision_request(observation())['questions']['action']['criteria']['option_1'])
    assert criterion['own_action_projection']['status'] == 'unavailable'
    assert 'utility_delta' not in criterion['own_action_projection']


def test_projection_request_stays_compatible_with_jev_large_cast_preflight():
    from test_strategic_scale import cast
    from decision_lab.strategic_worlds import StrategicWorld
    from decision_lab.strategic_models import decision_request
    from decision_lab.jev import validate_request
    for obs in StrategicWorld(cast(100)).observations().values():
        request = decision_request(obs)
        checked = validate_request(state=request['state'], questions=request['questions'], model='jev-latest')
        assert checked['state'] == obs
        assert len(checked['questions']) == 1


def test_regular_and_staged_authoring_share_construction_and_frozen_alignment_guidance():
    from decision_lab.game_construction import GAME_CONSTRUCTION_GUIDELINES
    from decision_lab.strategic_models import authoring_messages
    from decision_lab.batch_authoring import scaffold_messages, batch_messages
    from test_batch_authoring import scaffold, plan
    from test_strategic_scale import cast
    ordinary, _ = authoring_messages('A hypothetical project.', [], cast(2))
    staged, _ = scaffold_messages('A hypothetical project.', plan(100), cast(2))
    assert GAME_CONSTRUCTION_GUIDELINES in ordinary[0]['content']
    assert GAME_CONSTRUCTION_GUIDELINES in staged[0]['content']
    frozen = scaffold(100, 'a' * 64)
    profile, _ = batch_messages('A hypothetical project.', frozen, frozen['roster'][:20])
    instructions = profile[0]['content']
    for text in ('frozen signed utility_weights', 'cannot change', 'Silent wait',
                 'existing joint rule', 'risk-utility mechanism'):
        assert text in instructions
