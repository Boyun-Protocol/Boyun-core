"""Bounded scheduling of declared responses over evaluated condition firings.

Reservations move funds once, from balance to hold and then to spent or back. A pause
becomes effective only after its declared latency, so commitments that land first are
unavoidable rather than erased. A human-decision response suspends new discretionary
responses until a supplied decision arrives, and a confirmed stage transition can
invalidate an action that was scheduled under the previous stage.
"""
from __future__ import annotations

from copy import deepcopy
import heapq
import json

from .contingent_worlds import (_ENGINE_SHA256, _boolean, _canonical, _choice, _digest, _error,
                                _id, _integer, _list, _number, _object, _stage_at, _text, _unique,
                                evaluate_contingent_world, validate_contingent_world)

_LIMITS = {
    'input_bytes': 524288, 'output_bytes': 16777216, 'resources': 64, 'responses': 64,
    'commitments': 256, 'decisions': 64, 'reservations_per_response': 32,
    'responses_per_condition': 16, 'events': 10000, 'schedule': 10000,
    'priority': 10**6, 'amount': 10**12, 'seconds': 10**12,
}
_KINDS = {'automatic', 'human_decision', 'do_nothing', 'cancel_pending'}
_EVENT_ORDER = {'commitment': 0, 'firing': 1, 'cancel': 2, 'execution': 3, 'decision': 4}
_RECORD_KINDS = {'scheduled', 'executed', 'awaiting_user', 'approved', 'invalidated',
                 'released', 'no_action', 'unfunded', 'deferred_awaiting_decision',
                 'unmatched_decision', 'decision_unfunded', 'failed_execution',
                 'pending_at_horizon', 'commitment', 'unfunded_commitment', 'cancelled_commitment',
                 'halt_effective', 'cancelled_pending', 'resume_effective', 'cancel_effective'}
_LIMITATIONS = [
    'Responses are declared integers in declared units; nothing here is a venue order, fill or settlement.',
    'Commitment latencies and halt effects are author-declared models of an external service, not verified contract behavior.',
    'A human-decision record is a supplied decision, never an inferred or auto-completed user choice.',
    'Responses are selected only from the reviewed ordering for the firing condition.',
    'Balances conserve declared inputs; they do not prove real cash availability, fees or withdrawability.',
    'Runs are deterministic from declared input; replay proves internal consistency only.',
]


def _validate_resource(value, path):
    _object(value, {'id', 'unit', 'initial'}, path)
    _id(value['id'], path + '.id')
    _text(value['unit'], path + '.unit', 64)
    return {'id': value['id'], 'unit': value['unit'],
            'initial': _integer(value['initial'], path + '.initial', 0, _LIMITS['amount'])}


