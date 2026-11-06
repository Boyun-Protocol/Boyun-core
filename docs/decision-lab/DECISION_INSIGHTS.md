# Decision insights from recorded strategic worlds

`decision_lab.product_insights.build_insights(snapshot)` turns completed strategic
results into two reviewable questions: where did the modeled cash go, and does a
supported static game expose a better unilateral choice under declared utility?
For multi-round worlds a separate opening-game diagnostic answers only that
opening-round question while full-world strategic analysis remains unavailable.
It makes zero model, provider or network calls and never advances or changes a
world. It is author-private, data-derived analysis, not generated advice.

The presentation payload includes the result as the top-level
`decision_insights` field. Its existing five slides and their order are unchanged.
`product_reports.report_data` includes the same field. Markdown and PDF exports
include a compact Decision insights section with exact cash equations and either
the supported static findings or the specific reason analysis was unavailable.

## Input and replay

The input is a product snapshot with a `results` list of zero to four entries.
Each entry needs `world_index` (a unique integer from 0 through 3) and `result`
(a `strategic-world-result.v1` report). Additional model-decision metadata is not
used to establish financial or strategic findings. The authoritative source is
the replayed world report, including its selected actions and expense receipts.

Every report is replayed using `replay_strategic_world` before deriving insights.
Reports must be completed and share one world definition. If
`proposal.world` is supplied, it must agree with that definition. Tampered
receipts, costs, cash, decisions, metrics, engine identity or mismatched worlds
raise `ValueError`; they never produce partial verified findings.

With zero results, both sections are `not_computed`, aggregate resources are
`null`, and actor/world rows are empty. Failed, interrupted or unattempted worlds
do not become zero-cost outcomes. `source.replay_verified` is `false` when there
is nothing to replay. A supplied world is validated but cannot substitute for a
completed recorded result.

## JSON contract

The schema identifier is `decision-insights.v1`. Output is bounded at 2 MiB of
canonical JSON, in addition to existing world and report execution limits.
All cash cents and utility values are exact decimal integer strings. There are
no floating point money, rounded utility, invented probability or provider-billing
fields. Indexes, counts and booleans use their normal JSON types.

```json
{
  "schema_version": "decision-insights.v1",
  "source": {
    "world_sha256": "world digest or null without a supplied world",
    "completed_worlds": 1,
    "replay_verified": true,
    "model_requests": 0
  },
  "resources": {
    "status": "computed",
    "reason": null,
    "actors": [
      {
        "id": "alice",
        "name": "Alice",
        "role": "Builder",
        "initial_cash_cents": "100",
        "worlds": [
          {
            "world_index": 0,
            "initial_cash_cents": "100",
            "action_cost_cents": "60",
            "remaining_cash_cents": "40",
            "reconciled": true
          }
        ],
        "aggregate": {
          "initial_cash_cents": "100",
          "action_cost_cents": "60",
          "remaining_cash_cents": "40",
          "reconciled": true
        }
      }
    ],
    "worlds": [
      {
        "world_index": 0,
        "initial_cash_cents": "200",
        "action_cost_cents": "60",
        "remaining_cash_cents": "140",
        "reconciled": true
      }
    ],
    "aggregate": {
      "initial_cash_cents": "200",
      "action_cost_cents": "60",
      "remaining_cash_cents": "140",
      "reconciled": true
    },
    "meaning": "Explanation of modeled expenses and alternative-run totals."
  },
  "strategic": {
    "status": "computed",
    "reason": null,
    "scope": "Exact author-omniscient complete-information one-round game.",
    "profile_count": 4,
    "players": [
      {
        "id": "alice",
        "name": "Alice",
        "actions": [{"id": "wait", "label": "Wait"}]
      }
    ],
    "strategy_beliefs": null,
    "pure_nash_profiles": [{"alice": "wait", "bob": "wait"}],
    "strictly_dominated_actions": [
      {"player_id": "alice", "action_id": "build", "dominating_action_ids": ["wait"]}
    ],
    "observed_profiles": [
      {
        "world_index": 0,
        "actions": {"alice": "build", "bob": "wait"},
        "is_pure_nash": false,
        "actors": [
          {
            "id": "alice",
            "selected_action_id": "build",
            "selected_utility": "50",
            "best_response_action_ids": ["wait"],
            "best_response_utility": "110",
            "unilateral_improvement_utility": "60",
            "selected_cost_cents": "60",
            "best_responses": [{"action_id": "wait", "cost_cents": "0"}]
          }
        ]
      }
    ],
    "utility_unit": "declared utility points",
    "game_sha256": "finite-game digest",
    "engine_sha256": "finite-game analyzer digest",
    "limitations": ["Scope and interpretation limits."]
  },
  "opening_game": {
    "status": "computed",
    "scope": "FIRST ROUND ONLY: separate static diagnostic; same fields as strategic."
  },
  "caveats": ["Hypothetical rules, completion scope, billing separation and privacy."],
  "numeric_format": "Cash cents and utility are exact decimal integer strings."
}
```

