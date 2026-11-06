"""Bounded CoinGecko Pro pool-trade history collection; no retries or key storage.

This is an authenticated Analyst-or-higher API adapter, not a promise that an
account has entitlement or that provider history equals all on-chain activity.
The caller explicitly chooses pools and supplies a key in memory. No environment
variables, config files, wallets or model providers are accessed here.

Injected trusted transports accept keyword-only ``endpoint``, ``headers``,
``timeout_seconds`` and ``max_response_bytes`` and return bytes. They must enforce
no redirects, no retries and the same socket timeout/body limits as the default transport.
The urllib timeout limits blocking socket operations, not total request wall time.
"""
from datetime import datetime, timedelta, timezone
import json
import math
import re
from urllib.parse import quote, urlencode
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from .wallet_evidence import analyze_wallets
from .io_helpers import json_bytes

MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_RECORDS = 1000
MAX_PAGES = 20
_PROVIDER_ROOT = "https://pro-api.coingecko.com/api/v3/onchain/networks"
_TOKEN = re.compile(r"[A-Za-z0-9_.:-]{1,256}\Z")
_TRADE_FIELDS = {
    "tx_hash", "tx_from_address", "block_timestamp", "block_number", "kind",
    "volume_in_usd", "from_token_address", "to_token_address", "from_token_amount",
    "to_token_amount", "price_from_in_currency_token", "price_to_in_currency_token",
    "price_from_in_usd", "price_to_in_usd", "is_anomalous",
}


class CollectionError(ValueError):
    """Sanitized failure. Attempts do not prove remote success or billing."""

    def __init__(self, code, *, request_count=0):
        self.code = code
        self.request_count = request_count
        self.remote_outcome = "unknown" if request_count else "not_dispatched"
        super().__init__(f"History collection failed ({code}); attempts={request_count}; "
                         f"remote outcome={self.remote_outcome}.")


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _urllib_transport(*, endpoint, headers, timeout_seconds, max_response_bytes):
    opener = build_opener(ProxyHandler({}), _NoRedirect())
    request = Request(endpoint, headers=headers, method="GET")
    with opener.open(request, timeout=timeout_seconds) as response:
        if response.status != 200 or response.geturl() != endpoint:
            raise ValueError("unexpected HTTP response")
        body = response.read(max_response_bytes + 1)
        if len(body) > max_response_bytes:
            raise ValueError("response exceeds limit")
        return body


def _utc(value):
    if type(value) is not str or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z", value):
        raise ValueError("UTC timestamp required")
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    if parsed.utcoffset() != timedelta(0) or "T" not in value:
        raise ValueError("UTC timestamp required")
    return parsed


