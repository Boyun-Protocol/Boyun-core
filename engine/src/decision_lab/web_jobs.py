"""Bounded, offline jobs for the local workbench; no provider or wallet calls."""
from copy import deepcopy
from dataclasses import asdict
from importlib.resources import files
import json
import math
import os
from pathlib import Path
from queue import Queue
import secrets
import sqlite3
from threading import RLock, Thread
import time
from uuid import uuid4

from .actors import TRADING_CATEGORIES, build_cast
from .checkpoints import run_checkpointed
from .evaluation import evaluate_forecasts
from .experiments import ALLOWED_PARAMETERS, compare_policies, sensitivity
from .integrity import create_commitment, verify_commitment, near_anchor_action
from .policy_bundles import compile_bundle
from .policy_preparation import prepare_request, import_response, validate_request, _strict_json
from .simulation import default_scenario, load_pool, _validate, _policy_bindings, _prepare_simulation, _world, _summarize_worlds, simulate, compare_plans
from .topic_evidence import analyze_topics
from .wallet_evidence import analyze_wallets


MAX_JOBS = 64
MAX_QUEUED = 8
MAX_BODY = 2 * 1024 * 1024
MAX_RESULT_BYTES = 8 * 1024 * 1024
MAX_EXPANDED_METADATA_BYTES = 4 * 1024 * 1024


class BusyError(ValueError):
    """The bounded local queue is full."""


def encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()


