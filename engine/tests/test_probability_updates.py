"""Exact conditional Bayes updates from explicit, reviewable likelihoods."""
from copy import deepcopy
from fractions import Fraction

import pytest

from decision_lab.probability_updates import update_beliefs, validate_belief


def belief():
    return {'schema_version': 'finite-belief.v1', 'id': 'coin-type',
            'description': 'The selected coin is exactly one of the two specified hypotheses.',
            'hypotheses': [{'id': 'fair', 'prior_bps': 5000}, {'id': 'heads-biased', 'prior_bps': 5000}],
            'evidence': [{'id': 'first-head', 'likelihood_bps': {'fair': 5000, 'heads-biased': 10000},
                          'provenance': {'status': 'assumed', 'rationale': 'Known stipulated coin model, not empirical market calibration.', 'source_refs': []}},
                         {'id': 'second-head', 'likelihood_bps': {'fair': 5000, 'heads-biased': 10000},
                          'provenance': {'status': 'assumed', 'rationale': 'Separate toss is conditionally independent given coin type.', 'source_refs': []}}],
            'likelihood_assumption': 'conditionally_independent_given_hypothesis'}


def ratio(value):
    return {'numerator': value.numerator, 'denominator': value.denominator}


def test_coin_posterior_and_sequential_normalizers_are_exact():
    result = update_beliefs(belief())
    assert result['schema_version'] == 'finite-belief-update.v1'
    assert result['prior'] == {'fair': ratio(Fraction(1, 2)), 'heads-biased': ratio(Fraction(1, 2))}
    first, second = result['steps']
    assert first['conditional_evidence_likelihood'] == ratio(Fraction(3, 4))
    assert first['posterior'] == {'fair': ratio(Fraction(1, 3)), 'heads-biased': ratio(Fraction(2, 3))}
    assert second['conditional_evidence_likelihood'] == ratio(Fraction(5, 6))
    assert result['joint_evidence_likelihood'] == ratio(Fraction(5, 8))
    assert result['posterior'] == {'fair': ratio(Fraction(1, 5)), 'heads-biased': ratio(Fraction(4, 5))}
    assert second['joint_evidence_likelihood'] == result['joint_evidence_likelihood']


def test_no_evidence_returns_prior_without_invented_updates():
    value = belief();value['evidence'] = []
    result = update_beliefs(value)
    assert result['steps'] == []
    assert result['posterior'] == result['prior']
    assert result['joint_evidence_likelihood'] == ratio(Fraction(1))


def test_order_invariance_under_declared_conditional_independence():
    value = belief()
    value['evidence'][1]['likelihood_bps'] = {'fair': 2000, 'heads-biased': 8000}
    first = update_beliefs(value)
    value['evidence'].reverse()
    second = update_beliefs(value)
    assert first['posterior'] == second['posterior']
    assert first['joint_evidence_likelihood'] == second['joint_evidence_likelihood']
    assert first['steps'][0]['conditional_evidence_likelihood'] != second['steps'][0]['conditional_evidence_likelihood']


def test_zero_prior_stays_zero_and_zero_likelihood_eliminates_hypothesis():
    value = belief();value['hypotheses'][0]['prior_bps'] = 0;value['hypotheses'][1]['prior_bps'] = 10000
    assert update_beliefs(value)['posterior']['fair'] == ratio(Fraction(0))
    value = belief();value['evidence'][0]['likelihood_bps']['fair'] = 0
    assert update_beliefs(value)['posterior'] == {'fair': ratio(Fraction(0)), 'heads-biased': ratio(Fraction(1))}


def test_impossible_evidence_is_rejected_not_normalized_to_uniform():
    value = belief();value['evidence'][0]['likelihood_bps'] = {'fair': 0, 'heads-biased': 0}
    with pytest.raises(ValueError, match='zero probability'): update_beliefs(value)
    value = belief();value['evidence'][0]['likelihood_bps']['fair'] = 0
    value['evidence'][1]['likelihood_bps']['heads-biased'] = 0
    with pytest.raises(ValueError, match='zero probability'): update_beliefs(value)


def test_unchanged_inputs_and_deterministic_detached_provenance():
    value = belief();before = deepcopy(value)
    result = update_beliefs(value)
    assert value == before and result == update_beliefs(value)
    detached = validate_belief(value);detached['description'] = 'Changed'
    result['steps'][0]['provenance']['rationale'] = 'Changed'
    assert value == before


