"""Outcome groups summarize actual worlds, never generated narratives or odds."""
from copy import deepcopy

import pytest

from decision_lab.simulation import default_scenario, load_pool, simulate


def world(profit, catalyst=0, followup=0, initial=1_000_000):
    return {'net_profit_cents': profit, 'project_cash_cents': initial + profit,
            'external_draws': {'catalyst_draw_bps': catalyst, 'followup_draw_bps': followup},
            'cash_bridge': {'contributed_capital_cents': initial, 'ending_withdrawable_cash_cents': initial + profit}}


def overview(rows, scenario=None):
    from decision_lab.scenario_overview import summarize_scenarios
    return summarize_scenarios({'worlds': rows, 'world_count': len(rows)}, scenario or default_scenario())


def test_event_paths_are_exhaustive_and_keep_unobserved_paths():
    rows = [world(100, 0, 0), world(-100, 0, 9999), world(500, 9999, 0)]
    result = overview(rows)
    assert result['schema_version'] == 'scenario-overview.v1'
    groups = {row['id']: row for row in result['event_paths']}
    assert set(groups) == {'confirmed_positive', 'confirmed_contradicted', 'rumor_positive', 'rumor_contradicted'}
    assert sum(row['count'] for row in groups.values()) == 3
    assert sum(row['frequency'] for row in groups.values()) == pytest.approx(1)
    assert groups['confirmed_contradicted']['mean_cents'] == -100
    assert groups['rumor_contradicted']['count'] == 0
    assert groups['rumor_contradicted']['frequency'] == 0
    assert groups['rumor_contradicted']['median_cents'] is None
    assert 'separate claim' in groups['confirmed_positive']['label'].lower()


def test_cash_bins_boundaries_once_each_and_weighted_statistics():
    values = [-500001, -500000, -1, 0, 1_999_999, 2_000_000, 2_000_001]
    result = overview([world(value) for value in values])
    assert [(row['id'], row['count']) for row in result['cash_outcomes']] == [
        ('severe_loss', 1), ('loss', 2), ('modest_profit', 2), ('large_profit', 2)]
    assert result['overall']['mean_cents'] == pytest.approx(sum(values) / len(values))
    assert result['overall']['median_cents'] == 0
    assert result['overall']['p05_cents'] == -500001
    assert result['overall']['p95_cents'] == 2_000_001
    assert result['overall']['mean_ending_cash_cents'] == pytest.approx(1_000_000 + sum(values) / len(values))
    bridge = {row['field']: row for row in result['cash_bridge']}
    assert bridge['ending_withdrawable_cash_cents']['median_cents'] == 1_000_000
    assert result['quantile_method'] == 'nearest_rank'
    assert result['world_count'] == len(values)


@pytest.mark.parametrize('enabled,horizon,expected', [
    (False, 720, {'news_disabled'}), (True, 0, {'news_not_reached'}),
    (True, 1, {'confirmed_pending', 'rumor_pending'}),
    (True, 95, {'confirmed_pending', 'rumor_pending'}),
    (True, 96, {'confirmed_positive', 'confirmed_contradicted', 'rumor_positive', 'rumor_contradicted'}),
])
def test_disabled_and_not_yet_reached_events_are_not_reported_as_observed(enabled, horizon, expected):
    scenario = {**default_scenario(), 'news_enabled': enabled, 'horizon_hours': horizon}
    result = overview([world(1, 0, 0), world(3, 9999, 9999)], scenario)
    assert {row['id'] for row in result['event_paths']} == expected
    assert sum(row['count'] for row in result['event_paths']) == 2


def test_simulation_attaches_actual_overview_and_user_brief_is_context_only():
    scenario = default_scenario()
    scenario.update(horizon_hours=1, founder_sales=[], campaigns=[], competitor_messages=[])
    baseline = simulate(scenario, load_pool(), worlds=2)
    brief = {'question': 'What could happen to my launch?', 'event': 'An explicitly hypothetical event', 'ticker': 'TEST'}
    scenario['user_brief'] = brief
    result = simulate(scenario, load_pool(), worlds=2)
    assert baseline['worlds'] == result['worlds']
    assert baseline['scenario_sha256'] != result['scenario_sha256']
    assert 'user_brief' not in baseline
    assert result['user_brief'] == brief
    assert result['overview'] == overview(result['worlds'], scenario)


@pytest.mark.parametrize('brief', [None, [], {'question': 'x'},
    {'question': '', 'event': '', 'ticker': ''},
    {'question': 'a' * 2001, 'event': '', 'ticker': ''},
    {'question': 'x', 'event': 'a' * 161, 'ticker': ''},
    {'question': 'x', 'event': '', 'ticker': 'a' * 25},
    {'question': 'x', 'event': '', 'ticker': '', 'unknown': 'x'}])
def test_user_brief_rejects_invalid_or_unbounded_context(brief):
    scenario = deepcopy(default_scenario())
    scenario['user_brief'] = brief
    with pytest.raises(ValueError, match='user brief'):
        simulate(scenario, load_pool(), worlds=1)


def test_exact_event_thresholds_and_even_sample_nearest_rank_median():
    result = overview([world(1, 6499, 4499), world(2, 6500, 4500)])
    groups = {row['id']: row for row in result['event_paths']}
    assert groups['confirmed_positive']['count'] == 1
    assert groups['rumor_contradicted']['count'] == 1
    assert result['overall']['mean_cents'] == 1.5
    assert result['overall']['median_cents'] == 1
