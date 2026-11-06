# Boyun in financial, economic and game research

Reviewed 29 October 2026 using primary papers, official project repositories and
official framework documentation. This is a research comparison, not a benchmark
ranking, dependency list, endorsement or transfer of published validation results.
MiroFish remains Boyun's direct software fork and is credited separately.

## Product focus

**Boyun simulates financial and economic decisions through actors with explicit
goals, incentives, resources, feasible actions and information.** The initial
scope is bounded crypto/DeFi research: capital-allocation choices, participation
incentives, disclosure, coordination and stress assumptions. Messages matter
when they change an actor's information or incentives; general social-life
simulation is not the product objective.

The current strategic product purchases declared effort and updates shared
metrics. It does not turn a participation score into a transaction, income,
creator profit or a full macroeconomy. The separate financial laboratory has
explicit accounting/AMM mechanics; these are not automatically joined to every
persona simulation. A new financial claim needs the corresponding settlement
mechanism, not a new label on a chart.

## What the decision record means

| Object | What can be checked | What cannot be inferred |
| --- | --- | --- |
| Reviewed game | Actor goals/weights, allocations, actions, costs, information and transition rules | That these assumptions describe real motives or a representative population |
| Supplied observation | Exactly which state and options were sent for a decision | Which facts the model internally attended to or believed |
| Typed Jev response | Returned scores, top label, actual selection mode/action, reported usage/model | Hidden deliberation, causal explanation, perfect rationality or calibration |
| Numeric result | Settlement, bounds, resource reconciliation and replay with saved choices | Identical fresh inference or real-world correctness |
| Provider receipt | Local request/response identities and provider-reported fields | Independently attested execution of a specific model |
| Optional NEAR commitment | Later disclosed bytes match the registered fingerprint | Why a decision was made, forecast truth, private identity or artifact availability |