The example abbreviates actor/action rows and explanatory text. Actual output
includes every applicable actor and affordable action. For an unavailable
strategic section, `status` is `not_computed`, `reason` explains why,
`profile_count` is `null`, findings and player rows are empty, and the two
finite-game digest fields are absent. Scope, limitations, utility unit and
`strategy_beliefs: null` remain present.

`opening_game` has the same complete section shape as `strategic`; its abbreviated
entry above is not a separate reduced schema. For one-round worlds its data
equals `strategic`. For multi-round worlds, its `scope` starts `FIRST ROUND ONLY`
and explicitly excludes future messages, events and commitments, later decisions
and reactions. It can be computed while `strategic.status` is `not_computed`.

## Expense and cash reconciliation

For each actor in each completed world, action cost is independently summed from
the replayed round receipts and checked against the actor's recorded total:

```text
initial_cash_cents - sum(round.receipt.cost_cents) = final_cash_cents
```

The same equation is checked for each entire world, each actor across completed
worlds, and the aggregate of completed worlds. Per-actor
`initial_cash_cents` is the supplied starting amount for one world; the actor's
`aggregate.initial_cash_cents` repeats that allocation for every completed world.
Aggregates sum alternative simulated runs. They are not a pooled portfolio,
expected cash balance or probability-weighted forecast.

The strategic engine models expenses leaving actor cash and accumulating in a
cost sink. It has no revenue, transfers, AMM, trades, borrowing, asset valuation
or profit mechanism. A shared metric improving or declared utility increasing
does not turn action spending into financial return. Provider call charges,
native token usage and input list-price estimates remain in separate run accounting;
actual provider billing is not attested.

## Static incentives and observed unilateral choices

The bridge calls the existing `strategic_worlds.strategic_game` without strategy
beliefs. That function constructs the finite table using the actual first-round
event effects, affordable actions, simultaneous aggregate effects, interactions,
metric clamps, actor cash and supplied utility weights, then calls the existing
exact `strategic_games.analyze_game` implementation.

The main `strategic` section only exposes this analysis for one-round worlds.
Multi-round worlds receive an explicit unsupported-horizon reason. The separate
`opening_game` diagnostic still calls `strategic_game` on the unchanged original
world to analyze opening incentives; it does not rewrite `world.rounds`, events,
recorded actions or settlement. First-round scheduled events are included; later
scheduled events, future messages, commitments, later action choices and reactions
are excluded. Opening Nash profiles apply solely to that static counterfactual,
not the multi-round world, a repeated game or its full trajectory.
Other existing analyzer limits also return specific reasons:

- Two to four actors, each with at least two affordable actions.
- At most 256 affordable joint profiles.
- Absolute raw utility at most `10**9`; larger values are not silently rescaled.

Pure Nash profiles have no strictly improving unilateral deviation in this
supplied static table. Strictly dominated actions are worse than another pure
action at every affordable opponent profile. Neither finding predicts how actors
will act. Absence of pure Nash does not establish absence of mixed equilibrium;
no mixed equilibrium solver is used.

For each recorded one-round profile, `observed_profiles` fixes all opponents at
their actual recorded actions, enumerates each actor's affordable alternatives,
and reports exact best-response utility and improvement over the selected
action. All tied best responses are retained, with their explicit cash costs.
This makes an incentive difference inspectable without claiming that choosing
it causes opponents to stay fixed, respects private information, or improves a
future trajectory. The complete-information analysis uses author-known private
utility weights and is not Bayesian Nash or a persona's available knowledge.

No actor action distributions are invented. There is no expected utility under
beliefs, probability of an equilibrium, confidence score, recommended trade or
forecast derived from this calculation.

## Export and verification

Markdown and PDF show per-world cash reconciliation, aggregate accounting,
analysis availability, exact profile/dominance counts and recorded unilateral
improvements. To keep exports compact, they show at most eight pure Nash
profiles and eight dominated-action findings, and explicitly label any omitted
rows. Presentation JSON retains every bounded finding. Supplied names and
other text are escaped by the existing Markdown/PDF renderers. When the main
strategic analysis is unavailable and the opening diagnostic is supported,
exports preserve the unavailable reason and label a separate Opening game
diagnostic before displaying its opening-only scope and findings.

`engine/tests/test_product_insights.py` executes real worlds and covers exact
actor/world/aggregate expense reconciliation, one-round pure equilibria and
dominance, unilateral incentives, no beliefs, zero results, unsupported horizons
and casts, affordability/profile caps, payoff overflow, tampering, duplicate
world identity, bounded 100-actor output, and presentation/report integration.
Opening-diagnostic tests execute the original two-round world, confirm unchanged
replay and cash settlement, change a future-round event and verify opening
findings stay identical, and check absent beliefs and honest unsupported-cast
behavior.
