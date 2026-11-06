"""Generalisation checks: a case that is not a fair launch, and verdict wording at the extremes."""
from __future__ import annotations

import csv
import json

import pytest

from decision_lab.case_report import doc_decision, render_case
from decision_lab.launch_estimate import estimate_launch, validate_params
from test_case_report import fixture_case


def pool_case(tmp_path):
    """Same renderer, different venue: an existing pool with team liquidity and no curve phase."""
    case = fixture_case(tmp_path)
    brief = json.loads((case / 'brief.json').read_text())
    brief['labels'] = {'title': 'Pool case', 'venue': 'existing constant-product pool'}
    brief['estimate'] = {'venue': 'pool', 'worlds': 120, 'bootstrap_usd': 20_000,
                         'sol_usd': 150, 'kol_cash_usd': 0, 'half_life_hours': 24,
                         'founder_supply_bps': 6_000, 'pool_supply_bps': 4_000,
                         'capital_usd': {'large_buyer': 40_000}}
    brief['sensitivity'] = {'grid': {'sol_usd': [150]}, 'worlds': 60}
    (case / 'brief.json').write_text(json.dumps(brief))
    (case / 'world-grounding-2026-10-30' / 'bootstrap-buy.json').write_text(json.dumps(
        {'venue': 'existing constant-product pool', 'base_fee_bps': 100, 'curve_phase': 'none'}))
    return case


def test_pool_venue_renders_without_curve_claims(tmp_path):
    case = pool_case(tmp_path)
    out = tmp_path / 'report'
    render_case(case, out)
    decision = (out / '00-DECISION.md').read_text()
    evidence = (out / '03-EVIDENCE.md').read_text()
    model = (out / '01-MODEL.md').read_text()
    assert 'deposited as pool liquidity' in decision
    assert 'Pool depth' in evidence
    assert 'Virtual SOL reserves' not in evidence
    assert 'no curve phase' in model.lower()
    assert 'Pool depth $20,000' in model


def test_pool_venue_has_no_migration_split(tmp_path):
    case = pool_case(tmp_path)
    out = tmp_path / 'report'
    render_case(case, out)
    with (out / 'DATA' / 'scenarios.csv').open() as handle:
        rows = list(csv.DictReader(handle))
    assert rows
    assert all('migrated' not in row['scenario'] for row in rows)
    assert len(rows) <= 6


def test_pool_scenario_narrative_does_not_assert_negative_medians(tmp_path):
    case = pool_case(tmp_path)
    out = tmp_path / 'report'
    render_case(case, out)
    scenarios = (out / '02-SCENARIOS.md').read_text()
    decision = (out / '00-DECISION.md').read_text()
    assert 'median is negative in every arm' not in scenarios
    assert 'without one the outcome is a loss' not in scenarios
    assert 'migration matters more' not in scenarios
    assert 'eight scenario rows' not in decision


def test_pool_venue_recovers_the_liquidity_deposit():
    """The team owns the pool it funded, so a quiet launch should not lose the whole deposit."""
    quiet = estimate_launch({'retail_patient': {'hold': 1.0}},
                            {'venue': 'pool', 'worlds': 40, 'bootstrap_usd': 20_000,
                             'kol_cash_usd': 0, 'sol_usd': 150})
    # the deposit comes back minus the fee and price impact of liquidating the holding
    assert -400 < quiet['net_quantiles']['p50'] <= 0
    assert quiet['migration_share'] == 1.0           # a pool venue is always "migrated"


def test_verdict_says_makes_money_when_the_median_is_positive():
    summary = estimate_launch({'large_buyer': {'buy_all': 1.0}}, {'worlds': 40})
    text = doc_decision(summary, {'actors': [], 'role_counts': {}},
                        {'large_buyer': {'buy_all': 1.0}}, {'title': 'F'})
    answer = next(line for line in text.splitlines() if 'cash than you' in line)
    assert 'makes money' in answer
    assert 'loses money' not in answer
    assert 'All 100' in answer


def test_verdict_says_loses_money_when_nothing_arrives():
    summary = estimate_launch({'retail_skeptical': {'hold': 1.0}}, {'worlds': 40})
    text = doc_decision(summary, {'actors': [], 'role_counts': {}},
                        {'retail_skeptical': {'hold': 1.0}}, {'title': 'F'})
    answer = next(line for line in text.splitlines() if 'cash than you' in line)
    assert 'loses money' in answer
    assert 'No simulated launch' in answer
    assert 'No whale-sized outside buyer' in text


def test_pool_parameters_are_validated():
    with pytest.raises(ValueError, match='curve or pool required'):
        validate_params({'venue': 'amm'})
    with pytest.raises(ValueError, match='cannot exceed the token supply'):
        validate_params({'venue': 'pool', 'pool_supply_bps': 6_000, 'founder_supply_bps': 5_000})
    with pytest.raises(ValueError, match='must come from the founder holding'):
        validate_params({'venue': 'pool', 'founder_supply_bps': 100, 'kol_supply_bps': 300})


def test_verdict_and_icon_array_count_every_profitable_world(tmp_path):
    """A profitable world with no outside money must still be counted as a win."""
    import re
    case = pool_case(tmp_path)
    out = tmp_path / 'report'
    render_case(case, out)
    overall = json.loads((out / 'DATA' / 'outputs.json').read_text())['overall']
    expected = round(overall['profit_count'] / overall['worlds'] * 100)
    decision = (out / '00-DECISION.md').read_text()
    assert f'{expected} of every 100' in decision
    svg = (out / 'FIGURES' / 'fig-outcomes.svg').read_text()
    whale_dots = len(re.findall(r'fill="#b8860b"', svg)) - 1   # minus the legend swatch
    profit_dots = len(re.findall(r'fill="#2f6f4f"', svg)) - 1
    assert whale_dots + profit_dots == expected
