from __future__ import annotations

from copy import deepcopy
import json

import pytest

from decision_lab.contingent_worlds import (
    contingent_world_capabilities, evaluate_contingent_world, validate_contingent_world,
    verify_contingent_evaluation,
)


def sample(index, value, at=None, available=None):
    at = index * 10 if at is None else at
    return {'id': f's{index}', 'at_seconds': at,
            'available_at_seconds': at if available is None else available,
            'value': value, 'source': f'src-{index}'}


def world(series=None, conditions=None, transitions=None, stages=None, initial='pre',
          start=0, end=100):
    return {
        'schema_version': 'contingent-world.v1', 'id': 'w1', 'question': 'When does the alert fire?',
        'parameters': {}, 'start_seconds': start, 'end_seconds': end,
        'actors': [{'id': 'founder', 'label': 'Founder', 'role': 'owner'}],
        'series': [{'id': 'px', 'unit': 'usd_milli', 'minimum': 0, 'maximum': 10**9,
                    'stale_after_seconds': 10**6, 'actor_ids': ['founder'],
                    'samples': series or [sample(0, 1000)]}],
        'lifecycle': {'initial_stage_id': initial,
                      'stages': stages or [{'id': 'pre', 'label': 'Before migration'},
                                           {'id': 'post', 'label': 'After migration'}],
                      'transitions': transitions or []},
        'conditions': conditions or [], 'composites': [], 'assumptions': ['declared sample data only']}


def condition(cid='c1', series_id='px', stages=None, first=10, cadence=10, last=None,
              reference=None, comparison=None, persistence=1, reset='on_non_true',
              cooldown=0, rearm=False, delay=0):
    return {'id': cid, 'series_id': series_id, 'stage_ids': stages or ['pre', 'post'],
            'evaluation': {'first_at_seconds': first, 'cadence_seconds': cadence,
                           'last_at_seconds': last},
            'reference': reference or {'kind': 'window_aggregate', 'start_seconds': 0,
                                       'end_seconds': 20, 'aggregation': 'maximum'},
            'comparison': comparison or {'mode': 'ratio_bps', 'direction': 'at_or_below',
                                         'threshold_bps': 8000, 'threshold': 0},
            'persistence_consecutive': persistence, 'persistence_reset': reset,
            'cooldown_seconds': cooldown, 'rearm_requires_false': rearm,
            'detection_delay_seconds': delay, 'explanation': 'declared test condition'}


def absolute(value, direction='at_or_below'):
    return {'mode': 'absolute', 'direction': direction, 'threshold_bps': 0, 'threshold': value}


def counts(result, cid='c1'):
    return result['conditions'][cid]['outcome_counts']


def test_exact_boundary_fires_on_equality():
    rows = [sample(0, 1000), sample(1, 800, at=10)]
    prior = {'kind': 'prior_sample_window', 'window_seconds': 10, 'tolerance_seconds': 0}
    result = evaluate_contingent_world(world(series=rows, end=10,
                                              conditions=[condition(reference=prior, last=10)]))
    assert result['firings'][0]['current_value'] == 800
    assert result['firings'][0]['reference_value'] == 1000
    assert counts(result)['fired'] == 1


def test_one_milliabove_boundary_does_not_fire():
    prior = {'kind': 'prior_sample_window', 'window_seconds': 10, 'tolerance_seconds': 0}
    rows = [sample(0, 1000), sample(1, 801, at=10)]
    result = evaluate_contingent_world(world(series=rows, end=10,
                                             conditions=[condition(reference=prior, last=10)]))
    assert result['firings'] == []
    assert counts(result)['false'] == 1


def test_cadence_and_reference_window_are_separate_controls():
    rows = [sample(0, 1000, at=0), sample(1, 500, at=15)]
    prior = {'kind': 'prior_sample_window', 'window_seconds': 10, 'tolerance_seconds': 10}
    result = evaluate_contingent_world(world(series=rows, end=40,
                                             conditions=[condition(reference=prior, first=15,
                                                                   cadence=5, last=35)]))
    assert result['conditions']['c1']['ticks'] == 5
    assert counts(result) == {'fired': 2, 'false': 3}
    assert [f['evaluated_at_seconds'] for f in result['firings']] == [15, 20]


