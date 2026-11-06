"""Decision insights are replayed arithmetic, not generated recommendations."""
from copy import deepcopy
import json

import pytest

from decision_lab.strategic_worlds import StrategicWorld
from test_strategic_worlds import decisions, world
from test_strategic_scale import cast


def completed(value=None, actions=None, index=0):
    value = world() if value is None else value
    engine = StrategicWorld(value)
    while engine.observations():
        selected = decisions(engine)
        for actor, action in (actions or {}).get(engine.round, {}).items():
            selected[actor]['action_id'] = action
        engine.advance(selected)
    return {'world_index': index, 'result': engine.report(), 'decisions': []}


def snapshot(entries):
    return {'proposal': {'world': entries[0]['result']['world']}, 'results': entries}


def insights(value):
    from decision_lab.product_insights import build_insights
    return build_insights(value)


def test_reconciles_actual_action_costs_for_actors_worlds_and_aggregate():
    entries = [completed(actions={1: {'alice': 'build', 'bob': 'build'}}),
               completed(index=1)]
    source = snapshot(entries)
    before = deepcopy(source)
    result = insights(source)
    assert result['schema_version'] == 'decision-insights.v1'
    assert result['source']['completed_worlds'] == 2
    assert result['source']['replay_verified'] is True
    assert result['source']['model_requests'] == 0
    assert any('Jev returns no reasoning trace' in note for note in result['caveats'])
    resource = result['resources']
    assert resource['status'] == 'computed'
    assert resource['aggregate'] == {'initial_cash_cents': '400', 'action_cost_cents': '120',
        'remaining_cash_cents': '280', 'reconciled': True}
    assert resource['worlds'][0] == {'world_index': 0, 'initial_cash_cents': '200',
        'action_cost_cents': '120', 'remaining_cash_cents': '80', 'reconciled': True}
    alice = resource['actors'][0]
    assert alice['id'] == 'alice'
    assert alice['aggregate']['remaining_cash_cents'] == '140'
    assert alice['worlds'][0]['action_cost_cents'] == '60'
    assert all(a['aggregate']['reconciled'] for a in resource['actors'])
    assert 'revenue' in resource['meaning'].lower()
    assert 'AMM' in resource['meaning'] and 'profit' in resource['meaning']
    assert source == before
    json.dumps(result, allow_nan=False)


def test_exact_one_round_game_shows_incentives_without_invented_beliefs():
    value = world(); value['rounds'] = 1; value['events'] = []
    for actor in value['actors']:
        actor['actions'][1]['effects'] = {}
    result = insights(snapshot([completed(value, {1: {'alice': 'build'}})]))
    game = result['strategic']
    assert game['status'] == 'computed' and game['profile_count'] == 4
    assert game['strategy_beliefs'] is None
    assert game['pure_nash_profiles'] == [{'alice': 'wait', 'bob': 'wait'}]
    assert game['strictly_dominated_actions'] == [
        {'player_id': 'alice', 'action_id': 'build', 'dominating_action_ids': ['wait']},
        {'player_id': 'bob', 'action_id': 'build', 'dominating_action_ids': ['wait']}]
    observed = game['observed_profiles'][0]
    assert observed['is_pure_nash'] is False
    alice = observed['actors'][0]
    assert alice == {'id': 'alice', 'selected_action_id': 'build', 'selected_utility': '50',
        'best_response_action_ids': ['wait'], 'best_response_utility': '110',
        'unilateral_improvement_utility': '60', 'selected_cost_cents': '60',
        'best_responses': [{'action_id': 'wait', 'cost_cents': '0'}]}
    assert 'forecast' in ' '.join(game['limitations']).lower()
    assert 'complete-information' in game['scope']


def test_zero_completed_worlds_do_not_become_zero_cost_outcomes_or_equilibria():
    result = insights({'results': [], 'proposal': {'world': world()}})
    assert result['source']['completed_worlds'] == 0
    assert result['source']['replay_verified'] is False
    assert result['resources']['status'] == 'not_computed'
    assert result['resources']['aggregate'] is None
    assert result['resources']['actors'] == []
    assert result['strategic']['status'] == 'not_computed'
    assert 'completed' in result['strategic']['reason']


@pytest.mark.parametrize('value,reason', [(world(), 'round'), (cast(20, 1), 'four')])
def test_unsupported_game_size_or_horizon_keeps_exact_resources(value, reason):
    result = insights(snapshot([completed(value)]))
    assert result['resources']['status'] == 'computed'
    assert result['strategic']['status'] == 'not_computed'
    assert reason in result['strategic']['reason']


