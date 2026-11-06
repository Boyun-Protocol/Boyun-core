"""Data-only evaluation of supplied categorical event trees.

Descriptions are context. Only declared adjust_metric effects execute. This is
neither a financial ledger nor an inference model for participant behavior.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import hashlib
import json
import math
import re

_LIMITS = {
    'input_bytes': 262_144, 'depth': 12, 'nodes': 30_000,
    'personas': 64, 'parameters': 128, 'metrics': 64, 'rules': 128,
    'outcomes_per_rule': 16, 'effects_per_outcome': 32, 'total_effects': 4096,
    'horizon_ticks': 10_000, 'worlds': 10_000, 'world_rule_visits': 100_000,
    'world_effect_visits': 1_000_000, 'output_bytes': 16_777_216, 'metric_magnitude': 10**12,
    'integer_magnitude': 10**9, 'text_characters': 4096,
}
_IDENTIFIER = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z')
_LIMITATIONS = [
    'Supplied conditional events and metric effects only; no emergent participant behavior or equilibrium solver.',
    'Persona descriptions are context only; they do not generate policies, resources or probability estimates.',
    'Probabilities and sources are supplied declarations, not verified estimates or calibrated forecasts.',
    'Observed path frequencies describe completed synthetic worlds, not real adoption or profit odds.',
    'Metrics, including declared USD payoffs, are not withdrawable cash or financial settlement.',
    'No lending, interest, collateral, liquidation, wallet or on-chain protocol mechanics are implemented.',
]


def _error(path: str, reason: str) -> None:
    # Paths use schema keys/list indices, never untrusted input values.
    raise ValueError(f'{path}: {reason}')


def _object(value, keys: set[str], path: str) -> dict:
    if type(value) is not dict or set(value) != keys:
        _error(path, 'expected object with exactly the declared fields')
    return value


def _list(value, path: str, maximum: int, minimum: int = 0) -> list:
    if type(value) is not list or not minimum <= len(value) <= maximum:
        _error(path, 'invalid list size or type')
    return value


def _text(value, path: str, maximum: int = 4096) -> str:
    if type(value) is not str or not value.strip() or len(value) > maximum:
        _error(path, 'expected bounded nonempty text')
    return value


def _id(value, path: str) -> str:
    if type(value) is not str or not _IDENTIFIER.fullmatch(value):
        _error(path, 'expected identifier of 1 to 64 ASCII letters, digits, dots, dashes or underscores')
    return value


def _integer(value, path: str, lower: int, upper: int) -> int:
    if type(value) is not int or not lower <= value <= upper:
        _error(path, 'integer outside declared bounds or invalid integer type')
    return value


def _bounded_json(value) -> None:
    """Bound traversal before serialization or copying, including recursive input."""
    nodes = 0
    # UTF-8 encoding is attempted only after a bounded tree walk.
    def visit(item, depth):
        nonlocal nodes
        nodes += 1
        if nodes > _LIMITS['nodes'] or depth > _LIMITS['depth']:
            _error('$', 'input exceeds tree size or depth limit')
        if type(item) is dict:
            if len(item) > _LIMITS['nodes']:
                _error('$', 'input object exceeds size limit')
            for key, child in item.items():
                if type(key) is not str or len(key) > 4096:
                    _error('$', 'invalid object key')
                visit(child, depth + 1)
        elif type(item) is list:
            if len(item) > _LIMITS['nodes']:
                _error('$', 'input list exceeds size limit')
            for child in item:
                visit(child, depth + 1)
        elif type(item) is str:
            if len(item) > _LIMITS['text_characters']:
                _error('$', 'text exceeds size limit')
        elif type(item) is int:
            if abs(item) > _LIMITS['metric_magnitude']:
                _error('$', 'numeric magnitude exceeds limit')
        else:
            _error('$', 'expected only JSON objects, lists, strings and integers')
    visit(value, 0)
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')
    except (ValueError, UnicodeError):
        _error('$', 'invalid JSON text encoding')
    if len(encoded) > _LIMITS['input_bytes']:
        _error('$', 'serialized input exceeds byte limit')


def _number(value, parameters: dict, path: str, lower: int, upper: int) -> int:
    if type(value) is dict:
        _object(value, {'parameter'}, path)
        key = _id(value['parameter'], path + '.parameter')
        if key not in parameters:
            _error(path, 'unknown parameter reference')
        value = parameters[key]
    return _integer(value, path, lower, upper)


def _unique_id(record, seen: set, path: str) -> str:
    key = _id(record['id'], path + '.id')
    if key in seen:
        _error(path + '.id', 'duplicate identifier')
    seen.add(key)
    return key


def validate_event_chain(value: dict) -> dict:
    """Return a deep copy after validating every branch, reference and bound.

    Raises ValueError with structural paths and safe explanations. Equal-time
    rules cannot depend on one another. Their additive effects commute; replay
    and traces use the stable (at_tick, id) order.
    """
    _bounded_json(value)
    _object(value, {'schema_version', 'id', 'event_description', 'parameters', 'personas',
                    'metrics', 'rules', 'horizon_ticks', 'assumptions'}, '$')
    if value['schema_version'] != 'event-chain.v1':
        _error('$.schema_version', 'unsupported event-chain schema')
    _id(value['id'], '$.id')
    _text(value['event_description'], '$.event_description')
    horizon = _integer(value['horizon_ticks'], '$.horizon_ticks', 0, _LIMITS['horizon_ticks'])
    params = value['parameters']
    if type(params) is not dict or len(params) > _LIMITS['parameters']:
        _error('$.parameters', 'expected bounded parameter object')
    for index, (key, item) in enumerate(params.items()):
        _id(key, f'$.parameters[{index}].key')
        _integer(item, f'$.parameters[{index}].value', -_LIMITS['integer_magnitude'], _LIMITS['integer_magnitude'])
    for i, assumption in enumerate(_list(value['assumptions'], '$.assumptions', 128)):
        _text(assumption, f'$.assumptions[{i}]')
    actors, actor_ids = {}, set()
    for i, actor in enumerate(_list(value['personas'], '$.personas', _LIMITS['personas'], 1)):
        path = f'$.personas[{i}]'
        _object(actor, {'id', 'name', 'description', 'role', 'allowed_actions'}, path)
        key = _unique_id(actor, actor_ids, path)
        for field in ('name', 'description', 'role'):
            _text(actor[field], path + '.' + field)
        actions = _list(actor['allowed_actions'], path + '.allowed_actions', 1)
        if any(action != 'adjust_metric' for action in actions):
            _error(path + '.allowed_actions', 'unsupported action capability')
        actors[key] = actions
    metric_ids, budgets = set(), {}
    for i, metric in enumerate(_list(value['metrics'], '$.metrics', _LIMITS['metrics'], 1)):
        path = f'$.metrics[{i}]'
        _object(metric, {'id', 'unit', 'initial'}, path)
        key = _unique_id(metric, metric_ids, path)
        _text(metric['unit'], path + '.unit', 64)
        budgets[key] = abs(_integer(metric['initial'], path + '.initial', -_LIMITS['metric_magnitude'], _LIMITS['metric_magnitude']))
    rule_ids, rules, total_effects = set(), {}, 0
    for i, rule in enumerate(_list(value['rules'], '$.rules', _LIMITS['rules'], 1)):
        path = f'$.rules[{i}]'
        _object(rule, {'id', 'at_tick', 'actor_id', 'requires', 'outcomes', 'probability_provenance'}, path)
        key = _unique_id(rule, rule_ids, path)
        _integer(rule['at_tick'], path + '.at_tick', 0, horizon)
        actor = _id(rule['actor_id'], path + '.actor_id')
        if actor not in actors or 'adjust_metric' not in actors[actor]:
            _error(path + '.actor_id', 'unknown actor or missing adjust_metric capability')
        provenance = _object(rule['probability_provenance'], {'status', 'rationale', 'source_refs'}, path + '.probability_provenance')
        if provenance['status'] not in ('assumed', 'estimated', 'model_proposal'):
            _error(path + '.probability_provenance.status', 'unsupported provenance status')
        _text(provenance['rationale'], path + '.probability_provenance.rationale')
        for j, ref in enumerate(_list(provenance['source_refs'], path + '.probability_provenance.source_refs', 32)):
            _text(ref, path + f'.probability_provenance.source_refs[{j}]')
        _list(rule['requires'], path + '.requires', _LIMITS['rules'])
        seen_outcomes, probability_sum, rule_magnitudes = set(), 0, Counter()
        for j, outcome in enumerate(_list(rule['outcomes'], path + '.outcomes', _LIMITS['outcomes_per_rule'], 1)):
            opath = path + f'.outcomes[{j}]'
            _object(outcome, {'id', 'probability_bps', 'effects'}, opath)
            _unique_id(outcome, seen_outcomes, opath)
            probability_sum += _number(outcome['probability_bps'], params, opath + '.probability_bps', 0, 10000)
            changes = Counter()
            for k, effect in enumerate(_list(outcome['effects'], opath + '.effects', _LIMITS['effects_per_outcome'])):
                epath = opath + f'.effects[{k}]'
                _object(effect, {'action', 'metric_id', 'delta'}, epath)
                if effect['action'] != 'adjust_metric':
                    _error(epath + '.action', 'unsupported action')
                metric_id = _id(effect['metric_id'], epath + '.metric_id')
                if metric_id not in metric_ids:
                    _error(epath + '.metric_id', 'unknown metric reference')
                changes[metric_id] += _number(effect['delta'], params, epath + '.delta', -_LIMITS['integer_magnitude'], _LIMITS['integer_magnitude'])
                total_effects += 1
                if total_effects > _LIMITS['total_effects']:
                    _error('$.rules', 'total effects exceed limit')
            for metric_id, delta in changes.items():
                rule_magnitudes[metric_id] = max(rule_magnitudes[metric_id], abs(delta))
        if probability_sum != 10000:
            _error(path + '.outcomes', 'probabilities must sum to 10000 basis points')
        for metric_id, magnitude in rule_magnitudes.items():
            budgets[metric_id] += magnitude
        rules[key] = (rule, seen_outcomes)
    for i, rule in enumerate(value['rules']):
        seen_dependencies = set()
        for j, dep in enumerate(rule['requires']):
            path = f'$.rules[{i}].requires[{j}]'
            _object(dep, {'event_id', 'outcome_id'}, path)
            event = _id(dep['event_id'], path + '.event_id')
            outcome = _id(dep['outcome_id'], path + '.outcome_id')
            if event not in rules or outcome not in rules[event][1]:
                _error(path, 'unknown event or outcome reference')
            if event in seen_dependencies:
                _error(path, 'duplicate or conflicting dependency event')
            seen_dependencies.add(event)
            if rules[event][0]['at_tick'] >= rule['at_tick']:
                _error(path, 'dependencies must refer to strictly earlier ticks')
    if any(magnitude > _LIMITS['metric_magnitude'] for magnitude in budgets.values()):
        _error('$.metrics', 'conservative total metric magnitude exceeds limit')
    return deepcopy(value)


def _draw(seed: int, world_id: int, rule_id: str) -> int:
    """Named, unbiased categorical draw; no process/global RNG state."""
    counter = 0
    space = 2**256
    limit = space - space % 10000
    while True:
        material = json.dumps(['event-chain-draw.v1', seed, world_id, rule_id, counter], separators=(',', ':')).encode()
        number = int.from_bytes(hashlib.sha256(material).digest(), 'big')
        if number < limit:
            return number % 10000
        counter += 1


def run_event_chain(value, worlds=100, seed=42) -> dict:
    """Validate completely, then execute bounded synthetic worlds and summaries."""
    checked = validate_event_chain(value)
    _integer(worlds, '$run.worlds', 1, _LIMITS['worlds'])
    _integer(seed, '$run.seed', -(2**63), 2**63 - 1)
    rules = sorted(checked['rules'], key=lambda rule: (rule['at_tick'], rule['id']))
    if worlds * len(rules) > _LIMITS['world_rule_visits']:
        _error('$run', 'world-rule visits exceed workload limit')
    max_effect_visits = sum(max(len(outcome['effects']) for outcome in rule['outcomes']) for rule in rules) * worlds
    if max_effect_visits > _LIMITS['world_effect_visits']:
        _error('$run', 'world-effect visits exceed workload limit')
    params = checked['parameters']
    def resolve(number):
        return params[number['parameter']] if type(number) is dict else number
    # Bound the largest serialized world and distinct path before executing.
    # Provenance remains attached to each event for self-contained audit traces.
    # ASCII escaping gives a conservative bound for ordinary JSON exporters.
    def encoded_size(item):
        return len(json.dumps(item, ensure_ascii=True, separators=(',', ':')).encode())
    maximum_trace, maximum_selected = [], {}
    for rule in rules:
        traces = [
            {'rule_id': rule['id'], 'at_tick': rule['at_tick'], 'actor_id': rule['actor_id'],
             'status': 'executed', 'outcome_id': outcome['id'], 'draw_bps': 9999,
             'probability_bps': resolve(outcome['probability_bps']),
             'effects': [dict(effect, delta=resolve(effect['delta'])) for effect in outcome['effects']],
             'probability_provenance': rule['probability_provenance']}
            for outcome in rule['outcomes']
        ]
        maximum_trace.append(max(traces, key=encoded_size))
        maximum_selected[rule['id']] = max((o['id'] for o in rule['outcomes']), key=len)
    largest_world = {'world_id': worlds - 1, 'selected_outcomes': maximum_selected,
                     'metrics': {metric['id']: -_LIMITS['metric_magnitude'] for metric in checked['metrics']},
                     'trace': maximum_trace}
    largest_path = {'selected_outcomes': maximum_selected, 'count': worlds, 'frequency': 0.0001}
    # 128 bytes per world covers float representations/separators; fixed reserve
    # covers metric summaries, limitations and top-level fields.
    output_bound = worlds * (encoded_size(largest_world) + encoded_size(largest_path) + 128) + 65_536
    if output_bound > _LIMITS['output_bytes']:
        _error('$run', 'conservative serialized output exceeds byte limit')
    results, counts = [], Counter()
    for world_id in range(worlds):
        metrics = {metric['id']: metric['initial'] for metric in checked['metrics']}
        selected, trace = {}, []
        for rule in rules:
            if not all(selected.get(dep['event_id']) == dep['outcome_id'] for dep in rule['requires']):
                trace.append({'rule_id': rule['id'], 'at_tick': rule['at_tick'], 'status': 'skipped_dependency'})
                continue
            draw = _draw(seed, world_id, rule['id'])
            cumulative = 0
            for outcome in rule['outcomes']:
                cumulative += resolve(outcome['probability_bps'])
                if draw < cumulative:
                    break
            selected[rule['id']] = outcome['id']
            effects = [dict(effect, delta=resolve(effect['delta'])) for effect in outcome['effects']]
            changes = Counter()
            for effect in effects:
                changes[effect['metric_id']] += effect['delta']
            # All branches/bounds were validated before the first world. Apply
            # the selected outcome as one metric-state transition.
            updated = dict(metrics)
            for metric_id, delta in changes.items():
                updated[metric_id] += delta
            metrics = updated
            trace.append({'rule_id': rule['id'], 'at_tick': rule['at_tick'], 'actor_id': rule['actor_id'],
                          'status': 'executed', 'outcome_id': outcome['id'], 'draw_bps': draw,
                          'probability_bps': resolve(outcome['probability_bps']), 'effects': effects,
                          'probability_provenance': deepcopy(rule['probability_provenance'])})
        results.append({'world_id': world_id, 'selected_outcomes': selected, 'metrics': metrics, 'trace': trace})
        counts[tuple(selected.items())] += 1
    summary = {}
    for metric in checked['metrics']:
        ordered = sorted(result['metrics'][metric['id']] for result in results)
        def rank(percent):
            return ordered[max(0, math.ceil(percent * worlds / 100) - 1)]
        summary[metric['id']] = {'unit': metric['unit'], 'mean': sum(ordered) / worlds,
                                 'median': rank(50), 'p05': rank(5), 'p95': rank(95)}
    return {'schema_version': 'event-chain-result.v1', 'scenario_id': checked['id'], 'worlds': worlds, 'seed': seed,
            'world_results': results,
            'paths': [{'selected_outcomes': dict(path), 'count': count, 'frequency': count / worlds}
                      for path, count in sorted(counts.items())],
            'metrics': summary, 'limitations': list(_LIMITATIONS)}


def event_chain_capabilities() -> dict:
    """Publish the exact finite vocabulary; no inference or transport occurs."""
    return {
        'schema_version': 'event-chain.v1', 'level': 'declared_event_scenarios',
        'actions': ['adjust_metric'], 'parameter_type': 'integer',
        'probabilities': 'Exactly one categorical outcome per eligible rule; sum 10000 integer basis points.',
        'dependencies': 'AND of named outcomes from strictly earlier ticks; unmet dependencies skip the rule.',
        'ordering': 'Rules sorted by (at_tick, id); effects within an outcome applied atomically.',
        'randomness': 'SHA256 named draws keyed by seed, world_id and rule_id with rejection sampling.',
        'statistics': 'Mean and nearest-rank median/P05/P95 over actual completed worlds; no interpolation.',
        'bounds': dict(_LIMITS), 'limitations': list(_LIMITATIONS),
        'fields': {
            'required': ['schema_version', 'id', 'event_description', 'parameters', 'personas', 'metrics', 'rules', 'horizon_ticks', 'assumptions'],
            'parameters': 'Object mapping identifiers to supplied integers; no defaults.',
            'personas': {'required': ['id', 'name', 'description', 'role', 'allowed_actions']},
            'metrics': {'required': ['id', 'unit', 'initial']},
            'rules': {'required': ['id', 'at_tick', 'actor_id', 'requires', 'outcomes', 'probability_provenance']},
            'requires': {'required': ['event_id', 'outcome_id']},
            'outcomes': {'required': ['id', 'probability_bps', 'effects']},
            'effects': {'required': ['action', 'metric_id', 'delta']},
            'number': 'Literal integer or object with exactly {parameter: identifier}; probabilities 0..10000.',
            'probability_provenance': {'required': ['status', 'rationale', 'source_refs'], 'status': ['assumed', 'estimated', 'model_proposal']},
        },
    }
