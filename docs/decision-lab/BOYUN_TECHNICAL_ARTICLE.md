# Boyun (拨云): A Self-Hosted Agent Swarm Simulation Engine for Formal Financial, Economic, and Strategic Decision Systems on NEAR

**Author:** Cherry Q  
**Project:** Boyun Protocol (`Boyun-core`, `Boyun-interface`, `Boyun-skills`)  
**Website & Interactive Demo:** [https://boyun-protocol.github.io/](https://boyun-protocol.github.io/)  
**Research Paper:** [*Boyun: Multi-Agent Simulation for Financial and Economic Decisions*](../whitepaper/main.pdf)  
**License:** AGPL-3.0-only  

![Boyun Hero Banner](../readme-assets/hero.jpg)

---

## Abstract

Evaluating decisions in multi-actor economic, financial, and institutional systems requires modeling how heterogeneous participants dynamically respond to policy interventions, external shocks, and one another under uncertainty. Existing computational tools force an artificial trade-off between two methodological extremes: **closed-form equilibrium or spreadsheet models**, which enforce algebraic conservation laws but compress strategic human adaptation into static scalar parameters; and **unconstrained large-language-model (LLM) social simulations**, which capture rich qualitative context and open-ended discourse but permit models to violate budget constraints, invent balances, and hallucinate state transitions.

Inspired by the **[MiroFish](https://github.com/666ghj/MiroFish)** and **[OASIS](https://github.com/camel-ai/oasis)** multi-agent simulation paradigm, **Boyun** (拨云, *bō yún* — *"parting the clouds"*, from the classical idiom 拨云见日, *"parting the clouds to reveal the sun"*) introduces a hybrid computational architecture that unifies **autonomous Agent Swarm reasoning** with **deterministic state accounting**. In Boyun, institutional, market, and governance participants operate as a bounded **Swarm of Agents** communicating across a formal **Directed Social Graph** $G = (V, E)$. At every discrete round or timestamped decision point, Boyun enforces a strict division of responsibility: **AI agents evaluate restricted local observations and score feasible actions; deterministic code enforces resource constraints and settles every numerical consequence.**

Grounded in three formal disciplines—**Game Theory**, **Directed Social Graphs**, and **Probability & Statistics**—Boyun provides a general-purpose simulation engine equipped with pluggable domain ledgers (**Strategic & Governance**, **Market Microstructure**, and **Collateralized Credit**), zero-API-cost local neural inference via the open-weight **Laya** model (alongside hosted **Jev** inference), and end-to-end integration across the **NEAR Protocol** stack for empirical state grounding, confidential compute, verifiable SHA-256 replay commitments, and post-simulation execution rails.

---

## 1. The Methodological Bottleneck in Multi-Actor Decision Systems

Why do well-specified economic policies, treasury allocations, governance disclosures, and mechanism designs frequently diverge from their pre-deployment projections? Across financial and institutional systems, macro-level outcomes rarely depend on a single operator acting against a passive background. Instead, they emerge from **coupled, path-dependent interactions** among heterogeneous actors with distinct incentives, asymmetric information, and hard balance-sheet limits:

1. **Strategic Coupling and Feedback**: An institutional participant's choice to commit capital, endorse a governance proposal, or provide liquidity depends on how peer actors, competitors, and independent analysts respond—and whether their joint actions cross critical system thresholds.
2. **Information Asymmetry and Propagation Lags**: Participants do not observe a shared, omniscient state vector. Disclosures, market catalysts, and peer signals propagate across specific communication channels with heterogeneous arrival delays.
3. **Hard Conservation and Feasibility Constraints**: No economic actor can spend resources exceeding liquid balances, execute trades without shifting reserve curves, or maintain undercollateralized debt positions below liquidation thresholds without triggering systemic intervention.

![Methodological Comparison: Static Models vs. Open-Ended LLM Chat vs. Boyun Hybrid Swarm Engine](../readme-assets/paradigm-comparison.png)

As illustrated in the methodological comparison above, neither classical spreadsheets nor unconstrained conversational agent frameworks can simultaneously satisfy all three requirements:

- **Static Equilibrium & Classical Agent-Based Models (ABMs)** guarantee exact accounting identities, yet rely on rigid, pre-programmed behavioral rules (`if/else` thresholds or fixed elasticities) that cannot interpret qualitative disclosures, changing narratives, or multi-dimensional strategic context.
- **Open-Ended LLM Roleplay Simulators** allow dozens of personas to converse naturally over shared social feeds, surfacing valuable qualitative perspectives. However, because narrative state and numerical state are conflated inside free-text prompts, an agent stating *"I commit $100,000 to stabilize the reserve"* does not deduct cash, update pool accounting, or prevent double-spending.
- **The Boyun Hybrid Paradigm** resolves this tension by combining **MiroFish's world-first Agent Swarm workflow** with **formal game-theoretic specification and deterministic ledger settlement**. Agents reason over qualitative and quantitative context through typed option distributions, while deterministic state machines govern every balance, metric, reserve, and debt invariant.

---

## 2. Formal Foundations of a Boyun World

![Three Formal Foundations of Boyun](../readme-assets/foundations.png)

Before a single inference call is dispatched, Boyun compiles a scenario into a formal, machine-validated **World Specification**. Every Boyun world rests on three mathematical foundations implemented directly in [`Boyun-core`](https://github.com/Boyun-Protocol/Boyun-core).

### 2.1 Game Theory: Heterogeneous Incentives, Feasibility Guards, and Equilibrium Kernels

In Boyun, the cast of participants is formalized as an interacting **Swarm of Agents** $i \in \{1, \dots, N\}$. Rather than relying on prose biography adjectives to make an agent "conservative" or "opportunistic," Boyun encodes incentives into an executable game-theoretic structure:

- **Resource Endowments & Pre-Inference Feasibility ($A_{i,t}$)**: Each agent $i$ holds explicit resource balances $b_{i,t}$ (alongside domain-specific holdings such as inventory, pledged collateral $Q_\ell$, or credit supply claims $c_s$). Prior to querying the decision model at step $t$, the engine filters agent $i$'s reviewed action menu $\operatorname{Menu}_i$ in deterministic code:
  $$A_{i,t} = \{a \in \operatorname{Menu}_i : c_i(a) \le b_{i,t}\}$$
  where $c_i(a)$ denotes the integer resource cost of action $a$. Infeasible actions are removed from the choice set *before* inference, guaranteeing by construction that no prompt interpretation can induce an agent to overspend.
- **Explicit Preference Weights & Cardinal Utility ($U_{i,t}$)**: In strategic and institutional worlds, each agent $i$ is parameterized by explicit preference weights $w_{i,\mathrm{cash}}$ and $w_{i,k}$ over shared state metrics $x_{k,t} \in [L_k, H_k]$ (such as institutional credibility, qualified participation, systemic risk, or governance alignment):
  $$U_{i,t} = w_{i,\mathrm{cash}}\, b_{i,t} + \sum_k w_{i,k}\, x_{k,t}$$
- **Joint-Action Coupling & Analytical Normal-Form Solver**: When subsets of agents execute complementary or conflicting actions simultaneously, joint-action rules $r \in R_t$ contribute non-additive interaction terms $g_{k,r}$. For compact normal-form subgames ($\le 4$ actors, $\le 256$ action profiles) with declared opponent belief distributions $\pi_i(a_{-i})$, Boyun's analytical game-theory kernel (`decision_lab/math_foundations.py`) computes exact expected utility and unilateral deviation regret:
  $$\mathrm{EU}_i(a_i) = \sum_{a_{-i}} \pi_i(a_{-i})\, U_i(a_i, a_{-i}), \qquad \mathrm{Reg}_i(a_i) = \max_{a' \in A_i} \mathrm{EU}_i(a') - \mathrm{EU}_i(a_i)$$
  alongside pure-strategy Nash equilibria and strict dominance verification.

---

### 2.2 Directed Social Graphs: Information Topology Across the Agent Swarm

![Directed Social Graph: Swarm of Agents](../readme-assets/social-graph.png)

Incentives alone do not determine *who observes which signal, and when*. If every agent in a simulation had read access to the master world file—including counterparties' private budgets, unannounced policy branches, and future scheduled catalysts—their decisions would suffer from omniscient look-ahead bias.

Boyun structures communication across the **Swarm of Agents** via a formal **Directed Social Graph** $G = (V, E)$, where vertices $V = \{1, \dots, N\}$ represent agents and directed edges $(j \to i) \in E$ define permitted information channels:

- **Restricted Per-Agent Observations ($O_{i,t}$)**: At step $t$, the engine constructs a canonical JSON observation object $O_{i,t}$ for agent $i$ containing *exclusively*:
  1. Agent $i$'s own identity, objective, preference weights, and private balances $b_{i,t}$.
  2. Publicly observable state variables (shared world metrics $x_{k,t}$, market reserve quotes, utilization rates, and oracle prices).
  3. Exogenous events whose declared availability timestamp $\tau_e \le \tau_t$ has arrived and whose target audience includes $i$.
  4. Peer messages emitted by sender $j$ at an earlier step where $(j \to i) \in E$ and the channel's delivery lag has elapsed.
- **Order-Independent Synchronous Delivery**: In round-based worlds, messages emitted during round $t$ are delivered to subscribed graph neighbors at the opening of round $t+1$. Consequently, the internal iteration order in which agents are queried within round $t$ cannot leak intra-round choices or introduce artificial first-mover artifacts.
- **Cryptographic Observation Pinning**: Every constructed observation $O_{i,t}$ is canonically serialized and hashed with `SHA-256` prior to model inference, creating an immutable audit trail of the exact information set conditioned upon by agent $i$ at step $t$.

---

### 2.3 Probability & Statistics: Bayesian Updating, Seeded Sampling, and Calibration

Economic and strategic analysis requires rigorous handling of both epistemic uncertainty and stochastic branching. Boyun integrates three formal statistical mechanisms while enforcing strict scientific boundaries against overclaiming:

1. **Exact Sequential Bayesian Updating**: Given a finite set of mutually exclusive hypotheses $H$, explicit prior probabilities $P(h)$, and conditional signal likelihoods $P(E \mid h)$, the engine updates posterior beliefs via Bayes' theorem:
   $$P(h \mid E) = \frac{P(E \mid h)\, P(h)}{\sum_{h' \in H} P(E \mid h')\, P(h')}$$
   Zero-denominator or unnormalized inputs are rejected explicitly rather than silently smoothed.
2. **Typed Option Distributions & Reproducible Selection Rules**: When queried with observation $O_{i,t}$ and feasible menu $A_{i,t}$, the agent decision model returns normalized **option scores** $q_{i,t}(a) \in [0,1]$ satisfying $\sum_{a \in A_{i,t}} q_{i,t}(a) = 1$. The engine maps $q_{i,t}(a)$ to a concrete executed action $a_{i,t}$ via a pre-declared selection rule—either deterministic **argmax** (with canonical action-ID tie-breaking) or **seeded inverse-CDF sampling**:
   $$\text{argmax: } a_{i,t} = \arg\max_{a \in A_{i,t}} q_{i,t}(a)$$
   $$\text{sampling: } a_{i,t} = a_{(m^\ast)}, \quad m^\ast = \min\left\{m : \sum_{\nu=1}^{m} q_{i,t}\big(a_{(\nu)}\big) > \xi_{i,t}\right\}$$
   where $\xi_{i,t} \in [0,1)$ is derived deterministically from a `SHA-256` stream keyed to `(seed, world_id, step, agent_id)`.
3. **Monte Carlo Quantiles & Proper Scoring Rules**: Across multi-seed ensembles, Boyun summarizes outcome dispersion via nearest-rank quantiles ($P_{05}, P_{50}, P_{95}$) and evaluates dated probabilistic predictions $p_n \in [0,1]$ against resolved binary outcomes $y_n \in \{0,1\}$ using the **Brier score** and **log-loss**:
   $$\mathrm{Brier} = \frac{1}{N} \sum_{n=1}^{N} (p_n - y_n)^2, \qquad \mathrm{LogLoss} = -\frac{1}{N} \sum_{n=1}^{N} \big[y_n \ln p_n + (1 - y_n) \ln(1 - p_n)\big]$$

---

## 3. System Architecture, Execution Pipeline & Pluggable Domain Ledgers

![Formal Step-t Execution & Evidence Pipeline](../readme-assets/execution-pipeline.png)

Boyun's core runtime (`Boyun-core`) is architected as a modular, domain-general simulation engine. As shown in the step-$t$ execution pipeline above, every simulation step $\tau_t$ ($t \in \{1, \dots, T\}$) passes through six verifiable stages:

1. **Stage 01 — Exogenous Schedule & Committed Operator Plan Execution**: Scheduled external catalysts and pre-committed operator plans (such as scheduled disclosures, capital deployments, or funded incentive programs) execute first and deduct payer budgets *before* independent swarm agents observe the resulting state and react.
2. **Stage 02 — Directed Social Graph Observation Pinning**: For each active agent $i$, the runtime builds $O_{i,t}$ along $G = (V, E)$ and records `SHA-256(O_{i,t})`.
3. **Stage 03 — Hard Affordability Filtering**: The feasibility guard constructs $A_{i,t}$. Whenever $|A_{i,t}| = 1$ (only `wait` is affordable), `wait` is recorded immediately without expending a model query.
4. **Stage 04 — Bounded Swarm Inference (`Laya` or `Jev`)**: The inference adapter verifies that returned option scores $q_{i,t}(a)$ are finite, span $A_{i,t}$ without extra keys, and sum to $1$ within a $\le 0.001$ tolerance. Any malformed response halts the step atomically prior to state mutation.
5. **Stage 05 — Atomic Deterministic Ledger Settlement**: The selected action profile $a_t = (a_{1,t}, \dots, a_{N,t})$ settles against one of Boyun's pluggable domain ledgers.
6. **Stage 06 — Offline Replay Verification & Cryptographic Commitment**: The recorded action trace is replayed offline without model calls to verify bit-identical state reproduction, compiled into a five-volume research report package, and optionally anchored on NEAR Testnet.

![How Boyun Works — End-to-End Architecture](../readme-assets/architecture.png)

### 3.1 Pluggable Domain Engine A: The Strategic & Governance Ledger

Designed for institutional policy evaluation, governance proposals, disclosure timing, regulatory stress-testing, and bilateral or multilateral strategic negotiations:
- Deducts integer resource costs atomically: $b_{i,t}^{+} = b_{i,t} - c_i(a_{i,t})$.
- Aggregates individual action effects $e_k(a_{i,t})$ and triggered joint-action coupling rules $g_{k,r}$ simultaneously across all participating agents, clamping shared state metrics once at round end:
  $$x_{k,t}^{+} = \operatorname{clip}_{[L_k, H_k]}\left(x_{k,t} + \sum_i e_k(a_{i,t}) + \sum_{r \in R_t} g_{k,r}\right)$$
- Enforces **Exact Resource Conservation** at every round:
  $$b_{i,t}^{+} \ge 0 \quad \text{and} \quad \sum_i b_{i,t}^{+} + S_t^{+} = \sum_i b_{i,0}$$
  where $S_t^{+}$ tracks cumulative cast expenditure.

### 3.2 Pluggable Domain Engine B: The Market Microstructure Ledger

Designed for spot market microstructure, liquidity provisioning, treasury execution policies, and automated market maker (AMM) or bonding-curve dynamics:
- Tracks exact integer cash and asset balances across all swarm participants and liquidity pools.
- Settles swaps against constant-product AMM reserves ($x \cdot y = k$) with configurable fee retention $f$ as well as virtual-reserve bonding curves:
  $$\Delta y = \frac{y \cdot \Delta x (1 - f)}{x + \Delta x (1 - f)}$$
- Enforces pre-trade slippage guards and inventory bounds: orders exceeding maximum permitted slippage or available balances are rejected atomically with a machine-readable rejection code (`SLIPPAGE_EXCEEDED`, `INSUFFICIENT_CASH`, `INSUFFICIENT_INVENTORY`).
- Strictly separates **realized liquid cash** from **unrealized mark-to-market inventory valuations** across all accounting tables.

### 3.3 Pluggable Domain Engine C: The Collateralized Credit & Liquidation Ledger

Designed for decentralized and institutional credit markets, interest-rate curve calibration, liquidity queue stress-testing, and collateral drawdown analysis:
- Tracks pool idle cash $C_t$, lent principal $P_t$, supplier share claims $c_s$, and first-in-first-out (FIFO) withdrawal queues whenever requested redemptions exceed $C_t$.
- Computes utilization $u_t = P_t / (C_t + P_t)$ and evaluates the **kinked utilization interest-rate model**:
  $$r(u_t) = \begin{cases} r_0 + (r^\ast - r_0)\,\frac{u_t}{u^\ast}, & u_t \le u^\ast \\ r^\ast + (r_1 - r^\ast)\,\frac{u_t - u^\ast}{1 - u^\ast}, & u_t > u^\ast \end{cases}$$
- Accrues simple interest $I_\ell = P_\ell \, r(u_t)\, \Delta t / Y$ over elapsed seconds $\Delta t$ between the protocol reserve (share $\varphi$) and suppliers on a deterministic $\epsilon = 10^{-12}$ precision grid:
  $$\Delta I_\ell^{\mathrm{prot}} = \lfloor \varphi I_\ell \rfloor_\epsilon, \qquad \Delta I_\ell^s = \left\lfloor (1 - \varphi) I_\ell \frac{c_s}{\sum_{s'} c_{s'}} \right\rfloor_\epsilon$$
- Evaluates each loan $\ell$'s **Health Factor** at every oracle price update:
  $$h_\ell = \frac{Q_\ell \, p_t \, \theta}{D_\ell \, p_t^{\mathrm{usd}}}$$
  where $Q_\ell$ is pledged collateral at price $p_t$, $\theta$ is the liquidation threshold, and $D_\ell$ is principal plus accrued debt. When $h_\ell < 1$, liquidator agents repay debt (up to the close factor, or $100\%$ when $h_\ell \le 0.95$) in exchange for collateral plus liquidation bonus $\beta$, constrained by liquidator cash and secondary market exit depth; unrecovered underwater debt writes off against a capped protocol loss reserve.

### 3.4 Self-Hosted Local Inference (`Laya`) vs. Hosted Inference (`Jev`)

Executing a 16-to-20 agent swarm across 24 matched policy worlds and hundreds of hourly decision timestamps requires **more than 130,000 typed agent inferences**. Routing 130,000 prompts through commercial cloud APIs is both cost-prohibitive and leaks sensitive, unpublished strategic parameters (treasury caps, reserve thresholds, and contingency schedules) to external providers.

Boyun decouples the simulation runtime from any single model vendor via a unified adapter interface:
- **Local `Laya` Engine (Default Self-Hosted Path)**: Executes an open-weight GGUF agent decision model locally on CPU/Metal (`decision_lab/laya.py`). It incurs **$0.00 in API fees**, keeps all scenario observations 100% on-device, enforces a strict 1024-token context ceiling, and emits normalized JSON option scores $q_{i,t}(a)$.
- **Hosted `Jev` Engine (TypeSafe System One)**: Connects to remote typed decision endpoints (`decision_lab/jev.py`) with mandatory pre-run cost estimation, hard call-allowance ceilings, and per-call token/spend receipts.
- **Deterministic Offline Baseline**: A zero-model immediate-utility rule (`decision_lab/offline_decisions.py`) for rapid CI verification, game construction audits, and zero-dependency local exploration.

---

## 4. Architecture & Integration Across the NEAR Protocol Stack

![Boyun x NEAR Protocol Architecture Stack](../readme-assets/near-stack.png)

Boyun is designed as a native decision and verification layer within the **NEAR Protocol** ecosystem. In accordance with our scientific evidence standard, the architecture diagram and table below explicitly distinguish **deployed on-chain contracts and implemented runtime adapters** from **proof-of-concept (PoC) and formal architectural specifications**:

| Architectural Layer | Module / Artifact | Technical Mechanism in Boyun | Status |
| :--- | :--- | :--- | :--- |
| **1. On-Chain Integrity Registry** | `contracts/commitment-registry` & `near_registry.py` | Rust (`near-sdk 5.29.1`) smart contract deployed at `csl-registry-2e4069fc870d.testnet`. Anchors salted `SHA-256` simulation digests on-chain with code-hash pinning (`9Fc8Eu3Tj589sxW5oQngK4MqrmTgA2zuaU2JzK1uVcS7`) and RPC finality verification. | **Deployed & Verified on NEAR Testnet** |
| **2. Browser Wallet Signing** | `product_near.py` & `Boyun-interface` | Pinned **NEAR Wallet Selector (Intear adapter)** enabling operators to connect a NEAR testnet wallet, inspect `register_commitment` payloads (`0.01 testNEAR` storage bound, `30 Tgas`), sign commitments, and export private opening receipts. | **Implemented** |
| **3. NEAR AI Cloud Adapter** | `near_ai.py` (`NearAITextModel`) | World-architect model adapter targeting `https://cloud-api.near.ai/v1/chat/completions` and `/v1/models` with canonical `organization/model` pinning, `x-no-aliasing: true`, no-redirect HTTPS transport, and cryptographic request/response receipts. | **Implemented** |
| **4. Confidential GPU TEE & E2EE** | `NEAR_TECH_GUIDE.md` & `NEAR_RESEARCH_FOUNDATIONS.md` | Formal verification specification grounded in *Decentralized Confidential Machine Learning* (Polosukhin, Skidanov, Le Guen) for hardware TEE enclave attestation, TLS key binding, and client-side E2EE world authoring. | **Architecture Specification** |
| **5. NEAR On-Chain Grounding & DeFi** | `near_demo.py`, `Boyun-skills`, & `lending.py` | Public NEAR JSON-RPC account/contract state snapshots, dated NEAR chain TVL ($175M) and Rhea DEX pool ($6.29M 24h volume) grounding registers, and a 90-day native NEAR collateral / USDC lending stress engine. | **Implemented & Evaluated** |
| **6. NEAR Intents (1Click & Confidential)** | `NEAR_TECH_GUIDE.md` | Post-simulation execution rail utilizing the NEAR Intents 1Click API (`dry: true` route quotes) and Confidential Intents to translate a selected Decision Record branch into a privacy-preserving liquidity or treasury settlement plan. | **PoC / Technical Specification** |
| **7. NEAR Chain Signatures (MPC)** | `NEAR_TECH_GUIDE.md` | Multi-party computation (MPC) signing specification allowing a single NEAR account to authorize constrained foreign-chain treasury or governance transactions once a simulation branch passes audit. | **Architecture Specification** |
| **8. NEAR Agent Market & IronClaw** | `NEAR_TECH_GUIDE.md` | Self-hosted worker specification wrapping `Boyun-core` inside an isolated **IronClaw** runtime so autonomous research agents can accept simulation jobs on **NEAR Agent Market** and return verified 5-report packages. | **Architecture Specification** |

### Resolving the Auditability–Privacy Dilemma via Salted NEAR Commitments

In institutional and protocol decision analysis, publishing raw simulation files on a public blockchain would expose proprietary budgets, internal risk tolerances, and unannounced policy schedules. Conversely, keeping simulation artifacts purely local permits post-hoc cherry-picking or retroactive alteration of parameters after real-world outcomes are observed.

Boyun resolves this dilemma through a **Salted Cryptographic Commitment Protocol** (`engine/src/decision_lab/integrity.py`):
1. Upon completing a simulation run, `Boyun-core` canonically serializes the result package bytes and generates a 32-byte cryptographic salt.
2. It computes a salted digest $H = \operatorname{SHA256}(\text{salt} \parallel \text{canonical\_bytes})$ and submits *only* $H$ to `csl-registry-2e4069fc870d.testnet` via the user's connected **Intear NEAR Wallet** (or the operator testnet relayer).
3. The Rust contract records the immutable first registration (`commitment`, `signer`, `block_height`, `block_timestamp_ns`) and automatically refunds any excess storage deposit.
4. All scenario text, persona observations, salt bytes, and raw artifact hashes remain **100% off-chain**. When the operator subsequently elects to share the study with governance voters, risk committees, or external auditors, providing the artifact alongside the private opening file allows any verifier to confirm via `Verify from NEAR` that the exact simulation package existed prior to the decision timestamp—and to re-run `decision-lab` offline replay to verify every ledger transition.

---

## 5. Methodological Guidelines & Operational Workflows

Boyun is organized across three open-source repositories so researchers and engineering teams can run it headlessly in CI/CD, interactively in a browser workbench, or through an AI coding assistant:

- **[Boyun-core](https://github.com/Boyun-Protocol/Boyun-core)**: Core Python simulation engine, domain ledgers, model adapters, CLI, HTTP API server, Model Context Protocol (MCP) server, report compilers, and NEAR smart contract.
- **[Boyun-interface](https://github.com/Boyun-Protocol/Boyun-interface)**: Browser workbench UI, guided scenario setup flow, trajectory inspector, and Intear NEAR Wallet bundle.
- **[Boyun-skills](https://github.com/Boyun-Protocol/Boyun-skills)**: First-party skill packs (`boyun-world-grounding` and `boyun-financial-reports`) for Claude Code, Codex, Cursor, and Cindy.

### 5.1 Four Principles for Rigorous Scenario Design

To produce decision-grade analytical evidence, Boyun enforces four methodological guidelines codified in `docs/decision-lab/SIMULATION_EVIDENCE_STANDARD.md`:

1. **Formulate Matched Counterfactual Branches**: Define the exact policy variable under operator control (e.g., *incentive budget sizing*, *disclosure timing*, *interest-rate kink parameters*, or *drawdown contingency rules*). Hold initial endowments, pseudorandom seeds, and exogenous event schedules identical across matched branches so outcome differences isolate the policy intervention.
2. **Execute Committed Operator Plans Prior to Swarm Reaction**: Never model an operator's already-committed schedule (such as a dated governance proposal, reserve injection, or scheduled campaign) as an optional guess. Encode committed plans explicitly so Stage 01 executes and deducts their costs *before* independent swarm agents observe the state and respond.
3. **Maintain Strict Provenance Between Empirical Data and Labeled Assumptions**: Every material parameter in a Boyun world must trace either to a **dated external source** (with an `as-of` timestamp, unit, and citation) or an explicitly labeled **modeling assumption**. Never conflate assumed behavioral weights with calibrated market probabilities.
4. **Encode Behavioral Differentiation in Numeric Weights and Graph Topology**: Changing adjectives in a persona's biography does not alter ledger settlement. Differentiate agents via numeric preference weights $w_{i,\mathrm{cash}}, w_{i,k}$, resource endowments $b_{i,0}$, action costs $c_i(a)$, and directed Social Graph edges $(j \to i) \in E$.

---

### 5.2 Workflow 1: Headless CLI & Guided Scenario Journey (Zero-Key Quick Start)

**Prerequisites:** Python `>=3.11` and [`uv`](https://docs.astral.sh/uv/).

```bash
# Clone Boyun-core and Boyun-interface into sibling directories
git clone https://github.com/Boyun-Protocol/Boyun-core.git
git clone https://github.com/Boyun-Protocol/Boyun-interface.git
cd Boyun-core

# Synchronize the engine, PDF report compiler, and developer test suite
uv sync --project engine --extra pdf --dev
```

Execute an interactive, guided scenario journey directly in the terminal using the deterministic offline baseline (requiring zero API keys or external network calls):

```bash
uv run --project engine --extra pdf decision-lab journey \
  --offline --format both --output-dir engine/output/my-first-journey
```

During `decision-lab journey`:
1. The CLI guides the operator through selecting a decision domain, horizon, and matched policy comparison while displaying a live stage and progress header on every prompt surface.
2. Before execution, it runs automated **Game Construction Audits** (`game_construction_audit`), verifying resource conservation, non-empty feasible menus, unilateral utility deltas, and Social Graph connectivity.
3. Upon confirmation (`RUN`), the engine executes all rounds, verifies bit-identical offline replay, and compiles `scenario-report.md` and `scenario-report.pdf`.

---

### 5.3 Workflow 2: Interactive Browser Workbench & Intear NEAR Wallet Signing

To launch the full visual workbench supporting local `Laya`, hosted `Jev`, `NEAR AI Cloud`, and browser-based **Intear NEAR Testnet Wallet** commitments:

```bash
uv run --project engine --extra pdf --with-editable ../Boyun-interface \
  decision-lab serve --port 8769
```

Navigate to **`http://127.0.0.1:8769/`**:

1. **Guided World Setup**: Step through structured setup cards to configure the focal decision question, Agent Swarm cast, preference trade-offs, and counterfactual branches—or load a pre-grounded NEAR ecosystem world via **Try a free example**.
2. **Inference & Privacy Configuration**:
   - Select **Offline — local rules** for instantaneous deterministic baseline execution.
   - Select **Local Laya (GGUF)** for zero-API-cost, on-device neural option scoring.
   - Or configure a session-only **TypeSafe (`Jev`)** or **NEAR AI Cloud** key under **AI & privacy** (keys reside strictly in volatile process memory and require explicit pre-run budget approval).
3. **Trajectory Inspection & Replay**: Compare cash, utility, reserve, or utilization trajectories across matched branches, and audit round-by-round settlement logs and rejected actions.
4. **On-Chain Commitment via NEAR Testnet**:
   - Select **Record on NEAR testnet** on the summary view to compute a salted `SHA-256` commitment for the exact result package bytes.
   - Click **Connect testnet wallet** to authenticate via the **Intear NEAR Wallet Selector**, inspect the `register_commitment` transaction against `csl-registry-2e4069fc870d.testnet`, and sign—or submit via the operator testnet relayer.
   - Use **Verify from NEAR** at any time to confirm `final_verified` block finality and code-hash agreement.

---

### 5.4 Workflow 3: 15–30 Minute Automated World Grounding & Math Verification via Coding Agents (`MCP` + `Boyun-skills`)

<table>
<tr>
<td width="50%"><img src="../readme-assets/skills-data.png" alt="Boyun Empirical Data Grounding Skill" width="100%"/></td>
<td width="50%"><img src="../readme-assets/skills-math.png" alt="Boyun Mathematical Mechanism Verification Skill" width="100%"/></td>
</tr>
<tr>
<td align="center"><b>1. Empirical Data Grounding Skill (<code>boyun-world-grounding</code>)</b></td>
<td align="center"><b>2. Mathematical Mechanism &amp; Report Skill (<code>boyun-financial-reports</code>)</b></td>
</tr>
</table>

Rather than authoring complex JSON world specifications manually, operators can connect an AI coding agent (**Claude Code**, **Codex**, **Cursor**, **Gemini**, or **Cindy**) to Boyun's local **Model Context Protocol (MCP)** server alongside [`Boyun-skills`](https://github.com/Boyun-Protocol/Boyun-skills):

```bash
# 1. Clone Boyun-skills and install the skill packs into your coding agent
git clone https://github.com/Boyun-Protocol/Boyun-skills.git

# 2. Launch the Boyun-core MCP server over stdio
uv run --project engine --extra mcp decision-lab mcp --workspace engine/output/mcp
```

With both skills active, constructing and executing a full multi-branch empirical study takes **15 to 30 minutes**:
1. **Structured Operator Interview**: The coding agent conducts a concise, progress-tracked interview to establish the decision question, policy branches, time horizon, and institutional constraints.
2. **Empirical Data Grounding**: The agent queries live market and protocol data sources (NEAR JSON-RPC, DeFiLlama TVL, GeckoTerminal / Rhea DEX liquidity, TokenTerminal filings) to compile a dated **Evidence Register** where every empirical input carries an explicit `as-of` timestamp, unit, and source URL (recording data gaps transparently rather than fabricating proxies).
3. **Mathematical Mechanism Verification**: The agent formulates the exact domain equations (strategic utility matrices, AMM slippage bounds, or kinked utilization and health-factor thresholds), writes the world specification, and invokes `validate_strategic_world` and `game_construction_audit` over MCP to verify conservation invariants prior to simulation.
4. **Five-Volume Research Casebook Compilation**: Following simulation and bit-identical replay verification, `boyun-financial-reports` compiles an institutional-grade five-report package:
   - **`01-WORLD-CREATION`**: Problem formulation, dated evidence register, Agent Swarm cast, preference weights, Social Graph topology, and labeled modeling assumptions.
   - **`02-BEAR-CASE`**: Downside and stress-regime trajectory analysis, liquidity/collateral bottlenecks, and capital preservation invariants.
   - **`03-BULL-CASE`**: Expansion-regime trajectory analysis, capacity utilization, and upside capture dynamics.
   - **`04-TECHNICAL-REPORT`**: Step-by-step ledger accounting, option-score distributions $q_{i,t}(a)$, atomic rejection logs, and deterministic replay verification receipts.
   - **`05-DECISION-RECORD`**: Counterfactual branch comparison matrix, separation of mechanical invariants from model-sensitive conclusions, and an actionable pre-deployment checklist.

![Boyun 5-Report Analytical Package](../readme-assets/report-package.png)

---

## 6. Empirical Evaluation: Synthetic Mechanism Kernels & Full-Horizon Case Studies

To evaluate both mathematical correctness and large-scale operational behavior, we benchmarked Boyun across **six controlled mechanism verification experiments**, **two full-horizon multi-agent case studies executed locally with `Laya`**, and a **matched-brief architectural comparison with `MiroFish`**.

### 6.1 Six Controlled Mechanism Verification Benchmarks

Executed completely offline (`python3 -m pytest engine/tests tools/tests`), six synthetic benchmarks confirm that Boyun's mathematical kernels reproduce analytical ground truth byte for byte:

1. **Normal-Form Equilibrium & Regret Solver**: On a $2 \times 2$ strategic game with payoffs $U_1(A,C)=4, U_1(A,D)=1, U_1(B,C)=2, U_1(B,D)=3$ and opponent beliefs $\pi_1(C)=1/3, \pi_1(D)=2/3$, reproduces exact expected utilities $\mathrm{EU}_1(A)=2.0$, $\mathrm{EU}_1(B)=2.6667$, best response $B$, deviation regret $\mathrm{Reg}_1(A)=0.6667$, and pure Nash equilibrium $(B,D)$.
2. **Sequential Bayesian Belief Updating**: Given balanced priors $(0.5, 0.5)$ and signal likelihoods $(0.8, 0.2)$, reproduces exact posterior probabilities $(0.8, 0.2)$ after one signal and $(16/17, 1/17) \approx (0.941176, 0.058824)$ after two conditionally independent signals.
3. **Synchronous Multi-Round Settlement & Replay**: Verifies exact cash conservation ($200\text{¢}$ initial endowment $= 80\text{¢}$ retained $+ 120\text{¢}$ expended), boundary clamping $[0,10]$, round-$t+1$ Social Graph message arrival, and bit-identical offline replay.
4. **Proper Scoring Rule Calibration**: Reproduces exact Brier ($0.0625$) and log-loss ($0.287682$) values against a chronological training baseline ($0.25$ and $0.693147$).
5. **Social Graph Topology vs. Payoff Coupling Ablation**: Isolates information routing from payoff interaction—removing a joint-action coupling rule lowers final readiness from $6$ to $3$ without altering the recipient's action choice, whereas severing the directed Social Graph edge $(A \to B)$ deprives agent $B$ of the signal, causing $B$ to select `wait` and keeping readiness at $1$.
6. **Numeric Preference Weights vs. Narrative Biography Prose**: Demonstrates in an 8-agent institutional world that shifting an actor's numeric risk weight from $-500$ to $-5{,}000$ flips the equilibrium decision and reduces total cast expenditure from $120{,}000\text{¢}$ to $110{,}000\text{¢}$, whereas rewriting all persona biographies to emphasize extreme caution while holding numeric weights fixed produces zero change in settled outcomes.

---

### 6.2 Empirical Benchmark 1: 24-World Market Microstructure & Treasury Policy Matrix (16-Agent Swarm · 136,841 Local `Laya` Inferences)

![24-World Market Microstructure Price Trajectories](../readme-assets/price-paths.png)

To stress-test the **Market Microstructure Ledger** across a high-dimensional policy factorial, we evaluated a 14-day (336-hour) spot market and bonding-curve scenario across **24 matched worlds**:

- **Factorial Design**: $2 \text{ macro regimes (\textit{BULL} / \textit{BEAR})} \times 3 \text{ capital endowments (\$5K, \$10K, \$15K)} \times 2 \text{ upfront cost structures} \times 2 \text{ drawdown contingency rules (\textit{Pause \& Observe} vs. \textit{Staged Exit})}$.
- **Swarm Topology & Scale**: A **16-agent swarm** (operator treasury, marketing operator, liquidity pool, whale cohorts, momentum traders, and retail cohorts) communicating across a directed Social Graph over 336 hourly steps and dated external catalysts. All **24 worlds** completed the full 336-hour horizon (**8,064 simulated path-hours**, **8,754 decision points**, and **136,841 local `Laya` option-scoring calls**) on consumer hardware at **$0.00 API cost**, settling **50,251 filled trades** ($16.77M cumulative notional volume) and recording **11,350 atomic slippage and balance rejections**.
- **Structural Insight (Liquid Treasury Extraction vs. Equilibrium Reserve Depth)**:
  - Across all 12 matched branch pairs, the **Staged Exit** rule (liquidating treasury tranches when trailing 6-hour volume falls below threshold) yielded **$1,546.54 to $10,330.65 higher realized liquid cash** than **Pause & Observe**, because tranche liquidations directly convert inventory into cash.
  - However, the 24-world price trajectory ensemble above exposes the exact dual consequence on market depth: **Pause & Observe** preserves AMM counter-asset reserves and sustains substantially higher terminal prices (**28.6 $\mu\$$, 51.2 $\mu\$$, and 95.6 $\mu\$$** across the $5K, $10K, and $15K tiers at Hour 336) relative to **Staged Exit** (**11.9–13.2 $\mu\$$**), where automated tranche sales depress the reserve curve by **54% to 88%**. When retained inventory is marked to terminal pool quotes, Pause & Observe outperforms in 6 of the 12 matched pairs—quantifying the precise trade-off between immediate cash realization and market reserve stability.

---

### 6.3 Empirical Benchmark 2: 90-Day Collateralized Credit & Liquidation Stress Suite on NEAR (20-Agent Swarm)

![90-Day NEAR Collateralized Lending Simulation](../readme-assets/lending-paths.png)

To evaluate the **Collateralized Credit & Liquidation Ledger**, we simulated a 90-day (2,160-hour) **NEAR-collateralized USDC lending market** populated by a **20-agent swarm** (protocol operator, institutional and retail USDC suppliers, leveraged and conservative NEAR borrowers, arbitrage liquidators, and an external benchmark venue):

- **Experimental Design**: Four 90-day policy worlds comparing base ($100K) vs. expanded ($200K) supplier incentive budgets, standard vs. conservative kinked utilization rate curves, and historical NEAR hourly price paths vs. a stressed **35% collateral drawdown** trajectory, all scored locally by `Laya` (**2,880 decision points**, **21,600 agent decisions**, **$0.00 API cost**).
- **Structural Insight (Mechanical Invariants vs. Model Behavioral Sensitivity)**:
  - Active USDC liquidity grew from **$1.25M to $1.95M** while borrowed principal reached **$0.29M** (bounded by per-borrower debt ceilings), accruing **$4,296.46 to $4,707.01** in deterministic pool interest.
  - Under the 35% NEAR collateral drawdown branch, borrower health factors $h_\ell$ breached the $1.0$ threshold, triggering **13 automated liquidations** that repaid **$89,259.68** of debt and seized **$96,400.45** of NEAR collateral with **zero bad-debt write-offs** under the modeled liquidator cash and DEX exit depth constraints.
  - Crucially, Boyun's Technical Report explicitly separates **mechanical conclusions** (utilization curve accounting, debt ceilings, and liquidation health-factor math) from **behavioral sensitivities** (identifying that `Laya`'s uncalibrated option scores favored borrowing across both rate curves, motivating empirical borrower-elasticity calibration before committing additional incentive capital).

---

### 6.4 Architectural Comparison on a Matched Scenario Brief: `Boyun` and `MiroFish`

Executing the exact same scenario brief on upstream **MiroFish** (40 rounds on OASIS with Gemini 2.5 Flash across 37 social personas) alongside **Boyun** illustrates how the two architectures address complementary analytical layers:
- **MiroFish** excels at open-ended **qualitative discourse exploration**, generating **1,111 free-text posts and comments** that surface community skepticism, narrative framing, and conversational dynamics—while settling **0 financial transactions** and maintaining no resource ledgers.
- **Boyun** structures participants as a **constrained Agent Swarm over a Directed Social Graph** and settles **50,251 transactions** with exact reserve conservation, slippage rejection logs, counterfactual trajectory matrices, and bit-identical offline replay—demonstrating how MiroFish's world-first swarm paradigm can be coupled with formal economic accounting.

---

## 7. Scientific Boundaries, Automated Verification & Open-Source Repositories

Boyun enforces strict scientific discipline regarding what multi-agent simulations can and cannot claim:
- **Conditional Scenario Exploration, Not Point Forecasting**: Simulation outputs represent conditional trajectories under explicit ledger rules and declared modeling assumptions. They are not calibrated market forecasts or financial advice.
- **Uncalibrated Option Scores vs. Empirical Probabilities**: Neither local `Laya` nor hosted `Jev` option scores $q_{i,t}(a)$ constitute calibrated real-world probabilities. Establishing predictive forecasting skill requires pre-registered prospective resolution studies evaluated via proper scoring rules (Brier and log-loss) against historical base rates.

### Run the Automated Verification Suite

Every mathematical kernel, ledger invariant, source symbol, and smart contract in `Boyun-core` is continuously verified by **1,918+ automated tests**:

```bash
# 1. Execute the full Python engine, ledger, adapter, and report test suite
uv run --project engine --extra pdf --with-editable ../Boyun-interface \
  python -m pytest engine/tests tools/tests -q

# 2. Verify all 64 AST source symbols and documentation cross-references
python3 tools/build_evidence_docs.py --check

# 3. Execute the NEAR Commitment Registry Rust smart contract test suite
cargo test --locked --manifest-path contracts/commitment-registry/Cargo.toml
```

---

## 8. Companion High-Impression X Thread Adaptation (10-Post Visual Thread)

For publishing on X alongside or pointing to the full X Article, the thread below adapts the article into a concise, high-contrast 10-post technical thread where each post pairs one core architectural thesis with one visual diagram:

### Post 1/10 — Thesis & Visual Hook (`hero.jpg`)
```text
Introducing Boyun (拨云): an open-source, self-hosted Agent Swarm simulation engine for formal financial, economic, and strategic decision systems on @NEARProtocol.

> Autonomous Swarm of Agents communicating over a Directed Social Graph
> Deterministic Strategic, Market (AMM), and Credit ledgers
> Local Laya neural inference ($0 API cost) + on-chain NEAR verification

Paper, code & live walkthrough 🧵👇
```
*Attach:* `docs/readme-assets/hero.jpg`

### Post 2/10 — The Methodological Bottleneck (`paradigm-comparison.png`)
```text
1/ Why do economic policies, liquidity allocations, and mechanism designs diverge from pre-deployment projections?

> Static spreadsheets & closed-form models enforce accounting identities, but compress strategic human adaptation into rigid constants.
> Unconstrained LLM social chats generate expressive dialogue, but models invent balances, ignore budgets, and hallucinate settlement.

Boyun bridges both worlds: AI agents score bounded actions from restricted observations; deterministic code validates feasibility and settles every number.
```
*Attach:* `docs/readme-assets/paradigm-comparison.png`

### Post 3/10 — Three Formal Foundations (`foundations.png`)
```text
2/ Inspired by @666ghj's MiroFish & OASIS, every Boyun world is compiled into a machine-verified specification built on three formal pillars:

> Game Theory: Explicit resource endowments b_{i,t}, pre-inference affordability guards A_{i,t}, cardinal utility weights, and normal-form Nash/regret kernels.
> Directed Social Graphs: Formal information topology G=(V,E) controlling who observes which signal and when.
> Probability & Statistics: Sequential Bayesian updating, seeded inverse-CDF sampling, and Brier/log-loss calibration rules.
```
*Attach:* `docs/readme-assets/foundations.png`

### Post 4/10 — Directed Social Graph & Swarm Topology (`social-graph.png`)
```text
3/ In a multi-actor system, incentives alone do not determine who knows what, and when.

> Boyun connects its Swarm of Agents through a Directed Social Graph G=(V,E).
> At step t, each agent i receives a restricted JSON observation O_{i,t} containing only its own private state, public ledger metrics, arrived catalysts, and peer messages along directed edges (j -> i).
> Synchronous round t+1 delivery eliminates loop-order bias, and every O_{i,t} is pinned with SHA-256 before inference.
```
*Attach:* `docs/readme-assets/social-graph.png`

### Post 5/10 — Step-$t$ Execution Pipeline & Pluggable Ledgers (`execution-pipeline.png`)
```text
4/ Inside a single Boyun simulation step tau_t:

> Stage 01: Execute scheduled exogenous events & committed operator plans first.
> Stage 02-03: Pin SHA-256 graph observations O_{i,t} and filter affordable menus A_{i,t} in code.
> Stage 04: Score options q_{i,t}(a) locally via Laya (GGUF, $0 API cost) or hosted Jev.
> Stage 05: Settle atomically across pluggable Strategic, Market Microstructure (x*y=k AMM & bonding curves), or Collateralized Lending (kinked rates & health factor h_l) ledgers.
> Stage 06: Verify bit-identical offline replay.
```
*Attach:* `docs/readme-assets/execution-pipeline.png`

### Post 6/10 — End-to-End NEAR Protocol Integration Stack (`near-stack.png`)
```text
5/ Boyun is deeply integrated across the @NEARProtocol & @near_ai stack, with clear boundaries between live deployed modules and architectural specs:

> Deployed on NEAR Testnet: Rust Commitment Registry (`csl-registry-2e4069fc870d.testnet`) + Intear Wallet Selector signing.
> Implemented Adapters: `NearAITextModel` Cloud adapter (`x-no-aliasing: true`), NEAR JSON-RPC grounding, and native NEAR collateral lending engine.
> PoC & Specs: Confidential GPU TEE / E2EE world authoring, NEAR Intents (1Click & Confidential), Chain Signatures (MPC), and IronClaw workers on NEAR Agent Market.
```
*Attach:* `docs/readme-assets/near-stack.png`

### Post 7/10 — 15–30 Minute World Construction via MCP Skills (`skills-data.png` & `skills-math.png`)
```text
6/ How do you build a custom simulation world without hand-writing thousands of lines of JSON?

Connect Claude Code, Codex, Cursor, or Cindy to Boyun's MCP server + `Boyun-skills`:
> `boyun-world-grounding`: Interviews the operator and pulls dated on-chain/market data (NEAR RPC, DeFiLlama, Rhea DEX) into a cited Evidence Register.
> `boyun-financial-reports`: Verifies AMM, lending, and utility equations via `game_construction_audit` and compiles a 5-volume financial research package.
```
*Attach:* `docs/readme-assets/skills-data.png` and `docs/readme-assets/skills-math.png`

### Post 8/10 — Empirical Benchmark 1: 24-World Market Microstructure Matrix (`price-paths.png`)
```text
7/ Benchmark 1: A 14-day (336-hour) Market Microstructure Matrix across 24 matched policy worlds and a 16-agent swarm.

> 8,064 simulated path-hours | 136,841 local Laya neural decisions | $0.00 API cost | 50,251 settled trades | 11,350 atomic slippage rejections.
> Isolates the exact structural trade-off between Staged Exit (yielding +$1.5K to +$10.3K realized liquid cash) and Pause & Observe (preserving AMM counter-asset reserves and 2x-7x higher terminal prices).
```
*Attach:* `docs/readme-assets/price-paths.png`

### Post 9/10 — Empirical Benchmark 2: 90-Day NEAR Collateralized Credit Suite (`lending-paths.png`)
```text
8/ Benchmark 2: A 90-day (2,160-hour) NEAR-collateralized USDC lending simulation with a 20-agent swarm (suppliers, borrowers, liquidators, operator).

> 21,600 local Laya decisions across base ($100K) vs. expanded ($200K) incentive budgets and a 35% NEAR collateral drawdown stress branch.
> Automatically triggers 13 health-factor liquidations ($89.3K debt repaid, $96.4K collateral seized, zero bad debt) while separating mechanical rate invariants from model behavioral sensitivity.
```
*Attach:* `docs/readme-assets/lending-paths.png`

### Post 10/10 — Five-Volume Research Package & Open-Source Links (`report-package.png`)
```text
9/ Every Boyun study compiles into an auditable 5-report package (World Creation, Bear Case, Bull Case, Technical Report, Decision Record) that can be committed via salted SHA-256 digest to NEAR Testnet while keeping scenario text 100% private.

Explore the open-source stack (AGPL-3.0, 1,918+ automated tests):
> Interactive Demo & Whitepaper: https://boyun-protocol.github.io/
> Boyun-core: https://github.com/Boyun-Protocol/Boyun-core
> Boyun-interface: https://github.com/Boyun-Protocol/Boyun-interface
> Boyun-skills: https://github.com/Boyun-Protocol/Boyun-skills
```
*Attach:* `docs/readme-assets/report-package.png`
