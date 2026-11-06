"""Explicit launch imports must preserve finance while rejecting invented mechanics."""
from copy import deepcopy

import pytest

from decision_lab import actors, simulation


def api():
    # Delayed import makes the initial missing feature an assertion-style failure.
    from decision_lab import explicit_cast
    return explicit_cast


def fixture():
    scenario = simulation.default_scenario()
    scenario['horizon_hours'] = 120
    scenario['campaigns'] = [{'at_hour': 5, 'fee_cents': 50_000}]
    scenario['founder_sales'] = [{'at_hour': 72, 'token_units': 300_000}]
    recipe = scenario['cast_recipe']
    for group in recipe['groups'].values():
        group['count'] = 0
    for category in ('launch_teams', 'liquidity', 'retail', 'creators_marketing'):
        recipe['groups'][category]['count'] = 1
    cast = actors.build_cast(simulation.load_pool(), recipe, 42)
    return scenario, cast


def explicit_fixture():
    scenario, cast = fixture()
    return scenario, api().export_cast(cast)


def with_alternatives(spec):
    trader = next(a for a in spec['actors'] if a['category'] == 'retail')
    spec['mixture_assumption'] = 'independent_per_actor_per_world'
    spec['alternatives'] = [{'actor_id': trader['id'], 'variants': [
        {'id': 'wait', 'weight_bps': 5000, 'overrides': {'attention_capacity': 0}},
        {'id': 'engage', 'weight_bps': 5000, 'overrides': {'strategy': 'momentum', 'entry_fraction_bps': 10_000}},
    ]}]
    return spec


def test_same_supplied_cast_produces_exact_legacy_worlds_without_generation(monkeypatch):
    scenario, cast = fixture()
    expected = [simulation._world(scenario, cast, 42, i, 'launch_now', i < 3) for i in range(3)]
    spec = api().export_cast(cast)
    def forbidden(*args, **kwargs):
        pytest.fail('explicit execution called persona generation or library loading')
    monkeypatch.setattr(simulation, 'build_cast', forbidden)
    monkeypatch.setattr(simulation, 'load_pool', forbidden)
    monkeypatch.setattr(actors, 'build_cast', forbidden)
    report = api().simulate_explicit(scenario, spec, worlds=3)
    assert report['worlds'] == expected
    assert report['cast']['selected_count'] == 4
    assert report['usage']['model_calls'] == 0
    assert report['schema_version'] == 'explicit-launch-result.v1'


def test_custom_descriptions_roundtrip_and_no_input_mutation():
    scenario, spec = explicit_fixture()
    spec['actors'][0]['provenance'] = {'description': 'Self-authored unique risk story'}
    before = deepcopy((scenario, spec))
    cast = api().validate_explicit_cast(spec, scenario)
    assert api().export_cast(cast) == spec
    report = api().simulate_explicit(scenario, spec, worlds=1)
    assert report['cast']['actors'][0]['provenance']['description'] == 'Self-authored unique risk story'
    assert (scenario, spec) == before
    cast.actors[0].provenance['description'] = 'changed'
    assert spec['actors'][0]['provenance']['description'] != 'changed'


def test_alternatives_preserve_population_and_endowments_and_replay():
    scenario, spec = explicit_fixture()
    with_alternatives(spec)
    original = api().validate_explicit_cast(spec, scenario)
    selections = []
    for world_id in range(20):
        cast, selected = api().cast_for_world(spec, scenario, 17, world_id)
        assert [(a.id, a.owner_id, a.initial_cash_cents) for a in cast.actors] == [
            (a.id, a.owner_id, a.initial_cash_cents) for a in original.actors]
        assert (cast, selected) == api().cast_for_world(spec, scenario, 17, world_id)
        selections.append(selected['retail-001'])
    assert set(selections) == {'wait', 'engage'}
    report = api().simulate_explicit(scenario, spec, worlds=5, seed=17)
    assert report == api().simulate_explicit(scenario, spec, worlds=5, seed=17)
    assert [row['selections']['retail-001'] for row in report['variant_selections']] == selections[:5]
    assert all(w['initial_totals'] == w['ending_totals'] for w in report['worlds'])
    assert all(w['initial_totals'][0] == sum(a.initial_cash_cents for a in original.actors) for w in report['worlds'])
    reordered = deepcopy(spec)
    reordered['actors'].reverse()
    reordered['alternatives'][0]['variants'].reverse()
    assert api().cast_for_world(reordered, scenario, 17, 2)[1] == api().cast_for_world(spec, scenario, 17, 2)[1]


