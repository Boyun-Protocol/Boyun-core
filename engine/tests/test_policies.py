from decision_lab.actors import Actor
from decision_lab.policies import Message, decide, select_messages
from decision_lab.randomness import keyed_rng
import pytest


def trader(**changes):
    values = dict(id="r1", template_id="retail-01", category="retail", owner_id="r1", initial_cash_cents=25000,
                  allowed_actions=frozenset({"buy", "sell", "abstain"}), subscriptions=("news", "creator"),
                  position_limit_cents=10000, entry_fraction_bps=1000, attention_capacity=2,
                  strategy="cautious", provenance={"status": "assumed", "rationale": "test fixture"})
    values.update(changes)
    return Actor(**values)


def test_cautious_actor_ignores_rumor_but_proposes_bounded_confirmed_entry():
    actor = trader()
    rumor = Message("m1", "claim", "news", 0, "rumor")
    confirmed = Message("m2", "claim", "news", 1, "confirmed")
    assert decide(actor, [rumor], 25000, 0, 0, set(), 1).kind == "abstain"
    decision = decide(actor, [confirmed], 25000, 0, 0, set(), 1)
    assert (decision.kind, decision.amount) == ("buy", 2500)


def test_duplicate_claim_does_not_create_repeated_entries():
    m = Message("m2", "claim", "creator", 1, "confirmed")
    assert decide(trader(), [m], 25000, 0, 0, {"claim"}, 1).kind == "abstain"


def test_private_future_and_unsubscribed_messages_are_invisible():
    messages = [Message("p", "p", "creator", 0, "confirmed", public=False),
                Message("f", "f", "news", 10, "confirmed"),
                Message("x", "x", "other", 0, "confirmed")]
    assert select_messages(trader(), messages, 1, set(), keyed_rng(42, "feed")) == []


def test_finite_attention_and_origin_deduplication():
    messages = [Message(str(i), "same" if i < 4 else str(i), "creator", 0, "confirmed") for i in range(10)]
    selected = select_messages(trader(), messages, 1, set(), keyed_rng(42, "feed"))
    assert len(selected) == 2
    assert len({m.origin for m in selected}) == 2


def test_exit_is_a_proposal_only_and_respects_capabilities():
    m = Message("bad", "claim", "news", 0, "contradicted")
    assert decide(trader(), [m], 0, 100, 2500, {"claim"}, 1).kind == "sell"
    assert decide(trader(allowed_actions=frozenset({"abstain"})), [m], 0, 100, 2500, {"claim"}, 1).kind == "abstain"


def test_unseen_information_cannot_be_used_and_position_cap_bounds_orders():
    m = Message("m", "claim", "news", 10, "confirmed")
    assert decide(trader(), [m], 25000, 0, 0, set(), 1).kind == "abstain"
    m = Message("m", "claim", "news", 0, "confirmed")
    assert decide(trader(), [m], 25000, 1, 9900, set(), 1).amount == 100


def test_keyed_external_draws_do_not_depend_on_other_draw_consumption():
    expected = keyed_rng(42, "external", 3, "catalyst").random()
    for _ in range(12):
        keyed_rng(42, "action-order").random()
    assert keyed_rng(42, "external", 3, "catalyst").random() == expected
    assert keyed_rng(43, "external", 3, "catalyst").random() != expected


def test_seen_message_does_not_hide_new_contradiction_of_seen_origin():
    confirmed = Message("first", "claim", "news", 0, "confirmed")
    contradiction = Message("update", "claim", "news", 2, "contradicted")
    selected = select_messages(trader(), [confirmed, contradiction], 2, {"first"}, keyed_rng(42, "feed"))
    assert selected == [contradiction]
    assert decide(trader(), selected, 0, 10, 100, {"claim"}, 2).kind == "sell"


