# Parameter guide

This guide describes the implemented numeric engine. It does not assign real-world event odds or claim that synthetic actor rules are fitted to observed markets. Hover or focus a field's info button for a short explanation of its effect; Escape dismisses it. Full explanations stay in this guide and the Advanced reference.

The initial question, optional event and ticker are retained context. They do not
automatically change any numeric parameter or call a model. Changing the brief
marks existing results as previous until a new experiment completes.

## Visible controls

### Starting capital (`capital`)

Project cash available before any costs.

More capital leaves more unallocated cash when every other setting stays fixed. It does not create buyers or raise profit by itself: profit subtracts this starting capital. Less capital may make the launch, liquidity and scheduled campaign obligations unaffordable.

### Liquidity deposit (`liquidity`)

Cash placed in the initial trading pool.

More cash at the same token deposit raises the initial cash-per-token price and changes trade size relative to reserves. Less cash lowers that price and makes a fixed cash trade move the pool more. This deposit stays locked and is excluded from withdrawable cash; neither direction guarantees more profit.

### Launch cost (`launch-cost`)

One payment to the service account at launch.

More cost directly reduces project cash by the extra amount; less cost preserves cash. This setting does not improve launch quality, visibility or demand in the current engine. Nothing is paid under the do-not-launch plan.

### Campaign budget (`campaign`)

Fees for posts already in the campaign schedule.

Changing this value redistributes it across the existing scheduled posts, keeping their relative fees. More spending does not add posts, reach, attention or buyers; less spending does not remove posts. The lower-marketing comparison separately removes the latter half of the scheduled posts.

### Horizon (`horizon`)

Hours of simulated activity before results are measured.

A longer horizon includes more scheduled events and actor visits; a shorter one omits events after the cutoff. The follow-up cannot appear before hour 96. The form moves the liquidity lock to horizon + 1 if needed. No final token sale or liquidity withdrawal is forced, so more time need not mean more cash.

### Catalyst assumption (`catalyst`)

Assumed chance that hour-1 news confirms the catalyst.

Higher values make confirmation occur in more sampled worlds; lower values make the initial message a rumor more often. Cautious baseline actors require confirmation, while momentum actors can enter on rumors they actually see. This is your input assumption, not an estimated real-world probability.

### Positive follow-up (`followup`)

Assumed chance of favorable news at hour 96.

Higher values more often publish a separate confirmed follow-up claim. Lower values more often contradict the original catalyst; actors who saw and acted on it may then sell. The draw is separate from the initial catalyst draw. No follow-up is delivered if the horizon ends before hour 96 or news is disabled.

### Worlds (`world-count`)

Number of repeated outcomes under the same assumptions.

More worlds sample more event, feed and execution draws and take longer; fewer finish faster but give noisier frequencies. The cast remains fixed within an experiment. More repetitions reduce sampling noise, not incorrect assumptions or missing real-world behavior.

### Seed (`seed`)

An identifier for reproducible random draws.

Another seed can change the constructed cast, initial cash, news, feed delivery and execution order. A larger seed is not better or more optimistic. Reusing the seed, inputs, policies and engine version reproduces the experiment; paired comparisons reuse matched draw identities.

### Actor policy (`run-policy`)

Rules executed for eligible trading actors.

Baseline uses cautious or momentum Python rules. An imported bundle can change entry signals, reduce entry size or disable contradiction exits for covered templates; uncovered templates use its fallback. This selection starts no model calls and does not change actor funding, permissions or founder schedules.

### Worlds in this batch (`batch-worlds`)

How many additional worlds to complete before pausing.

A larger batch works longer before a checkpoint; a smaller batch pauses sooner. Resuming adds the next batch until the original world target is reached. It preserves the saved inputs and seed rather than starting a new experiment; the batch size does not change individual world rules.

### World (`world-select`)

Inspect one outcome from the completed experiment.

