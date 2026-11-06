"""Pure, bounded analysis of declared GeckoTerminal public trade snapshots.

This describes observed addresses; it does not establish human identity, wealth,
wallet age, common control, profitability, or executable persona policies.
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
import hashlib
import json
import math
import re
from urllib.parse import quote

_TOP_KEYS = {"schema_version", "network", "target_days", "captured_at", "pools"}
_POOL_KEYS = {"address", "name", "base_token_address", "quote_token_address", "source_url", "retrieved_at", "trades"}
_UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z\Z")
_UNKNOWN = ["retail_or_institutional_identity", "human_or_bot", "kol_or_market_maker_role", "common_wallet_control",
            "wallet_creation_date", "balances_and_holdings", "available_capital", "realized_profit", "social_influence",
            "risk_preferences", "future_behavior"]


def _keys(value, keys, name):
    if type(value) is not dict or set(value) != keys:
        raise ValueError(f"{name} has missing or unknown fields")


def _text(value, name, limit=256):
    if type(value) is not str or not value or value != value.strip() or len(value) > limit or any(ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF for c in value):
        raise ValueError(f"invalid {name}")
    return value


def _date(value, name):
    if type(value) is not str or not _UTC.fullmatch(value):
        raise ValueError(f"{name} must be a UTC timestamp ending Z")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        raise ValueError(f"invalid {name}") from None


def _iso(value):
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _bounded_json(value):
    """Walk before serialization; cap depth, nodes and aggregate text allocation."""
    nodes = 0
    characters = 0
    stack = [(value, 0)]
    while stack:
        current, depth = stack.pop()
        nodes += 1
        if nodes > 100000 or depth > 10:
            raise ValueError("snapshot JSON resource limit exceeded")
        if type(current) is dict:
            if len(current) > 80:
                raise ValueError("snapshot object too large")
            for key, item in current.items():
                if type(key) is not str or len(key) > 128:
                    raise ValueError("invalid JSON key")
                characters += len(key)
                stack.append((item, depth + 1))
        elif type(current) is list:
            if len(current) > 1000:
                raise ValueError("snapshot list too large")
            stack.extend((item, depth + 1) for item in current)
        elif type(current) is str:
            if len(current) > 2048:
                raise ValueError("snapshot text too long")
            characters += len(current)
        elif type(current) is float:
            if not math.isfinite(current):
                raise ValueError("nonfinite JSON number")
        elif type(current) is int:
            if abs(current) > 10 ** 18:
                raise ValueError("JSON integer too large")
        elif current is not None and type(current) is not bool:
            raise ValueError("snapshot must contain JSON values")
        if characters > 1500000:
            raise ValueError("snapshot text resource limit exceeded")


def _cents(value):
    if type(value) not in {int, float, str} or len(str(value)) > 256:
        raise ValueError("volume_in_usd must be a positive bounded decimal")
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or not 0 < amount <= Decimal("1000000000000"):
            raise ValueError("volume_in_usd must be positive and at most 1e12 USD")
        with localcontext() as context:
            context.prec = max(32, len(amount.as_tuple().digits) + 4)
            return int((amount * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    except (InvalidOperation, OverflowError):
        raise ValueError("invalid volume_in_usd") from None


def _median(values):
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid] + 1) // 2


def _size(cents):
    return "small" if cents <= 10000 else "large" if cents >= 1000000 else "medium"


def _share(amount, total):
    return (amount * 10000 + total // 2) // total if total else 0


def analyze_wallets(snapshot):
    """Validate one network's declared snapshot and return descriptive cohorts.

    Raises ValueError on malformed rows; only the documented exclusion classes
    are skipped. Duplicate identity is (network, pool, event.id), not tx_hash.
    """
    _bounded_json(snapshot)
    _keys(snapshot, _TOP_KEYS, "snapshot")
    if snapshot["schema_version"] != "wallet-observations.v1":
        raise ValueError("unsupported wallet observation schema")
    network = snapshot["network"]
    if type(network) is not str or network not in {"near", "solana"}:
        raise ValueError("network must be near or solana")
    if type(snapshot["target_days"]) is not int or snapshot["target_days"] != 30:
        raise ValueError("target_days must be 30")
    captured = _date(snapshot["captured_at"], "captured_at")
    try:
        start = captured - timedelta(days=30)
    except OverflowError:
        raise ValueError("target window starts before supported dates") from None
    pools = snapshot["pools"]
    if type(pools) is not list or not 1 <= len(pools) <= 4:
        raise ValueError("one to four pools required")
    if any(type(p) is not dict or type(p.get("trades")) is not dict or type(p["trades"].get("data")) is not list for p in pools):
        raise ValueError("pool trades.data must be an array")
    if sum(len(p["trades"]["data"]) for p in pools) > 1000:
        raise ValueError("at most 1000 raw trade records required")
    seen_pools, seen_events, accepted, pool_coverage, sources = set(), {}, [], [], []
    excluded = {"anomalous": 0, "missing_wallet": 0, "unsupported_direction": 0, "outside_window": 0}
    raw_count = duplicates = disagreements = 0
    for pool in sorted(pools, key=lambda p: str(p.get("address"))):
        _keys(pool, _POOL_KEYS, "pool")
        address = _text(pool["address"], "pool.address")
        if address in seen_pools:
            raise ValueError("duplicate pool address")
        seen_pools.add(address)
        _text(pool["name"], "pool.name", 160)
        base = _text(pool["base_token_address"], "base_token_address")
        quote_token = _text(pool["quote_token_address"], "quote_token_address")
        if base == quote_token:
            raise ValueError("pool tokens must differ")
        expected_url = f"https://api.geckoterminal.com/api/v2/networks/{network}/pools/{quote(address, safe='')}/trades"
        pro_url = f"https://pro-api.coingecko.com/api/v3/onchain/networks/{network}/pools/{quote(address, safe='')}/trades"
        if pool["source_url"] not in (expected_url, pro_url, pro_url + "/range"):
            raise ValueError("source_url must exactly match a declared network/pool provider trades endpoint")
        provider = "GeckoTerminal" if pool["source_url"] == expected_url else "CoinGecko Pro"
        retrieved = _date(pool["retrieved_at"], "retrieved_at")
        _keys(pool["trades"], {"data"}, "pool.trades")
        times, provider_times = [], []
        pool_accepted = 0
        pool_excluded = dict.fromkeys(excluded, 0)
        pool_duplicates = 0
        for event in pool["trades"]["data"]:
            raw_count += 1
            if type(event) is not dict or event.get("type") != "trade" or type(event.get("attributes")) is not dict:
                raise ValueError("invalid provider trade record")
            event_id = _text(event.get("id"), "event.id", 512)
            if event_id.startswith(("near_", "solana_")) and not event_id.startswith(network + "_"):
                raise ValueError("trade event ID belongs to another network")
            key = (network, address, event_id)
            canonical = _canonical(event)
            if key in seen_events:
                if seen_events[key] != canonical:
                    raise ValueError("conflicting duplicate event ID")
                duplicates += 1
                pool_duplicates += 1
                continue
            seen_events[key] = canonical
            attrs = event["attributes"]
            when = _date(attrs.get("block_timestamp"), "block_timestamp")
            if when > retrieved or when > captured:
                raise ValueError("trade timestamp is after retrieval/capture")
            provider_times.append(when)
            tx_hash = _text(attrs.get("tx_hash"), "tx_hash")
            cents = _cents(attrs.get("volume_in_usd"))
            kind = attrs.get("kind")
            if kind is not None:
                _text(kind, "kind", 32)
            anomalous = attrs.get("is_anomalous", False)
            if type(anomalous) is not bool:
                raise ValueError("is_anomalous must be boolean")
            wallet = attrs.get("tx_from_address")
            if wallet is not None:
                _text(wallet, "tx_from_address")
            from_token = attrs.get("from_token_address")
            to_token = attrs.get("to_token_address")
            for token in (from_token, to_token):
                if token is not None:
                    _text(token, "trade token address")
            direction = "buy" if (from_token, to_token) == (quote_token, base) else "sell" if (from_token, to_token) == (base, quote_token) else None
            reason = "anomalous" if anomalous else "missing_wallet" if wallet is None else "unsupported_direction" if direction is None else "outside_window" if when < start else None
            if reason:
                excluded[reason] += 1
                pool_excluded[reason] += 1
                continue
            if attrs.get("kind") in {"buy", "sell"} and attrs["kind"] != direction:
                disagreements += 1
            times.append(when)
            pool_accepted += 1
            accepted.append({"address": wallet, "pool_address": address, "event_id": event_id, "tx_hash": tx_hash,
                             "timestamp": _iso(when), "direction": direction, "notional_cents": cents})
        pool_coverage.append({"pool_address": address, "name": pool["name"], "raw_records": len(pool["trades"]["data"]),
                              "duplicate_records": pool_duplicates, "accepted_trades": pool_accepted, "excluded": pool_excluded,
                              "earliest_observed_at": _iso(min(times)) if times else None,
                              "latest_observed_at": _iso(max(times)) if times else None,
                              "provider_slice_earliest_at": _iso(min(provider_times)) if provider_times else None,
                              "provider_slice_latest_at": _iso(max(provider_times)) if provider_times else None})
        sources.append({"pool_address": address, "name": pool["name"], "base_token_address": base,
                        "quote_token_address": quote_token, "source_url": pool["source_url"], "provider": provider, "retrieved_at": _iso(retrieved)})
    by_wallet = defaultdict(list)
    pool_totals = defaultdict(int)
    for row in accepted:
        by_wallet[row["address"]].append(row)
        pool_totals[row["pool_address"]] += row["notional_cents"]
    total = sum(row["notional_cents"] for row in accepted)
    profiles = []
    for address, rows in sorted(by_wallet.items()):
        rows.sort(key=lambda r: (_date(r["timestamp"], "timestamp"), r["pool_address"], r["event_id"]))
        buys = sum(r["direction"] == "buy" for r in rows)
        sells = len(rows) - buys
        amount = sum(r["notional_cents"] for r in rows)
        median = _median([r["notional_cents"] for r in rows])
        size = _size(median)
        activity = "both_directions" if buys and sells else "one_direction"
        per_pool = []
        for pool_address in sorted({r["pool_address"] for r in rows}):
            subset = [r for r in rows if r["pool_address"] == pool_address]
            subtotal = sum(r["notional_cents"] for r in subset)
            per_pool.append({"pool_address": pool_address, "trade_count": len(subset),
                             "buys": sum(r["direction"] == "buy" for r in subset),
                             "sells": sum(r["direction"] == "sell" for r in subset),
                             "notional_cents": subtotal, "observed_pool_volume_share_bps": _share(subtotal, pool_totals[pool_address])})
        references = [{k: r[k] for k in ("pool_address", "event_id", "tx_hash", "timestamp", "direction", "notional_cents")} for r in rows]
        profile_id = hashlib.sha256((network + "\0" + address).encode()).hexdigest()
        profiles.append({"profile_id": profile_id, "address": address, "network": network, "buys": buys, "sells": sells,
                         "trade_count": len(rows), "total_notional_cents": amount, "median_notional_cents": median,
                         "first_observed_at": rows[0]["timestamp"], "last_observed_at": rows[-1]["timestamp"],
                         "observed_volume_share_bps": _share(amount, total), "observed_size": size, "activity": activity,
                         "both_directions_observed": bool(buys and sells), "sources": per_pool,
                         "description": f"Observed address with {len(rows)} swaps across {len(per_pool)} sampled pools: {buys} base-token buys and {sells} base-token sells. Median observed swap ${median / 100:,.2f}; total sampled notional ${amount / 100:,.2f}. {size.capitalize()} observed-trade-size cohort; {activity.replace('_', ' ')} activity. First observed in this slice at {rows[0]['timestamp']}; this is not its creation date. Identity, holdings, capital and motives are unknown.",
                         "unknown_traits": list(_UNKNOWN),
                         "evidence": {"reference_count": len(references), "references": references[:30], "truncated": len(references) > 30,
                                      "all_references_sha256": hashlib.sha256(_canonical(references).encode()).hexdigest()}})
    cohort_map = defaultdict(list)
    for profile in profiles:
        cohort_map[(profile["observed_size"], profile["activity"])].append(profile)
    cohorts = [{"cohort_id": f"{size}:{activity}", "size": size, "activity": activity, "wallet_count": len(members),
                "trade_count": sum(p["trade_count"] for p in members),
                "notional_cents": sum(p["total_notional_cents"] for p in members),
                "profile_ids": [p["profile_id"] for p in members]} for (size, activity), members in sorted(cohort_map.items())]
    return {"schema_version": "wallet-cohorts.v1", "network": network, "simulation_effect": "none",
            "target_window": {"requested_days": 30, "start": _iso(start), "end": _iso(captured), "inclusive": True},
            "coverage": {"status": "recent_provider_slice", "complete_target_window": False, "history_attested": False,
                         "kind_direction_disagreements": disagreements, "pools": pool_coverage,
                         "threshold_basis": "analyst_chosen_median_observed_trade_usd",
                         "size_thresholds_usd": {"small_max_inclusive": 100, "large_min_inclusive": 10000},
                         "exclusion_precedence": list(excluded)},
            "source_metadata": {"provider": "CoinGecko / GeckoTerminal", "verification": "provider_declared_unverified",
                                "network_reliability": "declared_not_chain_attested",
                                "captured_at": _iso(captured), "sources": sources},
            "summary": {"raw_records": raw_count, "duplicate_records": duplicates, "accepted_trades": len(accepted),
                        "observed_wallets": len(profiles), "observed_notional_cents": total, "excluded": excluded},
            "cohorts": cohorts, "profiles": profiles,
            "limitations": ["Recent provider slice only; a 30-day target is not a complete 30-day history, even if endpoints span 30 days.",
                            "Timestamps, sender attribution and USD values are provider declarations, not independently verified RPC observations.",
                            "Observed addresses may be routers, bots or custodians; an address is not necessarily one person.",
                            "Sizes and activity groups are descriptive analyst choices, not verified retail, KOL, market-maker, whale or sybil identities.",
                            "Both trade directions do not establish a profitable round trip; no balances, holdings, wallet age or common funding were retrieved.",
                            "Observed pool shares refer only to accepted sampled swaps, not the whole market or wallet portfolio.",
                            "Profiles do not assign simulator capital or rules and are not calibrated executable personas.",
                            "NEAR and Solana snapshots are analyzed separately; neither chain supplies the other's behavioral assumptions."]}
