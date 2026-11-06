"""Matched comparisons reject misleading controls and recompute financial outcomes."""
from copy import deepcopy

import pytest

from decision_lab.agent_worlds import AgentWorld, digest, ENGINE_SHA256
from decision_lab.decision_analysis import ANALYSIS_ENGINE_SHA256
from decision_lab.decision_evidence import build_evidence_context, brief_evidence
from decision_lab.decision_comparisons import compare_decisions, render_comparison_report


def member(label='Baseline', *, lp_cash=400000, fee=30, exit_tokens=1000000,
           reason='Observe supplied event.', mutate_world=None):
    world = {'schema_version': 'agent-world.v1', 'id': 'matched-world',
        'event_description': 'Fictional NEAR event held fixed for comparison.', 'network': 'near', 'rounds': 1,
        'market': {'project_capital_cents': 1000000, 'launch_cost_cents': 100000,
                   'lp_cash_cents': lp_cash, 'project_token_units': 3000000,
                   'lp_token_units': 1000000, 'fee_bps': fee, 'max_slippage_bps': 500},
        'agents': [{'id': 'observer', 'name': 'Observer', 'role': 'analyst',
                    'description': 'Explicitly fictional observer.', 'goal': 'Observe evidence before spending.',
                    'initial_cash_cents': 100000, 'position_limit_cents': 100000,
                    'allowed_actions': ['hold'], 'attention_capacity': 1, 'subscriptions': ['news']}],
        'events': [{'id': 'opening', 'round': 1, 'text': 'Fictional launch information.', 'provenance': 'assumed'}],
        'assumptions': ['No measured buyer demand or outcome odds.']}
    if mutate_world:
        mutate_world(world)
    engine = AgentWorld(world, seed=42)
    for _ in range(world['rounds']):
        turns = []
        for obs in engine.observations().values():
            turns.append({'schema_version': 'agent-turn.v1', 'actor_id': obs['actor']['id'],
                          'round': obs['round'], 'observation_sha256': obs['observation_sha256'],
                          'action': {'kind': 'hold', 'amount': 0, 'evidence_ids': []},
                          'message': None, 'reason': reason})
        engine.advance(turns)
    result = engine.report()
    brief = {key: deepcopy(world[key]) for key in ('id', 'event_description', 'network', 'rounds', 'market', 'events', 'assumptions')}
    brief.update(schema_version='agent-world-brief.v1', evidence=[], slots=[
        {key: deepcopy(a[key]) for key in ('id', 'role', 'initial_cash_cents', 'position_limit_cents', 'allowed_actions', 'attention_capacity')} | {'required_sources': deepcopy(a['subscriptions'])} for a in world['agents']])
    evidence = build_evidence_context()
    brief['evidence'] = brief_evidence(evidence)
    proposal = {'schema_version': 'decision-proposal.v1', 'context_sha256': 'a' * 64,
                'decision_type': 'launch', 'summary': 'Compare explicitly supplied launch assumptions.',
                'questions': [], 'brief': brief, 'exit_token_units': exit_tokens,
                'assumptions': ['Hypothetical endowments.'], 'limitations': ['Not a forecast.']}
    review = {'schema_version': 'decision-review.v1', 'revision': 1, 'proposal_sha256': digest(proposal),
              'evidence_sha256': evidence['context_sha256'], 'engine_sha256': ENGINE_SHA256,
              'analysis_engine_sha256': ANALYSIS_ENGINE_SHA256,
              'route': {'model': 'fixture-model', 'adapter': 'Fixture'}, 'seed': 42,
              'max_calls': 2, 'required_model_calls': 1 + len(world['agents']) * world['rounds'],
              'max_external_cash_cents': 100000000, 'project_capital_cents': world['market']['project_capital_cents'],
              'outside_actor_cash_cents': sum(a['initial_cash_cents'] for a in world['agents']),
              'brief': brief, 'exit_token_units': exit_tokens, 'limitations': ['No real outcome odds.']}
    review['max_calls'] = review['required_model_calls']
    review['review_sha256'] = digest(review)
    state = {'schema_version': 'decision-session.v1', 'revision': 1, 'network': world['network'],
             'question': 'Should I launch?', 'proposal': proposal, 'evidence_context': evidence,
             'status': 'completed', 'execution_review': review, 'run_path': 'run-' + 'a' * 32}
    state['state_sha256'] = digest(state)
    required = review['required_model_calls']
    manifest = {'schema_version': 'agent-live-run.v1', 'status': 'completed',
                'world_sha256': result['world_sha256'], 'seed': 42,
                'required_calls': required, 'max_calls': required, 'attempted_calls': required,
                'completed_calls': required, 'completed_rounds': world['rounds'],
                'calls': [{'index': i + 1, 'status': 'response_received',
                           'receipt': {'model_declared': 'fixture-model'}} for i in range(required)],
                'cost_usd': None, 'error': None}
    return {'label': label, 'state': state, 'manifest': manifest, 'result': result}