def test_missing_reference_is_unknown_not_a_non_event():
    rows = [sample(0, 500, at=100)]
    prior = {'kind': 'prior_sample_window', 'window_seconds': 10, 'tolerance_seconds': 0}
    result = evaluate_contingent_world(world(series=rows, start=100, end=110,
                                             conditions=[condition(reference=prior, first=100,
                                                                   last=100)]))
    assert counts(result) == {'unknown_reference': 1}
    assert result['firings'] == []


def test_gap_before_first_sample_reports_no_current():
    rows = [sample(0, 500, at=50)]
    result = evaluate_contingent_world(world(series=rows, end=60,
                                             conditions=[condition(comparison=absolute(800),
                                                                   first=10, last=50)]))
    assert counts(result) == {'no_current': 4, 'fired': 1}


def test_stale_series_reports_stale_instead_of_firing():
    rows = [sample(0, 500, at=0), sample(1, 500, at=100)]
    package = world(series=rows, end=100, conditions=[condition(comparison=absolute(800),
                                                                first=10, cadence=10, last=100)])
    package['series'][0]['stale_after_seconds'] = 5
    result = evaluate_contingent_world(package)
    assert counts(result) == {'stale': 9, 'fired': 1}


def test_late_arriving_data_cannot_fire_an_earlier_alert():
    rows = [sample(0, 1000, at=0), sample(1, 500, at=10, available=30),
            sample(2, 480, at=20, available=30)]
    result = evaluate_contingent_world(world(series=rows, end=30,
                                             conditions=[condition(first=10, cadence=10, last=30)]))
    assert counts(result) == {'false': 2, 'fired': 1}
    assert result['firings'][0]['evaluated_at_seconds'] == 30
    assert result['series']['px']['late_arrival_samples'] == 2


def test_reference_window_grows_only_as_data_arrives():
    rows = [sample(0, 1000, at=0), sample(1, 400, at=10, available=25),
            sample(2, 500, at=20, available=20)]
    baseline = {'kind': 'window_aggregate', 'start_seconds': 0, 'end_seconds': 20,
                'aggregation': 'mean_floor'}
    result = evaluate_contingent_world(world(series=rows, end=30,
                                             conditions=[condition(reference=baseline, first=20,
                                                                   cadence=10, last=30)]))
    assert [firing['reference_value'] for firing in result['firings']] == [1000, 700]
    assert [firing['current_value'] for firing in result['firings']] == [500, 500]


def test_rolling_peak_uses_the_maximum_inside_the_window():
    rows = [sample(0, 1000, at=0), sample(1, 2000, at=10), sample(2, 1200, at=20),
            sample(3, 900, at=30)]
    peak = {'kind': 'rolling_peak_window', 'window_seconds': 25}
    result = evaluate_contingent_world(world(series=rows, end=30,
                                             conditions=[condition(reference=peak, first=30, last=30)]))
    assert result['firings'][0]['reference_value'] == 2000
    assert result['firings'][0]['current_value'] == 900


def test_window_aggregations_are_exact_integer_operations():
    rows = [sample(0, 100, at=0), sample(1, 90, at=10), sample(2, 85, at=20),
            sample(3, 60, at=30)]
    for aggregation, expected in [('maximum', 100), ('minimum', 85), ('last', 85),
                                  ('mean_floor', 91)]:
        reference = {'kind': 'window_aggregate', 'start_seconds': 0, 'end_seconds': 30,
                     'aggregation': aggregation}
        package = world(series=rows, end=30,
                        conditions=[condition(reference=reference, first=30, last=30)])
        assert evaluate_contingent_world(package)['firings'][0]['reference_value'] == expected


