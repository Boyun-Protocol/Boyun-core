"""Observed trade arithmetic and conservative, non-identifying cohort claims."""
from copy import deepcopy
from urllib.parse import quote

import pytest


def trade(event_id="event-1", wallet="alice.near", usd="100.00", direction="buy", **changes):
    attrs = {
        "tx_from_address": wallet, "tx_hash": "same-transaction", "block_timestamp": "2026-10-23T12:00:00Z",
        "volume_in_usd": usd, "is_anomalous": False, "kind": direction,
        "from_token_address": "wrap.near" if direction == "buy" else "meme.near",
        "to_token_address": "meme.near" if direction == "buy" else "wrap.near",
    }
    attrs.update(changes)
    return {"id": event_id, "type": "trade", "attributes": attrs}


def snapshot(rows=None, network="near"):
    address = "pool/123"
    return {
        "schema_version": "wallet-observations.v1", "network": network, "target_days": 30,
        "captured_at": "2026-10-24T00:00:00Z",
        "pools": [{"address": address, "name": "MEME / NEAR", "base_token_address": "meme.near",
                   "quote_token_address": "wrap.near", "retrieved_at": "2026-10-23T23:59:00Z",
                   "source_url": f"https://api.geckoterminal.com/api/v2/networks/{network}/pools/{quote(address, safe='')}/trades",
                   "trades": {"data": rows if rows is not None else [trade()]}}],
    }


def analyze(value):
    from decision_lab.wallet_evidence import analyze_wallets
    return analyze_wallets(value)


def test_observed_arithmetic_preserves_multifill_tx_and_labels_unknown_roles():
    value = snapshot([trade(usd="10.005"), trade("event-2", usd="20.00", direction="sell"),
                      trade("event-3", "bob.near", "10000")])
    before = deepcopy(value)
    result = analyze(value)
    assert value == before
    assert result["schema_version"] == "wallet-cohorts.v1"
    assert result["summary"] == {"raw_records": 3, "duplicate_records": 0, "accepted_trades": 3,
                                 "observed_wallets": 2, "observed_notional_cents": 1003001,
                                 "excluded": {"anomalous": 0, "missing_wallet": 0, "unsupported_direction": 0, "outside_window": 0}}
    alice = next(p for p in result["profiles"] if p["address"] == "alice.near")
    assert alice["buys"] == alice["sells"] == 1
    assert alice["total_notional_cents"] == 3001
    assert alice["median_notional_cents"] == 1501
    assert alice["activity"] == "both_directions"
    assert alice["both_directions_observed"] is True
    assert alice["sources"][0]["trade_count"] == 2
    assert alice["evidence"]["reference_count"] == 2
    assert len(alice["evidence"]["references"]) == 2
    assert "retail_or_institutional_identity" in alice["unknown_traits"]
    assert not {"capital", "strategy", "pnl", "wallet_age", "influence"} & alice.keys()
    assert result["source_metadata"]["verification"] == "provider_declared_unverified"


def test_direction_uses_token_addresses_even_if_kind_disagrees():
    value = snapshot([trade(kind="sell")])
    result = analyze(value)
    assert result["profiles"][0]["buys"] == 1
    assert result["profiles"][0]["sells"] == 0
    assert result["coverage"]["kind_direction_disagreements"] == 1


def test_exact_duplicate_removed_but_conflicting_id_rejected():
    row = trade()
    result = analyze(snapshot([row, deepcopy(row)]))
    assert result["summary"]["accepted_trades"] == 1
    assert result["summary"]["duplicate_records"] == 1
    conflict = deepcopy(row)
    conflict["attributes"]["volume_in_usd"] = "123"
    with pytest.raises(ValueError, match="conflicting"):
        analyze(snapshot([row, conflict]))


def test_short_provider_slice_never_claims_thirty_day_history_even_when_dates_span_it():
    rows = [trade(block_timestamp="2026-09-24T00:00:00Z"), trade("later")]
    result = analyze(snapshot(rows))
    assert result["coverage"]["status"] == "recent_provider_slice"
    assert result["coverage"]["complete_target_window"] is False
    assert result["coverage"]["history_attested"] is False
    assert result["coverage"]["pools"][0]["earliest_observed_at"] == "2026-09-24T00:00:00Z"
    assert result["target_window"]["start"] == "2026-09-24T00:00:00Z"
    assert result["target_window"]["requested_days"] == 30