def resign(value):
    state = value['state']
    review = state['execution_review']
    review['proposal_sha256'] = digest(state['proposal'])
    review['brief'] = deepcopy(state['proposal']['brief'])
    review.pop('review_sha256', None)
    review['review_sha256'] = digest(review)
    state.pop('state_sha256', None)
    state['state_sha256'] = digest(state)


def test_comparison_recomputes_cash_and_descriptive_deltas_without_mutation():
    members = [member(), member('Smaller pool', lp_cash=200000)]
    before = deepcopy(members)
    result = compare_decisions(members)
    assert members == before
    assert result['schema_version'] == 'decision-comparison.v1'
    assert result['baseline_label'] == 'Baseline'
    assert result['probability_status'] == result['provider_cost_status'] == 'unknown'
    assert result['rows'][0]['analysis']['no_launch']['profit_cents'] == 0
    alternative = result['rows'][1]
    assert alternative['analysis']['actual']['ending_cash_cents'] == 700000
    assert alternative['deltas']['actual_cash_profit_cents'] == 200000
    assert alternative['deltas']['locked_lp_cash_deposit_cents'] == -200000
    assert alternative['input_changes'] == [{'field': 'lp_cash_cents', 'baseline': 400000, 'value': 200000}]
    assert result['controls']['seed'] == 42 and result['controls']['network'] == 'near'
    assert result == compare_decisions(deepcopy(members))


def test_only_exit_quantity_and_fee_changes_are_explicit():
    result = compare_decisions([member(), member('Alternative', fee=100, exit_tokens=500000)])
    assert {row['field'] for row in result['rows'][1]['input_changes']} == {'fee_bps', 'exit_token_units'}
    assert result['rows'][1]['analysis']['hypothetical_exit']['exit_token_units'] == 500000


@pytest.mark.parametrize('mutate', [
    lambda w: w['agents'][0].update(description='A different behavioral description.'),
    lambda w: w['agents'][0].update(initial_cash_cents=200000),
    lambda w: w['agents'][0].update(subscriptions=[]),
    lambda w: w.update(network='solana'), lambda w: w.update(event_description='Different event.'),
    lambda w: w['events'][0].update(text='Different scheduled event.'),
    lambda w: w.update(rounds=2),
    lambda w: w['market'].update(project_capital_cents=2000000),
    lambda w: w['market'].update(project_token_units=4000000),
])
def test_mismatched_matched_controls_rejected(mutate):
    with pytest.raises(ValueError):
        compare_decisions([member(), member('Changed', lp_cash=200000, mutate_world=mutate)])


@pytest.mark.parametrize('change', [
    lambda m: m['state'].update(status='failed'),
    lambda m: m['state'].update(state_sha256='f' * 64),
    lambda m: m['manifest'].update(status='failed'),
    lambda m: m['manifest'].update(world_sha256='f' * 64),
    lambda m: m['manifest'].update(seed=43),
    lambda m: m['result']['balances']['project'].update(cash_cents=1),
    lambda m: m['state']['execution_review'].update(review_sha256='f' * 64),
])
def test_incomplete_tampered_or_unbound_sources_rejected(change):
    changed = member('Alternative', lp_cash=200000)
    change(changed)
    with pytest.raises(ValueError): compare_decisions([member(), changed])