def test_same_timestamp_samples_order_deterministically():
    a = {'id': 'a', 'at_seconds': 10, 'available_at_seconds': 10, 'value': 1000, 'source': 'x'}
    b = {'id': 'b', 'at_seconds': 10, 'available_at_seconds': 10, 'value': 500, 'source': 'y'}
    first = evaluate_contingent_world(world(series=[a, b], end=10,
                                            conditions=[condition(comparison=absolute(800), first=10,
                                                                  last=10)]))
    second = evaluate_contingent_world(world(series=[b, a], end=10,
                                             conditions=[condition(comparison=absolute(800), first=10,
                                                                   last=10)]))
    assert first['firings'] == second['firings']
    assert first['conditions'] == second['conditions']
    assert first['firings'][0]['current_value'] == 500


def test_persistence_requires_consecutive_true_ticks():
    rows = [sample(0, 700, at=10), sample(1, 700, at=20)]
    result = evaluate_contingent_world(world(series=rows, end=20,
                                             conditions=[condition(comparison=absolute(800),
                                                                   first=10, last=20, persistence=2)]))
    assert counts(result) == {'true_holding': 1, 'fired': 1}


def test_persistence_reset_rules_differ_on_false_ticks():
    rows = [sample(0, 700, at=10), sample(1, 900, at=20), sample(2, 700, at=30)]
    base = world(series=rows, end=30, conditions=[condition(comparison=absolute(800), first=10,
                                                            last=30, persistence=2)])
    for reset, fired in [('on_non_true', 0), ('on_false_only', 0), ('never', 1)]:
        package = deepcopy(base)
        package['conditions'][0]['persistence_reset'] = reset
        result = evaluate_contingent_world(package)
        assert result['conditions']['c1']['fired'] == fired, reset


def test_persistence_reset_on_non_true_bridges_a_stale_tick():
    rows = [sample(0, 700, at=10), sample(1, 700, at=30)]
    base = world(series=rows, end=30, conditions=[condition(comparison=absolute(800), first=10,
                                                            cadence=10, last=30, persistence=2)])
    base['series'][0]['stale_after_seconds'] = 5
    for reset, fired in [('on_false_only', 1), ('never', 1), ('on_non_true', 0)]:
        package = deepcopy(base)
        package['conditions'][0]['persistence_reset'] = reset
        assert evaluate_contingent_world(package)['conditions']['c1']['fired'] == fired, reset


def test_cooldown_suppresses_repeats_without_resetting_persistence():
    rows = [sample(index, 500, at=index * 10) for index in range(5)]
    result = evaluate_contingent_world(world(series=rows, end=40,
                                             conditions=[condition(comparison=absolute(800), first=10,
                                                                   cooldown=25, last=40)]))
    assert counts(result) == {'fired': 2, 'cooldown': 2}
    assert [f['evaluated_at_seconds'] for f in result['firings']] == [10, 40]


def test_rearm_requires_one_false_evaluation():
    rows = [sample(0, 500, at=10), sample(1, 500, at=20), sample(2, 900, at=30),
            sample(3, 500, at=40)]
    result = evaluate_contingent_world(world(series=rows, end=40,
                                             conditions=[condition(comparison=absolute(800), first=10,
                                                                   rearm=True, last=40)]))
    assert counts(result) == {'fired': 2, 'awaiting_rearm': 1, 'false': 1}
    assert [f['evaluated_at_seconds'] for f in result['firings']] == [10, 40]


def test_detection_delay_shifts_only_the_effective_time():
    rows = [sample(0, 500, at=10)]
    result = evaluate_contingent_world(world(series=rows, end=10,
                                             conditions=[condition(comparison=absolute(800), first=10,
                                                                   last=10, delay=1800)]))
    assert result['firings'][0]['evaluated_at_seconds'] == 10
    assert result['firings'][0]['effective_at_seconds'] == 1810


