"""Resume a recorded Jev lifecycle with local Laya, or run the same world with Laya from hour 0.

Resumed runs replay every archived checkpoint first; --from-start reuses only the
archived package, seed, response policy and evidence audit.
"""
import argparse
import json
import os
from pathlib import Path

from decision_lab.agent_worlds import canonical, digest
from decision_lab.launch_lifecycle import LaunchLifecycle, LIFECYCLE_HASH
from decision_lab.lifecycle_runs import RUNNER_HASH, lifecycle_request, sampled_choice, review_lifecycle
from decision_lab.laya_choices import LayaChoiceClient

MODEL = 'convaiinnovations/laya-typed-decisions'
REVISION = '1a793eb568e6718f15941d08f85432581df534e3'


def read(path):
    return json.loads(path.read_text())


def save(path, data):
    temporary = path.with_suffix(path.suffix + '.tmp')
    with temporary.open('w') as stream:
        json.dump(data, stream, indent=2, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def replay_step(engine, step):
    engine.prepare()
    actual = engine.advance(step['checkpoint']['choices'])
    if canonical(actual) != canonical(step['checkpoint']):
        raise ValueError('checkpoint mismatch at step %s' % actual['step'])


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--source', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--max-steps', type=int, help='Stop after this many newly completed barriers; omit for full continuation')
    p.add_argument('--from-start', action='store_true', help='Ignore archived Jev decisions; Laya chooses from step 0')
    args = p.parse_args()
    if args.max_steps is not None and args.max_steps < 1:
        p.error('--max-steps must be positive')
    source = args.source.resolve()
    old = read(source/'manifest.json')
    package = read(source/'package.json')
    if old['engine_sha256'] != LIFECYCLE_HASH or old['runner_sha256'] != RUNNER_HASH or old['mode'] != 'jev':
        raise ValueError('Archived engine or runner does not match; do not continue')
    audit = review_lifecycle(package, read(source/'evidence-register.json'))
    if audit != old['evidence_audit']:
        raise ValueError('Archived evidence audit mismatch')
    engine = LaunchLifecycle(package, old['seed'], old['response_policy'])
    source_steps = 0 if args.from_start else old['completed_steps']
    for i in range(source_steps):
        replay_step(engine, read(source/f'step-{i:05d}.json'))
    if not args.from_start and engine.summary() != old['summary']:
        raise ValueError('Archived summary mismatch')
    args.output.mkdir(mode=0o700, parents=True, exist_ok=True)
    manifest_path = args.output/'manifest.json'
    identity = {'source':str(source), 'source_final_hash':old['summary']['final_hash'],
                'source_steps':source_steps, 'engine_sha256':LIFECYCLE_HASH,
                'runner_sha256':RUNNER_HASH, 'model':MODEL, 'revision':REVISION}
    if manifest_path.exists():
        manifest = read(manifest_path)
        if manifest['identity'] != identity:
            raise ValueError('Output belongs to a different source or checkpoint')
        for i in range(manifest['new_steps']):
            replay_step(engine, read(args.output/f'step-{source_steps+i:05d}.json'))
        if engine.summary() != manifest['summary']:
            raise ValueError('Continuation summary mismatch')
    else:
        if any(args.output.iterdir()):
            raise ValueError('Output must be empty for a new continuation')
        manifest = {'schema_version':'laya-lifecycle-continuation.v1', 'identity':identity,
                    'status':'preparing', 'new_steps':0, 'model_calls':0, 'summary':engine.summary(),
                    'limitations':('Conditional Laya-only path from hour 0; Jev decisions are not used. ' if args.from_start else
                                   'Conditional mixed-model path: Jev history then local Laya. ')
                                  + 'Scores are not calibrated market odds.'}
        save(manifest_path, manifest)
    client = LayaChoiceClient(MODEL)
    initial_steps = manifest['new_steps']
    manifest['status'] = 'running'
    save(manifest_path, manifest)
    try:
        while engine.index < len(engine.schedule) and (args.max_steps is None or manifest['new_steps']-initial_steps < args.max_steps):
            engine.prepare()
            choices, evidence = {}, {}
            for actor in engine.actors:
                request = lifecycle_request(engine, actor, 'jev-1.14.0')
                if request is None:
                    choices[actor] = 'wait'
                    evidence[actor] = {'policy':'forced_wait_only_feasible_action'}
                    continue
                request['model'] = MODEL
                record_path = args.output / f'decision-{engine.index:05d}-{actor}.json'
                if record_path.exists():
                    record = read(record_path)
                    if record['request_sha256'] != digest(request) or record['observation_sha256'] != digest(engine.observation(actor)):
                        raise ValueError('Saved partial decision differs from current state')
                else:
                    response = client.evaluate(state=request['state'], questions=request['questions'])
                    record = {'request':request, 'request_sha256':digest(request),
                              'observation_sha256':digest(engine.observation(actor)), **response}
                    save(record_path, record)
                choices[actor], sampling = sampled_choice(record['answers']['action'], engine, actor)
                evidence[actor] = {'decision_file':record_path.name, 'sampling':sampling}
            checkpoint = engine.advance(choices)
            save(args.output / f'step-{checkpoint["step"]:05d}.json', {'checkpoint':checkpoint, 'decision_evidence':evidence})
            manifest['new_steps'] += 1
            manifest['model_calls'] += sum('decision_file' in x for x in evidence.values())
            manifest['summary'] = engine.summary()
            save(manifest_path, manifest)
            print('step', checkpoint['step'], 'hour', checkpoint['second']/3600, 'calls', manifest['model_calls'], flush=True)
        manifest['status'] = 'completed' if engine.index == len(engine.schedule) else 'paused_after_requested_steps'
    except Exception as error:
        manifest['status'] = 'failed'
        manifest['error'] = {'type':type(error).__name__, 'message':str(error), 'cause':str(error.__cause__ or '')}
        raise
    finally:
        save(manifest_path, manifest)
    print(json.dumps({'status':manifest['status'], 'new_steps':manifest['new_steps'], 'summary':manifest['summary']}), flush=True)

if __name__ == '__main__': main()
