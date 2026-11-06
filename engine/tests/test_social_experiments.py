"""Actual controlled communication treatments; fixture roles are not model forecasts."""
from copy import deepcopy
import json

import pytest

from test_agent_worlds import spec, proposal


def protocol():
    world=spec();world['agents']=world['agents'][:2]
    world['agents'][0]['subscriptions']=['news']
    return {'schema_version':'social-experiment.v1','id':'remove-analyst-link','baseline_world':world,
            'treatment':{'remove_subscriptions':[{'listener':'retail','source':'analyst'}]},'seeds':[42,43]}


def prepare(value):
    from decision_lab.social_experiments import prepare_social_experiment
    return prepare_social_experiment(value)


class Role:
    def __init__(self,fail_at=None):self.calls=[];self.fail_at=fail_at
    def generate(self,messages):
        self.calls.append(deepcopy(messages))
        if len(self.calls)==self.fail_at:raise RuntimeError('private provider error')
        observation=json.loads(messages[1]['content'])['observation']
        peer=next((m for m in observation['messages'] if m['source']=='analyst'),None)
        value=proposal(observation,kind='buy' if peer else 'hold',amount=1000 if peer else 0,
                       text='Publication with uncertain implications' if observation['actor']['id']=='analyst' else None)
        return {'value':value,'receipt':{'transport':'test_fixture','request_attempts':1,'usage':None,'cost_usd':None}}


def test_prepare_changes_only_declared_peer_edges_and_no_input_mutation():
    p=protocol();before=deepcopy(p);plan=prepare(p)
    assert p==before
    assert plan['required_calls']==16
    assert plan['baseline_world']==p['baseline_world']
    expected=deepcopy(p['baseline_world']);expected['agents'][1]['subscriptions']=[]
    assert plan['treatment_world']==expected
    assert plan['protocol']==p
    assert len(plan['protocol_sha256'])==64


@pytest.mark.parametrize('mutate',[
    lambda p:p.update(seeds=[]),lambda p:p.update(seeds=[42,42]),lambda p:p.update(seeds=[True]),
    lambda p:p.update(seeds=list(range(5))),lambda p:p['baseline_world'].update(rounds=1),
    lambda p:p['treatment']['remove_subscriptions'][0].update(source='news'),
    lambda p:p['treatment']['remove_subscriptions'][0].update(listener='analyst'),
    lambda p:p['treatment'].update(remove_subscriptions=[]),
    lambda p:p['treatment']['remove_subscriptions'].append({'listener':'retail','source':'analyst'}),
    lambda p:p['baseline_world']['agents'][0].update(allowed_actions=['hold']),
    lambda p:p['baseline_world']['agents'][1].update(attention_capacity=0),
    lambda p:p['treatment'].update(changed_resources=100),
])
def test_invalid_or_ineffective_treatments_reject(mutate):
    p=protocol();mutate(p)
    with pytest.raises(ValueError):prepare(p)


def test_call_budget_and_new_directory_preflight_before_first_dispatch(tmp_path):
    from decision_lab.social_experiments import run_social_experiment
    client=Role();out=tmp_path/'experiment'
    with pytest.raises(ValueError):run_social_experiment(protocol=protocol(),client=client,output_dir=out,max_calls=15)
    assert client.calls==[] and not out.exists()
    out.mkdir()
    with pytest.raises((OSError,ValueError)):run_social_experiment(protocol=protocol(),client=client,output_dir=out,max_calls=16)
    assert client.calls==[]


def test_real_round_barrier_treatment_has_matched_resources_and_observed_effect(tmp_path):
    from decision_lab.social_experiments import run_social_experiment
    client=Role();out=tmp_path/'experiment'
    result=run_social_experiment(protocol=protocol(),client=client,output_dir=out,max_calls=16)
    assert result['status']=='completed'
    assert result['attempted_calls']==16 and result['completed_pairs']==2
    analysis=json.loads((out/'analysis.json').read_text())
    assert analysis['planned_pairs']==analysis['completed_pairs']==2
    assert analysis['excluded_pairs']==0
    for pair in analysis['pairs']:
        assert pair['baseline']['peer_new_deliveries']==1
        assert pair['treatment']['peer_new_deliveries']==0
        assert pair['delta']['executed_buy_cash_cents']==-1000
        assert pair['delta']['actor_ending_cash_cents']['retail']==1000
    assert analysis['aggregate']['executed_buy_cash_cents']['median']==-1000
    observations=[json.loads(call[1]['content'])['observation']for call in client.calls]
    assert len([o for o in observations if o['round']==1 and not o['own_history']])==8
    assert all((path.stat().st_mode&0o777)==0o600 for path in out.rglob('*.json'))
    assert 'private provider error'not in (out/'manifest.json').read_text()


