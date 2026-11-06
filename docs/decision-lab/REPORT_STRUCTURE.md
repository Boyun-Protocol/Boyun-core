# Case report structure — evidence and decision (v2)

## Stateful financial-report package (current project convention)

For a stateful Boyun financial simulation, the standard package has five
deliverables: three reader-facing financial documents (**World Creation**, **Bear
Case**, **Bull Case**), a **Technical Report**, and a **User Q&A Record**. Put a
contents page near the start of every substantial PDF. The technical report
records provider/model calls, costs, receipts, blockers, replay, and reproducible
tool steps. The Q&A record links the user's actual decisions to the inputs they
changed. This package supersedes the fixed five-document layout below as to
document responsibilities; it does not waive evidence, accounting, uncertainty,
small-sample, provenance, or publication requirements in this file,
[REPORT_DEPTH_STANDARD.md](REPORT_DEPTH_STANDARD.md), or
[SIMULATION_EVIDENCE_STANDARD.md](SIMULATION_EVIDENCE_STANDARD.md). Keep source
data, run receipts, and reproducibility artifacts alongside the reader-facing
documents when available.

The World Creation document explains actors, rules, assumptions, real-world
relationships, and how evidence becomes model inputs. Bear and Bull documents
each define their own regime assumptions and rationale, then report that
scenario's progression, material events, actor actions and reactions, and
decision-relevant outcomes. State whether the run is native and complete or
offline/incomplete, and make same-time comparisons explicit. Include a no-launch
baseline when the experiment supports one. The reusable step-by-step process,
visual design rules, technical-report checklist, Q&A record format, and MACRON
example are in the [financial reporting playbook](FINANCIAL_REPORTING_PLAYBOOK.md)
and project skill at
boyun-financial-reports.

Do not invent real-world odds when the model is uncalibrated. State that odds are
unknown and give only the observed sample frequencies with their true denominator.
Use charts only when they expose a meaningful actor action, reaction, trend, or
comparison; pair each with the numerical finding, denominator, supported
mechanism (or clearly labeled hypothesis), and decision implication. An LLM
rationale is not evidence for why an outcome occurred.

The research-style reference
records eight featured DL Research web editions reviewed on 3 November 2026.
Borrow their analytical structure, not their prose or unverified claims; this was
not a readership ranking or an exhaustive review of downloadable PDFs.

For analytical depth and statistical publication gates, follow
[REPORT_DEPTH_STANDARD.md](REPORT_DEPTH_STANDARD.md). Its small-sample, uncertainty,
accounting and evidence-label rules take precedence over older generic layout
recommendations below. In particular: never scale four worlds into an implied
100-world sample, require a chance estimate when odds are unknown, or draw forecast
bands from a static or inadequate sample. File structure is not evidence quality.

For stateful long-horizon cases, also follow the [lifecycle guidelines](LIFECYCLE_SIMULATION_GUIDELINES.md):
compare exact common timestamps, expose actual completed coverage, retain undefined
statistics and keep native inference, synthetic reference and artificial stress
arms visibly separate. Explanatory text belongs directly below each data chart.

How a Boyun case report is split, and why. Applies to any case, not just $MACRON.
Every rule below traces to published guidance or to a local precedent; taste is not a source.

## What the deeper research changed

| Finding | Source | Consequence |
|---|---|---|
| Working memory holds about **four chunks**, not seven | Cowan 2001, ~11k citations | The decision document carries **at most four findings**; the whole set stays 5–6 artefacts |
| **Natural frequencies + icon arrays** beat percentages, especially for lower numeracy | Gigerenzer 2003, ~1.1k; Galesic 2009, ~530 | Odds are printed as **"31 of 100 sampled worlds"** with a 100-dot array, never a bare "20.1%" |
| Density forecasts are shown as **fan charts** in finance and macro | Bank of England / OBR fan charts | Proceeds and net cash are shown as percentile bands over time, not a single number |
| Model transparency has a standard: **Model Cards** (intended use, factors, metrics, evaluation, caveats) | Mitchell et al. 2019, ~6.1k citations | The model document is a model card first, narrative second |
| Simulation documentation has a standard above ODD: **TRACE**, which also documents testing and analysis | Grimm et al. 2014, ~425; ODD 2020, ~1.35k | Verification evidence (test counts, fuzz sweeps) belongs in the model document, not only in chat |
| Investment memos work because of **risks + a recommendation in context**, not a data dump | IC-memo practice; Stanford study of memo use | The decision document follows the IC memo skeleton, not a generic board summary |
| Forecasters are credible only if they **keep score** | Tetlock / Good Judgment; Brier scoring | A forecast register is a required artefact, not an appendix |
| Answer first, 2–4 supporting points | Minto / SCQA | Situation → Complication → Question → Answer, then at most four supports |