Selecting another world changes the cash bridge and recorded trace on screen. It does not rerun the engine or change the distribution. Only the first three worlds retain up to 500 trace events each; later worlds keep aggregates.

### Category (`people-category`)

Filter the displayed library or constructed cast.

Choosing a category hides other categories on screen. It does not add or remove simulated actors; edit cast_recipe.groups in advanced scenario JSON to change the actual population.

### Comparison experiment (`comparison-kind`)

Choose which controlled experiment to run.

Four launch plans compare launching now, reducing scheduled posts, delaying launch 24 hours, and not launching. Policy comparison swaps rules; sensitivity varies one selected assumption. All arms execute the engine with matched random draws, and none predicts the effect of an unimplemented action.

### Imported policy (`compare-policy`)

Bundle tested against the Python baseline.

Choosing a bundle changes rules only for the templates it covers, with its declared fallback for others. Actor cash and limits still bind. The reported differences are conditional on this scenario; a declared model name does not prove the model generated the bundle.

### Sensitivity assumption (`sensitivity-parameter`)

One numerical assumption varied between runs.

Catalyst and follow-up values change the sampled news states. A higher market fee retains more of each swap input in the pool and reduces quoted output. Higher max slippage allows more deterioration from the start-of-visit quote; lower values reject more moved-price proposals. It is an execution tolerance, not a direct price-impact limit.

### Sensitivity values (`sensitivity-values`)

Comma-separated values in basis points: 100 = 1%.

Larger or smaller values change the selected assumption, not every parameter at once. Event odds and slippage accept 0–10,000; market fees stop at 9,999. More values create more arms and take longer; the UI permits up to eight values and 200 total worlds.

### Completed experiment (`integrity-job`)

The exact saved result to bind with a commitment.

Selecting another experiment chooses a different artifact and its own commitment. It does not edit or rerun either result. Verification proves the opening matches those bytes, not that the assumptions, authorship or event probabilities are true.

### Model name (`model-name`)

A declaration in an exported request, not a model connection.

Changing the name changes the prepared request and its hash. It does not authenticate, select a local executable, start inference or require an API key in this UI. A separate provider workflow would need to support that model name.

### Policy fallback (`policy-fallback`)

Rules for trading templates missing from a bundle.

Baseline keeps the recipe-selected cautious or momentum behavior for uncovered templates. Abstain prevents those uncovered trading actors from proposing trades. Neither choice changes passive roles, campaign delivery, founder sales or liquidity schedules.

### Requested output tokens (`output-tokens`)

Declared maximum output for a separate model workflow.

A larger request allows a longer external response if the provider honors it and may cost more; a smaller request may truncate it. Preparing this request calls no model. Import checks any supplied token count against this value, but cannot authenticate usage or enforce a provider budget.

### Search people (`people-search`)

Find descriptions or actors without changing the simulation.

A broader or narrower search only changes the visible list. It does not alter cast membership, policy rules or funding.

### Signer account (`near-signer`)

Proposed NEAR testnet account for the unsigned descriptor.

Changing the account changes the proposed signer. The UI does not check ownership or existence, connect a wallet, sign a transaction, transfer funds or guarantee anonymity.

### Contract account (`near-contract`)

Proposed destination for a testnet receipt action.

Changing the account changes the unsigned descriptor destination. It does not deploy a contract or verify its interface. A result commitment does not publish the private scenario or encrypt data sent elsewhere.

### Dataset JSON (`evaluation-json`)

Dated forecasts and resolved binary outcomes to score.

More eligible holdout records give more evaluation observations, not automatically better predictions. Changing probabilities, outcomes or the time cutoff changes scores. Source timestamps are declarations and are not independently verified here. See the dataset reference below.

### Evaluation file (`evaluation-file`)

Load a local forecast JSON file into the editor.

Choosing another file replaces the editor contents only; evaluation starts when you press Evaluate forecasts. The loader accepts files smaller than 2 MB and performs no news or website retrieval.

### Request JSON (`import-request`)

