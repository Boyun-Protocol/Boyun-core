"""Bounded paired experiments under fixed synthetic assumptions and one cast.

All monetary summaries are withdrawable project cash profit in integer cents,
excluding token inventory and locked LP shares. Quantiles use nearest rank:
sorted values at ceil(p*n), with a minimum rank of one; no interpolation.
"""
from copy import deepcopy
from math import ceil

from .actors import build_cast
from .policy_bundles import compile_bundle
from .simulation import _validate, simulate


ALLOWED_PARAMETERS = frozenset({
    "catalyst_probability_bps", "followup_positive_probability_bps", "fee_bps", "max_slippage_bps",
})
MAX_TOTAL_WORLDS = 10_000
MAX_ACTOR_VISITS = 50_000_000
MAX_CAST_SLOTS = 10_000
INTERPRETATION = "conditional_synthetic_comparison_not_real_world_odds"
LIMITATIONS = [
    "Conditional synthetic comparisons under supplied assumptions; not calibrated real-world odds or causal estimates.",
    "One sampled cast is fixed across all arms; no population resampling, inference calls or calibration fitting.",
    "Cash profit excludes unsold tokens and locked LP shares; it is not mark-to-market economic profit.",
    "Nearest-rank monetary quantiles describe these worlds only; they are not confidence intervals.",
]


def _preflight(scenarios, pool, policy_bundle, worlds, seed):
    """Validate every arm and workload before executing any world."""
    if type(worlds) is not int or worlds < 1 or worlds * len(scenarios) > MAX_TOTAL_WORLDS:
        raise ValueError("experiment world budget exceeded or invalid worlds")
    for scenario in scenarios:
        _validate(scenario, worlds, seed, "launch_now")
    recipe = scenarios[0].get("cast_recipe")
    groups = recipe.get("groups") if type(recipe) is dict else None
    if type(groups) is not dict or not groups:
        raise ValueError("invalid cast groups")
    slots = 0
    for group in groups.values():
        count = group.get("count") if type(group) is dict else None
        if type(count) is not int or count < 0:
            raise ValueError("invalid cast group count")
        slots += count
    visits = sum(scenario["horizon_hours"] // scenario["visit_interval_hours"] + 1 for scenario in scenarios)
    if slots > MAX_CAST_SLOTS or visits * slots * worlds > MAX_ACTOR_VISITS:
        raise ValueError("experiment cast or actor-visit budget exceeded")
    cast = build_cast(pool, scenarios[0]["cast_recipe"], seed)
    if policy_bundle is not None:
        compile_bundle(policy_bundle, pool)
    if any(scenario["campaigns"] for scenario in scenarios) and not any(
        actor.category == "creators_marketing" for actor in cast.actors
    ):
        raise ValueError("campaigns require an explicit creator counterparty")


def _summary(values):
    ordered = sorted(values)
    return {
        "count": len(values), "mean_cents": sum(values) / len(values),
        "minimum_cents": ordered[0], "maximum_cents": ordered[-1],
        "quantiles_cents": {name: ordered[max(1, ceil(p * len(values))) - 1]
                            for name, p in (("p05", .05), ("p50", .5), ("p95", .95))},
        "quantile_method": "nearest_rank",
    }


def _cash_summary(report):
    return _summary([world["net_profit_cents"] for world in report["worlds"]])


def _paired(baseline, variant):
    if baseline["seed"] != variant["seed"] or baseline["cast"] != variant["cast"] or len(baseline["worlds"]) != len(variant["worlds"]):
        raise RuntimeError("experiment arms are not matched")
    pairs = []
    for reference, other in zip(baseline["worlds"], variant["worlds"]):
        if reference["world_id"] != other["world_id"] or reference["external_draws"] != other["external_draws"]:
            raise RuntimeError("experiment world draws are not matched")
        pairs.append({"world_id": reference["world_id"], "external_draws": deepcopy(reference["external_draws"]),
                      "baseline_net_profit_cents": reference["net_profit_cents"],
                      "variant_net_profit_cents": other["net_profit_cents"],
                      "difference_cents": other["net_profit_cents"] - reference["net_profit_cents"]})
    return {"direction": "variant_minus_baseline", "summary": _summary([pair["difference_cents"] for pair in pairs]),
            "worlds_with_higher_cash_profit": sum(pair["difference_cents"] > 0 for pair in pairs), "worlds": pairs}


def _metadata(worlds, seed, arms):
    return {"interpretation": INTERPRETATION, "world_count": worlds, "seed": seed, "plan": "launch_now",
            "cast_fixed": True, "limitations": list(LIMITATIONS),
            "usage": {"model_calls": 0, "model_cost_usd": "0.00", "mode": "offline_experiment",
                      "world_executions": worlds * arms, "cost_scope": "offline_rollouts_only"}}


def compare_policies(scenario: dict, pool: dict, policy_bundle: dict, worlds: int = 100, seed: int = 42) -> dict:
    """Compare rules baseline and explicit policy on identical world IDs/draws."""
    if policy_bundle is None:
        raise ValueError("policy comparison requires an explicit policy bundle")
    _preflight([scenario, scenario], pool, policy_bundle, worlds, seed)
    baseline = simulate(scenario, pool, worlds=worlds, seed=seed)
    policy = simulate(scenario, pool, worlds=worlds, seed=seed, policy_bundle=policy_bundle)
    return {"schema_version": "synthetic-policy-comparison.v1", **_metadata(worlds, seed, 2),
            "baseline": baseline, "policy": policy, "baseline_summary": _cash_summary(baseline),
            "policy_summary": _cash_summary(policy), "paired": _paired(baseline, policy)}


def sensitivity(scenario: dict, pool: dict, *, parameter: str, values: list,
                worlds: int = 100, seed: int = 42, policy_bundle: dict | None = None) -> dict:
    """One-at-a-time sweeps; no averaging or forecast mixing across assumptions."""
    if type(parameter) is not str or parameter not in ALLOWED_PARAMETERS:
        raise ValueError("unsupported sensitivity parameter")
    if type(values) is not list or not 1 <= len(values) <= 16 or any(type(value) is not int for value in values):
        raise ValueError("sensitivity values must contain 1..16 finite integers")
    if len(set(values)) != len(values):
        raise ValueError("sensitivity values must be unique")
    if type(scenario) is not dict:
        raise ValueError("scenario must be a mapping")
    variants = []
    for value in values:
        variant = deepcopy(scenario)
        variant[parameter] = value
        variants.append(variant)
    _preflight([scenario, *variants], pool, policy_bundle, worlds, seed)
    baseline = simulate(scenario, pool, worlds=worlds, seed=seed, policy_bundle=policy_bundle)
    reports = []
    for value, variant in zip(values, variants):
        report = simulate(variant, pool, worlds=worlds, seed=seed, policy_bundle=policy_bundle)
        reports.append({"value": value, "report": report, "summary": _cash_summary(report), "paired": _paired(baseline, report)})
    return {"schema_version": "synthetic-sensitivity.v1", **_metadata(worlds, seed, len(variants) + 1),
            "parameter": parameter, "baseline_value": scenario[parameter], "baseline": baseline,
            "baseline_summary": _cash_summary(baseline), "variants": reports}
