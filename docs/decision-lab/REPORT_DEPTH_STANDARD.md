# Decision-grade report depth standard

Status: product requirement and publication checklist, 2 November 2026. This is the
target for Boyun outputs, not a claim that the current product outperforms MiroFish
in a measured benchmark. No new upstream-product comparison was performed here.

## Stateful financial reports: package override

For stateful Boyun financial simulations, use the three-document package **World
Creation**, **Bear Case**, and **Bull Case**, each with a table of contents on
page 1 or 2. This supersedes the fixed twelve-section single-report layout below
only as a packaging/layout choice. Preserve the standard's evidence labels,
provenance, statistical and accounting minimums, insight contract, edge-case
coverage, and publication gates across the three documents. See the
financial-report skill
for how to allocate the analysis. Static estimator reports retain their existing
layout unless the user requests the stateful financial package.

## Product promise

A report must answer: **what happened, why that explanation is supported, who
benefits or bears losses, what can fail, what is still unknown, and what evidence
would change the decision**. More prose, charts or model calls alone are not depth.
The short summary stays short; supporting analysis is progressively disclosed.

## Main report: twelve sections

| Section | Required content | Normal budget |
|---|---|---|
| 1. Decision brief | Question, plan, baseline, at most four quantified findings and decision boundaries | 1–2 pages |
| 2. Evidence and assumptions | Sources, as-of cutoff, missing data, input provenance, observed/simulated/assumed labels | 1–2 pages |
| 3. Plan and resources | Committed versus optional actions, costs, authority, timing, delivery and execution receipts | 1–2 pages |
| 4. Actors and information | Distinct goals, resources, public/private knowledge, memory and communication | 1–2 pages |
| 5. Timeline and turning points | State changes, attempted versus filled actions, delivery versus reaction, event-time alignment | 2–3 pages |
| 6. Outcomes and accounting | Founder, marketing, consolidated controlled cash, inventory, LP claims and counterparties | 2 pages |
| 7. Statistical results | World-level distributions, sample sizes, uncertainty, failures, missingness and dependencies | 2 pages |
| 8. Drivers and counterfactuals | Which inputs changed, matched arms, ablations, alternative explanations and confounding | 1–2 pages |
| 9. Edge cases and coverage | Favorable/adverse/composed shocks, trigger definitions, tested versus untested branches | 2 pages |
| 10. Expected and surprising | Explicit reference, difference, potential mechanism and falsification check | 1 page |
| 11. Decision options | Feasible alternatives, tradeoffs, risk triggers, unresolved user choices; no invented optimum | 1–2 pages |
| 12. Limitations and follow-up | Unsupported mechanisms, claim register, reproduction recipe, outcome resolution | 1–2 pages |

These are content budgets, not mandatory padding. Combine pages when data is sparse.
Use 150–250 words of interpretation for each major figure when warranted, with a
clear finding, denominator, mechanism/hypothesis distinction and decision relevance.
Do not shrink type or add unsupported analysis to satisfy a page count.

## Insight contract

Each important finding has: a stable claim ID; a numerical observation and unit;
the relevant world/sample denominator; comparison or reference; supported mechanism
versus competing hypotheses; implication for the decision; evidence that could
falsify it; and links to exact input/run/checkpoint sources. Use the labels:

- **Recorded simulation fact:** reconstructed from verified states or settlements.
- **Empirical observation:** measured outside the simulation, with source and date.
- **Assumption/policy intervention:** chosen scenario input, including activity buffs.
- **Association:** co-occurrence or grouped difference; not proof of a cause.
- **Hypothesis:** plausible mechanism not isolated by an experiment.
- **Unsupported:** cannot currently be inferred or executed; never substitute zero.

An LLM's free-text rationale is not causal evidence. A typed choice model may not
return a rationale at all; the report must not invent an explanation in its voice.

## Statistical minimums

1. Count independent sampling units correctly. Four simulated worlds with 2,048
   actor calls are four worlds, not 2,048 independent market experiments. Shared
   seeds, common initial conditions and temporal dependence must be disclosed.
2. With four worlds, show all worlds, observed range and descriptive median. Do
   not manufacture p95/p99, CVaR, smooth density/fan charts or strong probability
   claims. Larger samples still require appropriate dependence assumptions and
   calibration before claiming real-world odds.
