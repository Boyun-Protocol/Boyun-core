"""Bounded public GeckoTerminal GET snapshots; no keys, backfill or retries.

Public recent-trades slices accumulate only while a caller actually collects.
Repeated overlapping slices never establish a complete chain history. Trusted
test transports share market_sources' keyword-only bytes transport contract.
"""
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import json
import time
from urllib.error import HTTPError
from urllib.parse import quote

from .io_helpers import json_bytes
from .market_sources import (_TOKEN, _bounded_text, _float, _integer, _nonfinite,
                             _pairs, _trade, _urllib_transport)
from .wallet_evidence import analyze_wallets

MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_PUBLIC_REQUESTS = 8
_ROOT = "https://api.geckoterminal.com/api/v2/networks"


class PublicCaptureError(ValueError):
    """Sanitized error; request count is attempts, not proof of remote success."""

    def __init__(self, code, *, request_count=0, retry_after_seconds=None):
        self.code = code
        self.request_count = request_count
        self.retry_after_seconds = retry_after_seconds
        super().__init__(f"Public collection failed ({code}); attempts={request_count}.")


def _now():
    return datetime.now(timezone.utc)


def _timestamp(now_fn):
    value = now_fn()
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError("timezone-aware clock required")
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _url(network, address):
    return f"{_ROOT}/{network}/pools/{quote(address, safe='')}/trades"


def _snapshot(network, pool, at, rows=None):
    return {"schema_version": "wallet-observations.v1", "network": network,
            "target_days": 30, "captured_at": at,
            "pools": [{**pool, "source_url": _url(network, pool["address"]),
                       "retrieved_at": at, "trades": {"data": rows or []}}]}


def _validate_pool(network, pool, at):
    if type(network) is not str or network not in {"near", "solana"}:
        raise ValueError("unsupported network")
    keys = {"address", "name", "base_token_address", "quote_token_address"}
    if type(pool) is not dict or set(pool) != keys:
        raise ValueError("explicit pool metadata required")
    clean = {key: _bounded_text(pool[key], maximum=160 if key == "name" else 256) for key in keys}
    if any(not _TOKEN.fullmatch(clean[key]) for key in keys - {"name"}):
        raise ValueError("invalid address")
    analyze_wallets(_snapshot(network, clean, at))
    return clean


def validate_public_config(config, *, at=None):
    """Preflight every pool before any request or partially successful collection."""
    try:
        if type(config) is not dict or not config or set(config) - {"near", "solana"}:
            raise ValueError("explicit network pool lists required")
        at = at or _timestamp(_now)
        result = []
        for network in ("near", "solana"):
            if network not in config:
                continue
            pools = config[network]
            if type(pools) is not list or not 1 <= len(pools) <= 4:
                raise ValueError("one to four pools per network required")
            seen = set()
            for pool in pools:
                clean = _validate_pool(network, pool, at)
                if clean["address"] in seen:
                    raise ValueError("duplicate pool")
                seen.add(clean["address"])
                result.append((network, clean))
        return result
    except (ValueError, TypeError, OverflowError):
        raise PublicCaptureError("invalid_request") from None


def _retry_after(headers, now_fn):
    try:
        value = headers.get("Retry-After")
        if type(value) is not str or len(value) > 128:
            return None
        if value.isascii() and value.isdecimal():
            return min(3600, int(value))
        delta = (parsedate_to_datetime(value) - now_fn()).total_seconds()
        return max(0, min(3600, int(delta)))
    except (TypeError, ValueError, OverflowError, AttributeError):
        return None


