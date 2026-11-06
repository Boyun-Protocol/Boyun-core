# Research foundations: what supports the method, and what does not

For the formal paper, see the technical whitepaper,
with a mathematical model, reproducible synthetic experiments and bibliography.

Updated 29 October 2026. **Boyun simulates financial and economic decisions
with explicit actor incentives.**
Its mechanisms have established mathematical and agent-modeling precedents.
Its present crypto population, behavioral accuracy and real-world event
probabilities have not been empirically validated. These are different claims.

This document maps research → design choice → executable code → evidence → limit.
Code links are maintained by `python3 tools/build_evidence_docs.py --check`.
[System design](SYSTEM_DESIGN.md) explains connections; [source map](SOURCE_MAP.md)
lists symbols; [provenance](UPSTREAM_REUSE.md) distinguishes inherited software.

The decision record is an input/output and execution record. Jev does not supply
an internal reasoning trace. Declared goals, action scores and payoff checks do
not recover the model's reasons. Replay and artifact commitments establish
separate, limited consistency properties.

## Standing research-to-outcome requirement

Apply [the shared evidence standard](SIMULATION_EVIDENCE_STANDARD.md) to all
simulation types, including new domains. Every material assumption and modeled
consequence needs a specific real-world reference or a documented reasonable
cause. Preserve claim links through input → mechanism → outcome, not just a
bibliography. Persona behavior, information access and causal transfers count as
assumptions too. State sensitivity, competing explanations and falsification.

A reputable forecast, poll, actual vote or market quote supports its own defined
claim; transferring it to another event, population, time horizon or price/usage
response needs separate justification. Keep unsupported odds unknown, carry input
uncertainty into outputs, and never force simulated results to match a reference.
Conditional scenario analysis is allowed without claiming empirical calibration.

[Additional economic/game projects and primary research](ECONOMIC_RELATED_WORK.md)
cover AI Economist, EconAgent, ABIDES, OpenSpiel and controlled repeated-game
experiments, with a method-to-product comparison and no inherited accuracy claim.

## Evidence levels

| Level | What can be concluded | Our current position |
| --- | --- | --- |
| Mathematical correctness | A calculation follows its stated definitions and assumptions | Exact finite-game/Bayes kernels, resource checks and replay have tests |
| Engineering verification | The implementation performs its declared transitions | Schema, visibility, atomicity, replay, export and failure tests |
| Behavioral validation | Simulated people match specified human behavior | Not established for our personas or crypto domain |
| Forecast validation | Predictions beat appropriate baselines on unseen resolved events | Scoring tools exist; relevant held-out evidence is not yet supplied |
| Business validation | A defined customer repeatedly pays for this decision aid | Proposed alpha and pricing; no demonstrated traction/revenue |

A successful API call, realistic biography, attractive chart, passing test suite
or blockchain receipt does not advance the last three levels by itself.

## Research-to-code matrix

