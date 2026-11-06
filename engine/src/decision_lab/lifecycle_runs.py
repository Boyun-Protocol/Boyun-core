"""Budget-reserved lifecycle inference, durable receipts and zero-call exact replay."""
from copy import deepcopy
from decimal import Decimal, ROUND_CEILING
from fractions import Fraction
from hashlib import sha256
from pathlib import Path
from threading import RLock

from .agent_orchestration import _Artifacts
from .agent_worlds import canonical, digest
from .io_helpers import read_json
from .jev import TypeSafeClient, validate_request
from .launch_lifecycle import LaunchLifecycle, LIFECYCLE_HASH
from .probability_sampling import sample_answer
from .simulation_evidence import audit_evidence, numeric_targets

RUNNER_HASH = sha256(Path(__file__).read_bytes() + Path(__file__).with_name('probability_sampling.py').read_bytes()).hexdigest()

class SpendGuard:
    def __init__(self, cap_usd, price_per_million='0.042'):
        cap = Decimal(str(cap_usd))
        price = Decimal(str(price_per_million))
        if not cap.is_finite() or not price.is_finite() or cap <= 0 or price <= 0:
            raise ValueError('positive explicit inference budget and price required')
        self.cap_micro_usd = int(cap * 1000000)
        self.price = price
        self.spent_micro_usd = 0
        self.reserved_micro_usd = 0
        self.attempted_calls = 0
        self.completed_calls = 0
        self.lock = RLock()

    def estimate(self, request):
        tokens = len(canonical(request)) + 1024
        return int((Decimal(tokens) * self.price).to_integral_value(rounding=ROUND_CEILING))

    def reserve(self, request):
        amount = self.estimate(request)
        with self.lock:
            if self.spent_micro_usd + self.reserved_micro_usd + amount > self.cap_micro_usd:
                raise ValueError('inference budget exhausted before dispatch')
            self.reserved_micro_usd += amount
            self.attempted_calls += 1
            identifier = self.attempted_calls
        return {'micro_usd': amount, 'call_index': identifier}

    def settle(self, reservation, receipt):
        reservation = reservation['micro_usd']
        tokens = receipt.get('usage', {}).get('input_tokens')
        with self.lock:
            if type(tokens) is not int or tokens < 0:
                return
            actual = int((Decimal(tokens) * self.price).to_integral_value(rounding=ROUND_CEILING))
            self.reserved_micro_usd -= reservation
            self.spent_micro_usd += actual
            self.completed_calls += 1
            if actual > reservation:
                raise ValueError('reported usage exceeded conservative request reservation; stop and reconcile billing')

    def snapshot(self):
        with self.lock:
            return {'cap_micro_usd': self.cap_micro_usd, 'spent_estimate_micro_usd': self.spent_micro_usd,
                    'uncertain_reserved_micro_usd': self.reserved_micro_usd,
                    'attempted_calls': self.attempted_calls, 'completed_calls': self.completed_calls,
                    'price_usd_per_million': str(self.price),
                    'limitation': 'Published tariff estimate, not a provider billing guarantee. Unknown dispatches retain reservations; no automatic retry.'}


def lifecycle_targets(package):
    targets = numeric_targets(package)
    for index, actor in enumerate(package['actors']):
        targets[f'/actors/{index}/goal'] = 'input'
        targets[f'/actors/{index}/role'] = 'input'
    for index, campaign in enumerate(package['campaigns']):
        targets[f'/campaigns/{index}/delivery_bps'] = 'probability'
        targets[f'/campaigns/{index}/text'] = 'input'
    for index in range(len(package['events'])):
        targets[f'/events/{index}/text'] = 'input'
    targets.update({'input:regime': 'input', 'input:memory_policy': 'input',
                    'probability:actor_scores': 'probability', 'outcome:cash': 'outcome',
                    'outcome:price': 'outcome', 'outcome:volume': 'outcome'})
    return targets


def review_lifecycle(package, register):
    if register is None:
        raise ValueError('lifecycle evidence register required before inference')
    audit = audit_evidence(register, required_targets=lifecycle_targets(package), target_sha256=digest(package))
    if audit['status'] != 'ready_for_conditional_simulation':
        raise ValueError('lifecycle evidence review blocked')
    return audit


