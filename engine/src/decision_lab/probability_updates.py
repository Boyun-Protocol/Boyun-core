"""Exact belief updates for declared finite hypotheses and explicit likelihoods.

This reasoning kernel exists to separate prior assumptions, likelihood claims
and posterior arithmetic. It does not manufacture calibrated event odds from
model confidence, news text or simulated world frequencies. The caller must
justify an exhaustive mutually exclusive hypothesis set and conditional signal
independence before using this specific update rule.
"""
from copy import deepcopy
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
import re

MAX_BYTES = 131072
ENGINE_SHA256 = sha256(Path(__file__).read_bytes()).hexdigest()
ASSUMPTION = 'conditionally_independent_given_hypothesis'


def _shape(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        raise ValueError('invalid finite-belief object shape')


def _text(value, limit):
    if type(value) is not str or not value.strip() or len(value) > limit:
        raise ValueError('nonempty bounded finite-belief text required')
    return value


def _id(value):
    if type(value) is not str or not re.fullmatch(r'[a-z][a-z0-9-]{0,47}', value):
        raise ValueError('invalid finite-belief identifier')
    return value


def _bps(value):
    if type(value) is not int or not 0 <= value <= 10000:
        raise ValueError('likelihood/prior must be integer basis points from 0 to 10000')
    return value


def _list(value, minimum, maximum):
    if type(value) is not list or not minimum <= len(value) <= maximum:
        raise ValueError('invalid bounded finite-belief list')
    return value


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':'),
                      allow_nan=False).encode('ascii')


def validate_belief(value):
    """Validate exhaustive declared hypotheses and the supported likelihood model."""
    try:
        if len(_canonical(value)) > MAX_BYTES:
            raise ValueError('finite-belief input exceeds size budget')
        _shape(value, {'schema_version', 'id', 'description', 'hypotheses', 'evidence',
                       'likelihood_assumption'})
        if value['schema_version'] != 'finite-belief.v1':
            raise ValueError('unsupported finite-belief schema')
        _id(value['id']);_text(value['description'], 8000)
        if value['likelihood_assumption'] != ASSUMPTION:
            raise ValueError('only explicit conditional independence given hypothesis is supported')
        hypotheses = _list(value['hypotheses'], 2, 16)
        ids = []
        for hypothesis in hypotheses:
            _shape(hypothesis, {'id', 'prior_bps'})
            identifier = _id(hypothesis['id']);_bps(hypothesis['prior_bps'])
            if identifier in ids:
                raise ValueError('duplicate finite-belief hypothesis')
            ids.append(identifier)
        if sum(hypothesis['prior_bps'] for hypothesis in hypotheses) != 10000:
            raise ValueError('prior basis points must sum to 10000')
        evidence_ids = set()
        for observation in _list(value['evidence'], 0, 8):
            _shape(observation, {'id', 'likelihood_bps', 'provenance'})
            identifier = _id(observation['id'])
            if identifier in evidence_ids:
                raise ValueError('duplicate finite-belief evidence')
            evidence_ids.add(identifier)
            _shape(observation['likelihood_bps'], ids)
            for likelihood in observation['likelihood_bps'].values():
                _bps(likelihood)
            provenance = observation['provenance']
            _shape(provenance, {'status', 'rationale', 'source_refs'})
            if provenance['status'] not in {'assumed', 'estimated', 'model_proposal'}:
                raise ValueError('likelihood needs explicit assumption/estimate/model provenance')
            _text(provenance['rationale'], 1600)
            for reference in _list(provenance['source_refs'], 0, 8):
                _text(reference, 400)
        return deepcopy(value)
    except (TypeError, KeyError, OverflowError, RecursionError) as error:
        raise ValueError('invalid finite-belief input') from error


def _ratio(value):
    return {'numerator': value.numerator, 'denominator': value.denominator}


def update_beliefs(value):
    """Apply Bayes' rule with exact normalization at each evidence step.

    posterior(H) = prior(H) * likelihood(E|H) / sum_h prior(h)*likelihood(E|h).
    After each step the posterior becomes the next prior. Because supplied
    likelihoods are declared conditionally independent given hypothesis, their
    product yields the same final posterior in any evidence order. Step
    normalizers are conditional evidence probabilities under earlier updates;
    their product is the joint evidence probability in the supplied model.
    Distinct evidence IDs cannot establish statistical independence by themselves.
    """
    belief = validate_belief(value)
    prior = {hypothesis['id']: Fraction(hypothesis['prior_bps'], 10000)
             for hypothesis in belief['hypotheses']}
    posterior, joint, steps = dict(prior), Fraction(1), []
    for evidence in belief['evidence']:
        weighted = {identifier: probability * Fraction(evidence['likelihood_bps'][identifier], 10000)
                    for identifier, probability in posterior.items()}
        marginal = sum(weighted.values(), Fraction(0))
        if marginal == 0:
            raise ValueError('observed evidence has zero probability under all surviving hypotheses; revise model or evidence')
        posterior = {identifier: weight / marginal for identifier, weight in weighted.items()}
        joint *= marginal
        steps.append({'evidence_id': evidence['id'],
                      'conditional_evidence_likelihood': _ratio(marginal),
                      'joint_evidence_likelihood': _ratio(joint),
                      'posterior': {identifier: _ratio(probability) for identifier, probability in posterior.items()},
                      'provenance': deepcopy(evidence['provenance'])})
    return {
        'schema_version': 'finite-belief-update.v1', 'input_sha256': sha256(_canonical(belief)).hexdigest(),
        'engine_sha256': ENGINE_SHA256, 'belief_id': belief['id'], 'advisory_only': True,
        'likelihood_assumption': ASSUMPTION,
        'prior': {identifier: _ratio(probability) for identifier, probability in prior.items()},
        'steps': steps, 'posterior': {identifier: _ratio(probability) for identifier, probability in posterior.items()},
        'joint_evidence_likelihood': _ratio(joint),
        'limitations': [
            'The caller declares hypotheses mutually exclusive and exhaustive. Arithmetic cannot establish that this list covers the real world.',
            'Prior weights and likelihoods are explicit supplied assumptions/estimates, not learned or validated real-world event chances.',
            'Conditionally independent signals are assumed given hypothesis; dependent, copied or overlapping signals can double-count evidence and exaggerate certainty.',
            'Distinct evidence IDs and provenance references do not verify independence, truth, completeness or causal relevance.',
            'Likelihoods are P(evidence|hypothesis), not P(hypothesis|evidence). They need not sum to one across hypotheses.',
            'No Jev confidence, model score, news sentiment or simulation frequency is automatically converted into a likelihood or calibrated posterior.',
            'Posteriors are conditional on this finite supplied model. They are not authenticated real-world odds or a guarantee of outcomes.',
            'No model inference, ledger mutation, market action, evidence collection or automatic decision is performed.',
        ],
    }
