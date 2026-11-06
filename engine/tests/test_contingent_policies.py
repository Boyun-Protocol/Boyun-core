from __future__ import annotations

from copy import deepcopy
import json

import pytest

from decision_lab.contingent_policies import (
    contingent_policy_capabilities, run_contingent_policy, validate_contingent_policy,
    verify_contingent_policy_run,
)


def sample(index, value=500, at=None, available=None):
    at = index * 10 if at is None else at
    return {'id': f's{index}', 'at_seconds': at,
            'available_at_seconds': at if available is None else available,
            'value': value, 'source': 'feed'}


def condition(cid='c1', first=10, last=10, delay=0, stages=None, cadence=10, comparison=None):
    return {'id': cid, 'series_id': 'px', 'stage_ids': stages or ['pre', 'post'],
            'evaluation': {'first_at_seconds': first, 'cadence_seconds': cadence,
                           'last_at_seconds': last},
            'reference': {'kind': 'window_aggregate', 'start_seconds': 0, 'end_seconds': 20,
                          'aggregation': 'maximum'},
            'comparison': comparison or {'mode': 'absolute', 'direction': 'at_or_below',
                                         'threshold_bps': 0, 'threshold': 800},
            'persistence_consecutive': 1, 'persistence_reset': 'on_non_true',
            'cooldown_seconds': 0, 'rearm_requires_false': False,
            'detection_delay_seconds': delay, 'explanation': 'declared test trigger'}


def response(rid, kind='automatic', priority=1, reservations=(), effects=(), decision=0,
             execution=0, halts=False, invalidates=False, resumes=False, cancels=()):
    return {'id': rid, 'label': rid.upper(), 'actor_id': 'founder', 'kind': kind,
            'priority': priority, 'reservations': [dict(item) for item in reservations],
            'effects': [dict(item) for item in effects], 'decision_seconds': decision,
            'execution_seconds': execution, 'halts_commitments': halts,
            'resumes_commitments': resumes, 'cancels': list(cancels),
            'invalidate_on_stage_change': invalidates, 'explanation': f'{rid} is reviewed'}


def plan(responses=None, policy=None, resources=None, commitments=(), decisions=(),
         conditions=None, transitions=(), end=100, stages=None, initial_stage='pre'):
    responses = responses or [response('pause_spend')]
    conditions = conditions or [condition()]
    policy = policy or {item['id']: [responses[0]['id']] for item in conditions}
    return {
        'schema_version': 'contingent-policy.v1', 'id': 'run1',
        'objective': 'Protect net cash without inventing venue behavior',
        'world': {
            'schema_version': 'contingent-world.v1', 'id': 'w1', 'question': 'What does the alert change?',
            'parameters': {}, 'start_seconds': 0, 'end_seconds': end,
            'actors': [{'id': 'founder', 'label': 'Founder', 'role': 'owner'}],
            'series': [{'id': 'px', 'unit': 'usd_milli', 'minimum': 0, 'maximum': 10**9,
                        'stale_after_seconds': 10**6, 'actor_ids': ['founder'],
                        'samples': [sample(0, 500, at=10)]}],
            'lifecycle': {'initial_stage_id': initial_stage,
                          'stages': stages or [{'id': 'pre', 'label': 'Before'},
                                               {'id': 'post', 'label': 'After'}],
                          'transitions': list(transitions)},
            'conditions': conditions, 'composites': [], 'assumptions': ['declared test data']},
        'resources': resources or [{'id': 'cash', 'unit': 'usd_cents', 'initial': 1000}],
        'responses': responses,
        'policy': policy,
        'commitments': [dict(item) for item in commitments],
        'decisions': [dict(item) for item in decisions],
        'assumptions': ['latencies are assumptions, not contract terms']}


def kinds(run, at=None):
    rows = run['schedule'] if at is None else [row for row in run['schedule']
                                               if row['at_seconds'] == at]
    return [row['kind'] for row in rows]


def reserve(amount):
    return [{'resource_id': 'cash', 'amount': amount}]