def _validate_response(value, path, resources, actors):
    _object(value, {'id', 'label', 'actor_id', 'kind', 'priority', 'reservations', 'effects',
                    'decision_seconds', 'execution_seconds', 'halts_commitments',
                    'resumes_commitments', 'cancels', 'invalidate_on_stage_change',
                    'explanation'}, path)
    kind = _choice(value['kind'], _KINDS, path + '.kind', 'unsupported response kind')
    _text(value['label'], path + '.label', 256)
    if _id(value['actor_id'], path + '.actor_id') not in actors:
        _error(path + '.actor_id', 'unknown actor reference')
    _integer(value['priority'], path + '.priority', 0, _LIMITS['priority'])
    _boolean(value['halts_commitments'], path + '.halts_commitments')
    _boolean(value['resumes_commitments'], path + '.resumes_commitments')
    _boolean(value['invalidate_on_stage_change'], path + '.invalidate_on_stage_change')
    if value['halts_commitments'] and value['resumes_commitments']:
        _error(path, 'one response cannot both halt and resume commitments')
    _text(value['explanation'], path + '.explanation')
    cancels = []
    for j, target in enumerate(_list(value['cancels'], path + '.cancels',
                                     _LIMITS['responses_per_condition'])):
        target = _id(target, path + f'.cancels[{j}]')
        if target in cancels:
            _error(path + f'.cancels[{j}]', 'duplicate cancellation target')
        cancels.append(target)
    if kind == 'cancel_pending':
        if not cancels:
            _error(path + '.cancels', 'cancel_pending must name at least one target response')
        if value['reservations'] or value['effects'] or value['halts_commitments'] \
                or value['resumes_commitments'] or value['invalidate_on_stage_change']:
            _error(path, 'cancel_pending cannot reserve, affect, halt, resume or invalidate')
    elif cancels:
        _error(path + '.cancels', 'only cancel_pending may declare cancellation targets')
    reserved, effected = [], []
    for j, item in enumerate(_list(value['reservations'], path + '.reservations',
                                   _LIMITS['reservations_per_response'])):
        rpath = path + f'.reservations[{j}]'
        _object(item, {'resource_id', 'amount'}, rpath)
        resource = _id(item['resource_id'], rpath + '.resource_id')
        if resource not in resources:
            _error(rpath + '.resource_id', 'unknown resource reference')
        if resource in reserved:
            _error(rpath, 'resource may be reserved only once per response')
        reserved.append(resource)
        _integer(item['amount'], rpath + '.amount', 1, _LIMITS['amount'])
    for j, item in enumerate(_list(value['effects'], path + '.effects',
                                   _LIMITS['reservations_per_response'])):
        epath = path + f'.effects[{j}]'
        _object(item, {'resource_id', 'delta'}, epath)
        resource = _id(item['resource_id'], epath + '.resource_id')
        if resource not in resources:
            _error(epath + '.resource_id', 'unknown resource reference')
        if resource in effected:
            _error(epath, 'resource may be affected only once per response')
        effected.append(resource)
        _integer(item['delta'], epath + '.delta', -_LIMITS['amount'], _LIMITS['amount'])
    decision = _integer(value['decision_seconds'], path + '.decision_seconds', 0, _LIMITS['seconds'])
    execution = _integer(value['execution_seconds'], path + '.execution_seconds', 0, _LIMITS['seconds'])
    if kind == 'do_nothing' and (value['reservations'] or value['effects']
                                 or decision or execution
                                 or value['halts_commitments']
                                 or value['invalidate_on_stage_change']):
        _error(path, 'do_nothing cannot reserve, affect, delay, halt or invalidate')
    return {'id': _id(value['id'], path + '.id'), 'label': value['label'],
            'actor_id': value['actor_id'], 'kind': kind, 'priority': value['priority'],
            'reservations': deepcopy(value['reservations']), 'effects': deepcopy(value['effects']),
            'decision_seconds': decision, 'execution_seconds': execution,
            'halts_commitments': value['halts_commitments'],
            'resumes_commitments': value['resumes_commitments'], 'cancels': cancels,
            'invalidate_on_stage_change': value['invalidate_on_stage_change'],
            'explanation': value['explanation']}


