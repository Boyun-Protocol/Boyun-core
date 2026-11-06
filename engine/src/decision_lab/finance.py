"""Integer-only settlement and a synthetic constant-product liquidity pool.

All assets live in the ledger, including retained trading fees. LP shares are
synthetic ownership units, not a model of any particular launch venue.
"""

from dataclasses import dataclass
from math import isqrt
from threading import RLock
from types import MappingProxyType
from typing import Mapping


def _integer(value: int, name: str, *, positive: bool = False) -> None:
    if type(value) is not int or value < (1 if positive else 0):
        raise ValueError(f"{name} must be a {'positive' if positive else 'nonnegative'} integer")


@dataclass(frozen=True, slots=True)
class Balance:
    cash_cents: int = 0
    token_units: int = 0

    def __post_init__(self) -> None:
        _integer(self.cash_cents, "cash_cents")
        _integer(self.token_units, "token_units")


@dataclass(frozen=True, slots=True)
class Fill:
    cash_cents: int = 0
    token_units: int = 0
    fee_cash_cents: int = 0
    fee_token_units: int = 0

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            _integer(getattr(self, name), name)


@dataclass(frozen=True, slots=True)
class Transfer:
    event_id: str
    sender: str
    recipient: str
    cash_cents: int
    token_units: int


_MISSING = object()


class Ledger:
    """Conserved balances with one idempotency namespace for all settlements."""

    def __init__(self, accounts: dict[str, Balance]):
        self._accounts: dict[str, Balance] = {}
        for owner, balance in accounts.items():
            if not isinstance(owner, str) or not owner or not isinstance(balance, Balance):
                raise ValueError("accounts require nonempty owner names and Balance values")
            self._accounts[owner] = Balance(balance.cash_cents, balance.token_units)
        self._events: dict[str, tuple[tuple, object]] = {}
        self._journal: list[Transfer] = []
        # Market settlement and LP share changes hold this same reentrant lock.
        self._lock = RLock()

    @property
    def accounts(self) -> Mapping[str, Balance]:
        return MappingProxyType(self._accounts)

    @property
    def journal(self) -> tuple[Transfer, ...]:
        with self._lock:
            return tuple(self._journal)

    def totals(self) -> tuple[int, int]:
        with self._lock:
            return (
                sum(balance.cash_cents for balance in self._accounts.values()),
                sum(balance.token_units for balance in self._accounts.values()),
            )

    def _cached(self, event_id: str, payload: tuple) -> object:
        if not isinstance(event_id, str) or not event_id:
            raise ValueError("event_id must be a nonempty string")
        previous = self._events.get(event_id)
        if previous is None:
            return _MISSING
        if previous[0] != payload:
            raise ValueError("event_id already used with a different payload")
        return previous[1]

    def _commit(self, event_id: str, payload: tuple, movements: tuple, result: object) -> object:
        """Preflight every leg, then publish balances, journal and event together.

        Caller holds _lock. Staging prevents a later failing leg from exposing a
        partially settled trade or consuming its event ID.
        """
        staged = self._accounts.copy()
        records = []
        for sender, recipient, cash, tokens in movements:
            _integer(cash, "cash_cents")
            _integer(tokens, "token_units")
            if sender not in staged or recipient not in staged:
                raise ValueError("unknown account")
            source = staged[sender]
            if source.cash_cents < cash or source.token_units < tokens:
                raise ValueError("insufficient funds")
            staged[sender] = Balance(source.cash_cents - cash, source.token_units - tokens)
            destination = staged[recipient]
            staged[recipient] = Balance(destination.cash_cents + cash, destination.token_units + tokens)
            records.append(Transfer(event_id, sender, recipient, cash, tokens))
        self._accounts.update(staged)
        self._journal.extend(records)
        self._events[event_id] = (payload, result)
        return result

    def transfer(self, event_id: str, sender: str, recipient: str,
                 cash_cents: int = 0, token_units: int = 0) -> bool:
        _integer(cash_cents, "cash_cents")
        _integer(token_units, "token_units")
        payload = ("transfer", sender, recipient, cash_cents, token_units)
        with self._lock:
            if self._cached(event_id, payload) is not _MISSING:
                return False
            self._commit(event_id, payload, ((sender, recipient, cash_cents, token_units),), True)
            return True