def test_failed_arm_is_durable_and_excluded_never_counted_success(tmp_path):
    from decision_lab.social_experiments import run_social_experiment
    out=tmp_path/'experiment';client=Role(fail_at=3)
    result=run_social_experiment(protocol=protocol(),client=client,output_dir=out,max_calls=16)
    assert result['status']=='partial'
    assert result['completed_pairs']==1 and result['failed_arms']==1
    assert result['attempted_calls']==15
    analysis=json.loads((out/'analysis.json').read_text())
    assert analysis['completed_pairs']==1 and analysis['excluded_pairs']==1
    assert (out/'seed-42'/'baseline'/'call-003.receipt.json').exists()
    assert analysis['exclusions'][0]['seed']==42


def test_analysis_rejects_mispaired_world_seed_duplicate_or_tampered_results(tmp_path):
    from decision_lab.social_experiments import run_social_experiment,analyze_social_experiment
    p=protocol();out=tmp_path/'experiment'
    run_social_experiment(protocol=p,client=Role(),output_dir=out,max_calls=16)
    pair={'seed':42,**{arm:json.loads((out/'seed-42'/arm/'result.json').read_text())for arm in ('baseline','treatment')}}
    assert analyze_social_experiment(p,[pair])['completed_pairs']==1
    for mutation in ('seed','world','balance','duplicate'):
        bad=deepcopy(pair)
        if mutation=='seed':bad['treatment']['seed']=43
        elif mutation=='world':bad['treatment']=deepcopy(bad['baseline'])
        elif mutation=='balance':bad['baseline']['balances']['retail']['cash_cents']+=1
        with pytest.raises(ValueError):analyze_social_experiment(p,[bad,bad]if mutation=='duplicate'else[bad])


def test_all_missing_pairs_have_zero_success_denominator_and_no_aggregate():
    from decision_lab.social_experiments import analyze_social_experiment
    result=analyze_social_experiment(protocol(),[])
    assert result['completed_pairs']==0 and result['excluded_pairs']==2
    assert result['aggregate'] is None


def test_failed_first_request_keeps_partial_replay_and_runs_other_prescheduled_arm(tmp_path):
    from decision_lab.social_experiments import run_social_experiment
    from decision_lab.agent_worlds import replay_agent_world
    out=tmp_path/'first-failure';client=Role(fail_at=1)
    manifest=run_social_experiment(protocol=protocol(),client=client,output_dir=out,max_calls=16)
    assert manifest['status']=='partial' and manifest['attempted_calls']==13
    partial=json.loads((out/'seed-42'/'baseline'/'result.json').read_text())
    assert partial['completed_rounds']==0 and replay_agent_world(partial)==partial
    assert len(list(out.glob('seed-*/treatment/manifest.json')))==2


def test_caller_protocol_mutation_during_provider_call_cannot_change_reviewed_matrix(tmp_path):
    from decision_lab.social_experiments import run_social_experiment
    p=protocol()
    class Mutator(Role):
        def generate(self,messages):
            response=super().generate(messages)
            p['seeds'].append(999)
            return response
    out=tmp_path/'mutation';client=Mutator()
    result=run_social_experiment(protocol=p,client=client,output_dir=out,max_calls=16)
    assert result['status']=='completed' and result['attempted_calls']==16
    assert len(list(out.glob('seed-*')))==2
    saved=json.loads((out/'protocol.json').read_text())
    assert saved['seeds']==[42,43]


def test_nonpublishing_listener_is_valid_when_source_can_publish():
    p=protocol();p['baseline_world']['agents'][1]['allowed_actions']=['hold','buy']
    assert prepare(p)['required_calls']==16


def test_report_prompt_expansion_blocks_before_any_paid_dispatch(tmp_path):
    from decision_lab.social_experiments import run_social_experiment
    p=protocol();p['baseline_world']['event_description']='😀'*8000
    p['baseline_world']['agents'][0]['description']='😀'*1600
    p['baseline_world']['agents'][0]['name']='😀'*1600
    p['baseline_world']['agents'][0]['role']='😀'*1600
    p['baseline_world']['agents'][0]['goal']='😀'*1600
    p['baseline_world']['rounds']=8
    client=Role();out=tmp_path/'oversized'
    with pytest.raises(ValueError):run_social_experiment(protocol=p,client=client,output_dir=out,max_calls=64)
    assert not out.exists() and not client.calls