Two earlier findings still hold: 79% of readers scan and only 16% read linearly (NN/g 1997);
readers have time for at most 28% of the words, 20% likely (NN/g 2008). Executive summaries run
about 10% of report length.

## Decision: five prose documents plus a register

| Artefact | Audience | Length | Content | Figures |
|---|---|---|---|---|
| `00-DECISION.md` | decision-maker | **~700 words, one page** | SCQA answer, four findings, does it beat doing nothing | 100-dot odds array; net-cash distribution |
| `01-MODEL.md` | analysts, reviewers | 3–4 pages | model card (intended use, factors, metrics, evaluation, caveats) + ODD Overview / Design concepts / Details + verification evidence | pipeline diagram |
| `02-SCENARIOS.md` | decision + analysts | 2 pages | every scenario as "X of 100", tails, sensitivity | sensitivity bars; scenario table |
| `03-EVIDENCE.md` | reviewers | 2 pages | actor probabilities, cast, event calendar, claims register | none: tables only |
| `04-FORECAST.md` | future readers | 1 page, templated | the recorded prediction, resolution criteria, date, status, later the Brier score | none |
| `DATA/` + `FIGURES/` | machines, auditors | no prose | inputs, assumptions, outputs, receipts, sources | all figures, regenerated by one command |

**Why five prose documents.** Each answers a question the reader already has: what do I do (`00`),
what is this model (`01`), what are the branches (`02`), what is it built from (`03`), and what did we
actually claim (`04`). That is five chunks — inside the 4±1 limit once the register is treated as an
appendix rather than a reading task.

**Why the register is separate from the report.** A prediction and its later score are different
documents written at different times. Mixing them lets a report quietly edit its own history.

**Why not three.** Merging scenarios into the model document pushes it past 4,000 words, so the
scenario table — the thing a decision-maker reads — falls below the fold.

**Why not seven or more.** Cast and events would each be about a page: that is a section, not a file,
and splitting them duplicates the evidence register.

## Format rules

- Sampled frequencies preserve the actual denominator, for example **"three of
  four worlds"**. A percentage may appear beside it, never alone. Do not inflate
  a small sample into a 100-world display or call sampled frequency calibrated odds.
- Every figure is regenerable from `DATA/` by one command; a hand-built chart is a defect.
- A scenario row states outcome, sample size, evidence status and supported risk
  information. Unknown chance and unestimable tails are explicitly unavailable,
  not mandatory invented values.
- "Do nothing" is always a row. If the model cannot beat it, that is the first sentence.
- Unknowns print as unknowns; an absent input never becomes zero.
- The model document must list the tests that could have falsified it.

## Pipeline

`brief.json` (interview output) → evidence pack → launch cases → cast → Jev probabilities →
sampled estimate → renderer → five documents, register, `DATA/`, `FIGURES/`.

Each stage writes a typed artefact and a receipt. The brief is produced by the user's agent from a
guided interview, and the interview is published as a Q&A table so assumptions stay auditable.

## Sources

- [Model Cards for Model Reporting — Mitchell et al. 2019](https://arxiv.org/abs/1810.03993)
- [TRACE — Grimm et al. 2014](https://www.sciencedirect.com/science/article/abs/pii/S0304380014000611)
- [ODD protocol — Grimm et al. 2020, USGS](https://pubs.usgs.gov/publication/70209554)
- [Natural frequencies — Gigerenzer 2003](https://www.bmj.com/content/327/7420/933) · [Icon arrays — Galesic et al. 2009](https://pure.mpg.de/rest/items/item_2099767_4/component/file_2562291/content)
- [Fan charts — OBR, presenting uncertainty](https://obr.uk/box/presenting-uncertainty-in-our-forecasts/)
- [Working memory, the magical number 4 — Cowan 2001](https://pubmed.ncbi.nlm.nih.gov/11515286/)
- [IC memo best practices — Hebbia](https://www.hebbia.com/resources/ic-memo-best-practices) · [Stanford, investment memos and decision-making](https://longterminvesting.stanford.edu/sites/g/files/sbiybj23856/files/media/file/addepar-investment-memos-and-decision-making.pdf)
- [Superforecasters' track record — Good Judgment](https://goodjudgment.com/resources/the-superforecasters-track-record/)
- [Minto Pyramid & SCQA](https://modelthinkers.com/mental-model/minto-pyramid-scqa)
- [NN/g — How Users Read](https://www.nngroup.com/articles/how-users-read-on-the-web/) · [NN/g — How Little Do Users Read](https://www.nngroup.com/articles/how-little-do-users-read/)
