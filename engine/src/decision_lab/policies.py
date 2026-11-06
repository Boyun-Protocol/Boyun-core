"""Observable information and bounded rule proposals, separate from execution."""
from dataclasses import dataclass

from .actors import Actor, TRADING_CATEGORIES, _integer, _text
from .policy_bundles import PolicyRule


@dataclass(frozen=True)
class Message:
    id: str
    origin: str
    source: str
    published_at: int
    status: str
    public: bool = True
    asset: str = "project"

    def __post_init__(self):
        for name in ("id", "origin", "source", "asset"):
            _text(getattr(self, name), name)
        _integer(self.published_at, "published_at")
        if not isinstance(self.status, str) or self.status not in {"rumor", "confirmed", "contradicted"}:
            raise ValueError("unknown message status")
        if type(self.public) is not bool:
            raise ValueError("public must be a boolean")


@dataclass(frozen=True)
class Decision:
    kind: str
    amount: int = 0
    evidence_origins: tuple[str, ...] = ()
    reason: str = "no_eligible_signal"

    def __post_init__(self):
        if self.kind not in {"buy", "sell", "abstain"}:
            raise ValueError("unknown decision kind")
        _integer(self.amount, "amount")
        if (self.kind == "abstain" and self.amount != 0) or (self.kind != "abstain" and self.amount == 0):
            raise ValueError("action amount must be positive; abstention amount must be zero")


def _visible_latest(actor, messages, now):
    """Baseline has no message expiry; visibility starts at publication.

    Claim identity includes its asset. At a shared timestamp a contradiction
    wins over confirmation/rumor for that asset and origin, avoiding entry on
    an already contradicted claim without discarding another asset's evidence.
    """
    _integer(now, "now")
    if not isinstance(actor, Actor):
        raise ValueError("actor must be an Actor")
    priority = {"rumor": 0, "confirmed": 1, "contradicted": 2}
    latest = {}
    for message in messages:
        if not isinstance(message, Message):
            raise ValueError("messages must contain Message values")
        if not message.public or message.source not in actor.subscriptions or message.published_at > now:
            continue
        key = (message.asset, message.origin)
        previous = latest.get(key)
        rank = (message.published_at, priority[message.status], message.id)
        if previous is None or rank > (previous.published_at, priority[previous.status], previous.id):
            latest[key] = message
    return sorted(latest.values(), key=lambda message: (message.published_at, message.id, message.asset, message.origin))


def select_messages(actor, messages, now, seen_messages, rng):
    """Choose finite unique asset-origin exposure, retaining status updates.

    `seen_messages` contains delivered message IDs, not claim origins. Select
    latest visible status before removing delivered IDs so old confirmations
    cannot resurface after their newer contradiction has already been seen.
    The caller records delivery; this function does not mutate its sets.
    """
    eligible = [message for message in _visible_latest(actor, messages, now) if message.id not in seen_messages]
    count = min(actor.attention_capacity, len(eligible))
    return sorted(rng.sample(eligible, count), key=lambda message: (message.published_at, message.id, message.asset, message.origin))


def decide(actor, messages, cash_cents, token_units, spent_cents, seen_claims, now, policy=None, *, fallback="baseline"):
    """Propose at most one bounded action; execution belongs to the ledger.

    Cautious rules enter on confirmation; momentum also permits rumors.
    Entry size is the recipe fraction (baseline 10%) of *current* cash, capped
    by remaining cumulative acquisition budget. Contradiction of an observed
    origin proposes selling all currently held tokens. No price, hidden feed,
    expiry, calibrated threshold, or terminal forced liquidation is implied.
    Explicit compiled rules can narrow signal/exit behavior and sizing while
    actor capabilities, attention, subscriptions, and budget remain binding.
    """
    for name, value in (("cash_cents", cash_cents), ("token_units", token_units), ("spent_cents", spent_cents)):
        _integer(value, name)
    if not isinstance(fallback, str) or fallback not in {"baseline", "abstain"}:
        raise ValueError("fallback must be baseline or abstain")
    if policy is not None and not isinstance(policy, PolicyRule):
        raise ValueError("policy must be a compiled PolicyRule")
    visible = [message for message in _visible_latest(actor, messages, now) if message.asset == "project"]
    if policy is not None and policy.template_id != actor.template_id:
        raise ValueError("policy template must match actor template")
    if policy is None and fallback == "abstain":
        return Decision("abstain", reason="declared_abstain_fallback")
    if policy is not None and actor.category not in TRADING_CATEGORIES:
        return Decision("abstain", reason="passive_or_scheduled_role")
    if actor.strategy not in {"cautious", "momentum"} or actor.attention_capacity == 0:
        return Decision("abstain", reason="passive_or_scheduled_role")
    contradictions = [message for message in visible if message.status == "contradicted" and message.origin in seen_claims]
    exit_enabled = policy is None or policy.exit_on_contradiction
    if exit_enabled and contradictions and token_units and "sell" in actor.allowed_actions:
        return Decision("sell", token_units, tuple(message.origin for message in contradictions), "observed_claim_contradicted")
    eligible_statuses = {"confirmed", "rumor"} if actor.strategy == "momentum" else {"confirmed"}
    fraction_bps = actor.entry_fraction_bps
    if policy is not None:
        eligible_statuses = {"confirmed", "rumor"} if policy.entry_signal == "rumor_or_confirmed" else (
            {"confirmed"} if policy.entry_signal == "confirmed" else set())
        fraction_bps = min(fraction_bps, policy.entry_fraction_bps)
    fresh = [message for message in visible if message.status in eligible_statuses and message.origin not in seen_claims]
    if fresh and "buy" in actor.allowed_actions:
        amount = min(cash_cents, cash_cents * fraction_bps // 10000,
                     max(0, actor.position_limit_cents - spent_cents))
        if amount:
            message = fresh[-1]
            strategy_name = "explicit_policy" if policy is not None else actor.strategy
            return Decision("buy", amount, (message.origin,), f"{strategy_name}_{message.status}_entry")
    return Decision("abstain")