The complete, unmodified prepared policy request.

Changing any bound content requires preparing a new request and matching response. A valid hash binds the supplied data; it does not prove that an external model received it. The request can contain private scenario information.

### Response JSON (`import-response`)

A supplied response bound to the prepared request hash.

Different valid rules can change future simulations after you select the imported policy. Import validates structure and bounded fields, not forecasting skill or model identity. Reported usage is unverified; null usage means unknown, not zero.

### Request file (`request-file`)

Load a prepared policy request from a local JSON file.

Choosing another file replaces Request JSON. It does not send the request to a provider. Retain this exact request to validate the corresponding response.

### Response file (`response-file`)

Load a supplied policy response from a local JSON file.

Choosing another file replaces Response JSON. It does not contact the declared model. The importer still requires the matching request and complete rules for the requested templates.

### Bundle ID (`bundle-id`)

A name for the imported rule artifact.

A different ID names a different bundle artifact and changes its hash, even with identical rules. It does not change the rules or authenticate their origin. Choose a recognizable name to keep comparisons readable.

### Trading template IDs (`template-ids`)

Exact outside trading templates for which to request rules.

More IDs request more rule entries and may require more output tokens in a separate model workflow. One template can be reused by several cast actors, so this is not an actor count. Only retail, event-trader and large-holder template IDs are eligible.

## Full scenario JSON

| Field | Meaning | Effect / limit |
| --- | --- | --- |
| `schema_version · mode · name` | Format, synthetic execution mode, and a descriptive label. | Keep synthetic-scenario.v1 and mode synthetic. Renaming does not change behavior; this engine does not accept an observed-market execution mode. |
| `capital_cents · launch_cost_cents · lp_cash_cents` | Starting project cash, launch payment, and initial pool cash, in integer cents. | More starting cash alone is not more profit. Costs reduce cash; pool cash changes reserves and stays locked. Capital must equal cast_recipe.founder_initial_cash_cents. |
| `lp_tokens · founder_tokens` | Initial pool deposit and total initial project token inventory, in integer units. | At fixed pool cash, more pool tokens lower the initial cash-per-token price. Pool allocation must not exceed founder inventory. Extra unsold tokens are excluded from cash profit. |
| `horizon_hours · lp_unlock_at_hour` | Result cutoff and declared liquidity unlock hour. | Longer horizons include more scheduled activity. Unlock must be strictly after the horizon: liquidity withdrawal is not implemented. The simple horizon form extends the lock if necessary. |
| `founder_vested_at_hour` | Earliest absolute hour at which founder sales may execute. | Later vesting can reject a scheduled early sale. Rejected sales are not retried automatically. This is not a gradual vesting schedule. |
| `founder_sales[].at_hour · token_units` | Sale time relative to launch, and token units offered. | Larger sales can withdraw more cash while moving price and reducing remaining inventory. Events beyond the horizon do not run. A delay-launch plan shifts sale times by 24 hours; vesting remains an absolute-hour check. |
| `campaign_budget_cents · campaigns[].fee_cents` | Approved spending ceiling and each scheduled post fee. | In advanced JSON, raising the ceiling alone does not change fees or delivery. The simple budget form rescales existing fees. Fees are paid on publication; the engine does not buy reach or convert spend directly to buyers. |
| `campaigns[].at_hour` | Post publication hour relative to launch. | Earlier or later posts change which visits can see them and which news state they repost. More entries add posts, while higher fees on the same entries do not. Postponed launches shift this schedule 24 hours. |
| `news_enabled · catalyst_probability_bps` | Enable fixed news events and set the chance of initial confirmation. | When enabled, hour 1 contains either confirmation or a rumor. Higher catalyst values increase confirmation frequency across worlds. A basis point is 0.01%; 6,500 means 65%. |
| `followup_positive_probability_bps` | Separate assumed chance for favorable news at absolute hour 96. | Favorable draws add a new confirmed follow-up origin; unfavorable draws contradict the initial catalyst. The draw is independent of initial confirmation. Horizons shorter than 96 hours omit it. |
| `competitor_messages[].at_hour` | Absolute publication hours of competing messages. | More competing messages can consume subscribed actors’ limited feed attention. Actors do not trade a second competitor asset in this fixture. Adding text or an identity does not create an external news integration. |
| `observation_window_hours` | Maximum age of messages still available for first feed delivery. | A larger window keeps old posts available longer; a smaller one can cause missed posts. It does not erase remembered claims: observed beliefs persist with no decay in this engine. Default: 48 hours. |
| `visit_interval_hours` | Hours between actor observation and decision batches, starting at hour 0. | Smaller intervals create more visits and computation; larger intervals may miss short-lived messages. At each visit an actor proposes at most one action. The whole batch quotes the same starting reserves before seeded execution. |
| `fee_bps` | Swap fee retained by the constant-product pool, from 0 to 9,999 bps. | Higher fees reduce effective swap input and quoted output while retaining more in the pool. The net effect on founder cash is not guaranteed. Example: 30 bps = 0.30%. |
| `max_slippage_bps` | Allowed deterioration from each proposal’s start-of-visit output quote. | Higher tolerance admits more fills after earlier trades move reserves; lower tolerance can reject them. It does not directly prevent a trade’s own price impact. This bound applies to participant proposals; scheduled founder sales use a one-cent minimum output. |
| `assumptions[].id · status · rationale` | Human-readable provenance declarations retained with results. | Clearer records improve interpretation and auditability; changing their text does not fit or validate numeric parameters. They must identify unmeasured behavior honestly. |