def test_condition_is_gated_by_confirmed_lifecycle_stage():
    rows = [sample(index, 500, at=index * 10) for index in range(4)]
    transition = {'id': 't1', 'from_stage_id': 'pre', 'to_stage_id': 'post',
                  'effective_at_seconds': 25, 'confirmed': True, 'source': 'protocol'}
    result = evaluate_contingent_world(world(series=rows, end=30, transitions=[transition],
                                             conditions=[condition(comparison=absolute(800),
                                                                   stages=['post'], first=10, last=30)]))
    assert counts(result) == {'outside_stage': 2, 'fired': 1}
    assert result['lifecycle']['confirmed_transitions'] == 1
    assert result['lifecycle']['stage_at_seconds'][-1] == {'at_seconds': 30, 'stage_id': 'post'}


def test_unconfirmed_transition_never_advances_the_stage():
    rows = [sample(0, 500, at=10)]
    transition = {'id': 't1', 'from_stage_id': 'pre', 'to_stage_id': 'post',
                  'effective_at_seconds': 5, 'confirmed': False, 'source': 'rumor'}
    result = evaluate_contingent_world(world(series=rows, end=10, transitions=[transition],
                                             conditions=[condition(comparison=absolute(800),
                                                                   stages=['post'], first=10, last=10)]))
    assert counts(result) == {'outside_stage': 1}
    assert result['lifecycle']['unconfirmed_transitions'] == 1


def test_nonpositive_reference_stays_unknown():
    rows = [sample(0, 0, at=0), sample(1, 0, at=10)]
    prior = {'kind': 'prior_sample_window', 'window_seconds': 10, 'tolerance_seconds': 0}
    result = evaluate_contingent_world(world(series=rows, end=10,
                                             conditions=[condition(reference=prior, last=10)]))
    assert counts(result) == {'unknown_reference': 1}


def test_parameters_resolve_windows_thresholds_and_values():
    package = world(series=[{'id': 's0', 'at_seconds': 0, 'available_at_seconds': 0,
                             'value': {'parameter': 'crash'}, 'source': 'x'}],
                    end=10, conditions=[condition(comparison=absolute({'parameter': 'limit'}),
                                                  first=10, last=10)])
    package['parameters'] = {'crash': 500, 'limit': 800}
    result = evaluate_contingent_world(package)
    assert result['firings'][0]['current_value'] == 500
    assert result['firings'][0]['threshold'] == 800


def test_null_last_second_evaluates_through_the_horizon_end():
    rows = [sample(0, 500, at=10)]
    result = evaluate_contingent_world(world(series=rows, end=50,
                                             conditions=[condition(comparison=absolute(800), first=10,
                                                                   cadence=10, last=None)]))
    assert result['conditions']['c1']['ticks'] == 5
    assert counts(result) == {'fired': 5}


def test_evaluation_is_reproducible_and_verifiable():
    rows = [sample(index, 1000 - index * 120, at=index * 10) for index in range(6)]
    package = world(series=rows, end=50, conditions=[condition(first=10, persistence=2)])
    result = evaluate_contingent_world(package)
    assert json.dumps(result, sort_keys=True) == json.dumps(evaluate_contingent_world(deepcopy(package)),
                                                            sort_keys=True)
    assert verify_contingent_evaluation(deepcopy(result), package) == result
    tampered = deepcopy(result)
    tampered['firings'][0]['current_value'] += 1
    with pytest.raises(ValueError, match='deterministic recomputation'):
        verify_contingent_evaluation(tampered, package)


def test_package_hash_is_input_identity_not_dictionary_order():
    rows = [sample(0, 1000), sample(1, 500, at=10)]
    package = world(series=rows, end=10, conditions=[condition(comparison=absolute(800), last=10)])
    reordered = json.loads(json.dumps(package))
    reordered['series'][0] = dict(reversed(list(reordered['series'][0].items())))
    first = evaluate_contingent_world(package)
    second = evaluate_contingent_world(reordered)
    assert first['package_sha256'] == second['package_sha256']
    changed = deepcopy(package)
    changed['series'][0]['samples'][1]['value'] = 501
    assert evaluate_contingent_world(changed)['package_sha256'] != first['package_sha256']