def _bounded_text(value, *, maximum=256):
    if (type(value) is not str or not value.strip() or value != value.strip() or len(value) > maximum
            or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise ValueError("invalid text")
    return value


def _integer(value, lo, hi):
    if type(value) is not int or not lo <= value <= hi:
        raise ValueError("invalid bounded integer")
    return value


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _nonfinite(_):
    raise ValueError("nonfinite JSON number")


def _float(value):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("nonfinite JSON number")
    return result


def _no_secret(value, secret):
    """Inspect decoded values and object keys before JSON escaping can hide them."""
    pending = [value]
    nodes = 0
    while pending:
        item = pending.pop()
        nodes += 1
        if nodes > 100000:
            raise ValueError("response resource limit")
        if type(item) is str:
            if secret in item:
                raise ValueError("credential appeared in nonsecret data")
        elif type(item) is dict:
            pending.extend(item.keys())
            pending.extend(item.values())
        elif type(item) is list:
            pending.extend(item)


def _source_url(network, address):
    return f"{_PROVIDER_ROOT}/{network}/pools/{quote(address, safe='')}/trades/range"


def _observation_pool(network, pool):
    return {**pool, "source_url": _source_url(network, pool["address"]),
            "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "trades": {"data": []}}


def _page(raw, per_page, api_key):
    if type(raw) is not bytes or len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError("invalid response bytes")
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                       parse_constant=_nonfinite, parse_float=_float)
    _no_secret(value, api_key)
    if (type(value) is not dict or "error" in value or "errors" in value
            or type(value.get("data")) is not list or len(value["data"]) > 300):
        raise ValueError("invalid response object")
    # Providers may return more than requested; the caller's record cap still holds.
    meta = value.get("meta")
    if type(meta) is not dict or "next_cursor" not in meta:
        raise ValueError("pagination metadata required")
    cursor = meta["next_cursor"]
    if cursor is not None:
        _bounded_text(cursor, maximum=1024)
    return value["data"], cursor


def _trade(raw):
    if (type(raw) is not dict or type(raw.get("attributes")) is not dict
            or raw.get("type") not in {"trade", "trades"}):
        raise ValueError("invalid trade")
    identifier = _bounded_text(raw.get("id"), maximum=512)
    attrs = raw["attributes"]
    cleaned = {}
    for key in _TRADE_FIELDS:
        if key not in attrs:
            continue
        value = attrs[key]
        if value is None:
            cleaned[key] = None
        elif key == "is_anomalous" and type(value) is bool:
            cleaned[key] = value
        elif type(value) is int and abs(value) <= 10 ** 18:
            cleaned[key] = value
        elif type(value) is float and math.isfinite(value):
            cleaned[key] = value
        else:
            cleaned[key] = _bounded_text(value, maximum=512)
    timestamp = _utc(cleaned.get("block_timestamp"))
    _bounded_text(cleaned.get("tx_hash"), maximum=256)
    if "is_anomalous" in cleaned and type(cleaned["is_anomalous"]) is not bool:
        raise ValueError("invalid anomaly flag")
    return {"id": identifier, "type": "trade", "attributes": cleaned}, timestamp


def collect_pool_trades(*, network, pools, captured_at, api_key, max_pages=5,
                        max_records=MAX_RECORDS, timeout_seconds=20, transport=None):
    """Return ``(snapshot, receipt)`` for one network's explicit pools.

    ``max_pages`` and ``max_records`` are total request/unique-record budgets
    across pools, not per-pool limits. Cutoff bounds are frozen for all requests.
    An exhausted provider cursor is reported as provider-declared exhaustion;
    chain completeness is deliberately never asserted.
    """
    try:
        if network not in {"near", "solana"} or type(network) is not str:
            raise ValueError("unsupported network")
        captured = _utc(captured_at)
        if captured.microsecond or captured > datetime.now(timezone.utc):
            raise ValueError("whole-second nonfuture cutoff required")
        _bounded_text(api_key, maximum=512)
        if any(ord(c) > 126 for c in api_key):
            raise ValueError("invalid header key")
        _integer(max_pages, 1, MAX_PAGES)
        _integer(max_records, 1, MAX_RECORDS)
        _integer(timeout_seconds, 1, 30)
        if type(pools) is not list or not 1 <= len(pools) <= 4:
            raise ValueError("one to four pools required")
        clean_pools = []
        addresses = set()
        required = {"address", "name", "base_token_address", "quote_token_address"}
        for pool in pools:
            if type(pool) is not dict or set(pool) != required:
                raise ValueError("explicit pool metadata required")
            clean = {key: _bounded_text(pool[key], maximum=160 if key == "name" else 256) for key in required}
            for key in required - {"name"}:
                if not _TOKEN.fullmatch(clean[key]):
                    raise ValueError("invalid address")
            if clean["address"] in addresses or clean["base_token_address"] == clean["quote_token_address"]:
                raise ValueError("duplicate pool or tokens")
            addresses.add(clean["address"])
            clean_pools.append(clean)
        _no_secret({"pools": clean_pools, "network": network, "captured_at": captured_at}, api_key)
        start = captured - timedelta(days=30)
        if start.timestamp() < 0:
            raise ValueError("unsupported historical cutoff")
        if transport is not None and not callable(transport):
            raise ValueError("invalid transport")
        # Share the analyzer's complete metadata contract before a paid request.
        analyze_wallets({"schema_version": "wallet-observations.v1", "network": network,
                         "target_days": 30, "captured_at": captured_at,
                         "pools": [_observation_pool(network, pool) for pool in clean_pools]})
    except (ValueError, TypeError, OverflowError):
        raise CollectionError("invalid_request") from None

    fetch = transport or _urllib_transport
    window_from, window_to = int(start.timestamp()), int(captured.timestamp())
    receipt = {"schema_version": "history-collection-receipt.v1", "provider": "coingecko-pro",
               "network": network, "target_days": 30, "captured_at": captured_at,
               "requested_window": {"from": window_from, "to": window_to, "inclusive": True},
               "request_count": 0, "max_pages": max_pages, "max_records": max_records,
               "coverage": "unverified", "account_access": "not_independently_verified", "pools": []}
    snapshot = {"schema_version": "wallet-observations.v1", "network": network,
                "target_days": 30, "captured_at": captured_at, "pools": []}
    remaining = max_records
    try:
        for pool in clean_pools:
            endpoint = _source_url(network, pool["address"])
            status = {"address": pool["address"], "source_url": endpoint,
                      "pagination_status": "not_started", "coverage": "incomplete",
                      "request_count": 0, "records": 0, "duplicates_removed": 0, "out_of_window": 0}
            receipt["pools"].append(status)
            result_pool = _observation_pool(network, pool)
            snapshot["pools"].append(result_pool)
            seen_ids, seen_cursors = {}, set()
            cursor = None
            while True:
                if remaining == 0:
                    status["pagination_status"] = "record_limit"
                    break
                if receipt["request_count"] >= max_pages:
                    status["pagination_status"] = "page_limit"
                    break
                per_page = min(300, remaining)
                query = {"from": window_from, "to": window_to, "per_page": per_page}
                if cursor is not None:
                    query["cursor"] = cursor
                request_url = endpoint + "?" + urlencode(query)
                _no_secret(request_url, api_key)
                receipt["request_count"] += 1
                status["request_count"] += 1
                try:
                    raw = fetch(endpoint=request_url,
                                headers={"x-cg-pro-api-key": api_key, "Accept": "application/json"},
                                timeout_seconds=timeout_seconds, max_response_bytes=MAX_RESPONSE_BYTES)
                except Exception:
                    raise CollectionError("transport_failed", request_count=receipt["request_count"]) from None
                result_pool["retrieved_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
                data, next_cursor = _page(raw, per_page, api_key)
                overflow = False
                for item in data:
                    cleaned, timestamp = _trade(item)
                    _no_secret(cleaned, api_key)
                    identifier = cleaned["id"]
                    if identifier in seen_ids:
                        if seen_ids[identifier] != cleaned:
                            raise ValueError("conflicting duplicate trade")
                        status["duplicates_removed"] += 1
                        continue
                    seen_ids[identifier] = cleaned
                    if not start <= timestamp <= captured:
                        status["out_of_window"] += 1
                        continue
                    if remaining == 0:
                        overflow = True
                        continue
                    result_pool["trades"]["data"].append(cleaned)
                    status["records"] += 1
                    remaining -= 1
                if next_cursor is None and not overflow:
                    status["pagination_status"] = "exhausted"
                    status["coverage"] = "unverified"
                    break
                if next_cursor is not None:
                    if next_cursor in seen_cursors:
                        raise ValueError("cursor loop")
                    seen_cursors.add(next_cursor)
                cursor = next_cursor
                if overflow:
                    status["pagination_status"] = "record_limit"
                    break
        if any(p["coverage"] == "incomplete" for p in receipt["pools"]):
            receipt["coverage"] = "incomplete"
        # A successful snapshot must also be consumable by the downstream
        # analyzer; provider-only fields can otherwise violate its numeric/text
        # resource limits even when pagination and JSON were syntactically valid.
        analyze_wallets(snapshot)
        if len(json_bytes(snapshot)) > MAX_RESPONSE_BYTES:
            raise ValueError("serialized snapshot exceeds downstream input limit")
        _no_secret(snapshot, api_key)
        _no_secret(receipt, api_key)
        return snapshot, receipt
    except CollectionError:
        raise
    except Exception:
        raise CollectionError("invalid_response", request_count=receipt["request_count"]) from None