def validate_contingent_policy(package):
    """Return an independent validated plan; raise ValueError on unsafe or inconsistent data."""
    _canonical(package, _LIMITS['input_bytes'])
    _object(package, {'schema_version', 'id', 'objective', 'world', 'resources', 'responses',
                      'policy', 'commitments', 'decisions', 'assumptions'}, '$')
    if package['schema_version'] != 'contingent-policy.v1':
        _error('$.schema_version', 'unsupported contingent-policy schema')
    _id(package['id'], '$.id')
    _text(package['objective'], '$.objective')
    world = validate_contingent_world(package['world'])
    resources, seen = {}, set()
    for index, item in enumerate(_list(package['resources'], '$.resources', _LIMITS['resources'])):
        resource = _validate_resource(item, f'$.resources[{index}]')
        if resource['id'] in seen:
            _error(f'$.resources[{index}]', 'duplicate identifier')
        seen.add(resource['id'])
        resources[resource['id']] = resource
    actors = {actor['id'] for actor in world['actors']}
    responses, seen = {}, set()
    priorities = {}
    for index, item in enumerate(_list(package['responses'], '$.responses',
                                       _LIMITS['responses'], 1)):
        response = _validate_response(item, f'$.responses[{index}]', resources, actors)
        if response['id'] in seen:
            _error(f'$.responses[{index}]', 'duplicate identifier')
        if response['priority'] in priorities:
            _error(f'$.responses[{index}].priority',
                   f'priority already declared by {priorities[response["priority"]]}')
        seen.add(response['id'])
        priorities[response['priority']] = response['id']
        responses[response['id']] = response
    triggers = list(world['conditions']) + list(world['composites'])
    if type(package['policy']) is not dict or set(package['policy']) != set(triggers):
        _error('$.policy', 'one ordering is required for every declared condition and composite, '
                          'and no others')
    for response in responses.values():
        for target in response['cancels']:
            if target == response['id']:
                _error('$.responses', f'{response["id"]} cannot cancel itself')
            if target not in responses:
                _error('$.responses', f'{response["id"]} cancels an unknown response {target}')
    policy = {}
    for index, key in enumerate(triggers):
        ordering = _list(package['policy'][key], f'$.policy[{index}]',
                         _LIMITS['responses_per_condition'], 1)
        declared = set()
        for item in ordering:
            choice = _id(item, f'$.policy[{index}]')
            if choice not in responses or choice in declared:
                _error(f'$.policy[{index}]', 'unknown or duplicate response reference')
            declared.add(choice)
        policy[key] = ordering
    commitments, seen = [], set()
    for index, item in enumerate(_list(package['commitments'], '$.commitments',
                                       _LIMITS['commitments'])):
        path = f'$.commitments[{index}]'
        _object(item, {'id', 'resource_id', 'amount', 'requested_at_seconds',
                       'commits_at_seconds'}, path)
        commitment_id = _unique(item, seen, path)
        if _id(item['resource_id'], path + '.resource_id') not in resources:
            _error(path + '.resource_id', 'unknown resource reference')
        requested = _number(item['requested_at_seconds'], {}, path + '.requested_at_seconds',
                            0, world['end_seconds'])
        commits = _number(item['commits_at_seconds'], {}, path + '.commits_at_seconds',
                          requested, world['end_seconds'])
        _integer(item['amount'], path + '.amount', 1, _LIMITS['amount'])
        commitments.append({'id': commitment_id, 'resource_id': item['resource_id'],
                            'amount': item['amount'], 'requested_at_seconds': requested,
                            'commits_at_seconds': commits})
    decisions, seen_pairs = [], set()
    for index, item in enumerate(_list(package['decisions'], '$.decisions', _LIMITS['decisions'])):
        path = f'$.decisions[{index}]'
        _object(item, {'at_seconds', 'condition_id', 'response_id'}, path)
        _integer(item['at_seconds'], path + '.at_seconds', 0, world['end_seconds'])
        condition_id = _id(item['condition_id'], path + '.condition_id')
        if condition_id not in policy:
            _error(path + '.condition_id', 'decision references an undeclared condition')
        response_id = _id(item['response_id'], path + '.response_id')
        if response_id not in policy[condition_id]:
            _error(path + '.response_id', 'decision must choose a reviewed response for the condition')
        pair = (item['at_seconds'], condition_id)
        if pair in seen_pairs:
            _error(path, 'only one decision may resolve a condition at a given second')
        seen_pairs.add(pair)
        decisions.append(deepcopy(item))
    assumptions = set()
    for index, item in enumerate(_list(package['assumptions'], '$.assumptions', 128)):
        _text(item, f'$.assumptions[{index}]')
        assumptions.add(item)
    return {'schema_version': 'contingent-policy.v1', 'id': package['id'],
            'objective': package['objective'], 'world': world, 'resources': resources,
            'responses': responses, 'policy': policy, 'commitments': commitments,
            'decisions': sorted(deepcopy(decisions), key=lambda d: (d['at_seconds'], d['condition_id'])),
            'assumptions': list(package['assumptions']),
            'world_sha256': _digest(package['world'])}


def _push(queue, order, at, kind, payload):
    heapq.heappush(queue, (at, _EVENT_ORDER[kind], kind, order, payload))


