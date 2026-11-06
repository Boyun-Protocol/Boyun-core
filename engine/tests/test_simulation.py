from copy import deepcopy

import pytest

from decision_lab.simulation import compare_plans, default_scenario, load_pool, simulate


def scenario():
    return default_scenario()


def test_seeded_experiment_replays_and_conserves_all_assets():
    first = simulate(scenario(), load_pool(), worlds=3, seed=42)
    assert first == simulate(scenario(), load_pool(), worlds=3, seed=42)
    assert first["world_count"] == 3
    assert first["cast"]["selected_count"] == 78
    assert first["cast"]["template_pool_count"] == 80
    assert first["usage"]["model_calls"] == 0
    for world in first["worlds"]:
        assert world["initial_totals"] == world["ending_totals"]
        assert world["project_cash_cents"] - 1_000_000 == world["net_profit_cents"]
        assert world["unsold_project_tokens"] >= 0
        assert world["locked_project_lp_shares"] > 0


def test_no_delivered_project_information_means_no_buys():
    value = scenario()
    value["news_enabled"] = False
    value["campaigns"] = []
    value["competitor_messages"] = []
    result = simulate(value, load_pool(), worlds=2)
    assert all(w["participant_buys"] == 0 for w in result["worlds"])


def test_empty_attention_capacity_cannot_convert_posts_to_demand():
    value = scenario()
    for group in value["cast_recipe"]["groups"].values():
        group["attention_capacity"] = 0
    result = simulate(value, load_pool(), worlds=1)
    assert result["worlds"][0]["participant_buys"] == 0
    assert result["worlds"][0]["delivered_campaigns"] == len(value["campaigns"])


def test_campaign_budget_cannot_exceed_reserved_funds():
    value = scenario()
    value["campaigns"][0]["fee_cents"] = 999999
    with pytest.raises(ValueError, match="campaign"):
        simulate(value, load_pool(), worlds=1)


def test_all_plans_share_external_draws_independent_of_actions():
    result = compare_plans(scenario(), load_pool(), worlds=4, seed=14)
    external = [tuple(w["external_draws"].items()) for w in result["plans"]["launch_now"]["worlds"]]
    for report in result["plans"].values():
        assert [tuple(w["external_draws"].items()) for w in report["worlds"]] == external
    assert result["paired_comparisons"]


def test_undelivered_future_campaign_does_not_spend_cash():
    value = scenario()
    value["horizon_hours"] = 4
    value["launch_cost_cents"] = 0
    value["news_enabled"] = False
    value["founder_sales"] = []
    result = simulate(value, load_pool(), worlds=1)["worlds"][0]
    assert result["campaign_paid_cents"] == 0
    assert result["unpaid_obligations_cents"] == 0
    assert result["net_profit_cents"] == -400000


@pytest.mark.parametrize("field,bad", [("horizon_hours", True), ("capital_cents", 1.0), ("catalyst_probability_bps", 10001)])
def test_malformed_or_uncertain_venue_parameters_do_not_run(field, bad):
    value = scenario()
    value[field] = bad
    with pytest.raises(ValueError):
        simulate(value, load_pool(), worlds=1)


def test_actual_event_times_and_plan_rejections_remain_visible():
    value = scenario()
    value["founder_sales"] = [{"at_hour": 3, "token_units": 10_000_000}]
    result = simulate(value, load_pool(), worlds=1)
    trace = result["worlds"][0]["trace"]
    rejection = [e for e in trace if e["kind"] == "founder_sale_rejected"]
    assert rejection and rejection[0]["at_hour"] == 3
    assert "rejection" in rejection[0]


def test_no_launch_plan_does_not_incur_launch_cost_or_lock_liquidity():
    result = simulate(scenario(), load_pool(), worlds=1, plan="do_not_launch")
    w = result["worlds"][0]
    assert w["net_profit_cents"] == 0
    assert w["project_cash_cents"] == 1_000_000
    assert w["locked_project_lp_shares"] == 0
    assert w["participant_buys"] == 0


def test_probabilities_are_output_counts_not_prefilled_claims():
    result = simulate(scenario(), load_pool(), worlds=5)
    assert sum(x["count"] for x in result["outcomes"]) == 5
    assert sum(x["frequency"] for x in result["outcomes"]) == 1
    assert result["interpretation"] == "conditional_synthetic_frequency_not_calibrated_real_world_odds"