def test_payoff_overflow_is_explicit_and_cash_never_becomes_float():
    value = world(); value['rounds'] = 1; value['events'] = []
    for actor in value['actors']:
        actor['initial_cash_cents'] = 10**12
        actor['utility_weights']['cash_cents'] = 10**6
    result = insights(snapshot([completed(value)]))
    assert result['resources']['aggregate']['initial_cash_cents'] == '2000000000000'
    assert result['strategic']['status'] == 'not_computed'
    assert 'payoff bound' in result['strategic']['reason']
    assert '1000000000000000010' not in json.dumps(result)  # no rounded utility leakage


@pytest.mark.parametrize('mutate', [
    lambda s: s['results'][0]['result']['actor_results']['alice'].update(cash_cents=99),
    lambda s: s['results'][0]['result'].update(total_cost_cents=1),
    lambda s: s['results'][0]['result']['rounds'][0]['receipts']['alice'].update(cost_cents=1),
    lambda s: s['results'][0]['result'].update(engine_sha256='0' * 64),
    lambda s: s['proposal']['world'].update(title='Different world'),
    lambda s: s['results'].append(deepcopy(s['results'][0])),
    lambda s: s['results'][0].update(world_index=True),
])
def test_tampered_results_or_mismatched_identity_are_rejected(mutate):
    source = snapshot([completed()]); mutate(source)
    with pytest.raises(ValueError):
        insights(source)


def test_incomplete_world_and_excessive_results_are_rejected():
    entry = {'world_index': 0, 'result': StrategicWorld(world()).report(), 'decisions': []}
    with pytest.raises(ValueError, match='completed'):
        insights(snapshot([entry]))
    with pytest.raises(ValueError):
        insights({'results': [completed(index=i) for i in range(5)]})


def test_100_actor_execution_has_bounded_json_and_no_equilibrium_enumeration():
    result = insights(snapshot([completed(cast(100, 1))]))
    assert len(result['resources']['actors']) == 100
    assert result['resources']['aggregate']['initial_cash_cents'] == '10000'
    assert result['strategic']['status'] == 'not_computed'
    assert len(json.dumps(result)) < 200000


def test_presentation_carries_identical_insights_without_changing_five_slides():
    from decision_lab.scenario_presentation import build_presentation
    from test_scenario_presentation import snapshot as presentation_snapshot
    source = presentation_snapshot()
    deck = build_presentation(source)
    assert deck['decision_insights'] == insights(source)
    assert len(deck['slides']) == 5
    assert [slide['id'] for slide in deck['slides']] == ['overview', 'outcomes', 'resources', 'scenarios', 'evidence']


def test_report_data_markdown_and_pdf_include_reconciliation_and_actual_incentives():
    from decision_lab.product_reports import report_data, markdown, pdf, pdf_available
    value = world(); value['rounds'] = 1; value['events'] = []
    for actor in value['actors']:
        actor['actions'][1]['effects'] = {}
    source = snapshot([completed(value, {1: {'alice': 'build'}})])
    source['status'] = 'completed'
    data = report_data(source)
    assert data['decision_insights'] == insights(source)
    text = markdown(data).decode()
    assert '## Decision insights' in text
    assert r'200 \- 60 = 140 cents' in text
    assert 'Pure Nash profiles: 1' in text
    assert 'alice: wait' in text
    assert 'Strictly dominated actions: 2' in text
    assert 'unilateral improvement: 60 utility points' in text
    assert 'No revenue' in text and 'AMM' in text
    if pdf_available():
        raw = pdf(data)
        assert raw.startswith(b'%PDF-')
        # The PDF's embedded content stream is compressed; inspect the local
        # story's actual paragraph text through a standard PDF reader if present.
        try:
            from pypdf import PdfReader
        except ImportError:
            return
        from io import BytesIO
        extracted = ' '.join(page.extract_text() for page in PdfReader(BytesIO(raw)).pages)
        assert 'Decision insights' in extracted and '200 - 60 = 140 cents' in extracted
        assert 'Pure Nash profiles: 1' in extracted


def test_zero_completed_export_names_missing_analysis_and_never_claims_reconciliation():
    from decision_lab.product_reports import report_data, markdown
    source = {'proposal': {'world': world()}, 'results': [], 'status': 'failed'}
    text = markdown(report_data(source)).decode()
    assert '## Decision insights' in text
    assert 'No completed recorded worlds' in text
    assert 'Reconciled' not in text


