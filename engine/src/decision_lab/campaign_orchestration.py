"""Streamed campaign-world experiments with explicit budgets and replayable steps."""
from copy import deepcopy
from pathlib import Path

from .agent_models import ModelFailure
from .agent_orchestration import _Artifacts
from .agent_worlds import canonical, digest
from .campaign_worlds import CampaignWorld, ENGINE_HASH, campaign_plan, campaign_request, decide_campaign
from .io_helpers import read_json


def _campaign_engine(package, seed, commitments=None):
    if commitments is None:
        return CampaignWorld(package, seed)
    from .committed_campaigns import CommittedCampaignWorld
    return CommittedCampaignWorld(package, seed, commitments)


def _prepare(engine):
    if callable(getattr(engine, 'prepare_step', None)):
        engine.prepare_step()


def run_campaign_experiment(*, package, client, output_dir, worlds, max_calls, seed=7, stress=None, commitments=None, sample_actions=True, evidence_register=None):
    from .jev import TypeSafeClient
    if not isinstance(client, TypeSafeClient):
        raise ValueError('native typed TypeSafe client required')
    if stress is not None:
        from .campaign_stress import stress_package, POLICY_HASH
        package = stress_package(package, stress)
    plan = campaign_plan(package, worlds=worlds, max_calls=max_calls)
    if type(sample_actions) is not bool:
        raise ValueError('explicit action sampling policy required')
    if stress is None and sample_actions:
        from .probability_sampling import POLICY_SHA256
        plan.update(sampling_policy_sha256=POLICY_SHA256, decision_policy='sample_jev_action_and_coordination_scores')
    else:
        plan['decision_policy'] = 'artificial_stress_sampling' if stress else 'legacy_argmax_with_confidence_gate'
    if stress is not None:
        plan.update(stress_policy=deepcopy(stress), stress_policy_sha256=POLICY_HASH)
    if commitments is not None:
        from .committed_campaigns import PLAN_ENGINE_HASH
        plan.update(committed_plan=deepcopy(commitments), plan_engine_sha256=PLAN_ENGINE_HASH)
    preview = _campaign_engine(package, seed, commitments)
    _prepare(preview)
    from .campaign_evidence import campaign_evidence_context, review_campaign_evidence
    context = campaign_evidence_context(package, commitments=commitments, stress=stress, sample_actions=sample_actions)
    evidence_audit = review_campaign_evidence(evidence_register, context)
    for actor in preview.actors:
        campaign_request(preview, actor, client.model)
    store = _Artifacts(output_dir)
    store.new('package.json', package)
    store.new('plan.json', plan)
    store.new('evidence-register.json', evidence_register)
    manifest = {**plan, 'schema_version': 'campaign-experiment.v1', 'engine_sha256': ENGINE_HASH,
                'model': client.model, 'evidence_audit': evidence_audit, 'sample_actions': sample_actions,
                'status': 'running', 'base_seed': seed, 'attempted_calls': 0, 'completed_calls': 0,
                'completed_steps': 0, 'completed_worlds': 0, 'error': None, 'world_summaries': [],
                'retry_policy': 'none', 'resume_status': 'not implemented; failed runs preserve partial evidence'}
    manifest.pop('model_calls')
    store.new('manifest.json', manifest)
    try:
        for world_index in range(worlds):
            engine = _campaign_engine(package, seed + world_index, commitments)
            for step_index in range(len(package['decision_seconds'])):
                _prepare(engine)
                requests = {actor: campaign_request(engine, actor, client.model) for actor in engine.actors}
                prefix = f'world-{world_index:04d}-step-{step_index:05d}'
                store.new(prefix + '.observations.json', {actor: request['state'] for actor, request in requests.items()})
                decisions = []
                for actor in engine.actors:
                    if manifest['attempted_calls'] >= max_calls:
                        raise ValueError('experiment call cap reached')
                    call_prefix = f'call-{manifest["attempted_calls"] + 1:06d}'
                    store.new(call_prefix + '.request.json', requests[actor])
                    store.new(call_prefix + '.dispatch.json', {'status': 'dispatching', 'world': world_index,
                                                               'step': step_index, 'actor': actor,
                                                               'request_sha256': digest(requests[actor])})
                    manifest['attempted_calls'] += 1
                    store.replace('manifest.json', manifest)
                    if stress is None and sample_actions:
                        from .probability_sampling import decide_sampled
                        response = decide_sampled(engine, actor, client)
                    elif stress is None:
                        response = decide_campaign(engine, actor, client)
                    else:
                        from .campaign_stress import decide_stress
                        response = decide_stress(engine, actor, client, stress)
                    store.new(call_prefix + '.response.json', response)
                    manifest['completed_calls'] += 1
                    store.replace('manifest.json', manifest)
                    decisions.append(response['decision'])
                checkpoint = engine.advance(decisions)
                store.new(prefix + '.checkpoint.json', checkpoint)
                manifest['completed_steps'] += 1
                store.replace('manifest.json', manifest)
            manifest['completed_worlds'] += 1
            manifest['world_summaries'].append({'world': world_index, 'seed': seed + world_index,
                                               'final_state_hash': engine.chain_hash,
                                               'final_market': engine.market_state(package['decision_seconds'][-1]),
                                               'actor_summaries': deepcopy(engine.summary),
                                               'balances': {actor: {'cash_cents': balance.cash_cents,
                                                                     'token_units': balance.token_units}
                                                            for actor, balance in engine.ledger.accounts.items()}})
            store.replace('manifest.json', manifest)
        manifest['status'] = 'completed'
    except Exception as error:
        manifest['status'] = 'failed'
        manifest['error'] = {'code': error.code if isinstance(error, ModelFailure) else 'validation_or_artifact_failure',
                             'remote_outcome': error.remote_outcome if isinstance(error, ModelFailure) else 'unknown'}
        if callable(getattr(error, 'safe_details', None)):
            manifest['error']['details'] = error.safe_details()
    store.replace('manifest.json', manifest)
    return deepcopy(manifest)


