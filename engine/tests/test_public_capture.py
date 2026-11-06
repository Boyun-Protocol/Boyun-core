"""Public collection uses fixed, bounded GETs; these tests never use the network."""
from datetime import datetime, timezone
import json
from urllib.error import HTTPError

import pytest

from decision_lab.public_capture import PublicCaptureError, capture_public_pool, collect_public

POOL = {"address": "pool.near", "name": "Example / USDC", "base_token_address": "meme.near", "quote_token_address": "usdc.near"}
NOW = datetime(2026, 10, 24, 12, tzinfo=timezone.utc)


def trade(n=1, timestamp="2026-10-23T12:00:00Z"):
    return {"id": str(n), "type": "trade", "attributes": {"tx_hash": f"tx{n}", "tx_from_address": f"wallet{n}.near", "block_timestamp": timestamp, "kind": "buy", "volume_in_usd": "12.5", "from_token_address": "usdc.near", "to_token_address": "meme.near"}}


class Transport:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        result = next(self.responses)
        if isinstance(result, Exception):
            raise result
        return result if isinstance(result, bytes) else json.dumps(result).encode()


class Archive:
    def __init__(self):
        self.snapshots, self.failures = [], []

    def record_snapshot(self, snapshot):
        self.snapshots.append(snapshot)
        return {"inserted_trades": len(snapshot["pools"][0]["trades"]["data"])}

    def record_failure(self, network, address, at, code, pool_metadata=None):
        self.failures.append((network, address, at, code))


def capture(transport, **kwargs):
    return capture_public_pool(network="near", pool=POOL, transport=transport, now_fn=lambda: NOW, **kwargs)


def test_capture_fixed_public_endpoint_and_actual_response_cutoff_without_credentials():
    transport = Transport([{"data": [trade()]}])
    snapshot, receipt = capture(transport)
    assert transport.calls == [{"endpoint": "https://api.geckoterminal.com/api/v2/networks/near/pools/pool.near/trades", "headers": {"Accept": "application/json"}, "timeout_seconds": 10, "max_response_bytes": 2 * 1024 * 1024}]
    assert snapshot["captured_at"] == "2026-10-24T12:00:00Z"
    assert snapshot["pools"][0]["retrieved_at"] == snapshot["captured_at"]
    assert receipt["request_count"] == 1
    assert receipt["coverage"] == "recent_provider_slice"
    assert receipt["complete_history"] is False


def test_post_response_clock_is_used():
    clock = [NOW]
    def transport(**kwargs):
        clock[0] = datetime(2026, 10, 24, 12, 1, tzinfo=timezone.utc)
        return json.dumps({"data": [trade()]}).encode()
    snapshot, _ = capture_public_pool(network="near", pool=POOL, transport=transport, now_fn=lambda: clock[0])
    assert snapshot["captured_at"] == "2026-10-24T12:01:00Z"


@pytest.mark.parametrize("patch", [{"network": "ethereum"}, {"pool": {**POOL, "address": "https://evil.test"}}, {"pool": {**POOL, "name": " padded "}}, {"pool": {**POOL, "api_key": "x"}}, {"timeout_seconds": 0}, {"timeout_seconds": 31}])
def test_invalid_pool_metadata_fails_before_dispatch(patch):
    transport = Transport([])
    args = dict(network="near", pool=POOL, transport=transport)
    args.update(patch)
    with pytest.raises(PublicCaptureError) as error:
        capture_public_pool(**args)
    assert error.value.code == "invalid_request"
    assert error.value.request_count == 0
    assert not transport.calls


@pytest.mark.parametrize("response", [b'{"data":[],"data":[]}', b'{"data":[],"x":NaN}', b'{"data":[],"x":1e9999}', {"errors": [], "data": []}, {"data": [trade()] * 301}, b"x" * (2 * 1024 * 1024 + 1), {"data": [trade(timestamp="2026-10-24T12:00:01Z")]}, {"data": [{**trade(), "attributes": {**trade()["attributes"], "volume_in_usd": None}}]}, b'not json'], ids=["duplicate-key", "nan", "overflow", "provider-error", "rows", "bytes", "future", "bad-number", "bad-json"])
def test_invalid_response_is_sanitized_and_never_retried(response):
    transport = Transport([response])
    with pytest.raises(PublicCaptureError) as error:
        capture(transport)
    assert error.value.code == "invalid_response"
    assert error.value.request_count == 1
    assert len(transport.calls) == 1


