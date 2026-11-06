# Long-horizon campaign runtime

Updated 2 November 2026.

For the subsequent **separate fourteen-day lifecycle estimate**, see the
MACRON lifecycle plan and [reusable execution rules](LIFECYCLE_SIMULATION_GUIDELINES.md).
Its native matrix uses a shared $2 guard and receipt-safe recovery; complete
offline references and artificial stress remain distinct from partial live paths.
This page preserves the older seven-day runtime contract for replay compatibility.

## What changed

The earlier financial actor engine was limited to 16 rounds and 128 actor turns.
Those limits remain unchanged for reproducibility. The separate
`campaign-world.v1` runtime accepts up to 32 actors, 4,096 decision points over
seven days and 100,000 actor turns per world. Every experiment also requires an
explicit total call budget, at most 100,000, before any native inference.

The implementation is in `campaign_worlds.py`, `campaign_orchestration.py` and
`campaign_commands.py`. This is an experimental synthetic market runtime, not a
completed or calibrated memecoin-launch engine.

## Implemented mechanics

- Initial actor inventory is explicit and reconciles with pool reserves and total
  supply. Founder/MM sale menus no longer require a prior purchase.
- Actor cash and token inventories settle through the existing integer-conserved
  AMM, including fees, seeded ordering and slippage rejection.
- An authorized campaign purchase transfers cash to a service account exactly
  once. Delivery delay, uncertain delivery, visibility and expiry are separate
  from buying tokens. Advertising never directly raises pool price or volume.
- Authorized private signal templates are selected independently by each sender
  and delivered after the decision barrier. Retail never receives private team
  messages. A proposal does not force the recipient to act.
- Source events use keyed occurrence draws. Unrealized and not-yet-available
  events are excluded from actor context. Declared event probabilities are input
  assumptions, not measured probabilities or model-derived forecasts.
- Every completed barrier saves full before/after market and actor balances,
  frozen actor observations, decisions, execution receipts, private campaign
  records and a chained checkpoint hash. Each native request, dispatch marker and
  typed response is saved separately before progressing.
- Context carries the latest four public/own states, own cumulative trading and
  campaign spending, cumulative market turnover, step-end price extrema and the
  latest message per authorized signal. Full history remains on disk. Only the
  last twelve available source events are placed in context, with a total count.
  This is an explicit bounded memory policy, not perfect historical recall or a
  retrieval agent.
- Replay reconstructs the world without inference and compares checkpoints,
  frozen observations, recorded requests and decision evidence. This verifies
  local consistency; it is not a provider-signed proof of remote inference.

## MACRON experiment

`engine/examples/macron-campaign-world.v1.json` contains eight illustrative actors:
founder, MM, marketing partner, KOL, ecosystem and three distinct retail personas.
There are 64 decision points: the root, every minute through minute 15, then hourly
through hour 48. Four seeded worlds require exactly **2,048 native actor calls**.
Each call can answer both action and authorized signal questions.

The 12:00 UTC+4 root and expected 10–15 minute curve window come from the user.
Resource allocations, finite retail population, campaign assumptions and stress
event odds are explicitly hypothetical. Token Info uses a checked current offer,
not an established pre-launch quote. An assumed KOL publication is not a real
purchase. Unverified Boost pack pricing is excluded.

```sh
PYTHONPATH=engine/src engine/.venv/bin/python -m decision_lab.cli campaign plan \
  --input engine/examples/macron-campaign-world.v1.json \
  --worlds 4 --max-calls 2048

PYTHONPATH=engine/src engine/.venv/bin/python -m decision_lab.cli campaign run \
  --input engine/examples/macron-campaign-world.v1.json \
  --worlds 4 --max-calls 2048 --seed 31 \
  --output-dir engine/output/my-new-campaign-run \
  --allow-model --env-file .env --api-key-env TYPESAFE_API_KEY \
  --model jev-1.14.0 --http-client curl --timeout 60

PYTHONPATH=engine/src engine/.venv/bin/python -m decision_lab.cli campaign replay \
  --directory engine/output/my-new-campaign-run
```

Output directories must be new and private. Credentials are never written to
artifacts. The provider receives the selected actor's goal and permitted context;
private founder/MM content therefore goes to the configured inference provider,
but not to other actors. This is model inference only: no actual promotion,
on-chain transaction or trade is executed.

The private manifest exposes `attempted_calls`, `completed_calls`, completed steps
and worlds, current status and sanitized failure information. Calls are sequential,
have no automatic retry and stop on failure. Failed/uncertain dispatches preserve
their evidence; automatic resume is not implemented. Provider cost is unknown;
individual receipts retain reported usage and available input-cost estimates.
The initial live-run manifest also inherited the planning-only `model_calls: 0`
field; use `attempted_calls`/`completed_calls`, not that field. New manifests omit
it.

## Evidence and limits

### Required assumption-to-outcome register

Apply [the shared cross-domain evidence standard](SIMULATION_EVIDENCE_STANDARD.md).
New campaign inference requires `--evidence-register <reviewed-sidecar.json>`.
The CLI checks it before reading the selected key; the runner checks it again
before creating run artifacts or dispatching calls. This register covers the
effective world, committed orders, stress intervention, action-selection policy,
qualitative behavior/information rights, probabilities and output mechanisms.
Its content hash and audit are saved in the manifest and rechecked on replay.