@pytest.mark.parametrize('mutation', [
    lambda s: s.update(policy_bundle={}),
    lambda s: s['actors'][0].update(extra='private-secret-value'),
    lambda s: s['actors'][0].update(strategy='private-secret-value'),
    lambda s: s['actors'][0].update(category='private-secret-value'),
    lambda s: s['actors'][0].update(allowed_actions=['borrow']),
    lambda s: s['actors'][0].update(allowed_actions=['buy', 'buy', 'abstain']),
    lambda s: s['actors'][0].update(subscriptions=['unknown-channel']),
    lambda s: s['actors'][0].update(initial_cash_cents=True),
    lambda s: s['actors'][0].update(owner_id='pool'),
    lambda s: s['actors'][0].update(id='project-founder'),
    lambda s: s['actors'][0].pop('provenance'),
    lambda s: s['actors'].append(deepcopy(s['actors'][0])),
    lambda s: next(a for a in s['actors'] if a['id'] == 'project-lp').update(initial_cash_cents=1),
    lambda s: next(a for a in s['actors'] if a['id'] == 'project-founder').update(initial_cash_cents=1),
    lambda s: next(a for a in s['actors'] if a['category'] == 'creators_marketing').update(owner_id='retail-001'),
    lambda s: next(a for a in s['actors'] if a['category'] == 'creators_marketing').update(owner_id='project'),
    lambda s: s['actors'].__setitem__(slice(None), [a for a in s['actors'] if a['id'] != 'project-founder']),
    lambda s: s['actors'].__setitem__(slice(None), [a for a in s['actors'] if a['category'] != 'creators_marketing']),
])
def test_invalid_actor_schema_roles_and_capabilities_fail_safely(mutation):
    scenario, spec = explicit_fixture()
    mutation(spec)
    with pytest.raises(ValueError) as error:
        api().validate_explicit_cast(spec, scenario)
    assert 'private-secret-value' not in str(error.value)


@pytest.mark.parametrize('mutation', [
    lambda s: s.pop('mixture_assumption'),
    lambda s: s.update(mixture_assumption='correlated'),
    lambda s: s['alternatives'][0].update(actor_id='missing'),
    lambda s: s['alternatives'].append(deepcopy(s['alternatives'][0])),
    lambda s: s['alternatives'][0]['variants'][0].update(weight_bps=1),
    lambda s: s['alternatives'][0]['variants'][0].update(weight_bps=True),
    lambda s: s['alternatives'][0]['variants'][0]['overrides'].update(owner_id='another'),
    lambda s: s['alternatives'][0]['variants'][0]['overrides'].update(initial_cash_cents=1),
    lambda s: s['alternatives'][0]['variants'][0]['overrides'].update(strategy='unimplemented'),
    lambda s: s['alternatives'][0]['variants'][0].update(id='engage'),
])
def test_invalid_mixtures_never_run_or_mint_capital(mutation):
    scenario, spec = explicit_fixture()
    with_alternatives(spec)
    mutation(spec)
    with pytest.raises(ValueError):
        api().simulate_explicit(scenario, spec, worlds=1)


def test_hash_binds_cast_description_scenario_seed_and_alternatives():
    scenario, spec = explicit_fixture()
    first = api().simulate_explicit(scenario, spec, worlds=1)
    changed = deepcopy(spec)
    changed['actors'][0]['provenance']['description'] = 'new description'
    assert api().simulate_explicit(scenario, changed, worlds=1)['input_sha256'] != first['input_sha256']
    assert api().simulate_explicit(scenario, spec, worlds=1, seed=43)['input_sha256'] != first['input_sha256']
    scenario['name'] = 'changed'
    assert api().simulate_explicit(scenario, spec, worlds=1)['input_sha256'] != first['input_sha256']
    assert api().simulate_explicit(scenario, with_alternatives(spec), worlds=1)['input_sha256'] != first['input_sha256']


def test_resource_limits_and_unknown_scenario_fields_fail_before_worlds(monkeypatch):
    scenario, spec = explicit_fixture()
    def forbidden(*args, **kwargs):
        pytest.fail('invalid input reached financial kernel')
    monkeypatch.setattr(simulation, '_world', forbidden)
    for worlds in (0, True, 101):
        with pytest.raises(ValueError):
            api().simulate_explicit(scenario, spec, worlds=worlds)
    scenario['horizon_hours'] = 100000
    with pytest.raises(ValueError):
        api().simulate_explicit(scenario, spec, worlds=1)
    scenario['horizon_hours'] = 120
    scenario['liquidation'] = 'private-secret-value'
    with pytest.raises(ValueError) as error:
        api().simulate_explicit(scenario, spec, worlds=1)
    assert 'private-secret-value' not in str(error.value)


