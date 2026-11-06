"""Bounded, deterministic execution of supplied scene choices and metric effects.

Descriptions and declared probability sources are context, never inferred policy.
Snapshots prove internal replay consistency, not authorship or historical truth.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import sys

_LIMITS = {
    'input_bytes': 262144, 'snapshot_bytes': 524288, 'nodes': 50000, 'depth': 20,
    'scenes': 16, 'choices_per_scene': 8, 'outcomes_per_choice': 16, 'steps': 32,
    'metrics': 32, 'parameters': 128, 'personas': 64, 'effects_per_stage': 32,
    'total_effects': 4096, 'worlds': 10000, 'world_effect_visits': 1000000,
    'world_choice_visits': 1000000, 'integer_magnitude': 10**9,
    'metric_magnitude': 10**12, 'output_bytes': 16777216,
}
_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z')
_ENGINE_SHA256 = hashlib.sha256(Path(__file__).read_bytes() + sys.version.encode()).hexdigest()
_LIMITATIONS = [
    'Only supplied choices, integer metrics and adjust_metric effects execute; no model calls.',
    'Probabilities and provenance are declarations, not verified sources or calibrated forecasts.',
    'Metrics are scenario points, not conserved financial balances or withdrawable cash.',
    'Replay and content hashes establish internal consistency, not authorship or historical truth.',
    'Branch lineage is declared metadata; forks preserve future scene draws and do not offer rerolls.',
]
_SNAPSHOT_KEYS = {'schema_version', 'package', 'seed', 'world_id', 'scene_id', 'step_count',
                  'metrics', 'history', 'status', 'branch_id', 'parent_branch_id',
                  'source_sha256', 'input_sha256', 'engine_sha256'}
_HISTORY_KEYS = {'scene_id', 'choice_id', 'action_id', 'outcome_id', 'draw_bps', 'metrics_after', 'next_scene_id'}


def _error(path, reason):
    raise ValueError(f'{path}: {reason}')


def _object(value, keys, path):
    if type(value) is not dict or set(value) != keys:
        _error(path, 'expected object with exactly the declared fields')
    return value


def _list(value, path, maximum, minimum=0):
    if type(value) is not list or not minimum <= len(value) <= maximum:
        _error(path, 'invalid list type or size')
    return value


def _text(value, path, maximum=4096):
    if type(value) is not str or not value.strip() or len(value) > maximum:
        _error(path, 'expected bounded nonempty text')
    return value


def _id(value, path):
    if type(value) is not str or not _ID.fullmatch(value):
        _error(path, 'expected bounded ASCII identifier')
    return value


def _integer(value, path, low, high):
    if type(value) is not int or not low <= value <= high:
        _error(path, 'integer outside bounds or invalid integer type')
    return value


def _canonical(value, maximum=None):
    nodes = 0
    def walk(item, depth):
        nonlocal nodes
        nodes += 1
        if nodes > _LIMITS['nodes'] or depth > _LIMITS['depth']:
            _error('$', 'JSON tree exceeds size or depth limit')
        if type(item) is dict:
            if len(item) > _LIMITS['nodes']:
                _error('$', 'JSON object exceeds size limit')
            for key, child in item.items():
                if type(key) is not str or len(key) > 4096:
                    _error('$', 'invalid JSON object key')
                walk(child, depth + 1)
        elif type(item) is list:
            if len(item) > _LIMITS['nodes']:
                _error('$', 'JSON list exceeds size limit')
            for child in item:
                walk(child, depth + 1)
        elif type(item) is str:
            if len(item) > 4096:
                _error('$', 'JSON text exceeds size limit')
        elif type(item) is int:
            if abs(item) > _LIMITS['metric_magnitude']:
                _error('$', 'JSON integer exceeds magnitude limit')
        elif item is not None:
            _error('$', 'expected only JSON objects, lists, strings, integers or null')
    walk(value, 0)
    try:
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False,
                         separators=(',', ':')).encode('utf-8')
    except (ValueError, UnicodeError):
        _error('$', 'invalid JSON encoding')
    if len(raw) > (maximum or _LIMITS['input_bytes']):
        _error('$', 'JSON input exceeds byte limit')
    return raw


def _digest(value):
    return hashlib.sha256(_canonical(value, _LIMITS['snapshot_bytes'])).hexdigest()


def _number(value, parameters, path, low, high):
    if type(value) is dict:
        _object(value, {'parameter'}, path)
        key = _id(value['parameter'], path + '.parameter')
        if key not in parameters:
            _error(path, 'unknown parameter reference')
        value = parameters[key]
    return _integer(value, path, low, high)


def _unique(record, seen, path):
    key = _id(record['id'], path + '.id')
    if key in seen:
        _error(path, 'duplicate identifier')
    seen.add(key)
    return key


def validate_choice_world(package):
    """Return an independent validated input; raise ValueError on unsafe data."""
    _canonical(package)
    _object(package, {'schema_version', 'id', 'event_description', 'parameters', 'personas',
                      'metrics', 'scenes', 'initial_scene_id', 'policy', 'assumptions'}, '$')
    if package['schema_version'] != 'choice-world.v1':
        _error('$.schema_version', 'unsupported choice-world schema')
    _id(package['id'], '$.id')
    _text(package['event_description'], '$.event_description')
    params = package['parameters']
    if type(params) is not dict or len(params) > _LIMITS['parameters']:
        _error('$.parameters', 'expected bounded parameter object')
    for index, (key, item) in enumerate(params.items()):
        _id(key, f'$.parameters[{index}].key')
        _integer(item, f'$.parameters[{index}].value', -10**9, 10**9)
    for index, assumption in enumerate(_list(package['assumptions'], '$.assumptions', 128)):
        _text(assumption, f'$.assumptions[{index}]')
    actors, seen = {}, set()
    for index, actor in enumerate(_list(package['personas'], '$.personas', _LIMITS['personas'], 1)):
        path = f'$.personas[{index}]'
        _object(actor, {'id', 'name', 'description', 'role', 'allowed_actions'}, path)
        key = _unique(actor, seen, path)
        for field in ('name', 'description', 'role'):
            _text(actor[field], path + '.' + field)
        actions = _list(actor['allowed_actions'], path + '.allowed_actions', 1)
        if any(action != 'adjust_metric' for action in actions):
            _error(path, 'unsupported actor capability')
        actors[key] = actions
    metrics, seen = {}, set()
    for index, metric in enumerate(_list(package['metrics'], '$.metrics', _LIMITS['metrics'], 1)):
        path = f'$.metrics[{index}]'
        _object(metric, {'id', 'unit', 'initial', 'minimum', 'maximum'}, path)
        key = _unique(metric, seen, path)
        _text(metric['unit'], path + '.unit', 64)
        low = _integer(metric['minimum'], path + '.minimum', -10**12, 10**12)
        high = _integer(metric['maximum'], path + '.maximum', low, 10**12)
        _integer(metric['initial'], path + '.initial', low, high)
        metrics[key] = metric
    total_effects = 0
    def effects(value, path):
        nonlocal total_effects
        for index, effect in enumerate(_list(value, path, _LIMITS['effects_per_stage'])):
            epath = path + f'[{index}]'
            _object(effect, {'action', 'metric_id', 'delta'}, epath)
            if effect['action'] != 'adjust_metric':
                _error(epath, 'unsupported action')
            if _id(effect['metric_id'], epath + '.metric_id') not in metrics:
                _error(epath, 'unknown metric reference')
            _number(effect['delta'], params, epath + '.delta', -10**9, 10**9)
            total_effects += 1
            if total_effects > _LIMITS['total_effects']:
                _error('$.scenes', 'total effects exceed limit')
    scenes, seen = {}, set()
    links = []
    for index, scene in enumerate(_list(package['scenes'], '$.scenes', _LIMITS['scenes'], 1)):
        path = f'$.scenes[{index}]'
        _object(scene, {'id', 'title', 'description', 'choices'}, path)
        key = _unique(scene, seen, path)
        _text(scene['title'], path + '.title')
        _text(scene['description'], path + '.description')
        choices = set()
        for j, choice in enumerate(_list(scene['choices'], path + '.choices', _LIMITS['choices_per_scene'], 1)):
            cpath = path + f'.choices[{j}]'
            _object(choice, {'id', 'label', 'explanation', 'actor_id', 'requirements',
                             'immediate_effects', 'outcomes', 'probability_provenance'}, cpath)
            _unique(choice, choices, cpath)
            _text(choice['label'], cpath + '.label')
            _text(choice['explanation'], cpath + '.explanation')
            actor = _id(choice['actor_id'], cpath + '.actor_id')
            if actor not in actors or 'adjust_metric' not in actors[actor]:
                _error(cpath, 'unknown actor or missing adjust_metric capability')
            provenance = _object(choice['probability_provenance'], {'status', 'rationale', 'source_refs'}, cpath + '.probability_provenance')
            if type(provenance['status']) is not str or provenance['status'] not in {'assumed', 'estimated', 'model_proposal'}:
                _error(cpath + '.probability_provenance', 'unsupported provenance status')
            _text(provenance['rationale'], cpath + '.probability_provenance.rationale')
            for k, ref in enumerate(_list(provenance['source_refs'], cpath + '.probability_provenance.source_refs', 32)):
                _text(ref, cpath + f'.probability_provenance.source_refs[{k}]')
            requirements = set()
            for k, req in enumerate(_list(choice['requirements'], cpath + '.requirements', _LIMITS['metrics'])):
                rpath = cpath + f'.requirements[{k}]'
                _object(req, {'metric_id', 'minimum', 'maximum'}, rpath)
                mid = _id(req['metric_id'], rpath + '.metric_id')
                if mid not in metrics or mid in requirements:
                    _error(rpath, 'unknown or duplicate requirement metric')
                requirements.add(mid)
                low = _integer(req['minimum'], rpath + '.minimum', metrics[mid]['minimum'], metrics[mid]['maximum'])
                _integer(req['maximum'], rpath + '.maximum', low, metrics[mid]['maximum'])
            effects(choice['immediate_effects'], cpath + '.immediate_effects')
            outcomes, probability_sum = set(), 0
            for k, outcome in enumerate(_list(choice['outcomes'], cpath + '.outcomes', _LIMITS['outcomes_per_choice'], 1)):
                opath = cpath + f'.outcomes[{k}]'
                _object(outcome, {'id', 'label', 'probability_bps', 'effects', 'next_scene_id'}, opath)
                _unique(outcome, outcomes, opath)
                _text(outcome['label'], opath + '.label')
                probability_sum += _number(outcome['probability_bps'], params, opath + '.probability_bps', 0, 10000)
                effects(outcome['effects'], opath + '.effects')
                target = outcome['next_scene_id']
                if target is not None:
                    _id(target, opath + '.next_scene_id')
                    links.append((key, target, opath))
            if probability_sum != 10000:
                _error(cpath + '.outcomes', 'probabilities must sum to 10000 basis points')
        scenes[key] = choices
    initial = _id(package['initial_scene_id'], '$.initial_scene_id')
    if initial not in scenes:
        _error('$.initial_scene_id', 'unknown initial scene')
    edges = {key: set() for key in scenes}
    for source, target, path in links:
        if target not in scenes:
            _error(path, 'unknown scene reference')
        edges[source].add(target)
    visiting, visited = set(), set()
    def visit(key):
        if key in visiting:
            _error('$.scenes', 'scene links must form an acyclic graph')
        if key not in visited:
            visiting.add(key)
            for target in edges[key]:
                visit(target)
            visiting.remove(key)
            visited.add(key)
    for key in scenes:
        visit(key)
    policy = package['policy']
    if type(policy) is not dict or set(policy) != set(scenes):
        _error('$.policy', 'explicit policy required for every scene')
    for index, (key, ordering) in enumerate(policy.items()):
        _list(ordering, f'$.policy[{index}]', _LIMITS['choices_per_scene'], 1)
        prior = set()
        for item in ordering:
            _id(item, f'$.policy[{index}]')
            if item not in scenes[key] or item in prior:
                _error(f'$.policy[{index}]', 'unknown or duplicate policy choice')
            prior.add(item)
    return deepcopy(package)


def _resolve(package):
    result = deepcopy(package)
    params = result['parameters']
    for scene in result['scenes']:
        for choice in scene['choices']:
            stages = [choice['immediate_effects']]
            for outcome in choice['outcomes']:
                outcome['probability_bps'] = _number(outcome['probability_bps'], params, '$', 0, 10000)
                stages.append(outcome['effects'])
            for stage in stages:
                for effect in stage:
                    effect['delta'] = _number(effect['delta'], params, '$', -10**9, 10**9)
    return result


def _apply(metrics, effects):
    result = metrics.copy()
    changes = Counter()
    for effect in effects:
        changes[effect['metric_id']] += effect['delta']
    for key, delta in changes.items():
        result[key] += delta
    return result


def _in_bounds(metrics, package):
    return all(m['minimum'] <= metrics[m['id']] <= m['maximum'] for m in package['metrics'])


def _reason(choice, metrics, package):
    if any(not r['minimum'] <= metrics[r['metric_id']] <= r['maximum'] for r in choice['requirements']):
        return 'Current metrics do not satisfy this choice requirement.'
    immediate = _apply(metrics, choice['immediate_effects'])
    if not _in_bounds(immediate, package):
        return 'Immediate effects would exceed declared metric bounds.'
    if any(o['probability_bps'] > 0 and not _in_bounds(_apply(immediate, o['effects']), package)
           for o in choice['outcomes']):
        return 'A possible outcome would exceed declared metric bounds.'
    return None


def _scene(package, scene_id):
    return next(scene for scene in package['scenes'] if scene['id'] == scene_id)


def _status(snapshot, resolved):
    if snapshot['scene_id'] is None:
        return 'completed'
    if snapshot['step_count'] >= _LIMITS['steps']:
        return 'blocked'
    choices = _scene(resolved, snapshot['scene_id'])['choices']
    return 'active' if any(_reason(c, snapshot['metrics'], resolved) is None for c in choices) else 'blocked'


def _new(package, seed, world_id, source_hash=None, input_hash=None):
    result = {'schema_version': 'choice-world-snapshot.v1', 'package': deepcopy(package),
              'seed': seed, 'world_id': world_id, 'scene_id': package['initial_scene_id'], 'step_count': 0,
              'metrics': {metric['id']: metric['initial'] for metric in package['metrics']},
              'history': [], 'status': 'active', 'branch_id': 'main', 'parent_branch_id': None,
              'source_sha256': source_hash or _digest(package),
              'input_sha256': input_hash or _digest({'package': package, 'seed': seed, 'world_id': world_id}),
              'engine_sha256': _ENGINE_SHA256}
    result['status'] = _status(result, _resolve(package))
    return result


def start_choice_world(package, seed=42, world_id=0):
    """Start a fresh experiment with no inferred policy or provider calls."""
    package = validate_choice_world(package)
    _integer(seed, '$.seed', 0, 10**9)
    _integer(world_id, '$.world_id', 0, 10**9)
    return _new(package, seed, world_id)


def _step(snapshot, choice_id, action_id, resolved):
    if snapshot['status'] != 'active':
        _error('$.status', 'world is not active')
    choices = _scene(resolved, snapshot['scene_id'])['choices']
    choice = next((c for c in choices if c['id'] == choice_id), None)
    if choice is None:
        _error('$.choice_id', 'unknown choice in current scene')
    reason = _reason(choice, snapshot['metrics'], resolved)
    if reason is not None:
        _error('$.choice_id', reason)
    # Integer rejection sampling avoids modulo bias; the named stream has no branch/action input.
    counter, ceiling = 0, (1 << 256) - ((1 << 256) % 10000)
    while True:
        raw = hashlib.sha256(json.dumps(['choice-world.v1', snapshot['seed'], snapshot['world_id'],
                                         snapshot['scene_id'], counter], separators=(',', ':')).encode()).digest()
        draw = int.from_bytes(raw, 'big')
        if draw < ceiling:
            draw %= 10000
            break
        counter += 1
    threshold = 0
    for outcome in choice['outcomes']:
        threshold += outcome['probability_bps']
        if draw < threshold:
            break
    metrics = _apply(_apply(snapshot['metrics'], choice['immediate_effects']), outcome['effects'])
    snapshot['history'].append({'scene_id': snapshot['scene_id'], 'choice_id': choice_id,
                                'action_id': action_id, 'outcome_id': outcome['id'], 'draw_bps': draw,
                                'metrics_after': metrics.copy(), 'next_scene_id': outcome['next_scene_id']})
    snapshot['metrics'] = metrics
    snapshot['scene_id'] = outcome['next_scene_id']
    snapshot['step_count'] += 1
    snapshot['status'] = _status(snapshot, resolved)
    return snapshot


def validate_choice_snapshot(snapshot):
    """Replay complete original input and reject mismatched state or engine identity."""
    _canonical(snapshot, _LIMITS['snapshot_bytes'])
    _object(snapshot, _SNAPSHOT_KEYS, '$')
    if snapshot['schema_version'] != 'choice-world-snapshot.v1':
        _error('$.schema_version', 'unsupported snapshot schema')
    if snapshot['engine_sha256'] != _ENGINE_SHA256:
        _error('$.engine_sha256', 'snapshot uses a different execution engine')
    package = validate_choice_world(snapshot['package'])
    seed = _integer(snapshot['seed'], '$.seed', 0, 10**9)
    world_id = _integer(snapshot['world_id'], '$.world_id', 0, 10**9)
    _id(snapshot['branch_id'], '$.branch_id')
    if snapshot['parent_branch_id'] is not None:
        _id(snapshot['parent_branch_id'], '$.parent_branch_id')
        if snapshot['parent_branch_id'] == snapshot['branch_id']:
            _error('$.parent_branch_id', 'branch cannot be its own parent')
    expected = _new(package, seed, world_id)
    resolved, seen = _resolve(package), set()
    for index, history in enumerate(_list(snapshot['history'], '$.history', _LIMITS['steps'])):
        path = f'$.history[{index}]'
        _object(history, _HISTORY_KEYS, path)
        action_id = _id(history['action_id'], path + '.action_id')
        choice_id = _id(history['choice_id'], path + '.choice_id')
        if action_id in seen:
            _error(path, 'duplicate historical action ID')
        seen.add(action_id)
        _step(expected, choice_id, action_id, resolved)
        if expected['history'][-1] != history:
            _error(path, 'history does not match deterministic replay')
    expected['branch_id'] = snapshot['branch_id']
    expected['parent_branch_id'] = snapshot['parent_branch_id']
    if expected != snapshot:
        _error('$', 'snapshot does not match input identity and replayed state')
    return deepcopy(expected)


def choice_options(snapshot):
    """Expose resolved effects and odds, with bounded, safe disabled reasons."""
    snapshot = validate_choice_snapshot(snapshot)
    if snapshot['scene_id'] is None:
        return []
    resolved = _resolve(snapshot['package'])
    choices = _scene(resolved, snapshot['scene_id'])['choices']
    for choice in choices:
        reason = _reason(choice, snapshot['metrics'], resolved)
        if snapshot['step_count'] >= _LIMITS['steps']:
            reason = 'World reached the step limit.'
        choice['eligible'] = reason is None
        choice['disabled_reason'] = reason
    return choices


def step_choice_world(snapshot, choice_id, action_id):
    """Atomically apply an eligible choice, or return current state for an old action."""
    snapshot = validate_choice_snapshot(snapshot)
    _id(choice_id, '$.choice_id')
    _id(action_id, '$.action_id')
    for history in snapshot['history']:
        if history['action_id'] == action_id:
            if history['choice_id'] != choice_id:
                _error('$.action_id', 'action ID was already used with another choice')
            return snapshot
    return _step(snapshot, choice_id, action_id, _resolve(snapshot['package']))


def fork_choice_world(snapshot, branch_id):
    """Copy replayed state; branch metadata does not enter any outcome draw."""
    snapshot = validate_choice_snapshot(snapshot)
    _id(branch_id, '$.branch_id')
    if branch_id == snapshot['branch_id']:
        _error('$.branch_id', 'new branch ID must differ from current branch')
    snapshot['parent_branch_id'] = snapshot['branch_id']
    snapshot['branch_id'] = branch_id
    return snapshot


def _percentile(values, fraction):
    position = (len(values) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    return values[lower] + (values[upper] - values[lower]) * (position - lower)


def run_choice_policy(package, worlds=100, seed=42):
    """Run explicit first-eligible policies and retain every requested world."""
    package = validate_choice_world(package)
    _integer(worlds, '$.worlds', 1, _LIMITS['worlds'])
    _integer(seed, '$.seed', 0, 10**9)
    choices = [choice for scene in package['scenes'] for choice in scene['choices']]
    effect_visits = sum(len(c['immediate_effects']) + sum(len(o['effects']) for o in c['outcomes']) for c in choices)
    if worlds * max(1, effect_visits) > _LIMITS['world_effect_visits'] or worlds * len(choices) > _LIMITS['world_choice_visits']:
        _error('$.worlds', 'batch work exceeds declared limit')
    resolved = _resolve(package)
    source_hash = _digest(package)
    status_counts = {'completed': 0, 'blocked': 0}
    paths, metric_values = Counter(), {m['id']: [] for m in package['metrics']}
    blocked_reasons = Counter()
    path_values = {}
    for world_id in range(worlds):
        # No snapshots are exposed here; avoid repeated package hashing/replay for each step.
        snapshot = _new(package, seed, world_id, source_hash, 'batch-internal')
        policy_exhausted = False
        while snapshot['status'] == 'active':
            scene = _scene(resolved, snapshot['scene_id'])
            by_id = {c['id']: c for c in scene['choices']}
            choice = next((by_id[key] for key in package['policy'][scene['id']]
                           if _reason(by_id[key], snapshot['metrics'], resolved) is None), None)
            if choice is None:
                snapshot['status'] = 'blocked'
                blocked_reasons['policy_exhausted'] += 1
                policy_exhausted = True
                break
            _step(snapshot, choice['id'], f'policy-{snapshot["step_count"]}', resolved)
        status_counts[snapshot['status']] += 1
        if snapshot['status'] == 'blocked' and not policy_exhausted:
            blocked_reasons['no_eligible_choices'] += 1
        key = (snapshot['status'], tuple((h['scene_id'], h['choice_id'], h['outcome_id']) for h in snapshot['history']))
        paths[key] += 1
        grouped = path_values.setdefault(key, {mid: [] for mid in metric_values})
        for mid in metric_values:
            metric_values[mid].append(snapshot['metrics'][mid])
            grouped[mid].append(snapshot['metrics'][mid])
    def summary(values):
        values = sorted(values)
        return {'minimum': values[0], 'maximum': values[-1], 'mean': sum(values) / len(values),
                'median': _percentile(values, .5), 'p05': _percentile(values, .05),
                'p95': _percentile(values, .95)}
    stats = []
    for metric in package['metrics']:
        stats.append({'id': metric['id'], 'unit': metric['unit'], **summary(metric_values[metric['id']])})
    result = {'schema_version': 'choice-world-results.v1', 'worlds': worlds, 'seed': seed,
              'source_sha256': source_hash, 'input_sha256': _digest({'package': package, 'seed': seed, 'worlds': worlds}),
              'engine_sha256': _ENGINE_SHA256, 'status_counts': status_counts,
              'blocked_reasons': dict(blocked_reasons), 'metrics': stats,
              'paths': [{'status': status, 'path': [{'scene_id': s, 'choice_id': c, 'outcome_id': o} for s, c, o in path],
                         'count': count, 'frequency': count / worlds,
                         'metrics': {mid: summary(values) for mid, values in path_values[(status, path)].items()}}
                        for (status, path), count in sorted(paths.items())], 'limitations': list(_LIMITATIONS)}
    if len(json.dumps(result, ensure_ascii=False).encode()) > _LIMITS['output_bytes']:
        _error('$.worlds', 'batch output exceeds limit')
    return result


def choice_world_capabilities():
    """Publish every required input field without inventing executable values.

    Contracts are descriptive authoring data. ``contract`` names refer to other
    entries in ``fields``; all objects have exactly their declared required keys.
    """
    def integer(minimum, maximum):
        return {'type': 'integer', 'minimum': minimum, 'maximum': maximum,
                'boolean_is_integer': False}

    def text(maximum=4096):
        return {'type': 'string', 'nonempty': True, 'max_characters': maximum}

    def identifier(reference=None):
        value = {'type': 'string', 'pattern': '[A-Za-z0-9][A-Za-z0-9_.-]{0,63}'}
        if reference is not None:
            value['reference'] = reference
        return value

    def array(contract, maximum, minimum=0):
        return {'type': 'array', 'minimum_items': minimum, 'maximum_items': maximum,
                'items': {'contract': contract}}

    def record(fields, constraints=None):
        result = {'type': 'object', 'required': list(fields), 'additional_fields': False,
                  'fields': fields}
        if constraints:
            result['constraints'] = constraints
        return result

    def number(minimum, maximum):
        return {'contract': 'number', 'minimum': minimum, 'maximum': maximum,
                'bounds_apply_after_parameter_resolution': True}

    fields = {
        'package': record({
            'schema_version': {'type': 'string', 'const': 'choice-world.v1'},
            'id': identifier(), 'event_description': text(),
            'parameters': {'contract': 'parameters'},
            'personas': array('persona', _LIMITS['personas'], 1),
            'metrics': array('metric', _LIMITS['metrics'], 1),
            'scenes': array('scene', _LIMITS['scenes'], 1),
            'initial_scene_id': identifier('scene.id'), 'policy': {'contract': 'policy'},
            'assumptions': {'type': 'array', 'minimum_items': 0, 'maximum_items': 128,
                            'items': text()},
        }, ['Persona, metric and scene IDs are unique within their respective arrays.']),
        'parameters': {'type': 'object', 'maximum_properties': _LIMITS['parameters'],
                       'keys': identifier(), 'values': integer(-10**9, 10**9),
                       'defaults': None},
        'persona': record({
            'id': identifier(), 'name': text(), 'description': text(), 'role': text(),
            'allowed_actions': {'type': 'array', 'minimum_items': 0, 'maximum_items': 1,
                                'items': {'type': 'string', 'enum': ['adjust_metric']}},
        }, ['Any persona referenced by a choice must allow adjust_metric. Descriptions execute no behavior.']),
        'metric': record({
            'id': identifier(), 'unit': text(64), 'initial': integer(-10**12, 10**12),
            'minimum': integer(-10**12, 10**12), 'maximum': integer(-10**12, 10**12),
        }, ['minimum <= initial <= maximum; declared units are not financial settlement.']),
        'scene': record({
            'id': identifier(), 'title': text(), 'description': text(),
            'choices': array('choice', _LIMITS['choices_per_scene'], 1),
        }, ['Choice IDs must be unique within each scene. All next-scene links form a finite DAG, including zero-probability links.']),
        'choice': record({
            'id': identifier(), 'label': text(), 'explanation': text(),
            'actor_id': identifier('persona.id with adjust_metric capability'),
            'requirements': array('requirement', _LIMITS['metrics']),
            'immediate_effects': array('effect', _LIMITS['effects_per_stage']),
            'outcomes': array('outcome', _LIMITS['outcomes_per_choice'], 1),
            'probability_provenance': {'contract': 'probability_provenance'},
        }, ['Resolved outcome probabilities sum to exactly 10000 basis points.',
            'Eligibility checks current requirements, atomic immediate effects, and every positive-probability outcome against all metric bounds.']),
        'requirement': record({
            'metric_id': identifier('metric.id'), 'minimum': integer(-10**12, 10**12),
            'maximum': integer(-10**12, 10**12),
        }, ['Each metric may occur once per choice requirement list.',
            'metric.minimum <= requirement.minimum <= requirement.maximum <= metric.maximum.']),
        'effect': record({
            'action': {'type': 'string', 'const': 'adjust_metric'},
            'metric_id': identifier('metric.id'), 'delta': number(-10**9, 10**9),
        }, ['Effects in one stage aggregate atomically per metric; immediate and realized outcome are separate bounded stages.']),
        'outcome': record({
            'id': identifier(), 'label': text(), 'probability_bps': number(0, 10000),
            'effects': array('effect', _LIMITS['effects_per_stage']),
            'next_scene_id': {**identifier('scene.id'), 'nullable': True,
                              'null_means': 'complete this world'},
        }, ['Outcome IDs must be unique within their choice. Zero-probability effects do not affect eligibility.']),
        'number': {
            'literal': integer(-10**9, 10**9),
            'parameter_reference': record({'parameter': identifier('parameters key')}),
            'alternatives': ['literal', 'parameter_reference'],
            'resolution': 'Use the supplied parameter integer; no inference, substitution or defaults.',
        },
        'probability_provenance': record({
            'status': {'type': 'string', 'enum': ['assumed', 'estimated', 'model_proposal']},
            'rationale': text(),
            'source_refs': {'type': 'array', 'minimum_items': 0, 'maximum_items': 32,
                            'items': text()},
        }, ['Rationale and source references are supplied declarations, not verified evidence.']),
        'policy': {
            'type': 'object', 'keys': identifier('scene.id'),
            'required_keys': 'Every declared scene ID exactly once; no other keys.',
            'values': {'type': 'array', 'minimum_items': 1,
                       'maximum_items': _LIMITS['choices_per_scene'], 'unique': True,
                       'items': identifier('choice.id in this same scene')},
            'choice_order': 'first_eligible',
            'exhaustion': 'Count world as blocked with policy_exhausted; never use an unlisted choice or drop the world.',
        },
    }
    return {
        'schema_version': 'choice-world.v1', 'kind': 'declared_interactive_choices', 'model_calls': 0,
        'defaults_or_estimates': None, 'actions': ['adjust_metric'], 'fields': fields,
        'assumptions': {
            'parameter_values': 'supplied_integer_values_only',
            'persona_behavior': 'declared_choices_and_explicit_policy_only',
            'probability_calibration': 'supplied_unverified',
            'source_verification': 'none', 'financial_settlement': 'none',
            'unknown_values': 'Keep unknown authoring inputs null; execution requires complete valid values.',
            'authoring_fields': 'Draft fields are caller-authored typed values targeting existing object leaves. Integer parameter targets can use /parameters/<id>; never infer field values.',
        },
        'snapshot_schema': 'choice-world-snapshot.v1', 'result_schema': 'choice-world-results.v1',
        'statuses': ['active', 'completed', 'blocked'],
        'probability_statuses': ['assumed', 'estimated', 'model_proposal'],
        'draw_key': ['seed', 'world_id', 'scene_id'],
        'randomness': 'SHA256 named draws with integer rejection sampling; action and branch IDs do not enter draws.',
        'statistics': 'Actual final metrics over every requested world, including blocked worlds; linear-interpolated median/P05/P95, both overall and per path.',
        'run': {'worlds': integer(1, _LIMITS['worlds']), 'seed': integer(0, 10**9),
                'world_id': integer(0, 10**9)},
        'limits': dict(_LIMITS), 'engine_sha256': _ENGINE_SHA256,
        'limitations': list(_LIMITATIONS),
    }
