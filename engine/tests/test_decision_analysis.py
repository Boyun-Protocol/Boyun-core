"""Conditional launch feasibility uses replayed balances, never paper valuations."""
from copy import deepcopy
from fractions import Fraction

import pytest

from decision_lab.agent_worlds import AgentWorld
from decision_lab.decision_analysis import analyze_launch_result


def completed_report(*, fee=30, slippage=500, tokens=3000000, pool_tokens=1000000,
                     capital=1000000, launch_cost=100000, lp_cash=400000, actual_buy=0):
    world = {
        'schema_version': 'agent-world.v1', 'id': 'decision-test',
        'event_description': 'Fictional launch with explicitly supplied financial assumptions.',
        'network': 'near', 'rounds': 1,
        'market': {'project_capital_cents': capital, 'launch_cost_cents': launch_cost,
                   'lp_cash_cents': lp_cash, 'project_token_units': tokens,
                   'lp_token_units': pool_tokens, 'fee_bps': fee, 'max_slippage_bps': slippage},
        'agents': [{'id': 'observer', 'name': 'Observer', 'role': 'observer',
                    'description': 'Does not buy without evidence.', 'goal': 'Observe',
                    'initial_cash_cents': 10000000, 'position_limit_cents': 10000000,
                    'allowed_actions': ['hold', 'buy'], 'attention_capacity': 1,
                    'subscriptions': ['news']}],
        'events': [{'id': 'supplied-event', 'round': 1, 'text': 'Fictional event', 'provenance': 'assumed'}], 'assumptions': ['Synthetic pool and balances, not empirical odds.'],
    }
    engine = AgentWorld(world)
    observation = engine.observations()['observer']
    engine.advance([{'schema_version': 'agent-turn.v1', 'actor_id': 'observer', 'round': 1,
                     'observation_sha256': observation['observation_sha256'],
                     'action': {'kind': 'buy' if actual_buy else 'hold', 'amount': actual_buy,
                                'evidence_ids': ['event:supplied-event'] if actual_buy else []},
                     'message': None, 'reason': 'No personally observed evidence.'}])
    return engine.report()


def test_actual_and_hypothetical_cash_remain_separate_and_detached():
    report = completed_report()
    before = deepcopy(report)
    result = analyze_launch_result(report)
    assert report == before
    assert result['schema_version'] == 'decision-financial-analysis.v1'
    assert result['no_launch'] == {'ending_cash_cents': 1000000, 'profit_cents': 0}
    assert result['actual'] == {
        'initial_capital_cents': 1000000, 'ending_cash_cents': 500000,
        'paid_costs_cents': 100000, 'locked_lp_cash_deposit_cents': 400000,
        'locked_lp_shares': report['locked_project_lp_shares'],
        'unsold_token_units': 2000000, 'cash_profit_cents': -500000,
    }
    exit_quote = result['hypothetical_exit']
    effective = 2000000 * 9970 // 10000
    proceeds = 400000 * effective // (1000000 + effective)
    assert exit_quote == {
        'exit_token_units': 2000000, 'cash_proceeds_cents': proceeds,
        'ending_cash_cents': 500000 + proceeds, 'profit_cents': proceeds - 500000,
        'fee_token_units': 2000000 - effective, 'remaining_token_units': 0,
    }
    assert len(result['identity']['report_sha256']) == 64
    assert result == analyze_launch_result(deepcopy(report))


def test_break_even_is_minimal_to_the_cent():
    result = analyze_launch_result(completed_report(), demand_cents=[0, 1000000])
    boundary = result['break_even']
    assert boundary['status'] == 'reachable'
    minimum = boundary['minimum_additional_buy_cents']
    assert 0 < minimum <= boundary['search_bound_cents']
    edge = analyze_launch_result(completed_report(), demand_cents=[minimum - 1, minimum])
    assert edge['demand_stress'][0]['profit_cents'] < 0
    assert edge['demand_stress'][1]['profit_cents'] >= 0
    assert boundary['previous_cent_profit_cents'] == edge['demand_stress'][0]['profit_cents']


def test_manual_integer_stress_calculation_includes_both_fees():
    report = completed_report()
    result = analyze_launch_result(report, exit_token_units=100000, demand_cents=[0, 100000])
    row = result['demand_stress'][1]
    effective_buy = 100000 * 9970 // 10000
    bought = 1000000 * effective_buy // (400000 + effective_buy)
    effective_sell = 100000 * 9970 // 10000
    exact = Fraction(500000 * effective_sell, 1000000 - bought + effective_sell)
    assert row == {
        'external_buy_cents': 100000, 'bought_token_units': bought,
        'buy_fee_cash_cents': 300, 'exit_cash_proceeds_cents': int(exact),
        'ending_project_cash_cents': 500000 + int(exact), 'profit_cents': int(exact) - 500000,
        'exit_fee_token_units': 300,
    }
    assert result['hypothetical_exit']['remaining_token_units'] == 1900000


