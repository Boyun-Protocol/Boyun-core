import json
from pathlib import Path

import pytest

from decision_lab.actors import build_cast, default_recipe


POOL = json.loads((Path(__file__).parents[1] / "src/decision_lab/data/personas.json").read_text())


def test_scenario_cast_is_not_one_of_each_catalogue_entry():
    cast = build_cast(POOL, default_recipe(), seed=7)
    assert len(cast.actors) == 78
    assert len([a for a in cast.actors if a.category == "retail"]) == 48
    assert len([a for a in cast.actors if a.category == "launch_teams"]) == 3
    assert len(cast.excluded) == 2
    assert all(e["reason"] == "requires_two_executable_markets" for e in cast.excluded)


def test_founder_lp_alias_does_not_create_a_second_endowment():
    cast = build_cast(POOL, default_recipe(), seed=7)
    project_roles = [a for a in cast.actors if a.owner_id == "project"]
    assert {a.id for a in project_roles} == {"project-founder", "project-lp"}
    assert sum(a.initial_cash_cents for a in project_roles) == 1_000_000
    assert all(a.provenance["status"] == "assumed" for a in cast.actors)


def test_invalid_recipe_cannot_silently_make_money_or_actors():
    recipe = default_recipe()
    recipe["groups"]["retail"]["count"] = True
    with pytest.raises(ValueError):
        build_cast(POOL, recipe, seed=7)
    recipe = default_recipe()
    recipe["groups"]["retail"]["cash_range_cents"] = [10, -10]
    with pytest.raises(ValueError):
        build_cast(POOL, recipe, seed=7)


def test_seed_replays_cast_without_using_template_index_parameters():
    original = build_cast(POOL, default_recipe(), seed=7)
    changed = json.loads(json.dumps(POOL))
    for p in changed["profiles"]:
        p["policy"]["attention_half_life_hours"] = 999999
        p["capital"]["range_cents"] = [999999999, 999999999]
        p["information"]["relationship_template"] = []
    assert original == build_cast(changed, default_recipe(), seed=7)
    assert original != build_cast(POOL, default_recipe(), seed=8)


def test_observers_have_no_trading_capabilities():
    cast = build_cast(POOL, default_recipe(), seed=7)
    for a in cast.actors:
        if a.category in {"analysts_community", "creators_marketing"}:
            assert not ({"buy", "sell"} & a.allowed_actions)


def test_pool_requires_unique_reviewed_descriptions_and_known_categories():
    for field, value in [("id", ""), ("name", None), ("description", ""), ("category", "unknown")]:
        pool = json.loads(json.dumps(POOL))
        pool["profiles"][0][field] = value
        with pytest.raises(ValueError):
            build_cast(pool, default_recipe(), seed=7)
    pool = json.loads(json.dumps(POOL))
    pool["profiles"][1]["id"] = pool["profiles"][0]["id"]
    with pytest.raises(ValueError):
        build_cast(pool, default_recipe(), seed=7)


def test_recipe_rejects_unknown_groups_and_missing_founder():
    recipe = default_recipe()
    recipe["groups"]["surprise"] = recipe["groups"]["retail"].copy()
    with pytest.raises(ValueError):
        build_cast(POOL, recipe, seed=7)
    recipe = default_recipe()
    recipe["founder_count"] = 0
    with pytest.raises(ValueError):
        build_cast(POOL, recipe, seed=7)


def test_zero_attention_and_explicit_passive_roles():
    recipe = default_recipe()
    recipe["groups"]["retail"]["attention_capacity"] = 0
    cast = build_cast(POOL, recipe, seed=7)
    assert all(a.attention_capacity == 0 for a in cast.actors if a.category == "retail")
    assert all(a.strategy == "observe" for a in cast.actors
               if a.category in {"launch_teams", "liquidity"} and a.owner_id != "project")
    assert any("competitor" in a.subscriptions for a in cast.actors)


@pytest.mark.parametrize("field,value", [
    ("attention_capacity", True), ("position_limit_cents", -1),
    ("entry_fraction_bps", 10001), ("strategy_choices", [{}]),
    ("subscription_choices", [[None]]),
])
def test_group_behavior_settings_are_validated(field, value):
    recipe = default_recipe()
    recipe["groups"]["retail"][field] = value
    with pytest.raises(ValueError):
        build_cast(POOL, recipe, seed=7)


def test_route_flag_does_not_invent_arbitrage_execution():
    recipe = default_recipe()
    recipe["two_executable_markets"] = True
    cast = build_cast(POOL, recipe, seed=7)
    assert len(cast.actors) == 80
    assert cast.excluded == []
    arbitrage = [actor for actor in cast.actors if actor.category == "arbitrage"]
    assert all(actor.strategy == "observe" and "buy" not in actor.allowed_actions for actor in arbitrage)


def test_project_roles_use_explicit_reviewed_templates_and_reserve_them():
    recipe = default_recipe()
    assert recipe["role_templates"] == {
        "project-founder": "launch_teams-01", "project-lp": "liquidity-01",
    }
    for seed in (7, 42, 99):
        cast = build_cast(POOL, recipe, seed)
        roles = {actor.id: actor for actor in cast.actors if actor.owner_id == "project"}
        assert roles["project-founder"].template_id == "launch_teams-01"
        assert roles["project-founder"].provenance["template"]["name"] == "Project founder"
        assert roles["project-lp"].template_id == "liquidity-01"
        assert roles["project-lp"].provenance["template"]["name"] == "Founder liquidity operator"
        assert all(actor.template_id not in recipe["role_templates"].values()
                   for actor in cast.actors if actor.owner_id != "project")


@pytest.mark.parametrize("role_templates", [
    {}, {"project-founder": "missing", "project-lp": "liquidity-01"},
    {"project-founder": "retail-01", "project-lp": "liquidity-01"},
    {"project-founder": "launch_teams-01", "project-lp": "retail-01"},
])
def test_project_role_template_mapping_is_required_and_validated(role_templates):
    recipe = default_recipe()
    recipe["role_templates"] = role_templates
    with pytest.raises(ValueError):
        build_cast(POOL, recipe, 42)


def test_reserved_template_cannot_fill_an_outside_slot_when_library_is_exhausted():
    pool = json.loads(json.dumps(POOL))
    pool["profiles"] = [profile for profile in pool["profiles"]
                        if profile["category"] != "launch_teams" or profile["id"] == "launch_teams-01"]
    with pytest.raises(ValueError, match="outside"):
        build_cast(pool, default_recipe(), 42)
