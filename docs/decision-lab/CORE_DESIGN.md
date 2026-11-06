# How the core engines work, from the first input to the result

Design discussion, 23 October 2026. **No product code is authorized by this document alone.** The user requested explanation and discussion before implementation. The earlier implementation plan is provisional until this design is reviewed.

Historical design record: the user subsequently authorized core implementation and execution of remaining tasks. The open/recommended labels below describe that earlier discussion, not a new approval request. See current work status and core runbook for implemented behavior and remaining limits.

## Governing evidence rule — confirmed 2 November 2026

For **every simulation domain**, apply the
[shared evidence standard](SIMULATION_EVIDENCE_STANDARD.md): every material
numerical or qualitative assumption and its modeled consequences need a specific
real-life reference or a documented reasonable cause. Trace input → mechanism →
outcome; preserve uncertainty, sensitivity and falsification. A labelled arbitrary
number is not sufficient. Predictions, polls, resolved votes, market quotes and
actor-model scores are not interchangeable probabilities.

This is a standing framework requirement, not a MACRON-specific setting or a
provisional design suggestion. Reuse it when creating a new domain or resuming
an existing case. Keep accepted case choices separate from generalized methods;
do not copy one case's thresholds, capital, horizon or actor roster into another.
The standard records which checks are implemented and which remain author review;
no document or passing schema certifies real-world validity.

## Read this first

The product has to answer two different questions:

1. **If these assumptions and actions were true, what could happen to my money?** A transparent simulator can answer this without pretending to know the real odds.
2. **How likely are those assumptions and outcomes in the real world?** That requires relevant observations, a specified statistical model and evaluation. Detailed AI biographies do not provide that evidence.

The engine should make the first answer inspectable and gradually earn the second. A convincing story is not an acceptable substitute for either.

**Confirmed by the user:** crypto/finance focus; roughly 50–100 detailed templates; reviewed templates → scenario-specific cast; evidence or labelled assumptions for parameters; hybrid model-assisted strategic decisions with numeric execution; funded campaign posts competing for limited attention, followed by independent actor decisions; AGPL-compatible MiroFish reuse; remote providers selected by the user may read confidential inputs; public disclosure must be controlled; profit is after all costs.

**Recommended engineering choices, still open to review:** start with explicitly funded individual synthetic actors, not population multipliers; compare fixed founder plans before autonomous founder strategy search; no full natural-language conversation for every pair of actors; scenario analysis first, calibrated forecasts only when supported by evaluation; core engine before UI adaptation, NEAR or pitch work.

**Still being explained, not approved:** keeping one version of decision logic consistent during a batch of repeated simulated worlds. The user asked what “frozen policies” and “Monte Carlo” mean; that question is not consent to this design choice.

## Two terms explained using your memecoin example

**Simulation** means letting the modeled people, market and events interact to produce one possible history. **Monte Carlo** means doing that repeatedly while sampling different uncertain conditions. It is a repetition technique around the simulator, not a model, a blockchain feature or an automatic source of true probabilities.

**A policy is a decision rule.** For example: “If credible relevant news arrives and the position limit allows it, consider a small entry; if the thesis is contradicted, attempt to exit.” Keeping that policy **fixed within a batch** means the rule does not secretly change after the engine has seen earlier results.

| Fixed within the proposed batch | Can change inside each simulated world |
|---|---|
| The trader's policy family and declared parameter-generation recipe | The news it receives, and when |
| The model-assisted interpretation/decision mapping and its validity limits | Beliefs, attention, cash, holdings and available actions |
| Financial constraints and venue mechanics | Prices, depth, others' trades and feasible fills |
| The stated probability/assumption model | Which permitted event actually happens |

The actor is **not frozen**. It can buy in one world, wait in a second and attempt an exit in a third because its observations/state differ. A fixed rule can also contain declared random behavior. What stays consistent is the rule and its sampling recipe, not every action or result.

**Why repeat worlds?** Your launch can face attention fading, a fresh catalyst, a competitor, a thin exit or different buyer participation. One happy path cannot show their combined consequences. Repeated sampling explores those combinations. For illustration only, if 180 of 1,000 sampled worlds exceed $20k net profit, that is an 18% simulated frequency **under the supplied assumptions**. No such run has been performed here, and that number is not a forecast.

If we lack defensible event probabilities, we can first show named what-if scenarios and sensitivity ranges **without a single overall percentage**. Monte Carlo does not repair missing evidence. Enumerating a small scenario tree is also a valid early baseline; random sampling is useful when combinations become too numerous to enumerate conveniently.

**Why fix the rules for the batch?** Otherwise world #1 might use a newly consulted model, while world #900 uses fallback rules because the API budget ran out. The reported percentage would mix different decision systems and depend on processing order. Instead, prepare/review a policy version, run a comparable batch, inspect its gaps, then improve a new version. New real-world information can create a new scenario/policy revision and a new batch. Interactive adaptive exploration remains possible, with separate labels.

Recommended wording going forward: **“consistent decision rules within one experiment”**, rather than assuming “frozen policies” is self-explanatory.

## The five ideas that connect everything

| Idea | Meaning | Why it exists |
|---|---|---|
| Template | A reusable role, such as a cautious retail trader | We can review behavior once instead of inventing a new personality for every run |
| Actor | One instance of a template with its own information, state and resources | Two traders can have the same role but different balances, timing and beliefs |
| Entity/account | The owner of money, tokens or permissions | Two roles on the same project must not create two treasuries |
| World | One possible sequence of external events and participant decisions | One story cannot represent uncertainty |
| Policy | A rule for choosing an action from an actor's available information | A biography alone does not specify how to buy, sell, wait or publish |

