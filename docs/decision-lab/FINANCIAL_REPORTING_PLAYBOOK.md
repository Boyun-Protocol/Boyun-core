# Stateful financial simulation reporting playbook

This playbook turns a stateful simulation into a readable decision package and an auditable technical record. It generalizes the MACRON example; adapt sections to the domain and available evidence. It does not require a particular page count, chart count, model provider, or four-case scenario matrix.

## Package and audience

Deliver five human-readable documents when the project has both decision and technical stakeholders:

1. **World Creation** explains the experiment before outcomes: real-world evidence, actors, starting state, rules, assumptions, interventions, and comparison design.
2. **Bear Case** explains the adverse regime and its worlds, decision paths, events, outcomes, and implications.
3. **Bull Case** explains the favorable regime on the same terms, including where it fails or behaves unexpectedly.
4. **Technical Report** documents how the run was produced, verified, limited, and paid for. This is for analysts, engineers, model reviewers, and anyone reproducing the work.
5. **User Q&A Record** preserves the user's original questions and decisions that materially shaped the scenario. Separate direct quotations from agent summaries; include dates, links to resulting inputs, and unresolved answers. Do not silently rewrite a user's choice as a model conclusion.

A compact executive decision can lead the Bear and Bull documents. A combined HTML index may link all five. Keep source data, receipts, assumptions, evidence register, and reproducible chart data in a separate machine-readable appendix. The reports share the same frozen run identity and as-of date. Place a linked contents page at the beginning of each substantial PDF, ordinarily page 2 after a cover.

For a small project, combine the technical report and Q&A record as appendices only if their provenance remains easy to audit. Do not omit either when model calls, cost, stopping conditions, or user choices materially affect interpretation.

## Step-by-step workflow

### 1. Freeze the question and interview record

Create a brief with the decision question, intended reader, asset/domain, forecast horizon, baseline, risk tolerance, desired actions, budget, and known constraints. Ask for missing high-impact choices before spending inference budget. Save the Q&A as an append-only record: timestamp, speaker, exact question/answer or clearly marked summary, decision made, affected input IDs, and status (resolved, assumption, deferred, or unanswered). Do not convert user preferences into observed facts.

### 2. Build a dated evidence pack

Collect primary sources for each material real-world input (market prices, token supply, user/adoption measures, event dates, partner terms, regulations, and comparable projects where relevant). Record source URL or local artifact, publisher, observation date, retrieval date, unit, transformation, and uncertainty. Use a market-data snapshot for the simulation cutoff; do not mix future revisions into the same run. Prefer comparisons that answer a clear reader question, such as where an assumed launch budget sits against comparable launches, or how simulated users compare with a dated user cohort. Define inclusion rules and denominator. If no reliable peer set exists, say “no comparable benchmark available” and explain why; do not insert an arbitrary average.

Map each real-world observation to the model field it informs. Mark every transfer from an observed entity or event to a simulated actor as an assumption unless independently validated. Keep a claim-to-source register so each numeric assertion can be traced to its source or exact run state.

### 3. Specify actors, world mechanics, and hypotheses

For every actor type, define goals, resources, information, decision moments, available actions, constraints, and settlement effects. Describe real-world counterparties only to the extent supported by sources. Capture negotiations, price conditions, commitment length, and exit clauses as simulated only when the input or event log actually contains them. Missing partner behavior is an explicit limitation, not a narrative gap to fill.

Write a causal map from event or information → actor choice → attempted action → execution/settlement → changed state → downstream response. Identify what the experiment manipulates and what it holds constant. Name plausible competing explanations and the observations that could distinguish them. State the no-action baseline and whether it was actually run.

### 4. Choose the run design and state the inference boundary

Document provider/model/version, prompt or policy version, seed, number and dependence of worlds, run horizon, event cadence, retries, caching, stop conditions, missing calls, unknown receipts, and execution simulator. Keep native inference, replay, offline reference, stress, and any imputed or surrogate results visibly distinct.