def test_a_firing_schedules_and_executes_a_funded_response():
    run = plan(responses=[response('pause_spend', reservations=reserve(400))])
    result = run_contingent_policy(run)
    assert kinds(result) == ['scheduled', 'executed']
    assert result['resources']['cash'] == {'unit': 'usd_cents', 'initial': 1000, 'balance': 600,
                                           'held': 0, 'spent': 400, 'effects_applied': 0}
    assert result['conservation_holds'] is True
    assert result['firings'] == 1


def test_detection_delay_defers_when_the_response_can_start():
    run = plan(responses=[response('pause_spend', execution=300)],
               conditions=[condition(delay=1800)], end=3000)
    result = run_contingent_policy(run)
    scheduled = [row for row in result['schedule'] if row['kind'] == 'scheduled'][0]
    assert scheduled['at_seconds'] == 1810
    assert scheduled['executes_at_seconds'] == 2110


def test_reservation_is_held_once_and_a_later_response_cannot_reuse_it():
    rows = [sample(0, 500, at=10), sample(1, 500, at=20)]
    run = plan(responses=[response('spend', reservations=reserve(700))],
               conditions=[condition(last=20, cadence=10)],
               commitments=[])
    run['world']['series'][0]['samples'] = rows
    result = run_contingent_policy(run)
    assert result['outcome_counts'] == {'scheduled': 1, 'executed': 1, 'unfunded': 1}
    assert result['resources']['cash']['balance'] == 300


def test_simultaneous_triggers_resolve_by_declared_priority():
    conditions = [condition('c_fast'), condition('c_slow')]
    low_first = plan(responses=[response('top', priority=1, reservations=reserve(800)),
                                response('bottom', priority=5, reservations=reserve(800))],
                     policy={'c_fast': ['top'], 'c_slow': ['bottom']},
                     conditions=conditions)
    result = run_contingent_policy(low_first)
    assert [row['condition_id'] for row in result['schedule'] if row['kind'] == 'scheduled'] \
        == ['c_fast']
    assert [row['condition_id'] for row in result['schedule'] if row['kind'] == 'unfunded'] \
        == ['c_slow']
    reversed_ = deepcopy(low_first)
    reversed_['responses'] = [response('top', priority=9, reservations=reserve(800)),
                              response('bottom', priority=2, reservations=reserve(800))]
    assert [row['condition_id'] for row in run_contingent_policy(reversed_)['schedule']
            if row['kind'] == 'scheduled'] == ['c_slow']


def test_a_human_decision_suspends_new_discretionary_responses():
    run = plan(responses=[response('ask_owner', kind='human_decision', reservations=reserve(100),
                                   execution=10),
                          response('auto_hold', priority=7)],
               policy={'c1': ['ask_owner'], 'c2': ['auto_hold']},
               conditions=[condition('c1'), condition('c2')],
               decisions=[{'at_seconds': 50, 'condition_id': 'c1', 'response_id': 'ask_owner'}])
    result = run_contingent_policy(run)
    assert result['outcome_counts'] == {'awaiting_user': 1, 'deferred_awaiting_decision': 1,
                                        'approved': 1, 'scheduled': 1, 'executed': 2}
    assert result['awaiting_user_at_end'] == []
    approved = [row for row in result['schedule'] if row['kind'] == 'approved'][0]
    assert approved['at_seconds'] == 50 and approved['executes_at_seconds'] == 60
    deferred = [row for row in result['schedule'] if row['kind'] == 'scheduled'][0]
    assert deferred['at_seconds'] == 50


def test_a_decision_without_an_awaiting_condition_is_recorded_not_applied():
    run = plan(decisions=[{'at_seconds': 5, 'condition_id': 'c1', 'response_id': 'pause_spend'}])
    result = run_contingent_policy(run)
    assert result['outcome_counts']['unmatched_decision'] == 1
    assert kinds(result, 5) == ['unmatched_decision']
    assert 'executed' in kinds(result)


def test_an_unfunded_decision_is_visible_and_releases_the_pause():
    run = plan(responses=[response('ask_owner', kind='human_decision', reservations=reserve(5000))],
               policy={'c1': ['ask_owner']},
               decisions=[{'at_seconds': 50, 'condition_id': 'c1', 'response_id': 'ask_owner'}])
    result = run_contingent_policy(run)
    assert kinds(result) == ['awaiting_user', 'decision_unfunded']
    assert result['resources']['cash']['balance'] == 1000


