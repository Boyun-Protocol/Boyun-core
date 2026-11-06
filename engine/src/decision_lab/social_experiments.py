"""Controlled peer-information treatments over fresh, bounded live role worlds.

Only specified incoming subscriptions change. This measures a conditional model
experiment, not social prediction, causal human behavior or calibrated event odds.
"""
from copy import deepcopy
from fractions import Fraction
import json
import os
from pathlib import Path
import stat
from uuid import uuid4

from .agent_orchestration import run_live, _live_prompt_preflight
from .agent_worlds import (validate_agent_world, replay_agent_world, digest, canonical,
                           _shape, _id, _int, _list, MAX_REPORT_BYTES)
from .io_helpers import (reserve_outputs, json_bytes, ensure_directory, sync_directory,
                         _unique_object, _finite_float)

MAX_EXPERIMENT_CALLS = 256
_LIMITATIONS = [
    'A treatment removes specified peer information links; all declared resources, events, descriptions and rounds stay fixed.',
    'Every arm requests fresh model decisions. Equal engine seeds do not make provider inference deterministic or pair model randomness.',
    'Differences are conditional model-run outcomes, not identified human causal effects, significance estimates or real-world probabilities.',
    'Replay verifies recorded observations and arithmetic, not provider identity, factual message accuracy or population realism.',
    'Failed, missing and incomplete arms remain explicit and never enter completed-pair aggregates.',
    'Cash is a synthetic ledger balance. Locked liquidity and unsold tokens are not withdrawn profit.',
]


def prepare_social_experiment(protocol):
    if len(canonical(protocol)) > 262144:
        raise ValueError('social protocol exceeds size budget')
    _shape(protocol, {'schema_version', 'id', 'baseline_world', 'treatment', 'seeds'})
    if protocol['schema_version'] != 'social-experiment.v1':
        raise ValueError('unsupported social experiment')
    _id(protocol['id'])
    baseline = validate_agent_world(protocol['baseline_world'])
    if baseline['rounds'] < 2:
        raise ValueError('peer publication needs at least two rounds')
    seeds = _list(protocol['seeds'], 4, 1)
    for seed in seeds:
        _int(seed, 0, 10**9)
    if len(set(seeds)) != len(seeds):
        raise ValueError('duplicate experiment seeds')
    _shape(protocol['treatment'], {'remove_subscriptions'})
    edges = _list(protocol['treatment']['remove_subscriptions'], 64, 1)
    actors = {a['id']: a for a in baseline['agents']}
    seen = set()
    treatment = deepcopy(baseline)
    changed = {a['id']: a for a in treatment['agents']}
    for edge in edges:
        _shape(edge, {'listener', 'source'})
        listener, source = edge['listener'], edge['source']
        if (type(listener) is not str or type(source) is not str or listener not in actors
                or source not in actors or listener == source or (listener, source) in seen
                or source not in actors[listener]['subscriptions']):
            raise ValueError('treatment must remove unique existing directed peer links')
        if 'publish' not in actors[source]['allowed_actions'] or actors[listener]['attention_capacity'] == 0:
            raise ValueError('removed edge cannot carry an observed peer publication')
        seen.add((listener, source))
        changed[listener]['subscriptions'].remove(source)
    treatment = validate_agent_world(treatment)
    _live_prompt_preflight(baseline)
    _live_prompt_preflight(treatment)
    calls = len(seeds) * 2 * len(baseline['agents']) * baseline['rounds']
    if calls > MAX_EXPERIMENT_CALLS:
        raise ValueError('experiment call matrix exceeds budget')
    return {'schema_version': 'social-experiment-plan.v1', 'protocol': deepcopy(protocol),
            'protocol_sha256': digest(protocol), 'baseline_world': baseline,
            'treatment_world': treatment, 'required_calls': calls,
            'limits': {'maximum_calls': MAX_EXPERIMENT_CALLS, 'maximum_seeds': 4,
                       'maximum_report_bytes_per_arm': MAX_REPORT_BYTES},
            'limitations': list(_LIMITATIONS)}


