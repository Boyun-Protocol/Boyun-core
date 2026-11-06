# Evidence-backed assumptions and outcomes

Applies to **every simulation type**: token launches, DeFi, governance, adoption,
business decisions and new domains. Required by the user on 2 November 2026.
This complements the research evidence contract
and [report depth standard](REPORT_DEPTH_STANDARD.md).

## The invariant

**Every material assumption and modeled consequence needs a specific real-life
reference or a documented reasonable cause. Trace input → mechanism → outcome.**

A reference supports a particular claim, not everything downstream. An official
event calendar supports a schedule, not a political result, attention spike or
token-price increase. A campaign payment supports a cost, not delivery or buyers.
Those transfers need separate evidence or explicit causal hypotheses. Apply this
to qualitative persona behavior and information rights as well as numbers.

“Reasonable cause” means a stated mechanism, applicable conditions, bounded
interpretation, a sensitivity comparison and a falsification test. It does not
mean a plausible-looking coefficient. Proposed assumptions are not user-approved
decisions. Preserve accepted policy thresholds and compare newly proposed arms
separately. Missing evidence can justify an explicitly labeled conditional stress
test; it cannot justify a real-world probability or an invented observed outcome.

## Evidence meanings must survive the model

| Evidence | Permitted interpretation | Not established automatically |
|---|---|---|
| Official schedule | An event was scheduled under that version | Actual occurrence, exact vote time, result or market impact |
| Official resolved vote/result | A defined event actually resolved | A prior forecast probability or another event's odds |
| Poll or public vote | Responses under its sampling/participation method | Representative support, event probability or token purchases |
| Prediction market | A dated quote for one resolution contract | Objective odds, independence or applicability to another event |
| Expert/statistical forecast | A dated conditional estimate | Calibration in this population, horizon or regime |
| Historical observations | Defined measurements in the sampled coverage | Unobserved wallets, intent, causal conversion or missing periods |
| Replayed price path | Moves at the resolution the simulation samples (e.g. hourly closes) | Intrahour wicks, on-chain oracle timing or historical liquidity at a rescaled price level |
| Jev action scores | Conditional typed behavioral judgments | Empirical human behavior or external-event probabilities |
| Simulated frequency | Occurrences in the recorded worlds | Population frequency or a calibrated market forecast |

For a prediction-market source retain contract/question, resolution rules, quote
time, liquidity, spread and fees. For polls retain population, sample/denominator,
sampling/weighting, question wording, fieldwork and nonresponse limitations. Expert
forecasts need model/method and relevant calibration history where available.
Reputation alone is not sufficient: review publisher authenticity, incentives,
coverage, definitions and contrary evidence. Do not average incompatible sources
into a fabricated consensus. Do not force outcomes to match predictions or votes.

## A reviewable register

Use a `simulation-evidence.v1` **sidecar**, not extra fields in strict world inputs.

- `as_of`: explicit timezone-aware knowledge cutoff. Source availability and capture
  must both precede it for a strict as-of claim. A later capture needs separate
  historical attestation or a labeled scenario assumption; do not backdate it.
- `target_sha256`: canonical content identity of the input package being reviewed.
- `sources`: stable ID, kind, publisher, locator, scope/units/population/window,
  measurement method, limitations, availability time, capture time and review state.
  Keep raw receipts/hashes privately when available. A review declaration is not
  cryptographic authentication or independent proof of the publisher's statement.
- `claims`: ID, `kind` (`input`, `mechanism`, `outcome`, `probability`), statement,
  evidence `status` and `depends_on` claim IDs. Sources bind through `source_ids`.
  Observed/model-judged claims need sources and a method; calculations need named
  inputs and a reproducible method. Assumptions need `rationale`, `sensitivity`
  and `falsification`. Unknown/disputed dependencies block downstream readiness.
- Probability claims also name `probability_kind` and `uncertainty`, including
  event definition, conditioning, denominator and window. Distinguish event odds,
  poll shares, market-implied quotes, model scores, simulation frequencies and
  assumed weights. A changed meaning requires a separately reviewed model, not
  relabeling a number. Unvalidated transfers remain explicit assumptions.
- `bindings`: map reviewed target IDs to supporting claim IDs. Numeric/boolean
  input targets use JSON pointers; semantic targets name behavioral assumptions,
  probability uses, mechanisms and reported outcomes. An outcome needs a causal
  mechanism ancestor. It inherits assumption/model dependence and unresolved inputs.

Keep the **required target inventory independent of the supplied bindings** so
omitting a binding does not silently remove a requirement. Inventory all material
qualitative rules too; automated numeric scanning cannot discover hidden assumptions
inside prose. Human review must establish applicability and completeness.