def test_do_nothing_is_a_reviewed_choice_not_an_absent_action():
    run = plan(responses=[response('stay', kind='do_nothing'),
                          response('spend', priority=4, reservations=reserve(100))],
               policy={'c1': ['stay', 'spend']})
    result = run_contingent_policy(run)
    assert kinds(result) == ['no_action']
    assert result['resources']['cash']['balance'] == 1000


def test_requesting_a_pause_leaves_earlier_commitments_unavoidable():
    run = plan(responses=[response('request_mm_pause', execution=900, halts=True)],
               end=2000,
               commitments=[{'id': 'k1', 'resource_id': 'cash', 'amount': 100,
                             'requested_at_seconds': 0, 'commits_at_seconds': 600},
                            {'id': 'k2', 'resource_id': 'cash', 'amount': 100,
                             'requested_at_seconds': 0, 'commits_at_seconds': 1200}])
    result = run_contingent_policy(run)
    assert 'commitment' in kinds(result, 600)
    assert 'cancelled_commitment' in kinds(result, 1200)
    assert result['halted_commitments'] is True
    assert result['resources']['cash']['spent'] == 100


def test_a_halt_after_the_horizon_cannot_cancel_earlier_commitments_and_releases_funds():
    run = plan(responses=[response('request_mm_pause', reservations=reserve(400),
                                   execution=5000, halts=True)],
               end=2000,
               commitments=[{'id': 'k1', 'resource_id': 'cash', 'amount': 100,
                             'requested_at_seconds': 0, 'commits_at_seconds': 600}])
    result = run_contingent_policy(run)
    assert 'pending_at_horizon' in kinds(result)
    assert 'commitment' in kinds(result, 600)
    assert result['halted_commitments'] is False
    assert result['resources']['cash'] == {'unit': 'usd_cents', 'initial': 1000, 'balance': 900,
                                           'held': 0, 'spent': 100, 'effects_applied': 0}


def test_a_commitment_without_remaining_balance_is_recorded_as_unfunded():
    run = plan(responses=[response('spend', reservations=reserve(850))],
               commitments=[{'id': 'k1', 'resource_id': 'cash', 'amount': 100,
                             'requested_at_seconds': 0, 'commits_at_seconds': 5},
                            {'id': 'k2', 'resource_id': 'cash', 'amount': 100,
                             'requested_at_seconds': 0, 'commits_at_seconds': 20}])
    result = run_contingent_policy(run)
    assert 'commitment' in kinds(result, 5)
    assert 'unfunded_commitment' in kinds(result, 20)
    assert result['resources']['cash'] == {'unit': 'usd_cents', 'initial': 1000, 'balance': 50,
                                           'held': 0, 'spent': 950, 'effects_applied': 0}


def test_stage_transition_invalidates_an_action_scheduled_under_the_old_stage():
    transition = [{'id': 't1', 'from_stage_id': 'pre', 'to_stage_id': 'post',
                   'effective_at_seconds': 20, 'confirmed': True, 'source': 'protocol'}]
    run = plan(responses=[response('staged_exit', reservations=reserve(300), execution=15,
                                  invalidates=True)],
               transitions=transition)
    result = run_contingent_policy(run)
    assert kinds(result) == ['scheduled', 'invalidated']
    assert result['resources']['cash'] == {'unit': 'usd_cents', 'initial': 1000, 'balance': 1000,
                                           'held': 0, 'spent': 0, 'effects_applied': 0}
    unchanged = deepcopy(run)
    unchanged['responses'][0]['invalidate_on_stage_change'] = False
    assert 'executed' in kinds(run_contingent_policy(unchanged))


def test_an_effect_that_would_overdraw_fails_without_spending():
    run = plan(responses=[response('buyback', reservations=reserve(900),
                                   effects=[{'resource_id': 'cash', 'delta': -500}])])
    result = run_contingent_policy(run)
    assert kinds(result) == ['scheduled', 'failed_execution']
    assert result['resources']['cash'] == {'unit': 'usd_cents', 'initial': 1000, 'balance': 1000,
                                           'held': 0, 'spent': 0, 'effects_applied': 0}


