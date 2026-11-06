from copy import deepcopy
import json

import pytest

from decision_lab.agent_worlds import digest
from decision_lab.simulation_evidence import audit_evidence, numeric_targets


def register():
    return {
        'schema_version': 'simulation-evidence.v1',
        'as_of': '2026-11-02T08:00:00Z',
        'target_sha256': digest({'capital': 100}),
        'sources': [],
        'claims': [
            {'id': 'capital', 'kind': 'input', 'status': 'assumed',
             'statement': 'A hypothetical actor has 100 cash units.', 'depends_on': [],
             'rationale': 'A finite funded wallet makes spending and insolvency testable.',
             'sensitivity': 'Compare 50, 100 and 200 cash units without adding counterparties.',
             'falsification': 'Replace with a dated authorized balance before an empirical forecast.'},
            {'id': 'settlement', 'kind': 'mechanism', 'status': 'derived',
             'statement': 'Paid costs reduce the payer balance.', 'depends_on': ['capital'],
             'method': 'Closing cash = opening cash minus settled costs; reject unaffordable actions.'},
            {'id': 'closing-cash', 'kind': 'outcome', 'status': 'derived',
             'statement': 'Report conditional closing cash, not a prediction.',
             'depends_on': ['settlement'], 'method': 'Read reconciled terminal ledger cash.'},
        ],
        'bindings': {'/capital': 'capital', 'outcome:cash': 'closing-cash'},
    }


REQUIRED = {'/capital': 'input', 'outcome:cash': 'outcome'}


def audit(value):
    return audit_evidence(value, required_targets=REQUIRED, target_sha256=digest({'capital': 100}))


def sourced(value, kind='measurement'):
    value['sources'] = [{
        'id': 'reference', 'kind': kind, 'publisher': 'Fictional test provider',
        'locator': 'https://example.test/dataset', 'available_at': '2026-11-01T10:00:00Z',
        'retrieved_at': '2026-11-01T11:00:00Z', 'scope': 'Test actor, cash units, dated balance.',
        'method': 'Direct balance measurement.', 'limitations': 'Fictional test receipt, not live evidence.',
        'review': 'reviewed',
    }]
    value['claims'][0].update(status='observed', source_ids=['reference'],
                               method='Use the reported dated actor balance in the same units.')
    return value


def test_conditional_assumptions_are_allowed_but_do_not_certify_real_world_odds():
    value = register()
    original = deepcopy(value)
    result = audit(value)
    assert result['status'] == 'ready_for_conditional_simulation'
    assert result['forecast_validated'] is False
    assert result['assumed_claims'] == ['capital']
    assert result['claim_labels']['closing-cash'] == 'assumption_dependent'
    assert result['model_calls'] == 0 and value == original


@pytest.mark.parametrize('field', ['rationale', 'sensitivity', 'falsification'])
def test_an_assumption_needs_a_cause_sensitivity_and_disconfirmation(field):
    value = register()
    del value['claims'][0][field]
    result = audit(value)
    assert result['status'] == 'blocked'
    assert 'closing-cash' in result['blocked_claims']


@pytest.mark.parametrize('status', ['unknown', 'disputed'])
def test_unknown_or_disputed_inputs_block_dependent_outcomes(status):
    value = register()
    value['claims'][0]['status'] = status
    result = audit(value)
    assert set(result['blocked_claims']) == {'capital', 'settlement', 'closing-cash'}
    assert any(issue['code'] == 'dependency_blocked' for issue in result['issues'])
    assert result['claim_labels']['closing-cash'] == 'unresolved_dependency'


def test_a_reputable_link_without_a_specific_supported_measurement_is_not_enough():
    value = sourced(register())
    value['claims'][0].pop('method')
    assert audit(value)['status'] == 'blocked'
    value['claims'][0]['method'] = 'Exact balance, definition and population match.'
    value['sources'][0]['review'] = 'unreviewed'
    assert audit(value)['status'] == 'blocked'


@pytest.mark.parametrize('field', ['available_at', 'retrieved_at'])
def test_future_or_later_retrieved_evidence_cannot_be_backdated(field):
    value = sourced(register())
    value['sources'][0][field] = '2026-11-02T08:00:01Z'
    assert any(issue['code'] == 'source_after_cutoff' for issue in audit(value)['issues'])


def test_a_scheduled_event_after_cutoff_can_be_known_before_cutoff():
    value = sourced(register(), 'official_schedule')
    value['sources'][0]['scope'] = 'A November 3 event scheduled in a November 1 publication.'
    assert audit(value)['status'] == 'ready_for_conditional_simulation'


def test_capture_cannot_precede_publication_and_missing_time_does_not_hide_late_capture():
    value = sourced(register())
    value['sources'][0]['available_at'] = '2026-11-01T12:00:00Z'
    assert any(issue['code'] == 'source_time_order' for issue in audit(value)['issues'])
    value['sources'][0].update(available_at=None, retrieved_at='2026-11-02T09:00:00Z')
    codes = {issue['code'] for issue in audit(value)['issues']}
    assert {'unknown_source_time', 'source_after_cutoff'} <= codes