The [official TypeSafe API](https://docs.typesafe.ai/api/system-one) returns
typed answers, reported model identity and usage. It supplies no internal
reasoning trace. Boyun's `reason` text for native typed decisions is an adapter
status explanation, not Jev-generated reasoning. A separate text-model
alternative can emit prose, but that is not independently verified internal
reasoning either.

The useful claims are **explicit incentives, recorded choices and replayable
numerical execution**. We removed the broad “Auditable” title. A construction
“audit” in the code means checks of the declared game, not a model-reasoning
audit. Comparing a choice with a payoff table establishes its stipulated
consequence or deviation value; it does not establish why Jev chose it.

## 1. AI Economist and Foundation: separate private and planner objectives

[Zheng et al., 2020](https://arxiv.org/abs/2004.13332v1) study individual
agents and a tax-setting planner using two-level reinforcement learning.
[Foundation's official repository](https://github.com/salesforce/ai-economist)
organizes economic simulations into agents, components and scenarios.

The relevant design principle is that the investigator's outcome measure and
each actor's objective are different. A founder's preferred policy need not
be attractive to a reviewer, treasury steward or independent participant.
Boyun declares those preferences separately, then evaluates recorded outcomes.
It does not train a planner, implement this economic environment or inherit
its policy-performance results. The official repository is archived (owner
archive notice: 6 November 2023); it is a research reference, not a newly added
runtime dependency.

## 2. EconAgent: contextual choices inside an economic mechanism

[Li et al., ACL 2024; arXiv v4](https://arxiv.org/abs/2310.10436v4) combine
language-model work/consumption decisions with an environment specifying
labor, goods, tax, savings and interest-rate dynamics. Perception and memory
condition individual decisions on their economic context.
[Official implementation](https://github.com/tsinghua-fib-lab/ACL24-EconAgent).

Its close connection to Boyun is **decision policy versus environment**:
an agent chooses; numeric rules determine consequences. Boyun uses reviewed
finite menus, explicit utility weights and native typed Jev decisions for a
smaller research question. It does not reproduce EconAgent's economy or memory
architecture. The paper's limitations distinguish reproducing stylized facts
from accurate forecasting; matching a plausible pattern alone does not validate
Boyun forecasts either.

The repository also records model/format compatibility issues. This reinforces
the practical need to validate returned decisions and record model identity;
it does not show that typed output alone fixes economic reasoning.

## 3. ABIDES: financial claims need financial execution

[Byrd, Hybinette and Balch, 2019](https://arxiv.org/abs/1904.12066v1) introduce
an exchange simulator with trading agents, message protocols and configurable
latencies. It supports research into execution and market impact.

This is a stronger comparator when a task asks about fills, prices or trading
returns. Boyun's strategic interface has no ABIDES exchange or limit-order book.
Its reviewed resource/action rules answer a narrower question. Before claiming
price formation or realized profit, we need an explicit venue, positions,
valuation, fees and execution model, with tests and data for that task.
ABIDES is neither installed nor called by Boyun.

## 4. OpenSpiel: explicit games and evaluable policies

[Lanctot et al., 2019](https://arxiv.org/abs/1908.09453v1) provide a framework
for game environments and algorithms. The [official introduction](https://openspiel.readthedocs.io/en/latest/intro.html)
distinguishes observations, information states, legal actions, chance,
simultaneous/sequential play and returns.

For Boyun, the relevant principle is to evaluate a policy on a known game
rather than assess it by its persona's biography. Our separate small-game
kernel checks supplied payoff tables and unilateral deviations. It does not
import OpenSpiel solvers or solve the large dynamic game. OpenSpiel is a useful
future comparison environment for a Jev policy; no adapter or benchmark result
is claimed in this revision.

## 5. Repeated-game experiments: an incentive instruction is not rationality

[Akata et al., 2025 revision](https://arxiv.org/abs/2305.16867v2) test language
models in finitely repeated games. They report different behavior across
self-interested and coordination settings, and changes when opponent information
is supplied. These are findings for the studied models and tasks, not Jev.

The lesson is methodological: test a persona policy against controlled changes
in payoffs, information, horizon and opponents. A system prompt that says
“maximize your utility” does not prove that the model finds the best strategy.
Jev supplies no conversational reasoning trace, and Boyun does not implement
the study's conversational reasoning intervention. Observable decisions and
payoff consequences remain valid objects for behavioral evaluation.

## Relationship to MiroFish, OASIS and CAMEL

[MiroFish](https://github.com/666ghj/MiroFish) remains the direct software and
workflow precedent, with AGPL attribution; its application source left the
package on 2026-10-31 (see [NOTICE](../../NOTICE)).
[Upstream reuse](UPSTREAM_REUSE.md) identifies what is inherited and what the
active Boyun engine replaces. OASIS and CAMEL are social-platform/agent
architecture precedents described in the paper; they are not the active Boyun
financial execution engine. Their role should not dominate the product's
financial/economic research framing.

These relationships are different: MiroFish is direct software provenance;
the other projects are related research and comparison targets. Boyun does
not quietly depend on all of them or claim their reported results.

## How this changes the research plan

| Research question | Appropriate next comparison | Current evidence |
| --- | --- | --- |
| Does a numeric preference change alter the policy? | Known payoff games; local utility rule versus Jev | Local-rule sensitivity implemented; new Jev prompt/cast not live-evaluated |
| Does information delivery change coordination? | Fixed game with message-link ablations and controlled opponent policies | Synthetic delivery/joint-rule ablation implemented |
| Does heterogeneous motivation add value? | Same economics and budget, heterogeneous versus identical preferences | Worked eight-role assumptions; no population-fidelity result |
| Does the typed prompt improve decisions economically? | Minimal contract versus numeric support; menu-order controls; cost/quality together | Versioned prompt and arithmetic checks, not a matched-quality benchmark |
| Are forecasts useful outside the simulator? | Prospective resolved outcomes; base-rate and single-model baselines | Scoring tools exist; relevant held-out forecast evidence missing |
| Can we study market returns? | Explicit exchange/AMM/position accounting matched to the question | Separate limited finance laboratory; no integrated strategic return claim |

## Source-reading scope

- EconAgent: arXiv v4 full HTML, framework/perception/memory/action structure,
  limitations and official repository README.
- AI Economist: version-1 abstract/metadata and Foundation's official README.
  The journal landing page returned an access challenge; no full journal-paper
  reading is claimed. The bibliography explicitly cites the available 2020 preprint.
- ABIDES: version-1 abstract/metadata, consistent with the existing paper reference.
- OpenSpiel: version-1 abstract/metadata and official framework introduction.
- Akata et al.: version-2 abstract/metadata; broad study findings only, with no
  unverified detailed effect size or experimental reproduction claim.
- TypeSafe: official System One API request/response documentation.

No additional runtime dependency, paid model call or chain transaction was
introduced to conduct this literature and framing revision.