def _metrics(report):
    delivered = 0
    for phase in report['history']:
        for observation in phase['observations'].values():
            new = set(observation['new_message_ids'])
            delivered += sum(m['id'] in new and m['source'] != 'news' for m in observation['messages'])
    actions = {kind: sum(t['kind'] == kind for t in report['settlements']) for kind in ('hold', 'buy', 'sell')}
    executed = {kind: sum(t['kind'] == kind and t['status'] == 'executed' for t in report['settlements'])
                for kind in ('buy', 'sell')}
    return {'peer_new_deliveries': delivered, 'published_messages': len(report['messages']),
            'action_counts': actions, 'executed_action_counts': executed,
            'executed_buy_cash_cents': sum(t['fill']['cash_cents'] for t in report['settlements']
                                           if t['kind'] == 'buy' and t['status'] == 'executed'),
            'actor_ending_cash_cents': {actor['id']: report['balances'][actor['id']]['cash_cents'] for actor in report['world']['agents']},
            'project_ending_cash_cents': report['balances']['project']['cash_cents']}


def _difference(after, before):
    return {key: _difference(after[key], value) if type(value) is dict else after[key] - value
            for key, value in before.items()}


def _aggregate(values):
    if not values:
        return None
    if type(values[0]) is dict:
        return {key: _aggregate([value[key] for value in values]) for key in values[0]}
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    median = Fraction(ordered[midpoint]) if len(ordered) % 2 else Fraction(ordered[midpoint-1] + ordered[midpoint], 2)
    mean = Fraction(sum(values), len(values))
    def exact(value):
        return value.numerator if value.denominator == 1 else {'numerator': value.numerator, 'denominator': value.denominator}
    return {'count': len(values), 'sum': sum(values), 'minimum': min(values), 'maximum': max(values),
            'mean': exact(mean), 'median': exact(median)}


def analyze_social_experiment(protocol, pairs):
    plan = prepare_social_experiment(protocol)
    _list(pairs, len(protocol['seeds']))
    complete, excluded, seen = [], [], set()
    for pair in pairs:
        _shape(pair, {'seed', 'baseline', 'treatment'})
        seed = pair['seed']
        if type(seed) is not int or seed not in protocol['seeds'] or seed in seen:
            raise ValueError('invalid or duplicate paired seed')
        seen.add(seed)
        metrics = {}
        reasons = []
        for arm in ('baseline', 'treatment'):
            report = pair[arm]
            if report is None:
                reasons.append(arm + ':missing_or_failed')
                continue
            if (type(report) is not dict or report.get('seed') != seed
                    or report.get('world') != plan[arm + '_world']):
                raise ValueError('report is not matched to declared arm and seed')
            replay_agent_world(report)
            if report['status'] != 'completed':
                reasons.append(arm + ':incomplete')
            else:
                metrics[arm] = _metrics(report)
        if reasons:
            excluded.append({'seed': seed, 'reasons': reasons})
        else:
            complete.append({'seed': seed, **metrics, 'delta': _difference(metrics['treatment'], metrics['baseline'])})
    for seed in protocol['seeds']:
        if seed not in seen:
            excluded.append({'seed': seed, 'reasons': ['pair:not_supplied']})
    return {'schema_version': 'social-experiment-analysis.v1', 'protocol_sha256': plan['protocol_sha256'],
            'planned_pairs': len(protocol['seeds']), 'completed_pairs': len(complete),
            'excluded_pairs': len(excluded), 'pairs': complete, 'exclusions': excluded,
            'delta_definition': 'treatment_minus_baseline',
            'aggregate': _aggregate([pair['delta'] for pair in complete]),
            'limitations': list(_LIMITATIONS)}