## Cast recipe JSON

| Field | Meaning | Effect / limit |
| --- | --- | --- |
| `founder_count · founder_initial_cash_cents` | One founder and the project’s starting cash. | founder_count is fixed to 1. Cash must equal scenario capital; the simple capital control synchronizes both fields. The delegated LP shares the same project owner and adds no new cash. |
| `two_executable_markets` | Whether arbitrage roles are excluded for lack of two venues. | False excludes arbitrage actors. True only retains observation roles: it does not implement a second market, routing or arbitrage trading. |
| `role_templates.project-founder · project-lp` | Reviewed description IDs reserved for the project roles. | Changing them changes the chosen biography in the matching launch-team or liquidity category. It does not change scheduled founder behavior or implement extra LP actions. |
| `groups.{category}.count` | Number of individual actors requested per category. | More retail, event-trader or large-holder actors add separately funded possible traders. Other categories remain passive or scheduled. Counts include founder/LP slots and cannot be interpreted as a representative market population. |
| `groups.{category}.cash_range_cents` | Inclusive lower and upper bounds for seeded initial actor cash. | Higher bounds increase available outside cash; lower bounds reduce it. Each actor draws cash once when the cast is built. Greater cash does not force a purchase, and weight remains one actor per instance. |
| `groups.{category}.position_limit_cents` | Maximum remaining cash cost basis allowed for token acquisition. | A higher cap permits larger total acquisition cost basis; a lower cap restricts it. Partial sales reduce tracked cost basis proportionally, allowing capacity to be reused. This is not a limit on marked-to-market value or lifetime turnover. |
| `groups.{category}.entry_fraction_bps` | Maximum fraction of current cash for one entry. | Higher values allow larger eligible purchases up to the remaining position limit; zero prevents entry. An explicit policy can only reduce this fraction. A funded actor still needs an eligible observed claim. |
| `groups.{category}.attention_capacity` | Maximum eligible unseen messages delivered in one visit. | More capacity can expose the actor to more subscribed claims or contradictions; zero prevents trading decisions in the current rules. It is not follower count or guaranteed engagement. Reposts of the same origin do not create fresh purchase opportunities. |
| `groups.{category}.strategy_choices` | Seeded choice of cautious or momentum for trading categories. | Cautious enters on confirmation; momentum also accepts rumors. Nontrading categories accept observe only. Repeating a choice changes its sampling weight. These are fixed rule families, not independently reasoning agents. |
| `groups.{category}.subscription_choices` | Seeded choice among lists of source names. | Adding news, creator or competitor changes which sources an actor can receive. Each list is sampled as one choice; repeating it changes its weight. Subscriptions do not fetch an external platform or establish a social relationship. |