The path is:

```text
Private brief + evidence
        ↓
Reviewable world model + scenario-specific cast
        ↓
Actor observations → beliefs → strategic choice
        ↓
Permission/risk checks → venue execution → ledger
        ↓
New observations and later choices
        ↓
Many worlds → cash outcomes + sensitivity + explanations
```

Models help interpret and propose. The environment decides what is possible. The ledger determines what actually happened to money.

## What the current 80 profiles really are

They are **original, manually described synthetic templates**, serialized by a preparation script. They were not inferred from NEAR traders, wallet histories, interviews or a representative dataset. No model call generated them.

The preparation script currently sets attention half-life as `6 + index * 6`, links each profile to an adjacent category by index, and varies some delay/risk settings by list position. Those formulas were schema examples. **List order is not a reason for behavioral differences. Those numeric/network settings must not become production defaults.**

Keep useful role descriptions and contrasting objectives. Replace the arbitrary numeric/network generation before using the pool for a meaningful simulation. The existing asset checker verifies file structure and references; it does not validate realism or prediction quality.

Ten templates per category is a catalogue organization choice. It does not mean a real launch has ten whales, ten arbitrageurs and ten journalists. The earlier “include every eligible template” default is superseded by the user's newly confirmed **scenario-specific cast** direction.

## Every touch point: purpose, handoff and failure behavior

The artifact names A1–A10 refer to logical records explained later. They need not be ten separate files, services or model calls.

### A. Turn a question into a model we can inspect

| Step | What goes in → what comes out | Why it exists | Saved artifact / failure behavior |
|---|---|---|---|
| 1. Define the decision | Prose → target, horizon, candidate plans, profit definition, constraints | “Token price rises” and “creator earns cash” are different targets | **A1 InputRevision**. Missing target/horizon stops compilation |
| 2. Set private access | Provider choices and files → authorized data destinations | Remote inference permission must not become public publication permission | A1 settings; credentials stay outside artifacts. No selected provider means local/rules mode |
| 3. Gather evidence | User documents, allowed public sources, venue/data adapters → dated source records | Decisions need facts with known dates, not recalled or invented events | **A2 EvidenceSnapshot**; unavailable sources are reported, never silently fabricated |
| 4. Extract and distinguish claims | Sources → facts, disputed claims, unknowns, duplicates | Ten reposts of one rumor are not ten independent confirmations | A2 claim/source links and data cutoff; conflicting claims remain visible |
| 5. Register parameters | Evidence + user constraints + explicit assumptions → values/ranges with units and provenance | Every number that affects results must have an inspectable origin | **A3 ModelSpec** parameter registry. Material unknowns block real-venue mode or require a labelled assumption |
| 6. Compile event and market rules | Target, venue rules, assumptions → conditional event graph, market mechanics, time schedule | A language model's story must become something executable and falsifiable | A3; validate dependencies, probability semantics, units and venue limits |

### B. Build the people and information environment

| Step | What goes in → what comes out | Why it exists | Saved artifact / failure behavior |
|---|---|---|---|
| 7. Select relevant roles | ModelSpec + reviewed library → eligible roles and exclusions | No second venue means no executable arbitrage; observers need not trade | **A4 ScenarioCast** includes each inclusion/exclusion reason |
| 8. Choose cast composition | Relevant roles + market-size assumptions → actor counts and outside-capital constraints | Eighty templates are not a measured population or a funding source | A4 + A3 assumptions. Unsupported composition is a sensitivity variable, not a claimed fact |
| 9. Instantiate actors | Template + scenario parameters + named random draws → distinct actor IDs and starting traits | Same-role actors need controlled variation without duplicated identities or money | A4 instantiation recipe. Unknown traits retain labelled ranges; no fake biographies |
| 10. Bind economic owners | Actor roles + project/participant budgets → account ownership and permissions | Founder and LP operator can share one treasury; other participants cannot spend it | A4 ownership plus ledger initialization in A3; reject duplicate endowments |
| 11. Build observation links | Scenario relationships + labelled network assumptions → directed information graph | Not everyone sees a post immediately, trusts it or has private access | A4 edge type, exposure, trust, delay and source; replace the old index-based edges |
| 12. Create readable profile | Structured actor specification → human-readable description | Lets users inspect motives and limitations | Derived view of A4, not another behavioral authority. Prose may not change numeric parameters |
| 13. Compile decision policies | Traits + allowed observations/actions + model-assisted judgments → bounded policies | “Risk-averse” needs an operational meaning to affect a decision | **A5 PolicyBundle** with rules, model receipts and validity limits; invalid choices abstain or fail visibly |

### C. Freeze the experiment, then run a world