def test_fresh_same_world_outputs_allowed_but_duplicate_trajectory_rejected():
    with pytest.raises(ValueError, match='duplicate'):
        compare_decisions([member(), member('Same result')])
    fresh = member('Fresh independent decisions', reason='Independent freshly generated hold reason.')
    result = compare_decisions([member(), fresh])
    assert result['rows'][1]['source']['world_sha256'] == result['rows'][0]['source']['world_sha256']
    assert result['rows'][1]['source']['result_sha256'] != result['rows'][0]['source']['result_sha256']
    assert result['rows'][1]['input_changes'] == []


@pytest.mark.parametrize('field,value', [('seed', 43), ('route', {'model': 'other', 'adapter': 'Fixture'}),
                                          ('max_external_cash_cents', 1)])
def test_review_controls_rejected_even_with_fresh_checksums(field, value):
    alternative = member('Alternative', lp_cash=200000)
    alternative['state']['execution_review'][field] = value
    if field == 'seed': alternative['manifest']['seed'] = value
    resign(alternative)
    with pytest.raises(ValueError): compare_decisions([member(), alternative])


def test_evidence_content_not_just_network_must_match():
    alternative = member('Alternative', lp_cash=200000)
    context = alternative['state']['evidence_context']
    context['as_of'] = '2026-10-25T00:00:00Z'
    context.pop('context_sha256')
    from decision_lab.decision_evidence import _digest
    context['context_sha256'] = _digest(context)
    alternative['state']['execution_review']['evidence_sha256'] = context['context_sha256']
    resign(alternative)
    with pytest.raises(ValueError): compare_decisions([member(), alternative])


def test_unreviewed_exit_or_brief_change_rejected():
    for field, value in [('exit_token_units', 500000), ('brief', None)]:
        alternative = member('Alternative', lp_cash=200000)
        alternative['state']['proposal'][field] = value
        alternative['state'].pop('state_sha256')
        alternative['state']['state_sha256'] = digest(alternative['state'])
        with pytest.raises(ValueError): compare_decisions([member(), alternative])


@pytest.mark.parametrize('members', [[], [member()], [member(str(i), lp_cash=100000 + i) for i in range(9)],
                                     [member(), {'label': 'bad'}]])
def test_count_and_structure_bounds(members):
    with pytest.raises(ValueError): compare_decisions(members)


def test_render_is_safe_deterministic_and_disclaims_probability_and_ranking():
    comparison = compare_decisions([member('# Baseline\n[run](javascript:1)'), member('Smaller | pool', lp_cash=200000)])
    text = render_comparison_report(comparison)
    assert text == render_comparison_report(deepcopy(comparison))
    assert '# Baseline' not in text and '[run](' not in text
    assert 'Smaller | pool' not in text
    assert '$2,000.00' in text
    assert 'not a causal' in text and 'probabilities are unknown' in text
    assert 'No launch' in text and 'Provider cost' in text
    changed = deepcopy(comparison)
    changed['rows'][1]['analysis']['actual']['cash_profit_cents'] += 1
    with pytest.raises(ValueError): render_comparison_report(changed)


def test_branch_prepared_cast_review_is_required_and_validated():
    baseline = member()
    child = member('Reused cast', lp_cash=200000)
    review = child['state']['execution_review']
    review['construction_mode'] = 'reuse_reviewed_cast'
    review['prepared_world_sha256'] = child['result']['world_sha256']
    review['required_model_calls'] = 1
    review['max_calls'] = 1
    child['state']['comparison_parent'] = {'source_result_sha256': digest(baseline['result'])}
    manifest = child['manifest']
    for key in ('required_calls', 'max_calls', 'attempted_calls', 'completed_calls'):
        manifest[key] = 1
    manifest['calls'] = manifest['calls'][:1]
    resign(child)
    result = compare_decisions([baseline, child])
    assert result['rows'][1]['analysis']['actual']['ending_cash_cents'] == 700000
    review['prepared_world_sha256'] = 'f' * 64
    resign(child)
    with pytest.raises(ValueError, match='prepared world'):
        compare_decisions([baseline, child])


