"""Behavioral contracts for supplied, bounded event scenarios."""
from copy import deepcopy
import json
from pathlib import Path

import pytest


def api():
    # A missing implementation is an explicit RED assertion, not collection failure.
    import importlib.util
    assert importlib.util.find_spec('decision_lab.event_chains'), 'event-chain evaluator is not implemented'
    from decision_lab import event_chains
    return event_chains


def chain():
    return {
        'schema_version': 'event-chain.v1', 'id': 'test-chain',
        'event_description': 'Evaluate supplied score shocks.', 'parameters': {'gain': 7, 'odds': 2500},
        'personas': [{'id': 'reviewer', 'name': 'Reviewer', 'description': 'Explicit rule author.',
                      'role': 'evaluator', 'allowed_actions': ['adjust_metric']}],
        'metrics': [{'id': 'score', 'unit': 'declared_points', 'initial': 10}],
        'rules': [{'id': 'review', 'at_tick': 0, 'actor_id': 'reviewer', 'requires': [],
                   'outcomes': [
                       {'id': 'positive', 'probability_bps': {'parameter': 'odds'}, 'effects': [
                           {'action': 'adjust_metric', 'metric_id': 'score', 'delta': {'parameter': 'gain'}}]},
                       {'id': 'neutral', 'probability_bps': 7500, 'effects': []}],
                   'probability_provenance': {'status': 'assumed', 'rationale': 'Illustrative supplied mixture.', 'source_refs': []}}],
        'horizon_ticks': 2, 'assumptions': ['Rule probabilities are assumptions, not adoption forecasts.'],
    }


def deterministic(value, outcome='positive'):
    for option in value['rules'][0]['outcomes']:
        option['probability_bps'] = 10000 if option['id'] == outcome else 0
    return value


def followup():
    return {'id': 'followup', 'at_tick': 1, 'actor_id': 'reviewer',
            'requires': [{'event_id': 'review', 'outcome_id': 'positive'}],
            'outcomes': [{'id': 'done', 'probability_bps': 10000, 'effects': [
                {'action': 'adjust_metric', 'metric_id': 'score', 'delta': -2}]}],
            'probability_provenance': {'status': 'model_proposal', 'rationale': 'Explicit conditional rule.', 'source_refs': []}}


def test_replay_preserves_input_and_reports_actual_worlds_and_quantiles():
    mod = api()
    value = deterministic(chain())
    original = deepcopy(value)
    checked = mod.validate_event_chain(value)
    checked['metrics'][0]['initial'] = -50
    assert value == original
    result = mod.run_event_chain(value, worlds=3, seed=8)
    assert result == mod.run_event_chain(value, worlds=3, seed=8)
    assert value == original
    assert result['worlds'] == 3
    assert [w['metrics'] for w in result['world_results']] == [{'score': 17}] * 3
    assert result['metrics']['score'] == {'unit': 'declared_points', 'mean': 17.0, 'median': 17, 'p05': 17, 'p95': 17}
    assert result['paths'] == [{'selected_outcomes': {'review': 'positive'}, 'count': 3, 'frequency': 1.0}]
    trace = result['world_results'][0]['trace'][0]
    assert trace['rule_id'] == 'review' and trace['outcome_id'] == 'positive'
    assert 0 <= trace['draw_bps'] < 10000
    assert trace['effects'] == [{'action': 'adjust_metric', 'metric_id': 'score', 'delta': 7}]


def test_weighted_frequency_and_statistics_come_from_completed_worlds():
    result = api().run_event_chain(chain(), worlds=4000, seed=42)
    positive = sum(w['selected_outcomes']['review'] == 'positive' for w in result['world_results'])
    assert 850 < positive < 1150  # Wide predeclared bound around 1000, not a calibration assertion.
    assert sum(p['count'] for p in result['paths']) == 4000
    assert result['metrics']['score'] == {'unit': 'declared_points', 'mean': (40000 + positive * 7) / 4000,
                                         'median': 10, 'p05': 10, 'p95': 17}