| Step | What goes in → what comes out | Why it exists | Saved artifact / failure behavior |
|---|---|---|---|
| 14. Review and freeze | A1–A5 + budget/config → immutable versions and run identity | A result is meaningless if its assumptions can change unnoticed during execution | **A6 RunManifest**; edits create a new version/run, not a silent overwrite |
| 15. Initialize one world | Manifest + random stream → funded accounts, sampled environment/traits | Different worlds represent alternative plausible conditions | **A7 RunData**. Separate shared event randomness, participant randomness and execution-order randomness |
| 16. Apply due external events | Conditional event model + current time → event truth/state changes | Political developments and outages do not originate from a trader's imagination | A7 external event records; one shared event draw per world, with separate noisy/delayed reports |
| 17. Deliver observations | Published messages + graph + delays + permissions → each actor's inbox | Prevents omniscience and private-plan leakage | A7 selected observation receipts; deduplicate origin claims, not merely text strings |
| 18. Update beliefs and attention | Own observations + previous state → actor's revised interpretation | Seeing news matters only if it changes what the actor expects or attends to | A7 state changes/reason codes; uncalibrated scores are not called Bayesian probabilities |
| 19. Choose a strategic action | Actor state + frozen policy + trigger → proposed action | Different motives must cause different behavior at relevant moments | A7 typed action with policy/model provenance; unsupported states use the bundle's declared fallback, not an expanding live policy |
| 20. Authorize the action | Proposal + current balances, inventory, vesting, campaign/venue permissions → feasible order/message or rejection | Models can propose impossible actions; hard constraints must still hold | A7 accept/reject reason; authorization never depends on eloquent prose |
| 21. Execute and account | Accepted action + venue state/order → fill, fees, transfers, public outputs | Intent is not a fill; price impact and cash movement must be computed | A7 ledger/execution events atomically recorded; insufficient funds/depth cannot create cash |
| 22. Schedule feedback | Fills, publications and state changes → future public information and due actions | One participant's action can alter what others see and what they can execute | A7 queued events; no instantaneous unlimited repost/trade loop |
| 23. Checkpoint/cancel | Completed-world state + progress → durable restart point | Long jobs must not lose all progress or double-apply actions | A7 checkpoint and budget journal; restart incomplete world with recorded draws, do not count it twice |

### D. Turn worlds into an answer

| Step | What goes in → what comes out | Why it exists | Saved artifact / failure behavior |
|---|---|---|---|
| 24. Aggregate outcomes | Completed worlds + project ledger → cash-profit distribution, outcome counts, unresolved assets | The target is money the founder can withdraw, not simulated enthusiasm | **A8 AnalysisResult**. Partial runs show completed count and failure status |
| 25. Compare and stress assumptions | Same exogenous samples across candidate plans + parameter sweeps → paired differences and fragile conclusions | A useful tool helps decide and shows when its recommendation reverses | A8; separate within-model variation from disagreement between models/assumptions |
| 26. Explain with evidence | A8 + selected actual traces → readable causal paths and limitations | Users need to understand why results differ | Derived report from A8/A7. Model cannot alter arithmetic or fabricate a trace |
| 27. Evaluate | Frozen as-of inputs + resolved historical targets + baseline → validity/skill report | We must find out whether the simulator improves decisions or forecasts | **A9 EvaluationReport**, only when data exists. No outcome data means no accuracy claim |

### E. Optional boundaries, after the core works

| Step | What goes in → what comes out | Why it exists | Saved artifact / failure behavior |
|---|---|---|---|
| 28. Export or commit | Explicit user choice + safe projection → sanitized export / salted commitment | Supports reproducibility without automatically disclosing private plans | **A10 SafeExport**, optional; real confidential input stays private by default |
| 29. NEAR/provider adapters | Defined request → provider response, testnet receipt or supported-asset dry quote | Connects an already useful engine to external infrastructure | Linked receipts in A6/A10. Adapter failure does not change simulated historical results |

No NEAR transaction is needed to generate personas, interact, execute a simulated trade or calculate profit. That boundary is deliberate: blockchain is not a numerical simulation engine.

## Persona generation, precisely

### Step P1: Review archetypes once

An archetype contains a role, objective, economic capabilities, observation channels, policy family and necessary parameters. Keep a role only if removing it changes a decision, market constraint or information path we care about. “Knows French primary sources sooner” can matter; an invented favorite meal does not affect this engine.

The existing 80 descriptions form a draft library, not 80 validated behavioral models. Review each for redundant behavior, missing capabilities and unsupported assumptions. More words do not make two otherwise identical policies different.

### Step P2: Match the scenario to eligible roles

Use explicit capabilities first: chain, venue access, instruments, languages where they affect information access, public/private channels and relevant decisions. A model may propose relevance, but code enforces eligibility. Record why an actor is included, excluded or observation-only.

Do not infer a real person's risk tolerance or political beliefs from geography, nationality or a wallet balance. These are synthetic roles. Country/language can define observable source access only when the scenario needs that mechanism.

### Step P3: Choose a population model, not a balanced catalogue

The cast count is a computational choice; its composition and aggregate capital are modeling assumptions. A possible **illustrative 80-actor fixture**, not an empirical NEAR estimate:

| Group | Actors | Reason for including the mechanism |
|---|---:|---|
| Retail | 48 | Many small independent purchase/exit decisions |
| Event traders | 12 | Faster and differently informed reactions to the catalyst |
| Large holders | 4 | Concentration and trade-size effects |
| Liquidity roles | 3 | Available inventory/depth and permitted withdrawal |
| Arbitrage | 2 | Only active if two executable markets exist; otherwise excluded or replaced with a visible reason |
| Creators/marketing | 4 | Attention distribution and campaign costs |
| Launch teams | 3 | One founder and two competing projects |
| Analysts/community | 4 | Verification, skepticism and moderation |
| **Total** | **80** | An experiment size, not the whole real market |

An actor may instantiate a reviewed template already used by another actor. Every instance has a unique ID, its own state and appropriately funded ownership. Catalogue balance does not dictate cast balance. If capabilities exclude a role, never silently invent access merely to keep the count at 80.

Start with individual actors and weight 1. This bounds what the demo can represent: it does not simulate millions of unseen buyers. If later introducing aggregate background order flow or cohorts, specify their capital, execution and overlap with named actors; never count the same demand twice. Market participation/capital ranges should be varied explicitly because they can dominate creator profit.

### Step P4: Give each consequential parameter an origin

Each parameter has: `id`, `target`, `value_or_distribution`, `unit`, `status`, `source_ids`, `as_of`, `rationale`, `allowed_range`, `dependencies`, `sensitivity_priority`.