def replay_campaign_experiment(directory):
    root = Path(directory)
    manifest = read_json(root / 'manifest.json')
    package = read_json(root / 'package.json')
    plan = campaign_plan(package, worlds=manifest['worlds'], max_calls=manifest['max_calls'])
    if manifest['engine_sha256'] != ENGINE_HASH or plan['required_calls'] != manifest['required_calls']:
        raise ValueError('campaign experiment engine or plan mismatch')
    if 'evidence_audit' in manifest:
        from .campaign_evidence import campaign_evidence_context, review_campaign_evidence
        context = campaign_evidence_context(package, commitments=manifest.get('committed_plan'),
                    stress=manifest.get('stress_policy'), sample_actions=manifest.get('sample_actions',
                        manifest['decision_policy'] != 'legacy_argmax_with_confidence_gate'))
        evidence = review_campaign_evidence(read_json(root / 'evidence-register.json'), context)
        if evidence != manifest['evidence_audit']:
            raise ValueError('campaign evidence replay mismatch')
    if manifest.get('committed_plan') is not None:
        from .committed_campaigns import PLAN_ENGINE_HASH
        if manifest.get('plan_engine_sha256') != PLAN_ENGINE_HASH:
            raise ValueError('committed plan engine version mismatch')
    completed_steps = 0
    complete = []
    for world_index in range(manifest['worlds']):
        engine = _campaign_engine(package, manifest['base_seed'] + world_index, manifest.get('committed_plan'))
        for step_index in range(len(package['decision_seconds'])):
            path = root / f'world-{world_index:04d}-step-{step_index:05d}.checkpoint.json'
            if not path.exists():
                break
            _prepare(engine)
            saved = read_json(path)
            requests = {actor: campaign_request(engine, actor, manifest['model']) for actor in engine.actors}
            stored_observations = read_json(root / f'world-{world_index:04d}-step-{step_index:05d}.observations.json')
            if stored_observations != {actor: request['state'] for actor, request in requests.items()}:
                raise ValueError('campaign observation replay mismatch')
            for actor_index, actor in enumerate(engine.actors):
                call_index = ((world_index * len(package['decision_seconds']) + step_index) * len(engine.actors)
                              + actor_index + 1)
                call_prefix = root / f'call-{call_index:06d}'
                request = read_json(str(call_prefix) + '.request.json')
                response = read_json(str(call_prefix) + '.response.json')
                if (request != requests[actor] or response['request_sha256'] != digest(request)
                        or response['decision'] != saved['decisions'][actor]):
                    raise ValueError('campaign decision evidence mismatch')
                if manifest.get('stress_policy') is not None:
                    from .campaign_stress import stress_action, POLICY_HASH
                    if manifest.get('stress_policy_sha256') != POLICY_HASH:
                        raise ValueError('stress policy version mismatch')
                    selected, metadata = stress_action(engine, actor, response, manifest['stress_policy'])
                    if selected != response['decision']['action_id'] or metadata != response.get('stress_policy'):
                        raise ValueError('stress sampling replay mismatch')
                if manifest.get('sampling_policy_sha256') is not None:
                    from .probability_sampling import POLICY_SHA256, sample_answer
                    if manifest['sampling_policy_sha256'] != POLICY_SHA256:
                        raise ValueError('action sampling policy version mismatch')
                    metadata = {}
                    for question, field, fallback in (('action', 'action_id', 'wait'), ('coordination', 'signal_id', 'silent')):
                        selected = fallback
                        if question in response['answers']:
                            selected, metadata[question] = sample_answer(response['answers'][question],
                                seed=engine.seed, actor_id=actor, elapsed_seconds=engine.second, question=question)
                        if response['decision'][field] != selected:
                            raise ValueError('sampled action replay mismatch')
                    if metadata != response.get('sampling_policy'):
                        raise ValueError('sampling evidence replay mismatch')
            regenerated = engine.advance(list(saved['decisions'].values()))
            if canonical(saved) != canonical(regenerated):
                raise ValueError('campaign checkpoint replay mismatch')
            completed_steps += 1
        if engine.index == len(package['decision_seconds']):
            complete.append({'world': world_index, 'seed': manifest['base_seed'] + world_index,
                             'final_state_hash': engine.chain_hash,
                             'final_market': engine.market_state(package['decision_seconds'][-1]),
                             'actor_summaries': deepcopy(engine.summary),
                             'balances': {actor: {'cash_cents': balance.cash_cents, 'token_units': balance.token_units}
                                          for actor, balance in engine.ledger.accounts.items()}})
    if completed_steps != manifest['completed_steps'] or complete != manifest['world_summaries']:
        raise ValueError('campaign progress or final state mismatch')
    if len(complete) != manifest['completed_worlds']:
        raise ValueError('campaign world denominator mismatch')
    if manifest['status'] == 'completed' and len(complete) != manifest['worlds']:
        raise ValueError('incomplete experiment labeled completed')
    if manifest['status'] == 'completed' and not (manifest['attempted_calls'] == manifest['completed_calls'] == manifest['required_calls']):
        raise ValueError('campaign completed call denominator mismatch')
    return {'verified_steps': completed_steps, 'verified_worlds': len(complete), 'model_calls': 0}