def test_filters_are_explicit_and_no_sender_is_fabricated():
    value = snapshot([trade(), trade("anomaly", is_anomalous=True), trade("missing", wallet=None),
                      trade("unrelated", from_token_address="other.near"),
                      trade("old", block_timestamp="2026-09-01T00:00:00Z")])
    result = analyze(value)
    assert result["summary"]["excluded"] == {"anomalous": 1, "missing_wallet": 1,
                                              "unsupported_direction": 1, "outside_window": 1}
    assert result["summary"]["accepted_trades"] == 1


@pytest.mark.parametrize("usd,bucket", [("99.99", "small"), ("100", "small"), ("100.01", "medium"),
                                        ("9999.99", "medium"), ("10000", "large")])
def test_size_thresholds_are_explicit_analyst_choices_on_median_trade(usd, bucket):
    result = analyze(snapshot([trade(usd=usd)]))
    assert result["profiles"][0]["observed_size"] == bucket
    assert result["cohorts"][0]["size"] == bucket
    assert result["coverage"]["threshold_basis"] == "analyst_chosen_median_observed_trade_usd"


def test_pseudonyms_are_network_specific_and_order_independent():
    rows = [trade("b", usd="20"), trade("a", direction="sell")]
    first = analyze(snapshot(rows))
    second = analyze(snapshot(list(reversed(rows))))
    assert first == second
    assert first["profiles"][0]["profile_id"] != analyze(snapshot(rows, "solana"))["profiles"][0]["profile_id"]


def test_same_event_id_in_distinct_pools_is_not_deduplicated_and_source_splits_sum():
    value = snapshot()
    second = deepcopy(value["pools"][0])
    second["address"] = "other-pool"
    second["source_url"] = "https://api.geckoterminal.com/api/v2/networks/near/pools/other-pool/trades"
    value["pools"].append(second)
    result = analyze(value)
    profile = result["profiles"][0]
    assert result["summary"]["accepted_trades"] == 2
    assert len(profile["sources"]) == 2
    assert sum(row["notional_cents"] for row in profile["sources"]) == profile["total_notional_cents"]


def test_transaction_references_are_bounded_but_all_references_are_hashed():
    result = analyze(snapshot([trade(str(n), usd=str(n + 1)) for n in range(40)]))
    evidence = result["profiles"][0]["evidence"]
    assert evidence["reference_count"] == 40
    assert len(evidence["references"]) == 30
    assert len(evidence["all_references_sha256"]) == 64
    assert evidence["truncated"] is True


@pytest.mark.parametrize("usd", ["NaN", "Infinity", float("nan"), float("inf"), True, "-1", "0", "1000000000001", [], "1e999999"])
def test_invalid_usd_is_rejected(usd):
    with pytest.raises(ValueError):
        analyze(snapshot([trade(usd=usd)]))


@pytest.mark.parametrize("change", [
    {"block_timestamp": "2026-10-23T12:00:00"}, {"block_timestamp": "2026-10-24T00:00:01Z"},
    {"block_timestamp": "2026-10-23T23:59:01Z"}, {"is_anomalous": "false"},
    {"tx_from_address": "x" * 257}, {"tx_hash": ""}, {"from_token_address": []},
])
def test_invalid_rows_reject_instead_of_silently_misrepresenting(change):
    with pytest.raises(ValueError):
        analyze(snapshot([trade(**change)]))


@pytest.mark.parametrize("mutation", [
    lambda v: v.update(network="ethereum"), lambda v: v.update(target_days=True),
    lambda v: v.update(target_days=7), lambda v: v.update(captured_at="2026-10-24"),
    lambda v: v["pools"][0].update(source_url="https://api.geckoterminal.com/api/v2/networks/solana/pools/pool%2F123/trades"),
    lambda v: v["pools"][0].update(source_url="https://evil.test/trades"),
    lambda v: v["pools"][0].update(quote_token_address="meme.near"),
    lambda v: v.update(pools=v["pools"] * 5),
    lambda v: v["pools"][0].update(trades={"data": [trade(str(n)) for n in range(1001)]}),
    lambda v: v["pools"][0]["trades"]["data"][0].update(id="solana_wrongchain"),
    lambda v: v["pools"][0]["trades"]["data"][0].update(unknown=float("nan")),
])
def test_invalid_envelopes_and_resource_limits(mutation):
    value = snapshot()
    mutation(value)
    with pytest.raises(ValueError):
        analyze(value)


def test_empty_slice_is_valid_and_has_no_invented_profiles():
    result = analyze(snapshot([]))
    assert result["profiles"] == result["cohorts"] == []
    assert result["coverage"]["pools"][0]["earliest_observed_at"] is None
    assert result["summary"]["observed_wallets"] == 0