Use exactly these origin categories:

- **User constraint:** $10k available, locked founder tokens, approved campaign budget.
- **Observed:** a documented venue fee or measured historical activity, with scope/date.
- **Estimated:** derived from an identified dataset and method, with uncertainty and limitations.
- **Assumed:** a declared synthetic range because no adequate evidence exists.
- **Model-proposed:** an unreviewed suggestion; cannot silently be promoted to observed/estimated.

Example: a “cautious trader” has an assumed small position limit and a documented inability to access a particular venue. The description follows those facts. The model cannot invent a $50k balance or set “70% likely to buy” because the biography sounds plausible.

Avoid uniform sampling merely because a range exists. A range alone does not specify relative likelihood. Where distribution evidence is missing, use an explicit assumption ensemble/stress sweep rather than present a chosen uniform distribution as reality. Respect dependencies: resources, position limits, venue eligibility and response times cannot be independently sampled into impossible combinations.

### Step P5: Instantiate traits and starting state separately

**Traits** are comparatively stable: objectives, loss tolerance, source access, attention/holding tendencies, strategy family and permissions. **State** changes: cash, tokens, observations, beliefs, outstanding commitments and current attention. The actor's state cannot be encoded only inside a prose prompt; the engine must inspect and update it.

Static scenario parameters can be fixed across a comparison, while sampled traits vary across an outer assumption ensemble. Within a world, future event outcomes use separate random draws. Store the recipe and realized draws so we can tell whether a result changed because of the environment, population or policy.

### Step P6: Render the description and validate behavior

Generate the readable description **from** the structured actor, optionally using a frontier model. It describes the actual capabilities and policy; it does not override them. Avoid fictitious past actions or private relationships presented as evidence.

Validate: one project founder; no duplicated treasury; valid source references; no future/private observations; legal action set; feasible starting balances; appropriate horizon/venue; all assumptions labelled. Test contrasting cases: better evidence, worse depth and breached risk limit should yield the intended different responses. Do not require “good news always means buy”; it may already be priced in or conflict with the actor's constraints.

## Rules, models and game theory: who controls what

| Layer | Example | Who establishes it | Can a model override it? |
|---|---|---|---|
| Financial law inside the model | No spending unavailable cash; token/fee accounting | Numeric code and verified venue specification | No |
| User restriction | Founder cannot sell vested tokens before a date | User/contract constraint | No |
| Behavioral assumption | Actor avoids large concentration or loses interest after a short period | Reviewed policy with sourced/labelled parameters | It may propose a revision for a new version, not silently rewrite the current run |
| Interpretation | A report is a rumor, relevant to the catalyst, or a material contradiction | Selected model / typed judgments / explicit rules | Within bounded labels and recorded confidence semantics |
| Strategic choice | Enter small, wait, reduce exposure, publish a verified correction | Policy informed by the model and current permitted state | Proposal only; must pass authorization |
| World uncertainty | Catalyst occurs, attention persists, infrastructure fails | Declared conditional probability model / assumption ensemble | A language-model assertion alone is not the probability model |

An **expected utility** policy weighs the actor's own expected benefit against costs and risks. For a trading fixture, one possible explicit score is `expected own return - execution costs - risk penalty`. A marketing actor instead evaluates campaign compensation, effort and reputation constraints. Units and coefficients must be defined within each policy; do not add an arbitrary “reputation score” to USD profit without a declared conversion/normalization. Hard limits are checked before scores.

The actor's expected price/return is its own limited estimate, not the actual future sampled path. Using the latter would grant it perfect foresight.

### Concrete first policies: what actually makes an actor act

For the first baseline, prefer explicit conditional rules over an undefined “utility optimizer.” A strategy module must expose `required_parameters`, `observation_fields`, `state_fields`, `choose_action` and `action_reason_codes`. All required thresholds come from the parameter registry; missing required thresholds cause abstention/validation failure, not an invented value.

| Policy family | Reads | Rule order and proposed action | Why this is a separate behavior |
|---|---|---|---|
| Cautious news trader | Allowed claim IDs/status, relevance label, valid venue quote, own exposure/cash | First check access/quote freshness. If a previously used thesis is contradicted or its recorded risk limit triggers, attempt a permitted exit. Otherwise enter only on a new, relevant, confirmed claim and acceptable execution costs, within remaining exposure/cash caps. Otherwise wait | Requires evidence; does not buy because another actor is excited |
| Attention/momentum trader | Allowed rolling public attention/price observations, own cash/inventory, time window | Check risk/expiry first. Enter only when the actor's observed, dated activity crosses its declared threshold and execution is feasible. Reduce exposure when attention decays or the holding window expires | Responds to observed market participation rather than proof the political thesis is true |
| Large depth-sensitive buyer | Own inventory/cash, public concentration and size-specific executable quote | Abstain if its proposed size would breach concentration, price-impact or exit-depth constraints; otherwise follow its configured news/momentum policy with a capped order | Wealth creates possible size, not mandatory buying |
| Liquidity controller | Own permissions/inventory, actual venue rules and a funded allocation plan | Add/remove only allowed amounts at scheduled/triggered points, respecting locks. Founder LP role uses the project plan; independent LP policy has separate funded inventory | Changes available execution depth and inventory risk |
| Verification observer | Permitted claims/primary sources, own time/action allowance | Request evidence for unresolved material claims; publish a correction/confirmation only when its evidence rule passes; no trading actions | Changes what others may learn, without conjuring capital |
| Project founder | Reviewed plan, own budget/vested inventory and observed contingencies | Execute scheduled actions only if hard constraints pass; apply explicitly approved stop/contingency rules. No unrequested optimization of the whole launch plan | Defines the intervention we are comparing |