def test_result_declares_no_inference_and_no_settlement_claim():
    result = evaluate_contingent_world(world(series=[sample(0, 500, at=10)], end=10,
                                             conditions=[condition(comparison=absolute(800), last=10)]))
    assert result['model_calls'] == 0
    assert result['engine_sha256']
    assert any('alert' in item for item in result['limitations'])
    assert any('occurrence odds' in item for item in result['limitations'])


def validate_rejects(value, message):
    with pytest.raises(ValueError, match=message):
        validate_contingent_world(value)


def test_validation_rejects_unsafe_or_incomplete_input():
    good = world(series=[sample(0, 500, at=10)], conditions=[condition(comparison=absolute(800))])
    extra = deepcopy(good)
    extra['series'][0]['default'] = 0
    validate_rejects(extra, 'exactly the declared fields')
    missing = deepcopy(good)
    del missing['conditions'][0]['cooldown_seconds']
    validate_rejects(missing, 'exactly the declared fields')
    wrong_schema = deepcopy(good)
    wrong_schema['schema_version'] = 'contingent-world.v2'
    validate_rejects(wrong_schema, 'unsupported contingent-world schema')
    early = deepcopy(good)
    early['series'][0]['samples'][0]['available_at_seconds'] = 9
    validate_rejects(early, 'available before its event time')
    outside = deepcopy(good)
    outside['series'][0]['samples'][0]['value'] = 2000
    outside['series'][0]['maximum'] = 1000
    validate_rejects(outside, 'outside series bounds')
    duplicate = deepcopy(good)
    duplicate['series'][0]['samples'].append(duplicate['series'][0]['samples'][0])
    validate_rejects(duplicate, 'duplicate sample identifier')
    unknown_series = deepcopy(good)
    unknown_series['conditions'][0]['series_id'] = 'nope'
    validate_rejects(unknown_series, 'unknown series reference')
    unknown_actor = deepcopy(good)
    unknown_actor['series'][0]['actor_ids'] = ['ghost']
    validate_rejects(unknown_actor, 'unknown actor reference')
    zero_cadence = deepcopy(good)
    zero_cadence['conditions'][0]['evaluation']['cadence_seconds'] = 0
    validate_rejects(zero_cadence, 'integer outside bounds')
    inverted = deepcopy(good)
    inverted['end_seconds'] = 0
    validate_rejects(inverted, 'integer outside bounds')
    outside_horizon = deepcopy(good)
    outside_horizon['conditions'][0]['evaluation']['first_at_seconds'] = 500
    validate_rejects(outside_horizon, 'integer outside bounds')
    bool_value = deepcopy(good)
    bool_value['series'][0]['samples'][0]['value'] = True
    validate_rejects(bool_value, 'invalid integer type')
    float_value = deepcopy(good)
    float_value['series'][0]['samples'][0]['value'] = 500.5
    validate_rejects(float_value, 'integers or null')
    soft_confirmed = deepcopy(good)
    soft_confirmed['lifecycle']['transitions'] = [{'id': 't1', 'from_stage_id': 'pre',
                                                   'to_stage_id': 'post', 'effective_at_seconds': 1,
                                                   'confirmed': 'yes', 'source': 'x'}]
    validate_rejects(soft_confirmed, 'expected boolean')
    missing_zero = deepcopy(good)
    del missing_zero['conditions'][0]['comparison']['threshold_bps']
    validate_rejects(missing_zero, 'exactly the declared fields')
    bad_reset = deepcopy(good)
    bad_reset['conditions'][0]['persistence_reset'] = 'on_weekends'
    validate_rejects(bad_reset, 'unsupported persistence reset rule')
    bad_reference = deepcopy(good)
    bad_reference['conditions'][0]['reference'] = {'kind': 'oracle'}
    validate_rejects(bad_reference, 'unsupported reference kind')
    unhashable = deepcopy(good)
    unhashable['conditions'][0]['persistence_reset'] = ['on_non_true']
    validate_rejects(unhashable, 'unsupported persistence reset rule')
    unhashable = deepcopy(good)
    unhashable['conditions'][0]['comparison']['direction'] = {'at_or_below': 1}
    validate_rejects(unhashable, 'unsupported comparison direction')
    unhashable = deepcopy(good)
    unhashable['conditions'][0]['reference'] = {'kind': 'window_aggregate', 'start_seconds': 0,
                                               'end_seconds': 20, 'aggregation': ['maximum']}
    validate_rejects(unhashable, 'unsupported window aggregation')
    missing_lifecycle = deepcopy(good)
    del missing_lifecycle['lifecycle']['initial_stage_id']
    validate_rejects(missing_lifecycle, 'exactly the declared fields')
    invented_lifecycle = deepcopy(good)
    invented_lifecycle['lifecycle']['default_stage'] = 'post'
    validate_rejects(invented_lifecycle, 'exactly the declared fields')
    branching = deepcopy(good)
    branching['lifecycle']['transitions'] = [
        {'id': 't1', 'from_stage_id': 'post', 'to_stage_id': 'pre', 'effective_at_seconds': 1,
         'confirmed': True, 'source': 'x'}]
    validate_rejects(branching, 'but the stage is')
    same_stage = deepcopy(good)
    same_stage['lifecycle']['transitions'] = [
        {'id': 't1', 'from_stage_id': 'pre', 'to_stage_id': 'pre', 'effective_at_seconds': 1,
         'confirmed': True, 'source': 'x'}]
    validate_rejects(same_stage, 'cannot keep the same stage')
    huge = world(series=[sample(0, 500, at=10)], start=0, end=300000,
                 conditions=[condition(cadence=1)])
    validate_rejects(huge, 'evaluation ticks exceed limit')