def lifecycle_request(engine, actor, model):
    observed = engine.observation(actor)
    market = observed['market']
    signal = market['six_hour_signal']
    state = {'actor': observed['actor'], 'second': engine.second, 'regime': observed['regime'],
             'own': observed['own'],
             'market': {'phase': market['phase'], 'mc_usd': round(float(Fraction(market['market_cap_usd_exact'])), 2),
                        'real_cash_cents': market['real_cash_cents'], 'total_volume_cents': market['total_volume_cents'],
                        'volume_6h_cents': signal['current_volume_cents'], 'volume_peak_ratio': signal['fraction_of_peak_exact']},
             'memory': {'own_last_choice': observed['memory']['own_last_choice'],
                        'own_totals': observed['memory']['own_totals'],
                        'recent_prices': observed['memory']['recent_public_prices'][-3:]},
             'campaigns': [[item['id'], item['status']] for item in observed['campaigns']],
             'events': [item['text'] for item in observed['events'][-2:]],
             'posts': [[item['actor'], item['second']] for item in observed['public_posts']],
             'coordination': [[item['choice'], item['available_second']] for item in observed['coordination']]}
    if actor == engine.founder:
        state['own_policy'] = {'reserve_cents': observed['own_policy']['reserve_cents'],
                               'position_remaining': observed['own_policy']['remaining_position_cents'],
                               'response': observed['own_policy']['response']['policy'] if observed['own_policy']['response'] else None}
    menu = engine.menu(actor)
    if len(menu) == 1:
        return None
    instructions = ('Choose for your own goal from current public state, own funds and memory. '
                    'BULL/BEAR are conditional risk-appetite hypotheses. Ads are exposure, not buyers. '
                    'No future/private peer knowledge. Cash is cents; choices are not calibrated event odds.')
    criteria = {key: value for key, value in menu.items()}
    return validate_request(state=state, questions={'action': {'type': 'choice', 'instructions': instructions,
                                                            'criteria': criteria}}, model=model)


def offline_reference_choice(engine, actor):
    menu = engine.menu(actor)
    score = keyed_reference(engine, actor)
    if engine.actors[actor]['role'] in {'organic', 'foundation', 'partnership', 'kol'} and score < 12:
        return 'publish'
    if engine.package['regime'] == 'BULL':
        buy_cutoff, sell_cutoff = 40, 60
    else:
        buy_cutoff, sell_cutoff = 15, 55
    multiplier = engine.package['activity_multiplier']
    if score < min(75, buy_cutoff * multiplier) and 'buy_small' in menu:
        return 'buy_small'
    if score < min(95, sell_cutoff * multiplier) and 'sell_small' in menu:
        return 'sell_small'
    return 'wait'


def keyed_reference(engine, actor):
    from .randomness import keyed_rng
    return keyed_rng(engine.seed, 'explicit-offline-reference', engine.second, actor).randrange(100)


def sampled_choice(answer, engine, actor):
    original = deepcopy(answer)
    multiplier = engine.package['activity_multiplier']
    if multiplier != 1:
        weights = {key: score * (multiplier if key.startswith(('buy_', 'sell_')) else 1)
                   for key, score in original['probabilities'].items()}
        total = sum(weights.values())
        original['probabilities'] = {key: value / total for key, value in weights.items()}
        original['choice'] = max(original['probabilities'], key=original['probabilities'].get)
    selected, metadata = sample_answer(original, seed=engine.seed, actor_id=actor,
                                       elapsed_seconds=engine.second, question='lifecycle-action')
    metadata['activity_multiplier'] = multiplier
    metadata['provider_choice'] = answer['choice']
    return selected, metadata


def step_choices(engine, *, client=None, store=None, guard=None, mode='offline_reference', cache=None):
    choices, evidence = {}, {}
    for actor in engine.actors:
        if mode == 'offline_reference':
            choices[actor] = offline_reference_choice(engine, actor)
            evidence[actor] = {'policy': 'explicit_offline_reference_not_jev', 'model_calls': 0}
            continue
        request = lifecycle_request(engine, actor, client.model)
        if request is None:
            choices[actor] = 'wait'
            evidence[actor] = {'policy': 'forced_wait_only_feasible_action', 'model_calls': 0}
            continue
        full_observation_hash = digest(engine.observation(actor))
        cache_key = digest({'request': request, 'observation': full_observation_hash, 'seed': engine.seed})
        if cache is not None and cache_key in cache:
            saved = deepcopy(cache[cache_key])
            selected, metadata = sampled_choice(saved['answers']['action'], engine, actor)
            choices[actor] = selected
            evidence[actor] = {**saved, 'sampling': metadata, 'reuse': 'identical_actor_time_seed_observation_only', 'new_model_calls': 0}
            continue
        reservation = guard.reserve(request)
        index = reservation['call_index']
        prefix = f'call-{index:07d}'
        store.new(prefix + '.request.json', request)
        store.new(prefix + '.dispatch.json', {'status': 'dispatching', 'reservation_micro_usd': reservation['micro_usd'],
                    'second': engine.second, 'actor': actor, 'observation_sha256': full_observation_hash})
        store.replace('budget.json', guard.snapshot())
        response = client.evaluate(state=request['state'], questions=request['questions'])
        store.new(prefix + '.response.json', response)
        guard.settle(reservation, response['receipt'])
        store.replace('budget.json', guard.snapshot())
        selected, metadata = sampled_choice(response['answers']['action'], engine, actor)
        choices[actor] = selected
        evidence[actor] = {'answers': response['answers'], 'receipt': response['receipt'], 'sampling': metadata,
                           'request_sha256': digest(request), 'observation_sha256': full_observation_hash,
                           'call_prefix': prefix, 'new_model_calls': 1}
        if cache is not None:
            cache[cache_key] = deepcopy(evidence[actor])
    return choices, evidence