def test_declared_alternative_changes_actions_without_changing_starting_capital():
    scenario, spec = explicit_fixture()
    scenario['catalyst_probability_bps'] = 10_000
    with_alternatives(spec)
    waiting = deepcopy(spec)
    engaged = deepcopy(spec)
    waiting['alternatives'][0]['variants'][0]['weight_bps'] = 10_000
    waiting['alternatives'][0]['variants'][1]['weight_bps'] = 0
    engaged['alternatives'][0]['variants'][0]['weight_bps'] = 0
    engaged['alternatives'][0]['variants'][1]['weight_bps'] = 10_000
    wait_world = api().simulate_explicit(scenario, waiting, worlds=1)['worlds'][0]
    engage_world = api().simulate_explicit(scenario, engaged, worlds=1)['worlds'][0]
    assert wait_world['participant_buys'] == 0
    assert engage_world['participant_buys'] > 0
    assert wait_world['initial_totals'] == engage_world['initial_totals']
    assert wait_world['net_profit_cents'] != engage_world['net_profit_cents']


def test_default_cast_and_25_worlds_remain_within_explicit_budget():
    scenario = simulation.default_scenario()
    cast = actors.build_cast(simulation.load_pool(), scenario['cast_recipe'], 42)
    report = api().simulate_explicit(scenario, api().export_cast(cast), worlds=25)
    assert report['world_count'] == 25
    assert report['execution_limits']['actor_visits'] <= report['execution_limits']['max_actor_visits']


def test_actor_visit_and_population_budgets_reject_before_execution(monkeypatch):
    scenario, spec = explicit_fixture()
    scenario['horizon_hours'] = 8760
    scenario['lp_unlock_at_hour'] = 8761
    scenario['visit_interval_hours'] = 1
    def forbidden(*args, **kwargs):
        pytest.fail('workload rejection occurred too late')
    monkeypatch.setattr(simulation, '_world', forbidden)
    with pytest.raises(ValueError):
        api().simulate_explicit(scenario, spec, worlds=100)
    baseline = deepcopy(spec['actors'][0])
    while len(spec['actors']) < 257:
        actor = deepcopy(baseline)
        actor['id'] = actor['owner_id'] = f'outside-{len(spec["actors"])}'
        spec['actors'].append(actor)
    with pytest.raises(ValueError):
        api().simulate_explicit(scenario, spec, worlds=1)


def test_policy_arguments_are_explicitly_rejected():
    scenario, spec = explicit_fixture()
    with pytest.raises(TypeError):
        api().simulate_explicit(scenario, spec, policy_bundle={})


def test_report_labels_base_cast_and_records_actual_selected_policies():
    scenario, spec = explicit_fixture()
    with_alternatives(spec)
    trader = next(a for a in spec['actors'] if a['category'] == 'retail')
    trader['strategy'] = 'cautious'
    variants = spec['alternatives'][0]['variants']
    variants[0]['weight_bps'] = 0
    variants[1]['weight_bps'] = 10_000
    variants[1]['overrides'].update(position_limit_cents=12345, attention_capacity=3,
                                    subscriptions=['news', 'creator'])
    report = api().simulate_explicit(scenario, spec, worlds=2)
    assert report['cast_scope'] == 'base_before_variants'
    assert report['cast']['scope'] == 'base_before_variants'
    assert next(a for a in report['cast']['actors'] if a['id'] == trader['id'])['strategy'] == 'cautious'
    expected = {'variant_id': 'engage', 'strategy': 'momentum', 'entry_fraction_bps': 10_000,
                'position_limit_cents': 12345, 'attention_capacity': 3, 'subscriptions': ['news', 'creator']}
    for row in report['variant_selections']:
        assert row['effective_actor_policies'] == {trader['id']: expected}
    no_variants = api().simulate_explicit(scenario, api().export_cast(fixture()[1]), worlds=1)
    assert no_variants['variant_selections'][0]['effective_actor_policies'] == {}


def test_feed_scan_budget_rejects_message_explosion_before_kernel(monkeypatch):
    scenario = simulation.default_scenario()
    cast = actors.build_cast(simulation.load_pool(), scenario['cast_recipe'], 42)
    spec = api().export_cast(cast)
    scenario['competitor_messages'] = [{'at_hour': 1} for _ in range(2048)]
    def forbidden(*args, **kwargs):
        pytest.fail('feed scan limit failed to reject before kernel')
    monkeypatch.setattr(simulation, '_world', forbidden)
    with pytest.raises(ValueError, match='feed_scan_budget'):
        api().simulate_explicit(scenario, spec, worlds=100)


