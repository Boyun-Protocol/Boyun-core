# Persona customization that reaches the model

26 October 2026. The question flow first asks whose perspective matters, then
adds follow-ups for the chosen context. Balanced/retail perspectives ask whether
retail should be balanced, speculative/degen or cautious. Launch/DeFi plans and
team-focused questions ask whether the team should emphasize marketing,
liquidity/market-making readiness, or a balance. Other choices keep those
branches out of the flow. Inactive retail choices are normalized to balanced.

The recommendation tint now spans only 0.025–0.115 alpha; selected controls use
a separate gentle tint and border/checkmark. Text remains fully readable.
These interface guidance colors do not represent real-world event probabilities.

## Two real paths

**Custom authoring:** the selected retail style and team priority are included in
the actual author request brief. The author proposes profiles and rules, which
return for review. These inputs are requested motivations, not permission to
invent capital, observed behaviors, wallet-owner identities or outcome odds.
A staged author still freezes numeric allocations before profile batches.

**Ready worlds, including the shared Jev-only preview:** the user chooses a
perspective and follow-ups before loading the example. An optional exact
`persona_options` object is validated by `persona_controls.py`, then adapts
private motivation/goal text and role framing from the reviewed templates.
These changed profiles become part of the world and each actor's permitted
Jev observation. No Gemini call is needed. The adapted world is saved and
reviewed before paid actor calls.

The first role is the plan owner by the explicit example convention, not an
inferred real identity. Counterparty roles supply the hypothetical audience
perspective. Provenance is marked assumed/user-selected. Existing cash, utility
weights, action menus/costs, metric effects, events, peer links and rounds remain
unchanged. The base example is never mutated. A default balanced selection
returns the original world unchanged.

## Capital and market-making boundary

“Prioritize marketing” or “prioritize liquidity readiness” changes the persona's
motivation. It **does not allocate or spend capital**, buy audience, promise
liquidity, execute market-maker trades or add AMM inventory. Actual spending still
requires affordable actions in the reviewed engine. This distinction is stated
beside the question and retained in world assumptions. A future allocation
worksheet/venue adapter is a separate feature and must reconcile budget buckets,
market inventory and settlement before displaying funded allocations.

## Request

```json
{
  "mode": "example",
  "example_id": "near-launch-coordination",
  "question": "Compare the ready NEAR pilot",
  "public_input": false,
  "persona_options": {
    "focus": "retail",
    "retail_style": "degen",
    "team_priority": "marketing"
  }
}
```

Enums: focus `balanced|retail|liquidity|team`, retail style
`balanced|degen|cautious`, team priority `balanced|marketing|liquidity`. Unknown
fields/options are rejected. Authoring uses the brief rather than this example
adaptation field; the execution core still receives a validated world only.

Tests check unchanged financial/numeric state, real observation changes,
untouched source templates, unknown-field rejection and zero authoring attempts
for adapted ready examples. The local-only question map includes the selected
follow-ups; the public gateway continues to block internal routes.
