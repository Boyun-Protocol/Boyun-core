"""Synthetic discrete-event experiment; no network, model inference or trading.

Exogenous draws have stable identities. Feeds deliver bounded messages; policies
receive only their own observation/account snapshot. All transfers use Ledger.
"""
import hashlib
import heapq
import json
from copy import deepcopy
from importlib.resources import files
from math import isqrt

from .actors import TRADING_CATEGORIES, build_cast, default_recipe
from .finance import Balance, ConstantProductMarket, Ledger
from .policies import Message, decide, select_messages
from .policy_bundles import compile_bundle
from .randomness import keyed_rng


PLANS = ("launch_now", "lower_marketing", "defer_launch", "do_not_launch")


def default_scenario() -> dict:
    return {
        "schema_version": "synthetic-scenario.v1",
        "mode": "synthetic",
        "name": "Fictional Paris event launch — not a forecast",
        "horizon_hours": 720,
        "capital_cents": 1_000_000,
        "launch_cost_cents": 100_000,
        "lp_cash_cents": 400_000,
        "lp_tokens": 1_000_000,
        "founder_tokens": 3_000_000,
        "fee_bps": 30,
        "founder_vested_at_hour": 24,
        "lp_unlock_at_hour": 721,
        "founder_sales": [{"at_hour": 72, "token_units": 300_000},
                          {"at_hour": 168, "token_units": 300_000}],
        "campaigns": [{"at_hour": h, "fee_cents": 50_000} for h in (5, 9, 17, 33)],
        "campaign_budget_cents": 200_000,
        "news_enabled": True,
        "catalyst_probability_bps": 6500,
        "followup_positive_probability_bps": 4500,
        "competitor_messages": [{"at_hour": h} for h in (5, 9, 17, 33, 49, 73)],
        "observation_window_hours": 48,
        "visit_interval_hours": 6,
        "max_slippage_bps": 500,
        "cast_recipe": default_recipe(),
        "assumptions": [
            {"id": "fixture-population-and-capital", "status": "assumed", "rationale": "Explicit synthetic participant composition and cash ranges; not measured NEAR demand."},
            {"id": "fixture-news-probabilities", "status": "assumed", "rationale": "65% catalyst and 45% favorable follow-up are demonstration inputs, not estimates of a real event."},
            {"id": "fixture-feed-and-campaign", "status": "assumed", "rationale": "Funded posts, uniform finite-capacity subscription feeds, six-hour visits and a 48-hour attention window; not a real platform algorithm."},
            {"id": "fixture-venue", "status": "assumed", "rationale": "Integer-cent constant-product market with 30bps fee; not verified launchpad mechanics."},
        ],
    }


def load_pool() -> dict:
    return json.loads(files("decision_lab").joinpath("data/personas.json").read_text())


def _int(value, name, minimum=0, maximum=None):
    if type(value) is not int or value < minimum or (maximum is not None and value > maximum):
        raise ValueError(f"invalid {name}")