def test_provider_only_fields_are_not_persisted_and_analyzer_accepts_snapshot():
    from decision_lab.wallet_evidence import analyze_wallets
    row = trade()
    row["attributes"]["unexpected"] = "not persisted"
    snapshot, _ = capture(Transport([{"data": [row], "meta": {"other": "not persisted"}}]))
    assert "not persisted" not in json.dumps(snapshot)
    assert analyze_wallets(snapshot)["summary"]["observed_wallets"] == 1


def test_network_opt_in_required_and_all_pools_preflight_before_any_request():
    transport = Transport([])
    with pytest.raises(PublicCaptureError, match="network_opt_in_required"):
        collect_public(config={"near": [POOL]}, archive=Archive(), transport=transport)
    with pytest.raises(PublicCaptureError, match="invalid_request"):
        collect_public(config={"near": [POOL], "solana": [{**POOL, "name": " bad "}]}, archive=Archive(), allow_network=True, transport=transport)
    assert not transport.calls


def test_partial_success_failure_receipt_and_spacing_are_explicit():
    transport = Transport([{"data": [trade()]}, TimeoutError("private provider exception")])
    archive, sleeps = Archive(), []
    receipt = collect_public(config={"near": [POOL, {**POOL, "address": "second.near"}]}, archive=archive, allow_network=True, transport=transport, sleep_fn=sleeps.append, now_fn=lambda: NOW)
    assert receipt["request_count"] == 2
    assert receipt["success_count"] == 1
    assert receipt["failure_count"] == 1
    assert receipt["complete_history"] is False
    assert receipt["automatic_retry"] is False
    assert sleeps == [5]
    assert len(archive.snapshots) == len(archive.failures) == 1
    assert archive.failures[0][3] == "transport_failed"
    assert "private provider exception" not in json.dumps(receipt)


def test_429_stops_remaining_pools_without_immediate_retry_and_bounds_retry_after():
    transport = Transport([HTTPError("https://private.test", 429, "secret", {"Retry-After": "999999999"}, None)])
    archive, sleeps = Archive(), []
    receipt = collect_public(config={"near": [POOL, {**POOL, "address": "second.near"}]}, archive=archive, allow_network=True, transport=transport, sleep_fn=sleeps.append, now_fn=lambda: NOW)
    assert len(transport.calls) == 1
    assert not sleeps
    assert receipt["rate_limited"] is True
    assert receipt["skipped_count"] == 1
    assert receipt["pools"][0]["error_code"] == "rate_limited"
    assert receipt["pools"][0]["retry_after_seconds"] == 3600
    assert len(archive.failures) == 1
    assert "secret" not in json.dumps(receipt)


def test_four_default_requests_and_eight_hard_maximum():
    near = [{**POOL, "address": f"pool{n}.near"} for n in range(4)]
    solana = [{**POOL, "address": f"pool{n}sol"} for n in range(4)]
    transport = Transport([{"data": []}] * 4)
    receipt = collect_public(config={"near": near, "solana": solana}, archive=Archive(), allow_network=True, transport=transport, sleep_fn=lambda _: None, now_fn=lambda: NOW)
    assert receipt["request_count"] == 4
    assert receipt["skipped_count"] == 4
    assert all(p["status"] == "request_limit" for p in receipt["pools"][4:])
    with pytest.raises(PublicCaptureError):
        collect_public(config={"near": near}, archive=Archive(), allow_network=True, max_requests=9, transport=Transport([]))


@pytest.mark.parametrize("error", [HTTPError("https://private.test", 302, "secret", {}, None), TimeoutError("secret")])
def test_transport_errors_are_sanitized(error):
    with pytest.raises(PublicCaptureError) as result:
        capture(Transport([error]))
    assert "secret" not in str(result.value)
    assert result.value.request_count == 1


def test_public_capture_never_reads_environment_credentials(monkeypatch):
    import os
    def forbidden(*args, **kwargs):
        raise AssertionError("environment credentials accessed")
    monkeypatch.setattr(os, "getenv", forbidden)
    monkeypatch.setattr(os.environ, "get", forbidden)
    assert capture(Transport([{"data": []}]))[0]["pools"][0]["trades"]["data"] == []