def run_lifecycle(*, package, output_dir, seed=31, mode='offline_reference', client=None,
                  spend_guard=None, evidence_register=None, response_policy='pause-and-observe'):
    engine = LaunchLifecycle(package, seed, response_policy)
    audit = review_lifecycle(package, evidence_register) if mode == 'jev' else None
    if mode not in {'jev', 'offline_reference'}:
        raise ValueError('explicit native or offline-reference mode required')
    if mode == 'jev':
        if not isinstance(client, TypeSafeClient) or not isinstance(spend_guard, SpendGuard):
            raise ValueError('native client and shared spend guard required')
        preview = deepcopy(engine)
        preview.prepare()
        estimate = sum(spend_guard.estimate(request) for actor in preview.actors
                       if (request := lifecycle_request(preview, actor, client.model)) is not None)
        if estimate > spend_guard.cap_micro_usd - spend_guard.spent_micro_usd - spend_guard.reserved_micro_usd:
            raise ValueError('budget cannot fund the initial decision barrier')
    store = _Artifacts(output_dir)
    store.new('package.json', package)
    if audit is not None:
        store.new('evidence-register.json', evidence_register)
    manifest = {'schema_version': 'launch-lifecycle-run.v1', 'engine_sha256': LIFECYCLE_HASH,
                'runner_sha256': RUNNER_HASH,
                'status': 'running', 'mode': 'jev' if mode == 'jev' else 'offline_reference_not_jev',
                'seed': seed, 'response_policy': response_policy, 'completed_steps': 0, 'model_calls': 0,
                'evidence_audit': audit, 'error': None, 'summary': engine.summary()}
    store.new('manifest.json', manifest)
    try:
        while engine.index < len(engine.schedule):
            engine.prepare()
            choices, evidence = step_choices(engine, client=client, store=store, guard=spend_guard, mode=mode)
            checkpoint = engine.advance(choices)
            store.new(f'step-{checkpoint["step"]:05d}.json', {'checkpoint': checkpoint, 'decision_evidence': evidence})
            manifest['completed_steps'] += 1
            manifest['model_calls'] += sum(value.get('new_model_calls', 0) for value in evidence.values())
            manifest['summary'] = engine.summary()
            store.replace('manifest.json', manifest)
        manifest['status'] = 'completed'
    except Exception as error:
        manifest['status'] = 'budget_exhausted' if isinstance(error, ValueError) and 'budget' in str(error) else 'failed'
        manifest['error'] = {'code': getattr(error, 'code', 'validation_or_artifact_failure'),
                             'message': 'Stopped without retry. Inspect private dispatch receipts; no fabricated continuation.'}
    if spend_guard is not None:
        manifest['budget'] = spend_guard.snapshot()
    store.replace('manifest.json', manifest)
    return manifest


def replay_lifecycle(directory):
    root = Path(directory)
    package, manifest = read_json(root / 'package.json'), read_json(root / 'manifest.json')
    if manifest['engine_sha256'] != LIFECYCLE_HASH or manifest['runner_sha256'] != RUNNER_HASH:
        raise ValueError('lifecycle replay engine mismatch')
    engine = LaunchLifecycle(package, manifest['seed'], manifest['response_policy'])
    if manifest['mode'] == 'jev':
        audit = review_lifecycle(package, read_json(root / 'evidence-register.json'))
        if audit != manifest['evidence_audit']:
            raise ValueError('lifecycle evidence replay mismatch')
    verified_calls = 0
    for index in range(manifest['completed_steps']):
        saved = read_json(root / f'step-{index:05d}.json')
        engine.prepare()
        if manifest['mode'] == 'jev':
            for actor, evidence in saved['decision_evidence'].items():
                if evidence.get('policy') == 'forced_wait_only_feasible_action':
                    if len(engine.menu(actor)) != 1:
                        raise ValueError('forced choice replay mismatch')
                    continue
                request = lifecycle_request(engine, actor, evidence['receipt']['model_declared'])
                selected, metadata = sampled_choice(evidence['answers']['action'], engine, actor)
                if (digest(request) != evidence['request_sha256'] or metadata != evidence['sampling']
                        or digest(engine.observation(actor)) != evidence['observation_sha256']
                        or selected != saved['checkpoint']['choices'][actor]):
                    raise ValueError('lifecycle decision replay mismatch')
                verified_calls += evidence.get('new_model_calls', 0)
        regenerated = engine.advance(saved['checkpoint']['choices'])
        if canonical(regenerated) != canonical(saved['checkpoint']):
            raise ValueError('lifecycle checkpoint replay mismatch')
    if engine.summary() != manifest['summary']:
        raise ValueError('lifecycle final summary replay mismatch')
    if manifest['status'] == 'completed' and engine.index != len(engine.schedule):
        raise ValueError('incomplete horizon labeled complete')
    if manifest['mode'] == 'jev' and verified_calls != manifest['model_calls']:
        raise ValueError('lifecycle call count replay mismatch')
    return {'verified_steps': manifest['completed_steps'], 'last_second': engine.summary()['last_second'], 'model_calls': 0}
