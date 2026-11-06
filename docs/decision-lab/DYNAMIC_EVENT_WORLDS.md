# Dynamic event worlds — model work requirement

Status: user-requested core behavior, recorded 2 November 2026. Planning and author
guidance implemented. A first bounded synthetic-pool timestamped actor runtime now
has native Jev pilot evidence; implementation and remaining gaps.
The full evidence-calibrated launch lifecycle remains open. This is a prerequisite
for an evidence-backed event DAG, not simply a request to draw more nodes.

## Required experience

Apply [the cross-domain evidence standard](SIMULATION_EVIDENCE_STANDARD.md) to
every assumption and consequence, including arrival rates, persona choices and
external-event responses. A reference schedule does not validate its modeled impact.

The [campaign, memory and coordination design](CAMPAIGNS_MEMORY_AND_COORDINATION.md)
records the next requirements and the current model assessment. Every node must
retain pre/post token state and actor decisions; later prompts must carry forward
the actor's permitted context. More agents alone do not replace these mechanics.

The world develops through repeated, informed actor choices and external events.
At each eligible decision time, relevant personas receive the current token or
protocol state and the information available to them, then choose feasible actions
such as buy, sell or wait. Settlement changes the shared state. The next decision
uses that new state, including the actor's updated cash and inventory. Activity,
feedback, divergent paths and discoverable outcomes emerge from these interactions.

Meaningful events should be discoverable every few hours when justified by the
world. Do not schedule a spike merely to keep the display busy. Quiet hours,
inactivity, failed execution, contradictory signals and unavailable observations
are legitimate states. More visual branches do not establish model realism.

## MACRON planning context

- Planned launch: 2 November 2026, 12:00 UTC+4 / 08:00 UTC.
- Expected curve duration: 10–15 minutes, a user expectation rather than certainty.
- Sniper bots excluded from the requested scope; report what that omission changes.
- Founder objective: maximize net cash and minimize loss; the accepted loss budget
  and protected reserve are each 10,000 USD. Neither guarantees an executable stop.
- General counterparties: Market Makers, Marketing Partners, Meme / Foundation
  Ecosystem, alongside retail and other justified participants.

Record exact launch venue/program rules and supported action rights. Do not borrow
the October static run's odds for a new timing model. A planned launch calendar is
not a record of a launch, migration or actual token demand.

## Work the research/author agent owns

### 1. Research external catalysts and historical dynamics

Build a source register for scheduled announcements, political events and other
relevant catalysts. Each record includes source, capture date, event time/window,
timezone, publication/availability time, schedule version, status (confirmed,
provisional, canceled, unknown), and permitted model use. Keep announcement timing
separate from its uncertain content and the uncertain response to that content.
Allow schedule revision, delay, cancellation and countervailing announcements.

Propose a six- or twelve-month historical window for an appropriate comparison
cohort, selected for coverage and comparability. State the actual available period,
sample count, missing intervals, venue changes, selection/survivorship bias and
whether price, trades, volume, liquidity and attention are observed. A six-month
request is not proof that six months of data exists. The user need not supply
probabilities; research and estimation are model work.

Freeze an as-of cutoff for the simulation. Fit estimates only on evidence available
before that cutoff and use chronological holdout checks where possible. A historical
simulation at 08:00 UTC cannot use an announcement first published at 09:00 UTC as
an actor input. Actual future news can appear only in a separately labeled replay.

Estimate event occurrence, severity, duration, recovery and dependence separately.
Use historical or conditional models with sample sizes and uncertainty when supported;
otherwise retain unknown occurrence odds or review explicitly assumed stress arms.
Scheduled events need not have random occurrence times. Randomize their uncertain
outcomes or response conditional on evidence, not the known calendar itself.

### 2. Construct actors that can change their minds

Define resources, positions, cost basis, objectives, risk behavior, commitments,
information access, observation delays and permissible actions. Ask relevant actors
at least hourly during ordinary operation, with a reviewed eligibility rule and
skipped-turn reason for inactive or unaffected actors. Trigger additional decisions
for material news, thresholds and venue transitions where supported.

The initial 10–15 minute curve phase needs sub-hour resolution, finer than the
expected transition window, chosen from data resolution and execution mechanics.
Do not freeze all actors until hour one or fabricate minute bars from hourly data.
Every active actor receives the latest permitted state, not a reused launch prompt.

Use typed Jev decisions over currently feasible buy/sell/wait quantities and role
actions. Recompute affordability from current balances. Model scores can change
with news, price, liquidity, recent volume, private knowledge and own history. Keep
raw responses, normalized scores, selected action, sampling rule, observation hash,
model identity and receipts. Do not request a reasoning trace Jev does not expose;
explanation refers to supplied state, declared objectives and numerical comparisons.

### 3. Separate exogenous and endogenous events

External event examples: a dated public announcement, a revised calendar, a market-
wide shock estimated from a declared cohort. Actor-originated events: permitted
promotion, an executed large sale, withdrawal of an actor's own liquidity, or a public
message. Derived events: a volume spike, drawdown, liquidity deterioration or threshold
crossing computed from resulting trades and state.

