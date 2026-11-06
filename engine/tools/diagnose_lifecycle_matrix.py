"""Diagnose a lifecycle matrix from saved checkpoints: completeness, configuration warnings,
founder money attribution, paired policy effects and actor-score decisiveness.

Replays recorded choices only; makes no model calls. Writes diagnostics.json.
"""
import argparse
from collections import defaultdict
import json
import math
from pathlib import Path

from decision_lab.agent_worlds import canonical
from decision_lab.launch_lifecycle import LaunchLifecycle
from decision_lab.launch_decision_policy import HORIZON, HOUR

POLICIES = ('pause-and-observe', 'staged-exit')
RULE_REASONS = {'committed_launch_50_percent': 'Launch buy (fixed rule)',
                'confirmed_migration_20_percent': 'Post-migration top-up (fixed rule)',
                'staged_exit_tranche': 'Staged-exit sales (fixed rule)'}


def read(path):
    return json.loads(path.read_text())


def entropy(probabilities):
    values = [v for v in probabilities.values() if v > 0]
    if len(probabilities) < 2:
        return None
    return -sum(v * math.log(v) for v in values) / math.log(len(probabilities))


def marked(engine, capital):
    s = engine.summary()
    cash = s['founder_controlled_cash_cents'] - capital
    return {'cash': cash / 100, 'quote': s['estimated_inventory_exit_cents'] / 100,
            'marked': (cash + s['estimated_inventory_exit_cents']) / 100}


def alert_cause(checkpoint):
    signal = checkpoint['preparation_market_before']['six_hour_signal']
    if signal.get('exit_trigger') is True:
        return 'volume fell to 25% of its peak or less'
    return 'loss budget breached'


