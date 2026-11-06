"""Bounded evaluation of declared conditions over timestamped observations.

An observation may influence only evaluations at or after its ``available_at_seconds``,
so detection and delivery latency stay separate from the measured event. A missing
reference, a stale series or an unconfirmed transition produces ``unknown``, never a
silent non-event. Values are integers in a declared unit; nothing here settles cash.
"""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import sys

_LIMITS = {
    'input_bytes': 262144, 'output_bytes': 16777216, 'nodes': 50000, 'depth': 20,
    'series': 32, 'samples_per_series': 20000, 'total_samples': 100000,
    'conditions': 64, 'stages': 32, 'transitions': 64, 'actors': 64,
    'parameters': 128, 'assumptions': 128, 'evaluations': 200000, 'firings': 10000,
    'sample_visits': 10000000, 'window_seconds': 10**9, 'seconds_magnitude': 10**12,
    'value_magnitude': 10**12, 'threshold_bps': 10**6, 'persistence': 1000,
}
_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z')
_REFERENCE_KINDS = {'prior_sample_window', 'rolling_peak_window', 'window_aggregate'}
_AGGREGATIONS = {'maximum', 'minimum', 'last', 'mean_floor'}
_DIRECTIONS = {'at_or_below', 'at_or_above'}
_RESET_RULES = {'on_non_true', 'on_false_only', 'never'}
_OUTCOMES = {'fired', 'true_holding', 'awaiting_rearm', 'cooldown', 'false',
             'unknown_reference', 'stale', 'no_current', 'outside_stage', 'unknown_member'}
_TRUE_OUTCOMES = {'fired', 'true_holding', 'awaiting_rearm', 'cooldown'}
_ENGINE_SHA256 = hashlib.sha256(Path(__file__).read_bytes() + sys.version.encode()).hexdigest()
_LIMITATIONS = [
    'Only declared series samples, stages and conditions evaluate; no model calls and no network reads.',
    'Sample values are author-supplied observations, not verified venue data or a complete market history.',
    'Condition firing is an alert; it does not establish a fill, a price, a fee or withdrawable cash.',
    'Unconfirmed transitions never advance a stage; a cap or price level is not protocol confirmation.',
    'Threshold examples are stress cases, not calibrated occurrence odds.',
    'Evaluation is deterministic from declared input; replay proves internal consistency only.',
]


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
    if type(value) is not int or type(value) is bool or not low <= value <= high:
        _error(path, 'integer outside bounds or invalid integer type')
    return value


def _boolean(value, path):
    if type(value) is not bool:
        _error(path, 'expected boolean')
    return value


def _choice(value, allowed, path, reason):
    """Membership on a declared set, after a type check: unhashable input must not escape as TypeError."""
    if type(value) is not str or value not in allowed:
        _error(path, reason)
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
        elif type(item) is bool:
            pass
        elif type(item) is int:
            if abs(item) > _LIMITS['value_magnitude']:
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
    return hashlib.sha256(_canonical(value, _LIMITS['output_bytes'])).hexdigest()


def _unique(record, seen, path):
    key = _id(record['id'], path + '.id')
    if key in seen:
        _error(path, 'duplicate identifier')
    seen.add(key)
    return key


def _number(value, parameters, path, low, high):
    if type(value) is dict:
        _object(value, {'parameter'}, path)
        key = _id(value['parameter'], path + '.parameter')
        if key not in parameters:
            _error(path, 'unknown parameter reference')
        value = parameters[key]
    return _integer(value, path, low, high)


def _validate_reference(value, parameters, path):
    kind = value.get('kind') if type(value) is dict else None
    if kind == 'prior_sample_window':
        _object(value, {'kind', 'window_seconds', 'tolerance_seconds'}, path)
        return {'kind': kind,
                'window_seconds': _number(value['window_seconds'], parameters,
                                          path + '.window_seconds', 1, _LIMITS['window_seconds']),
                'tolerance_seconds': _number(value['tolerance_seconds'], parameters,
                                             path + '.tolerance_seconds', 0, _LIMITS['window_seconds'])}
    if kind == 'rolling_peak_window':
        _object(value, {'kind', 'window_seconds'}, path)
        return {'kind': kind,
                'window_seconds': _number(value['window_seconds'], parameters,
                                          path + '.window_seconds', 1, _LIMITS['window_seconds'])}
    if kind == 'window_aggregate':
        _object(value, {'kind', 'start_seconds', 'end_seconds', 'aggregation'}, path)
        low = _number(value['start_seconds'], parameters, path + '.start_seconds', 0,
                      _LIMITS['seconds_magnitude'])
        high = _number(value['end_seconds'], parameters, path + '.end_seconds',
                       low + 1, _LIMITS['seconds_magnitude'])
        aggregation = _choice(value['aggregation'], _AGGREGATIONS, path + '.aggregation',
                              'unsupported window aggregation')
        return {'kind': kind, 'start_seconds': low, 'end_seconds': high,
                'aggregation': aggregation}
    _error(path + '.kind', 'unsupported reference kind')