def _reserve(state, response):
    """Move funds from balance to hold; return None when the response is affordable."""
    held = []
    for item in response['reservations']:
        resource = state[item['resource_id']]
        if item['amount'] > resource['balance']:
            for taken in held:
                state[taken['resource_id']]['balance'] += taken['amount']
                state[taken['resource_id']]['held'] -= taken['amount']
            return None
        resource['balance'] -= item['amount']
        resource['held'] += item['amount']
        held.append(item)
    return held


def _release(state, reservation):
    resource = state[reservation['resource_id']]
    resource['balance'] += reservation['amount']
    resource['held'] -= reservation['amount']


def _consume(state, reservation):
    resource = state[reservation['resource_id']]
    resource['held'] -= reservation['amount']
    resource['spent'] += reservation['amount']


def _invariant(state):
    for resource in state.values():
        if resource['balance'] < 0 or resource['held'] < 0 or resource['spent'] < 0:
            return False
        if resource['initial'] != resource['balance'] + resource['held'] + resource['spent'] \
                - resource['effects']:
            return False
    return True


def run_contingent_policy(package):
    """Schedule reviewed responses over firings; every blocked path stays visible."""
    plan = validate_contingent_policy(package)
    world = plan['world']
    evaluation = evaluate_contingent_world(deepcopy(package['world']))
    state = {key: {'unit': item['unit'], 'initial': item['initial'], 'balance': item['initial'],
                   'held': 0, 'spent': 0, 'effects': 0}
             for key, item in plan['resources'].items()}
    queue, schedule, counter = [], [], 0
    precedence = {key: min(plan['responses'][item]['priority'] for item in plan['policy'][key])
                  for key in plan['policy']}
    for firing in evaluation['firings']:
        _push(queue, (precedence[firing['condition_id']], firing['condition_id']),
              firing['effective_at_seconds'], 'firing', firing)
    for commitment in plan['commitments']:
        _push(queue, commitment['id'], commitment['commits_at_seconds'], 'commitment', commitment)
    for decision in plan['decisions']:
        _push(queue, decision['condition_id'], decision['at_seconds'], 'decision', decision)
    awaiting, deferred, halted, pending = {}, [], False, {}
    counts = {kind: 0 for kind in _RECORD_KINDS}

    def record(at, kind, **fields):
        nonlocal counter
        counter += 1
        if counter > _LIMITS['events'] or len(schedule) > _LIMITS['schedule']:
            _error('$.responses', 'run record count exceeds limit')
        if not _invariant(state):
            _error('$.resources', 'resource conservation failed')
        counts[kind] += 1
        schedule.append({'at_seconds': at, 'kind': kind, **fields})

    def stage_of(at):
        return _stage_at(world['timeline'], world['lifecycle']['initial_stage_id'], at)

    def schedule_response(at, condition_id, response_id, kind_record):
        response = plan['responses'][response_id]
        hold = _reserve(state, response)
        if hold is None:
            return False
        executes_at = at + response['decision_seconds'] + response['execution_seconds']
        if executes_at > world['end_seconds']:
            for item in hold:
                _release(state, item)
            record(at, 'pending_at_horizon', condition_id=condition_id, response_id=response_id)
            return True
        token = f'{condition_id}@{at}@{response_id}'
        if response['kind'] == 'cancel_pending':
            record(at, kind_record, condition_id=condition_id, response_id=response_id,
                   executes_at_seconds=executes_at, cancels=deepcopy(response['cancels']))
            _push(queue, token, executes_at, 'cancel', {'condition_id': condition_id,
                                                        'response_id': response_id})
            return True
        pending[token] = {'condition_id': condition_id, 'response_id': response_id,
                          'reservations': hold, 'scheduled_at_seconds': at,
                          'scheduled_stage': stage_of(at), 'execution_stage': stage_of(executes_at)}
        record(at, kind_record, condition_id=condition_id, response_id=response_id,
               executes_at_seconds=executes_at, reservations=deepcopy(response['reservations']))
        _push(queue, token, executes_at, 'execution', token)
        return True

    def attempt(at, firing):
        """Choose the first feasible reviewed response for one firing."""
        condition_id = firing['condition_id']
        if awaiting:
            deferred.append(firing)
            record(at, 'deferred_awaiting_decision', condition_id=condition_id)
            return
        for response_id in plan['policy'][condition_id]:
            response = plan['responses'][response_id]
            if response['kind'] == 'do_nothing':
                record(at, 'no_action', condition_id=condition_id, response_id=response_id)
                return
            if response['kind'] == 'human_decision':
                awaiting[condition_id] = {'firing': firing, 'response_id': response_id,
                                          'requested_at_seconds': at}
                record(at, 'awaiting_user', condition_id=condition_id, response_id=response_id)
                return
            if schedule_response(at, condition_id, response_id, 'scheduled'):
                return
        record(at, 'unfunded', condition_id=condition_id,
               ordering=deepcopy(plan['policy'][condition_id]))

    while queue:
        at, _order, kind, token, payload = heapq.heappop(queue)
        if kind == 'commitment':
            if halted:
                record(at, 'cancelled_commitment', commitment_id=payload['id'],
                       resource_id=payload['resource_id'], amount=payload['amount'])
            elif state[payload['resource_id']]['balance'] >= payload['amount']:
                state[payload['resource_id']]['balance'] -= payload['amount']
                state[payload['resource_id']]['spent'] += payload['amount']
                record(at, 'commitment', commitment_id=payload['id'],
                       resource_id=payload['resource_id'], amount=payload['amount'])
            else:
                record(at, 'unfunded_commitment', commitment_id=payload['id'],
                       resource_id=payload['resource_id'], amount=payload['amount'])
        elif kind == 'firing':
            attempt(at, payload)
        elif kind == 'cancel':
            response = plan['responses'][payload['response_id']]
            record(at, 'cancel_effective', condition_id=payload['condition_id'],
                   response_id=payload['response_id'])
            for target in response['cancels']:
                for pending_token in [key for key, action in pending.items()
                                      if action['response_id'] == target]:
                    action = pending.pop(pending_token)
                    for item in action['reservations']:
                        _release(state, item)
                    record(at, 'cancelled_pending', condition_id=action['condition_id'],
                           response_id=target, cancelled_by=payload['response_id'])
        elif kind == 'decision':
            held = awaiting.get(payload['condition_id'])
            if held is None or held['requested_at_seconds'] > at:
                record(at, 'unmatched_decision', condition_id=payload['condition_id'],
                       response_id=payload['response_id'])
                continue
            awaiting.pop(payload['condition_id'])
            if not schedule_response(at, payload['condition_id'], payload['response_id'], 'approved'):
                record(at, 'decision_unfunded', condition_id=payload['condition_id'],
                       response_id=payload['response_id'])
            if not awaiting:
                queued, deferred = deferred, []
                for firing in queued:
                    attempt(at, firing)
        else:
            action = pending.pop(token, None)
            if action is None:
                continue
            response = plan['responses'][action['response_id']]
            if response['invalidate_on_stage_change'] and action['scheduled_stage'] != \
                    action['execution_stage']:
                for item in action['reservations']:
                    _release(state, item)
                record(at, 'invalidated', condition_id=action['condition_id'],
                       response_id=action['response_id'], stage_id=stage_of(at))
                continue
            shortfall = next((item for item in response['effects']
                              if state[item['resource_id']]['balance'] + item['delta'] < 0), None)
            if shortfall is not None:
                for item in action['reservations']:
                    _release(state, item)
                record(at, 'failed_execution', condition_id=action['condition_id'],
                       response_id=action['response_id'], resource_id=shortfall['resource_id'])
                continue
            for item in action['reservations']:
                _consume(state, item)
            for item in response['effects']:
                resource = state[item['resource_id']]
                resource['balance'] += item['delta']
                resource['effects'] += item['delta']
            record(at, 'executed', condition_id=action['condition_id'],
                   response_id=action['response_id'], effects=deepcopy(response['effects']))
            if response['halts_commitments']:
                halted = True
                record(at, 'halt_effective', response_id=action['response_id'])
            if response['resumes_commitments']:
                halted = False
                record(at, 'resume_effective', response_id=action['response_id'])
    if not _invariant(state):
        _error('$.resources', 'resource conservation failed')
    result = {'schema_version': 'contingent-policy-run.v1', 'run_id': plan['id'],
              'objective': plan['objective'], 'world_sha256': plan['world_sha256'],
              'input_sha256': _digest(package), 'engine_sha256': _ENGINE_SHA256,
              'model_calls': 0, 'horizon_seconds': world['end_seconds'],
              'resources': {key: {'unit': value['unit'], 'initial': value['initial'],
                                  'balance': value['balance'], 'held': value['held'],
                                  'spent': value['spent'], 'effects_applied': value['effects']}
                            for key, value in sorted(state.items())},
              'conservation_holds': True, 'outcome_counts': {k: v for k, v in sorted(counts.items()) if v},
              'firings': len(evaluation['firings']),
              'awaiting_user_at_end': sorted(awaiting),
              'deferred_at_end': sorted(firing['condition_id'] for firing in deferred),
              'halted_commitments': halted, 'schedule': schedule,
              'assumptions': plan['assumptions'], 'limitations': list(_LIMITATIONS)}
    if len(json.dumps(result, ensure_ascii=False).encode('utf-8')) > _LIMITS['output_bytes']:
        _error('$.responses', 'run output exceeds limit')
    return result


