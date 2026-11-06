"""Private bounded inference records for timestamped financial worlds."""
from copy import deepcopy

from .agent_models import ModelFailure
from .agent_orchestration import _Artifacts, turn_messages
from .agent_worlds import canonical, digest, _int
from .jev import JevActorModel, MAX_STATE_BYTES, prepare_actor_request
from .evolving_worlds import EvolvingWorld, make_timeline, replay_evolving


def run_timeline(*, package, client, output_dir, seed=42, max_calls=12):
    engine = make_timeline(package, seed)
    _int(max_calls, 1, 128)
    required = len(engine.world['agents']) * len(engine.steps)
    if required > max_calls:
        raise ValueError('timeline call budget insufficient; zero calls')
    if not isinstance(client, JevActorModel):
        raise ValueError('timeline runner requires the bounded typed Jev adapter')
    for actor_id, observation in engine.observations().items():
        actor = observation['actor']
        peer_count = sum(peer['id'] in actor['subscriptions'] and 'publish' in peer['allowed_actions']
                         for peer in engine.world['agents'])
        peer_messages = min(64, peer_count * (len(engine.steps) - 1))
        event_bytes = sum(len(canonical(event)) + 1024 for event in engine.package['events']
                          if 'public' in event['audience'] or actor_id in event['audience'])
        memory_bound = 0
        if isinstance(engine, EvolvingWorld):
            memory_bound = (2 * len(canonical(engine.market_state(0))) + 1024) * (len(engine.steps) - 1)
        bound = len(canonical(observation)) + event_bytes + 4096 * peer_messages + 8192 * (len(engine.steps) - 1) + memory_bound + 4096
        if bound > MAX_STATE_BYTES:
            raise ValueError('conservative typed timeline observation budget exceeded')
    store = _Artifacts(output_dir)
    manifest = {'schema_version': 'timeline-run.v1', 'status': 'running', 'required_calls': required,
                'max_calls': max_calls, 'attempted_calls': 0, 'completed_calls': 0,
                'completed_barriers': 0, 'cost_usd': None, 'retry_policy': 'none', 'error': None}
    store.new('package.json', engine.package)
    store.new('manifest.json', manifest)
    store.new('result.json', engine.timeline_report())
    try:
        while engine.round <= len(engine.steps):
            observations = engine.observations()
            for observation in observations.values():
                prepare_actor_request(observation, min_confidence=client.min_confidence)
            barrier = f'barrier-{engine.round:03d}'
            store.new(barrier + '.observations.json', observations)
            turns = []
            for actor_id, observation in observations.items():
                if manifest['attempted_calls'] >= max_calls:
                    raise ValueError('timeline budget exhausted')
                prefix = f'call-{manifest["attempted_calls"] + 1:03d}'
                messages = turn_messages(observation)
                store.new(prefix + '.request.json', {'actor_id': actor_id, 'messages': messages})
                manifest['attempted_calls'] += 1
                store.new(prefix + '.dispatch.json', {'status': 'dispatching', 'request_sha256': digest(messages)})
                store.replace('manifest.json', manifest)
                response = client.generate(messages)
                store.new(prefix + '.response.json', response)
                manifest['completed_calls'] += 1
                store.replace('manifest.json', manifest)
                turns.append(response['value'])
            engine.advance(turns)
            if isinstance(engine, EvolvingWorld):
                store.new(barrier + '.checkpoint.json', engine.checkpoints[-1])
            manifest['completed_barriers'] += 1
            store.replace('result.json', engine.timeline_report())
            store.replace('manifest.json', manifest)
        replay_evolving(engine.timeline_report())
        manifest['status'] = 'completed'
    except Exception as error:
        manifest['status'] = 'failed'
        manifest['error'] = {'code': error.code if isinstance(error, ModelFailure) else 'validation_or_artifact_failure',
                             'remote_outcome': error.remote_outcome if isinstance(error, ModelFailure) else 'unknown'}
        if callable(getattr(error, 'safe_details', None)):
            manifest['error']['details'] = error.safe_details()
        store.replace('result.json', engine.timeline_report())
    store.replace('manifest.json', manifest)
    return deepcopy(manifest)
