"""Agent drafts are editable data; the core never invents missing values."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from decision_lab.scenario_authoring import (
    apply_authoring_response, authoring_guidelines, capabilities, compile_draft,
    draft_digest, prepare_authoring_request, run_package,
)


def chain():
    return {
        'schema_version': 'event-chain.v1', 'id': 'ticker-choice',
        'event_description': 'Compare two ticker names using supplied audience scores.',
        'parameters': {'candidate_score': 75},
        'personas': [{'id': 'retail', 'name': 'Retail audience', 'description': 'A declared audience assessment.',
                      'role': 'audience', 'allowed_actions': ['adjust_metric']}],
        'metrics': [{'id': 'preference', 'unit': 'rubric_points', 'initial': 0}],
        'rules': [{'id': 'assessment', 'at_tick': 1, 'actor_id': 'retail', 'requires': [],
                   'outcomes': [{'id': 'scored', 'probability_bps': 10000,
                                 'effects': [{'action': 'adjust_metric', 'metric_id': 'preference',
                                              'delta': {'parameter': 'candidate_score'}}]}],
                   'probability_provenance': {'status': 'assumed', 'rationale': 'Deterministic supplied rubric.', 'source_refs': []}}],
        'horizon_ticks': 1, 'assumptions': ['Scores are supplied judgements, not adoption probabilities.'],
    }


def field(value=75):
    return {'id': 'score', 'label': 'Candidate audience score', 'type': 'integer', 'unit': 'rubric_points',
            'required': True, 'value': value, 'minimum': 0, 'maximum': 100, 'choices': [],
            'target': '/parameters/candidate_score', 'why': 'Sets this audience assessment, not future demand.',
            'provenance': {'status': 'user_supplied', 'rationale': 'Explicit user assessment.', 'source_refs': []}}


def draft(value=75):
    package = chain()
    return {'schema_version': 'scenario-draft.v1', 'id': package['id'], 'revision': 0,
            'event_description': package['event_description'], 'fields': [field(value)], 'engine_input': package}


def test_ready_draft_compiles_exact_values_without_changing_inputs():
    value = draft(82)
    before = deepcopy(value)
    result = compile_draft(value)
    assert result['ready'] and result['issues'] == []
    assert result['package']['parameters']['candidate_score'] == 82
    assert len(result['package_sha256']) == 64
    assert value == before
    report = run_package(result['package'], worlds=2, seed=17)
    assert report['usage']['model_calls'] == 0
    assert report['input_sha256'] == result['package_sha256']
    assert report['execution_input'] == result['package']
    assert report['run_identity']['seed'] == 17
    assert report['run_identity']['worlds'] == 2
    assert len(report['run_identity']['engine_sha256']) == 64
    assert report['run_sha256'] != run_package(result['package'], worlds=2, seed=18)['run_sha256']
    assert report == run_package(result['package'], worlds=2, seed=17)


def test_missing_required_value_is_a_question_not_an_assumption():
    value = draft(None)
    value['engine_input']['parameters']['candidate_score'] = None
    result = compile_draft(value)
    assert not result['ready'] and result['package'] is None
    assert result['draft_valid'] and result['issues'][0]['code'] == 'missing'
    assert any(issue['path'] == '/fields/0/value' and issue['code'] == 'missing' for issue in result['issues'])


def test_run_identity_accepts_the_modules_full_seed_range():
    report = run_package(chain(), worlds=1, seed=10**15+1)
    assert report['run_identity']['seed'] == 10**15+1
    assert len(report['run_sha256']) == 64


@pytest.mark.parametrize('value', [True, 1.0, -1, 101, '75'])
def test_field_integer_types_and_bounds_are_enforced(value):
    result = compile_draft(draft(value))
    assert not result['ready']
    assert any(issue['path'] == '/fields/0/value' for issue in result['issues'])


@pytest.mark.parametrize('target', ['/parameters/not-declared', '/rules/0', 'parameters/candidate_score', '/parameters/~2bad'])
def test_fields_cannot_create_unknown_paths_or_modify_arrays(target):
    value = draft()
    value['fields'][0]['target'] = target
    assert not compile_draft(value)['ready']


def test_duplicate_and_overlapping_target_fields_rejected():
    value = draft()
    value['fields'].append({**field(), 'id': 'score-copy'})
    assert not compile_draft(value)['ready']


def test_informational_optional_field_has_no_executable_effect():
    value = draft()
    value['fields'].append({**field(None), 'id': 'notes', 'type': 'text', 'unit': None,
                            'required': False, 'minimum': None, 'maximum': None, 'target': None})
    result = compile_draft(value)
    assert result['ready']
    assert result['package'] == chain()


def test_optional_mapped_null_cannot_reuse_a_hidden_previous_value():
    value = draft(None)
    value['fields'][0]['required'] = False
    result = compile_draft(value)
    assert not result['ready'] and result['package'] is None


@pytest.mark.parametrize('many_missing', [False, True])
def test_incomplete_response_does_not_hide_malformed_fields(many_missing):
    current = draft()
    revised = draft(None)
    revised['revision'] = 1
    if many_missing:
        revised['fields'] = [{**field(None), 'id': f'field-{i}', 'target': None} for i in range(64)]
        revised['fields'].append({'private': 'not a valid field'})
    else:
        revised['engine_input'] = None
        revised['fields'] = [{'private': 'not a valid field'}]
    response = {'schema_version':'scenario-authoring-response.v1','base_revision':0,
                'base_sha256':draft_digest(current),'draft':revised}
    with pytest.raises(ValueError):
        apply_authoring_response(current,response)


@pytest.mark.parametrize('engine_input', [[], 'unknown', {'schema_version':'unimplemented-lending.v1'}])
def test_missing_context_does_not_hide_an_invalid_engine_envelope(engine_input):
    value = draft()
    value['fields'] = [{**field(None), 'id':'missing-context', 'type':'text', 'unit':None,
                        'minimum':None, 'maximum':None, 'target':None}]
    value['engine_input'] = engine_input
    result = compile_draft(value)
    assert not result['ready'] and not result['draft_valid']


def test_unsupported_module_and_context_mismatch_are_explicit():
    value = draft()
    value['engine_input']['schema_version'] = 'unimplemented-lending.v1'
    result = compile_draft(value)
    assert not result['ready'] and any(issue['code'] == 'unsupported_module' for issue in result['issues'])
    value = draft()
    value['event_description'] = 'Another scenario'
    result = compile_draft(value)
    assert not result['ready'] and any(issue['code'] == 'context_mismatch' for issue in result['issues'])


def test_guidelines_cover_incentives_information_dependencies_and_no_fake_calibration():
    text = authoring_guidelines().lower()
    for phrase in ['incentives', 'information', 'conditional', 'independence', 'calibration', 'population', 'equilibrium']:
        assert phrase in text
    declared = capabilities()
    assert declared['model_calls'] == 0
    assert {row['schema_version'] for row in declared['modules']} == {'event-chain.v1', 'explicit-launch.v1', 'choice-world.v1'}


def test_authoring_request_exports_messages_but_no_transport_and_unknowns_stay_null():
    value = draft(None)
    request = prepare_authoring_request(value, model='user-selected-agent')
    assert request['draft_sha256'] == draft_digest(value)
    assert request['draft_revision'] == 0
    assert request['usage']['model_calls'] == 0
    assert request['model'] == 'user-selected-agent'
    assert json.loads(request['messages'][1]['content'])['fields'][0]['value'] is None


def test_stale_or_wrong_draft_response_cannot_overwrite_user_edits():
    current = draft()
    revised = draft(85)
    revised['revision'] = 1
    response = {'schema_version': 'scenario-authoring-response.v1', 'base_revision': 0,
                'base_sha256': draft_digest(current), 'draft': revised}
    assert apply_authoring_response(current, response) == revised
    changed = draft(90)
    with pytest.raises(ValueError, match='stale'):
        apply_authoring_response(changed, response)
    revised['id'] = 'unrelated'
    with pytest.raises(ValueError):
        apply_authoring_response(current, response)


def test_validation_errors_do_not_echo_confidential_values():
    value = draft()
    value['fields'][0]['value'] = 'PRIVATE-LAUNCH-PLAN-SECRET'
    result = compile_draft(value)
    assert 'PRIVATE-LAUNCH' not in json.dumps(result)
    assert result['package'] is None


@pytest.mark.parametrize('value', [None, [], {'schema_version': 'unknown'}, {'schema_version': 'scenario-draft.v1'}])
def test_invalid_drafts_return_bounded_structured_diagnostics(value):
    result = compile_draft(value)
    assert not result['ready'] and result['issues']
    assert all(set(issue) == {'path', 'code', 'message'} for issue in result['issues'])


def test_authored_examples_compile_and_execute_as_their_declared_modules():
    examples = Path(__file__).parents[1]/'examples'
    for name in ['ticker-evaluation-draft.v1.json','defi-stress-draft.v1.json']:
        value = json.loads((examples/name).read_text())
        compilation = compile_draft(value)
        assert compilation['ready'], compilation['issues']
        report = run_package(compilation['package'],worlds=3,seed=42)
        assert report['usage']['model_calls'] == 0
        assert len(report['world_results']) == 3
    launch = json.loads((examples/'launch-explicit.v1.json').read_text())
    report = run_package(launch,worlds=3,seed=42)
    assert report['cast']['selected_count'] == 6
    assert all(row['initial_totals'] == row['ending_totals'] for row in report['worlds'])
    assert len(report['variant_selections']) == 3
    empty = json.loads((examples/'scenario-draft.empty.v1.json').read_text())
    assert not compile_draft(empty)['ready']
    assert prepare_authoring_request(empty,'any-agent')['usage']['model_calls'] == 0


def test_choice_world_draft_compiles_and_batch_dispatches():
    value = json.loads((Path(__file__).parents[1]/'examples/choice-world-draft.v1.json').read_text())
    compilation = compile_draft(value)
    assert compilation['ready'], compilation['issues']
    result = run_package(compilation['package'],worlds=10,seed=42)
    assert result['schema_version'] == 'choice-world-results.v1'
    assert sum(row['count'] for row in result['paths']) == 10
    assert result['usage']['model_calls'] == 0
    assert result == run_package(result['execution_input'],worlds=10,seed=42)
