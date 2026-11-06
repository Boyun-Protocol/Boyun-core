# NEAR lending case runner

How the 90-day NEAR lending launch case is built, run, resumed, summarized and
reported. The first application is
`cases/near-lending/`, run 2026-11-05.
The design applies to any collateralized-lending launch. Constants such as the
$1M friendly supply, the cast and the Rhea snapshot belong to that case only.

## Pieces and where they live

| Piece | File | Role |
|---|---|---|
| Ledger | `engine/src/decision_lab/lending.py` | Settlement only: supply, withdraw, collateral, borrow, repay, liquidate, write-off, spend, accrual. No actor policy. |
| Decision menus | `engine/src/decision_lab/lending_choices.py` | Builds one actor's private observation and a menu of options the ledger would accept. |
| Runner | `engine/src/decision_lab/lending_case.py` | Hourly loop: settlement, oracle, campaign delivery, liquidation, triggers, decisions, daily metrics, decision cache. |
| Run script | `engine/tools/run_near_lending_case.py` | Loads the case files, picks Laya or Jev, writes outputs and a manifest, replays the ledger. |
| Summary | `engine/tools/summarize_near_lending_case.py` | Checkpoints, liquidations, choice mix and model decisiveness for one run. |
| Casebook | `tools/build_lending_casebook.py` (+ `lending_casebook_data.py`, `_docs.py`, `_records.py`) | Six-document report from frozen runs. No model calls. |

Case inputs are JSON files in the case folder: `proposed-settings.json` (rules),
`funded-cast-proposal.json` (actors and balances), `campaign-calendar.json`
(campaign items, channels, liquidator assumptions, cadence) and a
`price-path-*.json` (hourly prices). Variants are separate files with a
`variant-` prefix, never edits to the selected baseline.

## Ledger rules

- **Units.** Exact fractions, with one exception: hourly accrual, points and
  partial interest splits round **down to 10⁻¹² USDC**. With pure fractions,
  per-supplier receivables grew past Python's 4,300-digit integer limit by hour
  1,524 of a 90-day run. The dust favors borrowers and never creates cash.
  `test_hourly_accrual_stays_on_fixed_grid_over_90_days` reproduces the
  failure.
- **Conservation.** After every event, total USDC and NEAR across wallets,
  pool, reserve, treasury and the external market equal the opening totals.
  Supplier claims equal pool cash plus outstanding principal.
- **Rate.** Utilization *u* = principal / (pool cash + principal). The borrow
  rate is piecewise linear: from the base rate to the kink rate over
  0 ≤ *u* ≤ kink, then up to the full-utilization rate. Interest is simple
  (no compounding) and is a receivable until repaid; the protocol takes its
  share at collection.
- **Points.** Borrowed principal is allocated pro rata to unqueued supplier
  claims, at 1 point per borrowed USDC-day. Idle and queued supply earns none.
- **Withdrawals.** Paid from idle cash, otherwise queued first-in first-out.
  Queued withdrawals are paid before any new loan is made.
- **Liquidation.** Needs a fresh oracle and health < 1. The liquidator supplies
  the market price, impact and cost; the ledger refuses an unprofitable or
  unfunded liquidation instead of filling it partially.
- **Write-off and reserve.** Debt is written off only when collateral is
  exhausted. The capped reserve then pays suppliers pro rata, with no top-up.

## Hourly order

1. Accrue interest and points; publish the oracle price for the hour.
2. Deliver campaign items due this hour. A paid partner item is first offered
   to the partner, who can accept, delay three days (once) or decline. Cash is
   spent only on delivery.
3. Mark actors aware if a channel they follow delivered. Outsiders make no
   decisions until then; **no conversion rate is assumed**.
4. Liquidators act on a deterministic profit rule, within their per-hour exit
   depth.
5. Fire triggers on rising edges with a 12-hour cooldown per actor: NEAR ±8% in
   24h, utilization ≥ 90%, a withdrawal queue appearing, an actor's own health
   < 1.1, or a status update.
6. Aware actors decide daily at 12:00 UTC and when triggered. The team decides
   weekly and when triggered, from a communicate-and-spend menu only.
7. At 23:00, record daily metrics.

Menu step sizes: suppliers 25% of their resources (min $1K, max $100K);
borrowers 25% of their NEAR and $12,500 of borrowing. The model scores each
option and the top-scoring option settles. Scores are not probabilities of real
behavior.

## Run, resume, summarize, report

```sh
# Local Laya (free). Each world is a new --out directory.
engine/.venv/bin/python engine/tools/run_near_lending_case.py \
  --settings variant-cap100k-steep-settings.json --cast variant-split-cohort-cast.json \
  --calendar variant-split-cohort-calendar.json --path price-path-bear-2025-11.json \
  --out engine/output/near-lending-case-NEW

# Jev (spends money). The key is read only from the file you name.
... --actor-model jev --env-file .env --max-cost-usd 0.15

# Resume: rerun the same command with the same --out.
engine/.venv/bin/python engine/tools/summarize_near_lending_case.py engine/output/near-lending-case-NEW
engine/.venv/bin/python tools/build_lending_casebook.py --output docs/decision-lab/cases/near-lending/report-NEW
python tools/validate_financial_report_package.py docs/decision-lab/cases/near-lending/report-NEW
```

Every model answer is appended to `decisions.jsonl` keyed by the exact request.
Rerunning a folder reuses cached answers and calls the model only for new
states. A changed engine can reuse a cache only where requests are identical.
The 2026-11-05 baseline was reproduced from cache on the fixed engine with
identical figures and no new calls. The original output is kept because it
replays only on the earlier engine.

A 90-day world takes about 8–13 minutes on local Laya with about 1,600–2,500
decisions. On Jev it takes about 13 minutes with about 2,100 decisions, at
roughly $0.06 by list-price estimate.

## What the first case taught

- **Report what the ledger saw.** The oracle uses hourly closes. A −40% wick on
  2025-10-10 closed its hour about 9% down, so the ledger saw at most −31%.
  State drawdowns on the sampled series and name unsampled moves as untested.
- **Interest has three parts.** Total borrower interest = interest paid to
  suppliers + interest paid to the protocol + receivables still owed. The
  team's revenue is only the protocol share. The first summary left out the
  supplier part and understated totals by about half.
- **Separate mechanical from behavioral claims.** Caps bounded utilization
  under either actor model, and the risk rules produced no bad debt on both
  paths. Behavior did not hold up: Laya borrowed nearly every time it could,
  Jev almost never, and neither changed its choices when the rate rose 2.5×.
  Run a second actor model before relying on any behavioral result.
- **Check what binds.** In the first world every borrower hit the $50K
  per-borrower cap. In the next, the $500K aggregate cap bound. Arithmetic shows
  this before any model call: about $2M of supply against a $500K cap limits
  utilization to about 25%.
- **One account per decision-maker.** A cohort modeled as one account (80
  people, one $50K cap) understates its demand. Split cohorts before reading
  borrowing results.
- **An unrun regime gets its own short document** saying it was not run and how
  to run it. Never let another regime stand in for it.

## Known limits

Synthetic cast and balances; channel-based awareness without conversion data;
liquidator cash, depth and impact are assumptions; Rhea rates are held at the
2026-11-05 snapshot; no competitor reaction; the $30K operations budget is not
charged; no cap, rate or pause changes during a run; the optional $100K is not
modeled; hourly oracle sampling; one seed per world.
