"""Financial invariants use literal, hand-checked settlement amounts."""

from dataclasses import FrozenInstanceError

import pytest

from decision_lab.finance import Balance, ConstantProductMarket, Fill, Ledger


def market(*, fee_bps=30, lp_shares=None):
    ledger = Ledger({
        "pool": Balance(10_000, 20_000),
        "alice": Balance(5_000, 5_000),
        "project": Balance(10_000, 20_000),
        "empty": Balance(),
    })
    return ledger, ConstantProductMarket(
        ledger, fee_bps=fee_bps,
        lp_shares={"project": 1_000} if lp_shares is None else lp_shares,
    )


@pytest.mark.parametrize("bad", [-1, True, 1.5, "1", None])
@pytest.mark.parametrize("field", ["cash_cents", "token_units"])
def test_balance_rejects_noninteger_or_negative_funds(field, bad):
    with pytest.raises(ValueError):
        Balance(**{field: bad})


def test_balance_and_fill_are_immutable_and_validate_amounts():
    balance = Balance(1, 2)
    with pytest.raises(FrozenInstanceError):
        balance.cash_cents = 10
    fill = Fill(1, 2, 0, 0)
    with pytest.raises(FrozenInstanceError):
        fill.token_units = 10
    for field in ("cash_cents", "token_units", "fee_cash_cents", "fee_token_units"):
        with pytest.raises(ValueError):
            Fill(**{field: True})


def test_ledger_copies_initial_accounts_and_exposes_safe_balances():
    initial = {"a": Balance(10, 20), "b": Balance()}
    ledger = Ledger(initial)
    initial["a"] = Balance(999, 999)
    initial["new"] = Balance(999, 999)
    assert ledger.totals() == (10, 20)
    with pytest.raises(TypeError):
        ledger.accounts["a"] = Balance(999, 999)
    assert ledger.transfer("move", "a", "b", 4, 5) is True
    assert ledger.accounts["a"] == Balance(6, 15)
    assert ledger.accounts["b"] == Balance(4, 5)
    assert ledger.totals() == (10, 20)
    assert len(ledger.journal) == 1


def test_transfer_replay_is_idempotent_and_changed_payload_rejected():
    ledger = Ledger({"a": Balance(10, 20), "b": Balance()})
    ledger.transfer("move", "a", "b", 10, 20)
    assert ledger.transfer("move", "a", "b", 10, 20) is False
    with pytest.raises(ValueError):
        ledger.transfer("move", "b", "a", 10, 20)
    assert ledger.accounts["a"] == Balance()
    assert ledger.accounts["b"] == Balance(10, 20)
    assert len(ledger.journal) == 1


@pytest.mark.parametrize("sender,recipient,cash,tokens", [
    ("missing", "b", 1, 0), ("a", "missing", 1, 0),
    ("a", "b", 11, 0), ("a", "b", 0, 21),
    ("a", "b", -1, 0), ("a", "b", 0, -1),
    ("a", "b", True, 0), ("a", "b", 0, 1.0),
])
def test_failed_transfer_does_not_mutate_or_consume_id(sender, recipient, cash, tokens):
    ledger = Ledger({"a": Balance(10, 20), "b": Balance()})
    with pytest.raises(ValueError):
        ledger.transfer("retry", sender, recipient, cash, tokens)
    assert dict(ledger.accounts) == {"a": Balance(10, 20), "b": Balance()}
    assert len(ledger.journal) == 0
    assert ledger.transfer("retry", "a", "b", 1, 2) is True


def test_self_transfer_neither_creates_nor_destroys_funds():
    ledger = Ledger({"a": Balance(10, 20)})
    ledger.transfer("self", "a", "a", 10, 20)
    assert ledger.accounts["a"] == Balance(10, 20)
    with pytest.raises(ValueError):
        ledger.transfer("overdraw", "a", "a", 11)


def test_buy_uses_gross_reserve_input_and_retains_floor_fee():
    ledger, amm = market()
    before = ledger.totals()
    fill = amm.buy("alice", 1_000, "buy")
    assert fill == Fill(1_000, 1_813, 3, 0)
    assert ledger.accounts["pool"] == Balance(11_000, 18_187)
    assert ledger.accounts["alice"] == Balance(4_000, 6_813)
    assert ledger.totals() == before
    assert 11_000 * 18_187 >= 10_000 * 20_000