def _validate_comparison(value, parameters, path):
    _object(value, {'mode', 'direction', 'threshold_bps', 'threshold'}, path)
    direction = _choice(value['direction'], _DIRECTIONS, path + '.direction',
                        'unsupported comparison direction')
    if value['mode'] == 'ratio_bps':
        _integer(value['threshold'], path + '.threshold', 0, 0)
        return {'mode': 'ratio_bps', 'direction': direction,
                'threshold_bps': _number(value['threshold_bps'], parameters, path + '.threshold_bps',
                                         1, _LIMITS['threshold_bps']),
                'threshold': None}
    if value['mode'] == 'absolute':
        _integer(value['threshold_bps'], path + '.threshold_bps', 0, 0)
        return {'mode': 'absolute', 'direction': direction, 'threshold_bps': None,
                'threshold': _number(value['threshold'], parameters, path + '.threshold',
                                     -_LIMITS['value_magnitude'], _LIMITS['value_magnitude'])}
    _error(path + '.mode', 'unsupported comparison mode')


def _validate_sample(value, parameters, path):
    _object(value, {'id', 'at_seconds', 'available_at_seconds', 'value', 'source'}, path)
    sample_id = _id(value['id'], path + '.id')
    at = _number(value['at_seconds'], parameters, path + '.at_seconds', 0, _LIMITS['seconds_magnitude'])
    available = _number(value['available_at_seconds'], parameters, path + '.available_at_seconds',
                        0, _LIMITS['seconds_magnitude'])
    if available < at:
        _error(path, 'sample is available before its event time')
    _text(value['source'], path + '.source', 512)
    return {'id': sample_id, 'at_seconds': at, 'available_at_seconds': available,
            'value': _number(value['value'], parameters, path + '.value',
                             -_LIMITS['value_magnitude'], _LIMITS['value_magnitude']),
            'source': value['source']}


def _index(rows):
    """Event-time ordering with a stable tie-break; availability is checked per query."""
    ordered = sorted(rows, key=lambda row: (row['at_seconds'], row['available_at_seconds'], row['id']))
    return {'rows': ordered, 'at': [row['at_seconds'] for row in ordered],
            'value': [row['value'] for row in ordered]}


def _visible(index, upper_at, at, visits):
    """Newest event time at or below ``upper_at`` whose data had arrived by ``at``."""
    position = bisect_right(index['at'], upper_at)
    rows = index['rows']
    for cursor in range(position - 1, -1, -1):
        visits[0] += 1
        if rows[cursor]['available_at_seconds'] <= at:
            return rows[cursor]
    return None


def _reference_value(index, reference, at, visits):
    """Declared reference measurement, or None when it cannot be established."""
    rows, positions = index['rows'], index['at']
    if reference['kind'] == 'prior_sample_window':
        target = at - reference['window_seconds']
        row = _visible(index, target, at, visits)
        if row is None or target - row['at_seconds'] > reference['tolerance_seconds']:
            return None
        return row['value']
    if reference['kind'] == 'rolling_peak_window':
        window = reference['window_seconds']
        low = bisect_right(positions, at - window)
        high = bisect_right(positions, at)
        best = None
        for cursor in range(low, high):
            visits[0] += 1
            row = rows[cursor]
            if row['available_at_seconds'] <= at and (best is None or row['value'] > best):
                best = row['value']
        return best
    low = bisect_left(positions, reference['start_seconds'])
    high = bisect_left(positions, reference['end_seconds'])
    values, last = [], None
    for cursor in range(low, high):
        visits[0] += 1
        row = rows[cursor]
        if row['available_at_seconds'] <= at:
            values.append(row['value'])
            if reference['aggregation'] == 'last' and (last is None or row['at_seconds'] >= last[0]):
                last = (row['at_seconds'], row['available_at_seconds'], row['value'])
    if not values:
        return None
    if reference['aggregation'] == 'maximum':
        return max(values)
    if reference['aggregation'] == 'minimum':
        return min(values)
    if reference['aggregation'] == 'mean_floor':
        return sum(values) // len(values)
    return last[2]


def _is_true(comparison, value, reference_value):
    if comparison['mode'] == 'absolute':
        return value <= comparison['threshold'] if comparison['direction'] == 'at_or_below' \
            else value >= comparison['threshold']
    if reference_value is None or reference_value <= 0:
        return None
    left, right = value * 10000, comparison['threshold_bps'] * reference_value
    return left <= right if comparison['direction'] == 'at_or_below' else left >= right


def _stage_at(timeline, initial, at):
    stage = initial
    for moment, _transition_id, target in timeline:
        if moment > at:
            break
        stage = target
    return stage


