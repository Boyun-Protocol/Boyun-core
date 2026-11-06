"""Shared author instructions for discovering contingent financial decisions.

Planning guidance only: this module does not evaluate triggers, monitor markets,
execute trades, assign event odds, or expand any engine input schema.
"""
from .evidence_planning import EVIDENCE_PLANNING_GUIDELINES

STRESS_PLANNING_VERSION = 'stress-discovery.v1'
STRESS_PLANNING_GUIDELINES = '''Financial stress discovery and contingent response planning (stress-discovery.v1).
Do not wait for the user to enumerate edge cases. Infer applicable lifecycle stages and dependencies
from the research question, then propose material failure, upside, transition and recovery branches.
Use existing answers; ask at most two or three unresolved, decision-changing questions at a time.
Do not expose this as a mandatory universal checklist or invent calibrated odds.

1. Map lifecycle states and actors' control. Separate state transitions, external shocks, observations,
actor choices and settlement. A threshold crossing is not automatically a migration or other protocol
transition: confirm the actual venue/program state. Example domains: token pre-migration/migrating/
post-migration; DEX bootstrap/incentives/ordinary operation/stress/recovery. Apply only relevant states.
2. Discover candidate branches across price/path volatility, liquidity/position concentration,
capital/runway/cash flow, incentives/adverse selection, operations/data/oracles/security, external
catalysts and recovery/terminal exit. Include favorable conditions, do-nothing/delay, failure of a
response and combined shocks. Describe which actor, resource, information or payoff each changes.
3. Specify each trigger before proposing a response: named metric and unit, source/venue, lifecycle,
reference value, comparator/boundary, event-time window, observation cadence, freshness/gap policy,
detection delay, who can see it, persistence/rearming and evidence status. Distinguish a return from
window-start from peak drawdown; do not silently substitute one for the other. Market cap is not
pool cash; distinguish circulating cap, FDV and quote units. Missing data is unknown, not no event.
Five-minute conditions cannot be verified or calibrated from fifteen-minute bars; do not fabricate
finer observations. Observed sampled crossings are not proof of all intrawindow threshold crossings.
4. Map observed conditions to reviewed response choices with authority, preconditions, resource bounds,
latency, action costs, execution constraints, possible failure/partial fill and fallback. In simulation
an automatic policy is distinct from asking the user at the time. Neither grants permission for a
real transaction. No stop rule guarantees a fill or its threshold price. A funded reserve cannot be
spent twice. An LP/incentive/fee/admin change must be possible for that actor under the actual venue.
5. Resolve overlapping triggers explicitly: evaluate from a declared snapshot/time order; choose
priority or composable actions; prevent duplicate spending and repeated firing; define cooldown,
recovery and cancellation of stale decisions at lifecycle transitions. Include dependent shocks and
other actors' strategic reactions without giving them private plans or future information.
6. Research occurrence and severity separately from responses. Keep empirical conditional frequencies,
model action judgments, assumed stress magnitudes and simulated outcome frequencies distinct.
Do not assign arbitrary branch percentages to complete a presentation. Overlapping or dependent
hazards do not form independent exhaustive outcomes. Rare/missing events can be explicit stress
paths with unknown occurrence odds. A model's preference for an action does not estimate crash odds.
7. Compare fixed initial plans AND contingent policies under equal economics and declared shock paths.
Report trigger/detection times, observations, chosen/rejected actions and feasibility reasons,
execution failures, cash/resource consequences, terminal inventory, drawdown and recovery. Retain
blocked/unobserved paths; show conditional scenario results separately from unconditional averages.
An advisory 'what if' table is not a live market monitor or an implemented financial backtest.
8. Stay within the caller's output schema and published engine capabilities; do not add planning keys
or executable expressions to strict world inputs. Use existing summary, questions and limitations
or draft fields to explain the missing decision/mechanism. If the requested rolling-time policy or
financial settlement is unsupported, disclose that and withhold a ready world through the caller's
existing clarification/incomplete-draft contract. Do not replace it with scheduled metric effects,
claiming equivalent five-minute detection, faithful venue migration or USD profit. This instruction
adds author awareness, not those runtime capabilities.

9. Dynamic event worlds (dynamic-event-planning.v1): when a user requests an evolving timeline,
plan repeated state-conditioned decisions, not one launch choice reused across all hours.
Research dated real-world announcement schedules with source, timezone, event/availability time,
revision status and an as-of cutoff. Propose an appropriate six- or twelve-month historical cohort
with actual coverage, sample sizes, missingness and holdout evaluation; do not pretend the window
exists or invent past data. Known scheduled times need not be randomized; uncertain content,
response, severity and unscheduled events need separately justified conditional models.
At least hourly in ordinary operation, ask relevant eligible actors fresh typed buy/sell/wait
choices from current permitted observations, own cash/inventory, history and affordable menus.
Declare eligibility/skipped-turn rules. Use finer, evidence-supported steps for a 10-15 minute
curve phase and event-triggered decisions. Actor model scores are not calibrated event odds.
Separate external announcements from actor-generated actions and derived volume spikes, price
changes and liquidity events. Settle actions before deriving their market effects; do not double
count a trade as both a price shock and background demand. Allow quiet hours and failed actions.
Specify conditional dependence/shared shocks, same-time barriers, delays, fees, fills, confirmed
venue transitions and checkpoint/replay receipts; exclude future and peers' private information.
Persist trajectories before constructing the actor DAG, threshold frequencies or recommendations.
Preflight actor-time-world call counts and spend, including triggered turns; do not lift round
limits or launch paid calls to satisfy this requirement. Cached/surrogate policies require explicit
labels and cannot silently replace fresh inference. Existing static launch sampling is not this
hourly financial lifecycle. Report the integration gap through existing questions/limitations;
never claim scheduled metric effects implement the requested dynamic market.
10. Persist pre/post state at every decision/event boundary: price, declared circulating market cap,
FDV, exact volume windows, cash/inventory, choices, execution, observation hashes and source status.
Carry forward public market history, own positions/choices, available events and commitments in
actor-specific memory; retain full checkpoints on disk. Do not silently truncate critical history.
Model paid token information, exposure boosts and KOL campaigns as distinct budgeted actions with
verified/assumed prices, delivery delays, reach, expiry and uncertain actor responses. A listing is
not the same as paid token information. Paid exposure does not guarantee purchases or price rises.
Founder/MM/marketing coordination needs explicit restricted channels, resources, authority and
proposal/acknowledgement/execution stages. Retail sees public effects, not private instructions.
Allow ignored campaigns, skeptical selling, failed delivery, organic inflows and no intervention;
never insert a price uplift in addition to the same originating trades or create fictitious volume.
Assess world mechanics and incentives before blaming model reasoning or adding a swarm. More
agents do not fix absent campaign actions, empty inventory or missing historical observations.'''
STRESS_PLANNING_GUIDELINES += '\n\n11. ' + EVIDENCE_PLANNING_GUIDELINES