def test_a_positive_effect_returns_funds_and_conserves_the_pool():
    run = plan(responses=[response('staged_exit', reservations=reserve(400),
                                   effects=[{'resource_id': 'cash', 'delta': 650}])])
    result = run_contingent_policy(run)
    assert result['resources']['cash'] == {'unit': 'usd_cents', 'initial': 1000, 'balance': 1250,
                                           'held': 0, 'spent': 400, 'effects_applied': 650}
    assert result['conservation_holds'] is True


def test_two_resources_reserve_independently_and_conserve():
    resources = [{'id': 'cash', 'unit': 'usd_cents', 'initial': 1000},
                 {'id': 'reserve_fund', 'unit': 'usd_cents', 'initial': 500}]
    run = plan(resources=resources,
               responses=[response('split', reservations=[{'resource_id': 'cash', 'amount': 600},
                                                          {'resource_id': 'reserve_fund',
                                                           'amount': 100}])])
    result = run_contingent_policy(run)
    assert result['resources']['cash']['spent'] == 600
    assert result['resources']['reserve_fund'] == {'unit': 'usd_cents', 'initial': 500,
                                                   'balance': 400, 'held': 0, 'spent': 100,
                                                   'effects_applied': 0}


def test_partially_unaffordable_response_reserves_nothing():
    run = plan(resources=[{'id': 'cash', 'unit': 'usd_cents', 'initial': 1000},
                          {'id': 'locked', 'unit': 'usd_cents', 'initial': 50}],
               responses=[response('split', reservations=[{'resource_id': 'cash', 'amount': 900},
                                                           {'resource_id': 'locked', 'amount': 500}]),
                          response('fallback', priority=3, reservations=reserve(100))],
               policy={'c1': ['split', 'fallback']})
    result = run_contingent_policy(run)
    assert result['resources']['cash']['balance'] == 900
    assert result['resources']['locked']['balance'] == 50
    assert 'executed' in kinds(result)


def test_run_is_reproducible_and_verifiable():
    run = plan(responses=[response('ask_owner', kind='human_decision', reservations=reserve(200),
                                   execution=5),
                          response('auto_hold', priority=2, reservations=reserve(100))],
               policy={'c1': ['ask_owner'], 'c2': ['auto_hold']},
               conditions=[condition('c1'), condition('c2')],
               decisions=[{'at_seconds': 40, 'condition_id': 'c1', 'response_id': 'ask_owner'}])
    result = run_contingent_policy(run)
    assert json.dumps(result, sort_keys=True) == json.dumps(run_contingent_policy(deepcopy(run)),
                                                            sort_keys=True)
    assert verify_contingent_policy_run(deepcopy(result), run) == result
    tampered = deepcopy(result)
    tampered['resources']['cash']['spent'] += 1
    with pytest.raises(ValueError, match='deterministic recomputation'):
        verify_contingent_policy_run(tampered, run)


def reject(value, message):
    with pytest.raises(ValueError, match=message):
        validate_contingent_policy(value)


