"""Recover confirmed receipts without redispatching unknown requests or resetting the cap."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal, ROUND_CEILING
import json
from pathlib import Path

from decision_lab.agent_orchestration import _Artifacts
from decision_lab.agent_worlds import digest, canonical
from decision_lab.env_config import load_env_key
from decision_lab.io_helpers import read_json
from decision_lab.jev import TypeSafeClient
from decision_lab.launch_lifecycle import LaunchLifecycle
from decision_lab.lifecycle_runs import SpendGuard, replay_lifecycle, step_choices


ROOT = Path(__file__).resolve().parents[1]


class ExistingArtifacts(_Artifacts):
    def __init__(self, directory):
        self.root = Path(directory)
        if not self.root.is_dir() or self.root.is_symlink():
            raise ValueError('existing non-symlink artifact directory required')


def restore_receipts(root, seed):
    guard = SpendGuard('2.00')
    caches, blocked, identifiers = {}, set(), set()
    unknown = 0
    for dispatch_path in sorted(Path(root).glob('*/*/call-*.dispatch.json')):
        identifier = int(dispatch_path.name.split('.')[0].split('-')[1])
        if identifier in identifiers:
            raise ValueError('duplicate global dispatch identifier')
        identifiers.add(identifier)
        dispatch = read_json(dispatch_path)
        response_path = dispatch_path.with_name(dispatch_path.name.replace('.dispatch.', '.response.'))
        if not response_path.exists():
            guard.reserved_micro_usd += dispatch['reservation_micro_usd']
            blocked.add(dispatch_path.parent)
            unknown += 1
            continue
        response = read_json(response_path)
        tokens = response['receipt'].get('usage', {}).get('input_tokens')
        if type(tokens) is int and tokens >= 0:
            guard.spent_micro_usd += int((Decimal(tokens) * guard.price).to_integral_value(rounding=ROUND_CEILING))
            guard.completed_calls += 1
        else:
            guard.reserved_micro_usd += dispatch['reservation_micro_usd']
        request = read_json(dispatch_path.with_name(dispatch_path.name.replace('.dispatch.', '.request.')))
        cache_key = digest({'request': request, 'observation': dispatch['observation_sha256'], 'seed': seed})
        caches.setdefault(dispatch_path.parent.parent.name, {})[cache_key] = {
            'answers': response['answers'], 'receipt': response['receipt'],
            'request_sha256': digest(request), 'observation_sha256': dispatch['observation_sha256'],
            'call_prefix': dispatch_path.name.split('.')[0], 'new_model_calls': 0}
    guard.attempted_calls = max(identifiers, default=0)
    if guard.spent_micro_usd + guard.reserved_micro_usd > guard.cap_micro_usd:
        raise ValueError('recovered receipts exceed authorized budget')
    return guard, caches, blocked, {'confirmed_responses': len(identifiers) - unknown,
                                  'unknown_dispatches': unknown, 'budget': guard.snapshot()}


def recovered_engine(directory):
    replay_lifecycle(directory)
    manifest = read_json(directory / 'manifest.json')
    engine = LaunchLifecycle(read_json(directory / 'package.json'), manifest['seed'], manifest['response_policy'])
    checkpoints = sorted(directory.glob('step-*.json'))
    for index, path in enumerate(checkpoints):
        if path.name != f'step-{index:05d}.json':
            raise ValueError('non-contiguous recovered barriers')
        saved = read_json(path)
        engine.prepare()
        if canonical(engine.advance(saved['checkpoint']['choices'])) != canonical(saved['checkpoint']):
            raise ValueError('recovered checkpoint mismatch')
    manifest['completed_steps'] = len(checkpoints)
    manifest['model_calls'] = sum(sum(value.get('new_model_calls', 0) for value in read_json(path)['decision_evidence'].values())
                                  for path in checkpoints)
    manifest['summary'] = engine.summary()
    return engine, manifest


def resume(root, workers=4):
    root = Path(root)
    matrix = read_json(root / 'matrix.json')
    if matrix['mode'] != 'jev' or matrix['status'] != 'running':
        raise ValueError('only an interrupted running native matrix can be recovered')
    if not 1 <= workers <= 12:
        raise ValueError('one to twelve independent case workers required')
    manifests = [read_json(path) for path in root.glob('*/*/manifest.json')]
    seeds = {item['seed'] for item in manifests}
    if len(manifests) != 24 or len(seeds) != 1:
        raise ValueError('expected twenty-four paths with a common seed')
    guard, caches, blocked, recovery = restore_receipts(root, seeds.pop())
    store = ExistingArtifacts(root)
    store.new('recovery.json', recovery)
    key = load_env_key(ROOT / '.env', name='TYPESAFE_API_KEY')
    groups = []
    for case in sorted({path.parent for path in root.glob('*/*/manifest.json')}):
        engine, manifest = recovered_engine(case)
        group = next((item for item in groups if item['case'] == case.parent.name), None)
        if group is None:
            group = {'case': case.parent.name, 'cache': caches.get(case.parent.name, {}), 'runs': [],
                     'client': TypeSafeClient(api_key=key, model='jev-1.14.0', http_client='curl', timeout_seconds=60)}
            groups.append(group)
        if case in blocked:
            manifest['status'] = 'interrupted_unknown_dispatch'
            manifest['error'] = {'code': 'unknown_request_outcome', 'message': 'No retry; retained reservation and last complete state.'}
        elif engine.index == len(engine.schedule):
            manifest['status'] = 'completed'
        else:
            manifest['status'] = 'running'
            manifest['error'] = None
        run_store = ExistingArtifacts(case)
        run_store.replace('manifest.json', manifest)
        group['runs'].append({'store': run_store, 'engine': engine, 'manifest': manifest})

    def snapshot():
        matrix['budget'] = guard.snapshot()
        matrix['paths'] = [{'case': group['case'], 'policy': run['manifest']['response_policy'],
                            'status': run['manifest']['status'], 'completed_steps': run['manifest']['completed_steps'],
                            'summary': run['manifest']['summary']} for group in groups for run in group['runs']]
        matrix['completed_steps'] = sum(item['completed_steps'] for item in matrix['paths'])
        matrix['completed_paths'] = sum(item['status'] == 'completed' for item in matrix['paths'])
        matrix['recovery'] = recovery
        store.replace('matrix.json', matrix)

    def advance(group):
        for run in group['runs']:
            engine, manifest, run_store = run['engine'], run['manifest'], run['store']
            if manifest['status'] != 'running':
                continue
            try:
                engine.prepare()
                choices, evidence = step_choices(engine, client=group['client'], store=run_store, guard=guard,
                                                  mode='jev', cache=group['cache'])
                checkpoint = engine.advance(choices)
                run_store.new(f'step-{checkpoint["step"]:05d}.json', {'checkpoint': checkpoint, 'decision_evidence': evidence})
                manifest['completed_steps'] += 1
                manifest['model_calls'] += sum(value.get('new_model_calls', 0) for value in evidence.values())
                manifest['summary'] = engine.summary()
                if engine.index == len(engine.schedule):
                    manifest['status'] = 'completed'
            except Exception as error:
                manifest['status'] = 'budget_exhausted' if isinstance(error, ValueError) and 'budget' in str(error) else 'failed'
                manifest['error'] = {'code': getattr(error, 'code', 'stopped_before_next_complete_barrier'),
                                     'message': 'No automatic retry or fabricated continuation; inspect private receipts.'}
            run_store.replace('manifest.json', manifest)

    snapshot()
    with ThreadPoolExecutor(max_workers=workers) as executor:
        cycle = 0
        while any(run['manifest']['status'] == 'running' for group in groups for run in group['runs']):
            active = [group for group in groups if any(run['manifest']['status'] == 'running' for run in group['runs'])]
            list(executor.map(advance, active))
            cycle += 1
            snapshot()
            if cycle % 6 == 0:
                print(json.dumps({'recovery_cycle': cycle, 'steps': matrix['completed_steps'], 'budget': guard.snapshot()}), flush=True)
            if any(run['manifest']['status'] == 'failed' for group in groups for run in group['runs']):
                for group in groups:
                    for run in group['runs']:
                        if run['manifest']['status'] == 'running':
                            run['manifest']['status'] = 'stopped_after_peer_failure'
                            run['store'].replace('manifest.json', run['manifest'])
                break
    statuses = {run['manifest']['status'] for group in groups for run in group['runs']}
    matrix['status'] = 'partial_budget_limited' if 'budget_exhausted' in statuses else 'completed' if statuses == {'completed'} else 'partial_interrupted'
    snapshot()
    return matrix


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True)
    parser.add_argument('--workers', type=int, default=4)
    arguments = parser.parse_args()
    result = resume(arguments.root, arguments.workers)
    print(json.dumps({'status': result['status'], 'budget': result['budget']}, indent=2))