def test_capabilities_publish_the_whole_contract():
    capabilities = contingent_world_capabilities()
    assert capabilities['model_calls'] == 0
    assert capabilities['reference_kinds'] == ['prior_sample_window', 'rolling_peak_window',
                                               'window_aggregate']
    assert capabilities['outcomes'] == ['awaiting_rearm', 'cooldown', 'false', 'fired',
                                        'no_current', 'outside_stage', 'stale', 'true_holding',
                                        'unknown_member', 'unknown_reference']
    assert capabilities['condition_kinds'] == ['simple', 'all_of']
    assert 'composite' in capabilities['fields']
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
    assert all('contract' not in node or node['contract'] in names
               for node in [capabilities['fields']['package']])
    assert capabilities['fields']['sample']['constraints'][0].startswith('available_at_seconds >=')
    assert 'financial_settlement' in capabilities['assumptions']


def add_series(package, series_id, value, at=0, available=None, stale_after=10**6):
    package['series'].append({'id': series_id, 'unit': 'usd_milli', 'minimum': 0,
                              'maximum': 10**9, 'stale_after_seconds': stale_after,
                              'actor_ids': ['founder'],
                              'samples': [{'id': 'a0', 'at_seconds': at,
                                           'available_at_seconds': at if available is None else available,
                                           'value': value, 'source': 'second-feed'}]})
    return package


def composite(cid='k1', members=('c1', 'c2'), stages=None, first=10, cadence=10, last=None,
              persistence=1, reset='on_non_true', cooldown=0, rearm=False, delay=0):
    return {'id': cid, 'all_of': list(members), 'stage_ids': stages or ['pre', 'post'],
            'evaluation': {'first_at_seconds': first, 'cadence_seconds': cadence,
                           'last_at_seconds': last},
            'persistence_consecutive': persistence, 'persistence_reset': reset,
            'cooldown_seconds': cooldown, 'rearm_requires_false': rearm,
            'detection_delay_seconds': delay, 'explanation': 'declared conjunction'}