@pytest.mark.parametrize('case,reason', [('profiles', '256'), ('affordability', 'affordable')])
def test_exact_analysis_reports_profile_and_affordability_caps(case, reason):
    value = cast(4, 1)
    if case == 'profiles':
        for actor in value['actors']:
            for index in range(2, 8):
                action = deepcopy(actor['actions'][1]); action['id'] = f'act-{index}'
                actor['actions'].append(action)
    else:
        value['actors'][0]['initial_cash_cents'] = 0
    game = insights(snapshot([completed(value)]))['strategic']
    assert game['status'] == 'not_computed'
    assert reason in game['reason']


def test_multiround_opening_game_excludes_future_effects_and_preserves_settlement():
    from decision_lab.strategic_worlds import replay_strategic_world, strategic_game
    source = snapshot([completed(actions={1: {'alice': 'build'}, 2: {'bob': 'build'}})])
    original = deepcopy(source)
    result = insights(source)
    assert result['strategic']['status'] == 'not_computed'
    opening = result['opening_game']
    assert opening['status'] == 'computed' and opening['profile_count'] == 4
    assert opening['strategy_beliefs'] is None
    assert 'FIRST ROUND ONLY' in opening['scope']
    assert 'future messages, events and commitments' in opening['scope']
    assert 'not a full-world equilibrium' in opening['scope']
    existing = strategic_game(source['proposal']['world'])
    assert opening['pure_nash_profiles'] == existing['analysis']['pure_nash_profiles']
    assert opening['game_sha256'] == existing['analysis']['game_sha256']
    assert opening['observed_profiles'][0]['actions'] == {'alice': 'build', 'bob': 'wait'}
    # Opening metrics are 2 + 6 = 8: utility 40 + 80 = 120.
    # The round-two event and Bob's later build must not enter that utility.
    assert opening['observed_profiles'][0]['actors'][0]['selected_utility'] == '120'
    assert source == original
    assert replay_strategic_world(source['results'][0]['result']) == original['results'][0]['result']
    changed = world(); changed['events'][1]['effects']['readiness'] = -9
    altered = insights(snapshot([completed(changed, {1: {'alice': 'build'}, 2: {'bob': 'build'}})]))
    assert altered['opening_game'] == opening
    assert altered['resources'] == result['resources']


def test_opening_game_one_round_reuses_supported_analysis_and_large_world_stays_honest():
    value = world(); value['rounds'] = 1; value['events'] = []
    one = insights(snapshot([completed(value)]))
    assert one['opening_game'] == one['strategic']
    large = insights(snapshot([completed(cast(20, 2))]))
    assert large['opening_game']['status'] == 'not_computed'
    assert 'four' in large['opening_game']['reason']
    assert large['opening_game']['strategy_beliefs'] is None
    empty = insights({'results': []})
    assert empty['opening_game']['status'] == 'not_computed'
    assert empty['opening_game']['observed_profiles'] == []


def test_multiround_report_includes_separately_labeled_opening_diagnostic():
    from decision_lab.product_reports import report_data, markdown
    source = snapshot([completed()]); source['status'] = 'completed'
    data = report_data(source)
    text = markdown(data).decode()
    assert 'Static strategic analysis not computed' in text
    assert 'Opening game diagnostic' in text
    assert 'FIRST ROUND ONLY' in text
    assert 'Pure Nash profiles:' in text
    assert 'future messages, events and commitments' in text


def test_actual_near_two_round_demo_has_opening_incentives_and_exact_resources():
    from decision_lab.near_demo import build_near_demo, rehearse_near_demo
    from test_wallet_evidence import snapshot as evidence_snapshot
    demo = build_near_demo(evidence_snapshot())
    rehearsal = rehearse_near_demo(demo)
    entries = [{'world_index': index, 'result': branch['result']}
               for index, branch in enumerate(rehearsal['branches'])]
    source = snapshot(entries); original = deepcopy(source)
    result = insights(source)
    assert source['proposal']['world']['rounds'] == 2
    assert result['strategic']['status'] == 'not_computed'
    assert result['opening_game']['status'] == 'computed'
    assert result['opening_game']['profile_count'] == 9
    assert len(result['opening_game']['observed_profiles']) == 4
    assert result['opening_game']['strategy_beliefs'] is None
    assert result['resources']['aggregate']['reconciled'] is True
    assert result['source']['model_requests'] == rehearsal['model_requests'] == 0
    assert source == original