def _private_write(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(fd, 'wb') as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def _bounded_json(value, depth=0):
    if depth > 48:
        raise ValueError('JSON nesting limit exceeded')
    if type(value) is dict:
        if len(value) > 1000:
            raise ValueError('object limit exceeded')
        for key, item in value.items():
            if type(key) is not str or len(key) > 256:
                raise ValueError('invalid JSON key')
            _bounded_json(item, depth + 1)
    elif type(value) is list:
        if len(value) > 1000:
            raise ValueError('list limit exceeded')
        for item in value:
            _bounded_json(item, depth + 1)
    elif type(value) is str:
        if len(value) > 256_000:
            raise ValueError('text limit exceeded')
    elif type(value) in (int, float):
        if not math.isfinite(value) or abs(value) > 10**15:
            raise ValueError('numeric limit exceeded')
    elif value is not None and type(value) is not bool:
        raise ValueError('invalid JSON value')


def _integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError('integer outside workbench limits')
    return value


def _scenario_preflight(scenario, pool, worlds, seed):
    """Apply browser budgets before the cast builder allocates any actors."""
    if type(scenario) is not dict:
        raise ValueError('scenario required')
    if type(scenario.get('cast_recipe')) is not dict:
        raise ValueError('cast recipe must be an object')
    _validate(scenario, worlds, seed, 'launch_now')
    _integer(scenario['horizon_hours'], 1, 8760)
    recipe = scenario.get('cast_recipe')
    groups = recipe.get('groups') if type(recipe) is dict else None
    if type(groups) is not dict or not groups:
        raise ValueError('cast groups required')
    slots = 0
    for group in groups.values():
        if type(group) is not dict:
            raise ValueError('invalid cast group')
        slots += _integer(group.get('count'), 0, 1000)
        strategies, choices = group.get('strategy_choices'), group.get('subscription_choices')
        if type(strategies) is not list or not 1 <= len(strategies) <= 8:
            raise ValueError('strategy choice limit exceeded')
        if any(type(strategy) is not str or len(strategy) > 128 for strategy in strategies):
            raise ValueError('strategy text limit exceeded')
        if type(choices) is not list or not 1 <= len(choices) <= 16:
            raise ValueError('subscription choice limit exceeded')
        for choice in choices:
            if type(choice) is not list or len(choice) > 8:
                raise ValueError('subscription source count limit exceeded')
            if any(type(source) is not str or not source.strip() or len(source) > 128 for source in choice):
                raise ValueError('subscription source text limit exceeded')
    if slots > 1000 or slots * (scenario['horizon_hours'] // scenario['visit_interval_hours'] + 1) > 20_000:
        raise ValueError('cast or actor-visit budget exceeded')
    if any(len(scenario[key]) > 256 for key in ('campaigns', 'founder_sales', 'competitor_messages')):
        raise ValueError('event budget exceeded')
    cast = build_cast(pool, recipe, seed)
    if scenario['campaigns'] and not any(a.category == 'creators_marketing' for a in cast.actors):
        raise ValueError('campaigns require a creator')
    return cast


def _actor_dict(actor):
    value = asdict(actor)
    value['allowed_actions'] = sorted(actor.allowed_actions)
    value['subscriptions'] = list(actor.subscriptions)
    return value


def _cast_bindings(cast, compiled):
    if compiled is not None:
        return _policy_bindings(cast, compiled)
    actors = [{'actor_id': actor.id, 'template_id': actor.template_id,
               'mode': 'baseline' if actor.category in TRADING_CATEGORIES and actor.strategy in {'cautious', 'momentum'} else 'passive_role'}
              for actor in cast.actors]
    return {'counts': {mode: sum(actor['mode'] == mode for actor in actors) for mode in ('baseline', 'passive_role')}, 'actors': actors}


def _preflight_result(kind, context, cast, pool):
    bundle = context['policy_bundle']
    arms = 4 if kind == 'plans' else 2 if kind == 'policies' else len(context['values']) + 1 if kind == 'sensitivity' else 1
    # These user-authored fields are repeated in each comparison report. Bound
    # their expansion before any world or large result object is produced.
    metadata_size = len(encode(context['scenario']['assumptions'])) + (len(encode(bundle)) if bundle is not None else 0)
    if metadata_size * arms > MAX_EXPANDED_METADATA_BYTES:
        raise ValueError('expanded comparison metadata budget exceeded')
    if kind == 'cast':
        compiled = compile_bundle(bundle, pool) if bundle is not None else None
        rule_sizes = {template: len(encode(rule.as_dict())) for template, rule in compiled.rules.items()} if compiled else {}
        estimate = 1024 + (len(encode(bundle['source'])) if bundle else 0)
        for actor in cast.actors:
            # Serialize at most one small actor at a time. Do not construct a
            # huge repeated-rule actor list merely to discover its size.
            estimate += len(encode(_actor_dict(actor))) + 2048 + rule_sizes.get(actor.template_id, 0)
            if estimate > MAX_RESULT_BYTES:
                raise ValueError('expanded cast export budget exceeded')


def evaluation_fixture():
    """Packaged explicit synthetic scoring fixture; no historical data fetch."""
    return json.loads(files('decision_lab').joinpath('data/evaluation.synthetic.json').read_text())


class JobManager:
    def __init__(self, output_dir=None, *, policy_bundle_path=None, policy_evidence_path=None,
                 wallet_observation_paths=(), topic_observation_paths=(), public_archive_path=None):
        # A fresh session directory avoids collisions and public reuse of older files.
        root = Path(output_dir) if output_dir is not None else Path.cwd() / 'output' / 'workbench' / uuid4().hex
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.output_dir = root
        from .studio_api import StudioAPI
        self.studio = StudioAPI(root)
        self.pool = load_pool()
        self.csrf_token = secrets.token_urlsafe(32)
        self._lock = RLock()
        self._jobs = {}
        self._bundles = {}
        self._options = [{'id': 'baseline', 'label': 'Python rules baseline', 'bundle_id': None, 'model': None, 'source_kind': 'python_rules'}]
        self._queue = Queue(maxsize=MAX_QUEUED)
        self._closed = False
        self._evidence = {}
        self._evidence_options = []
        self._public_archive_path = public_archive_path
        self._archive_networks = {}
        if public_archive_path is not None:
            from .public_archive import PublicArchive
            with PublicArchive(public_archive_path, read_only=True) as archive:
                status = archive.status()
            for network in sorted({pool['network'] for pool in status['pools'] if pool['capture_count']}):
                evidence_id = uuid4().hex
                self._archive_networks[evidence_id] = network
                self._evidence_options.append({'id': evidence_id, 'kind': 'wallets', 'label': network.upper() + ' · accumulating public archive'})
        if len(wallet_observation_paths) + len(topic_observation_paths) > 8:
            raise ValueError('at most eight explicit evidence files supported')
        for kind, paths, analyze in (('wallets', wallet_observation_paths, analyze_wallets), ('topics', topic_observation_paths, analyze_topics)):
            for path in paths:
                path = Path(path)
                if path.stat().st_size > MAX_BODY:
                    raise ValueError('evidence input exceeds the local body limit')
                raw = _strict_json(path.read_text())
                result = analyze(raw)
                if len(encode(result)) > MAX_RESULT_BYTES:
                    raise ValueError('evidence export too large')
                evidence_id = uuid4().hex
                self._evidence[evidence_id] = result
                label = (result['network'].upper() + ' · observed wallet snapshot') if kind == 'wallets' else result['topic']
                self._evidence_options.append({'id': evidence_id, 'kind': kind, 'label': label})
        if policy_bundle_path is not None:
            path = Path(policy_bundle_path)
            if path.stat().st_size > MAX_BODY:
                raise ValueError('policy bundle too large')
            raw = _strict_json(path.read_text())
            _bounded_json(raw)
            bundle = compile_bundle(raw, self.pool).as_dict()
            self._bundles['loaded-policy'] = bundle
            label = 'Loaded manual policies' if bundle['source']['kind'] == 'manual' else 'Loaded policies · ' + bundle['source']['model']
            self._options.append(self._option('loaded-policy', label, bundle))
        # Explicit evidence may contain raw stdout, prompts or credentials. It is
        # deliberately not read; selected bundle metadata is declared/unverified.
        self._worker = Thread(target=self._work, name='decision-lab-local-worker', daemon=True)
        self._worker.start()

    @staticmethod
    def _option(policy_id, label, bundle):
        return {'id': policy_id, 'label': label, 'bundle_id': bundle['bundle_id'],
                'model': bundle['source'].get('model'), 'source_kind': bundle['source']['kind']}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def close(self):
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self._queue.put(None)
        self._worker.join()

    def bootstrap(self):
        with self._lock:
            return {'csrf_token': self.csrf_token, 'scenario': default_scenario(), 'pool': deepcopy(self.pool),
                'evaluation_fixture': evaluation_fixture(), 'policy_options': deepcopy(self._options),
                'evidence_options': deepcopy(self._evidence_options),
                'capabilities': {'local_only': True, 'offline_execution': True, 'live_model_calls': False,
                    'onchain_submission': False, 'unsigned_near_testnet_actions': True, 'max_worlds': 100,
                    'max_comparison_worlds': 50, 'max_cast_slots': 1000, 'max_actor_visits_per_world': 20000,
                    'max_jobs': MAX_JOBS, 'max_queued_jobs': MAX_QUEUED, 'max_result_bytes': MAX_RESULT_BYTES},
                'provenance': {'default_execution': 'Python rules; no LLM runs inside synthetic worlds.',
                    'policy_metadata': 'declared_unverified', 'model_access': 'No user API key has been received or used by this UI. No keys are read or stored.',
                    'pilot': ('No imported policy loaded.' if 'loaded-policy' not in self._bundles else
                        'Declared ' + (self._bundles['loaded-policy']['source'].get('model') or 'manual') +
                        ' source, unverified; no live calls.'),
                    'template_fields': 'Persona descriptions identify templates. Legacy numeric template defaults are not engine parameters; funded actor fields come from the explicit cast recipe.',
                    'evidence': 'Policy execution evidence logs are not read or exposed. Explicitly selected wallet/news snapshots are analyzed and exposed locally. Bundle metadata does not attest provider execution or usage.'}}

    def evidence(self, evidence_id):
        with self._lock:
            if evidence_id in self._archive_networks:
                from .public_archive import PublicArchive
                with PublicArchive(self._public_archive_path, read_only=True) as archive:
                    result = analyze_wallets(archive.export_snapshot(self._archive_networks[evidence_id]))
                    result['archive_status'] = {**archive.status(), 'configured': True}
                return result
            return deepcopy(self._evidence[evidence_id])

    def public_history(self):
        if self._public_archive_path is None:
            return {'configured': False}
        from .public_archive import PublicArchive
        try:
            with PublicArchive(self._public_archive_path, read_only=True) as archive:
                return {**archive.status(), 'configured': True}
        except (ValueError, OSError, sqlite3.Error):
            return {'configured': True, 'available': False}

    def _prepare(self, data):
        _bounded_json(data)
        if type(data) is not dict:
            raise ValueError('job must be an object')
        if data.get('kind') == 'scenario':
            from .studio_api import scenario_preflight
            return 'scenario', scenario_preflight(data), None
        if data.get('kind') in ('wallets', 'topics'):
            if set(data) != {'kind', 'snapshot'}:
                raise ValueError('evidence import takes only kind and snapshot')
            analyze = analyze_wallets if data['kind'] == 'wallets' else analyze_topics
            result = analyze(data['snapshot'])
            if len(encode(result)) > MAX_RESULT_BYTES:
                raise ValueError('evidence export too large')
            return data['kind'], {'worlds': 0, 'evidence': result}, None
        kinds = {'run', 'plans', 'policies', 'sensitivity', 'evaluate', 'cast', 'prepare', 'import', 'checkpoint', 'resume'}
        kind = data.get('kind')
        if type(kind) is not str or kind not in kinds:
            raise ValueError('unknown job kind')
        common = {'kind', 'scenario', 'worlds', 'seed', 'policy_id'}
        extras = {'sensitivity': {'parameter', 'values'}, 'evaluate': {'dataset'},
            'prepare': {'model', 'template_ids', 'fallback', 'max_output_tokens'},
            'import': {'request', 'response', 'bundle_id'}, 'checkpoint': {'batch_worlds'}, 'resume': {'resume_job_id'}}
        if set(data) - common - extras.get(kind, set()):
            raise ValueError('unknown job field')
        if kind == 'resume':
            # Browser callers can never supply a checkpoint path or replacement inputs.
            if set(data) != {'kind', 'resume_job_id'}:
                raise ValueError('resume requires only a saved job ID')
            original = self._jobs.get(data['resume_job_id']) if type(data['resume_job_id']) is str else None
            if original is None or original['status'] != 'paused' or original.get('resumed_by'):
                raise ValueError('saved job is not resumable')
            return kind, deepcopy(original['context']), original
        worlds = _integer(data.get('worlds', 10), 1, 50 if kind in {'plans', 'policies', 'sensitivity'} else 100)
        seed = _integer(data.get('seed', 42), 0, 2**63 - 1)
        policy_id = data.get('policy_id', 'baseline')
        if type(policy_id) is not str or policy_id != 'baseline' and policy_id not in self._bundles:
            raise ValueError('unknown registered policy')
        if kind == 'import':
            request = data.get('request')
            if type(request) is not dict or type(request.get('context')) is not dict:
                raise ValueError('invalid policy request')
            scenario = deepcopy(request['context'].get('scenario'))
        else:
            scenario = deepcopy(data.get('scenario', default_scenario()))
        cast = _scenario_preflight(scenario, self.pool, worlds, seed)
        context = {'scenario': scenario, 'worlds': worlds, 'seed': seed,
                   'policy_bundle': deepcopy(self._bundles.get(policy_id))}
        if kind == 'policies' and context['policy_bundle'] is None:
            raise ValueError('select an imported policy for comparison')
        if kind == 'checkpoint':
            context['batch_worlds'] = _integer(data.get('batch_worlds', 1), 1, worlds)
        elif kind == 'sensitivity':
            parameter, values = data.get('parameter'), data.get('values')
            if type(parameter) is not str or parameter not in ALLOWED_PARAMETERS or type(values) is not list or not 1 <= len(values) <= 8:
                raise ValueError('invalid sensitivity sweep')
            if any(type(v) is not int for v in values) or len(set(values)) != len(values):
                raise ValueError('invalid sensitivity values')
            if worlds * (len(values) + 1) > 200:
                raise ValueError('total comparison world budget exceeded')
            for value in values:
                _scenario_preflight({**scenario, parameter: value}, self.pool, worlds, seed)
            context.update(parameter=parameter, values=deepcopy(values))
        elif kind == 'evaluate':
            dataset = deepcopy(data.get('dataset'))
            evaluate_forecasts(dataset)
            context['dataset'] = dataset
        elif kind == 'prepare':
            context['request'] = prepare_request(scenario, self.pool, model=data.get('model'), template_ids=data.get('template_ids'),
                fallback=data.get('fallback', 'baseline'), max_output_tokens=_integer(data.get('max_output_tokens', 4096), 1, 32768))
        elif kind == 'import':
            request = data.get('request')
            # Embedded scenario already passed browser allocation limits above.
            validate_request(request, self.pool)
            bundle, receipt = import_response(request, data.get('response'), self.pool, bundle_id=data.get('bundle_id'))
            context.update(bundle=bundle, receipt=receipt)
        _preflight_result(kind, context, cast, self.pool)
        return kind, context, None

    def submit(self, data):
        with self._lock:
            if self._closed or len(self._jobs) >= MAX_JOBS or self._queue.full():
                raise BusyError('local job capacity reached')
            kind, context, original = self._prepare(data)
            job_id = uuid4().hex
            if kind == 'checkpoint':
                context['checkpoint_path'] = str(self.output_dir / (job_id + '.checkpoint.json'))
            job = {'job_id': job_id, 'kind': kind, 'status': 'queued', 'result': None, 'error': None,
                'elapsed_seconds': 0.0, 'phase': 'queued', 'actor_count': None, 'active_traders': None, 'completed_worlds': 0, 'target_worlds': context['worlds'] if kind in {'run', 'plans', 'policies', 'sensitivity', 'checkpoint', 'resume', 'scenario'} else 0,
                'context': context, 'created': time.monotonic()}
            self._jobs[job_id] = job
            if original is not None:
                original['resumed_by'] = job_id
                job['completed_worlds'] = original['completed_worlds']
            self._queue.put_nowait(job_id)
            return {'job_id': job_id, 'status': 'queued'}

    def snapshot(self, job_id):
        with self._lock:
            job = self._jobs[job_id]
            return deepcopy({key: job[key] for key in ('job_id', 'kind', 'status', 'result', 'error', 'elapsed_seconds', 'completed_worlds', 'target_worlds', 'phase', 'actor_count', 'active_traders')})

    def _work(self):
        while True:
            job_id = self._queue.get()
            if job_id is None:
                self._queue.task_done()
                return
            with self._lock:
                job = self._jobs[job_id]
                job['status'] = 'running'
                job['phase'] = 'validating' if job['kind'] == 'run' else 'running'
            start = time.monotonic()
            try:
                result = self.execute_job(job)
                content = encode(result) if result is not None else None
                if content is not None and len(content) > MAX_RESULT_BYTES:
                    raise ValueError('encoded result exceeds local export budget')
                if content is not None:
                    _private_write(self.output_dir / (job_id + '.result.json'), content)
                with self._lock:
                    job['result'] = result
                    if result is None:
                        job['status'] = 'paused'
                        job['phase'] = 'paused'
                        job['completed_worlds'] = job['context']['batch_worlds']
                    else:
                        job['status'] = 'completed'
                        job['phase'] = 'completed'
                        job['completed_worlds'] = job['target_worlds']
                        job['bytes'] = content
            except Exception:
                # Inputs may be confidential. No repr, path, traceback or raw provider data.
                with self._lock:
                    job['status'] = 'failed'
                    job['phase'] = 'failed'
                    job['error'] = 'Local computation failed; check supplied inputs and private output availability.'
            finally:
                with self._lock:
                    job['elapsed_seconds'] = round(time.monotonic() - start, 4)
                self._queue.task_done()

    def execute_job(self, job):
        kind, context = job['kind'], job['context']
        if kind == 'scenario':
            from .scenario_authoring import run_package
            return run_package(context['package'], worlds=context['worlds'], seed=context['seed'])
        if kind in {'wallets', 'topics'}:
            return context['evidence']
        scenario, worlds, seed, bundle = (context[k] for k in ('scenario', 'worlds', 'seed', 'policy_bundle'))
        if kind == 'run':
            # Progress reflects completed numerical work. No timers or invented
            # percentages stand in for cast building or simulated worlds.
            _validate(scenario, worlds, seed, 'launch_now')
            with self._lock:
                job['phase'] = 'building_cast'
            value, cast, compiled = _prepare_simulation(scenario, self.pool, worlds, seed, 'launch_now', bundle)
            with self._lock:
                job['actor_count'] = len(cast.actors)
                job['active_traders'] = sum(actor.category in TRADING_CATEGORIES and actor.strategy in {'cautious', 'momentum'} for actor in cast.actors)
                job['phase'] = 'preparing_worlds'
            results = []
            with self._lock:
                job['phase'] = 'simulating'
            for world_id in range(worlds):
                results.append(_world(value, cast, seed, world_id, 'launch_now', world_id < 3, compiled))
                with self._lock:
                    job['completed_worlds'] = len(results)
            with self._lock:
                job['phase'] = 'summarizing'
            return _summarize_worlds(value, self.pool, cast, results, seed, 'launch_now', compiled)
        if kind == 'plans':
            return compare_plans(scenario, self.pool, worlds, seed, policy_bundle=bundle)
        if kind == 'policies':
            return compare_policies(scenario, self.pool, bundle, worlds, seed)
        if kind == 'sensitivity':
            return sensitivity(scenario, self.pool, parameter=context['parameter'], values=context['values'], worlds=worlds, seed=seed, policy_bundle=bundle)
        if kind == 'evaluate':
            return evaluate_forecasts(context['dataset'])
        if kind == 'prepare':
            return context['request']
        if kind == 'import':
            policy_id = uuid4().hex
            with self._lock:
                self._bundles[policy_id] = deepcopy(context['bundle'])
                self._options.append(self._option(policy_id, 'Imported policies: ' + context['bundle']['bundle_id'], context['bundle']))
            return {'bundle': context['bundle'], 'receipt': context['receipt'], 'policy_id': policy_id}
        if kind == 'cast':
            cast = build_cast(self.pool, scenario['cast_recipe'], seed)
            compiled = compile_bundle(bundle, self.pool) if bundle is not None else None
            bindings = _cast_bindings(cast, compiled)
            modes = {binding['actor_id']: binding['mode'] for binding in bindings['actors']}
            actors = []
            for actor in cast.actors:
                value = _actor_dict(actor)
                mode = modes[actor.id]
                rule = compiled.rules[actor.template_id].as_dict() if mode == 'explicit_rule' else None
                value['policy_binding'] = {'mode': mode, 'rule': rule}
                value['effective_entry_fraction_bps'] = (0 if mode in {'passive_role', 'abstain_fallback'} else
                    min(actor.entry_fraction_bps, rule['entry_fraction_bps']) if rule is not None else actor.entry_fraction_bps)
                actors.append(value)
            return {'actors': actors, 'excluded': cast.excluded, 'pool_count': len(self.pool['profiles']), 'selected_count': len(actors),
                    'policy_bindings': bindings, 'policy_source': deepcopy(bundle['source']) if bundle else None}
        if kind in {'checkpoint', 'resume'}:
            return run_checkpointed(scenario, self.pool, checkpoint_path=context['checkpoint_path'], worlds=worlds,
                seed=seed, policy_bundle=bundle, resume=kind == 'resume',
                max_new_worlds=context['batch_worlds'] if kind == 'checkpoint' else None)
        raise ValueError('unsupported job')

    def result_bytes(self, job_id):
        with self._lock:
            job = self._jobs[job_id]
            if job['status'] != 'completed':
                raise ValueError('job is not completed')
            return job['bytes']

    def commitment(self, job_id):
        with self._lock:
            data = self.result_bytes(job_id)
            job = self._jobs[job_id]
            if 'public' not in job:
                public, opening = create_commitment(data)
                if not verify_commitment(data, public, opening):
                    raise ValueError('local commitment verification failed')
                _private_write(self.output_dir / (job_id + '.opening.json'), encode(opening))
                _private_write(self.output_dir / (job_id + '.commitment.json'), encode(public))
                job.update(public=public, opening=opening)
            return {'public': deepcopy(job['public']), 'verified': verify_commitment(data, job['public'], job['opening'])}

    def opening_bytes(self, job_id):
        with self._lock:
            opening = self._jobs[job_id].get('opening')
            if opening is None:
                raise ValueError('create commitment first')
            return encode(opening)

    def near_action(self, job_id, data):
        with self._lock:
            public = self._jobs[job_id].get('public')
            if public is None or type(data) is not dict or set(data) != {'network', 'signer_id', 'contract_id'}:
                raise ValueError('create commitment and supply explicit testnet accounts')
            return near_anchor_action(public, network=data['network'], signer_id=data['signer_id'], contract_id=data['contract_id'])