The template library can select combinations/variants of these families, but two templates with identical effective parameters/observations need not receive different decisions just to look diverse.

For a synthetic cautious retail actor, a declared `max_entry_fraction = 0.10` and $250 available cash permit an entry proposal of at most $25, further limited by remaining exposure and venue rules. That 0.10 is a fixture assumption, not an estimated human trait. A decision identifies the claim already acted on, so receiving ten copies does not trigger ten independent entries. A risk-triggered exit is an **attempt**, not guaranteed execution at a stop price.

The initial belief representation can be deliberately modest: claim status (`unconfirmed`, `corroborated`, `disputed`), relevance (`low`, `medium`, `high`), novelty (`new`, `repeat`) and actor-specific interpretation (`favorable`, `mixed`, `unfavorable`). Explicit observation rules or bounded model judgments update these fields. This avoids inventing numerical probability estimates for every actor. Add a numerical Bayesian/utility model only for an identified, testable target with specified inputs and likelihood/payoff assumptions.

The game-theory element is strategic dependence: a founder's spend influences attention; other projects compete for it; buyers anticipate other buyers/exits; liquidity providers react to inventory risk. We are initially implementing **bounded strategic responses**, not proving a Nash equilibrium or solving the entire market. Simple response games and best-response approximations can be added only with explicit payoff definitions and testable value.

**Important founder-policy default:** compare specified plans first, for example launch now versus wait, with a reviewed sale/spend schedule. Other actors respond. An autonomous founder that optimizes its actions at every step is a different experiment; do not mix it into fixed-plan comparisons without labeling that change.

### Where the hybrid model helps

1. Frontier model proposes a structured scenario and reviews semantic gaps; facts and numerical assumptions retain provenance.
2. During policy preparation, Jev or another chosen model makes bounded judgments for **meaningful trigger states**: new relevant evidence, contradiction, campaign offer or a changed strategic regime. Rollouts consult those frozen judgments. A rule can handle an already-defined price/loss threshold without another language call.
3. Numeric policies handle time, balances, attention decay, eligibility, position sizing, scheduling and execution between triggers.
4. Frontier model explains actual results and traces afterward.

During policy preparation, each representative trigger state creates a request containing only the actor's permitted observations/state and relevant policy context. A typed response could select `enter_small`, `hold`, `reduce_exposure`, `wait_for_confirmation` or `abstain`. Code maps that decision into a bounded executable proposal using **current** cash/inventory and venue limits. Models cannot create new action capabilities, cash, evidence or permission.

Model output variability is not a population distribution. Model confidence is not the true chance a political event occurs. Agreement between several generated personas does not create independent evidence.

### Repeated worlds without unbounded model calls

**Recommended strict-experiment mode, pending discussion:** during policy preparation, call the model on representative semantic/strategic states and freeze the responses as a versioned policy bundle. During final rollouts, rules consult that bundle within its reviewed validity range. Every unsupported state uses the **same predeclared deterministic rules/abstention fallback**, for all worlds. There are no additional model requests or policy expansion inside this experiment. Save unsupported-state coverage; improve the bundle and rerun as a new experiment if necessary.

Policy preparation may use pilot trajectories to discover important missing states, but those pilots are not silently included in the final reported world sample. Allocate budgets before the final run. A provider failure during preparation stops that task or produces an explicitly reviewed fallback bundle; it cannot make the last half of the final worlds follow a different policy. An interactive mode may call models while events unfold, but is separately versioned and cannot be pooled as if it sampled one frozen Monte Carlo policy. User preference between these modes is being discussed.

Cache semantic/policy judgments, not raw buy orders. “Positive verified update” may be reusable under the same policy context; “spend $200 now” cannot be replayed after the actor has spent its cash. Cache identity includes scenario/policy/model versions, question type, traits relevant to the decision and the permitted observation features. Sensitive actor-specific judgments are not shared with other actors.

Policy approximation is tested against a held-out set of uncompressed states. If bucketed observations cause material decision/outcome errors, refine or disable that approximation. A rules-only baseline must still run the same financial engine so we can measure whether model assistance adds value.

We cannot guarantee that the previous $5/1,500-Jev-decision envelope suffices before this policy workload is measured. Keep it a hard cap, display coverage/fallbacks, and never describe a largely fallback run as fully model-controlled.

## How personas interact

The MVP needs explicit interaction channels, not a chat room where every actor talks to all others.

| Channel | Actual mechanism | What it changes | What it does not imply |
|---|---|---|---|
| Public publication | Actor emits a message with topic, claim/source ID, timestamps and optional readable text | Reachable actors may later receive it | Everyone sees or believes it |
| Direct offer/private communication | Permitted sender addresses a known recipient; an offer can be accepted/declined | Recipient information, funded campaign commitments | Unrelated personas learn the private plan |
| Market transaction | Order fills against actual configured venue liquidity | Price/inventory, public execution data and owners' balances | A requested amount fully fills or the price is an external prophecy |
| Resource competition | Actors share a finite attention/time pool; projects have separate funded budgets | Who notices which campaign and opportunity | Every competing campaign causes a fixed percentage loss |
| Verification/moderation | Actor publishes a source-backed correction or applies an explicitly modeled local forum rule | Information quality, permitted exposure or perceived credibility | Global removal of information or automatic sell pressure |

### The missing link: campaign spend → messages → exposure → decisions