def test_optional_question_does_not_invalidate_executed_review():
    child = member('Optional question', lp_cash=200000)
    child['state']['proposal']['questions'] = [{'id': 'future', 'prompt': 'Further research?',
                                              'choices': [], 'required': False}]
    resign(child)
    assert compare_decisions([member(), child])['rows'][1]['label'] == 'Optional question'
    child['state']['proposal']['questions'][0]['required'] = True
    resign(child)
    with pytest.raises(ValueError): compare_decisions([member(), child])


@pytest.mark.parametrize('change', [
    lambda m: m['manifest']['calls'][0]['receipt'].update(model_declared='another-model'),
    lambda m: m['manifest'].update(completed_calls=1),
    lambda m: m['manifest'].update(error={'code': 'failure'}),
    lambda m: m['state'].update(result_sha256='f' * 64),
    lambda m: m['state']['execution_review'].update(prepared_world_sha256='f' * 64),
])
def test_source_receipts_and_optional_artifact_hashes_remain_bound(change):
    child = member('Changed', lp_cash=200000)
    change(child)
    resign(child)
    with pytest.raises(ValueError): compare_decisions([member(), child])


def test_render_rejects_rehashed_false_arithmetic_and_bounds():
    original = compare_decisions([member(), member('Smaller pool', lp_cash=200000)])
    for change in (lambda c: c['rows'][1]['deltas'].update(actual_cash_profit_cents=1),
                   lambda c: c['controls'].update(rounds=0),
                   lambda c: c['controls'].update(network='solana')):
        altered = deepcopy(original)
        change(altered)
        altered.pop('comparison_sha256')
        altered['comparison_sha256'] = digest(altered)
        with pytest.raises(ValueError): render_comparison_report(altered)


def test_frozen_evidence_must_be_actual_reviewed_construction_attachment():
    child = member('Different builder evidence', lp_cash=200000)
    child['state']['proposal']['brief']['evidence'] = []
    resign(child)
    with pytest.raises(ValueError, match='evidence attachment'):
        compare_decisions([member(), child])


def test_duplicate_labels_and_oversized_source_artifacts_rejected():
    with pytest.raises(ValueError, match='duplicate comparison label'):
        compare_decisions([member(), member(lp_cash=200000)])
    changed = member('Oversized', lp_cash=200000)
    changed['manifest']['extra'] = 'x' * (10 * 1024 * 1024)
    with pytest.raises(ValueError, match='size budget'):
        compare_decisions([member(), changed])


def test_zero_exit_or_unreachable_threshold_deltas_are_not_fabricated():
    result = compare_decisions([member(), member('No exit', lp_cash=200000, exit_tokens=0)])
    assert result['rows'][1]['analysis']['break_even']['status'] == 'no_exit_tokens'
    assert result['rows'][1]['deltas']['break_even_additional_buy_cents'] is None
    assert 'Not comparable within bounds' in render_comparison_report(result)


@pytest.mark.parametrize('question', [
    {'required': False},
    {'id': 'q', 'prompt': 'Question?', 'choices': ['one'], 'required': False},
    {'id': 'q', 'prompt': 'Question?', 'choices': [], 'required': 0},
])
def test_malformed_optional_question_cannot_enter_completed_comparison(question):
    child = member('Bad optional question', lp_cash=200000)
    child['state']['proposal']['questions'] = [question]
    resign(child)
    with pytest.raises(ValueError): compare_decisions([member(), child])