def validate_contingent_world(package):
    """Return an independent validated package; raise ValueError on unsafe data."""
    _canonical(package)
    _object(package, {'schema_version', 'id', 'question', 'parameters', 'start_seconds',
                      'end_seconds', 'actors', 'series', 'lifecycle', 'conditions', 'composites',
                      'assumptions'}, '$')
    if package['schema_version'] != 'contingent-world.v1':
        _error('$.schema_version', 'unsupported contingent-world schema')
    _id(package['id'], '$.id')
    _text(package['question'], '$.question')
    parameters = package['parameters']
    if type(parameters) is not dict or len(parameters) > _LIMITS['parameters']:
        _error('$.parameters', 'expected bounded parameter object')
    for index, (key, item) in enumerate(parameters.items()):
        _id(key, f'$.parameters[{index}].key')
        _integer(item, f'$.parameters[{index}].value', -_LIMITS['value_magnitude'],
                 _LIMITS['value_magnitude'])
    start = _number(package['start_seconds'], parameters, '$.start_seconds', 0,
                    _LIMITS['seconds_magnitude'])
    end = _number(package['end_seconds'], parameters, '$.end_seconds', start + 1,
                  _LIMITS['seconds_magnitude'])
    actors = set()
    for index, actor in enumerate(_list(package['actors'], '$.actors', _LIMITS['actors'])):
        path = f'$.actors[{index}]'
        _object(actor, {'id', 'label', 'role'}, path)
        _unique(actor, actors, path)
        _text(actor['label'], path + '.label', 256)
        _text(actor['role'], path + '.role', 256)
    total_samples = 0
    series, seen = {}, set()
    for index, item in enumerate(_list(package['series'], '$.series', _LIMITS['series'], 1)):
        path = f'$.series[{index}]'
        _object(item, {'id', 'unit', 'minimum', 'maximum', 'stale_after_seconds',
                       'actor_ids', 'samples'}, path)
        key = _unique(item, seen, path)
        _text(item['unit'], path + '.unit', 64)
        low = _integer(item['minimum'], path + '.minimum', -_LIMITS['value_magnitude'],
                       _LIMITS['value_magnitude'])
        high = _integer(item['maximum'], path + '.maximum', low, _LIMITS['value_magnitude'])
        stale = _integer(item['stale_after_seconds'], path + '.stale_after_seconds', 1,
                         _LIMITS['seconds_magnitude'])
        for j, actor_id in enumerate(_list(item['actor_ids'], path + '.actor_ids',
                                            _LIMITS['actors'], 1)):
            actor_id = _id(actor_id, path + f'.actor_ids[{j}]')
            if actor_id not in actors:
                _error(path + f'.actor_ids[{j}]', 'unknown actor reference')
        if len(item['actor_ids']) != len(set(item['actor_ids'])):
            _error(path + '.actor_ids', 'duplicate actor reference')
        rows, sample_ids = [], set()
        for j, raw in enumerate(_list(item['samples'], path + '.samples',
                                      _LIMITS['samples_per_series'], 1)):
            total_samples += 1
            if total_samples > _LIMITS['total_samples']:
                _error('$.series', 'total samples exceed limit')
            sample = _validate_sample(raw, parameters, path + f'.samples[{j}]')
            if sample['id'] in sample_ids:
                _error(path + f'.samples[{j}].id', 'duplicate sample identifier')
            if not low <= sample['value'] <= high:
                _error(path + f'.samples[{j}].value', 'sample value outside series bounds')
            sample_ids.add(sample['id'])
            rows.append(sample)
        series[key] = {'unit': item['unit'], 'minimum': low, 'maximum': high,
                       'stale_after_seconds': stale, 'actor_ids': list(item['actor_ids']),
                       'index': _index(rows)}
    stage_ids, seen = set(), set()
    lifecycle = _object(package['lifecycle'], {'initial_stage_id', 'stages', 'transitions'},
                        '$.lifecycle')
    for index, stage in enumerate(_list(lifecycle['stages'], '$.lifecycle.stages',
                                        _LIMITS['stages'], 1)):
        path = f'$.lifecycle.stages[{index}]'
        _object(stage, {'id', 'label'}, path)
        _unique(stage, seen, path)
        _text(stage['label'], path + '.label', 256)
        stage_ids.add(stage['id'])
    initial = _id(lifecycle['initial_stage_id'], '$.lifecycle.initial_stage_id')
    if initial not in stage_ids:
        _error('$.lifecycle.initial_stage_id', 'unknown initial stage')
    transitions, seen = [], set()
    for index, item in enumerate(_list(lifecycle['transitions'],
                                       '$.lifecycle.transitions', _LIMITS['transitions'])):
        path = f'$.lifecycle.transitions[{index}]'
        _object(item, {'id', 'from_stage_id', 'to_stage_id', 'effective_at_seconds',
                       'confirmed', 'source'}, path)
        _unique(item, seen, path)
        source_stage = _id(item['from_stage_id'], path + '.from_stage_id')
        target = _id(item['to_stage_id'], path + '.to_stage_id')
        if source_stage not in stage_ids or target not in stage_ids:
            _error(path, 'unknown stage reference')
        if source_stage == target:
            _error(path, 'transition cannot keep the same stage')
        _number(item['effective_at_seconds'], parameters, path + '.effective_at_seconds', 0,
                _LIMITS['seconds_magnitude'])
        _boolean(item['confirmed'], path + '.confirmed')
        _text(item['source'], path + '.source', 512)
        transitions.append({**deepcopy(item),
                            'effective_at_seconds': _number(item['effective_at_seconds'], parameters,
                                                            path + '.effective_at_seconds', 0,
                                                            _LIMITS['seconds_magnitude'])})
    cursor = initial
    for item in sorted(transitions, key=lambda t: (t['effective_at_seconds'], t['id'])):
        if not item['confirmed']:
            continue
        if item['from_stage_id'] != cursor:
            _error('$.lifecycle.transitions',
                   f'confirmed transition {item["id"]} leaves {item["from_stage_id"]} but the stage is {cursor}')
        cursor = item['to_stage_id']
    timeline = [(item['effective_at_seconds'], item['id'], item['to_stage_id'])
                for item in sorted(transitions, key=lambda t: (t['effective_at_seconds'], t['id']))
                if item['confirmed']]
    total_ticks = 0
    conditions, seen = {}, set()
    for index, item in enumerate(_list(package['conditions'], '$.conditions',
                                       _LIMITS['conditions'], 1)):
        path = f'$.conditions[{index}]'
        _object(item, {'id', 'series_id', 'stage_ids', 'evaluation', 'reference', 'comparison',
                       'persistence_consecutive', 'persistence_reset', 'cooldown_seconds',
                       'rearm_requires_false', 'detection_delay_seconds', 'explanation'}, path)
        key = _unique(item, seen, path)
        if _id(item['series_id'], path + '.series_id') not in series:
            _error(path + '.series_id', 'unknown series reference')
        declared = set()
        for j, stage in enumerate(_list(item['stage_ids'], path + '.stage_ids',
                                        _LIMITS['stages'], 1)):
            stage = _id(stage, path + f'.stage_ids[{j}]')
            if stage not in stage_ids or stage in declared:
                _error(path + f'.stage_ids[{j}]', 'unknown or duplicate stage reference')
            declared.add(stage)
        evaluation = _object(item['evaluation'], {'first_at_seconds', 'cadence_seconds',
                                                 'last_at_seconds'}, path + '.evaluation')
        first = _number(evaluation['first_at_seconds'], parameters,
                        path + '.evaluation.first_at_seconds', start, end)
        cadence = _integer(evaluation['cadence_seconds'], path + '.evaluation.cadence_seconds',
                           1, _LIMITS['window_seconds'])
        last = end if evaluation['last_at_seconds'] is None else \
            _number(evaluation['last_at_seconds'], parameters, path + '.evaluation.last_at_seconds',
                    first, end)
        ticks = 1 + (last - first) // cadence
        total_ticks += ticks
        if total_ticks > _LIMITS['evaluations']:
            _error('$.conditions', 'evaluation ticks exceed limit')
        conditions[key] = {
            'id': key, 'series_id': _id(item['series_id'], path + '.series_id'),
            'stage_ids': list(item['stage_ids']),
            'evaluation': {'first_at_seconds': first, 'cadence_seconds': cadence, 'last_at_seconds': last,
                           'ticks': ticks},
            'reference': _validate_reference(item['reference'], parameters, path + '.reference'),
            'comparison': _validate_comparison(item['comparison'], parameters, path + '.comparison'),
            'persistence_consecutive': _integer(item['persistence_consecutive'],
                                                path + '.persistence_consecutive', 1,
                                                _LIMITS['persistence']),
            'persistence_reset': _choice(item['persistence_reset'], _RESET_RULES,
                                         path + '.persistence_reset',
                                         'unsupported persistence reset rule'),
            'cooldown_seconds': _number(item['cooldown_seconds'], parameters,
                                        path + '.cooldown_seconds', 0, _LIMITS['seconds_magnitude']),
            'rearm_requires_false': _boolean(item['rearm_requires_false'], path + '.rearm_requires_false'),
            'detection_delay_seconds': _number(item['detection_delay_seconds'], parameters,
                                               path + '.detection_delay_seconds', 0,
                                               _LIMITS['seconds_magnitude']),
            'explanation': _text(item['explanation'], path + '.explanation')}
    composites, seen = {}, set()
    for index, item in enumerate(_list(package['composites'], '$.composites',
                                       _LIMITS['conditions'])):
        path = f'$.composites[{index}]'
        _object(item, {'id', 'all_of', 'stage_ids', 'evaluation', 'persistence_consecutive',
                       'persistence_reset', 'cooldown_seconds', 'rearm_requires_false',
                       'detection_delay_seconds', 'explanation'}, path)
        key = _unique(item, seen, path)
        if key in conditions:
            _error(path + '.id', 'composite id collides with a condition id')
        members = []
        for j, member in enumerate(_list(item['all_of'], path + '.all_of', 8, 2)):
            member = _id(member, path + f'.all_of[{j}]')
            if member not in conditions or member in members:
                _error(path + f'.all_of[{j}]', 'unknown or duplicate member condition')
            members.append(member)
        declared = set()
        for j, stage in enumerate(_list(item['stage_ids'], path + '.stage_ids',
                                        _LIMITS['stages'], 1)):
            stage = _id(stage, path + f'.stage_ids[{j}]')
            if stage not in stage_ids or stage in declared:
                _error(path + f'.stage_ids[{j}]', 'unknown or duplicate stage reference')
            declared.add(stage)
        evaluation = _object(item['evaluation'], {'first_at_seconds', 'cadence_seconds',
                                                 'last_at_seconds'}, path + '.evaluation')
        first = _number(evaluation['first_at_seconds'], parameters,
                        path + '.evaluation.first_at_seconds', start, end)
        cadence = _integer(evaluation['cadence_seconds'], path + '.evaluation.cadence_seconds',
                           1, _LIMITS['window_seconds'])
        last = end if evaluation['last_at_seconds'] is None else \
            _number(evaluation['last_at_seconds'], parameters, path + '.evaluation.last_at_seconds',
                    first, end)
        ticks = 1 + (last - first) // cadence
        total_ticks += ticks
        if total_ticks > _LIMITS['evaluations']:
            _error('$.composites', 'evaluation ticks exceed limit')
        composites[key] = {
            'id': key, 'kind': 'all_of', 'all_of': members, 'stage_ids': list(item['stage_ids']),
            'evaluation': {'first_at_seconds': first, 'cadence_seconds': cadence,
                           'last_at_seconds': last, 'ticks': ticks},
            'persistence_consecutive': _integer(item['persistence_consecutive'],
                                                path + '.persistence_consecutive', 1,
                                                _LIMITS['persistence']),
            'persistence_reset': _choice(item['persistence_reset'], _RESET_RULES,
                                         path + '.persistence_reset',
                                         'unsupported persistence reset rule'),
            'cooldown_seconds': _number(item['cooldown_seconds'], parameters,
                                        path + '.cooldown_seconds', 0, _LIMITS['seconds_magnitude']),
            'rearm_requires_false': _boolean(item['rearm_requires_false'],
                                             path + '.rearm_requires_false'),
            'detection_delay_seconds': _number(item['detection_delay_seconds'], parameters,
                                               path + '.detection_delay_seconds', 0,
                                               _LIMITS['seconds_magnitude']),
            'explanation': _text(item['explanation'], path + '.explanation')}
    for index, assumption in enumerate(_list(package['assumptions'], '$.assumptions',
                                             _LIMITS['assumptions'])):
        _text(assumption, f'$.assumptions[{index}]')
    return {'schema_version': 'contingent-world.v1', 'id': package['id'],
            'question': package['question'], 'start_seconds': start, 'end_seconds': end,
            'actors': deepcopy(package['actors']), 'series': series,
            'lifecycle': {'initial_stage_id': initial,
                          'stages': deepcopy(lifecycle['stages']),
                          'transitions': transitions},
            'conditions': conditions, 'composites': composites,
            'timeline': timeline, 'assumptions': list(package['assumptions'])}