**User-selected mechanism:** use funded campaign deliveries and an explicit limited-attention feed. The specific recipe below is a proposed transparent baseline to review; its coefficients still need evidence or labelled assumptions. A fixed exposure schedule can remain an internal test fixture, but must not be presented as the product's campaign-response model.

1. A campaign offer specifies recipient, fee, deliverable count, topic/scope and due times. The creator's policy accepts/declines based on capacity, relevance and reputation constraints. The first fixture can use a declared rate card, not an invented inferred advertising market.
2. On acceptance, reserve the funded fee as an obligation; when the delivery occurs, transfer the fee and publish its message under the agreed payment rules. The existing financial plan determines whether payment is upfront or on delivery. Failed/cancelled delivery has explicit refund/nonpayment rules. No accepted obligation may exceed reserved funds.
3. The campaign generates only the promised messages. The creator has only its explicit graph recipients. Do not multiply an assumed follower count into imaginary cash-bearing buyers.
4. Every actor has declared per-channel visit times and a finite attention capacity, such as at most two public-social messages at a visit in the illustrative fixture. Paid and organic messages compete for the same relevant capacity. A primary-source research channel can have a separate capacity where that matches the actor's role.
5. Candidate messages must pass access, delivery-time, freshness and topic rules. Among candidates, a proposed simple selection weight is `source_affinity × topic_affinity × freshness_decay`. The factors/ranges are registered assumptions or estimates. Sample up to the actor's capacity without replacement; all-zero weights mean no delivery. Order/draw identities are recorded. Do not add engagement-based amplification without a separately defined model.
6. Preserve the claim origin. Repeated promotion can refresh attention up to a declared per-window cap; it cannot create additional independent evidence for the same claim. Deliveries update the actor's attention/interpretation; its policy still decides whether to buy, sell or ignore.
7. A competitor's published messages join eligible actors' candidate feeds. They can displace the project's messages **only where their audiences/channels overlap**. More spending can fail to reach new actors, saturate them or lose money; it never guarantees higher demand.

This creates an inspectable causal link: campaign budget → accepted deliverables → reachable competing messages → finite exposure → independent actor response → feasible trades. Actual response strengths need data or sensitivity ranges. We can test saturation, no-audience and irrelevant-audience cases before trusting any marketing-budget comparison. The model does not claim that this simple feed matches a real platform's recommendation algorithm.

The graph, participation and campaign rate-card assumptions can dominate the result, so the report must expose them. Fixed-plan A/B comparisons keep exogenous audience/visit schedules matched; the plans may legitimately produce different publications and exposures.

### Relationships have separate meanings

`A follows B` means A is eligible to receive B's public messages. It is directional. An exposure probability/schedule governs receipt; a delay governs when; trust affects interpretation after receipt. These are different parameters and cannot be compressed into one unexplained `strength` value.

`A pays B`, `A owns account C`, `A competes with B` and `A trusts source D` are different edge types with different effects. Use observed/user-provided relations when available; otherwise an explicitly assumed network recipe with a fixed seed. Do not assign links by position in the persona list. Avoid all-to-all coupling unless the scenario genuinely requires it.

Treat repeated copies of one claim as one underlying evidence origin. They can increase visibility/attention but cannot independently multiply the truth evidence. Keep public event truth, observable reports and each actor's belief as separate states.

### One transition, in a precise order

1. Advance clock and apply due external events and deliveries.
2. Give each eligible actor its permitted information snapshot from the start of the decision phase.
3. Update beliefs/attention and produce proposed actions. Actors do not see other same-phase unexecuted decisions.
4. Validate actions and execute market operations in a seeded order with current reserve/balance checks. Later fills may differ because earlier trades consumed depth. Record rejections/partial fills. For a constant-product fixture, do not add an artificial partial-fill rule unless explicit minimum-output/limit rules support it.
5. Commit ledger updates and queue their public effects for the next permitted observation phase.
6. Apply elapsed-time effects and schedule the next transition; check invariants.

Messages have positive delivery delays and per-actor action limits, preventing infinite same-time reply loops. Model/rules decisions are bounded proposals; execution order randomness is distinct from event randomness.

For comparisons, merely resetting the same pseudorandom seed is insufficient if different plans consume draws in different orders. Use named, stable draw identities such as `(world_id, external_event_id, occurrence_index)` for shared exogenous randomness, with separate actor/execution streams. Matched external events then remain matched even when one plan causes additional trades or messages. Reproducibility means the same frozen inputs and recorded model responses reproduce a result; it does not promise a remote model will regenerate identical answers on demand.

**Time resolution matters:** the earlier hourly-first/daily-later grid is an untested convenience. A daily decision interval cannot implement a two-hour reaction policy faithfully. Proposed engine contract: an event queue handles off-grid due actions/deliveries at recorded times; the displayed grid is only for summaries. If we implement a coarse-grid baseline first, it must reject/warn on incompatible delays and report the approximation. Do not claim exact intraday execution from a daily model.

## A small worked interaction

All values here are illustrative, not observations or forecasts.

**Starting state:** the founder has $10k: $1k launch expenses, $2k marketing, $4k LP allocation, $3k reserve. The LP operator can control the $4k allocation but does not receive another $4k. A retail actor has a separately initialized $250 balance; it is not the founder's money.

