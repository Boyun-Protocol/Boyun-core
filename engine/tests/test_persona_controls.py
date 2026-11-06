from copy import deepcopy
import pytest
from decision_lab.product_api import examples
from decision_lab.persona_controls import adapt_personas,validate_options

def test_profile_controls_change_real_observations_without_changing_finances_or_rules():
    from decision_lab.strategic_worlds import StrategicWorld
    base=examples()[0]['world'];original=deepcopy(base)
    options={'focus':'retail','retail_style':'degen','team_priority':'liquidity'}
    changed=adapt_personas(base,options)
    assert base==original
    for before,after in zip(base['actors'],changed['actors']):
        for key in ('initial_cash_cents','utility_weights','actions','subscriptions'):assert before[key]==after[key]
    for key in ('metrics','events','interactions','rounds'):assert changed[key]==base[key]
    assert 'momentum'in changed['actors'][1]['motivation']
    obs=StrategicWorld(changed).observations()
    assert 'momentum'in str(obs[changed['actors'][1]['id']])
    assert 'market-making'in changed['actors'][0]['goal']
    assert adapt_personas(base,{'focus':'balanced','retail_style':'balanced','team_priority':'balanced'})==base


def test_unsupported_persona_parameters_rejected():
    for invalid in ({'focus':'retail'}, {'focus':'retail','retail_style':'invented','team_priority':'marketing'}, {'focus':'retail','retail_style':'degen','team_priority':'marketing','capital':100000}):
        with pytest.raises(ValueError):validate_options(invalid)


def test_example_creation_applies_requested_profiles(tmp_path):
    from decision_lab.product_api import ProductManager
    manager=ProductManager(tmp_path)
    try:
        base=examples()[0]
        state=manager.create({'mode':'example','example_id':base['id'],'question':base['question'],'public_input':False,'persona_options':{'focus':'retail','retail_style':'cautious','team_priority':'marketing'}})
        actors=state['proposal']['world']['actors']
        assert 'cautious retail'in actors[1]['goal']
        assert 'marketing'in actors[0]['goal']
        assert [a['initial_cash_cents']for a in actors]==[a['initial_cash_cents']for a in base['world']['actors']]
        assert state['status']=='ready'and state['authoring_attempts']==0
    finally:manager.close()