def test_validation_rejects_unsafe_or_inconsistent_plans():
    reject({**plan(), 'extra': 1}, 'exactly the declared fields')
    reject({**plan(), 'schema_version': 'contingent-policy.v2'}, 'unsupported contingent-policy schema')
    reject({**plan(), 'resources': [{'id': 'cash', 'unit': 'u', 'initial': 10},
                                    {'id': 'cash', 'unit': 'u', 'initial': 5}]},
           'duplicate identifier')
    reject({**plan(), 'responses': [response('a', priority=1), response('b', priority=1)]},
           'priority already declared')
    reject({**plan(), 'responses': [response('a', reservations=reserve(10)),
                                    response('b', priority=2, reservations=reserve(20))],
            'policy': {'c1': ['a', 'ghost']}}, 'unknown or duplicate response reference')
    reject({**plan(), 'policy': {'c1': ['pause_spend'], 'c9': ['pause_spend']}},
           'one ordering is required for every declared condition')
    reject({**plan(), 'policy': {'c1': []}}, 'invalid list type or size')
    reject({**plan(), 'responses': [response('a', kind='do_nothing', reservations=reserve(10))]},
           'do_nothing cannot reserve')
    reject({**plan(), 'responses': [response('a', kind='guess')]}, 'unsupported response kind')
    reject({**plan(), 'responses': [{**response('a'), 'kind': ['automatic']}]},
           'unsupported response kind')
    reject({**plan(), 'responses': [{**response('a'), 'kind': {'automatic': 1}}]},
           'unsupported response kind')
    reject({**plan(), 'responses': [{**response('a'), 'actor_id': 'stranger'}]},
           'unknown actor reference')
    reject({**plan(), 'responses': [response('a', reservations=[{'resource_id': 'ghost',
                                                                  'amount': 1}])]},
           'unknown resource reference')
    reject({**plan(), 'responses': [response('a', reservations=[{'resource_id': 'cash', 'amount': 1},
                                                                {'resource_id': 'cash',
                                                                 'amount': 2}])]},
           'reserved only once per response')
    reject({**plan(), 'responses': [response('a', effects=[{'resource_id': 'ghost',
                                                             'delta': 1}])]},
           'unknown resource reference')
    reject({**plan(), 'commitments': [{'id': 'k', 'resource_id': 'cash', 'amount': 1,
                                       'requested_at_seconds': 10, 'commits_at_seconds': 5}]},
           'integer outside bounds')
    reject({**plan(), 'decisions': [{'at_seconds': 1, 'condition_id': 'c9',
                                     'response_id': 'pause_spend'}]},
           'undeclared condition')
    reject({**plan(), 'decisions': [{'at_seconds': 1, 'condition_id': 'c1',
                                     'response_id': 'not_reviewed'}]},
           'must choose a reviewed response')
    reject({**plan(), 'decisions': [{'at_seconds': 1, 'condition_id': 'c1',
                                     'response_id': 'pause_spend'},
                                    {'at_seconds': 1, 'condition_id': 'c1',
                                     'response_id': 'pause_spend'}]},
           'only one decision may resolve')
    reject({**plan(), 'commitments': [{'id': 'k', 'resource_id': 'cash', 'amount': 1,
                                       'requested_at_seconds': 0, 'commits_at_seconds': 5000}]},
           'integer outside bounds')
    reject({**plan(), 'decisions': [{'at_seconds': 5000, 'condition_id': 'c1',
                                     'response_id': 'pause_spend'}]},
           'integer outside bounds')
    broken_world = plan()
    broken_world['world']['series'][0]['samples'][0]['value'] = 'high'
    reject(broken_world, 'invalid integer type')


def recovery():
    return {'mode': 'absolute', 'direction': 'at_or_above', 'threshold_bps': 0, 'threshold': 0}


def test_a_contrary_firing_defers_the_remaining_exit_and_releases_funds():
    run = plan(responses=[response('exit_tranche', reservations=reserve(300), execution=1800),
                          response('hold_and_watch', kind='cancel_pending', priority=2,
                                   cancels=['exit_tranche'])],
               policy={'c_decay': ['exit_tranche'], 'c_recover': ['hold_and_watch']},
               conditions=[condition('c_decay', first=10),
                           condition('c_recover', first=20, last=20, comparison=recovery())],
               end=3000)
    result = run_contingent_policy(run)
    assert result['outcome_counts'] == {'scheduled': 2, 'cancel_effective': 1,
                                        'cancelled_pending': 1}
    assert result['resources']['cash'] == {'unit': 'usd_cents', 'initial': 1000, 'balance': 1000,
                                           'held': 0, 'spent': 0, 'effects_applied': 0}


def test_a_late_cancel_does_not_undo_a_fill_that_already_landed():
    run = plan(responses=[response('exit_tranche', reservations=reserve(300), execution=600),
                          response('hold_and_watch', kind='cancel_pending', priority=2,
                                   cancels=['exit_tranche'], execution=1900)],
               policy={'c_decay': ['exit_tranche'], 'c_recover': ['hold_and_watch']},
               conditions=[condition('c_decay', first=10),
                           condition('c_recover', first=20, last=20, comparison=recovery())],
               end=3000)
    result = run_contingent_policy(run)
    assert 'executed' in kinds(result)
    assert 'cancelled_pending' not in kinds(result)
    assert result['resources']['cash']['spent'] == 300