def _validate(value, worlds, seed, plan):
    if not isinstance(value, dict) or value.get("mode") != "synthetic":
        raise ValueError("only explicitly synthetic scenarios supported")
    if "user_brief" in value:
        brief = value["user_brief"]
        limits = {"question": 2000, "event": 160, "ticker": 24}
        if (type(brief) is not dict or set(brief) != set(limits)
                or any(type(brief[key]) is not str or len(brief[key]) > limit for key, limit in limits.items())
                or not brief["question"].strip()):
            raise ValueError("invalid user brief")
    _int(worlds, "worlds", 1, 100_000)
    _int(seed, "seed")
    if plan not in PLANS:
        raise ValueError("unknown plan")
    for key in ("capital_cents", "lp_cash_cents", "lp_tokens", "founder_tokens", "horizon_hours", "visit_interval_hours", "observation_window_hours"):
        _int(value.get(key), key, 1)
    for key in ("launch_cost_cents", "campaign_budget_cents", "founder_vested_at_hour", "lp_unlock_at_hour"):
        _int(value.get(key), key)
    for key in ("catalyst_probability_bps", "followup_positive_probability_bps", "max_slippage_bps"):
        _int(value.get(key), key, 0, 10_000)
    _int(value.get("fee_bps"), "fee_bps", 0, 9999)
    if type(value.get("news_enabled")) is not bool:
        raise ValueError("invalid news_enabled")
    if value["founder_tokens"] < value["lp_tokens"]:
        raise ValueError("LP allocation exceeds token inventory")
    if value["capital_cents"] != value.get("cast_recipe", {}).get("founder_initial_cash_cents"):
        raise ValueError("founder capital and recipe disagree")
    if value["lp_unlock_at_hour"] <= value["horizon_hours"]:
        raise ValueError("first fixture requires LP locked beyond horizon; withdrawal policy not implemented")
    for key in ("campaigns", "founder_sales", "competitor_messages"):
        if not isinstance(value.get(key), list):
            raise ValueError(f"invalid {key}")
        for entry in value[key]:
            if not isinstance(entry, dict):
                raise ValueError(f"invalid {key} entry")
            _int(entry.get("at_hour"), f"{key} time", 0)
            if key == "campaigns":
                _int(entry.get("fee_cents"), "campaign fee", 0)
            if key == "founder_sales":
                _int(entry.get("token_units"), "founder sale", 1)
    total_campaign = sum(c["fee_cents"] for c in value["campaigns"])
    if total_campaign > value["campaign_budget_cents"]:
        raise ValueError("campaign obligations exceed approved campaign budget")
    if value["launch_cost_cents"] + value["lp_cash_cents"] + total_campaign > value["capital_cents"]:
        raise ValueError("campaign and launch obligations exceed capital")
    if not isinstance(value.get("assumptions"), list) or not value["assumptions"]:
        raise ValueError("declared assumptions required")


def _bin(profit):
    if profit < -500_000:
        return "severe_loss"
    if profit < 0:
        return "loss"
    if profit < 2_000_000:
        return "modest_profit"
    return "large_profit"