@pytest.mark.parametrize('change', [
    lambda b: b.update(schema_version='other'), lambda b: b.update(extra=True),
    lambda b: b.update(likelihood_assumption='independent'),
    lambda b: b['hypotheses'].pop(),
    lambda b: b['hypotheses'][0].update(prior_bps=True),
    lambda b: b['hypotheses'][0].update(prior_bps=1.0),
    lambda b: b['hypotheses'][0].update(prior_bps=6000),
    lambda b: b['hypotheses'][0].update(prior_bps=-1),
    lambda b: b['hypotheses'][0].update(id='heads-biased'),
    lambda b: b['evidence'][0]['likelihood_bps'].update(fair=True),
    lambda b: b['evidence'][0]['likelihood_bps'].update(fair=10001),
    lambda b: b['evidence'][0]['likelihood_bps'].pop('fair'),
    lambda b: b['evidence'][0]['likelihood_bps'].update(other=1),
    lambda b: b['evidence'].append(deepcopy(b['evidence'][0])),
    lambda b: b['evidence'][0]['provenance'].update(status='observed'),
    lambda b: b['evidence'][0]['provenance'].update(rationale=''),
    lambda b: b['evidence'][0]['provenance'].update(source_refs=['x'] * 9),
    lambda b: b['evidence'].extend([deepcopy(b['evidence'][0])] * 8),
    lambda b: b.update(description='x' * 8001),
])
def test_strict_prior_likelihood_identity_provenance_and_work_bounds(change):
    value = belief();change(value)
    with pytest.raises(ValueError): update_beliefs(value)


def test_boundaries_sixteen_hypotheses_eight_distinct_signals():
    value = belief()
    value['hypotheses'] = [{'id': f'hyp-{i}', 'prior_bps': 625} for i in range(16)]
    value['evidence'] = [{'id': f'obs-{i}', 'likelihood_bps': {f'hyp-{j}': 9999 if j == 0 else 1 for j in range(16)},
                          'provenance': {'status': 'estimated', 'rationale': 'Illustrative extremes, not learned.', 'source_refs': []}}
                         for i in range(8)]
    result = update_beliefs(value)
    assert len(result['posterior']) == 16 and len(result['steps']) == 8
    fractions = [Fraction(**{'numerator': item['numerator'], 'denominator': item['denominator']}) for item in result['posterior'].values()]
    assert sum(fractions) == 1
    assert result['posterior']['hyp-0']['denominator'] > 10**12


def test_limits_explain_dependent_signal_double_counting_and_no_market_calibration():
    result = update_beliefs(belief())
    limits = ' '.join(result['limitations'])
    assert 'dependent' in limits and 'double-count' in limits
    assert 'Jev' in limits and 'calibrat' in limits
    assert 'mutually exclusive' in limits and 'exhaustive' in limits
    assert result['advisory_only'] is True


def test_likelihoods_are_not_required_to_sum_across_hypotheses():
    value = belief();value['evidence'] = value['evidence'][:1]
    value['evidence'][0]['likelihood_bps'] = {'fair': 9000, 'heads-biased': 9000}
    result = update_beliefs(value)
    assert result['posterior'] == result['prior']
    assert result['joint_evidence_likelihood'] == ratio(Fraction(9, 10))


def test_distinct_but_duplicate_signal_likelihoods_are_not_claimed_independent_verified():
    result = update_beliefs(belief())
    assert len(result['steps']) == 2
    assert any('Distinct evidence IDs' in item and 'do not verify independence' in item for item in result['limitations'])


def test_attention_example_is_exact_assumed_conditional_model_not_market_odds():
    import json
    from pathlib import Path
    value = json.loads((Path(__file__).parents[1]/'examples/event-belief-update.json').read_text())
    result = update_beliefs(value)
    assert result['posterior']['attention-persists'] == ratio(Fraction(4, 5))
    assert result['joint_evidence_likelihood'] == ratio(Fraction(9, 40))
    assert all(step['provenance']['status'] == 'assumed' for step in result['steps'])


@pytest.mark.parametrize('bad', [None, [], {}, {'schema_version': 'finite-belief.v1'}, {'x': float('nan')}])
def test_nonobjects_and_nonfinite_input_rejected(bad):
    with pytest.raises(ValueError): validate_belief(bad)
