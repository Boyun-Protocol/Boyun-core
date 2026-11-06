"""Construction checks expose declared arithmetic without inventing human motives."""
from copy import deepcopy
import json

import pytest

from test_strategic_worlds import world, provenance


def audit(value=None, **kwargs):
    from decision_lab.game_construction import game_construction_audit
    return game_construction_audit(world() if value is None else value, **kwargs)


def test_own_counterfactual_uses_first_events_cash_bounds_and_exact_integer_utility():
    value = world()
    value['actors'][0]['utility_weights']['readiness'] = 20
    result = audit(value, main_actor_id='alice')
    alice = result['actors'][0]
    assert result['main_actor_id'] == 'alice'
    assert alice['own_action_counterfactuals']['baseline_metrics'] == {'readiness': 2}
    assert alice['own_action_counterfactuals']['baseline_utility'] == 140
    build = alice['own_action_counterfactuals']['actions'][1]
    assert build['action_id'] == 'build'
    assert build['metrics_after'] == {'readiness': 8}
    assert build['cash_after_cents'] == 40
    assert build['utility'] == 200 and build['utility_delta'] == 60
    assert type(build['utility_delta']) is int
    assert alice['goal'] == value['actors'][0]['goal']
    assert alice['motivation'] == value['actors'][0]['motivation']
    assert alice['utility_units']['readiness'] == 'utility points per points'
    value['metrics'][0]['initial'] = 9
    build = audit(value)['actors'][0]['own_action_counterfactuals']['actions'][1]
    assert build['metrics_after'] == {'readiness': 10}
    assert build['utility_delta'] == -60


def test_counterfactual_excludes_peer_actions_joint_effects_and_future_events():
    value = world()
    value['interactions'] = [{'id': 'together', 'when': {'alice': 'build', 'bob': 'build'},
        'effects': {'readiness': 7}, 'description': 'Joint effect.', 'provenance': provenance()}]
    result = audit(value)
    own = result['actors'][0]['own_action_counterfactuals']
    assert own['actions'][1]['metrics_after'] == {'readiness': 8}
    assert own['actions'][1]['utility_delta'] == 0
    assert own['excluded'] == ['other_actor_actions', 'joint_interaction_effects', 'future_events', 'future_rounds']
    rule = result['cross_dependencies']['joint_rules'][0]
    assert rule['id'] == 'together'
    assert rule['affected_objectives'][0]['utility_delta'] == 70
    assert result['specification']['terminal_objective'].startswith('Declared weighted utility')


def test_cross_dependencies_follow_weighted_bounded_effects_not_role_labels():
    value = world()
    value['actors'][1]['utility_weights'] = {'cash_cents': 1}
    result = audit(value)
    edges = result['cross_dependencies']['direct_edges']
    assert len(edges) == 1
    assert edges[0] == {'source_actor_id': 'bob', 'target_actor_id': 'alice',
        'action_ids': ['build'], 'metric_ids': ['readiness'], 'utility_delta_min': 0, 'utility_delta_max': 60}
    value['metrics'][0]['initial'] = 10
    assert audit(value)['cross_dependencies']['direct_edges'] == []


def test_actor_support_carries_only_own_information_and_visible_public_counterparties():
    from decision_lab.game_construction import actor_game_support
    value = world()
    value['schema_version'] = 'strategic-world.v2'
    value['actors'][0]['subscriptions'] = []
    support = actor_game_support(value, 'alice')
    encoded = json.dumps(support)
    assert support['actor_id'] == 'alice'
    assert support['actor']['information'] == 'PRIVATE-alice'
    assert support['information']['public_counterparties'] == []
    assert 'PRIVATE-bob' not in encoded and 'SECRET-FUTURE' not in encoded
    assert 'PRIVATE-EARLY' in encoded
    assert 'initial_cash_cents' not in encoded
    assert 'cross_dependencies' not in support
    value['actors'][0]['subscriptions'] = ['bob']
    support = actor_game_support(value, 'alice')
    assert support['information']['public_counterparties'][0]['id'] == 'bob'
    assert set(support['information']['public_counterparties'][0]) == {'id', 'name', 'role', 'publicactionlabels'}