def test_paid_post_cannot_resurrect_a_publicly_contradicted_claim():
    value = scenario()
    # Keep the fixture's trace below the explicit 500-event capture limit.
    value["cast_recipe"]["groups"]["retail"]["count"] = 4
    value["cast_recipe"]["groups"]["event_traders"]["count"] = 0
    value["cast_recipe"]["groups"]["large_holders"]["count"] = 0
    value.update(horizon_hours=120, campaigns=[{"at_hour": 100, "fee_cents": 50000}],
                 founder_sales=[], competitor_messages=[], catalyst_probability_bps=10000,
                 followup_positive_probability_bps=0)
    trace = simulate(value, load_pool(), worlds=1, seed=42)["worlds"][0]["trace"]
    assert not [e for e in trace if e["at_hour"] > 96 and e["kind"] == "participant_buy"]
    post = next(e for e in trace if e["kind"] == "campaign_delivery")
    assert post["status"] == "contradicted"
    assert post["evidence_message_id"] == "news-followup"


@pytest.mark.parametrize("news_enabled,at_hour", [(True, 0), (False, 5)])
def test_campaign_cannot_confirm_an_unpublished_external_outcome(news_enabled, at_hour):
    value = scenario()
    value.update(horizon_hours=12, campaigns=[{"at_hour": at_hour, "fee_cents": 50000}],
                 founder_sales=[], competitor_messages=[], news_enabled=news_enabled,
                 catalyst_probability_bps=10000)
    trace = simulate(value, load_pool(), worlds=1, seed=42)["worlds"][0]["trace"]
    post = next(e for e in trace if e["kind"] == "campaign_delivery")
    assert post["status"] == "rumor"
    assert post["evidence_message_id"] is None


def test_observed_exit_reason_survives_a_rejected_trade(monkeypatch):
    from decision_lab.finance import ConstantProductMarket
    attempts = {}
    original = ConstantProductMarket.sell

    def reject_first_exit(self, owner, *args, **kwargs):
        attempts[owner] = attempts.get(owner, 0) + 1
        if attempts[owner] == 1:
            raise ValueError("temporary execution rejection")
        return original(self, owner, *args, **kwargs)

    monkeypatch.setattr(ConstantProductMarket, "sell", reject_first_exit)
    value = scenario()
    value.update(horizon_hours=120, founder_sales=[], campaigns=[], competitor_messages=[],
                 catalyst_probability_bps=10000, followup_positive_probability_bps=0)
    simulate(value, load_pool(), worlds=1, seed=42)
    assert attempts
    assert all(count >= 2 for count in attempts.values())


def test_actor_remembers_public_news_seen_before_delayed_launch():
    value = scenario()
    value.update(horizon_hours=30, founder_sales=[], campaigns=[], competitor_messages=[],
                 catalyst_probability_bps=10000)
    result = simulate(value, load_pool(), worlds=1, seed=42, plan="defer_launch")
    assert result["worlds"][0]["participant_buys"] > 0


def empty_policy_bundle(fallback="abstain"):
    return {"schema_version": "policy-bundle.v1", "bundle_id": "test-bundle",
            "source": {"kind": "manual", "model": None, "prompt_sha256": None},
            "fallback": fallback, "policies": []}


def test_abstain_bundle_disables_entries_without_fabricating_model_calls():
    policy = empty_policy_bundle()
    result = simulate(scenario(), load_pool(), worlds=2, policy_bundle=policy)
    assert all(w["participant_buys"] == 0 for w in result["worlds"])
    assert result["policy_bundle"] == policy
    assert len(result["policy_bundle_sha256"]) == 64
    assert result["usage"]["model_calls"] == 0
    assert result["policy_bindings"]["counts"] == {
        "explicit_rule": 0, "baseline_fallback": 0, "abstain_fallback": 64, "passive_role": 14}


def test_policy_bundle_replays_and_compared_plans_record_identical_identity():
    policy = empty_policy_bundle("baseline")
    first = simulate(scenario(), load_pool(), worlds=1, seed=42, policy_bundle=policy)
    assert first == simulate(scenario(), load_pool(), worlds=1, seed=42, policy_bundle=policy)
    assert first["worlds"] == simulate(scenario(), load_pool(), worlds=1, seed=42)["worlds"]
    comparison = compare_plans(scenario(), load_pool(), worlds=1, seed=42, policy_bundle=policy)
    for result in comparison["plans"].values():
        assert result["policy_bundle_sha256"] == first["policy_bundle_sha256"]
        assert result["worlds"][0]["external_draws"] == first["worlds"][0]["external_draws"]


def test_unknown_executable_policy_fields_fail_before_simulation():
    policy = empty_policy_bundle()
    policy["code"] = "arbitrary expressions are not a policy language"
    with pytest.raises(ValueError):
        simulate(scenario(), load_pool(), worlds=1, policy_bundle=policy)