def test_actual_complete_report_required_and_tampering_rejected():
    report = completed_report()
    for key in ('balances', 'project_cash_profit_cents', 'history'):
        changed = deepcopy(report)
        if key == 'balances': changed[key]['project']['cash_cents'] += 1
        elif key == 'history': changed[key] = []
        else: changed[key] += 1
        with pytest.raises(ValueError): analyze_launch_result(changed)
    active = deepcopy(report)
    active['status'] = 'active'
    with pytest.raises(ValueError): analyze_launch_result(active)
    for invalid in ({}, None, [], {'schema_version': 'agent-world-results.v1'}):
        with pytest.raises(ValueError): analyze_launch_result(invalid)


@pytest.mark.parametrize('kwargs', [
    {'exit_token_units': -1}, {'exit_token_units': True}, {'exit_token_units': 1.0},
    {'exit_token_units': 2000001}, {'max_external_cash_cents': -1},
    {'max_external_cash_cents': True}, {'max_external_cash_cents': 10**12 + 1},
    {'demand_cents': [True]}, {'demand_cents': [-1]}, {'demand_cents': [1.0]},
    {'demand_cents': '100'}, {'demand_cents': [0] * 33},
    {'max_external_cash_cents': 10, 'demand_cents': [11]},
])
def test_strict_bounded_user_inputs(kwargs):
    with pytest.raises(ValueError): analyze_launch_result(completed_report(), **kwargs)


def test_zero_exit_tokens_and_no_unsold_tokens():
    for report, kwargs in ((completed_report(), {'exit_token_units': 0}),
                           (completed_report(tokens=1000000), {})):
        result = analyze_launch_result(report, **kwargs)
        assert result['hypothetical_exit']['cash_proceeds_cents'] == 0
        assert result['break_even']['status'] == 'no_exit_tokens'
        assert result['break_even']['minimum_additional_buy_cents'] is None
        assert all(row['profit_cents'] == -500000 for row in result['demand_stress'])


def test_unreachable_is_only_within_bound_not_universal_claim():
    result = analyze_launch_result(completed_report(), max_external_cash_cents=0)
    assert result['break_even']['status'] == 'not_reached_within_bound'
    assert result['break_even']['minimum_additional_buy_cents'] is None
    assert result['break_even']['search_bound_cents'] == 0
    assert len(result['demand_stress']) == 1


def test_tiny_rounded_outputs_and_maximum_fee_are_valid_not_fake_success():
    report = completed_report(fee=9999, tokens=1000001)
    result = analyze_launch_result(report, exit_token_units=1)
    assert result['hypothetical_exit']['fee_token_units'] == 1
    assert result['hypothetical_exit']['cash_proceeds_cents'] == 0
    assert result['break_even']['status'] == 'not_reached_within_bound'
    assert all(row['exit_cash_proceeds_cents'] == 0 for row in result['demand_stress'])


@pytest.mark.parametrize('slippage', [0, 10000])
def test_world_slippage_bounds_do_not_turn_quote_into_forecast(slippage):
    result = analyze_launch_result(completed_report(slippage=slippage))
    assert result['hypothetical_exit']['cash_proceeds_cents'] > 0
    assert any('slippage' in item.lower() for item in result['limitations'])


def test_monotonic_demand_and_exact_search_for_fee_and_integer_edge_cases():
    for fee in (0, 30, 2500, 9999):
        report = completed_report(fee=fee, tokens=37, pool_tokens=19,
                                  capital=20, launch_cost=2, lp_cash=10)
        result = analyze_launch_result(report, demand_cents=list(range(32)),
                                       max_external_cash_cents=31)
        profits = [row['profit_cents'] for row in result['demand_stress']]
        assert profits == sorted(profits)
        crossing = next((i for i, p in enumerate(profits) if p >= 0), None)
        assert result['break_even']['minimum_additional_buy_cents'] == crossing


def test_already_break_even_requires_no_new_demand_but_still_hypothetical_exit():
    report = completed_report(actual_buy=2000000)
    result = analyze_launch_result(report)
    assert result['actual']['cash_profit_cents'] == -500000
    assert result['hypothetical_exit']['profit_cents'] >= 0
    assert result['break_even']['status'] == 'already_break_even'
    assert result['break_even']['minimum_additional_buy_cents'] == 0
    assert result['break_even']['previous_cent_profit_cents'] is None


def test_valid_but_active_report_is_not_a_completed_decision():
    active = AgentWorld(completed_report()['world']).report()
    with pytest.raises(ValueError, match='completed'):
        analyze_launch_result(active)


def test_large_bound_search_is_bounded_and_demand_order_is_canonical():
    report = completed_report()
    result = analyze_launch_result(report, demand_cents=[10**12, 0, 10**12],
                                   max_external_cash_cents=10**12)
    assert len(result['demand_stress']) == 2
    assert result['demand_stress'][0]['external_buy_cents'] == 0
    assert result['break_even']['status'] == 'reachable'
    assert result['break_even']['minimum_additional_buy_cents'] < 10**12
    assert all(type(row['profit_cents']) is int for row in result['demand_stress'])