def test_latest_origin_status_prevents_entry_on_outdated_confirmation():
    messages = [Message("old", "claim", "news", 0, "confirmed"),
                Message("new", "claim", "news", 1, "contradicted")]
    assert select_messages(trader(), messages, 1, set(), keyed_rng(1, "feed")) == [messages[1]]
    assert decide(trader(), messages, 25000, 0, 0, set(), 1).kind == "abstain"


def test_delivered_contradiction_does_not_resurrect_old_confirmation():
    messages = [Message("old", "claim", "news", 0, "confirmed"),
                Message("new", "claim", "news", 1, "contradicted")]
    assert select_messages(trader(), messages, 1, {"new"}, keyed_rng(1, "feed")) == []


def test_competitor_promotion_uses_attention_but_cannot_trade_project():
    actor = trader(subscriptions=("competitor",), attention_capacity=1)
    message = Message("competitor", "competitor-launch", "competitor", 0, "confirmed", asset="competitor")
    assert select_messages(actor, [message], 0, set(), keyed_rng(1, "feed")) == [message]
    assert decide(actor, [message], 25000, 0, 0, set(), 0).kind == "abstain"


def test_competitor_claim_cannot_hide_project_entry_with_the_same_origin():
    actor = trader(subscriptions=("news", "competitor"))
    messages = [Message("project-confirmed", "shared-event", "news", 0, "confirmed"),
                Message("rival-post", "shared-event", "competitor", 1, "confirmed", asset="competitor")]
    action = decide(actor, messages, 25000, 0, 0, set(), 1)
    assert (action.kind, action.amount, action.evidence_origins) == ("buy", 2500, ("shared-event",))


def test_competitor_claim_cannot_hide_remembered_project_exit():
    actor = trader(subscriptions=("news", "competitor"))
    messages = [Message("project-denied", "shared-event", "news", 0, "contradicted"),
                Message("rival-post", "shared-event", "competitor", 1, "confirmed", asset="competitor")]
    action = decide(actor, messages, 25000, 100, 1000, {"shared-event"}, 1)
    assert (action.kind, action.amount, action.evidence_origins) == ("sell", 100, ("shared-event",))


def test_feed_deduplicates_within_assets_and_preserves_finite_attention():
    messages = [Message("project-rumor", "shared-event", "news", 0, "rumor"),
                Message("same-id", "shared-event", "news", 1, "confirmed"),
                Message("same-id", "shared-event", "competitor", 1, "confirmed", asset="competitor")]
    actor = trader(subscriptions=("news", "competitor"), attention_capacity=2)
    selected = select_messages(actor, messages, 1, set(), keyed_rng(1, "feed"))
    assert [(m.asset, m.id) for m in selected] == [("competitor", "same-id"), ("project", "same-id")]
    assert select_messages(actor, list(reversed(messages)), 1, set(), keyed_rng(1, "feed")) == selected
    actor = trader(subscriptions=("news", "competitor"), attention_capacity=1)
    selected = select_messages(actor, messages, 1, set(), keyed_rng(1, "feed"))
    assert len(selected) == 1
    assert selected[0].id == "same-id"
    assert select_messages(actor, list(reversed(messages)), 1, set(), keyed_rng(1, "feed")) == selected


def test_momentum_rumor_entry_and_no_order_for_zero_attention_or_cash():
    rumor = Message("rumor", "claim", "news", 0, "rumor")
    assert decide(trader(strategy="momentum"), [rumor], 25000, 0, 0, set(), 0).kind == "buy"
    assert select_messages(trader(attention_capacity=0), [rumor], 0, set(), keyed_rng(1, "feed")) == []
    assert decide(trader(strategy="momentum"), [rumor], 0, 0, 0, set(), 0).kind == "abstain"


@pytest.mark.parametrize("bad", [-1, True, 1.5])
def test_policy_rejects_invalid_balances(bad):
    with pytest.raises(ValueError):
        decide(trader(), [], bad, 0, 0, set(), 0)


