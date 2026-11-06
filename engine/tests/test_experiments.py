"""Matched experiments must compare cash outcomes without changing random worlds."""
from copy import deepcopy

import pytest

from decision_lab.simulation import default_scenario, load_pool


def bundle():
    return {"schema_version": "policy-bundle.v1", "bundle_id": "abstain-test",
            "source": {"kind": "manual", "model": None, "prompt_sha256": None},
            "fallback": "abstain", "policies": []}


def short_scenario():
    value = default_scenario()
    value["horizon_hours"] = 12
    return value


def test_policies_pair_identical_worlds_and_report_actual_cash_differences():
    from decision_lab.experiments import compare_policies
    value, pool, policy = short_scenario(), load_pool(), bundle()
    before = deepcopy((value, pool, policy))
    result = compare_policies(value, pool, policy, worlds=3, seed=7)
    assert (value, pool, policy) == before
    assert result == compare_policies(value, pool, policy, worlds=3, seed=7)
    assert result["baseline"]["policy_bundle"] is None
    assert result["policy"]["policy_bundle"]["bundle_id"] == "abstain-test"
    assert result["baseline"]["cast"] == result["policy"]["cast"]
    assert result["policy"]["world_count"] == 3
    assert result["interpretation"] == "conditional_synthetic_comparison_not_real_world_odds"
    differences = []
    for baseline, other, paired in zip(result["baseline"]["worlds"], result["policy"]["worlds"], result["paired"]["worlds"]):
        assert baseline["world_id"] == other["world_id"] == paired["world_id"]
        assert baseline["external_draws"] == other["external_draws"] == paired["external_draws"]
        delta = other["net_profit_cents"] - baseline["net_profit_cents"]
        assert paired["difference_cents"] == delta
        differences.append(delta)
    assert result["paired"]["summary"]["mean_cents"] == sum(differences) / 3
    assert result["paired"]["summary"]["quantiles_cents"]["p50"] == sorted(differences)[1]
    assert result["baseline_summary"]["mean_cents"] == -600000
    assert result["policy_summary"]["mean_cents"] == -600000
    assert result["usage"]["model_calls"] == 0


def test_sensitivity_is_one_at_a_time_with_explicit_original_baseline():
    from decision_lab.experiments import sensitivity
    value, pool = short_scenario(), load_pool()
    before = deepcopy(value)
    result = sensitivity(value, pool, parameter="fee_bps", values=[0, 9999], worlds=2, seed=3,
                         policy_bundle=bundle())
    assert value == before
    assert result["baseline_value"] == 30
    assert result["parameter"] == "fee_bps"
    assert result["cast_fixed"] is True
    assert [variant["value"] for variant in result["variants"]] == [0, 9999]
    for variant in result["variants"]:
        assert variant["report"]["cast"] == result["baseline"]["cast"]
        assert variant["report"]["policy_bundle_sha256"] == result["baseline"]["policy_bundle_sha256"]
        assert variant["report"]["scenario_sha256"] != result["baseline"]["scenario_sha256"]
        assert variant["report"]["worlds"][0]["external_draws"] == result["baseline"]["worlds"][0]["external_draws"]
        assert variant["paired"]["summary"]["mean_cents"] == 0


@pytest.mark.parametrize("parameter,values", [
    ("cast_recipe", [1]), ("horizon_hours", [24]), ("fee_bps", [9999, 10000]),
    ("fee_bps", [True]), ("fee_bps", [1.0]), ("fee_bps", [float("nan")]),
    ("fee_bps", []), ("fee_bps", [1, 1]), ("fee_bps", list(range(17))),
    ("fee_bps", "30"), ("catalyst_probability_bps", [-1]),
    ("followup_positive_probability_bps", [10001]), ("max_slippage_bps", [10001]),
])
def test_invalid_sweeps_fail_before_any_worlds(parameter, values, monkeypatch):
    import decision_lab.experiments as experiments
    def no_worlds(*args, **kwargs):
        pytest.fail("invalid sweep executed a world")
    monkeypatch.setattr(experiments, "simulate", no_worlds)
    with pytest.raises(ValueError):
        experiments.sensitivity(short_scenario(), load_pool(), parameter=parameter, values=values, worlds=1)


@pytest.mark.parametrize("worlds,seed", [(True, 1), (0, 1), (5001, 1), (1, True), (1, -1)])
def test_invalid_or_excessive_experiment_budget_rejected(worlds, seed):
    from decision_lab.experiments import compare_policies
    with pytest.raises(ValueError):
        compare_policies(short_scenario(), load_pool(), bundle(), worlds=worlds, seed=seed)


def test_sweep_total_world_budget_and_large_horizon_fail_before_execution(monkeypatch):
    import decision_lab.experiments as experiments
    def no_worlds(*args, **kwargs):
        pytest.fail("unbounded experiment executed")
    monkeypatch.setattr(experiments, "simulate", no_worlds)
    with pytest.raises(ValueError, match="budget"):
        experiments.sensitivity(short_scenario(), load_pool(), parameter="fee_bps", values=list(range(16)), worlds=1000)
    value = short_scenario()
    value["horizon_hours"] = 10**12
    value["lp_unlock_at_hour"] = 10**12 + 1
    with pytest.raises(ValueError, match="budget"):
        experiments.compare_policies(value, load_pool(), bundle(), worlds=1)


def test_policy_comparison_requires_explicit_valid_bundle_before_execution(monkeypatch):
    import decision_lab.experiments as experiments
    def no_worlds(*args, **kwargs):
        pytest.fail("invalid policy executed")
    monkeypatch.setattr(experiments, "simulate", no_worlds)
    for policy in (None, {}, {**bundle(), "fallback": "execute-python"}):
        with pytest.raises(ValueError):
            experiments.compare_policies(short_scenario(), load_pool(), policy, worlds=1)


def test_abstaining_policy_changes_recovery_when_founder_sale_executes():
    from decision_lab.experiments import compare_policies
    value = short_scenario()
    value["horizon_hours"] = 80
    result = compare_policies(value, load_pool(), bundle(), worlds=2, seed=7)
    assert all(world["participant_buys"] > 0 for world in result["baseline"]["worlds"])
    assert all(world["participant_buys"] == 0 for world in result["policy"]["worlds"])
    assert result["paired"]["summary"]["mean_cents"] < 0


def test_oversized_cast_is_rejected_before_allocating_actors(monkeypatch):
    import decision_lab.experiments as experiments
    value = short_scenario()
    value["cast_recipe"]["groups"]["retail"]["count"] = 10**12
    def no_allocation(*args, **kwargs):
        pytest.fail("unbounded cast allocation attempted")
    monkeypatch.setattr(experiments, "build_cast", no_allocation)
    with pytest.raises(ValueError, match="budget"):
        experiments.compare_policies(value, load_pool(), bundle(), worlds=1)
