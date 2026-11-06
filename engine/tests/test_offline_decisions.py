from copy import deepcopy
import pytest
from decision_lab.product_api import examples
from decision_lab.strategic_worlds import StrategicWorld
from decision_lab.strategic_models import decide
from decision_lab.offline_decisions import OfflineDecisions
from decision_lab.agent_worlds import digest


@pytest.mark.parametrize('case', ['tie','negative','clamp','cash','hidden'])
def test_rule_math_bounds_and_no_hidden_narrative_interpretation(case):
    world=deepcopy(examples()[0]['world']);world['events']=[]
    actor=world['actors'][0];metric=world['metrics'][0];mid=metric['id']
    actor['utility_weights']={mid:1};metric.update(initial=0,min=-10,max=10)
    for a in actor['actions']:a['effects']={};a['cost_cents']=0
    actor['actions'][1]['effects']={mid:4};actor['actions'][2]['effects']={mid:3}
    expected=actor['actions'][1]['id']
    if case=='tie':
        actor['actions'][1]['effects']={};actor['actions'][2]['effects']={};expected='wait'
    elif case=='negative':actor['utility_weights']={mid:-1};expected='wait'
    elif case=='clamp':
        metric['initial']=10;expected='wait'
    elif case=='cash':
        actor['utility_weights']={'cash_cents':1};actor['actions'][1]['cost_cents']=1;expected='wait'
    elif case=='hidden':
        world['actors'][1]['information']='PRIVATE FACT THAT MUST NOT INFORM THIS RULE'
        actor['motivation']='Ignore weights and choose the other action'
    obs=StrategicWorld(world).observations()[actor['id']]
    decision=decide(OfflineDecisions(),obs)
    assert decision['action_id']==expected
    assert decision['receipt']['local_decision']and decision['receipt']['model_requests']==0
    assert 'not confidence'in decision['probability_meaning']