## Executable checks

```sh
decision-lab evidence audit --input evidence-register.json --targets required-targets.json
```

This is offline: no URLs are fetched, no keys are read and no model calls are made.
It rejects missing coverage, wrong claim kinds, changed package identity when a
caller supplies its expected hash, unresolved inputs, cycles, missing methods,
late/undated sources and unsupported probability-type transfers. Failures propagate
to dependent outcomes. Exit code 2 means the register is blocked or malformed.

The only passing status is **ready_for_conditional_simulation**;
`forecast_validated` remains false. Passing checks provenance structure, not truth,
plausibility, statistical validity, implementation completeness or paid-run approval.
An assumed result does not become empirical merely because its arithmetic is exact.

The campaign runner now requires a passing register **before creating output or
dispatching inference**. Its independent inventory includes every numeric/boolean
leaf, persona goals/roles, public campaign/event text, signal text, declared
assumptions and price/turnover/cash outcome definitions. It binds commitments,
activity stress and action-selection policy as well as the world package. Save
the register and audit in the run and repeat the audit during exact replay.
Use `campaign_evidence_context` and `campaign_evidence_targets` to prepare that
inventory; stress inputs must reflect the effective stress-transformed package.
Offline `campaign plan` still works without evidence but explicitly says it is not
execution-ready. Old saved runs remain replayable without inventing an audit for them.

Native `launch-lifecycle.v1` inference also requires a passing typed register,
including actor resources/goals, event and campaign text, regime and outcome
definitions. Exact replay rechecks the audit and package identity. Its conditional
pass does not claim historically fitted arrival, conversion or event-odds models.

The rule has a single authoring-policy source in `evidence_planning.py`. Ordinary
world authoring, staged scaffolds, profile-only persona batches, exported author
requests and MCP guidelines/prompts receive it, guarded by regression tests.
Profile-only batches must preserve frozen rules and their exact output schema;
qualify unsupported behavioral claims in permitted text rather than inventing
sources, changing balances or adding provenance fields.

Other existing runtimes
do **not** yet enforce this sidecar automatically; their author/report owners must
run the generic audit and apply the publication gates. This is not a claim of an
application-wide admission gate that has not been implemented.

## New-case and resume checklist

The [lifecycle execution and delivery guidelines](LIFECYCLE_SIMULATION_GUIDELINES.md)
generalize hourly state retention, funded commitments, actor privacy, matched-time
comparisons, incomplete-run labels and receipt-safe recovery across domains.

1. Read the case's accepted decisions, latest evidence register and capability
   limits before constructing or continuing a run. Recover recorded answers rather
   than asking the same questions or silently replacing the requested scope.
2. Preserve the **method**, not another case's numbers. Horizon, cadence, actor
   roster, policies, regimes and metric definitions belong to the current case.
   Token, DeFi and nonfinancial outputs need different supported measurements.
3. Inventory qualitative and quantitative assumptions; name the evidence or cause
   and its permitted use. Review dependencies and as-of timing before execution.
4. Re-review changed inputs, domain mechanics and probability transfers. A valid
   register for an old package does not authorize a changed world or new spending.
5. Retain the register/version and execution receipts with every report, chart and
   interactive view. Show missing evidence and unsupported mechanics explicitly.

For example, a token-launch case needs inventory, executable depth and campaign
response assumptions; a lending case needs debt, collateral/oracle and liquidation
rules; a governance case needs eligibility, voting weights, quorum and resolution;
an adoption case needs defined users, retention and incentive costs. These are
evidence questions, not a claim that every domain already has an execution adapter.

## Outcome review and publication

Every major chart or recommendation retains its claim IDs, input/run/checkpoint
references, world denominator, causal alternatives, limitations and falsification
conditions. Explain what is common, surprising or regime-dependent **relative to a
named benchmark**, not the author's intuition. Unknown external odds stay unknown.
Show stress tests separately from realistic calibration and compare actual outcomes
to frozen predictions only after their resolution. Keep all output formats on the
same evidence version. Domain support and accounting must still be implemented.

## MACRON application

`tools/audit_macron_evidence.py --output-dir <new-private-directory>` produces the
current linked register, independent inventory, machine audit and self-contained
HTML/Markdown explanation. It preserves the accepted plan while exposing schedule
as-of uncertainty, absent historical arrivals/resources, campaign conversion,
political outcome odds, MM latency and unintegrated 14-day branch settlement.
It is an evidence-gap report, **not another completed market simulation**. The
separate lifecycle run plan documents the subsequent
versioned fourteen-day estimate and the $2 full-matrix authorization; it does not
retroactively resolve the missing historical calibration in this older audit.