3. Keep provider choice scores, assumed event odds, realized sampled frequencies
   and empirically estimated frequencies separate. Multipliers on normalized action
   weights are not guaranteed multipliers on realized volume or trade frequency.
4. Preserve natural denominators: three of four worlds, not a visually authoritative
   75 of 100 population display. Zero observations of a failure do not establish a
   zero true failure rate. No trade attempts means execution rejection rate unknown.
5. Report magnitude as well as counts: cash effects, inventory, drawdown, minimum
   sampled liquidity, fees, execution rejection rate, turnover concentration and
   campaign delivery/failure. Cash/token fees retain their original units.
6. Define windows and formulas. Sampled barrier drawdown can miss intrabarrier
   extrema. MC/FDV are not realizable liquidity; turnover is not new capital or ROI.
7. For valid matched experiments, report per-seed differences and what changed.
   Earlier BULL/BEAR arms changed policy, sampling and ticket caps together. The
   later lifecycle matrix keeps the artificial 4x stress separate and changes a
   qualitative risk-appetite context between native regimes. Neither design
   identifies an empirical market-regime effect or campaign causality.
8. Label exploratory analysis and post-hoc thresholds. Uncertainty must name its
   source: seed sampling, behavioral model, inputs, execution or missing mechanisms.
   More seeds reduce Monte Carlo variation, not structural model error.

## Accounting minimums

Show each actor separately and the declared economic group. Include prepaid costs
before the first action; do not hide them by starting the chart after payment.
Reconcile sources and uses of cash/tokens. Founder cash change, consolidated
founder-plus-marketing cash change, marked inventory and recoverable LP claims are
different metrics. If inventory/LP recovery is unsupported, total economic profit
stays unavailable. Campaign spend divided into subsequent volume is not causal ROI.

## Edge-case matrix

Every applicable branch names trigger, observation window, information recipient,
available response, funding/authority, execution failure and recovery. Coverage is
**observed in run**, **tested mechanism**, **planned experiment** or **unsupported**.

Required candidates include: nobody trades after publication; late arrivals;
selloff despite high volume; order rejection during exit; shallow liquidity;
budget exhaustion; inventory exhaustion; delayed/failed KOL delivery; correlated
partner failure; expired narrative/campaign; overlapping triggers; stale information;
private/public asymmetry; no recovery; unexpected revival; migration failure;
venue/chain outage; LP withdrawal; MEV; cancellation/refund and combined shocks.
Only apply branches supported by the domain and implemented action contracts.

An unrun edge case is a research question, not a simulated event. Show unknown
occurrence odds rather than inventing percentages to complete a diagram.

## Publication gates

- Apply [the shared assumption/outcome evidence standard](SIMULATION_EVIDENCE_STANDARD.md)
  across every domain: source or justify causal transfers, inherit upstream uncertainty,
  and do not treat polls, votes, market quotes or model scores as interchangeable odds.
- Every numeric claim regenerates from versioned data and has units/denominators.
- Exact replay succeeds; attempted, completed, failed and rejected cases reconcile.
- Executed-plan reports verify actual committed payments and delivered exposure.
- Major charts have interpretation underneath and retain flat/negative results.
- Small samples, unsupported fields, policy overrides and confounding are visible.
- No economic-profit claim without the required consolidated accounting.
- No causal campaign or regime claim without a suitable matched comparison.
- Every edge case has a coverage state, not just an evocative label.
- PDF, PPTX, interactive HTML and data files share the same frozen result version.
- Private analyst artifacts are distinguished from access-controlled actor views.

## MiroFish comparison discipline

Our desired differentiation is explicit economic settlement, auditability,
stateful decisions, adversarial/edge-case analysis and decision-grade statistical
reporting. Do not claim broader superiority without a dated comparison using the
same question and evidence cutoff. A future evaluation should blind-review source
traceability, supported quantitative claims, accounting completeness, tested edge
coverage, actionable uncertainty and reproducibility, while scoring readability
separately from report length. This standard defines our target, not the score.

## Current implementation boundary

The campaign report now adds consolidated liquid-cash reconciliation, per-world
sampled drawdown/liquidity floors, attempt/rejection counts, native-unit fees,
turnover concentration and delivery outcomes through `campaign_analysis.py`.
Reports label the missing counterfactuals and edge-case backlog. Historical demand
calibration, full economic-profit valuation and causal campaign/regime estimation
remain unavailable. The full twelve-section standard is a roadmap/publication
contract, not a claim that every current renderer implements all sections.
