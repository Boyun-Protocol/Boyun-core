"""Offline transport tests: no API account, provider usage or billing implied."""
import json
from urllib.error import HTTPError

import pytest

from decision_lab.market_sources import CollectionError, collect_pool_trades

CAPTURED = "2026-10-22T00:00:00Z"
POOL = {"address": "pool.near", "name": "Example / USDC", "base_token_address": "meme.near", "quote_token_address": "usdc.near"}
KEY = "secret-not-in-artifacts"


def trade(n, timestamp="2026-10-21T12:00:00Z"):
    return {"id": str(n), "type": "trade", "attributes": {"tx_hash": f"tx{n}", "tx_from_address": f"wallet{n}.near", "block_timestamp": timestamp, "kind": "buy", "volume_in_usd": "12.5", "from_token_address": "usdc.near", "to_token_address": "meme.near", "from_token_amount": "12.5", "to_token_amount": "100"}}


class Transport:
    def __init__(self, pages):
        self.pages = iter(pages)
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        item = next(self.pages)
        if isinstance(item, Exception):
            raise item
        return item if isinstance(item, bytes) else json.dumps(item).encode()


def collect(transport, **kwargs):
    return collect_pool_trades(network="near", pools=[POOL], captured_at=CAPTURED, api_key=KEY, transport=transport, **kwargs)


def test_pagination_preserves_opaque_cursor_and_strips_credentials():
    transport = Transport([{"data": [trade(1)], "meta": {"next_cursor": "opaque + / ? &="}}, {"data": [trade(2)], "meta": {"next_cursor": None}}])
    snapshot, receipt = collect(transport)
    assert len(snapshot["pools"][0]["trades"]["data"]) == 2
    assert snapshot["schema_version"] == "wallet-observations.v1"
    assert snapshot["target_days"] == 30
    assert receipt["request_count"] == 2
    assert "cursor=opaque+%2B+%2F+%3F+%26%3D" in transport.calls[1]["endpoint"]
    assert "/trades/range?" in transport.calls[0]["endpoint"]
    from datetime import datetime, timezone
    from urllib.parse import parse_qs, urlsplit
    query = parse_qs(urlsplit(transport.calls[0]["endpoint"]).query)
    to = int(datetime(2026, 10, 22, tzinfo=timezone.utc).timestamp())
    assert query["to"] == [str(to)]
    assert query["from"] == [str(to - 30 * 86400)]
    assert transport.calls[0]["headers"]["x-cg-pro-api-key"] == KEY
    assert KEY not in json.dumps([snapshot, receipt])
    assert "opaque" not in json.dumps([snapshot, receipt])
    assert receipt["pools"][0]["coverage"] == "unverified"
    assert receipt["pools"][0]["pagination_status"] == "exhausted"


@pytest.mark.parametrize("patch", [{"network": "ethereum"}, {"captured_at": "2026-10-22"}, {"max_pages": 0}, {"max_pages": 21}, {"max_records": 1001}, {"timeout_seconds": 31}, {"api_key": ""}, {"api_key": "bad\r\nkey"}, {"pools": [{**POOL, "address": "https://evil.test/"}]}])
def test_invalid_input_never_dispatches(patch):
    transport = Transport([])
    args = dict(network="near", pools=[POOL], captured_at=CAPTURED, api_key=KEY, transport=transport)
    args.update(patch)
    with pytest.raises(CollectionError) as err:
        collect_pool_trades(**args)
    assert err.value.request_count == 0
    assert transport.calls == []
    assert KEY not in str(err.value)


def test_page_cap_is_explicitly_incomplete_and_no_retry():
    transport = Transport([{"data": [trade(1)], "meta": {"next_cursor": "next"}}])
    _, receipt = collect(transport, max_pages=1)
    assert receipt["pools"][0]["pagination_status"] == "page_limit"
    assert receipt["pools"][0]["coverage"] == "incomplete"
    assert len(transport.calls) == 1


def test_record_limit_never_exceeds_analyzer_budget():
    transport = Transport([{"data": [trade(1), trade(2)], "meta": {"next_cursor": "next"}}])
    snapshot, receipt = collect(transport, max_records=1)
    assert len(snapshot["pools"][0]["trades"]["data"]) == 1
    assert receipt["pools"][0]["pagination_status"] == "record_limit"
    assert len(transport.calls) == 1


def test_duplicate_trades_are_deduplicated():
    transport = Transport([{"data": [trade(1)], "meta": {"next_cursor": "next"}}, {"data": [trade(1), trade(2)], "meta": {"next_cursor": None}}])
    snapshot, receipt = collect(transport)
    assert len(snapshot["pools"][0]["trades"]["data"]) == 2
    assert receipt["pools"][0]["duplicates_removed"] == 1