def rehash_comparison(comparison):
    baseline = comparison['rows'][0]['inputs']
    for row in comparison['rows']:
        row['input_changes'] = [{'field': key, 'baseline': baseline[key], 'value': row['inputs'][key]}
                                for key in ('launch_cost_cents', 'lp_cash_cents', 'lp_token_units',
                                            'fee_bps', 'max_slippage_bps', 'exit_token_units')
                                if row['inputs'][key] != baseline[key]]
    comparison.pop('comparison_sha256', None)
    comparison['comparison_sha256'] = digest(comparison)


def test_renderer_rejects_reviewed_overcommitment_and_impossible_fee_reproduction():
    comparison = compare_decisions([member(), member('Smaller pool', lp_cash=200000)])
    comparison['rows'][1]['inputs'].update(launch_cost_cents=900000, fee_bps=99999)
    rehash_comparison(comparison)
    with pytest.raises(ValueError): render_comparison_report(comparison)


def test_generated_comparison_retains_full_analyzed_market():
    members = [member(), member('Smaller pool', lp_cash=200000)]
    comparison = compare_decisions(members)
    assert comparison['rows'][1]['analyzed_market'] == members[1]['result']['world']['market']


@pytest.mark.parametrize('key,value', [
    ('launch_cost_cents', 999999), ('lp_cash_cents', 0), ('lp_token_units', 0),
    ('lp_token_units', 4000000), ('fee_bps', 10000), ('max_slippage_bps', 10001),
    ('fee_bps', 40), ('lp_cash_cents', 300000), ('lp_token_units', 900000),
])
def test_rehashed_display_inputs_must_match_analyzed_financial_inputs(key, value):
    comparison = compare_decisions([member(), member('Smaller pool', lp_cash=200000)])
    comparison['rows'][1]['inputs'][key] = value
    rehash_comparison(comparison)
    with pytest.raises(ValueError): render_comparison_report(comparison)


@pytest.mark.parametrize('key,value', [
    ('launch_cost_cents', 900000), ('lp_cash_cents', 0), ('lp_token_units', 0),
    ('lp_token_units', 4000000), ('fee_bps', 10000), ('max_slippage_bps', 10001),
    ('fee_bps', 40), ('project_capital_cents', 2000000), ('project_token_units', 4000000),
])
def test_full_analyzed_market_constraints_and_analysis_binding_cannot_be_rehashed_away(key, value):
    comparison = compare_decisions([member(), member('Smaller pool', lp_cash=200000)])
    row = comparison['rows'][1]
    row['analyzed_market'][key] = value
    if key in row['inputs']:
        row['inputs'][key] = value
    rehash_comparison(comparison)
    with pytest.raises(ValueError): render_comparison_report(comparison)


def test_even_coherent_display_cost_requires_consistent_actual_accounting():
    comparison = compare_decisions([member(), member('Smaller pool', lp_cash=200000)])
    row = comparison['rows'][1]
    row['inputs']['launch_cost_cents'] = 200000
    row['analyzed_market']['launch_cost_cents'] = 200000
    row['analysis']['actual']['paid_costs_cents'] = 200000
    rehash_comparison(comparison)
    with pytest.raises(ValueError): render_comparison_report(comparison)


@pytest.mark.parametrize('field', ['buy_fee_cash_cents', 'exit_fee_token_units'])
def test_rehashed_stress_retained_fee_arithmetic_must_match_analyzed_fee(field):
    comparison = compare_decisions([member(), member('Smaller pool', lp_cash=200000)])
    comparison['rows'][1]['analysis']['demand_stress'][1][field] += 1
    rehash_comparison(comparison)
    with pytest.raises(ValueError): render_comparison_report(comparison)


def test_report_exposes_both_initial_reserves_and_price_ratio_implication():
    report=render_comparison_report(compare_decisions([member(),member('Alternative',lp_cash=200000)]))
    assert 'Initial pool settings' in report
    assert '| Alternative | $2,000.00 | 1,000,000 | 30 | 500 |' in report
    assert 'changing one reserve changes the starting price' in report