def test_dependencies_skip_unmet_and_execute_met_with_stable_order():
    value = deterministic(chain())
    value['rules'].append(followup())
    result = api().run_event_chain(value, worlds=1)
    assert result['world_results'][0]['metrics'] == {'score': 15}
    assert list(result['world_results'][0]['selected_outcomes']) == ['review', 'followup']
    reordered = deepcopy(value)
    reordered['rules'].reverse()
    assert api().run_event_chain(reordered, worlds=3) == api().run_event_chain(value, worlds=3)
    deterministic(value, 'neutral')
    skipped = api().run_event_chain(value, worlds=1)['world_results'][0]
    assert skipped['metrics'] == {'score': 10}
    assert skipped['selected_outcomes'] == {'review': 'neutral'}
    assert skipped['trace'][1] == {'rule_id': 'followup', 'at_tick': 1, 'status': 'skipped_dependency'}


def test_named_draws_survive_adding_unrelated_rule():
    value = chain()
    before = api().run_event_chain(value, worlds=200, seed=-9)
    added = followup()
    added.update(id='earlier-alphabetically', at_tick=0, requires=[])
    value['rules'].append(added)
    after = api().run_event_chain(value, worlds=200, seed=-9)
    assert [w['selected_outcomes']['review'] for w in before['world_results']] == [w['selected_outcomes']['review'] for w in after['world_results']]


@pytest.mark.parametrize('mutation', [
    lambda v: v.update(extra='ignored'),
    lambda v: v.update(horizon_ticks=True),
    lambda v: v['parameters'].update(odds=2500.0),
    lambda v: v['parameters'].update(gain=float('nan')),
    lambda v: v['parameters'].update(gain=True),
    lambda v: v['rules'][0]['outcomes'][0].update(probability_bps=10001),
    lambda v: v['rules'][0]['outcomes'][0].update(probability_bps={'parameter': 'absent'}),
    lambda v: v['rules'][0]['outcomes'][0]['effects'][0].update(action='borrow'),
    lambda v: v['rules'][0]['outcomes'][0]['effects'][0].update(metric_id='missing'),
    lambda v: v['rules'][0]['outcomes'][0]['effects'][0].update(delta={'parameter': 'missing'}),
    lambda v: v['personas'][0].update(allowed_actions=[]),
    lambda v: v['rules'][0].update(actor_id='missing'),
    lambda v: v['rules'][0].update(at_tick=3),
    lambda v: v['rules'][0]['probability_provenance'].update(status='calibrated'),
    lambda v: v['rules'][0]['outcomes'].append(deepcopy(v['rules'][0]['outcomes'][0])),
    lambda v: v['metrics'].append(deepcopy(v['metrics'][0])),
])
def test_invalid_values_and_unknown_capabilities_rejected_before_execution(mutation):
    value = chain()
    mutation(value)
    original = deepcopy(value)
    with pytest.raises(ValueError):
        api().run_event_chain(value, worlds=1)
    # NaN cannot compare equal to a copy; serialization still proves no mutation.
    assert json.dumps(value, sort_keys=True) == json.dumps(original, sort_keys=True)


@pytest.mark.parametrize('dependency,tick', [
    ({'event_id': 'absent', 'outcome_id': 'positive'}, 1),
    ({'event_id': 'review', 'outcome_id': 'absent'}, 1),
    ({'event_id': 'review', 'outcome_id': 'positive'}, 0),
    ({'event_id': 'followup', 'outcome_id': 'done'}, 1),
])
def test_missing_dependencies_and_same_tick_or_cyclic_edges_are_rejected(dependency, tick):
    value = chain()
    child = followup()
    child.update(requires=[dependency], at_tick=tick)
    value['rules'].append(child)
    with pytest.raises(ValueError):
        api().validate_event_chain(value)


def test_atomic_effects_are_combined_and_all_branches_are_prevalidated():
    value = deterministic(chain())
    value['rules'][0]['outcomes'][0]['effects'].append({'action': 'adjust_metric', 'metric_id': 'score', 'delta': -3})
    assert api().run_event_chain(value, worlds=1)['world_results'][0]['metrics']['score'] == 14
    # Invalid unreachable actions also fail before executing the deterministic branch.
    value['rules'][0]['outcomes'][1]['effects'] = [{'action': 'transfer_cash', 'metric_id': 'score', 'delta': 4}]
    with pytest.raises(ValueError):
        api().run_event_chain(value, worlds=1)