def _write(root, name, value, *, replace=False):
    destination = root / name
    temporary = root / (name + '.' + uuid4().hex + '.tmp') if replace else destination
    with reserve_outputs([temporary]) as reservation:
        reservation.write(temporary, json_bytes(value))
        if replace:
            os.replace(temporary, destination)
        sync_directory(root)


def _read(path):
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | getattr(os, 'O_NOFOLLOW', 0))
    with os.fdopen(fd, 'rb') as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise ValueError('regular experiment artifact required')
        raw = handle.read(MAX_REPORT_BYTES + 1)
    if len(raw) > MAX_REPORT_BYTES:
        raise ValueError('experiment artifact exceeds budget')
    return json.loads(raw, object_pairs_hook=_unique_object, parse_float=_finite_float,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def run_social_experiment(*, protocol, client, output_dir, max_calls):
    plan = prepare_social_experiment(protocol)
    # Freeze the reviewed matrix independently of caller-owned mutable objects.
    protocol = plan['protocol']
    _int(max_calls, 1, MAX_EXPERIMENT_CALLS)
    if max_calls < plan['required_calls']:
        raise ValueError('full experiment call budget required before dispatch')
    root = Path(output_dir)
    ensure_directory(root.parent)
    root.mkdir(mode=0o700)
    sync_directory(root.parent)
    _write(root, 'protocol.json', protocol)
    _write(root, 'plan.json', plan)
    manifest = {'schema_version': 'social-experiment-run.v1', 'status': 'running',
                'protocol_sha256': plan['protocol_sha256'], 'required_calls': plan['required_calls'],
                'max_calls': max_calls, 'attempted_calls': 0, 'completed_calls': 0,
                'completed_pairs': 0, 'failed_arms': 0, 'arms': [], 'error': None,
                'cost_usd': None, 'limitations': list(_LIMITATIONS)}
    _write(root, 'manifest.json', manifest)
    pairs = []
    arm_calls = len(plan['baseline_world']['agents']) * plan['baseline_world']['rounds']
    try:
        for seed in protocol['seeds']:
            pair = {'seed': seed, 'baseline': None, 'treatment': None}
            seed_dir = root / f'seed-{seed}'
            seed_dir.mkdir(mode=0o700)
            sync_directory(root)
            for arm in ('baseline', 'treatment'):
                entry = {'seed': seed, 'arm': arm, 'status': 'dispatching', 'required_calls': arm_calls,
                         'path': f'seed-{seed}/{arm}'}
                manifest['arms'].append(entry)
                _write(root, 'manifest.json', manifest, replace=True)
                receipt = run_live(world=plan[arm + '_world'], seed=seed, client=client,
                                   output_dir=seed_dir / arm, max_calls=arm_calls)
                entry.update(status=receipt['status'], attempted_calls=receipt['attempted_calls'],
                             completed_calls=receipt['completed_calls'], completed_rounds=receipt['completed_rounds'])
                manifest['attempted_calls'] += receipt['attempted_calls']
                manifest['completed_calls'] += receipt['completed_calls']
                if receipt['status'] != 'completed':
                    manifest['failed_arms'] += 1
                # Retain replayable partial trajectories in analysis exclusions.
                pair[arm] = _read(seed_dir / arm / 'result.json')
                _write(root, 'manifest.json', manifest, replace=True)
            pairs.append(pair)
            analysis = analyze_social_experiment(protocol, pairs)
            manifest['completed_pairs'] = analysis['completed_pairs']
            _write(root, 'analysis.json', analysis, replace=(root / 'analysis.json').exists())
        manifest['status'] = 'completed' if manifest['completed_pairs'] == len(protocol['seeds']) else 'partial'
    except Exception:
        manifest['status'] = 'failed'
        manifest['error'] = {'code': 'experiment_or_artifact_failure', 'remote_outcome': 'inspect_arm_receipts'}
    _write(root, 'manifest.json', manifest, replace=True)
    return deepcopy(manifest)