def test_an_immediate_cancel_wins_the_same_second():
    run = plan(responses=[response('exit_tranche', reservations=reserve(300)),
                          response('hold_and_watch', kind='cancel_pending', priority=2,
                                   cancels=['exit_tranche'])],
               policy={'c_decay': ['exit_tranche'], 'c_recover': ['hold_and_watch']},
               conditions=[condition('c_decay', first=10),
                           condition('c_recover', first=10, comparison=recovery())])
    result = run_contingent_policy(run)
    assert 'cancelled_pending' in kinds(result)
    assert 'executed' not in kinds(result)
    assert result['resources']['cash']['balance'] == 1000


def test_the_funding_gate_can_resume_after_a_halt():
    run = plan(responses=[response('halt_mm', halts=True),
                          response('resume_mm', resumes=True, priority=2)],
               policy={'c_halt': ['halt_mm'], 'c_resume': ['resume_mm']},
               conditions=[condition('c_halt', first=10),
                           condition('c_resume', first=30, last=30, comparison=recovery())],
               commitments=[{'id': 'k1', 'resource_id': 'cash', 'amount': 100,
                             'requested_at_seconds': 0, 'commits_at_seconds': 20},
                            {'id': 'k2', 'resource_id': 'cash', 'amount': 100,
                             'requested_at_seconds': 0, 'commits_at_seconds': 40}])
    result = run_contingent_policy(run)
    assert 'cancelled_commitment' in kinds(result, 20)
    assert 'resume_effective' in kinds(result, 30)
    assert 'commitment' in kinds(result, 40)
    assert result['halted_commitments'] is False
    assert result['resources']['cash']['spent'] == 100


def test_cancellation_plan_is_validated():
    base = plan(responses=[response('exit_tranche', reservations=reserve(10)),
                           response('hold', kind='cancel_pending', priority=2,
                                    cancels=['exit_tranche'])],
                policy={'c1': ['exit_tranche'], 'c2': ['hold']},
                conditions=[condition('c1'), condition('c2')])
    validate_contingent_policy(base)
    reject({**base, 'responses': [{**base['responses'][1], 'cancels': []}]},
           'must name at least one target')
    reject({**base, 'responses': [base['responses'][0],
                                  {**base['responses'][1], 'cancels': ['ghost']}]},
           'cancels an unknown response')
    reject({**base, 'responses': [base['responses'][0],
                                  {**base['responses'][1], 'cancels': ['hold']}]},
           'cannot cancel itself')
    reject({**base, 'responses': [base['responses'][0],
                                  {**base['responses'][1], 'cancels': ['exit_tranche'] * 2}]},
           'duplicate cancellation target')
    reject({**base, 'responses': [base['responses'][0],
                                  {**base['responses'][1], 'reservations': reserve(5)}]},
           'cancel_pending cannot reserve')
    reject({**base, 'responses': [base['responses'][0],
                                  {**base['responses'][1], 'halts_commitments': True}]},
           'cancel_pending cannot reserve')
    reject({**base, 'responses': [{**base['responses'][0], 'cancels': ['hold']},
                                  base['responses'][1]]},
           'only cancel_pending may declare cancellation targets')
    reject({**base, 'responses': [{**base['responses'][0], 'halts_commitments': True,
                                   'resumes_commitments': True},
                                  base['responses'][1]]},
           'cannot both halt and resume')


def test_capabilities_publish_the_plan_contract():
    capabilities = contingent_policy_capabilities()
    assert capabilities['model_calls'] == 0
    assert capabilities['response_kinds'] == ['automatic', 'cancel_pending', 'do_nothing',
                                              'human_decision']
    assert capabilities['event_order_at_same_second'] == ['commitment', 'firing', 'cancel',
                                                          'execution', 'decision']
    names = set(capabilities['fields'])

    def walk(node):
        if type(node) is dict:
            if 'contract' in node:
                assert node['contract'] in names, node['contract']
            for child in node.values():
                walk(child)
        elif type(node) is list:
            for child in node:
                walk(child)

    walk(capabilities['fields'])
    assert any('venue order' in item for item in capabilities['limitations'])
    assert 'conservation' in capabilities


def test_run_result_declares_no_inference_and_no_settlement():
    result = run_contingent_policy(plan())
    assert result['model_calls'] == 0
    assert result['engine_sha256']
    assert result['world_sha256']
    assert any('not a venue order' in item or 'venue order' in item for item in result['limitations'])
    assert any('never an inferred' in item or 'supplied decision' in item
               for item in result['limitations'])


