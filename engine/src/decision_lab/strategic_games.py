"""Exact advisory mechanics for explicit finite normal-form strategic games.

This layer exists to expose incentives and profitable unilateral deviations
instead of calling an unconstrained model narrative game theory. A payoff table
states reviewed utility assumptions. Beliefs, when supplied, are independent
player action distributions; they are not inferred market outcome chances.
The functions cannot call models, send messages or write a financial ledger.
"""
from copy import deepcopy
from fractions import Fraction
from hashlib import sha256
from itertools import product
import json
from pathlib import Path
import re

MAX_BYTES = 524288
MAX_PROFILES = 256
ENGINE_SHA256 = sha256(Path(__file__).read_bytes()).hexdigest()


def _shape(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        raise ValueError('invalid finite-game object shape')


def _text(value, limit):
    if type(value) is not str or not value.strip() or len(value) > limit:
        raise ValueError('nonempty bounded finite-game text required')
    return value


def _id(value):
    if type(value) is not str or not re.fullmatch(r'[a-z][a-z0-9-]{0,47}', value):
        raise ValueError('invalid finite-game identifier')
    return value


def _integer(value, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError('finite-game integer outside bounds')
    return value


def _list(value, minimum, maximum):
    if type(value) is not list or not minimum <= len(value) <= maximum:
        raise ValueError('invalid bounded finite-game list')
    return value


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                      allow_nan=False).encode('ascii')


def validate_game(value):
    """Validate a full reviewed table before bounded exhaustive computation."""
    try:
        if len(_canonical(value)) > MAX_BYTES:
            raise ValueError('finite-game input exceeds size budget')
        _shape(value, {'schema_version', 'id', 'description', 'utility_unit', 'players',
                       'profiles', 'strategy_beliefs'})
        if value['schema_version'] != 'finite-game.v1':
            raise ValueError('unsupported finite-game schema')
        _id(value['id']);_text(value['description'], 8000);_text(value['utility_unit'], 200)
        players = _list(value['players'], 2, 4)
        ids, action_sets = [], []
        count = 1
        for player in players:
            _shape(player, {'id', 'name', 'actions'})
            identifier = _id(player['id']);_text(player['name'], 160)
            if identifier in ids:
                raise ValueError('duplicate finite-game player')
            ids.append(identifier)
            actions = _list(player['actions'], 2, 8)
            action_ids = []
            for action in actions:
                _shape(action, {'id', 'label'});_id(action['id']);_text(action['label'], 200)
                if action['id'] in action_ids:
                    raise ValueError('duplicate finite-game action')
                action_ids.append(action['id'])
            action_sets.append(action_ids);count *= len(action_ids)
        if count > MAX_PROFILES:
            raise ValueError('finite-game profile work budget exceeded')
        profiles = _list(value['profiles'], count, count)
        covered = set()
        for row in profiles:
            _shape(row, {'actions', 'payoffs', 'provenance'})
            _shape(row['actions'], ids);_shape(row['payoffs'], ids)
            profile = tuple(row['actions'][identifier] for identifier in ids)
            for action, allowed in zip(profile, action_sets):
                if type(action) is not str or action not in allowed:
                    raise ValueError('unknown finite-game action')
            if profile in covered:
                raise ValueError('duplicate finite-game profile')
            covered.add(profile)
            for payoff in row['payoffs'].values():
                _integer(payoff, -10**9, 10**9)
            provenance = row['provenance']
            _shape(provenance, {'status', 'rationale', 'source_refs'})
            if provenance['status'] not in {'assumed', 'estimated', 'model_proposal'}:
                raise ValueError('payoff utility needs explicit assumed/estimated/model provenance')
            _text(provenance['rationale'], 1600)
            for ref in _list(provenance['source_refs'], 0, 8):
                _text(ref, 400)
        if len(covered) != count:
            raise ValueError('incomplete finite-game profile coverage')
        beliefs = value['strategy_beliefs']
        if beliefs is not None:
            _shape(beliefs, ids)
            for identifier, allowed in zip(ids, action_sets):
                _shape(beliefs[identifier], allowed)
                for probability in beliefs[identifier].values():
                    _integer(probability, 0, 10000)
                if sum(beliefs[identifier].values()) != 10000:
                    raise ValueError('each independent strategy distribution must sum to 10000 basis points')
        return deepcopy(value)
    except (TypeError, KeyError, OverflowError, RecursionError) as error:
        raise ValueError('invalid finite-game input') from error


def _rational(value):
    return {'numerator': value.numerator, 'denominator': value.denominator}


def analyze_game(value):
    """Compute exact unilateral responses, pure Nash and pure dominance.

    For player i and action a, EU_i(a) sums utility_i(a, a_-i) times
    the product of the supplied opponents' independent action beliefs. Regret
    equals the best available expected utility minus the action's EU. A profile
    is pure Nash iff no unilateral deviation strictly improves utility. Pure
    action a is strictly dominated by b iff b's utility is greater at *every*
    opponent profile, including profiles with zero supplied belief probability.
    No mixed-strategy equilibrium, correlated belief or iterated elimination
    solver is implied by these separate calculations.
    """
    game = validate_game(value)
    ids = [player['id'] for player in game['players']]
    action_sets = [[action['id'] for action in player['actions']] for player in game['players']]
    tuples = list(product(*action_sets))
    table = {tuple(row['actions'][identifier] for identifier in ids): row['payoffs']
             for row in game['profiles']}
    beliefs = game['strategy_beliefs']
    players, dominated = {}, []
    for index, identifier in enumerate(ids):
        opponent_indices = [other for other in range(len(ids)) if other != index]
        opponent_profiles = list(product(*(action_sets[other] for other in opponent_indices)))

        def full_profile(action, opponents):
            profile = [None] * len(ids);profile[index] = action
            for other, selected in zip(opponent_indices, opponents):
                profile[other] = selected
            return tuple(profile)

        utilities = {}
        if beliefs is not None:
            for action in action_sets[index]:
                expected = Fraction(0)
                for opponents in opponent_profiles:
                    probability = Fraction(1)
                    for other, selected in zip(opponent_indices, opponents):
                        probability *= Fraction(beliefs[ids[other]][selected], 10000)
                    expected += probability * table[full_profile(action, opponents)][identifier]
                utilities[action] = expected
            maximum = max(utilities.values())
            mixed = sum((Fraction(beliefs[identifier][action], 10000) * utility
                         for action, utility in utilities.items()), Fraction(0))
            players[identifier] = {
                'expected_utilities': {action: _rational(utility) for action, utility in utilities.items()},
                'best_responses': [action for action, utility in utilities.items() if utility == maximum],
                'deviation_regret': {action: _rational(maximum - utility) for action, utility in utilities.items()},
                'mixed_strategy_expected_utility': _rational(mixed),
                'mixed_strategy_deviation_regret': _rational(maximum - mixed),
            }
        else:
            players[identifier] = {key: None for key in (
                'expected_utilities', 'best_responses', 'deviation_regret',
                'mixed_strategy_expected_utility', 'mixed_strategy_deviation_regret')}
        for action in action_sets[index]:
            dominators = [alternative for alternative in action_sets[index] if alternative != action
                and all(table[full_profile(alternative, opponents)][identifier]
                        > table[full_profile(action, opponents)][identifier]
                        for opponents in opponent_profiles)]
            if dominators:
                dominated.append({'player_id': identifier, 'action_id': action,
                                  'dominating_action_ids': dominators})
    equilibria = []
    for profile in tuples:
        is_equilibrium = True
        for index, identifier in enumerate(ids):
            current = table[profile][identifier]
            for alternative in action_sets[index]:
                deviated = profile[:index] + (alternative,) + profile[index + 1:]
                if table[deviated][identifier] > current:
                    is_equilibrium = False;break
            if not is_equilibrium:
                break
        if is_equilibrium:
            equilibria.append(dict(zip(ids, profile)))
    return {
        'schema_version': 'finite-game-analysis.v1',
        'game_sha256': sha256(_canonical(game)).hexdigest(), 'engine_sha256': ENGINE_SHA256,
        'game_id': game['id'], 'utility_unit': game['utility_unit'], 'profile_count': len(tuples),
        'advisory_only': True, 'strategy_beliefs': deepcopy(beliefs), 'players': players,
        'pure_nash_profiles': equilibria, 'strictly_dominated_actions': dominated,
        'payoff_provenance': [{'actions': deepcopy(row['actions']), 'provenance': deepcopy(row['provenance'])}
                              for row in game['profiles']],
        'limitations': [
            'Utilities and strategy beliefs are supplied assumptions or estimates, not measured willingness to pay or real-world outcome probabilities.',
            'Independent strategy beliefs exclude correlations; no default distribution is invented when beliefs are absent.',
            'Pure Nash is a no-profitable-unilateral-deviation condition in the supplied static game, not a forecast that people choose that profile.',
            'No mixed-strategy equilibrium solver, coalition deviation, repeated-game strategy, bargaining solution or iterated elimination is implemented.',
            'Strict domination considers other pure actions only, over all opponent profiles even when their belief probability is zero.',
            'Utility points are not cash profit. This advisory calculation neither executes actions nor modifies an agent world or financial ledger.',
        ],
    }