def test_resource_and_numeric_bounds_reject_before_world_execution():
    mod = api()
    for worlds in [0, True, 10001, 1.5]:
        with pytest.raises(ValueError):
            mod.run_event_chain(chain(), worlds=worlds)
    for seed in [True, '42', 2**65]:
        with pytest.raises(ValueError):
            mod.run_event_chain(chain(), seed=seed)
    cases = []
    value = chain(); value['event_description'] = 'x' * 300000; cases.append(value)
    value = chain(); value['parameters']['gain'] = 10**20; cases.append(value)
    value = chain(); value['metrics'][0]['initial'] = 10**12; cases.append(value)
    value = chain(); value['horizon_ticks'] = 10001; cases.append(value)
    value = chain(); value['rules'] = [dict(deepcopy(value['rules'][0]), id=f'r{i}') for i in range(129)]; cases.append(value)
    value = chain(); value['personas'] *= 65; cases.append(value)
    value = chain(); nested = {}; value['parameters']['gain'] = nested
    for _ in range(15):
        nested['nested'] = {}; nested = nested['nested']
    cases.append(value)

    for value in cases:
        with pytest.raises(ValueError):
            mod.validate_event_chain(value)
    value = chain()
    value['rules'] = [dict(deepcopy(value['rules'][0]), id=f'r{i}') for i in range(11)]
    with pytest.raises(ValueError):
        mod.run_event_chain(value, worlds=10000)


def test_examples_compute_declared_metrics_and_disclose_limits():
    mod = api()
    root = Path(__file__).resolve().parents[1] / 'examples'
    ticker = json.loads((root / 'ticker-evaluation.v1.json').read_text())
    stress = json.loads((root / 'defi-stress.v1.json').read_text())
    ranked = mod.run_event_chain(ticker, worlds=2)
    assert ranked['world_results'][0]['metrics'] == {'nova_score': 82, 'moss_score': 74}
    assert ranked['metrics']['nova_score']['unit'] == 'declared_rubric_points'
    stressed = mod.run_event_chain(stress, worlds=100)
    assert stressed['metrics']['declared_loss']['unit'] == 'declared_USD_payoff'
    assert all(w['metrics']['declared_loss'] >= 0 for w in stressed['world_results'])
    assert 'not withdrawable cash' in ' '.join(stressed['limitations'])
    assert mod.event_chain_capabilities()['actions'] == ['adjust_metric']


def test_output_budget_rejects_large_trace_before_execution():
    # Repeating long provenance on 10,000 worlds would make a very large result.
    value = chain()
    value['rules'][0]['probability_provenance']['rationale'] = 'a' * 4000
    value['rules'][0]['probability_provenance']['source_refs'] = ['b' * 4000] * 20
    value['rules'][0]['outcomes'][0]['effects'] *= 32
    value['rules'][0]['outcomes'][1]['effects'] = deepcopy(value['rules'][0]['outcomes'][0]['effects'])
    with pytest.raises(ValueError, match='output'):
        api().run_event_chain(value, worlds=10000)


def test_requires_is_and_and_equal_tick_execution_has_canonical_identity_order():
    value = deterministic(chain())
    peer = deepcopy(value['rules'][0])
    peer['id'] = 'a-peer'
    deterministic({'rules': [peer]}, 'neutral')
    child = followup()
    child['requires'].append({'event_id': 'a-peer', 'outcome_id': 'positive'})
    value['rules'].extend([child, peer])
    world = api().run_event_chain(value, worlds=1)['world_results'][0]
    assert [entry['rule_id'] for entry in world['trace']] == ['a-peer', 'review', 'followup']
    assert world['metrics'] == {'score': 17}
    assert world['trace'][-1]['status'] == 'skipped_dependency'
    deterministic({'rules': [peer]})
    assert api().run_event_chain(value, worlds=1)['world_results'][0]['metrics'] == {'score': 22}


def test_nearest_rank_even_sample_median_uses_lower_observation():
    # The first two named seed=42 draws straddle the 25% branch boundary.
    result = api().run_event_chain(chain(), worlds=2, seed=42)
    samples = sorted(w['metrics']['score'] for w in result['world_results'])
    assert samples == [10, 17]
    assert result['metrics']['score'] == {'unit': 'declared_points', 'mean': 13.5, 'median': 10, 'p05': 10, 'p95': 17}