def summarize_campaign_experiment(directory):
    from collections import Counter
    root = Path(directory)
    manifest = read_json(root / 'manifest.json')
    if manifest['status'] != 'completed':
        raise ValueError('final summary requires a completed experiment; inspect its manifest for live progress')
    verification = replay_campaign_experiment(root)
    outcomes = Counter()
    providers = Counter()
    sampled = Counter()
    unbuffed = Counter()
    volume = 0
    campaign_spend = 0
    for world in range(manifest['worlds']):
        for step in range(manifest['steps']):
            checkpoint = read_json(root / f'world-{world:04d}-step-{step:05d}.checkpoint.json')
            campaign_spend += sum(item['cost_cents'] for item in checkpoint.get('committed_plan_execution', []))
            for settlement in checkpoint['settlements']:
                kind, status = settlement['action']['kind'], settlement['status']
                outcomes[f'{kind}:{status}'] += 1
                if status == 'executed':
                    volume += settlement['fill']['cash_cents']
                elif status == 'paid':
                    campaign_spend += settlement['action']['cost_cents']
    for call in range(1, manifest['completed_calls'] + 1):
        response = read_json(root / f'call-{call:06d}.response.json')
        providers[response['answers'].get('action', {}).get('choice', 'wait')] += 1
        sampled[response['decision']['action_id']] += 1
        policy = response.get('stress_policy')
        if policy is not None:
            unbuffed[policy['unbuffed_same_draw_action']] += 1
    return {'schema_version': 'campaign-summary.v1', 'status': 'completed', **verification,
            'completed_actor_calls': manifest['completed_calls'], 'stress_policy': manifest.get('stress_policy'),
            'settlement_counts': dict(outcomes), 'executed_volume_cents': volume,
            'campaign_spend_cents': campaign_spend, 'provider_action_counts': dict(providers),
            'selected_policy_action_counts': dict(sampled),
            'conditional_unbuffed_sample_counts': dict(unbuffed),
            'interpretation': 'Recorded simulation fills only, not real market volume or calibrated behavior. '
                              'Conditional unbuffed samples are not an alternate full-world simulation.'}