A smaller pilot (for example, 20% of a full matrix) can diagnose feasibility and reveal detailed paths for the sampled subset. It does not establish the other 80% of outcomes. To estimate the rest, define a justified sampling design or validated surrogate, identify training and validation splits, quantify prediction error, and label generated results as modeled estimates rather than observed runs. Never copy a pilot path into unrun cells and present it as if simulated. Preserve the full intended denominator, the completed denominator, and reasons for missingness.

Report cost from provider receipts where available: confirmed requests, input/output tokens and tariff units, provider charge, retries, failed or unknown dispatches, and cap/reservation state. Separate provider-reported charges from list-price estimates and local planning estimates. Include the currency, tariff date, and formula. A call count without cost units is incomplete; a cost estimate without its source or token assumption is not an invoice.

### 5. Analyze the full decision path, not only endpoints

State the actual recorded duration and confirmed model-call count. At the last
saved checkpoint, show whether the project is still visibly active, citing the
relevant recent activity and window; a recording cutoff is not project closure.
When activity or termination cannot be determined, label it unknown. Focus the
reader-facing story on the observed data rather than a history of changed targets.

For each world, retain an event and action ledger with event time, information then available, actors eligible to act, options, model scores or probabilities, sampled choice, attempted action, fill/rejection, settlement, and resulting state. Preserve the distinction between consideration, choice, attempt, execution, and outcome. Aggregate repeated choices by actor family and time window, reporting numerator, denominator, and missingness. Discuss whether behavior appears hesitant, concentrated, split, or highly active only as a measured pattern; do not infer mental states from counts alone.

When choice scores exist, show them separately from realized choices and fills. If “odds” are uncalibrated model weights, label them as scores/weights rather than real-world probabilities. Report exact sample frequencies (for example, 7 of 20 worlds) and dependence; do not turn them into calibrated odds without out-of-sample evaluation against resolved outcomes.

### 6. Build the five documents

#### World Creation

Use this sequence, adapting it where the experiment needs a different order:

1. Executive description and experiment identity.
2. Table of contents.
3. Real-world setup and dated evidence.
4. Actor roster, objectives, resources, information, and supported relationships.
5. Rules, action/settlement contracts, schedule, and state transitions.
6. Assumptions and causal transfers, each with source, rationale, sensitivity, and falsifier.
7. World matrix and meaningful names/codes. Explain every code in plain language. Example: `B-P5U10` can mean Bear regime, a $5,000 token-position budget, and $10,000 launch/campaign spend; add what those amounts fund, what is protected, and what remains uncommitted. Prefer an evocative short name plus a transparent code, e.g. **Quiet Reserve (B-P5U10)**.
8. Baseline, comparison design, run coverage, and known unsupported mechanisms.

#### Bear Case and Bull Case

Each document states what its regime means in this experiment, why the assumptions were chosen, and what evidence supports them. Include:

1. Decision-oriented opening with the key finding and limits.
2. Table of contents.
3. Regime definition, worlds, concise memorable names, code legend, and true world/sample counts.
4. Full timeline from initial state to observed horizon. Use a Gantt-like event lane by day/hour and actor/event family; merge quiet periods only when the merged span is explicit. Mark data gaps and incomplete final periods. Each lane item links to the detailed event/action ledger.
5. One consistent per-world time-series panel for simulated token price, executed trades, and executed volume where the engine records those measures. Label time zone, units, sampling interval, partial buckets, and missing periods. Keep separate axes or small multiples where mixed scales would hide variation. Do not call attempted trades executed trades.
6. Per-world actor-choice, crowd-response, execution and accounting analysis. Explain options considered, scores/weights if available, choices, attempts, fills/rejections, and downstream state. Include distributions by actor family and event window; note when the effective independent sample is worlds rather than thousands of correlated decisions.
7. Partner/creator response only where those actors and choices exist in the logs. Otherwise label the question unsupported and propose a measurable future experiment.
8. Comparison section with aligned-time small multiples or one attribute per multi-world chart: price, executed trade count, volume, and other decision-relevant state. Show every world with legible series and distinguish scenarios by stable color/line style. State which arms are matched and what changed.
9. Risks, alternative explanations, failed paths, and decision implications.
10. Sources and exact run-data references at first use and in a compact source note.

