# Graph-led case reports — proposed format

Status: proposed for the MACRON redesign, 2 November 2026. Page and word counts
are design budgets, not research findings. This proposal supplements the existing
REPORT_STRUCTURE.md; it is not yet implemented in the report generator.

The later [depth standard](REPORT_DEPTH_STANDARD.md) adds the governing twelve-section
target and statistical/accounting publication gates. The current campaign renderer
implements nine analytical sections with risk/accounting supplements, not this
entire proposed main-report family. Do not infer implemented coverage from a page
plan or assume every input supports forecast bands or tail probabilities.

The later lifecycle renderer now supplies the twelve-section outline, aligned
response charts, explanatory text, separate BULL/BEAR documents and actor views.
See actual lifecycle results. Native paths remain
budget-limited and historical behavioral calibration remains unresolved; this is
not acceptance of every research/content target in the proposed report family.

## Reader promise

A reader should understand the decision, how the modeled outcome happens, what is
common, what differs, what remains uncertain, and what evidence could change the
conclusion. A figure is complete only when its interpretation is readable on the
same page. PDFs are written to be read without a presenter.

## Report family

| Report | Purpose | Target length | Visual budget | Text budget |
| --- | --- | --- | --- | --- |
| Decision brief | First read and sharing with a decision-maker | 2 pages | 2–3 figures | 500–700 words |
| Main case analysis | Explain the case and its outcomes | 16 pages including cover and reading guide | 12–16 figures across 9 sections | 2,800–3,800 words |
| Strategy comparison | Compare reviewed alternatives when matched runs exist | 6–10 pages | 6–10 figures | 1,200–2,000 words |
| Evidence and methods | Audit inputs, mechanics, assumptions, and verification | 8–12 pages plus necessary tables | 3–6 diagrams or tables | 2,000–3,000 words |
| Outcome follow-up | Compare a later observed outcome with the frozen claim | 2–4 pages | 2–4 figures | 500–900 words |

The main analysis is the primary deliverable. The brief summarizes it. Comparison
and follow-up reports are produced only when the necessary evidence exists.
Reports share a case ID, run ID, date, parameter version and source register.
Updating one report must not silently rewrite an earlier claim.

## Main analysis: nine sections and a 16-page plan

| Section | Pages | Contents | Visuals | Approximate words |
| --- | --- | --- | --- | --- |
| Front matter | 1–2 | Case title, decision question, recorded date, one-sentence result, reading guide, legend for observed/model/assumption | One compact result preview; no decorative full-page cover | 100–150 |
| 1. Decision and headline findings | 3 | Comparison with doing nothing; three findings; what the result permits the reader to conclude | Profit/loss frequency and median against baseline | 220–280 |
| 2. The plan and capital at risk | 4 | Starting resources, actual commitments, creator cash and supply allocation, exit policy | Capital allocation diagram and policy timeline | 220–280 |
| 3. Participants and mechanism | 5–6 | Relevant participant groups, incentives, decision inputs, curve, migration, exit and cash accounting | Participant map; mechanism flow; separately labeled illustrative price-impact diagram | 350–450 |
| 4. Typical outcomes and tails | 7–8 | Full distribution, central outcomes, loss range, positive tail, mean/median difference | Histogram with zero line; cumulative distribution or percentile interval plot | 350–450 |
| 5. Scenario differences | 9–10 | Demand groups, migration groups, creator-selling groups; group size and within-group outcome | Frequency bars and aligned outcome intervals; compact scenario matrix | 350–450 |
| 6. Drivers and sensitivity | 11–12 | Tested parameter arms, changed assumptions, fixed assumptions, sample differences, possible interactions | Comparable interval/dot plots for early buys, SOL assumption and timing | 350–450 |
| 7. What is expected, unusual or unresolved? | 13 | Reconcile results with a stated baseline; distinguish common outcomes from unusual tails and missing evidence | Evidence-status comparison table; anomaly callouts only when a declared rule supports them | 220–280 |
| 8. Alternatives and next decisions | 14 | Current plan versus doing nothing; tested changes; evidence needed to evaluate untested changes | Alternative comparison table with tested/untested labels | 220–280 |
| 9. Limits, confidence and follow-up | 15–16 | What would change the answer, model omissions, source quality, frozen claim, resolution criteria and next observations | Uncertainty register and follow-up checklist | 400–500 |

Allow an extra page when a figure requires it. Do not force small text to hit the
page budget. Source tables and detailed test logs belong in the methods report.

## The unit of explanation: one chart and its analysis

Use one primary chart per page, or two charts answering the same question. Reserve
roughly half the usable page for visuals and the rest for explanation and source
notes. Target 180–280 words on a normal analytical page, at least 11-point body
text on A4 portrait, and clearly readable axis labels. Check a phone preview as
well as the printed page; this is a readable document, not a reduced slide deck.

Every chart includes:

1. A question or supported finding as its title.
2. A subtitle naming the sample, population and units.
3. A chart with direct labels, a baseline when relevant, and explicit denominators.
4. A 100–160-word interpretation below the chart, normally in three short paragraphs.
5. A short source/run note and the limitation most relevant to that figure.