## Imported policy rules

| Field | Meaning | Effect / limit |
| --- | --- | --- |
| `policies[].template_id` | Trading template to which the rule applies. | One template rule can bind several actors. Descriptions and model names do not override cash, permissions, source subscriptions or attention. |
| `entry_signal` | confirmed, rumor_or_confirmed, or none. | Confirmed requires personally observed confirmation. Rumor-or-confirmed also permits rumors. None disables new entries; contradiction exits can remain enabled. |
| `entry_fraction_bps` | Policy’s cap on the per-entry cash fraction. | The effective fraction is the smaller of policy and recipe fractions; raising it above the recipe adds no purchasing capacity. |
| `exit_on_contradiction` | Whether to sell a holding after relevant observed contradiction. | True proposes a full-token sale when an origin previously acted on is contradicted. False disables this exit; it does not prevent scheduled founder sales. |
| `rationale · assumptions` | Explanations retained with the bounded rule. | Changing these strings changes provenance, not execution. They are not executable instructions or evidence of calibration. |

## Forecast evaluation JSON

| Field | Meaning | Effect / limit |
| --- | --- | --- |
| `source_mode · split_at` | Declared synthetic/observed source mode and UTC time cutoff. | A later cutoff may admit more resolved training records and leave fewer future holdout forecasts. Observed is a declaration, not authentication; the sample is synthetic. |
| `sources[].id · url · observed_at` | Declared source references and their available-at timestamps. | Forecast evidence must be dated no later than issuance. Outcome evidence must be dated between scheduled and recorded resolution. URLs are not fetched or content-verified. |
| `forecasts[].probability · outcome` | A probability in [0,1] and a resolved outcome of 0 or 1. | Confident wrong predictions worsen Brier score and log loss more. Altering outcomes changes the target rather than improving the forecaster. Brier uses raw probabilities; log loss clips at 10⁻¹⁵. |
| `issued_at · resolves_at · resolved_at` | Issuance, scheduled resolution and recorded resolution times. | Training needs resolution by the cutoff; holdout needs issuance at or after it. Earlier pending forecasts are excluded. A forecast must precede scheduled resolution, and recorded resolution cannot precede it. |
| `id · question · source_ids · outcome_source_ids` | Unique forecast identity, question and evidence references. | These link a supplied prediction to its declared evidence and outcome. More records can change score averages; repeated records would distort weighting. Forecast IDs must be unique. |

## What “up” and “down” mean

For cost and cash parameters the direct accounting effect is explicit. For prices, exposure, event odds and actor behavior, a directional outcome such as “more spending means more profit” is not guaranteed. Comparisons keep named random draws matched so changed outcomes can be inspected under the same synthetic setup.

A higher world count reduces Monte Carlo sampling noise conditional on the setup. It does not repair model error, validate a persona biography, or turn an assumed event probability into an empirical estimate.

## Implementation sources

- `engine/src/decision_lab/simulation.py`: event times, schedules, cash accounting, fixed news structure and liquidity restriction.
- `engine/src/decision_lab/actors.py`: recipe validation, seeded cast construction, individual funding and supported role capabilities.
- `engine/src/decision_lab/policies.py`: finite feed delivery, persistent observations, signal rules, position cost basis and bounded sizing.
- `engine/src/decision_lab/policy_preparation.py`: request/export/import semantics and unverified model declarations.
- `engine/src/decision_lab/evaluation.py`: chronological eligibility and forecast scoring.
- `engine/src/decision_lab/web/app.js`: dollar/percentage conversions and simple-form schedule rescaling.