def test_sell_uses_gross_reserve_input_and_retains_floor_fee():
    ledger, amm = market()
    before = ledger.totals()
    assert amm.sell("alice", 1_000, "sell") == Fill(474, 1_000, 0, 3)
    assert ledger.accounts["pool"] == Balance(9_526, 21_000)
    assert ledger.accounts["alice"] == Balance(5_474, 4_000)
    assert ledger.totals() == before


@pytest.mark.parametrize("operation,amount", [("buy", 1_000), ("sell", 1_000)])
def test_trade_replay_returns_original_fill_after_reserves_change(operation, amount):
    ledger, amm = market()
    trade = getattr(amm, operation)
    original = trade("alice", amount, "first")
    amm.buy("project", 500, "later")
    snapshot, journal = dict(ledger.accounts), ledger.journal
    assert trade("alice", amount, "first") == original
    assert dict(ledger.accounts) == snapshot
    assert ledger.journal == journal
    with pytest.raises(ValueError):
        trade("alice", amount + 1, "first")
    with pytest.raises(ValueError):
        getattr(amm, "sell" if operation == "buy" else "buy")("alice", amount, "first")
    assert dict(ledger.accounts) == snapshot


@pytest.mark.parametrize("operation,kwargs", [
    ("buy", {"min_tokens": 1_814}), ("sell", {"min_cash_cents": 475}),
])
def test_minimum_output_failure_is_atomic_and_retryable(operation, kwargs):
    ledger, amm = market()
    snapshot = dict(ledger.accounts)
    with pytest.raises(ValueError):
        getattr(amm, operation)("alice", 1_000, "slippage", **kwargs)
    assert dict(ledger.accounts) == snapshot
    assert not ledger.journal
    getattr(amm, operation)("alice", 1_000, "slippage")


@pytest.mark.parametrize("operation", ["buy", "sell"])
@pytest.mark.parametrize("bad", [0, -1, True, 1.0, 50_000])
def test_invalid_or_unfunded_trade_is_atomic(operation, bad):
    ledger, amm = market()
    snapshot = dict(ledger.accounts)
    with pytest.raises(ValueError):
        getattr(amm, operation)("alice", bad, "bad")
    assert dict(ledger.accounts) == snapshot
    assert not ledger.journal


def test_dust_trades_follow_floor_math_without_minting_assets():
    ledger, amm = market()
    before = ledger.totals()
    assert amm.buy("alice", 1, "dust-buy") == Fill(1, 0, 1, 0)
    assert amm.sell("alice", 1, "dust-sell") == Fill(0, 1, 0, 1)
    assert ledger.accounts["pool"] == Balance(10_001, 20_001)
    assert ledger.totals() == before


def test_zero_fee_math_remains_exact_for_integers_above_float_precision():
    ledger = Ledger({"pool": Balance(10**30, 2 * 10**30), "alice": Balance(10**30)})
    amm = ConstantProductMarket(ledger, fee_bps=0)
    assert amm.buy("alice", 10**30, "large") == Fill(10**30, 10**30, 0, 0)


@pytest.mark.parametrize("fee", [-1, 10_000, True, 3.0])
def test_market_rejects_invalid_fees(fee):
    with pytest.raises(ValueError):
        market(fee_bps=fee)


@pytest.mark.parametrize("reserves", [Balance(), Balance(1, 0), Balance(0, 1)])
def test_market_requires_positive_reserves(reserves):
    with pytest.raises(ValueError):
        ConstantProductMarket(Ledger({"pool": reserves}))


def test_market_ids_conflict_with_ledger_transfers():
    ledger, amm = market()
    ledger.transfer("shared", "alice", "project", 1)
    snapshot = dict(ledger.accounts)
    with pytest.raises(ValueError):
        amm.buy("alice", 1_000, "shared")
    amm.buy("alice", 1_000, "market")
    with pytest.raises(ValueError):
        ledger.transfer("market", "alice", "project", 1)
    assert ledger.accounts["project"] == snapshot["project"]