def explicit_rule(**changes):
    from decision_lab.policy_bundles import PolicyRule
    fields = dict(template_id="retail-01", entry_signal="confirmed", entry_fraction_bps=500,
                  exit_on_contradiction=True, rationale="Synthetic reviewed policy.",
                  assumptions=("Uncalibrated fixture.",))
    fields.update(changes)
    return PolicyRule(**fields)


def test_explicit_rule_caps_fraction_and_position_budget_without_escalating_recipe():
    message = Message("m", "claim", "news", 0, "confirmed")
    actor = trader()
    assert decide(actor, [message], 25000, 0, 0, set(), 0, explicit_rule()).amount == 1250
    assert decide(actor, [message], 25000, 0, 0, set(), 0,
                  explicit_rule(entry_fraction_bps=10000)).amount == 2500
    assert decide(actor, [message], 25000, 0, 9900, set(), 0, explicit_rule()).amount == 100


def test_explicit_entry_signal_overrides_strategy_and_none_disables_entry():
    rumor = Message("m", "claim", "news", 0, "rumor")
    assert decide(trader(), [rumor], 25000, 0, 0, set(), 0,
                  explicit_rule(entry_signal="rumor_or_confirmed")).kind == "buy"
    assert decide(trader(strategy="momentum"), [rumor], 25000, 0, 0, set(), 0,
                  explicit_rule()).kind == "abstain"
    confirmed = Message("c", "claim", "news", 0, "confirmed")
    assert decide(trader(), [confirmed], 25000, 0, 0, set(), 0,
                  explicit_rule(entry_signal="none")).kind == "abstain"


def test_explicit_rule_can_disable_contradiction_exit_but_not_create_sell_capability():
    bad = Message("bad", "claim", "news", 0, "contradicted")
    assert decide(trader(), [bad], 0, 100, 2500, {"claim"}, 0,
                  explicit_rule(exit_on_contradiction=False)).kind == "abstain"
    assert decide(trader(), [bad], 0, 100, 2500, {"claim"}, 0,
                  explicit_rule()).kind == "sell"
    actor = trader(allowed_actions=frozenset({"abstain"}))
    assert decide(actor, [bad], 0, 100, 2500, {"claim"}, 0, explicit_rule()).kind == "abstain"


def test_rule_cannot_activate_passive_role_or_observe_private_future_unsubscribed_information():
    rule = explicit_rule(entry_signal="rumor_or_confirmed")
    m = Message("m", "claim", "news", 0, "confirmed")
    for actor in (trader(category="launch_teams"), trader(strategy="observe"), trader(attention_capacity=0),
                  trader(allowed_actions=frozenset({"abstain"}))):
        assert decide(actor, [m], 25000, 0, 0, set(), 0, rule).kind == "abstain"
    messages = [Message("p", "p", "news", 0, "confirmed", public=False),
                Message("f", "f", "news", 10, "confirmed"),
                Message("u", "u", "other", 0, "confirmed"),
                Message("c", "c", "creator", 0, "confirmed", asset="competitor")]
    assert decide(trader(), messages, 25000, 0, 0, set(), 0, rule).kind == "abstain"


def test_missing_rule_uses_explicit_fallback_without_changing_baseline():
    m = Message("m", "claim", "news", 0, "confirmed")
    assert decide(trader(), [m], 25000, 0, 0, set(), 0, fallback="baseline").kind == "buy"
    assert decide(trader(), [m], 25000, 0, 0, set(), 0, fallback="abstain").kind == "abstain"
    assert decide(trader(), [m], 25000, 0, 0, set(), 0, explicit_rule(), fallback="abstain").kind == "buy"


def test_policy_binding_and_fallback_fail_closed_when_invalid():
    for policy, fallback in ((explicit_rule(template_id="retail-02"), "baseline"), ({}, "baseline"), (None, "infer")):
        with pytest.raises(ValueError):
            decide(trader(), [], 25000, 0, 0, set(), 0, policy, fallback=fallback)