def test_warnings_are_scoped_numeric_diagnostics_and_outside_option_is_explicit():
    value = world()
    value['events'] = []
    for actor in value['actors']:
        actor['utility_weights'] = {'readiness': 0}
        actor['subscriptions'] = []
        actor['actions'][1]['message'] = ''
    result = audit(value)
    codes = {(warning['code'], warning.get('actor_id')) for warning in result['warnings']}
    assert ('zero_utility_weights', 'alice') in codes
    assert ('no_distinct_own_action_utility', 'alice') in codes
    assert ('no_initial_objective_coupling', 'alice') in codes
    assert ('no_possible_peer_messages', 'alice') in codes
    assert result['actors'][0]['outside_option']['action_id'] == 'wait'
    assert result['actors'][0]['outside_option']['external_exit_modeled'] is False


def test_unaffordable_actions_never_rank_as_feasible_own_choices():
    value = world()
    value['actors'][0]['initial_cash_cents'] = 50
    choices = audit(value)['actors'][0]['own_action_counterfactuals']
    assert choices['affordable_action_ids'] == ['wait']
    assert choices['actions'][1]['affordable'] is False
    assert choices['actions'][1]['utility'] is None
    assert choices['actions'][1]['utility_delta'] is None
    assert ('one_affordable_action', 'alice') in {
        (warning['code'], warning.get('actor_id')) for warning in audit(value)['warnings']}


def test_count_and_capital_are_representations_without_population_inference():
    from test_strategic_scale import cast
    result = audit(cast(100))
    assert result['representation']['actor_count'] == 100
    assert result['representation']['role_counts'] == {'Builder': 100}
    assert result['representation']['population_estimate'] is None
    assert result['economics']['total_initial_cash_cents'] == 10000
    assert result['economics']['capital_allocation_cents']['actor-99'] == 100
    assert len(result['actors']) == 100
    assert result['main_actor_id'] is None


def test_provenance_is_assumption_attribution_and_return_is_detached():
    value = world()
    value['actors'][0]['provenance']['source_refs'] = ['https://example.test/context']
    before = deepcopy(value)
    result = audit(value)
    assert result['provenance']['status_counts']['assumed'] == 9
    assert result['provenance']['source_refs'] == ['https://example.test/context']
    assert result['provenance']['evidence_verification'] == 'not_performed'
    result['actors'][0]['utility_weights']['readiness'] = 999
    assert value == before
    assert audit(value)['actors'][0]['utility_weights']['readiness'] == 10


def test_validation_and_main_actor_identity_are_strict():
    from decision_lab.game_construction import actor_game_support
    with pytest.raises(ValueError):
        audit({'schema_version': 'strategic-world.v1'})
    with pytest.raises(ValueError, match='main actor'):
        audit(main_actor_id='not-present')
    with pytest.raises(ValueError, match='actor'):
        actor_game_support(world(), 'not-present')


def test_construction_guidelines_cover_unmodeled_beliefs_and_stable_economics():
    from decision_lab.game_construction import GAME_CONSTRUCTION_GUIDELINES
    assert 'Jev' in GAME_CONSTRUCTION_GUIDELINES
    assert 'terminal' in GAME_CONSTRUCTION_GUIDELINES
    assert 'population' in GAME_CONSTRUCTION_GUIDELINES
    assert 'belief' in GAME_CONSTRUCTION_GUIDELINES


def test_last_round_messages_cannot_create_a_communication_observation():
    value = world()
    value['rounds'] = 1
    value['events'] = []
    codes = {(warning['code'], warning.get('actor_id')) for warning in audit(value)['warnings']}
    assert ('no_possible_peer_messages', 'alice') in codes


def test_large_declared_utility_is_exact_and_motive_text_does_not_change_it():
    value = world()
    value['actors'][0]['initial_cash_cents'] = 10**12
    value['actors'][0]['utility_weights'] = {'cash_cents': 10**6, 'readiness': -10**6}
    first = audit(value)['actors'][0]['own_action_counterfactuals']
    assert first['baseline_utility'] == 10**18 - 2 * 10**6
    assert first['actions'][1]['utility_delta'] == -66 * 10**6
    value['actors'][0]['motivation'] = 'Maximize readiness at any cost.'
    assert audit(value)['actors'][0]['own_action_counterfactuals'] == first