Do not add a bare “References” section for internal editorial inspiration or formatting influences. The reader-facing sources should substantiate claims about the world: real-world events, prices, asset supply, users, counterparties, or methods required to evaluate a specific result. Internal writing references belong in the skill/playbook, not the financial report.

#### Technical Report

The technical report should make the experiment reproducible and explain what the system did:

- Run identity, dates, code/configuration and data hashes, provider/model, version, region, and execution environment.
- Full pipeline and tool calls: which command or API step creates inputs, dispatches calls, records receipts, replays checkpoints, analyzes results, and renders documents. Include safe, reproducible commands with paths generalized or parameterized; state which steps spend money or mutate external state.
- Planned matrix versus completed matrix, worlds, actors, decision rounds, and inference calls. Distinguish requested, confirmed, failed, unknown, retried, replayed, and cached calls. Give cost and units with source and tariff date.
- Runtime and stopping explanation: exact blocker, error/limit/guardrail, first and last successful timestamp, affected paths, recovery attempts, and what remains unknown. Do not attribute a stop to Jev unless receipts or logs identify Jev as the cause. Separate provider throttling, budget guards, orchestration failures, simulator termination, and expected terminal conditions.
- Model and tool contracts, prompt/policy hashes, state/checkpoint integrity, replay verification, data lineage, and known nondeterminism.
- Choice generation and aggregation: available options, score semantics, sampling method, eligibility, denominator, action execution, settlement, and rejected-action rules.
- Validation performed, coverage, unsupported mechanisms, safety or privacy handling, and reproduction recipe.

The technical report explains mechanics and limits; it does not claim validity from replayability alone. Include raw receipts or link to access-controlled artifacts without exposing secrets.

#### User Q&A Record

Preserve the original conversation portions that shaped the experiment, with question ID, timestamp, exact user language where possible, agent response/clarification, user selection/correction, resulting config field, and current disposition. Keep instructions and facts distinct. Link each decision to the report assumption or run input it changed. Mark assistant proposals that the user did not accept. Do not imply user approval for a later action from an earlier unrelated answer.

### 7. Design charts and pages for reading

A chart earns space by answering a question. Give it a descriptive headline that states the finding, a clear unit and time window, visible denominator, source, and a short interpretation connecting evidence to a decision. Add alternative explanations when the plot does not isolate a cause.

Use a consistent design system with a restrained background palette, high-contrast text, and semantic colors that remain distinguishable in print and color-vision differences. Use a readable, available font family with clear weight hierarchy; embed fonts in exported PDFs where licensing permits. Prefer off-white/light-tint page backgrounds for long reports unless dark mode is an intentional, tested deliverable. Avoid colored bars that imply meaning without a legend. Check grayscale and contrast. Keep enough spacing between title, chart, legend, caption, source and body text; do not let chart labels or sources collide or orphan onto another page.

For timeline/Gantt views, put time horizontally and actor/event lanes vertically. Use a shared time scale, label quiet spans, show duration versus point events distinctly, and distinguish planned events from observed events. Do not show events outside the run horizon as if observed. For multi-world comparison, keep axes and color assignments consistent, plot each world legibly, and use direct labels or a compact legend. Avoid stacking unlike units or allowing one large series to flatten the rest.

A first-use number needs context: source and date for external values; unit, denominator and comparison for simulated values; or an explicit “assumption” label. Benchmarks require a disclosed sample, inclusion criteria, time window and comparable unit. If those are unavailable, state that no defensible benchmark exists. Do not place an unexplained number in a table or figure simply because the run emitted it.

### 8. Reconcile and validate before delivery

Reconcile every headline figure to frozen inputs and outputs. Check that cash, fees, assets, inventory, and claims use consistent signs and units. Check all compared paths at the same timestamps; never use a later endpoint to make an earlier arm look worse. Preserve missing values rather than replacing them with zero. Ensure report data and figures share the same run/version hashes.

Render every PDF/HTML at its intended screen and print sizes. Inspect contents, page breaks, font embedding, background/foreground contrast, chart sizing, label overlap, legends, source notes, and mobile horizontal overflow. Review chart datasets independently of their renderer. Confirm links, figure references, and user Q&A IDs resolve. State remaining defects and unsupported analysis plainly.