def _public(package):
    """Validated data that declares the run, excluding internal indexes and caches."""
    return {'schema_version': package['schema_version'], 'id': package['id'],
            'question': package['question'], 'start_seconds': package['start_seconds'],
            'end_seconds': package['end_seconds'], 'actors': package['actors'],
            'series': {key: {**{k: v for k, v in item.items() if k != 'index'},
                             'samples': item['index']['rows']}
                       for key, item in package['series'].items()},
            'lifecycle': package['lifecycle'], 'conditions': package['conditions'],
            'composites': package['composites'], 'assumptions': package['assumptions']}


def _series_report(package):
    report = {}
    for key, item in package['series'].items():
        rows = item['index']['rows']
        report[key] = {'unit': item['unit'], 'samples': len(rows),
                       'first_at_seconds': rows[0]['at_seconds'],
                       'last_at_seconds': rows[-1]['at_seconds'],
                       'late_arrival_samples': sum(1 for row in rows
                                                   if row['available_at_seconds'] > row['at_seconds']),
                       'actor_ids': list(item['actor_ids'])}
    return report


def _member_state(trails, member, at):
    """Member truth at a tick: the last reported outcome at or before it."""
    times, outcomes = trails[member]
    position = bisect_right(times, at) - 1
    if position < 0:
        return 'unknown'
    state = outcomes[position]
    if state in _TRUE_OUTCOMES:
        return 'true'
    return 'false' if state == 'false' else 'unknown'