**S1. ODD: explicit models before persuasive stories.** Grimm et al. (2020),
[The ODD Protocol for Describing Agent-Based and Other Simulation Models](https://www.jasss.org/23/2/7.html),
organizes model descriptions around purpose, entities, scheduling, design
concepts and implementation details. We use that structure below and in the
architecture doc, including why each artifact exists. This is a documentation
practice, not ODD certification or a runtime library. Our concrete entity/rule
contract is [strategic_worlds.py:85](../../engine/src/decision_lab/strategic_worlds.py#L85)<!-- code:world_validate -->; the authoring contract is [strategic_models.py:206](../../engine/src/decision_lab/strategic_models.py#L206)<!-- code:author_prompt -->.

**S2. Verification is different from validation.** Galán et al. (2009),
[Errors and Artefacts in Agent-Based Modelling](https://www.jasss.org/12/1/1.html),
examines failures between model intent, code and interpretation. We apply the
lesson through transactional round updates, observation tests and exact replay:
[strategic_worlds.py:287](../../engine/src/decision_lab/strategic_worlds.py#L287)<!-- code:world_advance -->, [strategic_worlds.py:339](../../engine/src/decision_lab/strategic_worlds.py#L339)<!-- code:world_replay -->; tests [test_strategic_worlds.py:60](../../engine/tests/test_strategic_worlds.py#L60)<!-- code:test_atomic -->, [test_strategic_worlds.py:79](../../engine/tests/test_strategic_worlds.py#L79)<!-- code:test_replay -->.
Replay demonstrates consistency with recorded rules, not truth about the world.

**S3. LLM agents as a modeling architecture.** Park et al. (2023),
[Generative Agents: Interactive Simulacra of Human Behavior, v2](https://arxiv.org/abs/2304.03442v2),
studies a 25-agent sandbox with memory, retrieval, reflection and planning.
It motivates conditioning decisions on an actor's observations and history:
[strategic_worlds.py:255](../../engine/src/decision_lab/strategic_worlds.py#L255)<!-- code:world_observe -->, [strategic_models.py:105](../../engine/src/decision_lab/strategic_models.py#L105)<!-- code:decide -->. We do **not** implement that full memory/reflection
architecture; our history is bounded round state and delivered messages. The
paper's believability evaluation is not a crypto-return forecast benchmark.

**S4. Social interaction and small-model precedent.** Yang et al. (2025 revision),
[OASIS, v5](https://arxiv.org/html/2411.11581v5), studies platform actions,
recommendation and group dynamics, including backend-model ablations with
7B/8B/20B models (Appendix C.4). This motivates explicit action menus,
information delivery and controlled link removal: [strategic_models.py:75](../../engine/src/decision_lab/strategic_models.py#L75)<!-- code:decision_request -->,
[strategic_worlds.py:255](../../engine/src/decision_lab/strategic_worlds.py#L255)<!-- code:world_observe -->, [social_experiments.py:31](../../engine/src/decision_lab/social_experiments.py#L31)<!-- code:social -->. Appendix H describes gaps from real users and
recommendation systems. We neither run OASIS in the current product nor inherit
its million-agent scale or empirical results. A smaller-model precedent is not
validation of Jev on our task.

**S5. Grounding a persona matters.** Park et al. (2026 revision),
[LLM Agents Grounded in Self-Reports Enable General-Purpose Simulation of Individuals, v3](https://arxiv.org/abs/2411.10109v3),
compares agents built from interviews, surveys and demographics for 1,052 US
participants against participant-response benchmarks. It supports collecting
relevant grounding rather than inventing motives from a label. Our observed
wallet analysis [wallet_evidence.py:119](../../engine/src/decision_lab/wallet_evidence.py#L119)<!-- code:wallet_data --> reports sampled trade patterns and unknowns;
[persona_controls.py:15](../../engine/src/decision_lab/persona_controls.py#L15)<!-- code:persona --> applies user-selected **hypothetical** perspectives. We have no
comparable consented interview/survey data or crypto-population validation.
Observed trading size does not prove a wallet is a KOL, market maker or whale.

**S6. Incentives, beliefs and Nash conditions.** Ben Polak's Yale ECON159
[best responses](https://oyc.yale.edu/economics/econ-159/lecture-3) and
[coordination/Nash equilibrium](https://oyc.yale.edu/economics/econ-159/lecture-5)
provide the formal teaching foundation. [strategic_games.py:126](../../engine/src/decision_lab/strategic_games.py#L126)<!-- code:game --> exhaustively checks pure Nash
profiles and strict domination by other pure actions; it computes exact expected
utility and deviation regret only when independent strategy beliefs are supplied.
[strategic_worlds.py:360](../../engine/src/decision_lab/strategic_worlds.py#L360)<!-- code:world_game --> derives a first-round payoff table from actual strategic rules
for at most four players / 256 profiles. Test: [test_strategic_games.py:26](../../engine/tests/test_strategic_games.py#L26)<!-- code:test_game -->. This advisory,
author-omniscient calculation is not a 100-player equilibrium solver, Bayesian
Nash, subgame perfection or a claim that Jev selects an equilibrium.

**S7. Bayesian updating requires an explicit likelihood.** Pishro-Nik's author
textbook, [Bayes' rule §1.4.3](https://www.probabilitycourse.com/chapter1/1_4_3_bayes_rule.php),
states normalization over an exhaustive partition. [probability_updates.py:103](../../engine/src/decision_lab/probability_updates.py#L103)<!-- code:bayes --> implements finite
updates with exact fractions, explicit priors and conditionally independent
signals. Test: [test_probability_updates.py:25](../../engine/tests/test_probability_updates.py#L25)<!-- code:test_bayes -->. Likelihoods remain supplied assumptions; copied
articles are not independent evidence. This separate CLI kernel does not convert
Jev confidence, news sentiment or simulated frequency into market probabilities.

**S8. Markets need execution mechanics.** Angeris et al. (2021 revision),
[An analysis of Uniswap markets, v7](https://arxiv.org/abs/1911.03380v7), combines
constant-product analysis and agent simulation. Our separate financial kernel
uses integer balances, fee retention, liquidity ownership and executable minimum
outputs: [finance.py:93](../../engine/src/decision_lab/finance.py#L93)<!-- code:ledger -->, [finance.py:182](../../engine/src/decision_lab/finance.py#L182)<!-- code:amm -->; test [test_finance.py:91](../../engine/tests/test_finance.py#L91)<!-- code:test_money -->. This is not a reproduction of
that paper's experiments, a real venue adapter or the default strategic UI's
settlement. The strategic product spends declared costs into a sink; it does not
turn attention points into token-sale cash.

**S9. Finance ABMs are an established research direction, not a free shortcut.**
Byrd, Hybinette and Balch (2019),
[ABIDES: Towards High-Fidelity Market Simulation for AI Research](https://arxiv.org/abs/1904.12066v1),
models exchange messages and latency for market research. It is a useful
comparison for what realistic market microstructure entails. **ABIDES is not
installed, called or replicated here**; we have no limit-order-book/latency
matching claim. Our limited synthetic AMM should not be described as ABIDES-level
market realism.

**S10. Evaluate probabilities against resolved outcomes.** The original
[Brier (1950) paper](https://doi.org/10.1175/1520-0493(1950)078%3C0001:VOFEIT%3E2.0.CO;2)
and [Gneiting & Raftery (2007)](https://doi.org/10.1198/016214506000001437)
are bibliographic foundations for probability scoring. The formulas were checked
against the official [scikit-learn model-evaluation reference](https://scikit-learn.org/stable/modules/model_evaluation.html#brier-score-loss),
including its log-loss section; this is a reference, not a dependency. The
publisher's Gneiting page was access-blocked during this review; no full-paper
reading is claimed. [evaluation.py:123](../../engine/src/decision_lab/evaluation.py#L123)<!-- code:score --> and [evaluation.py:146](../../engine/src/decision_lab/evaluation.py#L146)<!-- code:evaluation --> score caller-supplied resolved
records with chronology checks and a training-only baseline. Test: [test_evaluation.py:39](../../engine/tests/test_evaluation.py#L39)<!-- code:test_eval -->.
Synthetic fixtures verify arithmetic, not forecast skill. Calibration bins are
descriptive; they do not fit a calibrator or remove selection bias.

## What the mathematics actually does

For strategic actor i, declared utility is:

```text
U_i = cash_weight_i × remaining_cash_cents_i
      + sum(metric_weight_i,k × metric_k)
```

The weights are scenario assumptions, not measured psychological traits. Cash
and metric units require explicit scaling. A nonlinear utility, utility learned
from behavior or a risk-preference estimator is not supplied. See [strategic_worlds.py:251](../../engine/src/decision_lab/strategic_worlds.py#L251)<!-- code:world_utility -->.

For explicit independent beliefs about opponents:

```text
EU_i(a) = sum_over_opponent_profiles[U_i(a, a_-i) × product_j p_j(a_j)]
regret_i(a) = max_b EU_i(b) - EU_i(a)
```

These formulas explain the advisory analyzer. Jev is separately asked to score
its permitted menu from goals, cash, public rules and visible context. Its
response is not constrained to be a best response, rational equilibrium or
empirically fitted human policy. That distinction is deliberate and testable.

For a declared hypothesis model:

```text
P(H | E) = P(E | H) × P(H) / sum_h[P(E | h) × P(h)]
```

This is conditional arithmetic. The engine cannot prove hypotheses exhaustive or
signals independent. It rejects impossible evidence rather than inventing a
uniform posterior.

## Reproduce the analytical examples without a model

From the repository root, choose output filenames that do not already exist:

```sh
uv run --project engine decision-lab mechanics game \
  --input engine/examples/launch-coordination.game.json \
  --output engine/output/research-game.json
uv run --project engine decision-lab mechanics bayes \
  --input engine/examples/event-belief-update.json \
  --output engine/output/research-bayes.json
uv run --project engine decision-lab evaluate \
  --input engine/examples/evaluation.synthetic.json \
  --output engine/output/research-scores.json
```

These commands were executed during this review with external connections blocked:

- Coordination fixture: two pure Nash profiles, review+escrow and skip+wait.
  Under the supplied independent beliefs, founder expected utility is 6/5 for
  review and 4/5 for skip; skip's deviation regret is 2/5 utility points.
- Bayesian fixture: the supplied attention prior plus two assumed independent
  signals produces posterior 4/5 persists, 1/5 fades. **80% is an illustration
  conditional on made-up inputs, not our estimate of current news attention.**
- Scoring fixture: two synthetic holdout records yield Brier 0.0625 against the
  training-base-rate baseline's 0.25. This is a formula check, not measured skill.

No inference, chain transaction, model key or empirical dataset is used. Existing
output files are refused; use fresh names rather than overwriting evidence.

## Four meanings of probability that must stay separate

| Quantity | Where it comes from | Permitted interpretation |
| --- | --- | --- |
| Jev action distribution | Context + typed action question, [jev.py:209](../../engine/src/decision_lab/jev.py#L209)<!-- code:jev --> | Direct TypeSafe scores over permitted actor actions; native live acceptance pending |
| Seeded action draw | `sample` mode in [strategic_models.py:105](../../engine/src/decision_lab/strategic_models.py#L105)<!-- code:decide --> | Repeatable engine sampling from those returned scores |
| Exogenous event probability | Supplied branch weights in [event_chains.py:240](../../engine/src/decision_lab/event_chains.py#L240)<!-- code:event --> | Assumed/estimated scenario chance, with provenance |
| Empirical forecast probability | Issued prediction judged by [evaluation.py:146](../../engine/src/decision_lab/evaluation.py#L146)<!-- code:evaluation --> | Requires relevant held-out resolved events; not established here |

Argmax repetitions may be identical. More samples reduce numerical sampling
noise under a fixed setup; they do not cure wrong rules, missing actors,
model bias or market regime change. A fixed seed replays engine sampling, not a
remote provider's latent generation. Current online strategic runs call the
model for each non-forced turn; they are not frozen-policy offline Monte Carlo.
The separate financial engine can repeat numeric policies on matched random
streams: [randomness.py:7](../../engine/src/decision_lab/randomness.py#L7)<!-- code:rng --> and [experiments.py:73](../../engine/src/decision_lab/experiments.py#L73)<!-- code:matched -->.

## ODD-style description of our strategic model

- **Purpose:** reveal conditional trade-offs around a bounded decision, initially
  crypto launches, ticker choice and DeFi incentives.
- **Entities/state:** actors with private information, goals, cash, utility
  weights, actions and subscriptions; bounded public metrics; scheduled events
  and joint-action rules. These are proposed or supplied, then reviewed.
- **Scheduling:** observe the shared round state → choose independently → validate
  every action → apply all costs/effects together → deliver publications next
  round. Events at the next round are a separate aggregate stage.
- **Design concepts:** heterogeneous motivations, strategic dependence, limited
  information and optional action randomization. There is no automatic learning,
  social-network rewiring, free-form actor tool use or empirically fitted trust.
- **Initialization/input:** ready authored templates, validated agent proposals or
  imported worlds. Public data can be attached as timestamped evidence; numeric
  effects and motives remain labelled assumptions.
- **Submodels/observations:** typed Jev choices and deterministic settlement;
  saved requests/receipts, action histories, costs, metrics and replayed reports.
  A small-game diagnostic is optional and bounded, not global equilibrium.

## Social experiments: what intervention means here

[social_experiments.py:31](../../engine/src/decision_lab/social_experiments.py#L31)<!-- code:social --> removes specified incoming subscription edges while preserving the
rest of a financial agent world. [social_experiments.py:176](../../engine/src/decision_lab/social_experiments.py#L176)<!-- code:social_run --> runs fresh baseline/treatment
model decisions; [test_social_experiments.py:34](../../engine/tests/test_social_experiments.py#L34)<!-- code:test_social --> checks the controlled input difference. This
measures sensitivity **inside the model**. Shared seeds do not match unknown
provider randomness, and no identified human causal effect, p-value or real
social experiment is claimed. This route is a separate financial-agent CLI/API,
not a hidden stage of every strategic UI run.

## Validation work required for a stronger thesis

1. Define one outcome/horizon and point-in-time evidence policy before collecting
   results. Separate creator-withdrawable cash, attention, risk and utility.
2. Assemble dated resolved crypto cases and explain exclusions, venue coverage,
   missing trades, survivorship and wallet-identity uncertainty.
3. Compare against base rates, simple rules and a single-model baseline under
   the same information, token/call budgets and frozen evaluation protocol.
4. Use temporal holdout and report Brier/log loss, reliability and uncertainty;
   do not tune on the test period. Test robustness to source/model/prompt changes.
5. Ablate interactions, motivations and information links. Determine whether the
   extra agent machinery improves a measurable task enough to justify its cost.
6. Publish negative results and failed runs as well as demonstrations. Run a
   separate customer study for decision usefulness, not just predictive skill.

The lecture coverage manifest records what was actually
accessed from the user's playlists. Yale formal concepts and the Predictive
History lecturer's interpretive narratives have different evidential status.
No named historical “law,” ideological assertion or demographic stereotype is
encoded as a scientific theorem or a persona-generation constant.