The examples above/below illustrate the mechanics and do not include a reviewed
sidecar. They therefore **cannot dispatch a new run as written**. Add an audited
register built for that exact input/policy, and separately confirm the full run's
inference budget before execution. `campaign plan` remains offline without one,
but reports `execution_ready: false`; structural validity is not evidentiary readiness.
The MACRON gap audit does not qualify as an executable campaign register.

Old recorded campaigns remain replayable under their actual policies without
retroactively declaring their unsupported assumptions validated. The passing
status `ready_for_conditional_simulation` is not truth verification, empirical
calibration, a completed fourteen-day implementation or paid-run approval.

### Artificial activity stress mode

Use `campaign plan|run --stress` for an explicitly artificial load test. Defaults
multiply buy and sell action **weights** by four, normalize all action weights and
sample one legal action with a reproducible actor/step/seed draw. They also double
the per-action buy cap, still limited by available own cash. Customize integer
multipliers from one through five with `--buy-multiplier`, `--sell-multiplier` and
`--ticket-multiplier`. Nondefault multipliers without `--stress` are rejected.

```sh
PYTHONPATH=engine/src engine/.venv/bin/python -m decision_lab.cli campaign run \
  --input engine/examples/macron-campaign-world.v1.json \
  --worlds 4 --max-calls 2048 --seed 31 \
  --stress --buy-multiplier 4 --sell-multiplier 4 --ticket-multiplier 2 \
  --output-dir engine/output/my-new-stress-run \
  --allow-model --env-file .env --api-key-env TYPESAFE_API_KEY \
  --model jev-1.14.0 --http-client curl --timeout 60
```

This is a policy intervention, not the original Jev decision. Original provider
choices, confidence and probability scores remain unchanged in receipts. The
stress record saves the selected action, exact normalized weights, random draw,
policy/configuration hashes and an unbuffed same-draw sample. The action confidence
gate is explicitly bypassed in this mode; coordination keeps its existing gate.
Replay recomputes sampling metadata as well as conserved market settlement.

Multiplying trade weights does **not** promise four times the executed frequency
or volume. For example, 80% wait / 10% buy / 10% sell becomes 50% / 25% / 25% under
4x buy/sell weights. Normalization, wallet exhaustion, inventory availability,
slippage and fees constrain realized activity. Zero provider weight stays zero;
the intervention does not invent fresh wallets, cash, tokens or demand. The
unbuffed same-draw action is a conditional diagnostic at the stress world's current
state, not a full alternate timeline or calibrated market counterfactual.

The initial stress experiment retains the MACRON narrative and decision schedule
to isolate activity policy changes. It does not adopt an unverified market regime
or news explanation as fact. A narrative comparison should be a separate arm.

The authorized live stress run is stored separately in
`engine/output/cases/macron-solana-2026-10-29/campaign-stress-4x-2026-11-02/`.
Its manifest is authoritative for progress. The first 24 completed checkpoints
contained 39 filled buys, 49 filled sells, four campaign payments and three
slippage/execution rejections, with $9,144.47 simulated turnover. These are partial
native stress results, not a completed 2,048-call result or real market trading.

After completion, `campaign summary --directory PATH` performs exact replay and
prints fill/rejection counts, executed turnover, campaign spend, provider choices,
selected policy actions and conditional unbuffed samples. It makes zero new model
calls and refuses to label an unfinished run as a final summary.

### Recorded validation

The focused campaign/timeline suite passed **35 tests**, including a complete
**2,064-call injected-transport experiment** and exact offline replay. Those are
offline fixtures, not paid Jev inference or evidence of economic realism. Tests
also cover campaign-only price invariance, delayed and failed delivery, authorized
next-step signals, initial inventory sales, traded volume, conservation, atomic
invalid barriers, bounded long-run context, budget refusal and no retry on failure.
The full engine suite passed **1,792 tests**. The long-run fixture was then
strengthened to include repeated buys/sells, campaign payment and private signal
delivery; all eleven focused campaign tests passed again.

The authorized baseline experiment completed all **2,048 native calls**, four
worlds and 256 checkpoints in
`engine/output/cases/macron-solana-2026-10-29/campaign-2048-2026-11-02/`.
Exact replay verified all 256 checkpoints with zero additional model calls.
The first 95 saved native responses all selected wait. These were provider choices,
not only confidence-gate abstentions. More calls alone cannot cure a static world;
do not force purchases to make a chart appear active.

Still missing: integration with the separate bonding-curve/graduation estimator,
as-of real-world announcement schedules, six-to-twelve-month historical calibration,
arrival/attention cohorts, inventory cost basis, LP ownership/withdrawal, reliable
tail-odds estimation and the full campaign-specific graph-led report/exporter.
Four seeds cannot support credible probabilities for a 5M market cap. Jev supplies
typed decisions/scores, not narrative causal explanations. No unrestricted swarm,
calibrated demand response or complete launch lifecycle is claimed.