def test_dense_100_actor_audit_is_bounded_with_explicit_omissions_and_exact_counts():
    from decision_lab.agent_worlds import canonical
    from decision_lab.game_construction import game_construction_summary, MAX_AUDIT_BYTES
    from test_strategic_scale import cast
    value = cast(100)
    report = audit(value)
    assert report['cross_dependencies']['direct_edge_count'] == 9900
    assert report['cross_dependencies']['omitted_direct_edge_count'] > 0
    assert (len(report['cross_dependencies']['direct_edges'])
        + report['cross_dependencies']['omitted_direct_edge_count']) == 9900
    assert report['actors'][0]['objective_dependencies']['incoming_actor_count'] == 99
    assert report['actors'][0]['objective_dependencies']['omitted_incoming_actor_ids'] == 87
    assert len(canonical(report)) <= MAX_AUDIT_BYTES
    summary = game_construction_summary(value)
    assert summary['direct_dependency_edge_count'] == 9900
    assert summary['total_initial_cash_cents'] == 10000
    assert summary['action_count'] == summary['initially_affordable_action_count'] == 200
    assert len(canonical(summary)) <= 16384
    assert 'PRIVATE' not in json.dumps(summary)
    assert 'Learn safely' not in json.dumps(summary)


def pilot_example():
    from decision_lab.product_api import examples
    return next(e['world'] for e in examples() if e['id'] == 'near-pilot-eight-roles')


def execute_local(value):
    from decision_lab.offline_decisions import OfflineDecisions
    from decision_lab.strategic_models import decide
    from decision_lab.strategic_worlds import StrategicWorld, replay_strategic_world
    engine = StrategicWorld(value)
    while engine.observations():
        choices = {key: decide(OfflineDecisions(), obs) for key, obs in engine.observations().items()}
        engine.advance({key: {k: choice[k] for k in ('action_id', 'observation_sha256')}
            for key, choice in choices.items()})
    result = engine.report()
    replay_strategic_world(result)
    return result


def test_eight_role_example_has_working_tradeoffs_and_fixed_cast_capital():
    value = pilot_example()
    reviewed = audit(value)
    assert reviewed['representation']['actor_count'] == 8
    assert len(reviewed['representation']['role_counts']) == 8
    assert reviewed['economics']['total_initial_cash_cents'] == 1000000
    actors = {a['id']: a for a in reviewed['actors']}
    # Same label "join" carries different effort/risk tradeoffs under own utility.
    assert actors['momentum']['own_action_counterfactuals']['actions'][1]['utility_delta'] == 8500
    assert actors['cautious']['own_action_counterfactuals']['actions'][1]['utility_delta'] == -7700
    assert reviewed['cross_dependencies']['direct_edge_count'] == 55
    result = execute_local(value)
    assert result['status'] == 'completed'
    assert sum(a['cash_cents'] for a in result['actor_results'].values()) + result['total_cost_cents'] == 1000000
    selected = result['rounds'][0]['receipts']
    assert selected['momentum']['action_id'] == 'join'
    assert selected['cautious']['action_id'] == 'wait'


def test_numeric_preference_change_changes_behavior_without_duplicating_cash():
    original = pilot_example()
    baseline = execute_local(original)
    changed = deepcopy(original)
    next(a for a in changed['actors'] if a['id'] == 'momentum')['utility_weights']['risk'] = -5000
    alternative = execute_local(changed)
    assert alternative['rounds'][0]['receipts']['momentum']['action_id'] == 'wait'
    assert alternative['final_metrics'] != baseline['final_metrics']
    assert sum(a['initial_cash_cents'] for a in changed['actors']) == 1000000
    # This baseline ignores prose: documentation alone cannot implement preferences.
    narrative_only = deepcopy(original)
    for actor in narrative_only['actors']:
        actor['motivation'] = 'Become exceptionally cautious.'
        actor['goal'] = 'Preserve cash above everything else.'
    narrative = execute_local(narrative_only)
    assert narrative['final_metrics'] == baseline['final_metrics']
    assert narrative['actor_results'] == baseline['actor_results']