The interpretation answers these questions:

- **What do we see?** Identify the dominant pattern and quote its magnitude.
- **What is common or different?** Compare groups or the center with the tails.
- **How might it happen?** Explain recorded mechanics; label hypotheses as hypotheses.
- **Is it expected?** Compare with a named, pre-existing baseline. If none exists,
  say that the result has no established benchmark.
- **Why does it matter?** Connect the pattern to the decision and the next useful check.

Use these questions as an editing checklist. Do not print five repetitive boxes
under every figure, and do not manufacture an answer when the data is absent.

## Language for common, special, expected and out of hand

| Reader question | Required comparison | Allowed interpretation |
| --- | --- | --- |
| What is common? | Count or share within the defined sample | Most sampled worlds, median, or an explicitly defined central interval |
| What is special? | A subgroup versus a stated reference group, with group counts | Different in this sample; avoid implying generality |
| Is it expected? | A reviewed prior assumption, empirical cohort, or model baseline | Consistent/inconsistent with that benchmark; otherwise unknown |
| Is it unusual? | A declared tail threshold and reference distribution | Unusual relative to this simulation or observed reference |
| Is it out of hand? | An agreed budget, loss, liquidity or policy limit | Breach of that named limit; report the threshold and count |

A negative result is not automatically anomalous. A model tail is not an empirical
market anomaly. A visually striking point is not evidence of a cause. Thresholds
must be reviewed or clearly labeled exploratory rather than invented after seeing
the result.

## MACRON: charts that existing artifacts can support

Available: per-world net cash and proceeds, outside-demand bucket, creator-sale
flag, migration flag, per-world deployed amount, aggregate quantiles, scenario
groups, actor scores, recorded parameters and sensitivity tables.

| Figure | Data | Interpretation focus |
| --- | --- | --- |
| Profit/loss frequency | 4,341 positive worlds out of 20,000 | About 22 of 100 exceed zero under the recorded assumptions |
| Net-cash histogram with zero line | worlds.csv | The shape of outcomes and how much lies below the baseline |
| Cumulative net-cash curve | worlds.csv | Share below any shown net-cash threshold; no unreviewed acceptable-loss rule |
| Percentile plot plus mean | outputs.json | Median −$2,332 and mean $301 answer different questions |
| Demand frequency plus outcome intervals | worlds.csv / outputs.json | No, moderate and whale demand have different counts and outcomes |
| Migration group comparison | worlds.csv | Associations in sampled groups, with sample sizes; not causal attribution |
| Creator-sale group comparison | worlds.csv | Marginal comparison may be confounded by demand and migration; show stratified groups where supported |
| Early-buy sensitivity | recorded sensitivity table | Three tested commitments; 5,000 worlds per arm |
| SOL-assumption sensitivity | recorded sensitivity table | Assumed conversion/venue effects rather than a live SOL-price forecast |
| Timing comparison | recorded sensitivity table | Cash outcomes unchanged in these arms because the model excludes later arrivals |

Do not plot a token-price history, realistic intraday volume trend, fan chart over
time, or empirical peer-launch comparison from these artifacts. Those require
additional data. A policy timeline may show scheduled actions, but must not look
like an observed market trajectory. Do not claim that migration or a whale
caused the result merely from grouped outcomes.

## Example interpretation: the mean and median page

**Title:** The positive average hides a negative central outcome.

**Observation:** Across the recorded 20,000 worlds, median net cash is −$2,332,
while mean net cash is $301. The recorded 90th percentile is $8,402 and the 99th
percentile is $37,419. The mean and median differ substantially because the
distribution includes large positive outcomes.

**Meaning:** The average does not describe the middle sampled outcome. These
statistics also do not establish the real-world likelihood of a profitable
launch: the worlds reuse the recorded participant scores and declared mechanics.

**Decision implication:** Read the median alongside the loss distribution and
the proportion above the $0 do-nothing baseline. Whether a particular loss is
acceptable requires the decision-maker's own risk limit; the report has not
established that limit.

## Production and acceptance

- Derive chart data from the recorded artifacts; keep manual prose free of invented numbers.
- Mark each figure as observed evidence, simulation output, assumption, or illustration.
- Preserve the 20,000-world headline versus 5,000-world sensitivity denominators.
- Explain frequency versus model score and cash versus utility where relevant.
- Generate charts with standard plotting tools and embed them in the PDF.
- Embed fonts and figures so a PDF works without network access.
- Review every rendered page at normal reading size for clipping, chart labels,
  misleading scales, caption placement, unsupported claims and numerical consistency.
- Preserve earlier PDFs and the original recorded claim; publish a new version.
- Produce the main analysis first; derive the brief after its findings stabilize.

## Implementation order

1. Agree the report architecture and primary audience using this proposal.
2. Build a MACRON prototype comprising the decision page, distribution page and
   scenario-comparison page, with full interpretation below each graph.
3. Review those rendered pages together before expanding the format.
4. Complete the main PDF and methods companion using the approved system.
5. Generalize the renderer for additional cases and optional report types.
