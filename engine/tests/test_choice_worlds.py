"""Choice-world behavior: invalid effects never create lottery rerolls or costs."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from decision_lab import choice_worlds as cw


def package():
    return {
        'schema_version': 'choice-world.v1', 'id': 'release', 'event_description': 'Supplied release choices.',
        'parameters': {'cost': -2, 'good_odds': 6000},
        'personas': [{'id': 'lead', 'name': 'Lead', 'description': 'Declared decision maker.',
                      'role': 'planner', 'allowed_actions': ['adjust_metric']}],
        'metrics': [{'id': 'budget', 'unit': 'planning_points', 'initial': 5, 'minimum': 0, 'maximum': 10}],
        'scenes': [
            {'id': 'plan', 'title': 'Plan', 'description': 'Select a plan.', 'choices': [
                {'id': 'build', 'label': 'Build', 'explanation': 'Spend two planning points.', 'actor_id': 'lead',
                 'requirements': [{'metric_id': 'budget', 'minimum': 2, 'maximum': 10}],
                 'immediate_effects': [{'action': 'adjust_metric', 'metric_id': 'budget', 'delta': {'parameter': 'cost'}}],
                 'outcomes': [
                     {'id': 'good', 'label': 'Good', 'probability_bps': {'parameter': 'good_odds'},
                      'effects': [{'action': 'adjust_metric', 'metric_id': 'budget', 'delta': 1}], 'next_scene_id': 'review'},
                     {'id': 'bad', 'label': 'Bad', 'probability_bps': 4000, 'effects': [], 'next_scene_id': 'review'}],
                 'probability_provenance': {'status': 'assumed', 'rationale': 'Illustrative odds.', 'source_refs': []}},
            ]},
            {'id': 'review', 'title': 'Review', 'description': 'Finish.', 'choices': [
                {'id': 'finish', 'label': 'Finish', 'explanation': 'End planning.', 'actor_id': 'lead',
                 'requirements': [], 'immediate_effects': [],
                 'outcomes': [{'id': 'done', 'label': 'Done', 'probability_bps': 10000, 'effects': [], 'next_scene_id': None}],
                 'probability_provenance': {'status': 'assumed', 'rationale': 'Declared transition.', 'source_refs': []}},
            ]},
        ], 'initial_scene_id': 'plan', 'policy': {'plan': ['build'], 'review': ['finish']},
        'assumptions': ['Planning points are not money.'],
    }


def test_validates_copy_and_starts_with_declared_metrics():
    p = package()
    validated = cw.validate_choice_world(p)
    validated['parameters']['cost'] = -3
    assert p['parameters']['cost'] == -2
    snap = cw.start_choice_world(p)
    assert snap['status'] == 'active'
    assert snap['metrics'] == {'budget': 5}
    assert snap['scene_id'] == 'plan'
    assert snap['history'] == []
    assert cw.validate_choice_snapshot(snap) == snap


@pytest.mark.parametrize('change', [
    lambda p: p['scenes'][0]['choices'][0]['outcomes'][0].update(probability_bps=5000),
    lambda p: p['scenes'][1]['choices'][0]['outcomes'][0].update(next_scene_id='plan'),
    lambda p: p['scenes'][0]['choices'][0].update(actor_id='missing'),
    lambda p: p['scenes'][0]['choices'][0]['outcomes'][0].update(next_scene_id='missing'),
    lambda p: p['scenes'][0]['choices'][0]['immediate_effects'][0].update(action='transfer'),
    lambda p: p['metrics'][0].update(initial=True),
    lambda p: p['metrics'][0].update(minimum=6),
    lambda p: p.update(policy={'plan': ['build']}),
    lambda p: p['policy'].update(plan=['missing']),
    lambda p: p['scenes'][0]['choices'][0].update(probability_provenance={}),
    lambda p: p['parameters'].update(cost=10**30),
])
def test_rejects_invalid_full_schema(change):
    p = package()
    change(p)
    with pytest.raises(ValueError):
        cw.validate_choice_world(p)


def test_bounds_cover_immediate_and_every_possible_outcome_atomically():
    p = package()
    # This rare positive-probability loss would underflow, even though the other branch fits.
    p['scenes'][0]['choices'][0]['outcomes'][1]['effects'] = [
        {'action': 'adjust_metric', 'metric_id': 'budget', 'delta': -4}]
    snap = cw.start_choice_world(p)
    assert snap['status'] == 'blocked'
    assert cw.choice_options(snap)[0]['eligible'] is False
    old = deepcopy(snap)
    with pytest.raises(ValueError):
        cw.step_choice_world(snap, 'build', 'a')
    assert snap == old
    assert snap['metrics'] == {'budget': 5}


def test_immediate_underflow_cannot_be_repaired_by_outcome():
    p = package()
    p['parameters']['cost'] = -6
    p['scenes'][0]['choices'][0]['outcomes'][0]['effects'][0]['delta'] = 10
    assert cw.start_choice_world(p)['status'] == 'blocked'


def test_zero_probability_outcome_is_not_an_eligibility_risk():
    p = package()
    p['parameters']['good_odds'] = 10000
    bad = p['scenes'][0]['choices'][0]['outcomes'][1]
    bad['probability_bps'] = 0
    bad['effects'] = [{'action': 'adjust_metric', 'metric_id': 'budget', 'delta': -999}]
    assert cw.start_choice_world(p)['status'] == 'active'


def test_requirements_check_current_metric_and_safe_disabled_reason():
    p = package()
    p['scenes'][0]['choices'][0]['requirements'][0]['minimum'] = 6
    snap = cw.start_choice_world(p)
    assert snap['status'] == 'blocked'
    assert isinstance(cw.choice_options(snap)[0]['disabled_reason'], str)


def test_idempotent_old_action_returns_current_state_and_conflict_rejected():
    start = cw.start_choice_world(package())
    first = cw.step_choice_world(start, 'build', 'request1')
    final = cw.step_choice_world(first, 'finish', 'request2')
    assert final['status'] == 'completed'
    assert cw.step_choice_world(final, 'build', 'request1') == final
    with pytest.raises(ValueError):
        cw.step_choice_world(final, 'finish', 'request1')
    assert start['metrics'] == {'budget': 5}
    assert start['history'] == []
    assert final['step_count'] == 2


def test_draws_ignore_action_and_branch_identity_and_preserve_fork_history():
    p = package()
    original = cw.start_choice_world(p, seed=7, world_id=12)
    fork = cw.fork_choice_world(original, 'alternate')
    one = cw.step_choice_world(original, 'build', 'one')
    two = cw.step_choice_world(fork, 'build', 'two')
    assert one['metrics'] == two['metrics']
    assert one['history'][0]['draw_bps'] == two['history'][0]['draw_bps']
    assert one['history'][0]['outcome_id'] == two['history'][0]['outcome_id']
    later_fork = cw.fork_choice_world(one, 'later')
    assert later_fork['history'] == one['history']
    assert later_fork['parent_branch_id'] == 'main'
    assert cw.validate_choice_snapshot(later_fork) == later_fork


@pytest.mark.parametrize('change', [
    lambda s: s['metrics'].update(budget=10),
    lambda s: s.update(step_count=0),
    lambda s: s.update(status='completed'),
    lambda s: s.update(seed=8),
    lambda s: s['package']['assumptions'].append('Changed source.'),
    lambda s: s['history'][0].update(outcome_id='forged'),
    lambda s: s['history'][0]['metrics_after'].update(budget=10),
    lambda s: s.update(scene_id='plan'),
])
def test_replay_rejects_forged_snapshots(change):
    snap = cw.step_choice_world(cw.start_choice_world(package()), 'build', 'a')
    change(snap)
    with pytest.raises(ValueError):
        cw.validate_choice_snapshot(snap)


def test_policy_uses_authored_fallback_and_counts_blocked_worlds():
    p = package()
    impossible = deepcopy(p['scenes'][0]['choices'][0])
    impossible['id'] = 'impossible'
    impossible['requirements'][0]['minimum'] = 6
    p['scenes'][0]['choices'].insert(0, impossible)
    p['policy']['plan'] = ['impossible', 'build']
    result = cw.run_choice_policy(p, worlds=8, seed=5)
    assert result['status_counts'] == {'completed': 8, 'blocked': 0}
    assert sum(path['count'] for path in result['paths']) == 8
    assert all(path['path'][0]['choice_id'] == 'build' for path in result['paths'])
    p['policy']['plan'] = ['impossible']
    blocked = cw.run_choice_policy(p, worlds=3)
    assert blocked['status_counts'] == {'completed': 0, 'blocked': 3}
    assert blocked['metrics'][0]['mean'] == 5
    assert blocked['paths'][0]['count'] == 3


@pytest.mark.parametrize('kwargs', [{'worlds': True}, {'worlds': 0}, {'worlds': 10001}, {'seed': True}, {'seed': 10**100}])
def test_rejects_unbounded_batch_inputs(kwargs):
    with pytest.raises(ValueError):
        cw.run_choice_policy(package(), **kwargs)


def test_json_and_graph_size_limits():
    for p in [None, {'schema_version': 'choice-world.v1'}, package()]:
        if isinstance(p, dict) and 'scenes' in p:
            p['event_description'] = 'x' * 5000
        with pytest.raises(ValueError):
            cw.validate_choice_world(p)
    recursive = package()
    recursive['assumptions'].append(recursive)
    with pytest.raises(ValueError):
        cw.validate_choice_world(recursive)


def test_example_and_draft_are_consistent_and_executable():
    root = Path(__file__).parents[1] / 'examples'
    example = json.loads((root / 'choice-world.v1.json').read_text())
    draft = json.loads((root / 'choice-world-draft.v1.json').read_text())
    assert draft['engine_input'] == example
    assert len(draft['fields']) >= 2
    assert all(field['type'] == 'integer' for field in draft['fields'])
    result = cw.run_choice_policy(example, worlds=20)
    assert sum(result['status_counts'].values()) == 20
    assert cw.choice_world_capabilities()['schema_version'] == 'choice-world.v1'


def test_initially_blocked_worlds_are_retained_without_attempting_a_choice():
    p = package()
    p['scenes'][0]['choices'][0]['requirements'][0]['minimum'] = 6
    result = cw.run_choice_policy(p, worlds=3)
    assert result['status_counts'] == {'completed': 0, 'blocked': 3}
    assert result['blocked_reasons'] == {'no_eligible_choices': 3}
    assert len(result['paths']) == 1
    assert result['paths'][0]['path'] == []
    assert result['paths'][0]['count'] == 3
    assert result['paths'][0]['frequency'] == 1
    assert result['paths'][0]['metrics']['budget']['mean'] == 5


def test_same_stage_effects_are_atomic_per_metric():
    p = package()
    p['scenes'][0]['choices'][0]['immediate_effects'] = [
        {'action': 'adjust_metric', 'metric_id': 'budget', 'delta': -8},
        {'action': 'adjust_metric', 'metric_id': 'budget', 'delta': 6}]
    snap = cw.step_choice_world(cw.start_choice_world(p), 'build', 'a')
    assert snap['metrics']['budget'] in {3, 4}


def test_engine_identity_is_part_of_snapshot_replay_contract():
    snap = cw.start_choice_world(package())
    snap['engine_sha256'] = '0' * 64
    with pytest.raises(ValueError, match='engine'):
        cw.validate_choice_snapshot(snap)


def test_grouped_path_statistics_use_all_actual_final_metrics():
    result = cw.run_choice_policy(package(), worlds=40, seed=4)
    assert sum(path['count'] for path in result['paths']) == 40
    for path in result['paths']:
        expected = 4 if path['path'][0]['outcome_id'] == 'good' else 3
        assert path['metrics']['budget'] == {
            'minimum': expected, 'maximum': expected, 'mean': expected,
            'median': expected, 'p05': expected, 'p95': expected,
        }
    assert 3 <= result['metrics'][0]['p05'] <= result['metrics'][0]['median'] <= result['metrics'][0]['p95'] <= 4


@pytest.mark.parametrize('kind', ['scenes', 'choices', 'outcomes', 'metrics', 'effects'])
def test_rejects_structural_size_limits_before_execution(kind):
    p = package()
    if kind == 'scenes':
        p['scenes'] = [dict(deepcopy(p['scenes'][0]), id=f'scene-{i}') for i in range(17)]
    elif kind == 'choices':
        p['scenes'][0]['choices'] *= 9
    elif kind == 'outcomes':
        p['scenes'][0]['choices'][0]['outcomes'] *= 9
    elif kind == 'metrics':
        p['metrics'] = [dict(p['metrics'][0], id=f'metric-{i}') for i in range(33)]
    else:
        p['scenes'][0]['choices'][0]['immediate_effects'] *= 33
    with pytest.raises(ValueError):
        cw.validate_choice_world(p)


def test_batch_rejects_effect_work_before_starting_worlds():
    p = package()
    p['scenes'][0]['choices'] = [dict(deepcopy(p['scenes'][0]['choices'][0]), id=f'choice-{i}') for i in range(8)]
    for choice in p['scenes'][0]['choices']:
        choice['immediate_effects'] = [{'action': 'adjust_metric', 'metric_id': 'budget', 'delta': 0}] * 32
    p['policy']['plan'] = ['choice-0']
    assert cw.validate_choice_world(p) == p
    with pytest.raises(ValueError, match='work'):
        cw.run_choice_policy(p, worlds=10000)


def test_invalid_action_preserves_source_and_replayed_future():
    snapshot = cw.start_choice_world(package(), seed=12)
    old = deepcopy(snapshot)
    with pytest.raises(ValueError):
        cw.step_choice_world(snapshot, 'unknown', 'a')
    with pytest.raises(ValueError):
        cw.step_choice_world(snapshot, 'build', '')
    assert snapshot == old
    after = cw.step_choice_world(snapshot, 'build', 'valid')
    direct = cw.step_choice_world(old, 'build', 'other')
    assert after['metrics'] == direct['metrics']
    assert after['history'][0]['outcome_id'] == direct['history'][0]['outcome_id']


def test_empty_draft_authoring_request_exports_complete_choice_input_contract():
    from decision_lab.scenario_authoring import prepare_authoring_request
    empty = {'schema_version': 'scenario-draft.v1', 'id': 'release', 'revision': 0,
             'event_description': 'Author supplied release choices.', 'fields': [], 'engine_input': None}
    request = prepare_authoring_request(empty, model='user-selected-agent')
    exported = json.loads(request['messages'][0]['content'].split('Capabilities:\n', 1)[1])
    details = next(item['details'] for item in exported['modules'] if item['schema_version'] == 'choice-world.v1')
    contracts = details['fields']
    p = package()
    specimens = {
        'package': p, 'persona': p['personas'][0], 'metric': p['metrics'][0],
        'scene': p['scenes'][0], 'choice': p['scenes'][0]['choices'][0],
        'requirement': p['scenes'][0]['choices'][0]['requirements'][0],
        'effect': p['scenes'][0]['choices'][0]['immediate_effects'][0],
        'outcome': p['scenes'][0]['choices'][0]['outcomes'][0],
        'probability_provenance': p['scenes'][0]['choices'][0]['probability_provenance'],
    }
    for name, specimen in specimens.items():
        assert set(contracts[name]['required']) == set(specimen)
        assert set(contracts[name]['fields']) == set(specimen)
        assert contracts[name]['additional_fields'] is False
    assert contracts['effect']['fields']['action']['const'] == 'adjust_metric'
    assert contracts['number']['parameter_reference']['required'] == ['parameter']
    assert contracts['outcome']['fields']['next_scene_id']['nullable'] is True
    assert contracts['policy']['choice_order'] == 'first_eligible'
    assert details['defaults_or_estimates'] is None
    assert details['assumptions']['probability_calibration'] == 'supplied_unverified'
    assert request['usage']['model_calls'] == 0
    assert json.loads(request['messages'][1]['content'])['engine_input'] is None


def test_published_metric_and_probability_bounds_match_actual_validation():
    contracts = cw.choice_world_capabilities()['fields']
    p = package()
    p['metrics'][0]['maximum'] = contracts['metric']['fields']['maximum']['maximum']
    assert cw.validate_choice_world(p)['metrics'][0]['maximum'] == 10**12
    p['metrics'][0]['maximum'] += 1
    with pytest.raises(ValueError):
        cw.validate_choice_world(p)
    p = package()
    bound = contracts['outcome']['fields']['probability_bps']['maximum']
    p['scenes'][0]['choices'][0]['outcomes'][0]['probability_bps'] = bound
    p['scenes'][0]['choices'][0]['outcomes'][1]['probability_bps'] = 0
    assert cw.validate_choice_world(p) == p
    p['scenes'][0]['choices'][0]['outcomes'][0]['probability_bps'] = bound + 1
    with pytest.raises(ValueError):
        cw.validate_choice_world(p)