@pytest.mark.parametrize('kind', ['poll', 'official_result', 'official_schedule', 'prediction_market', 'model_receipt'])
def test_poll_votes_schedule_market_quotes_and_model_scores_are_not_event_probabilities(kind):
    value = sourced(register(), kind)
    value['claims'][0].update(kind='probability', probability_kind='event_probability')
    value['bindings'] = {'probability:event': 'capital'}
    result = audit_evidence(value, required_targets={'probability:event': 'probability'})
    assert any(issue['code'] == 'invalid_probability_transfer' for issue in result['issues'])


@pytest.mark.parametrize('source_kind, probability_kind', [
    ('poll', 'poll_share'), ('prediction_market', 'market_implied'),
    ('forecast', 'event_probability'), ('model_receipt', 'model_score'),
    ('engine_receipt', 'simulation_frequency'),
])
def test_source_probability_types_keep_their_own_meaning(source_kind, probability_kind):
    value = sourced(register(), source_kind)
    value['claims'][0].update(kind='probability', probability_kind=probability_kind,
                              uncertainty='Sampling, resolution and source limitations remain explicit.')
    value['bindings'] = {'probability:reported': 'capital'}
    result = audit_evidence(value, required_targets={'probability:reported': 'probability'})
    assert result['status'] == 'ready_for_conditional_simulation'
    assert result['forecast_validated'] is False


def test_transforming_a_poll_to_event_odds_needs_a_separate_assumed_or_validated_model():
    value = sourced(register(), 'poll')
    value['claims'][0].update(kind='probability', probability_kind='poll_share', uncertainty='Nonrepresentative vote.')
    value['claims'].append({
        'id': 'event-odds', 'kind': 'probability', 'status': 'derived',
        'statement': 'An unjustified conversion of poll shares into crash odds.',
        'depends_on': ['capital'], 'method': 'Copy the share.',
        'probability_kind': 'event_probability', 'uncertainty': 'Unknown calibration.',
    })
    value['bindings'] = {'probability:event': 'event-odds'}
    result = audit_evidence(value, required_targets={'probability:event': 'probability'})
    assert any(issue['code'] == 'invalid_probability_transfer' for issue in result['issues'])


def test_coverage_hash_cycles_and_missing_dependencies_fail_closed():
    value = register()
    del value['bindings']['outcome:cash']
    assert any(issue['code'] == 'missing_binding' for issue in audit(value)['issues'])
    value = register()
    value['target_sha256'] = '0' * 64
    assert any(issue['code'] == 'target_mismatch' for issue in audit(value)['issues'])
    value = register()
    value['claims'][0]['depends_on'] = ['closing-cash']
    with pytest.raises(ValueError, match='cycle'):
        audit(value)
    value['claims'][0]['depends_on'] = ['nonexistent']
    with pytest.raises(ValueError, match='dependency'):
        audit(value)


def test_an_outcome_needs_a_mechanism_and_cannot_be_a_forecast_copied_from_a_link():
    value = sourced(register())
    value['claims'][2].update(depends_on=['capital'])
    assert any(issue['code'] == 'outcome_without_mechanism' for issue in audit(value)['issues'])
    value['claims'][2].update(depends_on=[], status='observed', source_ids=['reference'])
    assert audit(value)['status'] == 'blocked'


def test_same_contract_covers_defi_nonfinancial_and_json_pointer_escaping():
    targets = numeric_targets({'TVL/USD': 30, 'fees~due': 2, 'active': True, 'visits': [1, 2], 'label': 'DeFi'})
    assert targets == {'/TVL~1USD': 'input', '/fees~0due': 'input', '/active': 'input',
                       '/visits/0': 'input', '/visits/1': 'input'}
    value = register()
    value['bindings'] = {'/tvl': 'capital', 'outcome:adoption': 'closing-cash'}
    result = audit_evidence(value, required_targets={'/tvl': 'input', 'outcome:adoption': 'outcome'})
    assert result['status'] == 'ready_for_conditional_simulation'


@pytest.mark.parametrize('mutation', ['duplicate', 'nan', 'naive-time', 'unknown-source', 'empty-requirements'])
def test_malformed_or_unbounded_evidence_is_rejected(mutation):
    value = register()
    required = REQUIRED
    if mutation == 'duplicate':
        value['claims'].append(deepcopy(value['claims'][0]))
    elif mutation == 'nan':
        value['claims'][0]['bad'] = float('nan')
    elif mutation == 'naive-time':
        value['as_of'] = '2026-11-02T08:00:00'
    elif mutation == 'unknown-source':
        value['claims'][0]['source_ids'] = ['missing']
    else:
        required = {}
    with pytest.raises(ValueError):
        audit_evidence(value, required_targets=required)


def test_cli_audit_is_offline_and_exits_nonzero_for_missing_support(tmp_path, capsys):
    from decision_lab.cli import main
    source, required = tmp_path / 'evidence.json', tmp_path / 'targets.json'
    source.write_text(json.dumps(register()))
    required.write_text(json.dumps(REQUIRED))
    command = ['evidence', 'audit', '--input', str(source), '--targets', str(required)]
    assert main(command) == 0
    assert json.loads(capsys.readouterr().out)['model_calls'] == 0
    value = register()
    value['claims'][0]['status'] = 'unknown'
    source.write_text(json.dumps(value))
    assert main(command) == 2
    assert json.loads(capsys.readouterr().out)['status'] == 'blocked'