def two_feed_plan(price_holds):
    """Volume exits, price decides whether the deferral applies (Q19 conjunction)."""
    def feed(sid, unit, rows):
        return {'id': sid, 'unit': unit, 'minimum': 0, 'maximum': 10**9,
                'stale_after_seconds': 10**6, 'actor_ids': ['founder'],
                'samples': [{'id': f'{sid}{i}', 'at_seconds': at,
                             'available_at_seconds': at, 'value': value, 'source': 'feed'}
                            for i, (at, value) in enumerate(rows)]}

    def trigger(cid, series_id, mode, direction, threshold, first, last, bps=0):
        return {'id': cid, 'series_id': series_id, 'stage_ids': ['pre', 'post'],
                'evaluation': {'first_at_seconds': first, 'cadence_seconds': 10,
                               'last_at_seconds': last},
                'reference': {'kind': 'window_aggregate', 'start_seconds': 0, 'end_seconds': 20,
                              'aggregation': 'maximum'},
                'comparison': {'mode': mode, 'direction': direction, 'threshold_bps': bps,
                               'threshold': threshold},
                'persistence_consecutive': 1, 'persistence_reset': 'on_non_true',
                'cooldown_seconds': 0, 'rearm_requires_false': False,
                'detection_delay_seconds': 0, 'explanation': 'declared'}

    return {
        'schema_version': 'contingent-policy.v1', 'id': 'q19', 'objective': 'exit only if buying truly fades',
        'world': {
            'schema_version': 'contingent-world.v1', 'id': 'w', 'question': 'when to exit?',
            'parameters': {}, 'start_seconds': 0, 'end_seconds': 3000,
            'actors': [{'id': 'founder', 'label': 'F', 'role': 'owner'}],
            'series': [feed('vol', 'usd_volume', [(10, 1000), (20, 200)]),
                       feed('px', 'usd_milli', [(10, 1000), (20, 1000)])],
            'lifecycle': {'initial_stage_id': 'pre',
                          'stages': [{'id': 'pre', 'label': 'P'}, {'id': 'post', 'label': 'Q'}],
                          'transitions': []},
            'conditions': [trigger('c_exit', 'vol', 'absolute', 'at_or_below', 250, 20, 20),
                           trigger('c_vol_back', 'vol', 'absolute', 'at_or_above', 250, 20, 20),
                           trigger('c_price_hold', 'px', 'absolute',
                                   'at_or_above' if price_holds else 'at_or_below', 500, 20, 20)],
            'composites': [{'id': 'c_defer', 'all_of': ['c_vol_back', 'c_price_hold'],
                            'stage_ids': ['pre', 'post'],
                            'evaluation': {'first_at_seconds': 20, 'cadence_seconds': 10,
                                           'last_at_seconds': 20},
                            'persistence_consecutive': 1, 'persistence_reset': 'on_non_true',
                            'cooldown_seconds': 0, 'rearm_requires_false': False,
                            'detection_delay_seconds': 0, 'explanation': 'conjunction'}],
            'assumptions': ['declared feeds']},
        'resources': [{'id': 'cash', 'unit': 'usd_cents', 'initial': 1000}],
        'responses': [response('exit_tranche', reservations=reserve(250), execution=600),
                      response('hold_and_watch', kind='cancel_pending', priority=2,
                               cancels=['exit_tranche'])],
        'policy': {'c_exit': ['exit_tranche'], 'c_vol_back': ['hold_and_watch'],
                   'c_price_hold': ['hold_and_watch'], 'c_defer': ['hold_and_watch']},
        'commitments': [], 'decisions': [], 'assumptions': ['declared']}


def test_deferral_needs_volume_and_price_together():
    deferring = run_contingent_policy(two_feed_plan(price_holds=True))
    assert 'cancelled_pending' in kinds(deferring)
    assert deferring['resources']['cash']['balance'] == 1000
    exiting = run_contingent_policy(two_feed_plan(price_holds=False))
    assert 'cancelled_pending' not in kinds(exiting)
    assert 'executed' in kinds(exiting)
    assert exiting['resources']['cash']['spent'] == 250