def capture_public_pool(*, network, pool, transport=None, timeout_seconds=10, now_fn=None):
    """Return one analyzer-compatible public snapshot and an honest slice receipt.

    The fixed endpoint returns at most its recent 300 trades, not a 30-day
    historical window. Socket timeout is bounded; it is not a total wall timer.
    No credentials, environment variables, proxy config or redirects are used.
    """
    clock = now_fn or _now
    try:
        _integer(timeout_seconds, 1, 30)
        if transport is not None and not callable(transport):
            raise ValueError("invalid transport")
        clean = _validate_pool(network, pool, _timestamp(clock))
    except (ValueError, TypeError, OverflowError):
        raise PublicCaptureError("invalid_request") from None
    try:
        raw = (transport or _urllib_transport)(endpoint=_url(network, clean["address"]),
            headers={"Accept": "application/json"}, timeout_seconds=timeout_seconds,
            max_response_bytes=MAX_RESPONSE_BYTES)
    except HTTPError as error:
        if error.code == 429:
            raise PublicCaptureError("rate_limited", request_count=1,
                retry_after_seconds=_retry_after(error.headers, clock)) from None
        raise PublicCaptureError("transport_failed", request_count=1) from None
    except Exception:
        raise PublicCaptureError("transport_failed", request_count=1) from None
    try:
        at = _timestamp(clock)
        if type(raw) is not bytes or len(raw) > MAX_RESPONSE_BYTES:
            raise ValueError("invalid bounded response")
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                           parse_constant=_nonfinite, parse_float=_float)
        if (type(value) is not dict or "error" in value or "errors" in value
                or type(value.get("data")) is not list or len(value["data"]) > 300):
            raise ValueError("invalid provider response")
        rows = [_trade(row)[0] for row in value["data"]]
        snapshot = _snapshot(network, clean, at, rows)
        analysis = analyze_wallets(snapshot)
        if len(json_bytes(snapshot)) > MAX_RESPONSE_BYTES:
            raise ValueError("serialized snapshot exceeds input limit")
        return snapshot, {"network": network, "address": clean["address"],
            "captured_at": at, "request_count": 1, "records": len(rows),
            "accepted_trades": analysis["summary"]["accepted_trades"],
            "coverage": "recent_provider_slice", "complete_history": False}
    except Exception:
        raise PublicCaptureError("invalid_response", request_count=1) from None


def collect_public(*, config, archive, allow_network=False, max_requests=4,
                   timeout_seconds=10, spacing_seconds=5, transport=None,
                   sleep_fn=None, now_fn=None):
    """One bounded pass. A 429 stops the pass; no failed request is retried."""
    if allow_network is not True:
        raise PublicCaptureError("network_opt_in_required")
    clock = now_fn or _now
    try:
        _integer(max_requests, 1, MAX_PUBLIC_REQUESTS)
        _integer(timeout_seconds, 1, 30)
        _integer(spacing_seconds, 5, 60)
        for injected in (transport, sleep_fn, now_fn):
            if injected is not None and not callable(injected):
                raise ValueError("invalid callable")
        at = _timestamp(clock)
        pools = validate_public_config(config, at=at)
    except (ValueError, TypeError, OverflowError):
        raise PublicCaptureError("invalid_request") from None
    receipt = {"schema_version": "public-collection-receipt.v1",
        "provider": "geckoterminal-public", "started_at": at,
        "request_count": 0, "success_count": 0, "failure_count": 0,
        "skipped_count": 0, "max_requests": max_requests,
        "automatic_retry": False, "rate_limited": False,
        "complete_history": False, "coverage": "accumulating_public_slices",
        "pools": []}
    for network, pool in pools:
        result = {"network": network, "address": pool["address"]}
        receipt["pools"].append(result)
        if receipt["rate_limited"] or receipt["request_count"] >= max_requests:
            result["status"] = "rate_limit_stop" if receipt["rate_limited"] else "request_limit"
            receipt["skipped_count"] += 1
            continue
        if receipt["request_count"]:
            (sleep_fn or time.sleep)(spacing_seconds)
        try:
            snapshot, captured = capture_public_pool(network=network, pool=pool,
                transport=transport, timeout_seconds=timeout_seconds, now_fn=clock)
        except PublicCaptureError as error:
            receipt["request_count"] += error.request_count
            receipt["failure_count"] += 1
            result.update(status="failed", error_code=error.code,
                          retry_after_seconds=error.retry_after_seconds)
            archive.record_failure(network, pool["address"], _timestamp(clock), error.code,
                                   pool_metadata=pool)
            if error.code == "rate_limited":
                receipt["rate_limited"] = True
            continue
        receipt["request_count"] += captured["request_count"]
        # Archive failure is deliberately not mislabeled as successful capture.
        archive_result = archive.record_snapshot(snapshot)
        receipt["success_count"] += 1
        result.update(captured, status="captured", archive=archive_result)
    receipt["finished_at"] = _timestamp(clock)
    return receipt