def test_lp_deposit_and_locked_withdrawal_preserve_assets_and_share_ownership():
    ledger, amm = market()
    totals = ledger.totals()
    assert amm.add_liquidity("alice", 1_000, 2_000, "add") == 100
    assert amm.lp_shares == {"project": 1_000, "alice": 100}
    assert amm.total_lp_shares == 1_100
    assert ledger.accounts["pool"] == Balance(11_000, 22_000)
    snapshot = dict(ledger.accounts)
    with pytest.raises(ValueError):
        amm.remove_liquidity("alice", 100, "remove", now=9, unlock_at=10)
    assert dict(ledger.accounts) == snapshot
    assert amm.lp_shares["alice"] == 100
    assert amm.remove_liquidity("alice", 100, "remove", now=10, unlock_at=10) == Fill(1_000, 2_000)
    assert ledger.accounts["pool"] == Balance(10_000, 20_000)
    assert amm.total_lp_shares == 1_000
    assert amm.lp_shares.get("alice", 0) == 0
    assert ledger.totals() == totals


def test_lp_replays_do_not_duplicate_share_mint_or_burn():
    ledger, amm = market()
    assert amm.add_liquidity("alice", 1_000, 2_000, "add") == 100
    assert amm.add_liquidity("alice", 1_000, 2_000, "add") == 100
    assert amm.total_lp_shares == 1_100
    with pytest.raises(ValueError):
        amm.add_liquidity("alice", 2_000, 4_000, "add")
    fill = amm.remove_liquidity("alice", 100, "remove")
    snapshot = dict(ledger.accounts)
    assert amm.remove_liquidity("alice", 100, "remove") == fill
    assert dict(ledger.accounts) == snapshot
    assert amm.total_lp_shares == 1_000
    with pytest.raises(ValueError):
        amm.remove_liquidity("alice", 99, "remove")


@pytest.mark.parametrize("owner,cash,tokens", [
    ("alice", 1_000, 1_999), ("alice", 0, 0),
    ("alice", True, 2), ("alice", 1, 2.0),
    ("empty", 1_000, 2_000), ("missing", 1_000, 2_000),
])
def test_invalid_lp_deposit_is_atomic(owner, cash, tokens):
    ledger, amm = market()
    snapshot = dict(ledger.accounts)
    with pytest.raises(ValueError):
        amm.add_liquidity(owner, cash, tokens, "bad-add")
    assert dict(ledger.accounts) == snapshot
    assert amm.total_lp_shares == 1_000
    assert not ledger.journal


@pytest.mark.parametrize("owner,shares", [("alice", 1), ("project", 1_001),
    ("project", 0), ("project", -1), ("project", True), ("project", 1.0)])
def test_invalid_lp_withdrawal_cannot_burn_another_owners_shares(owner, shares):
    ledger, amm = market()
    snapshot = dict(ledger.accounts)
    with pytest.raises(ValueError):
        amm.remove_liquidity(owner, shares, "bad-remove")
    assert dict(ledger.accounts) == snapshot
    assert amm.total_lp_shares == 1_000
    assert not ledger.journal


def test_lp_share_configuration_is_copied_and_validated():
    shares = {"project": 1_000}
    _, amm = market(lp_shares=shares)
    shares["project"] = 99_999
    assert amm.total_lp_shares == 1_000
    with pytest.raises(TypeError):
        amm.lp_shares["project"] = 10
    for invalid in ({}, {"missing": 1}, {"project": True}, {"project": -1}):
        with pytest.raises(ValueError):
            market(lp_shares=invalid)


def test_lp_share_dust_deposit_is_rejected_and_final_owner_receives_remainders():
    ledger, amm = market(lp_shares={"project": 3})
    snapshot = dict(ledger.accounts)
    with pytest.raises(ValueError):
        amm.add_liquidity("alice", 1, 2, "dust-add")
    assert dict(ledger.accounts) == snapshot
    assert amm.remove_liquidity("project", 1, "first") == Fill(3_333, 6_666)
    assert amm.remove_liquidity("project", 2, "last") == Fill(6_667, 13_334)
    assert ledger.accounts["pool"] == Balance()
    assert amm.total_lp_shares == 0
    assert ledger.totals() == (25_000, 45_000)


@pytest.mark.parametrize("operation", ["buy", "sell", "add", "remove"])
def test_pool_owner_cannot_self_settle_market_operations(operation):
    ledger, amm = market()
    snapshot = dict(ledger.accounts)
    with pytest.raises(ValueError):
        if operation == "add":
            amm.add_liquidity("pool", 1_000, 2_000, "self")
        elif operation == "remove":
            amm.remove_liquidity("pool", 1, "self")
        else:
            getattr(amm, operation)("pool", 100, "self")
    assert dict(ledger.accounts) == snapshot