class _Trigger:
    """Persistence, cooldown and rearm state shared by simple and composite conditions."""

    def __init__(self, condition):
        self.condition = condition
        self.held = 0
        self.last_fire = None
        self.armed = True

    def step(self, at, raw):
        """Return (reported outcome, fired, consecutive count) for one tick."""
        if raw != 'true':
            reset = self.condition['persistence_reset']
            if raw == 'false' and reset in {'on_non_true', 'on_false_only'}:
                self.held, self.armed = 0, True
            elif raw != 'false' and reset == 'on_non_true':
                self.held, self.armed = 0, True
            return raw, False, self.held
        self.held += 1
        if not self.armed:
            return 'awaiting_rearm', False, self.held
        if self.last_fire is not None and at - self.last_fire < self.condition['cooldown_seconds']:
            return 'cooldown', False, self.held
        if self.held < self.condition['persistence_consecutive']:
            return 'true_holding', False, self.held
        count = self.held
        self.last_fire, self.held = at, 0
        self.armed = not self.condition['rearm_requires_false']
        return 'fired', True, count


def evaluate_contingent_world(package):
    """Evaluate every declared tick; unknown data never becomes a silent non-event."""
    package = validate_contingent_world(package)
    visits = [0]
    firings, conditions, trails = [], {}, {}
    for key, condition in package['conditions'].items():
        plan = condition['evaluation']
        first, cadence, ticks = plan['first_at_seconds'], plan['cadence_seconds'], plan['ticks']
        index = package['series'][condition['series_id']]['index']
        stale_after = package['series'][condition['series_id']]['stale_after_seconds']
        reference, comparison = condition['reference'], condition['comparison']
        allowed = set(condition['stage_ids'])
        trigger = _Trigger(condition)
        counts = {outcome: 0 for outcome in _OUTCOMES}
        times, outcomes = [], []
        for step in range(ticks):
            at = first + step * cadence
            stage = _stage_at(package['timeline'], package['lifecycle']['initial_stage_id'], at)
            current_value = reference_value = None
            if stage not in allowed:
                raw = 'outside_stage'
            else:
                current = _visible(index, at, at, visits)
                if current is None:
                    raw = 'no_current'
                elif at - current['at_seconds'] > stale_after:
                    raw = 'stale'
                else:
                    current_value = current['value']
                    reference_value = _reference_value(index, reference, at, visits)
                    truth = _is_true(comparison, current_value, reference_value)
                    raw = 'unknown_reference' if truth is None else 'true' if truth else 'false'
            outcome, fired, held = trigger.step(at, raw)
            counts[outcome] += 1
            times.append(at)
            outcomes.append(outcome)
            if fired:
                firings.append({
                    'condition_id': key, 'kind': 'simple', 'evaluated_at_seconds': at,
                    'effective_at_seconds': at + condition['detection_delay_seconds'],
                    'stage_id': stage, 'current_value': current_value,
                    'reference_value': reference_value, 'consecutive_true': held,
                    'reference_kind': reference['kind'], 'comparison_mode': comparison['mode'],
                    'direction': comparison['direction'],
                    'threshold_bps': comparison['threshold_bps'],
                    'threshold': comparison['threshold'],
                    'detection_delay_seconds': condition['detection_delay_seconds']})
        trails[key] = (times, outcomes)
        conditions[key] = {'kind': 'simple', 'series_id': condition['series_id'],
                           'unit': package['series'][condition['series_id']]['unit'],
                           'ticks': ticks, 'outcome_counts': {k: v for k, v in sorted(counts.items()) if v},
                           'fired': sum(1 for firing in firings if firing['condition_id'] == key),
                           'reference_kind': reference['kind'],
                           'comparison': {k: v for k, v in comparison.items() if v is not None},
                           'persistence_consecutive': condition['persistence_consecutive'],
                           'persistence_reset': condition['persistence_reset'],
                           'cooldown_seconds': condition['cooldown_seconds'],
                           'rearm_requires_false': condition['rearm_requires_false'],
                           'detection_delay_seconds': condition['detection_delay_seconds']}
    for key, composite in package['composites'].items():
        plan = composite['evaluation']
        first, cadence, ticks = plan['first_at_seconds'], plan['cadence_seconds'], plan['ticks']
        allowed = set(composite['stage_ids'])
        members = composite['all_of']
        trigger = _Trigger(composite)
        counts = {outcome: 0 for outcome in _OUTCOMES}
        for step in range(ticks):
            at = first + step * cadence
            stage = _stage_at(package['timeline'], package['lifecycle']['initial_stage_id'], at)
            if stage not in allowed:
                raw = 'outside_stage'
            else:
                states = [_member_state(trails, member, at) for member in members]
                if all(state == 'true' for state in states):
                    raw = 'true'
                elif any(state == 'false' for state in states):
                    raw = 'false'
                else:
                    raw = 'unknown_member'
            outcome, fired, held = trigger.step(at, raw)
            counts[outcome] += 1
            if fired:
                firings.append({
                    'condition_id': key, 'kind': 'all_of', 'members': list(members),
                    'evaluated_at_seconds': at,
                    'effective_at_seconds': at + composite['detection_delay_seconds'],
                    'stage_id': stage, 'consecutive_true': held,
                    'detection_delay_seconds': composite['detection_delay_seconds']})
        conditions[key] = {'kind': 'all_of', 'members': list(members), 'ticks': ticks,
                           'outcome_counts': {k: v for k, v in sorted(counts.items()) if v},
                           'fired': sum(1 for firing in firings if firing['condition_id'] == key),
                           'persistence_consecutive': composite['persistence_consecutive'],
                           'persistence_reset': composite['persistence_reset'],
                           'cooldown_seconds': composite['cooldown_seconds'],
                           'rearm_requires_false': composite['rearm_requires_false'],
                           'detection_delay_seconds': composite['detection_delay_seconds']}
        if visits[0] > _LIMITS['sample_visits']:
            _error('$.conditions', 'evaluation sample visits exceed limit')
    firings.sort(key=lambda f: (f['effective_at_seconds'], f['condition_id']))
    if len(firings) > _LIMITS['firings']:
        _error('$.conditions', 'firing count exceeds limit')
    result = {'schema_version': 'contingent-evaluation.v1', 'world_id': package['id'],
              'question': package['question'], 'start_seconds': package['start_seconds'],
              'end_seconds': package['end_seconds'], 'sample_visits': visits[0],
              'lifecycle': {'initial_stage_id': package['lifecycle']['initial_stage_id'],
                            'confirmed_transitions': len(package['timeline']),
                            'unconfirmed_transitions': sum(1 for item in package['lifecycle']['transitions']
                                                           if not item['confirmed']),
                            'stage_at_seconds': [{'at_seconds': at,
                                                  'stage_id': _stage_at(package['timeline'],
                                                                        package['lifecycle']['initial_stage_id'], at)}
                                                 for at in sorted({package['start_seconds'],
                                                                   package['end_seconds'],
                                                                   *(moment for moment, _id, _t in package['timeline'])})]},
              'series': _series_report(package), 'conditions': conditions, 'firings': firings,
              'assumptions': package['assumptions'], 'model_calls': 0,
              'package_sha256': _digest(_public(package)), 'engine_sha256': _ENGINE_SHA256,
              'limitations': list(_LIMITATIONS)}
    if len(json.dumps(result, ensure_ascii=False).encode('utf-8')) > _LIMITS['output_bytes']:
        _error('$.conditions', 'evaluation output exceeds limit')
    return result