def test_composite_fires_only_when_every_member_is_true():
    package = world(series=[sample(0, 500)], end=10,
                    conditions=[condition('c1', comparison=absolute(500)),
                                condition('c2', series_id='px2', comparison=absolute(500))])
    add_series(package, 'px2', 900)
    package['composites'] = [composite()]
    blocked = evaluate_contingent_world(package)
    assert counts(blocked, 'k1') == {'false': 1}
    assert [f for f in blocked['firings'] if f['condition_id'] == 'k1'] == []
    package['series'][1]['samples'][0]['value'] = 500
    fired = evaluate_contingent_world(package)
    assert counts(fired, 'k1')['fired'] == 1
    composite_firing = [f for f in fired['firings'] if f['condition_id'] == 'k1'][0]
    assert composite_firing['kind'] == 'all_of'
    assert composite_firing['members'] == ['c1', 'c2']


def test_composite_reports_unknown_member_instead_of_false():
    package = world(series=[sample(0, 500)], end=30,
                    conditions=[condition('c1', comparison=absolute(500)),
                                condition('c2', series_id='px2', first=20, last=30,
                                          comparison=absolute(500))])
    add_series(package, 'px2', 500, at=0, stale_after=5)
    package['composites'] = [composite(first=10, last=30)]
    result = evaluate_contingent_world(package)
    assert set(counts(result, 'k1')) == {'unknown_member'}
    assert 'fired' not in counts(result, 'k1')


def test_composite_waits_for_persistence_across_both_members():
    package = world(series=[sample(0, 500)], end=20,
                    conditions=[condition('c1', comparison=absolute(500)),
                                condition('c2', series_id='px2', comparison=absolute(500))])
    add_series(package, 'px2', 500)
    package['composites'] = [composite(first=10, cadence=10, last=20, persistence=2)]
    result = evaluate_contingent_world(package)
    assert counts(result, 'k1') == {'true_holding': 1, 'fired': 1}
    composite_firing = [f for f in result['firings'] if f['condition_id'] == 'k1'][0]
    assert composite_firing['evaluated_at_seconds'] == 20
    assert composite_firing['consecutive_true'] == 2


def test_composite_is_stage_gated():
    transition = {'id': 't1', 'from_stage_id': 'pre', 'to_stage_id': 'post',
                  'effective_at_seconds': 15, 'confirmed': True, 'source': 'protocol'}
    package = world(series=[sample(0, 500)], end=20, transitions=[transition],
                    conditions=[condition('c1', comparison=absolute(500)),
                                condition('c2', series_id='px2', comparison=absolute(500))])
    add_series(package, 'px2', 500)
    package['composites'] = [composite(stages=['post'], first=10, cadence=10, last=20)]
    result = evaluate_contingent_world(package)
    assert counts(result, 'k1') == {'outside_stage': 1, 'fired': 1}


def test_composite_members_must_be_distinct_known_conditions():
    package = world(series=[sample(0, 500)], end=10,
                    conditions=[condition('c1', comparison=absolute(500)),
                                condition('c2', series_id='px2', comparison=absolute(500))])
    add_series(package, 'px2', 500)
    package['composites'] = [composite(members=('c1', 'ghost'))]
    with pytest.raises(ValueError, match='unknown or duplicate member condition'):
        evaluate_contingent_world(package)
    package['composites'] = [composite(members=('c1', 'c1'))]
    with pytest.raises(ValueError, match='unknown or duplicate member condition'):
        evaluate_contingent_world(package)
    package['composites'] = [composite(members=('c1',))]
    with pytest.raises(ValueError, match='invalid list type or size'):
        evaluate_contingent_world(package)
    package['composites'] = [composite(cid='c1')]
    with pytest.raises(ValueError, match='collides with a condition id'):
        evaluate_contingent_world(package)