@pytest.mark.parametrize("pages", [[{"data": [trade(1)], "meta": {"next_cursor": "repeat"}}, {"data": [trade(2)], "meta": {"next_cursor": "repeat"}}], [{"data": [], "meta": {"next_cursor": "x" * 1025}}]])
def test_cursor_loop_and_unbounded_cursor_are_safe_failures(pages):
    transport = Transport(pages)
    with pytest.raises(CollectionError) as err:
        collect(transport)
    assert err.value.code == "invalid_response"
    assert KEY not in str(err.value)


@pytest.mark.parametrize("response", [TimeoutError(KEY), HTTPError("https://example.test/" + KEY, 302, KEY, {}, None), b"{" + KEY.encode(), b"x" * (2 * 1024 * 1024 + 1), {"data": [], "error": KEY}, {"data": [], "meta": {"next_cursor": 5}}, {"data": [trade(1)] * 301}, b'{"data": [], "data": []}', b'{"data": [], "a": NaN}'], ids=["timeout", "redirect", "bad-json", "oversize", "error", "bad-cursor", "excess-records", "duplicate-key", "nonfinite"])
def test_transport_and_parse_errors_are_sanitized_without_retry(response):
    transport = Transport([response])
    with pytest.raises(CollectionError) as err:
        collect(transport)
    assert err.value.request_count == 1
    assert KEY not in str(err.value)
    assert len(transport.calls) == 1


def test_response_metadata_cannot_leak_key_or_arbitrary_fields():
    item = trade(1)
    item["attributes"]["unexpected_secret"] = KEY
    transport = Transport([{"data": [item], "meta": {"next_cursor": None, "key": KEY}}])
    with pytest.raises(CollectionError, match="invalid_response"):
        collect(transport)


def test_window_filters_future_and_old_trades_without_claiming_coverage():
    transport = Transport([{"data": [trade(1, "2026-09-22T00:00:00Z"), trade(2, "2026-09-21T23:59:59Z"), trade(3, "2026-10-22T00:00:01Z")], "meta": {"next_cursor": None}}])
    snapshot, receipt = collect(transport)
    assert [x["id"] for x in snapshot["pools"][0]["trades"]["data"]] == ["1"]
    assert receipt["pools"][0]["out_of_window"] == 2
    assert receipt["pools"][0]["coverage"] == "unverified"


def test_multiple_networks_or_pools_must_be_explicit_and_bounded():
    transport = Transport([])
    with pytest.raises(CollectionError):
        collect_pool_trades(network="near", pools=[POOL] * 2, captured_at=CAPTURED, api_key=KEY, transport=transport)
    assert not transport.calls


def test_anomalous_and_missing_wallet_flags_are_preserved_for_exclusion():
    item = trade(1)
    item["attributes"]["is_anomalous"] = True
    item["attributes"]["tx_from_address"] = None
    transport = Transport([{"data": [item], "meta": {"next_cursor": None}}])
    snapshot, _ = collect(transport)
    attrs = snapshot["pools"][0]["trades"]["data"][0]["attributes"]
    assert attrs["is_anomalous"] is True
    assert attrs["tx_from_address"] is None


def test_global_budgets_cover_all_pools_and_unvisited_pools_are_visible():
    other = {**POOL, "address": "other.near"}
    transport = Transport([{"data": [trade(1)], "meta": {"next_cursor": None}}])
    snapshot, receipt = collect_pool_trades(network="near", pools=[POOL, other], captured_at=CAPTURED, api_key=KEY, max_pages=1, transport=transport)
    assert len(snapshot["pools"]) == 2
    assert snapshot["pools"][1]["trades"]["data"] == []
    assert receipt["pools"][1]["pagination_status"] == "page_limit"
    assert receipt["coverage"] == "incomplete"


def test_conflicting_duplicate_trade_is_rejected():
    changed = trade(1)
    changed["attributes"]["volume_in_usd"] = "99"
    transport = Transport([{"data": [trade(1), changed], "meta": {"next_cursor": None}}])
    with pytest.raises(CollectionError, match="invalid_response"):
        collect(transport)


def test_actual_urllib_transport_disables_proxy_and_redirect_and_bounds_read(monkeypatch):
    from decision_lab import market_sources as module
    seen = {}
    class Reply:
        status = 200
        def __enter__(self):
            return self
        def __exit__(self, *_):
            pass
        def geturl(self):
            return seen["request"].full_url
        def read(self, limit):
            assert limit == 1025
            return b"{}"
    class Opener:
        def open(self, request, timeout):
            seen.update(request=request, timeout=timeout)
            return Reply()
    def opener(*handlers):
        seen["handlers"] = handlers
        return Opener()
    monkeypatch.setattr(module, "build_opener", opener)
    assert module._urllib_transport(endpoint="https://pro-api.coingecko.com/example", headers={"x-cg-pro-api-key": KEY}, timeout_seconds=20, max_response_bytes=1024) == b"{}"
    assert seen["handlers"][0].proxies == {}
    assert seen["handlers"][1].redirect_request(None, None, 302, "", {}, "https://pro-api.coingecko.com/other") is None
    assert seen["request"].method == "GET"
    assert KEY not in seen["request"].full_url
    assert seen["timeout"] == 20


