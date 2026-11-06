from __future__ import annotations

import json

import pytest

from decision_lab.launch_estimate import (
    CURVE_TOKENS, SUPPLY, VIRTUAL_SOL, VIRTUAL_TOKENS, buy, estimate_launch, sell, sensitivity,
    usd_to_lamports, validate_params,
)


def probabilities(**overrides):
    base = {
        'large_buyer': {'hold': .8, 'buy_small': .15, 'buy_half': .04, 'buy_all': .01},
        'retail_momentum': {'hold': .4, 'buy_small': .35, 'buy_half': .1, 'buy_all': .15},
        'kol_a': {'hold': .6, 'sell_half': .15, 'sell_all': .25},
    }
    base.update(overrides)
    return base


def curve():
    return {'sold': 0, 'real_left': CURVE_TOKENS, 'virtual_sol': VIRTUAL_SOL,
            'virtual_tokens': VIRTUAL_TOKENS, 'migrated': False, 'pool_sol': 0,
            'pool_tokens': 0}


def test_buy_then_sell_round_trip_costs_only_fees():
    state = curve()
    quote = usd_to_lamports(1000, 90)
    tokens = buy(state, quote, 100)
    returned = sell(state, tokens, 100)
    assert returned < quote
    assert returned > quote * 0.97          # two 1% fees plus a little curve impact
    assert state['sold'] == 0


def test_curve_exhausts_near_the_documented_migration_level():
    state = curve()
    sol = 0
    while state['real_left'] > 0 and sol < 200:
        buy(state, 1 * 10**9, 100)          # one SOL at a time, no fee assumption drift
        sol += 1
    assert 80 <= sol <= 90


def test_bootstrap_share_matches_the_curve_calculation():
    result = estimate_launch(probabilities(kol_a={'hold': 1.0}), {'worlds': 5})
    params = result['params']
    state = curve()
    tokens = buy(state, usd_to_lamports(params['bootstrap_usd'], params['sol_usd']), params['fee_bps'])
    share = tokens / SUPPLY
    assert 0.68 < share < 0.71


def test_kol_allocation_is_three_percent_in_total():
    result = estimate_launch(probabilities(), {'worlds': 5})
    params = result['params']
    per_actor = SUPPLY * params['kol_supply_bps'] // 10_000 // len(params['kol_actors'])
    assert per_actor * len(params['kol_actors']) == SUPPLY * 3 // 100


def test_same_seed_replays_exactly_and_another_seed_differs():
    first = estimate_launch(probabilities(), {'worlds': 400, 'seed': 11})
    second = estimate_launch(probabilities(), {'worlds': 400, 'seed': 11})
    other = estimate_launch(probabilities(), {'worlds': 400, 'seed': 12})
    assert first['net_quantiles'] == second['net_quantiles']
    assert first['by_bucket'] == second['by_bucket']
    assert (first['net_quantiles'], first['by_bucket']) != (other['net_quantiles'], other['by_bucket'])


def test_outcome_classes_follow_deployed_capital():
    only_holds = estimate_launch({'retail_patient': {'hold': 1.0}}, {'worlds': 50})
    whale = estimate_launch({'large_buyer': {'buy_all': 1.0}}, {'worlds': 50})
    assert 'whale outside money' in whale['by_bucket']
    assert 'whale outside money' not in only_holds['by_bucket']
    assert only_holds['by_bucket']['no outside money']['share'] == 1.0


def test_exit_hour_follows_the_decay_half_life():
    for half_life in (12, 24, 48):
        result = estimate_launch(probabilities(), {'worlds': 20, 'half_life_hours': half_life})
        assert result['exit_hour'] == half_life * 2


def test_higher_bootstrap_buys_more_supply_and_costs_more():
    small = estimate_launch(probabilities(), {'worlds': 200, 'bootstrap_usd': 3_000})
    large = estimate_launch(probabilities(), {'worlds': 200, 'bootstrap_usd': 7_000})
    assert small['net_quantiles']['p05'] != large['net_quantiles']['p05']
    assert small['params']['bootstrap_usd'] == 3_000


def test_summary_is_self_consistent():
    result = estimate_launch(probabilities(), {'worlds': 500})
    assert result['worlds'] == 500
    assert result['profit_count'] <= 500
    assert result['net_min'] <= result['net_quantiles']['p50'] <= result['net_max']
    assert 0 <= result['net_cash_usd']['share_positive'] <= 1
    assert sum(row['out_of_100'] for row in result['scenarios']) in range(99, 102)
    assert sum(entry['n'] for entry in result['by_bucket'].values()) == 500
    assert result['limitations']


def test_sensitivity_covers_every_declared_arm():
    result = sensitivity(probabilities(), {'worlds': 60}, worlds=40)
    assert result['worlds_per_arm'] == 40
    assert len(result['arms']) == 9
    assert {row['parameter'] for row in result['arms']} == {
        'sol_usd', 'half_life_hours', 'bootstrap_usd'}


def test_parameters_are_validated():
    with pytest.raises(ValueError, match='unknown parameter'):
        validate_params({'nope': 1})
    with pytest.raises(ValueError, match='integer outside bounds'):
        validate_params({'sol_usd': 0})
    with pytest.raises(ValueError, match='integer outside bounds'):
        validate_params({'bootstrap_usd': 10**9})
    with pytest.raises(ValueError, match='probabilities must sum to one'):
        estimate_launch({'a': {'hold': .5}}, {'worlds': 5})
    with pytest.raises(ValueError, match='bounded actor capital map required'):
        validate_params({'capital_usd': {}})
    with pytest.raises(ValueError, match='integer outside bounds'):
        validate_params({'worlds': 10**9})