def _world(value, cast, seed, world_id, plan, keep_trace, bundle=None):
    external = {
        "catalyst_draw_bps": keyed_rng(seed, "external", world_id, "catalyst").randrange(10_000),
        "followup_draw_bps": keyed_rng(seed, "external", world_id, "followup").randrange(10_000),
    }
    accounts = {a.owner_id: Balance(a.initial_cash_cents) for a in cast.actors if a.owner_id != "project"}
    accounts.update(project=Balance(value["capital_cents"], value["founder_tokens"]), pool=Balance(), services=Balance())
    ledger = Ledger(accounts)
    starting = ledger.totals()
    actor_by_id = {a.id: a for a in cast.actors}
    creators = [a for a in cast.actors if a.category == "creators_marketing"]
    if value["campaigns"] and not creators:
        raise ValueError("campaigns require an explicit creator counterparty")
    horizon = value["horizon_hours"]
    launch_time = 24 if plan == "defer_launch" else 0
    campaigns = value["campaigns"] if plan != "lower_marketing" else value["campaigns"][:len(value["campaigns"]) // 2]
    market = None
    messages = []
    seen_messages = {a.id: set() for a in cast.actors}
    beliefs = {a.id: {} for a in cast.actors}
    seen_claims = {a.id: set() for a in cast.actors}
    cost_basis = {a.id: 0 for a in cast.actors}
    trace = []
    campaign_paid = 0
    delivered_campaigns = 0
    buys = 0
    sells = 0
    launch_paid = 0
    founder_proceeds = 0
    proposal_rejections = 0
    exposures = 0
    queue = []
    sequence = 0

    def push(at, priority, kind, payload):
        nonlocal sequence
        if at <= horizon:
            heapq.heappush(queue, (at, priority, sequence, kind, payload))
            sequence += 1

    def log(at, kind, **data):
        if keep_trace and len(trace) < 500:
            trace.append({"at_hour": at, "kind": kind, **data})

    if plan != "do_not_launch":
        push(launch_time, 0, "launch", None)
        for i, campaign in enumerate(campaigns):
            push(launch_time + campaign["at_hour"], 1, "campaign", (i, campaign))
        for i, sale in enumerate(value["founder_sales"]):
            push(launch_time + sale["at_hour"], 2, "founder_sale", (i, sale))
    if value["news_enabled"]:
        status = "confirmed" if external["catalyst_draw_bps"] < value["catalyst_probability_bps"] else "rumor"
        push(1, 1, "message", Message("news-initial", "catalyst", "news", 1, status))
        favorable = external["followup_draw_bps"] < value["followup_positive_probability_bps"]
        push(96, 1, "message", Message("news-followup", "followup" if favorable else "catalyst", "news", 96, "confirmed" if favorable else "contradicted"))
    for i, entry in enumerate(value["competitor_messages"]):
        at = entry["at_hour"]
        push(at, 1, "message", Message(f"competitor-{i}", f"rival-{i}", "competitor", at, "confirmed", asset="competitor"))
    interval = value["visit_interval_hours"]
    for at in range(0, horizon + 1, interval):
        push(at, 3, "visit_batch", None)

    while queue:
        at, _, _, kind, payload = heapq.heappop(queue)
        if kind == "launch":
            ledger.transfer("launch-fee", "project", "services", value["launch_cost_cents"])
            ledger.transfer("initial-lp", "project", "pool", value["lp_cash_cents"], value["lp_tokens"])
            shares = isqrt(value["lp_cash_cents"] * value["lp_tokens"])
            market = ConstantProductMarket(ledger, fee_bps=value["fee_bps"], lp_shares={"project": shares})
            launch_paid = value["launch_cost_cents"]
            log(at, "launch", lp_cash_cents=value["lp_cash_cents"], paid_cost_cents=launch_paid)
        elif kind == "message":
            messages.append(payload)
            log(at, "publication", message_id=payload.id, origin=payload.origin, source=payload.source, asset=payload.asset, status=payload.status)
        elif kind == "campaign" and market:
            i, campaign = payload
            # First fixture: explicit accepted deliverable, pay on publication;
            # no debt or payment for undelivered end-of-horizon items.
            creator = creators[i % len(creators)]
            ledger.transfer(f"campaign-{i}", "project", creator.owner_id, campaign["fee_cents"])
            campaign_paid += campaign["fee_cents"]
            delivered_campaigns += 1
            # A paid repost can amplify public evidence, never reveal a hidden
            # draw or reverse a contradiction by repeating an older claim.
            evidence = [m for m in messages if m.public and m.asset == "project"
                        and m.origin == "catalyst" and m.published_at <= at
                        and m.source != "creator"]
            priority = {"rumor": 0, "confirmed": 1, "contradicted": 2}
            latest = max(evidence, key=lambda m: (m.published_at, priority[m.status], m.id)) if evidence else None
            status = latest.status if latest else "rumor"
            messages.append(Message(f"campaign-{i}", "catalyst", "creator", at, status))
            log(at, "campaign_delivery", paid_cents=campaign["fee_cents"], recipient=creator.id,
                status=status, evidence_message_id=latest.id if latest else None)
        elif kind == "founder_sale" and market:
            i, sale = payload
            try:
                if at < value["founder_vested_at_hour"]:
                    raise ValueError("founder tokens not vested")
                fill = market.sell("project", sale["token_units"], f"founder-sale-{i}", min_cash_cents=1)
                founder_proceeds += fill.cash_cents
                log(at, "founder_sale", cash_cents=fill.cash_cents, token_units=fill.token_units)
            except ValueError as error:
                proposal_rejections += 1
                log(at, "founder_sale_rejected", rejection=str(error))
        elif kind == "visit_batch":
            eligible = [m for m in messages if at - m.published_at <= value["observation_window_hours"]]
            proposals = []
            # All decisions use the same start-of-phase snapshot, then execute
            # in a seeded order against updated reserves/minimum-output bounds.
            for actor in cast.actors:
                observed = select_messages(actor, eligible, at, seen_messages[actor.id], keyed_rng(seed, "feed", world_id, actor.id, at))
                exposures += len(observed)
                seen_messages[actor.id].update(m.id for m in observed)
                # Delivery consumes attention once. Remembered public evidence
                # persists across visits and rejected executions; it is never
                # refreshed from the global feed without actual delivery.
                status_rank = {"rumor": 0, "confirmed": 1, "contradicted": 2}
                for message in observed:
                    key = (message.asset, message.origin)
                    previous = beliefs[actor.id].get(key)
                    rank = (message.published_at, status_rank[message.status], message.id)
                    if previous is None or rank > (previous.published_at, status_rank[previous.status], previous.id):
                        beliefs[actor.id][key] = message
                balance = ledger.accounts[actor.owner_id]
                rule = bundle.rules.get(actor.template_id) if bundle else None
                fallback = bundle.fallback if bundle else "baseline"
                action = decide(actor, beliefs[actor.id].values(), balance.cash_cents, balance.token_units,
                                cost_basis[actor.id], seen_claims[actor.id], at, rule, fallback=fallback)
                if market and action.kind in {"buy", "sell"} and actor.owner_id != "project":
                    reserves = ledger.accounts["pool"]
                    buying = action.kind == "buy"
                    reserve_in, reserve_out = (reserves.cash_cents, reserves.token_units) if buying else (reserves.token_units, reserves.cash_cents)
                    effective = action.amount * (10_000 - value["fee_bps"]) // 10_000
                    quote_output = reserve_out * effective // (reserve_in + effective)
                    minimum = max(1, quote_output * (10_000 - value["max_slippage_bps"]) // 10_000)
                    proposals.append((actor.id, action, minimum))
            keyed_rng(seed, "execution-order", world_id, at).shuffle(proposals)
            for actor_id, action, minimum in proposals:
                actor = actor_by_id[actor_id]
                event_id = f"action:{actor_id}:{at}"
                try:
                    if action.kind not in actor.allowed_actions:
                        raise ValueError("actor not authorized")
                    if action.kind == "buy":
                        fill = market.buy(actor.owner_id, action.amount, event_id, min_tokens=minimum)
                        cost_basis[actor_id] += fill.cash_cents
                        buys += 1
                    else:
                        before_tokens = ledger.accounts[actor.owner_id].token_units
                        fill = market.sell(actor.owner_id, action.amount, event_id, min_cash_cents=minimum)
                        cost_basis[actor_id] = cost_basis[actor_id] * (before_tokens - fill.token_units) // before_tokens
                        sells += 1
                    seen_claims[actor_id].update(action.evidence_origins)
                    log(at, "participant_" + action.kind, actor_id=actor_id, cash_cents=fill.cash_cents, token_units=fill.token_units, reason=action.reason)
                except ValueError as error:
                    proposal_rejections += 1
                    log(at, "proposal_rejected", actor_id=actor_id, rejection=str(error))
        if ledger.totals() != starting:
            raise RuntimeError("conservation invariant violated")

    ending_cash = ledger.accounts["project"].cash_cents
    net_profit = ending_cash - value["capital_cents"]
    return {
        "world_id": world_id, "external_draws": external,
        "initial_totals": list(starting), "ending_totals": list(ledger.totals()),
        "project_cash_cents": ending_cash, "net_profit_cents": net_profit,
        "unsold_project_tokens": ledger.accounts["project"].token_units,
        "locked_project_lp_shares": market.lp_shares.get("project", 0) if market else 0,
        "campaign_paid_cents": campaign_paid, "unpaid_obligations_cents": 0,
        "delivered_campaigns": delivered_campaigns, "participant_buys": buys,
        "participant_sells": sells, "observed_message_count": exposures,
        "proposal_rejections": proposal_rejections,
        "cash_bridge": {"contributed_capital_cents": value["capital_cents"], "launch_paid_cents": launch_paid,
                        "lp_cash_allocated_cents": value["lp_cash_cents"] if market else 0,
                        "campaign_paid_cents": campaign_paid, "founder_sale_proceeds_cents": founder_proceeds,
                        "ending_withdrawable_cash_cents": ending_cash},
        "trace": trace, "trace_limited_to_events": 500 if keep_trace else 0,
    }


def _policy_bindings(cast, bundle):
    counts = dict.fromkeys(("explicit_rule", "baseline_fallback", "abstain_fallback", "passive_role"), 0)
    bindings = []
    for actor in cast.actors:
        if actor.category not in TRADING_CATEGORIES or actor.strategy not in {"cautious", "momentum"}:
            mode = "passive_role"
        elif actor.template_id in bundle.rules:
            mode = "explicit_rule"
        else:
            mode = bundle.fallback + "_fallback"
        counts[mode] += 1
        bindings.append({"actor_id": actor.id, "template_id": actor.template_id, "mode": mode})
    return {"counts": counts, "actors": bindings}


def _prepare_simulation(scenario, pool, worlds, seed, plan, policy_bundle):
    _validate(scenario, worlds, seed, plan)
    value = deepcopy(scenario)
    cast = build_cast(pool, value["cast_recipe"], seed)
    bundle = compile_bundle(policy_bundle, pool) if policy_bundle is not None else None
    return value, cast, bundle


def simulate(scenario: dict, pool: dict, worlds: int = 100, seed: int = 42,
             plan: str = "launch_now", policy_bundle: dict | None = None) -> dict:
    value, cast, bundle = _prepare_simulation(scenario, pool, worlds, seed, plan, policy_bundle)
    results = [_world(value, cast, seed, i, plan, i < 3, bundle) for i in range(worlds)]
    return _summarize_worlds(value, pool, cast, results, seed, plan, bundle)


def _summarize_worlds(value, pool, cast, results, seed, plan, bundle):
    worlds = len(results)
    counts = {name: 0 for name in ("severe_loss", "loss", "modest_profit", "large_profit")}
    for world in results:
        counts[_bin(world["net_profit_cents"])] += 1
    canonical = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    result = {
        "schema_version": "synthetic-result.v1", "plan": plan, "seed": seed, "world_count": worlds,
        "interpretation": "conditional_synthetic_frequency_not_calibrated_real_world_odds",
        "policy_version": "policy-bundle.v1" if bundle else "rules-only.v1",
        "policy_bundle": bundle.as_dict() if bundle else None,
        "policy_bundle_sha256": bundle.sha256 if bundle else None,
        "policy_provenance_status": "declared_unverified" if bundle else None,
        "policy_bindings": _policy_bindings(cast, bundle) if bundle else None,
        "scenario_sha256": hashlib.sha256(canonical.encode()).hexdigest(),
        "cast": {"template_pool_count": len(pool["profiles"]), "selected_count": len(cast.actors), "excluded": cast.excluded,
                 "actors": [{"id": a.id, "template_id": a.template_id, "category": a.category, "owner_id": a.owner_id,
                             "initial_cash_cents": a.initial_cash_cents, "strategy": a.strategy, "provenance": a.provenance} for a in cast.actors]},
        "assumptions": value["assumptions"], "worlds": results,
        "outcomes": [{"id": name, "count": count, "frequency": count / worlds} for name, count in counts.items()],
        "usage": {"mode": "offline_policy_bundle" if bundle else "offline_rules_baseline",
                  "model_calls": 0, "model_cost_usd": "0.00", "cost_scope": "offline_rollouts_only"},
        "limitations": ["Synthetic venue, population, capital, news and campaign assumptions; not fitted to real launch history.",
                        "One fixed sampled cast per experiment; worlds vary external outcomes and feed/execution sampling.",
                        "Delivered claim states persist without belief decay; the 48-hour default limits feed availability, not memory.",
                        "No real launchpad, per-world model inference, price-history beliefs or empirical calibration in these rollouts.",
                        "Bundle source metadata is declared, not model-call attestation or scientific validation; compilation checks structure and bounds only.",
                        "Campaign acceptance is fixture-prespecified, paid on delivery; other LP/competitor agents are observation-only.",
                        "LP locked past horizon; token inventory and LP shares excluded from cash profit. Cash recovery is not economic mark-to-market P&L.",
                        "Full selected trace capped at 500 events for the first 3 worlds; remaining worlds retain aggregates only."],
    }

    from .scenario_overview import summarize_scenarios
    result["overview"] = summarize_scenarios(result, value)
    if "user_brief" in value:
        result["user_brief"] = deepcopy(value["user_brief"])
    return result


def compare_plans(scenario: dict, pool: dict, worlds: int = 100, seed: int = 42, policy_bundle: dict | None = None) -> dict:
    reports = {name: simulate(scenario, pool, worlds, seed, name, policy_bundle) for name in PLANS}
    base = reports["launch_now"]["worlds"]
    paired = []
    for name in PLANS[1:]:
        differences = [other["net_profit_cents"] - ref["net_profit_cents"] for ref, other in zip(base, reports[name]["worlds"])]
        paired.append({"plan": name, "relative_to": "launch_now", "mean_cash_profit_difference_cents": sum(differences) / worlds,
                       "worlds_with_higher_cash_profit": sum(d > 0 for d in differences)})
    return {"schema_version": "synthetic-comparison.v1", "plans": reports, "paired_comparisons": paired}
