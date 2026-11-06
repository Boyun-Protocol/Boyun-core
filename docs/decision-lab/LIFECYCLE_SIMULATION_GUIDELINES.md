# Stateful lifecycle runs — reusable delivery and recovery rules

These rules apply to token launches, DeFi protocols and non-crypto event worlds.
They complement [the evidence standard](SIMULATION_EVIDENCE_STANDARD.md), not replace
it. The MACRON parameter values are case choices, not defaults for other domains.

## Define the accepted world before inference

- Preserve the user’s root timestamp, horizon, objective, response options and
  protected resources. Cover every required time boundary, adding event decisions
  without silently skipping quiet periods. Record eligibility and forced actions.
- Define domain-specific state: a token can use traded cash, liquidity and MC/FDV;
  a protocol may need TVL, DAU, liabilities and withdrawal capacity. Metrics need
  units, source/derivation, timing, and clear stock versus flow definitions.
- Separate schedules from outcomes, observed facts from conditional assumptions,
  provider action scores from forecast probabilities, and dependent parameter paths
  from independent replications. Never fit a narrative by forcing external outcomes.
- Each assumption and consequence requires an actual reference or a documented
  reasonable cause, with sensitivity and falsification. An evidence-audit pass is
  conditional readiness, not proof of calibration or causal validity.

## State, actions and information

- Persist the predecision permitted observation, action menu, selected action,
  score/draw receipt, settlement or rejection, and postdecision state at each barrier.
  A quiet interval is still a saved decision, not a missing hour.
- Maintain finite resources and conservation. A virtual pricing quantity is not
  real capital; campaign delivery is not a buyer; a proposed action is not a fill.
- Execute accepted commitments with their actual payer, recipient, timing and
  conditional failure semantics. Independent actors then choose their reactions.
- Keep own memory and authorized coordination distinct from public events. Saving
  all state on disk does not authorize sending it all to each persona.
- A public/actor export must physically exclude peer private data. Hiding a control
  or filtering an analyst payload in browser JavaScript is not information isolation.

## Spend and interrupted execution

- One shared budget covers the whole authorized comparison and any continuation.
  Reserve conservatively before dispatch; reconcile confirmed usage afterwards.
  Clearly distinguish published-tariff estimates from provider billing guarantees.
- Persist request and dispatch identity before sending. Save the confirmed response
  before settlement. Never automatically retry an unknown network outcome.
- On interruption, reconcile all global call IDs and reservations, exactly replay
  saved barriers, and reuse a confirmed receipt only for an identical actor, time,
  seed, request and full permitted observation. No approximate or cross-hour cache.
- Retain uncertain cost reservations and stop the affected path rather than invent
  its decision. Keep the unaffected comparison progressing fairly within the same
  cap. A new process must not reset already incurred spend or call identifiers.
- Report incomplete barriers, blocked paths, missing horizons and unknown charges.
  Do not silently replace them with offline policies to claim a completed live run.

## Analysis and outputs

- Compare response branches at the latest exact common saved timestamp, not at
  unequal unfinished endpoints. Report residual exposure separately from cash.
- Report attempt/rejection denominators, defined drawdown sampling, participation,
  concentration and funded cash accounting. Undefined statistics stay undefined.
- Before/after campaign changes are descriptive when other events overlap. Do not
  call them incremental ROI without a suitable counterfactual design.
- Artificial activity/load stress is a separate labeled arm. A 4x decision bias does
  not imply 4x realized transactions, volume or real-world likelihood.
- Produce an explanatory written report, graph-led report with interpretations,
  downloadable data and self-contained interactive views. Each result must declare
  evidence mode, actual coverage, limitations and reproduction identity.
- Node guidance must state its permitted evidence and mechanism. A transparent
  risk-control rule is not a model rationale or a guaranteed optimal decision.
- Finish with separate implementation, replay, native-inference and evidence-
  calibration acceptance statements. More calls or better typography cannot repair
  missing historical evidence or validate a weak behavioral model.

## Current implementation boundaries

`launch_lifecycle.py` implements a fourteen-day finite-wallet financial estimate;
`lifecycle_runs.py` records sampled native choices and exact replay. The MACRON
matrix and receipt-recovery tools exercise these mechanisms. Other domain runtimes
must demonstrate their own equivalent gates; this document does not claim they
already implement every requirement.