def verify_contingent_policy_run(run, package):
    """Recompute from declared input and reject any mismatch with the stored run."""
    _canonical(run, _LIMITS['output_bytes'])
    expected = run_contingent_policy(package)
    if run != expected:
        _error('$', 'run does not match deterministic recomputation')
    return deepcopy(expected)


def contingent_policy_capabilities():
    """Publish the declared plan contract without inventing executable values."""
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
            'schema_version': {'type': 'string', 'const': 'contingent-policy.v1'},
            'id': identifier(), 'objective': text(), 'world': {'contract': 'world'},
            'resources': array('resource', _LIMITS['resources']),
            'responses': array('response', _LIMITS['responses'], 1),
            'policy': {'contract': 'policy'},
            'commitments': array('commitment', _LIMITS['commitments']),
            'decisions': array('decision', _LIMITS['decisions']),
            'assumptions': {'type': 'array', 'minimum_items': 0, 'maximum_items': 128,
                            'items': text()},
        }, ['Resource, response and commitment IDs are unique. Response priorities are unique.']),
        'world': {'type': 'object', 'schema': 'contingent-world.v1',
                  'description': 'A complete contingent-world package; its conditions define the '
                                 'policy keys and its actors define the response actor_id values.',
                  'validation': 'Validated by the condition runtime before any response is scheduled.'},
        'resource': record({'id': identifier(), 'unit': text(64),
                            'initial': integer(0, _LIMITS['amount'])},
                           ['A resource is one declared integer pool, e.g. uncommitted USD cents.']),
        'response': record({
            'id': identifier(), 'label': text(256),
            'actor_id': identifier('world actor id'),
            'kind': {'type': 'string', 'enum': sorted(_KINDS)},
            'priority': integer(0, _LIMITS['priority']),
            'reservations': array('reservation', _LIMITS['reservations_per_response']),
            'effects': array('effect', _LIMITS['reservations_per_response']),
            'decision_seconds': integer(0, _LIMITS['seconds']),
            'execution_seconds': integer(0, _LIMITS['seconds']),
            'halts_commitments': {'type': 'boolean'},
            'resumes_commitments': {'type': 'boolean'},
            'cancels': {'type': 'array', 'minimum_items': 0,
                        'maximum_items': _LIMITS['responses_per_condition'], 'unique': True,
                        'items': identifier('response.id, never this response')},
            'invalidate_on_stage_change': {'type': 'boolean'},
            'explanation': text(),
        }, ['priority is unique across responses. Simultaneous firings are attempted in ascending '
            'priority of the highest-priority response listed for each condition, then by condition '
            'id; within one condition the declared list order decides.',
            'A reservation holds funds from scheduling until execution or release.',
            'Effects apply at execution and may be positive or negative.',
            'halts_commitments and resumes_commitments are mutually exclusive; together they make the '
            'gate two-way, so funding can stop and later restart without a new run.',
            'cancel_pending names at least one target response, reserves nothing and takes effect after '
            'its own latency; it releases the targets still pending at that moment.',
            'A cancel effective in the same second as an execution takes effect first, so cancellation '
            'wins that tie by declaration.',
            'decision_seconds plus execution_seconds is the full latency before a response is effective.',
            'A response whose latency would land past the world horizon is recorded pending_at_horizon '
            'and its reservation is released; it is never silently carried over.',
            'While any condition awaits a user decision, later firings are recorded '
            'deferred_awaiting_decision and re-attempted from the decision time once the queue clears.',
            'halts_commitments stops later commitments from executing once this response executes; '
            'already-scheduled work still lands, which is how unavoidable fills are modeled.',
            'do_nothing must reserve, affect, delay, halt and invalidate nothing.']),
        'reservation': record({'resource_id': identifier('resource.id'),
                               'amount': integer(1, _LIMITS['amount'])},
                              ['Each resource may appear at most once per response.']),
        'effect': record({'resource_id': identifier('resource.id'),
                          'delta': integer(-_LIMITS['amount'], _LIMITS['amount'])},
                         ['Each resource may appear at most once per response.']),
        'policy': {'type': 'object', 'keys': identifier('world condition id'),
                   'required_keys': 'Every declared condition and composite exactly once; no other keys.',
                   'values': {'type': 'array', 'minimum_items': 1,
                              'maximum_items': _LIMITS['responses_per_condition'], 'unique': True,
                              'items': identifier('response.id')},
                   'choice_order': 'first_feasible',
                   'exhaustion': 'Record unfunded with the full ordering; never use an unlisted response '
                                 'or drop the firing.'},
        'commitment': record({
            'id': identifier(), 'resource_id': identifier('resource.id'),
            'amount': integer(1, _LIMITS['amount']),
            'requested_at_seconds': integer(0, _LIMITS['seconds']),
            'commits_at_seconds': integer(0, _LIMITS['seconds']),
        }, ['commits_at_seconds >= requested_at_seconds, and both lie inside the world horizon.',
            'A commitment landing before an effective halt is unavoidable; later ones are cancelled.']),
        'decision': record({'at_seconds': integer(0, _LIMITS['seconds']),
                            'condition_id': identifier('world condition id'),
                            'response_id': identifier('response id in that condition ordering')},
                           ['Supplied by the author; the runtime never invents a user decision.',
                            'at_seconds lies inside the world horizon.',
                            'At most one decision may resolve a condition at a given second.']),
    }
    return {
        'schema_version': 'contingent-policy.v1', 'kind': 'declared_response_scheduling',
        'model_calls': 0, 'defaults_or_estimates': None,
        'response_kinds': sorted(_KINDS), 'record_kinds': sorted(_RECORD_KINDS),
        'event_order_at_same_second': ['commitment', 'firing', 'cancel', 'execution', 'decision'],
        'event_order_rationale': 'Money already committed lands first; every trigger at that second '
                                 'is then evaluated before any same-second execution; cancellation '
                                 'takes effect before execution; decisions resolve last.',
        'conservation': 'initial == balance + held + spent - effects_applied for every resource at '
                        'every recorded step; a violated invariant fails the run.',
        'fields': fields, 'result_schema': 'contingent-policy-run.v1',
        'limits': dict(_LIMITS), 'engine_sha256': _ENGINE_SHA256,
        'assumptions': {
            'responses': 'declared_latencies_and_amounts_only_not_venue_orders',
            'decisions': 'supplied_by_author_never_inferred',
            'financial_settlement': 'none; resources are declared integer pools',
            'unknown_values': 'Unresolved paths are recorded as awaiting, deferred, unfunded or failed.',
        },
        'limitations': list(_LIMITATIONS),
    }
