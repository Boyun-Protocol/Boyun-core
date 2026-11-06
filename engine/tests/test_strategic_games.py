"""Exact normal-form mechanics state incentives, not population forecasts."""
from copy import deepcopy
from fractions import Fraction
from itertools import product

import pytest

from decision_lab.strategic_games import analyze_game, validate_game


def game():
    table = {('cooperate', 'cooperate'): (3, 3), ('cooperate', 'defect'): (0, 5),
             ('defect', 'cooperate'): (5, 0), ('defect', 'defect'): (1, 1)}
    return {'schema_version': 'finite-game.v1', 'id': 'explicit-dilemma',
            'description': 'Illustrative private incentives, not measured human behavior.',
            'utility_unit': 'assumed utility points, not cash or probability',
            'players': [{'id': p, 'name': p.title(), 'actions': [{'id': a, 'label': a.title()} for a in ('cooperate', 'defect')]} for p in ('alice', 'bob')],
            'profiles': [{'actions': dict(zip(('alice', 'bob'), actions)),
                          'payoffs': dict(zip(('alice', 'bob'), payoffs)),
                          'provenance': {'status': 'assumed', 'rationale': 'Explicit test incentives.', 'source_refs': []}}
                         for actions, payoffs in table.items()],
            'strategy_beliefs': {'alice': {'cooperate': 5000, 'defect': 5000},
                                 'bob': {'cooperate': 2500, 'defect': 7500}}}


def test_exact_expected_utility_best_response_and_deviation_regret():
    result = analyze_game(game())
    assert result['schema_version'] == 'finite-game-analysis.v1'
    alice = result['players']['alice']
    assert alice['expected_utilities'] == {'cooperate': {'numerator': 3, 'denominator': 4},
                                           'defect': {'numerator': 2, 'denominator': 1}}
    assert alice['best_responses'] == ['defect']
    assert alice['deviation_regret'] == {'cooperate': {'numerator': 5, 'denominator': 4},
                                        'defect': {'numerator': 0, 'denominator': 1}}
    assert alice['mixed_strategy_expected_utility'] == {'numerator': 11, 'denominator': 8}
    assert alice['mixed_strategy_deviation_regret'] == {'numerator': 5, 'denominator': 8}
    assert result['pure_nash_profiles'] == [{'alice': 'defect', 'bob': 'defect'}]
    assert result['strictly_dominated_actions'] == [
        {'player_id': 'alice', 'action_id': 'cooperate', 'dominating_action_ids': ['defect']},
        {'player_id': 'bob', 'action_id': 'cooperate', 'dominating_action_ids': ['defect']}]


def test_missing_beliefs_never_invents_uniform_distribution():
    value = game();value['strategy_beliefs'] = None
    result = analyze_game(value)
    assert result['strategy_beliefs'] is None
    assert result['players']['alice']['expected_utilities'] is None
    assert result['players']['alice']['best_responses'] is None
    assert result['pure_nash_profiles'] == [{'alice': 'defect', 'bob': 'defect'}]


def test_ties_are_not_strict_domination_and_all_best_responses_retained():
    value = game()
    for row in value['profiles']:row['payoffs'] = {'alice': -2, 'bob': -2}
    result = analyze_game(value)
    assert result['strictly_dominated_actions'] == []
    assert len(result['pure_nash_profiles']) == 4
    assert result['players']['alice']['best_responses'] == ['cooperate', 'defect']
    assert result['players']['bob']['mixed_strategy_deviation_regret'] == {'numerator': 0, 'denominator': 1}


def test_matching_pennies_has_no_pure_equilibrium_and_does_not_claim_mixed_solver():
    value = game()
    for row in value['profiles']:
        same = len(set(row['actions'].values())) == 1
        row['payoffs'] = {'alice': 1 if same else -1, 'bob': -1 if same else 1}
    result = analyze_game(value)
    assert result['pure_nash_profiles'] == []
    assert any('mixed-strategy equilibrium' in item for item in result['limitations'])


def test_three_player_independent_product_beliefs_use_exact_fraction():
    value = game()
    value['players'].append({'id': 'cara', 'name': 'Cara', 'actions': [{'id': 'cooperate', 'label': 'Cooperate'}, {'id': 'defect', 'label': 'Defect'}]})
    value['strategy_beliefs']['cara'] = {'cooperate': 3333, 'defect': 6667}
    value['profiles'] = [{'actions': dict(zip(('alice', 'bob', 'cara'), acts)),
                          'payoffs': {'alice': int(acts[1] == 'cooperate' and acts[2] == 'cooperate'), 'bob': 0, 'cara': 0},
                          'provenance': {'status': 'assumed', 'rationale': 'Explicit joint case.', 'source_refs': []}}
                         for acts in product(('cooperate', 'defect'), repeat=3)]
    result = analyze_game(value)
    expected = Fraction(2500, 10000) * Fraction(3333, 10000)
    assert result['players']['alice']['expected_utilities']['cooperate'] == {'numerator': expected.numerator, 'denominator': expected.denominator}


def test_input_is_detached_output_deterministic_and_profiles_canonicalized():
    value = game();before = deepcopy(value)
    result = analyze_game(value)
    assert value == before
    assert result == analyze_game(deepcopy(value))
    detached = validate_game(value)
    detached['players'][0]['name'] = 'Other'
    assert value == before
    reversed_value = deepcopy(value);reversed_value['profiles'].reverse()
    assert analyze_game(reversed_value)['pure_nash_profiles'] == result['pure_nash_profiles']


