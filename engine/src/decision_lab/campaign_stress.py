"""Explicit synthetic activity bias, separate from provider decisions and forecasts."""
from copy import deepcopy
from fractions import Fraction
from hashlib import sha256
from pathlib import Path

from .agent_worlds import _int, _shape, digest
from .campaign_worlds import decide_campaign, validate_campaign_world
from .randomness import keyed_rng


POLICY_HASH = sha256(Path(__file__).read_bytes()).hexdigest()


def stress_config(buy_multiplier=4, sell_multiplier=4, ticket_multiplier=2):
    for value in (buy_multiplier, sell_multiplier, ticket_multiplier):
        _int(value, 1, 5)
    return {'schema_version': 'campaign-stress.v1', 'buy_multiplier': buy_multiplier,
            'sell_multiplier': sell_multiplier, 'ticket_multiplier': ticket_multiplier}


def validate_stress(config):
    _shape(config, {'schema_version', 'buy_multiplier', 'sell_multiplier', 'ticket_multiplier'})
    validated = stress_config(config['buy_multiplier'], config['sell_multiplier'], config['ticket_multiplier'])
    if config != validated:
        raise ValueError('unknown stress policy')
    return validated


def stress_package(package, config):
    validate_stress(config)
    result = validate_campaign_world(package)
    result['id'] = result['id'][:41] + '-stress'
    for actor in result['actors']:
        actor['max_buy_cents'] *= config['ticket_multiplier']
    result['assumptions'].append(
        f"ARTIFICIAL LOAD TEST: sample provider action scores with buy weights x{config['buy_multiplier']}, "
        f"sell weights x{config['sell_multiplier']} and buy-ticket caps x{config['ticket_multiplier']}. "
        'This overrides provider argmax/confidence abstention for financial actions only. '
        'Cash, token and slippage constraints still apply. These are not calibrated behavior or event odds. '
        f"Original package SHA256: {digest(package)}.")
    return validate_campaign_world(result)


def _sample(weights, draw):
    total = sum(weights.values())
    if total == 0:
        return 'wait'
    target = total * Fraction(draw, 2**53)
    cumulative = Fraction(0)
    for action, weight in sorted(weights.items()):
        cumulative += weight
        if target < cumulative:
            return action
    raise RuntimeError('invalid stress sampling interval')


def stress_action(engine, actor_id, response, config):
    validate_stress(config)
    actions = engine.menu(actor_id)[0]
    answer = response['answers'].get('action')
    scores = answer['probabilities'] if answer else {'wait': 1}
    if set(scores) != set(actions):
        raise ValueError('stress scores do not cover the current action menu')
    original = {action: Fraction(str(value)) for action, value in scores.items()}
    if any(value < 0 for value in original.values()):
        raise ValueError('negative stress score')
    weights = {action: weight * config.get(actions[action]['kind'] + '_multiplier', 1)
               for action, weight in original.items()}
    draw = keyed_rng(engine.seed, 'campaign-stress-action', engine.index, actor_id).getrandbits(53)
    selected = _sample(weights, draw)
    total = sum(weights.values())
    metadata = {'config': deepcopy(config), 'policy_sha256': POLICY_HASH, 'draw_uint53': draw,
                'provider_choice': answer['choice'] if answer else 'wait',
                'provider_confidence': answer['confidence'] if answer else None,
                'unbuffed_same_draw_action': _sample(original, draw), 'sampled_action': selected,
                'normalized_weights_exact': {action: str(weight / total) if total else str(int(action == 'wait'))
                                             for action, weight in weights.items()},
                'interpretation': 'Synthetic stress sampling weights, not measured trade frequencies or event odds.',
                'confidence_gate': 'bypassed for action only; coordination policy unchanged'}
    return selected, metadata


def decide_stress(engine, actor_id, client, config):
    result = decide_campaign(engine, actor_id, client)
    selected, metadata = stress_action(engine, actor_id, result, config)
    result['decision']['action_id'] = selected
    result['stress_policy'] = metadata
    return result