def test_coingecko_pro_source_is_canonical_and_never_attests_history_or_network():
    value = snapshot()
    value["pools"][0]["source_url"] = "https://pro-api.coingecko.com/api/v3/onchain/networks/near/pools/pool%2F123/trades"
    result = analyze(value)
    assert result["source_metadata"]["sources"][0]["provider"] == "CoinGecko Pro"
    assert result["source_metadata"]["network_reliability"] == "declared_not_chain_attested"
    assert result["coverage"]["history_attested"] is False
    value["pools"][0]["source_url"] += "?x_cg_pro_api_key=secret"
    with pytest.raises(ValueError):
        analyze(value)


@pytest.mark.parametrize("kind", [[], {}, True, "x" * 33])
def test_malformed_kind_is_rejected_with_value_error(kind):
    with pytest.raises(ValueError):
        analyze(snapshot([trade(kind=kind)]))


def test_resource_validation_precedes_aggregation_of_provider_unknown_fields():
    value = snapshot()
    value["pools"][0]["trades"]["data"][0]["attributes"]["unexpected"] = {"nested": "x" * 2049}
    with pytest.raises(ValueError, match="text too long"):
        analyze(value)


def test_pro_range_endpoint_accepted_without_claiming_provider_exhaustion_or_full_window():
    value = snapshot()
    value["pools"][0]["source_url"] = "https://pro-api.coingecko.com/api/v3/onchain/networks/near/pools/pool%2F123/trades/range"
    result = analyze(value)
    assert result["source_metadata"]["sources"][0]["provider"] == "CoinGecko Pro"
    assert result["coverage"]["complete_target_window"] is False
    value["pools"][0]["source_url"] = "https://api.geckoterminal.com/api/v2/networks/near/pools/pool%2F123/trades/range"
    with pytest.raises(ValueError):
        analyze(value)


def test_target_window_date_underflow_is_a_validation_error():
    value = snapshot([])
    value.update(captured_at="0001-01-01T00:00:00Z")
    value["pools"][0]["retrieved_at"] = value["captured_at"]
    with pytest.raises(ValueError, match="target window"):
        analyze(value)


def test_high_precision_provider_decimal_keeps_cent_rounding_exact():
    usd = "24.71159297342107337814570181028960416799728240581754489197768826258908"
    result = analyze(snapshot([trade(usd=usd)]))
    assert result["summary"]["observed_notional_cents"] == 2471
    boundary = "100.004" + "9" * 100
    result = analyze(snapshot([trade(usd=boundary)]))
    assert result["summary"]["observed_notional_cents"] == 10000
    assert result["profiles"][0]["observed_size"] == "small"


def test_decimal_string_limit_still_bounds_provider_numeric_resources():
    with pytest.raises(ValueError):
        analyze(snapshot([trade(usd="1." + "0" * 255)]))


def test_observed_profiles_explicitly_have_no_simulation_effect():
    assert analyze(snapshot())["simulation_effect"] == "none"


def test_retrieval_can_follow_frozen_range_cutoff_but_trade_cannot():
    value = snapshot()
    value["pools"][0]["retrieved_at"] = "2026-10-24T00:10:00Z"
    assert analyze(value)["summary"]["accepted_trades"] == 1
    value["pools"][0]["trades"]["data"][0]["attributes"]["block_timestamp"] = "2026-10-24T00:01:00Z"
    with pytest.raises(ValueError, match="timestamp"):
        analyze(value)


@pytest.mark.parametrize("field", ["tx_from_address", "tx_hash", "from_token_address"])
def test_surrogate_text_is_rejected_before_unicode_encoding(field):
    with pytest.raises(ValueError, match="invalid"):
        analyze(snapshot([trade(**{field: "bad\ud800text"})]))


def test_fractional_timestamps_sort_by_time_for_profile_bounds_and_earliest_references():
    result = analyze(snapshot([
        trade('whole', block_timestamp='2026-10-23T12:00:00Z'),
        trade('fraction', block_timestamp='2026-10-23T12:00:00.100000Z'),
    ]))
    profile = result['profiles'][0]
    assert profile['first_observed_at'] == '2026-10-23T12:00:00Z'
    assert profile['last_observed_at'] == '2026-10-23T12:00:00.100000Z'
    assert [r['event_id'] for r in profile['evidence']['references']] == ['whole', 'fraction']