| Moment | What happens | Why this causes the next step |
|---|---|---|
| 1 | A specified public catalyst happens in this world | It creates a reportable event, not an automatic price increase |
| 2 | A relevant creator sees a verified report and publishes | A policy permits publication based on relevance/constraints; any paid campaign cost is accounted for |
| 3 | One retail actor receives the message; another does not | The observation graph, attention and delays differ |
| 4 | Model judgment says the story is relevant but uncertain | It informs a decision class; it is not “70% chance of profit” |
| 5 | Retail policy proposes a $25 entry from its $250 balance | Its own position cap and current constraints determine size |
| 6 | Venue validates the quote/slippage rules and executes if feasible | Pool reserves determine the actual tokens received and price impact; fees and cash transfer are recorded |
| 7 | A whale observes poor exit depth and abstains | Large hypothetical capital does not guarantee demand |
| 8 | Attention fades or a rival narrative becomes more attractive | A declared attention/competition mechanism changes later observations and choices |
| 9 | Some holders try to sell | Feasible fills depend on remaining depth; positions can remain unsold |
| 10 | Founder follows its reviewed sale/LP rules | Actual withdrawn cash can produce profit/loss; unsold or locked assets remain separate |

This is one path. Another world changes the catalyst, exposure, capital participation or policy response. Neither path earns a real-world probability merely by being narrated plausibly.

## Where the percentages come from

There are two levels of uncertainty:

- **Within one specified model:** sample event outcomes, exposure and individual variation using declared conditional distributions. If 240 of 1,000 completed equally weighted draws earn at least $20k, report 24% **under that model**, with Monte Carlo uncertainty.
- **Across plausible models/assumptions:** vary participation, outside capital, attention persistence, behavior and event probabilities. If the large-profit frequency ranges from 5% to 35%, show that disagreement and its drivers. Do not average to 20% unless there is a defensible weighting model.

Never calculate output probability by counting how many personas “feel bullish.” Never assign the happy-case frequency in advance and then generate matching stories. Narrative branches explain outcomes after simulation; they do not determine the result to satisfy a pitch.

Every world must have a funded source for purchases. With only $X of available outside cash, the model cannot invent unlimited cash proceeds for the founder. External entries/withdrawals must be explicit. Token price, token supply and liquidity do not themselves create dollars.

### How evidence can justify a parameter

1. Define the observable quantity and population, such as fee, entry delay or event-resolution frequency.
2. Obtain dated data with usage permission and an as-of boundary.
3. State the estimation method and biases, including missing failed tokens or unidentified wallet owners.
4. Fit on training data; retain uncertainty and dependencies.
5. Check held-out behavior/outcomes against a simple baseline.
6. Keep failures visible; revise a new model version, not the old forecast.

On-chain wallet actions do not directly reveal someone's motive, all their holdings or which address belongs to the creator. Creator cash-profit validation needs creator-level cash-flow evidence; token returns alone validate a different target. Before that evidence exists, the release can claim accounting correctness and inspectable conditional analysis, not calibrated creator-profit odds.

## The artifacts: why each exists and when it is created

An artifact is a versioned record another step needs or an audit/replay needs. It is not automatically a standalone JSON file. Use a small SQLite store plus private attachments/selected traces; do not create a new microservice or duplicated document for every step.

| ID | Record | Producer → consumer | Why save it / what breaks without it | Lifetime/invalidation |
|---|---|---|---|---|
| A1 | InputRevision | User input → compiler and later review | Preserve what was actually asked and constrained | Save on meaningful edits; edits create a new version |
| A2 | EvidenceSnapshot | Retrieval/extraction → compiler, actors' allowed reports, evaluator | Sources change; provenance and as-of replay otherwise disappear | Freeze per model version; respect retention/licensing; private sources stay private |
| A3 | ModelSpec + parameter registry | Compiler/review → cast, policies, runner | Makes assumptions, units, event probabilities and mechanics executable | Freeze after review; any material edit invalidates dependent policies/runs |
| A4 | ScenarioCast | Selector/instantiator → observation/policy/runner engines | Defines whose behavior is modeled and where their resources come from | Version with A3; preserve recipes and exclusions, not only biographies |
| A5 | PolicyBundle | Reviewed rules + bounded model work → runner | Repeated worlds need reproducible decisions and known approximation limits | Version by model/prompt/rules/features; invalidate when relevant assumptions change |
| A6 | RunManifest + usage journal | Controller → runner, replay, cost review | Connects a result to exact versions, seeds, modes and paid usage | Immutable identity; append status/usage events; distinguish cached/rules/live |
| A7 | RunData | Runner → checkpoints, analysis, selected explanations | Need to reconcile money, resume, and inspect actual causal paths | Keep summaries all worlds; bounded detailed traces; private and user-deletable |
| A8 | AnalysisResult | Aggregator → UI/report/export | Code-computed outcomes are the authoritative answer | Recompute from a run or keep immutable; prose is a derived view |
| A9 | EvaluationReport | Evaluator → development/release decisions | Distinguishes a working simulator from a useful predictor | Only create for a real defined evaluation; no empty report claiming validation |
| A10 | SafeExport / optional receipt package | Explicit export → recipient/NEAR verifier | Disclosure needs a controlled projection; commitments need exact bytes | Optional; private salt/canonical package retained locally for verification |

The schema files exist to reject incompatible/ambiguous records. They do not prove realism. A derived catalogue or HTML reader exists for people to inspect the same source data; it must not become a second independently editable source of behavior. A snapshot of a model response exists because live model outputs can change; seeds alone do not reproduce remote inference.

Do not persist every full prompt at every numeric action. Store model receipts for actual paid decisions in protected local data; retain the necessary observation/action IDs and ledger events for replay. Detailed trace selection must be deterministic or explicitly recorded. Discarding most traces cannot be advertised as retaining every causal detail of every world.

### What happens to the existing preparation artifacts