## MACRON example: how the guidance changes the reader package

The MACRON lifecycle matrix is a worked example of the division of responsibilities, not a template for assuming every project has the same cast or mechanisms:

- World Creation defines founder capital, protected reserve, position budget, launch spend, actor roles, execution rules and the distinction between scenario assumptions and observed market facts. Names pair an intuitive title with an explicit budget code.
- Bear and Bull each explain their context labels, six funding designs, event schedule, choice/action/settlement sequence, prices/trades/volume over time, event timeline, actor-family decisions, crowd response, accounting, and aligned comparisons across the six worlds.
- The technical report explains the 24-path native matrix, actual Jev/provider receipts and cost, replay and checkpoint validation, incomplete native duration, offline comparison arms, and exact stop reasons by path. It must identify separately whether a path stopped at a spend cap, call budget, unknown dispatch, or provider/runtime error.
- The Q&A record retains the user's choices about six-hour total volume for funding/exit rules, matched crash response comparisons, $2 total inference budget, and a 14-day target horizon. Those choices constrain the experiment; they do not establish that the target horizon completed.
- A reduced pilot can be used to test the run path and inspect a subset. The unrun remainder must stay marked unobserved unless a separately validated model estimates it.

MACRON-specific constants, prices, actors and filenames are examples only. Use the actual run's frozen evidence and user decisions for another case.

## NEAR lending example: a second, different case

The NEAR lending casebook (`docs/decision-lab/cases/near-lending/report-2026-11-05/`) applies the same package to a collateralized-lending launch. It shows where the package bends:

- **Regimes follow what was run.** Five worlds replay a real choppy window and one a real bear window. The second document is therefore a **Choppy Case**, and the **Bull Case** is a short document saying no bull world was run and how to run one. The choppy window is not relabeled as bullish.
- **World codes name every changed input**, e.g. `B-P100-R8-L`: bear path, $100K per-borrower cap, 8%-base rate curve, Laya. The World Creation comparison table flags the one comparison that changed two inputs at once.
- **The actor model is an experimental factor.** Two worlds repeat Laya worlds on Jev. They reversed every behavioral result, so the reports label each finding mechanical (set by rules, caps and prices) or behavioral (set by model choices) and rely only on the mechanical ones.
- **Numbers come from a data module.** `tools/lending_casebook_data.py` computes interest from receipts plus receivables, the protocol share separately, liquidation days from receipts, and drawdowns from the hourly closes the oracle used. Writing the text from these values corrected two hand-written errors: understated interest, and a −40% wick the ledger never saw.

See the [lending runner guide](LENDING_CASE_RUNNER.md) for how the worlds were produced.

## Tooling reference

For the current MACRON lifecycle artifacts, the local report builder is documented in `tools/README.md`. The typical sequence is:

1. Run or resume the accepted matrix using the lifecycle runner and preserve provider receipts.
2. Freeze source bundle and verify checkpoint/result identity; do not spend calls just to restyle reports.
3. Run `tools/build_financial_casebook.py` into a new output directory. Use `--verify-replay` when exact replay is needed and affordable in time; replay makes no inference calls.
4. Run `python tools/validate_financial_report_package.py <package-directory>` to check document and exhibit structure. This is not a visual or factual audit.
5. Inspect structured data under `DATA/`, figure files under `FIGURES/`, and all PDF/HTML output. Check the technical report and Q&A record against runner logs, receipts, interview files and model configuration. Regenerate after edits from the frozen source bundle. The builder cannot infer a provider stop reason that is absent from those records.

For the NEAR lending case, `tools/build_lending_casebook.py --output <new-directory>` builds the six-document package from the frozen worlds in `engine/output/`. It reuses the MACRON renderer through optional `project`, `footer_note`, `cover_note`, `cast_panel` and `x_unit` fields, so MACRON output is unchanged. Validate it with the same package validator, then inspect the HTML in a browser as well as the PDFs.

These commands and paths are project-specific. Other simulations should use the closest supported runner, receipt store, replay/checkpoint validator and renderer rather than pretending this builder supports arbitrary data.