def verify_contingent_evaluation(evaluation, package):
    """Recompute from declared input and reject any mismatch with the stored result."""
    _canonical(evaluation, _LIMITS['output_bytes'])
    expected = evaluate_contingent_world(package)
    if evaluation != expected:
        _error('$', 'evaluation does not match deterministic recomputation')
    return deepcopy(expected)


def contingent_world_capabilities():
    """Publish the declared field contract without inventing executable values."""
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

    fields = {
        'package': record({
            'schema_version': {'type': 'string', 'const': 'contingent-world.v1'},
            'id': identifier(), 'question': text(), 'parameters': {'contract': 'parameters'},
            'start_seconds': {'contract': 'number', 'minimum': 0},
            'end_seconds': {'contract': 'horizon_end'},
            'actors': array('actor', _LIMITS['actors']),
            'series': array('series', _LIMITS['series'], 1),
            'lifecycle': {'contract': 'lifecycle'},
            'conditions': array('condition', _LIMITS['conditions'], 1),
            'composites': array('composite', _LIMITS['conditions']),
            'assumptions': {'type': 'array', 'minimum_items': 0,
                            'maximum_items': _LIMITS['assumptions'], 'items': text()},
        }, ['Sample, stage, transition, actor and condition IDs are unique in their own scope.',
            'Nothing is defaulted; an omitted field is a validation error, not an assumption.']),
        'parameters': {'type': 'object', 'maximum_properties': _LIMITS['parameters'],
                       'keys': identifier(),
                       'values': integer(-_LIMITS['value_magnitude'], _LIMITS['value_magnitude']),
                       'defaults': None,
                       'use': 'Any seconds, value or threshold field may be {"parameter": id} instead of a literal.'},
        'horizon_end': {**integer(1, _LIMITS['seconds_magnitude']),
                        'constraint': 'end_seconds > start_seconds; every tick and reference lies inside the horizon.'},
        'actor': record({'id': identifier(), 'label': text(256), 'role': text(256)},
                        ['Actors record who could observe a series; evaluation itself makes no decision.']),
        'series': record({
            'id': identifier(), 'unit': text(64),
            'minimum': integer(-_LIMITS['value_magnitude'], _LIMITS['value_magnitude']),
            'maximum': integer(-_LIMITS['value_magnitude'], _LIMITS['value_magnitude']),
            'stale_after_seconds': integer(1, _LIMITS['seconds_magnitude']),
            'actor_ids': {'type': 'array', 'minimum_items': 1, 'maximum_items': _LIMITS['actors'],
                          'unique': True, 'items': identifier('actor.id')},
            'samples': array('sample', _LIMITS['samples_per_series'], 1),
        }, ['minimum <= maximum and every sample value lies inside those bounds.',
            'A gap is absent samples. Missing data is never zero or carried forward.',
            'stale_after_seconds is declared tolerance: an older newest sample reports stale.']),
        'sample': record({
            'id': identifier(),
            'at_seconds': integer(0, _LIMITS['seconds_magnitude']),
            'available_at_seconds': integer(0, _LIMITS['seconds_magnitude']),
            'value': {'contract': 'number'}, 'source': text(512),
        }, ['available_at_seconds >= at_seconds: data cannot be observed before it exists.',
            'Only samples available by the tick enter a current or reference window, so late arrivals cannot leak backwards.',
            'Samples sharing an event time are ordered deterministically by arrival then identifier.']),
        'lifecycle': record({
            'initial_stage_id': identifier('stage.id'),
            'stages': array('stage', _LIMITS['stages'], 1),
            'transitions': array('transition', _LIMITS['transitions']),
        }, ['Confirmed transitions must chain from the initial stage without branching.',
            'confirmed=false records a claimed or pending change and never advances the stage.']),
        'stage': record({'id': identifier(), 'label': text(256)}),
        'transition': record({
            'id': identifier(), 'from_stage_id': identifier('stage.id'),
            'to_stage_id': identifier('stage.id'),
            'effective_at_seconds': {'contract': 'number'},
            'confirmed': {'type': 'boolean'}, 'source': text(512),
        }, ['Confirmation is a supplied declaration with a source; a price or cap level is not confirmation.']),
        'condition': record({
            'id': identifier(), 'series_id': identifier('series.id'),
            'stage_ids': {'type': 'array', 'minimum_items': 1, 'maximum_items': _LIMITS['stages'],
                          'unique': True, 'items': identifier('stage.id')},
            'evaluation': {'contract': 'evaluation'}, 'reference': {'contract': 'reference'},
            'comparison': {'contract': 'comparison'},
            'persistence_consecutive': integer(1, _LIMITS['persistence']),
            'persistence_reset': {'type': 'string', 'enum': sorted(_RESET_RULES)},
            'cooldown_seconds': integer(0, _LIMITS['seconds_magnitude']),
            'rearm_requires_false': {'type': 'boolean'},
            'detection_delay_seconds': integer(0, _LIMITS['seconds_magnitude']),
            'explanation': text(),
        }, ['A tick is true, then suppression applies in order: rearm, cooldown, persistence.',
            'cooldown_seconds counts from the firing tick and suppresses repeats without resetting persistence.',
            'rearm_requires_false demands one false evaluation before rearming after a firing.',
            'detection_delay_seconds shifts only when a firing becomes effective; it never shifts data availability.',
            'persistence_reset=never can bridge unknown or stale periods; state that explicitly in assumptions.']),
        'composite': record({
            'id': identifier(), 'all_of': {'type': 'array', 'minimum_items': 2,
                                           'maximum_items': 8, 'unique': True,
                                           'items': identifier('condition.id, simple only')},
            'stage_ids': {'type': 'array', 'minimum_items': 1, 'maximum_items': _LIMITS['stages'],
                          'unique': True, 'items': identifier('stage.id')},
            'evaluation': {'contract': 'evaluation'},
            'persistence_consecutive': integer(1, _LIMITS['persistence']),
            'persistence_reset': {'type': 'string', 'enum': sorted(_RESET_RULES)},
            'cooldown_seconds': integer(0, _LIMITS['seconds_magnitude']),
            'rearm_requires_false': {'type': 'boolean'},
            'detection_delay_seconds': integer(0, _LIMITS['seconds_magnitude']),
            'explanation': text(),
        }, ['A composite fires only when every member\'s latest evaluation at or before the tick is '
            'true; a member that is false makes it false, and a member with no evaluation yet, a gap, '
            'stale data or another unknown state makes it unknown_member rather than false.',
            'Members are simple conditions on distinct series; composites do not nest, so the graph '
            'is one level deep and cannot cycle.']),
        'evaluation': record({
            'first_at_seconds': integer(0, _LIMITS['seconds_magnitude']),
            'cadence_seconds': integer(1, _LIMITS['window_seconds']),
            'last_at_seconds': {**integer(0, _LIMITS['seconds_magnitude']), 'nullable': True,
                                'null_means': 'evaluate to end_seconds'},
        }, ['Ticks are first_at_seconds + n * cadence_seconds inside the horizon.',
            'cadence_seconds is observation frequency; reference windows are declared separately.']),
        'reference': {
            'prior_sample_window': record({
                'kind': {'type': 'string', 'const': 'prior_sample_window'},
                'window_seconds': {'contract': 'number', 'minimum': 1},
                'tolerance_seconds': {'contract': 'number', 'minimum': 0},
            }, ['Point-to-point return r(t)=P(t)/P(t-window)-1: the reference is the newest sample at or '
                'before tick - window whose data had arrived. No such sample within tolerance is unknown_reference.']),
            'rolling_peak_window': record({
                'kind': {'type': 'string', 'const': 'rolling_peak_window'},
                'window_seconds': {'contract': 'number', 'minimum': 1},
            }, ['Drawdown reference: maximum sample value with event time in (tick - window, tick].']),
            'window_aggregate': record({
                'kind': {'type': 'string', 'const': 'window_aggregate'},
                'start_seconds': {'contract': 'number', 'minimum': 0},
                'end_seconds': {'contract': 'number', 'minimum': 1},
                'aggregation': {'type': 'string', 'enum': sorted(_AGGREGATIONS)},
            }, ['Fixed reference period, e.g. a launch window: start_seconds <= event time < end_seconds.',
                'mean_floor is the integer floor of sum divided by the visible sample count.']),
            'alternatives': sorted(_REFERENCE_KINDS),
        },
        'comparison': {
            'mode_ratio_bps': record({
                'mode': {'type': 'string', 'const': 'ratio_bps'},
                'direction': {'type': 'string', 'enum': sorted(_DIRECTIONS)},
                'threshold_bps': {'contract': 'number', 'minimum': 1, 'maximum': _LIMITS['threshold_bps']},
                'threshold': integer(0, 0),
            }, ['Compares value * 10000 against threshold_bps * reference by exact integer cross-multiplication.',
                '8000 with at_or_below means at or below -20% versus the reference. A non-positive reference is unknown_reference.']),
            'mode_absolute': record({
                'mode': {'type': 'string', 'const': 'absolute'},
                'direction': {'type': 'string', 'enum': sorted(_DIRECTIONS)},
                'threshold_bps': integer(0, 0), 'threshold': {'contract': 'number'},
            }, ['Compares the current value directly against the declared threshold in the series unit.']),
            'required_null_field': 'threshold_bps and threshold are both required; the unused one is exactly 0.',
            'boundary': 'at_or_below and at_or_above both fire on equality with the threshold.',
        },
        'number': {'literal': integer(-_LIMITS['value_magnitude'], _LIMITS['value_magnitude']),
                   'parameter_reference': record({'parameter': identifier('parameters key')}),
                   'alternatives': ['literal', 'parameter_reference'],
                   'resolution': 'Use the supplied parameter integer; no inference or substitution.'},
    }
    return {
        'schema_version': 'contingent-world.v1', 'kind': 'declared_condition_evaluation',
        'model_calls': 0, 'defaults_or_estimates': None, 'condition_kinds': ['simple', 'all_of'],
        'outcomes': sorted(_OUTCOMES), 'reference_kinds': sorted(_REFERENCE_KINDS),
        'aggregations': sorted(_AGGREGATIONS), 'directions': sorted(_DIRECTIONS),
        'persistence_reset_rules': sorted(_RESET_RULES), 'fields': fields,
        'assumptions': {
            'sample_values': 'supplied_observations_only_not_verified_venue_data',
            'stage_confirmation': 'declared_confirmed_flag_with_source',
            'occurrence_odds': 'none; a firing is a declared condition outcome, not a probability',
            'financial_settlement': 'none; units are declared measurement units only',
            'unknown_values': 'Unknown is its own outcome and is never converted to false or zero.',
        },
        'result_schema': 'contingent-evaluation.v1', 'limits': dict(_LIMITS),
        'engine_sha256': _ENGINE_SHA256, 'limitations': list(_LIMITATIONS),
    }