| Existing artifact | Purpose and next action |
|---|---|
| `personas.json` | Draft role library/fixture data; retain descriptions, replace unsupported generated numeric/link fields before meaningful runs |
| `persona.schema.json` | Shape checks for the draft; extend for template/actor/owner separation and parameter provenance after design review |
| `persona-catalog.md` | Derived human-readable inspection; label current placeholder parameters plainly |
| `build-persona-assets.py` | Reproducible preparation-fixture serializer; **not** the proposed production persona generator |
| `check-assets.py` | Structural integrity checks; retain without presenting them as behavioral or forecasting tests |
| `scenario.template.json` | Shows missing user inputs; becomes A1 draft, not a ready-to-run world |
| `run-config.json` | Illustrative budget/grid defaults; revise for event scheduling and scenario-specific cast before implementation |
| `result.template.json` | Output shape with null probabilities; becomes A8 after a real run |
| `receipt-test-vector.json` | Optional cross-language encoding test; keep, defer receipt implementation until core works |
| Earlier build specification/implementation plan | Rough component/reuse map; revise around this reviewed engine design before coding |
| HTML readers | Documentation navigation only; no simulation is running inside them |

## How this maps to code and MiroFish

Recommended core boundaries, all inside one Python package, not separate deployed services:

| Module | Sole authority | Why separated |
|---|---|---|
| `contracts` / `provenance` | Types, units, source/assumption status | Prevents every engine inventing its own meaning for a field |
| `compiler` | Brief/evidence → proposed ModelSpec | Model-assisted interpretation can change without changing accounting |
| `cast` | Templates → actors, owners, valid capabilities and networks | Population generation must be testable independently of prose |
| `observations` / `beliefs` | Visibility, delay, evidence identity and actor state | Prevents information leakage and omniscience |
| `policies` / `providers` | Strategy proposals, bounded model requests and usage | Model judgments remain separate from executable money actions |
| `scheduler` / `runner` | Event ordering, seeded worlds, checkpoints | Timing/replay must be consistent for every policy and venue |
| `venue` / `ledger` | Feasible fills, fees, cash/token ownership | All financial outcomes share one source of truth |
| `analysis` / `evaluation` | Outcome aggregation, comparisons and skill checks | Reports cannot silently change calculated results |
| `store` / adapters | Durable records and external API boundaries | Providers, UI and NEAR can be replaced without changing the kernel |

**MiroFish reuse:** preserve the approved AGPL-compatible direction. Its profiles/editor, graph display, simulation controls and report UI can be adapted later. In the inspected upstream `oasis_profile_generator.py`, entity context feeds either LLM-generated profiles or a rule fallback; the result is an OASIS profile, including descriptive persona and social fields. Twitter runner uses OASIS `LLMAction` through its environment. These are useful patterns for context, profiles and action orchestration; they do not supply our financial accounting or calibrated population generation.

Source pin: `7657031ac01184afe2cb220f5ee3545573b5e843`; see [profile generation](https://github.com/666ghj/MiroFish/blob/7657031ac01184afe2cb220f5ee3545573b5e843/backend/app/services/oasis_profile_generator.py) and [Twitter runner](https://github.com/666ghj/MiroFish/blob/7657031ac01184afe2cb220f5ee3545573b5e843/backend/scripts/run_twitter_simulation.py). Findings were checked against that pinned source, not inferred from marketing; the upstream application itself is no longer in this checkout.

Do not import the complete OASIS/Zep application into the numeric core merely to reuse a profile card. UI adaptation remains valuable, but core behavior must be proven without external model credentials, graph hosting or a wallet.

## What should happen before coding, then what to code first

Before coding, review the population/parameter model, policy boundaries, observation/interaction cycle, time resolution and outcome meaning in this document. The two confirmed A/A decisions do not automatically approve every new engineering default.

After the engine design is agreed, revise the implementation plan and build in this order:

1. Contracts/provenance + owner/account model + deterministic synthetic fixture. **Why first:** every other module needs consistent meanings and funded starting states.
2. Ledger + synthetic venue, then visibility/scheduler. **Why:** impossible money and future-information leakage invalidate all later results.
3. Template-to-cast builder + rule-policy baseline. **Why:** establish controllable differences in behavior without model/API noise.
4. Seeded world runner + outcome aggregation + paired comparisons. **Why:** prove reproducibility, cash reconciliation and meaningful uncertainty before narrative polish.
5. Bounded model policy assistance + held-out behavior checks. **Why:** measure its incremental value over the baseline using the same engine.
6. MiroFish UI integration, evidence adapters and real-venue validation. **Why:** inspect a real working core rather than build screens around undefined behavior.
7. NEAR receipt/provider integration after the relevant core interfaces stabilize. **Why:** useful external integration cannot repair an undefined simulator.

First deliverable after approval: a small deterministic financial/event experiment with a few inspectable actors, plus support for loading the larger pool—not a claim to have validated 80 personas. Expand to the scenario-specific 50–100 actor run only after mechanisms pass invariant/replay tests. Pitch and founder preparation remain deferred at the user's request.


## Academic evidence for this design

The 23 October literature review is available in the reader’s **Research evidence** tab and at `research/event-chain-decision-lab/preparation/engineering/research-foundations.md`. Its purpose is to map mechanisms to evidence and define validation tasks, not to approve untested behavior.

An [AMM agent simulation](https://arxiv.org/html/1911.03380v7) provides direct precedent for separately modeled traders, LPs, arbitrage and contract execution. [OASIS](https://arxiv.org/html/2411.11581v5) supports empirical testing of social propagation with small models, while documenting mismatches in cascade depth and human herding. The [grounded-persona study](https://arxiv.org/abs/2411.10109v3) supports meaningful observed inputs, not arbitrary profile parameters. These results motivate our architecture and tests; none validates the current 80 templates or creator-profit forecasts.