An announcement does not directly manufacture buyers. Actors observe it and react
through permitted actions; prices and cash follow execution. If an explicitly
modeled background population contributes demand, declare its resources and rules
once; do not count its trades again as named actors' demand. Avoid applying both an
arbitrary price shock and its supposed originating trade as separate effects.

Event intensities can depend on prior state and actor behavior through a reviewed
model. Use conditional distributions/shared factors rather than independent draws
for every visually distinct event. Correlation learned from history is not proof of
causal response. Common shocks may affect multiple actors without shared private plans.

## Runtime iteration at a decision boundary

1. Advance the clock to the next scheduled event, action execution, observation or
   decision boundary; keep event time and availability time distinct.
2. Apply due events and earlier committed executions under declared same-time
   precedence; do not apply an event twice when windows overlap.
3. Build an immutable actor-specific observation from available information, own
   balances/history and the correct metric windows; exclude future draws/private peers.
4. Determine eligible actors and affordable menus, then request their typed choices.
   Actors choosing in the same barrier do not see each other's fresh proposals.
5. Validate and commit proposals, then execute under a reviewed queue/simultaneous
   policy, including latency, fees, impact, failures, partial fills and cancellation
   only where supported. Proposed orders are not settled trades.
6. Derive volume, price, liquidity and event detectors from the updated venue state;
   compute market cap from its stated supply definition, not pool cash.
7. Record the complete checkpoint and deliver public observations/messages at their
   availability times. Continue until the declared horizon or terminal condition.

Use integer financial settlement and conservation checks. Domain adapters own venue
transition, liquidity, TVL, DAU and other metric semantics; renaming strategic points
does not implement token trading or a DeFi protocol.

## Reproducibility, budget and failure

Separate reproducibility of event draws and replay of recorded decisions from new
provider inference. Key random draws by seed/world/event/actor/time without leaking
them into observations. Replaying receipts makes no model request; a fresh model
run need not return identical decisions. Compare policies using matched external
draws and separately reevaluated actor reactions as defined by the experiment.

Preflight call counts, tokens, output size and possible spend before execution.
For example, 15 eligible actors × 48 hourly barriers × 20 worlds is 14,400 actor
turns before sub-hour or event-triggered turns; this is arithmetic, not approval
to spend. The existing estimator's 20,000 worlds must not silently become 20,000
fresh multi-round model runs. Small pilots, replay and explicitly labeled cached
or surrogate policies need distinct evidence and cost accounting. No silent retry,
fallback, cached choice under changed inputs, or limit increase.

Store blocked, failed and unfinished worlds with their denominator and reason.
Checkpointing resumes without duplicate calls/settlement. Authoring must report a
capability gap rather than bypass engine budgets or claim unsupported execution.

## Output: trajectories first, graph second

Persist timestamped state, actor observation hashes, action proposals and execution
receipts, exogenous source records, generated events, draw keys, decisions, failures
and model usage. The actor-projected DAG and graph-led PDF derive from those artifacts.

The full trajectory space can grow exponentially. Preserve individual paths and
render bounded summaries, expandable branches and filters. Never merge states
solely because displayed market caps match: continuation depends on positions,
private information, commitments and history. Show the policy/conditioning set,
sample size, horizon and uncertainty behind threshold frequencies. Do not multiply
marginal event odds or equate an actor's buy score with a $5M market-cap likelihood.

Recommendations compare feasible policies for the selected actor's objective and
known information. A retail recommendation cannot reveal a team's private sale
plan. Joint founder cash/loss objectives require explicit tradeoffs or a displayed
frontier, rather than an invented uniquely best action. Explain supporting evidence,
risks, alternatives and what would reverse a suggestion.

## Implementation gates

| Gate | Deliverable | Acceptance |
| --- | --- | --- |
| A. Evidence | As-of calendar and cohort manifest | Sources/timezones, unknowns, sample coverage, no future information |
| B. Clock and replay | Timestamped event/observation/action scheduler | Deterministic receipt replay, monotonic time, no duplicated effects |
| C. Actor loop | Fresh state-bound affordable decisions | State changes prompts/menus; current balance checks; hidden information excluded |
| D. Venue integration | Supported financial execution and transitions | Conservation, fees/impact, confirmed migration, failure semantics |
| E. Pilot | Small explicitly approved multi-world experiment | Full receipts, spend/denominator accounting, policy comparisons |
| F. Presentation | Artifact-derived actor DAG and PDFs | Probabilities reconcile; actor projections protect private state; missing data visible |

Also test quiet hours, contradictory announcements, late arrivals, correlated
shocks, no eligible actors, zero liquidity, repeated observations, stale news,
competing actions and expired provider budgets. Do not require actors to trade or
events to occur merely to satisfy a graph-density target.

## Current boundaries

`launch_estimate.py` remains a static sampled launch/exit estimator. Financial
`agent_worlds.py` has repeated round observations and settlement but not this
complete timestamped evidence-calibrated lifecycle. Strategic worlds and contingent
condition/policy runtimes supply useful separate primitives; none establishes that
all gates above are integrated. The HTML event map remains an illustrative prototype.

Planning guidance is propagated through the shared authoring instructions and case
report procedure. No live research, paid inference, venue call or new simulation
is triggered by this requirement document.