def test_collected_snapshot_is_analyzer_compatible_without_retrieval_backdating():
    from decision_lab.wallet_evidence import analyze_wallets
    transport = Transport([{"data": [trade(1)], "meta": {"next_cursor": None}}])
    snapshot, _ = collect(transport)
    assert snapshot["pools"][0]["retrieved_at"] >= CAPTURED
    result = analyze_wallets(snapshot)
    assert result["summary"]["observed_wallets"] == 1
    assert result["summary"]["accepted_trades"] == 1
    assert result["coverage"]["complete_target_window"] is False


@pytest.mark.parametrize("secret", ['fake-quoted-"key', 'fake-backslash-\\key'])
def test_escaped_credentials_in_raw_response_strings_are_rejected(secret):
    item = trade(1)
    item["attributes"]["tx_hash"] = secret
    transport = Transport([{"data": [item], "meta": {"next_cursor": None}}])
    with pytest.raises(CollectionError, match="invalid_response") as error:
        collect_pool_trades(network="near", pools=[POOL], captured_at=CAPTURED, api_key=secret, transport=transport)
    assert error.value.request_count == 1
    assert secret not in str(error.value)


@pytest.mark.parametrize("secret", ['fake-quoted-"key', 'fake-backslash-\\key'])
def test_escaped_credentials_in_metadata_rejected_before_dispatch(secret):
    transport = Transport([])
    with pytest.raises(CollectionError, match="invalid_request"):
        collect_pool_trades(network="near", pools=[{**POOL, "name": secret}], captured_at=CAPTURED, api_key=secret, transport=transport)
    assert not transport.calls


@pytest.mark.parametrize("field,value", [("captured_at", "20261022T000000Z"), ("pools", [{**POOL, "name": " Name with padding "}])])
def test_analyzer_invalid_preflight_input_rejected_without_dispatch(field, value):
    transport = Transport([])
    args = dict(network="near", pools=[POOL], captured_at=CAPTURED, api_key=KEY, transport=transport)
    args[field] = value
    with pytest.raises(CollectionError, match="invalid_request"):
        collect_pool_trades(**args)
    assert not transport.calls


@pytest.mark.parametrize("attribute,value", [("block_number", 10**19), ("volume_in_usd", None)])
def test_analyzer_invalid_trade_cannot_be_returned_as_success(attribute, value):
    item = trade(1)
    item["attributes"][attribute] = value
    transport = Transport([{"data": [item], "meta": {"next_cursor": None}}])
    with pytest.raises(CollectionError, match="invalid_response"):
        collect(transport)


def test_secret_bearing_cursor_is_rejected_before_it_enters_next_request_url():
    secret = 'quoted-"cursor-key'
    transport = Transport([{"data": [trade(1)], "meta": {"next_cursor": secret}}])
    with pytest.raises(CollectionError, match="invalid_response"):
        collect_pool_trades(network="near", pools=[POOL], captured_at=CAPTURED, api_key=secret, transport=transport)
    assert len(transport.calls) == 1
    assert secret not in transport.calls[0]["endpoint"]


def test_aggregate_multibyte_snapshot_never_exceeds_cli_serialized_input_cap():
    pages = []
    for page in range(4):
        rows = []
        for index in range(page * 250, (page + 1) * 250):
            item = trade(index)
            item["attributes"]["price_from_in_usd"] = "界" * 300
            item["attributes"]["price_to_in_usd"] = "界" * 300
            rows.append(item)
        pages.append({"data": rows, "meta": {"next_cursor": str(page) if page < 3 else None}})
    transport = Transport(pages)
    with pytest.raises(CollectionError, match="invalid_response"):
        collect(transport)
    assert len(transport.calls) == 4


def test_retrieval_timestamp_is_recorded_after_provider_response(monkeypatch):
    from datetime import datetime, timezone
    from decision_lab import market_sources as module
    clock = [datetime(2026, 10, 23, tzinfo=timezone.utc)]
    class ControlledDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock[0]
    monkeypatch.setattr(module, "datetime", ControlledDateTime)
    def transport(**kwargs):
        clock[0] = datetime(2026, 10, 23, 0, 3, tzinfo=timezone.utc)
        return json.dumps({"data": [trade(1)], "meta": {"next_cursor": None}}).encode()
    snapshot, _ = collect(transport)
    assert snapshot["pools"][0]["retrieved_at"] == "2026-10-23T00:03:00Z"