def replay_path(directory):
    manifest, package = read(directory/'manifest.json'), read(directory/'package.json')
    capital = package['founder']['capital_cents']
    engine = LaunchLifecycle(package, manifest['seed'], manifest['response_policy'])
    series, flows, scores = [], defaultdict(float), defaultdict(list)
    alert = None
    for index in range(manifest['completed_steps']):
        saved = read(directory/f'step-{index:05d}.json')
        engine.prepare()
        checkpoint = engine.advance(saved['checkpoint']['choices'])
        if canonical(checkpoint) != canonical(saved['checkpoint']):
            raise ValueError(f'{directory}: replay mismatch at step {index}')
        for receipt in checkpoint['settlements']:
            if receipt.get('actor') == engine.founder and receipt.get('status') == 'executed':
                label = RULE_REASONS.get(receipt['reason'], 'Founder model-chosen trades')
                sign = -1 if receipt['side'] == 'buy' else 1
                flows[label] += sign * receipt['cash_cents'] / 100
        if alert is None and checkpoint['response'] is not None:
            alert = {'hour': checkpoint['response']['alert_second'] / HOUR, 'cause': alert_cause(checkpoint)}
        for actor, evidence in saved['decision_evidence'].items():
            if 'answers' in evidence:
                role = checkpoint['observations'][actor]['actor']['role']
                value = entropy(evidence['answers']['action']['probabilities'])
                if value is not None:
                    scores[role].append(value)
        if checkpoint['second'] % HOUR == 0:
            series.append({'hour': checkpoint['second'] // HOUR, **marked(engine, capital)})
    end = marked(engine, capital)
    summary = engine.summary()
    return {'status': manifest['status'], 'steps': manifest['completed_steps'],
            'last_hour': (summary['last_second'] or 0) / HOUR, 'capital': capital / 100,
            'upfront': package['founder']['upfront_cents'] / 100,
            'loss_budget': package['founder']['loss_budget_cents'] / 100,
            'migrated_hour': summary['migrated_at'] / HOUR if summary['migrated_at'] is not None else None,
            'alert': alert, 'flows': dict(flows), 'end': end, 'series': series,
            'scores': {role: values for role, values in scores.items()}}


def laya_scores(run_dirs):
    scores = defaultdict(list)
    for run in run_dirs:
        for decision in run.glob('*/decision-*.json'):
            record = read(decision)
            value = entropy(record['answers']['action']['probabilities'])
            if value is not None:
                scores[record['request']['state']['actor']['role']].append(value)
    return scores


def warnings(world):
    found = []
    for policy, path in world['paths'].items():
        if path['last_hour'] < HORIZON / HOUR:
            found.append({'level': 'serious', 'policy': policy,
                          'text': f"Stopped at hour {path['last_hour']:g} of 336 ({path['status'].replace('_', ' ')})."})
    pause = world['paths'].get('pause-and-observe')
    if pause and pause['alert'] and pause['alert']['hour'] == 0:
        found.append({'level': 'critical', 'policy': 'both',
                      'text': (f"Exit alert fired at hour 0: the ${pause['upfront']:,.0f} upfront cost uses the "
                               f"${pause['loss_budget']:,.0f} loss budget before any trading. Policies are compared "
                               'under an immediate alarm, not a market signal.')})
    if pause and 'Post-migration top-up (fixed rule)' in pause['flows']:
        found.append({'level': 'warning', 'policy': 'both',
                      'text': ('The fixed post-migration top-up executed because migration came before the alert. '
                               'Worlds where the alert came first skip it, which changes founder cash.')})
    return found


def paired_effect(world):
    pause, staged = (world['paths'].get(p) for p in POLICIES)
    if not pause or not staged:
        return None
    common = {row['hour']: row for row in pause['series']}
    shared = [row for row in staged['series'] if row['hour'] in common]
    if not shared:
        return None
    last = shared[-1]
    base = common[last['hour']]
    return {'hour': last['hour'], 'diverged_hour': pause['alert']['hour'] if pause['alert'] else None,
            'pause_marked': base['marked'], 'staged_marked': last['marked'],
            'difference': last['marked'] - base['marked']}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--matrix', type=Path, required=True)
    parser.add_argument('--laya-run', type=Path, action='append', default=[])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    worlds = []
    for world_dir in sorted(p for p in args.matrix.iterdir() if p.is_dir()):
        package = read(next(world_dir.glob('*/package.json')))
        world = {'name': world_dir.name.removeprefix('macron-'), 'regime': package['regime'],
                 'position': package['founder']['position_cents'] / 100,
                 'upfront': package['founder']['upfront_cents'] / 100, 'paths': {}}
        for policy in POLICIES:
            if (world_dir/policy/'manifest.json').is_file():
                world['paths'][policy] = replay_path(world_dir/policy)
                print(world['name'], policy, 'replayed', flush=True)
        world['warnings'] = warnings(world)
        world['paired'] = paired_effect(world)
        worlds.append(world)
    jev = defaultdict(list)
    for world in worlds:
        for path in world['paths'].values():
            for role, values in path.pop('scores').items():
                jev[role].extend(values)
    laya = laya_scores(args.laya_run)
    decisiveness = [{'role': role, 'jev': sum(jev[role]) / len(jev[role]), 'jev_n': len(jev[role]),
                     'laya': sum(laya[role]) / len(laya[role]) if laya.get(role) else None,
                     'laya_n': len(laya.get(role, []))} for role in sorted(jev)]
    args.output.mkdir(parents=True, exist_ok=True)
    result = {'schema_version': 'lifecycle-diagnostics.v1', 'matrix': str(args.matrix),
              'laya_runs': [str(p) for p in args.laya_run], 'worlds': worlds, 'decisiveness': decisiveness,
              'limitations': ('Replays saved choices only; one seed per path. Unsold inventory quotes are model '
                              'sale prices at the saved pool state, not executed sales. Entropy is 1.0 for a '
                              'uniform score split.')}
    (args.output/'diagnostics.json').write_text(json.dumps(result, indent=1))
    print('wrote', args.output/'diagnostics.json')


if __name__ == '__main__':
    main()