class ConstantProductMarket:
    """Fee-retaining AMM with exact floors and synthetic, ratio-correct LPs.

    Without an explicit allocation, initial shares are floor(sqrt(cash*tokens))
    and belong to pool_owner. Give shares to an external account explicitly if
    those initial reserves should be withdrawable by a project or LP.
    """

    def __init__(self, ledger: Ledger, pool_owner: str = "pool", fee_bps: int = 30,
                 lp_shares: dict[str, int] | None = None):
        _integer(fee_bps, "fee_bps")
        if fee_bps >= 10_000:
            raise ValueError("fee_bps must be below 10000")
        self.ledger = ledger
        self.pool_owner = pool_owner
        self.fee_bps = fee_bps
        with ledger._lock:
            reserves = self._reserves()
            shares = ({pool_owner: isqrt(reserves.cash_cents * reserves.token_units)}
                      if lp_shares is None else dict(lp_shares))
            for owner, amount in shares.items():
                if owner not in ledger.accounts:
                    raise ValueError("unknown LP owner")
                _integer(amount, "LP shares")
            if sum(shares.values()) <= 0:
                raise ValueError("initial LP supply must be positive")
            self._lp_shares = shares

    @property
    def lp_shares(self) -> Mapping[str, int]:
        return MappingProxyType(self._lp_shares)

    @property
    def total_lp_shares(self) -> int:
        return sum(self._lp_shares.values())

    def _reserves(self) -> Balance:
        reserves = self.ledger.accounts.get(self.pool_owner)
        if reserves is None or reserves.cash_cents <= 0 or reserves.token_units <= 0:
            raise ValueError("pool must have positive cash and token reserves")
        return reserves

    def _owner(self, owner: str) -> None:
        if owner not in self.ledger.accounts or owner == self.pool_owner:
            raise ValueError("market owner must be a known account outside the pool")

    def buy(self, owner: str, spend_cents: int, event_id: str, min_tokens: int = 0) -> Fill:
        return self._trade(owner, spend_cents, event_id, min_tokens, buying=True)

    def sell(self, owner: str, tokens: int, event_id: str, min_cash_cents: int = 0) -> Fill:
        return self._trade(owner, tokens, event_id, min_cash_cents, buying=False)

    def _trade(self, owner: str, amount: int, event_id: str, minimum: int, *, buying: bool) -> Fill:
        _integer(amount, "trade input", positive=True)
        _integer(minimum, "minimum output")
        payload = ("buy" if buying else "sell", self.pool_owner, self.fee_bps, owner, amount, minimum)
        with self.ledger._lock:
            cached = self.ledger._cached(event_id, payload)
            if cached is not _MISSING:
                return cached
            self._owner(owner)
            reserves = self._reserves()
            reserve_in, reserve_out = ((reserves.cash_cents, reserves.token_units) if buying
                                       else (reserves.token_units, reserves.cash_cents))
            effective = amount * (10_000 - self.fee_bps) // 10_000
            output = reserve_out * effective // (reserve_in + effective)
            if output < minimum:
                raise ValueError("minimum output not met")
            if buying:
                fill = Fill(amount, output, amount - effective, 0)
                movements = ((owner, self.pool_owner, amount, 0), (self.pool_owner, owner, 0, output))
            else:
                fill = Fill(output, amount, 0, amount - effective)
                movements = ((owner, self.pool_owner, 0, amount), (self.pool_owner, owner, output, 0))
            self.ledger._commit(event_id, payload, movements, fill)
            return fill

    def add_liquidity(self, owner: str, cash_cents: int, token_units: int, event_id: str) -> int:
        _integer(cash_cents, "cash_cents", positive=True)
        _integer(token_units, "token_units", positive=True)
        payload = ("add_liquidity", self.pool_owner, owner, cash_cents, token_units)
        with self.ledger._lock:
            cached = self.ledger._cached(event_id, payload)
            if cached is not _MISSING:
                return cached
            self._owner(owner)
            reserves = self._reserves()
            if cash_cents * reserves.token_units != token_units * reserves.cash_cents:
                raise ValueError("liquidity deposit must match the reserve ratio")
            minted = cash_cents * self.total_lp_shares // reserves.cash_cents
            if minted <= 0:
                raise ValueError("deposit is too small to mint a share")
            self.ledger._commit(event_id, payload, ((owner, self.pool_owner, cash_cents, token_units),), minted)
            self._lp_shares[owner] = self._lp_shares.get(owner, 0) + minted
            return minted

    def remove_liquidity(self, owner: str, shares: int, event_id: str,
                         now: int = 0, unlock_at: int = 0) -> Fill:
        _integer(shares, "shares", positive=True)
        _integer(now, "now")
        _integer(unlock_at, "unlock_at")
        payload = ("remove_liquidity", self.pool_owner, owner, shares, now, unlock_at)
        with self.ledger._lock:
            cached = self.ledger._cached(event_id, payload)
            if cached is not _MISSING:
                return cached
            self._owner(owner)
            if now < unlock_at:
                raise ValueError("liquidity is locked")
            if shares > self._lp_shares.get(owner, 0):
                raise ValueError("insufficient LP shares")
            reserves = self._reserves()
            total = self.total_lp_shares
            fill = Fill(reserves.cash_cents * shares // total, reserves.token_units * shares // total)
            self.ledger._commit(event_id, payload,
                                ((self.pool_owner, owner, fill.cash_cents, fill.token_units),), fill)
            self._lp_shares[owner] -= shares
            return fill