def test_default_100_worlds_fit_actor_and_feed_scan_budgets():
    scenario = simulation.default_scenario()
    cast = actors.build_cast(simulation.load_pool(), scenario['cast_recipe'], 42)
    report = api().simulate_explicit(scenario, api().export_cast(cast), worlds=100)
    limits = report['execution_limits']
    assert limits['actor_visits'] == 943800
    assert limits['feed_scan_upper_bound'] == 11_325_600
    assert limits['feed_scan_upper_bound'] <= limits['max_feed_scans']
    assert report['world_count'] == 100


def test_capabilities_publish_complete_explicit_contract_and_are_detached():
    contract = api().explicit_launch_capabilities()
    assert contract['schema_version'] == 'explicit-launch.v1'
    assert set(contract['wrapper']['required']) == {'schema_version', 'id', 'event_description', 'scenario', 'cast'}
    assert set(contract['scenario']['required']) == set(simulation.default_scenario())
    assert set(contract['scenario']['fields']) == set(contract['scenario']['required']) | {'user_brief'}
    assert set(contract['cast']['actor_fields']) == set(actors.Actor.__dataclass_fields__)
    assert contract['scenario']['fields']['capital_cents']['unit'] == 'cents'
    assert contract['scenario']['fields']['cast_recipe']['required'] == ['founder_initial_cash_cents']
    assert set(contract['cast']['alternatives']['allowed_overrides']) == {
        'strategy', 'entry_fraction_bps', 'position_limit_cents', 'attention_capacity', 'subscriptions'}
    assert contract['limits']['max_feed_scans'] == 20_000_000
    contract['cast']['role_rules']['project-founder']['allowed_actions'].append('borrow')
    assert 'borrow' not in api().explicit_launch_capabilities()['cast']['role_rules']['project-founder']['allowed_actions']


def test_minimal_fully_explicit_scenario_requires_no_generated_recipe_or_profiles():
    scenario = {
        'schema_version': 'synthetic-scenario.v1', 'mode': 'synthetic', 'name': 'Supplied launch mechanics',
        'horizon_hours': 1, 'capital_cents': 10_000, 'launch_cost_cents': 1000,
        'lp_cash_cents': 5000, 'lp_tokens': 1000, 'founder_tokens': 1000, 'fee_bps': 30,
        'founder_vested_at_hour': 0, 'lp_unlock_at_hour': 2, 'founder_sales': [], 'campaigns': [],
        'campaign_budget_cents': 0, 'news_enabled': False, 'catalyst_probability_bps': 0,
        'followup_positive_probability_bps': 0, 'competitor_messages': [],
        'observation_window_hours': 1, 'visit_interval_hours': 1, 'max_slippage_bps': 0,
        'cast_recipe': {'founder_initial_cash_cents': 10_000},
        'assumptions': [{'status': 'user_supplied', 'rationale': 'Explicit minimal mechanism inputs'}],
    }
    founder = {
        'id': 'project-founder', 'template_id': 'supplied-founder', 'category': 'launch_teams',
        'owner_id': 'project', 'initial_cash_cents': 10_000, 'allowed_actions': ['sell', 'abstain'],
        'subscriptions': [], 'position_limit_cents': 0, 'entry_fraction_bps': 0,
        'attention_capacity': 0, 'strategy': 'scheduled_exit',
        'provenance': {'description': 'Supplied founder account, no scheduled token sales'},
    }
    lp = {**founder, 'id': 'project-lp', 'template_id': 'supplied-lp', 'category': 'liquidity',
          'initial_cash_cents': 0, 'strategy': 'observe',
          'allowed_actions': ['add_liquidity', 'remove_liquidity', 'abstain'],
          'provenance': {'description': 'Delegated project LP account, no independent endowment'}}
    cast = {'schema_version': 'explicit-cast.v1', 'actors': [founder, lp], 'excluded': []}
    validated = api().validate_explicit_cast(cast, scenario)
    assert len(validated.actors) == 2
    result = api().simulate_explicit(scenario, cast, worlds=1)
    assert result['worlds'][0]['project_cash_cents'] == 4000
    assert result['worlds'][0]['initial_totals'] == result['worlds'][0]['ending_totals'] == [10_000, 1000]