@pytest.mark.parametrize('change', [
    lambda g: g.update(schema_version='other'), lambda g: g.update(extra=True),
    lambda g: g['players'].pop(), lambda g: g['players'].append(deepcopy(g['players'][0])),
    lambda g: g['players'][0]['actions'].pop(),
    lambda g: g['players'][0]['actions'].append(deepcopy(g['players'][0]['actions'][0])),
    lambda g: g['profiles'].pop(), lambda g: g['profiles'].append(deepcopy(g['profiles'][0])),
    lambda g: g['profiles'][0]['payoffs'].update(alice=True),
    lambda g: g['profiles'][0]['payoffs'].update(alice=1.5),
    lambda g: g['profiles'][0]['payoffs'].update(alice=10**9 + 1),
    lambda g: g['profiles'][0]['actions'].update(alice='unknown'),
    lambda g: g['profiles'][0]['payoffs'].update(stranger=1),
    lambda g: g['profiles'][0]['provenance'].update(status='observed'),
    lambda g: g['profiles'][0]['provenance'].update(rationale=''),
    lambda g: g['strategy_beliefs']['alice'].update(cooperate=True),
    lambda g: g['strategy_beliefs']['alice'].update(cooperate=9999),
    lambda g: g['strategy_beliefs']['alice'].update(other=1),
    lambda g: g['strategy_beliefs'].pop('bob'),
    lambda g: g.update(description='x' * 8001),
])
def test_strict_shapes_bounds_and_complete_explicit_games(change):
    value = game();change(value)
    with pytest.raises(ValueError): analyze_game(value)


def test_profile_work_bound_rejects_before_expensive_analysis():
    value = game()
    value['players'] = [{'id': f'p{i}', 'name': f'Player {i}', 'actions': [{'id': f'a{j}', 'label': f'Action {j}'} for j in range(8)]} for i in range(4)]
    value['strategy_beliefs'] = None
    with pytest.raises(ValueError, match='profile'):
        analyze_game(value)


def test_zero_probability_opponent_profiles_still_prevent_strict_domination():
    value = game()
    value['strategy_beliefs']['bob'] = {'cooperate': 10000, 'defect': 0}
    # Defect is better against the believed action but worse in an off-support case.
    value['profiles'][-1]['payoffs']['alice'] = -1
    result = analyze_game(value)
    assert result['players']['alice']['best_responses'] == ['defect']
    assert not any(row['player_id'] == 'alice' and row['action_id'] == 'cooperate'
                   for row in result['strictly_dominated_actions'])


def test_four_players_at_exact_profile_budget_are_bounded_and_valid():
    value = game()
    value['players'] = [{'id': f'player-{i}', 'name': f'Player {i}',
                         'actions': [{'id': f'action-{j}', 'label': f'Action {j}'} for j in range(4)]}
                        for i in range(4)]
    ids = [p['id'] for p in value['players']]
    value['strategy_beliefs'] = {identifier: {f'action-{j}': 2500 for j in range(4)} for identifier in ids}
    value['profiles'] = [{'actions': dict(zip(ids, actions)), 'payoffs': {identifier: 0 for identifier in ids},
                          'provenance': {'status': 'assumed', 'rationale': 'Complete explicit indifferent game.', 'source_refs': []}}
                         for actions in product([f'action-{j}' for j in range(4)], repeat=4)]
    result = analyze_game(value)
    assert result['profile_count'] == 256
    assert len(result['pure_nash_profiles']) == 256
    assert result['strictly_dominated_actions'] == []


def test_eight_actions_and_extreme_negative_utilities_remain_exact():
    value = game()
    value['players'][0]['actions'] = [{'id': f'action-{j}', 'label': f'Action {j}'} for j in range(8)]
    value['strategy_beliefs'] = None
    value['profiles'] = [{'actions': {'alice': f'action-{j}', 'bob': action},
                          'payoffs': {'alice': -10**9 + j, 'bob': 10**9},
                          'provenance': {'status': 'model_proposal', 'rationale': 'Explicitly proposed utility, not empirical.', 'source_refs': ['proposal:test']}}
                         for j in range(8) for action in ('cooperate', 'defect')]
    result = analyze_game(value)
    assert result['pure_nash_profiles'] == [{'alice': 'action-7', 'bob': 'cooperate'}, {'alice': 'action-7', 'bob': 'defect'}]
    assert len(result['strictly_dominated_actions']) == 7


@pytest.mark.parametrize('change', [
    lambda g: g['profiles'][0]['provenance'].update(source_refs=['x'] * 9),
    lambda g: g['profiles'][0]['provenance'].update(source_refs=[None]),
    lambda g: g['strategy_beliefs']['alice'].update(cooperate=-1, defect=10001),
    lambda g: g['strategy_beliefs']['alice'].update(cooperate=5000.0),
    lambda g: g['players'][0].update(id=True),
    lambda g: g['players'][0]['actions'][0].update(id='not valid'),
])
def test_probability_and_provenance_boundaries(change):
    value = game();change(value)
    with pytest.raises(ValueError): validate_game(value)


def test_coordination_example_runs_and_has_multiple_equilibria():
    import json
    from pathlib import Path
    value = json.loads((Path(__file__).parents[1]/'examples/launch-coordination.game.json').read_text())
    result = analyze_game(value)
    assert result['pure_nash_profiles'] == [
        {'founder': 'fund-disclosure', 'liquidity-partner': 'commit-escrow'},
        {'founder': 'skip-review', 'liquidity-partner': 'wait'}]
    assert result['players']['founder']['expected_utilities']['fund-disclosure'] == {'numerator': 6, 'denominator': 5}
