# Boyun (拨云): Parting the Clouds — Self-Hosted Agent Swarm Simulation for Financial and Economic Decisions on NEAR

**Author:** Cherry Q  
**Project:** Boyun Protocol (`Boyun-core`, `Boyun-interface`, `Boyun-skills`)  
**Website & Interactive Demo:** [https://boyun-protocol.github.io/](https://boyun-protocol.github.io/)  
**Research Paper:** [*Boyun: Multi-Agent Simulation for Financial and Economic Decisions*](../whitepaper/main.pdf)  
**License:** AGPL-3.0-only  

---

## Abstract & Executive Summary

Every high-stakes financial or economic decision—whether designing a decentralized lending market, allocating treasury liquidity, structuring a token launch, or stress-testing a governance disclosure policy—depends on how heterogeneous actors respond to one another over time under uncertainty. Yet the tools available to decision-makers today force an artificial choice between two flawed extremes:

1. **Static Spreadsheets and Equilibrium Formulas**, which compress strategic human behavior into fixed scalar assumptions and cannot capture how whales, retail traders, liquidity providers, borrowers, and competitors dynamically react to a committed plan and to one another.
2. **Unconstrained Language-Model Roleplay**, which generates expressive narrative dialogue but allows models to invent numbers, ignore budget constraints, violate conservation of funds, and hallucinate protocol accounting.

Inspired by **[MiroFish](https://github.com/666ghj/MiroFish)** and the **[OASIS](https://github.com/camel-ai/oasis)** multi-agent simulation paradigm, **Boyun** (拨云, *bō yún* — *"part the clouds"*, from the classical idiom 拨云见日, *"parting the clouds to reveal the sun"*) bridges this methodological gap. Boyun is an open-source, self-hosted **Agent Swarm simulation engine** in which market and protocol participants operate as autonomous **agents** communicating across a directed **Social Graph** inside a formally specified digital world.

At every simulation step, Boyun enforces a strict architectural separation: **AI agents choose bounded actions from restricted observations; deterministic code validates feasibility and settles every numerical consequence.** Built on three formal pillars—**Game Theory**, **Directed Social Graphs**, and **Probability & Statistics**—Boyun executes scenarios across three specialized accounting engines (**Strategic**, **Market AMM / Bonding Curve**, and **Lending / Liquidation** ledgers), runs tens of thousands of typed agent decisions locally on consumer hardware via the open-weight **Laya** model at zero API cost (or via hosted **Jev** inference), and integrates deeply across the **NEAR Protocol** ecosystem for on-chain grounding, world authoring, verifiable SHA-256 replay commitments, and post-simulation execution rails.

![Boyun Hero Banner](../readme-assets/hero.jpg)

---

## 1. The Methodological Gap in Economic & Protocol Decision Analysis

When a team prepares a capital allocation or protocol mechanism change, the outcome is rarely determined by a single actor in isolation. Suppose a protocol team commits a marketing and liquidity budget across a 14-day schedule, or launches a 90-day collateralized lending market on NEAR with a points-based supplier incentive program. What actually happens next depends on coupled, path-dependent interactions:

- **Strategic Interdependence**: A liquidity partner's willingness to supply capital depends on whether independent analysts verify the reserve disclosure and whether early borrowers push pool utilization past the interest-rate kink.
- **Asymmetric Information & Timing**: Not every participant sees every signal at the same time. An announcement, an on-chain whale transfer, or an external market shock propagates through specific channels with measurable reporting lags.
- **Hard Resource & Protocol Constraints**: No participant can spend cash they do not hold, buy tokens without moving the Automated Market Maker (AMM) reserve curve, or borrow against collateral below the liquidation health threshold without triggering liquidator intervention.

Traditional agent-based models (ABMs) capture explicit rules but rely on rigid, hand-coded heuristics that cannot interpret qualitative context (such as a governance announcement or a regulatory catalyst). Conversely, recent LLM-based social simulators excel at open-ended discourse over a shared feed, but an expressed narrative intention (*"I will support the pool with $50,000"*) does not by itself deduct cash, update pool reserves, accrue interest, or conserve balances.

**Boyun** resolves this tension by combining **MiroFish's world-first Agent Swarm workflow** with **formal game-theoretic specification and deterministic ledger settlement**.

---

## 2. Three Formal Foundations of a Boyun World

![Three Foundations of Boyun](../readme-assets/foundations.png)

Before a single model query is dispatched, Boyun constructs an explicit, auditable **World Specification**. Every world is grounded in three mathematical foundations:

### 2.1 Game Theory: Heterogeneous Incentives, Budgets, and Strategic Coupling

In Boyun, the cast of participants is modeled as an interacting **Swarm of Agents** $i \in \{1, \dots, N\}$. Rather than relying on prose biographies to make an agent "cautious" or "aggressive," Boyun gives every agent an executable game-theoretic structure:

- **Resource Endowments & Constraints**: Each agent $i$ holds an explicit pre-decision balance $b_{i,t}$ (and, in market or lending worlds, token inventory, collateral $Q_\ell$, or pool supply claims $c_s$).
- **Affordable Action Menu ($A_{i,t}$)**: Before querying the agent decision model at step $t$, the engine filters agent $i$'s reviewed action menu $\operatorname{Menu}_i$ against its current liquid resources in code:
  $$A_{i,t} = \{a \in \operatorname{Menu}_i : c_i(a) \le b_{i,t}\}$$
  where $c_i(a)$ is the integer cost of action $a$. Unaffordable actions are physically excluded from the choice set, guaranteeing that no prompt interpretation can cause an agent to overspend.
- **Explicit Preference Weights & Utility ($U_{i,t}$)**: In strategic worlds, each agent $i$ is assigned declared preference weights $w_{i,\mathrm{cash}}$ and $w_{i,k}$ over shared world metrics $x_{k,t} \in [L_k, H_k]$ (such as protocol credibility, qualified participation, or execution risk):
  $$U_{i,t} = w_{i,\mathrm{cash}}\, b_{i,t} + \sum_k w_{i,k}\, x_{k,t}$$
  A founder agent may weight participation heavily, while an institutional partner weights retained cash and credibility.
- **Strategic Coupling & Normal-Form Kernels**: Actions can trigger joint-action rules $r \in R_t$ when specific combinations of agents act simultaneously. For compact normal-form subgames ($\le 4$ actors, $\le 256$ profiles) with supplied opponent beliefs $\pi_i(a_{-i})$, Boyun's analytical kernel computes exact expected utility and deviation regret:
  $$\mathrm{EU}_i(a_i) = \sum_{a_{-i}} \pi_i(a_{-i})\, U_i(a_i, a_{-i}), \qquad \mathrm{Reg}_i(a_i) = \max_{a'} \mathrm{EU}_i(a') - \mathrm{EU}_i(a_i)$$
  alongside pure-strategy Nash equilibria and strict dominance checks.

### 2.2 Social Graphs: Directed Information Routing Across the Swarm

![Social Graph: Swarm of Agents](../readme-assets/social-graph.png)

Incentives alone do not determine *who knows what, and when*. If every agent in a simulation could read the world author's master state—including rivals' private budgets, hidden preference weights, and future scheduled events—their decisions would reflect omniscient hindsight rather than local market behavior.

Boyun connects the **Swarm of Agents** through an explicit **Social Graph**, formalized as a **directed information graph** $G = (V, E)$:

- **Restricted Per-Agent Observations ($O_{i,t}$)**: At step $t$, the engine constructs a canonical JSON observation for agent $i$ containing *only*:
  1. Agent $i$'s own persona, goal, preference weights, and private balances $b_{i,t}$.
  2. Publicly observable ledger state (shared metrics $x_{k,t}$, AMM pool reserves, lending utilization, and oracle prices).
  3. Exogenous events whose declared availability timestamp has arrived and whose audience includes $i$.
  4. Messages emitted by peer agents $j$ where a directed edge $(j \to i) \in E$ exists in the Social Graph and the message delivery delay has elapsed.
- **Order-Independent Synchronous Delivery**: Messages attached to step-$t$ actions arrive at subscribed recipients at step $t+1$ (or after their declared timestamp lag), ensuring that the internal loop order in which agents are queried never leaks information or creates an artificial first-mover advantage.
- **Cryptographic Observation Pinning**: Every constructed observation $O_{i,t}$ is serialized canonically and hashed with SHA-256 before inference, proving exactly what information was visible to agent $i$ at the moment of its choice.

### 2.3 Probability & Statistics: Bayesian Updating, Seeded Sampling, and Calibration

Financial scenarios involve both structural rules and epistemic uncertainty. Boyun incorporates three statistical mechanisms while maintaining strict scientific boundaries:

1. **Exact Bayesian Belief Updating**: Given a finite set of mutually exclusive hypotheses $H$, explicit priors $P(h)$, and signal likelihoods $P(E \mid h)$, Boyun updates posterior beliefs via Bayes' rule:
   $$P(h \mid E) = \frac{P(E \mid h)\, P(h)}{\sum_{h' \in H} P(E \mid h')\, P(h')}$$
2. **Typed Option Scoring & Reproducible Action Selection**: When queried over an affordable menu $A_{i,t}$, the agent decision model returns normalized **option scores** $q_{i,t}(a) \in [0,1]$ satisfying $\sum_{a \in A_{i,t}} q_{i,t}(a) = 1$. The engine maps $q_{i,t}(a)$ to a single executed action $a_{i,t}$ using a pre-declared selection rule—either deterministic **argmax** or **seeded inverse-CDF sampling**:
   $$\text{argmax: } a_{i,t} = \arg\max_{a \in A_{i,t}} q_{i,t}(a)$$
   $$\text{sampling: } a_{i,t} = a_{(m^\ast)}, \quad m^\ast = \min\left\{m : \sum_{\nu=1}^{m} q_{i,t}\big(a_{(\nu)}\big) > \xi_{i,t}\right\}$$
   where $\xi_{i,t} \in [0,1)$ is a deterministic pseudorandom draw keyed to the run seed, world ID, step $t$, and agent ID $i$.
3. **Monte Carlo Quantiles & Proper Scoring Rules**: Across seeded multi-branch batches, Boyun summarizes outcome dispersion using nearest-rank quantiles (5th, 50th, and 95th percentiles) and evaluates dated probabilistic forecasts against resolved binary outcomes $y_n \in \{0,1\}$ using the **Brier score** and **log-loss**:
   $$\mathrm{Brier} = \frac{1}{N} \sum_{n=1}^{N} (p_n - y_n)^2, \qquad \mathrm{LogLoss} = -\frac{1}{N} \sum_{n=1}^{N} \big[y_n \ln p_n + (1 - y_n) \ln(1 - p_n)\big]$$

---

## 3. System Architecture & The Three Deterministic Ledgers (`Boyun-core`)

![How Boyun Works — End-to-End Architecture](../readme-assets/architecture.png)

Boyun's runtime (`Boyun-core`) separates world authoring, swarm inference, and state settlement into verifiable stages. At every round or timestamped decision point $\tau_t$ ($t \in \{1, \dots, T\}$):

1. **Step Preparation & Committed Plan Execution**: Scheduled exogenous events and pre-committed operator plans (such as scheduled launch posts, liquidity injections, or funded KOL campaigns) execute first and deduct payer budgets *before* independent market agents observe the state and react.
2. **Observation Construction & Affordability Filtering**: For each active agent $i$ in the swarm, the engine builds the SHA-256 hashed observation $O_{i,t}$ along the Social Graph and filters $A_{i,t}$. If only `wait` is affordable ($|A_{i,t}| = 1$), `wait` is recorded immediately without wasting a model query.
3. **Bounded Agent Inference (`Laya` or `Jev`)**: The adapter validates that the returned option scores $q_{i,t}(a)$ are finite, cover $A_{i,t}$, and sum to $1$ (within a $\le 0.001$ rounding tolerance). Malformed outputs halt the step atomically without partial state mutation.
4. **Atomic Ledger Settlement**: Selected actions $a_{i,t}$ are settled on one of three deterministic ledgers.

### 3.1 The Strategic Ledger

Designed for governance, disclosure, partnership, and multi-round strategic games:
- Deducts integer cash costs atomically: $b_{i,t}^{+} = b_{i,t} - c_i(a_{i,t})$.
- Applies individual action effects $e_k(a_{i,t})$ and triggered joint-action rules $g_{k,r}$ simultaneously across all actors, clamping shared metrics once at the end of the round:
  $$x_{k,t}^{+} = \operatorname{clip}_{[L_k, H_k]}\left(x_{k,t} + \sum_i e_k(a_{i,t}) + \sum_{r \in R_t} g_{k,r}\right)$$
- Enforces **Exact Cash Conservation** at every step:
  $$b_{i,t}^{+} \ge 0 \quad \text{and} \quad \sum_i b_{i,t}^{+} + S_t^{+} = \sum_i b_{i,0}$$
  where $S_t^{+}$ tracks cumulative cast spending.

### 3.2 The Market Ledger (AMM & Bonding-Curve Microstructure)

Designed for token launches, liquidity provisioning, and spot trading stress tests:
- Tracks integer cash and token balances across all swarm participants and liquidity pools.
- Settles swaps against a constant-product Automated Market Maker ($x \cdot y = k$) with configurable fee retention $f$ and virtual-reserve bonding curves (such as `pump.fun` pre-migration curves):
  $$\Delta y = \frac{y \cdot \Delta x (1 - f)}{x + \Delta x (1 - f)}$$
- Enforces strict slippage tolerances and inventory bounds: orders that would exceed permitted slippage or available balances are rejected atomically with a recorded rejection reason.
- Strictly separates **realized liquid cash** from **unrealized mark-to-market inventory quotes** in all downstream reports.

### 3.3 The Lending Ledger (Collateralized Credit & Liquidations)

Designed for decentralized credit protocols, interest-rate calibration, and collateral drawdown stress tests:
- Tracks pool idle cash $C_t$, lent principal $P_t$, supplier share claims $c_s$, and FIFO withdrawal queues when requested withdrawals exceed $C_t$.
- Computes pool utilization $u_t = P_t / (C_t + P_t)$ and applies the standard **kinked utilization interest-rate curve**:
  $$r(u_t) = \begin{cases} r_0 + (r^\ast - r_0)\,\frac{u_t}{u^\ast}, & u_t \le u^\ast \\ r^\ast + (r_1 - r^\ast)\,\frac{u_t - u^\ast}{1 - u^\ast}, & u_t > u^\ast \end{cases}$$
- Accrues simple interest $I_\ell = P_\ell \, r(u_t)\, \Delta t / Y$ over elapsed seconds $\Delta t$ to the protocol reserve (share $\varphi$) and suppliers on a deterministic $\epsilon = 10^{-12}$ precision grid:
  $$\Delta I_\ell^{\mathrm{prot}} = \lfloor \varphi I_\ell \rfloor_\epsilon, \qquad \Delta I_\ell^s = \left\lfloor (1 - \varphi) I_\ell \frac{c_s}{\sum_{s'} c_{s'}} \right\rfloor_\epsilon$$
- Evaluates each loan $\ell$'s **Health Factor** at every oracle update:
  $$h_\ell = \frac{Q_\ell \, p_t \, \theta}{D_\ell \, p_t^{\mathrm{usd}}}$$
  where $Q_\ell$ is pledged collateral at price $p_t$, $\theta$ is the liquidation threshold, and $D_\ell$ is principal plus accrued debt. When $h_\ell < 1$, liquidator agents repay debt (partially, or fully when $h_\ell \le 0.95$) in exchange for collateral plus bonus $\beta$, subject to market exit depth; unrecovered underwater debt writes off against a capped loss reserve.

### 3.4 Self-Hosted Local Inference (`Laya`) vs. Hosted Inference (`Jev`)

Simulating a 16-to-20 agent swarm across 24 policy worlds and 336 hourly steps requires **over 130,000 typed decision queries**. Sending 130,000 prompts to commercial cloud APIs is both expensive and exposes unpublished launch budgets, treasury limits, and risk parameters to third-party servers.

Boyun solves this with a dual inference architecture:
- **Local `Laya` Engine (Default Self-Hosted Path)**: Runs an open-weight GGUF agent decision model locally on CPU/Metal (`decision_lab/laya.py`). Incurs **zero API fees**, keeps all agent observations on-device, enforces a strict 1024-token context ceiling, and returns structured JSON option scores $q_{i,t}(a)$.
- **Hosted `Jev` Engine (TypeSafe System One)**: Connects to remote typed decision endpoints with pre-run cost estimation, hard call-allowance guards, and per-call token/cost receipts (`decision_lab/jev.py`).
- **Deterministic Offline Baseline**: A zero-model immediate-utility rule (`decision_lab/offline_decisions.py`) for instant CI verification and free local exploration.

---

## 4. Deep Integration Across the NEAR Ecosystem

Boyun is architected around the **NEAR Protocol** stack, combining live deployed contracts and runtime adapters with forward-looking architectural specifications for confidential compute and intent-based execution:

| NEAR Layer | Component / Module | Role in Boyun | Implementation Status |
| :--- | :--- | :--- | :--- |
| **1. On-Chain Integrity** | `contracts/commitment-registry` & `near_registry.py` | Rust (`near-sdk 5.29.1`) smart contract deployed at `csl-registry-2e4069fc870d.testnet`. Anchors salted SHA-256 simulation digests on-chain with code-hash pinning (`9Fc8Eu3Tj589sxW5oQngK4MqrmTgA2zuaU2JzK1uVcS7`) and RPC finality verification. | **Deployed & Verified on NEAR Testnet** |
| **2. Browser Wallet Flow** | `product_near.py` & `Boyun-interface` | Pinned **NEAR Wallet Selector (Intear adapter)** allowing users to connect a NEAR testnet wallet, inspect `register_commitment` payloads, sign on-chain commitments (0.01 testNEAR + 30 Tgas), and download private opening receipts. | **Implemented** |
| **3. NEAR AI Cloud** | `near_ai.py` (`NearAITextModel`) | World-architect adapter targeting `https://cloud-api.near.ai/v1/chat/completions` and `/v1/models` with canonical `organization/model` pinning, `x-no-aliasing: true`, no-redirect transport, and cryptographic request/response receipts. | **Implemented** |
| **4. Confidential GPU TEE & E2EE** | `docs/decision-lab/NEAR_TECH_GUIDE.md` & `NEAR_RESEARCH_FOUNDATIONS.md` | Architectural specification grounded in *Decentralized Confidential Machine Learning* (Polosukhin, Skidanov, Le Guen) for verifying NEAR AI Cloud hardware enclave attestation, TLS binding, and client-side E2EE world authoring. | **Architecture Specification** |
| **5. NEAR On-Chain Grounding & DeFi** | `near_demo.py`, `Boyun-skills`, & Lending Runner | Public NEAR RPC account/contract state snapshots, dated NEAR chain TVL ($175M) and Rhea DEX pool ($6.29M 24h volume) grounding via MCP skills, and a 90-day native NEAR collateral / USDC lending stress engine. | **Implemented & Evaluated** |
| **6. NEAR Intents (1Click & Confidential)** | `docs/decision-lab/NEAR_TECH_GUIDE.md` | Post-simulation execution rail using NEAR Intents 1Click API (`dry: true` route quotes) and Confidential Intents to translate a selected scenario branch into a concrete, privacy-preserving treasury or liquidity transfer plan. | **PoC / Technical Spec** |
| **7. NEAR Chain Signatures (MPC)** | `docs/decision-lab/NEAR_TECH_GUIDE.md` | Multi-party computation (MPC) signing design allowing a single NEAR account to authorize constrained foreign-chain liquidity or governance actions after reviewing Boyun's Decision Record. | **Architecture Specification** |
| **8. NEAR Agent Market & IronClaw** | `docs/decision-lab/NEAR_TECH_GUIDE.md` | Self-hosted worker specification wrapping `Boyun-core` inside an isolated **IronClaw** runtime to accept research assignments on **NEAR Agent Market** and deliver verified 5-report packages. | **Architecture Specification** |

### How Salted NEAR Commitments Preserve Both Auditability and Privacy

When an analyst finishes a simulation batch, publishing the raw scenario file on-chain would leak proprietary launch schedules and treasury caps. Conversely, keeping results purely local allows someone to selectively alter a report after the fact.

Boyun resolves this via a **Salted Cryptographic Commitment** (`engine/src/decision_lab/integrity.py`):
1. The engine serializes the exact result package bytes and generates a fresh 32-byte cryptographic salt.
2. It computes a salted SHA-256 digest and registers *only* the digest on `csl-registry-2e4069fc870d.testnet` via either the user's connected **Intear NEAR Wallet** or the operator testnet relayer.
3. The contract records the immutable first registration (`commitment`, `signer`, `block_height`, `block_timestamp_ns`) and refunds any excess storage deposit.
4. Scenario text, persona observations, salt, and raw artifact hashes remain 100% off-chain. When the author later chooses to disclose the report to partners or auditors, sharing the artifact alongside the private opening file allows any third party to verify via `Verify from NEAR` that the exact bytes existed at that NEAR block timestamp—and to re-run `decision-lab` offline replay to confirm every state transition.

---

## 5. Practical Guidelines & How to Use Boyun

Boyun is packaged into three modular repositories so teams can run it headlessly in CI/CD, interactively in a browser workbench, or directly inside their AI coding assistant:

- **[Boyun-core](https://github.com/Boyun-Protocol/Boyun-core)**: Python simulation engine, ledgers, model adapters, CLI, HTTP API server, MCP server, report compilers, and NEAR smart contract.
- **[Boyun-interface](https://github.com/Boyun-Protocol/Boyun-interface)**: Installable browser workbench UI, guided setup flow, trajectory inspector, and Intear NEAR wallet bundle.
- **[Boyun-skills](https://github.com/Boyun-Protocol/Boyun-skills)**: First-party skill packs (`boyun-world-grounding` and `boyun-financial-reports`) for Claude Code, Codex, Cursor, and Cindy.

### 5.1 Core Modeling Guidelines (Best Practices Before You Run)

To get decision-grade analytical value from Boyun, follow four core modeling rules enforced by our evidence standard (`docs/decision-lab/SIMULATION_EVIDENCE_STANDARD.md`):

1. **Start from the Decision Question and Matched Branches**: Define the exact policy choice you control (e.g., *$100K vs. $200K points budget*, *early vs. delayed reserve disclosure*, or *pause-and-observe vs. staged treasury exit during a drawdown*). Hold opening balances, random seeds, and exogenous event calendars identical across matched branches so differences isolate your policy intervention.
2. **Simulate the Committed Plan First**: Never treat your own launch schedule or paid marketing campaign as an optional guess. Schedule your committed actions and budget deductions explicitly so the engine executes them *before* independent swarm agents observe the resulting state and react.
3. **Separate Dated Empirical Evidence from Labeled Assumptions**: Every material parameter in a Boyun world must trace either to a **dated external source** (e.g., DeFiLlama TVL, GeckoTerminal pool reserves, or a dated governance calendar) or an explicitly labeled **modeling assumption**. Never present assumed behavioral weights as empirical market odds.
4. **Encode Behavior in Numeric Weights and Rules, Not Prose**: Calling a persona "risk-averse" in its bio does not change ledger settlement. Assign distinct numeric preference weights $w_{i,\mathrm{cash}}, w_{i,k}$, action costs $c_i(a)$, and Social Graph edges $(j \to i)$ so incentives mechanically govern choices.

---

### 5.2 Workflow 1: Installation & Guided CLI Journey (Zero-Key Quick Start)

**Prerequisites:** Python `>=3.11` and [`uv`](https://docs.astral.sh/uv/).

```bash
# Clone Boyun-core and Boyun-interface into sibling directories
git clone https://github.com/Boyun-Protocol/Boyun-core.git
git clone https://github.com/Boyun-Protocol/Boyun-interface.git
cd Boyun-core

# Install the core engine, PDF report generator, and developer test suite
uv sync --project engine --extra pdf --dev
```

Run an interactive, guided scenario journey directly in your terminal using the deterministic offline baseline (zero API keys or network calls required):

```bash
uv run --project engine --extra pdf decision-lab journey \
  --offline --format both --output-dir engine/output/my-first-journey
```

**What happens during `journey`:**
1. The CLI walks you step by step through selecting a decision question, horizon, and policy comparison (showing your setup stage and progress at each prompt).
2. It runs automated **Game Construction Checks** (`game_construction_audit`), verifying balance conservation, affordable menus, isolated unilateral utility deltas, and Social Graph links.
3. Once you review the world summary and type `RUN`, the engine executes all rounds, verifies bit-identical offline replay, and exports `scenario-report.md` and `scenario-report.pdf` into `engine/output/my-first-journey/`.

---

### 5.3 Workflow 2: Interactive Browser Workbench & NEAR Wallet Signing

To use the full visual interface with local `Laya`, hosted `Jev`, `NEAR AI Cloud`, and the **Intear NEAR Testnet Wallet**:

```bash
uv run --project engine --extra pdf --with-editable ../Boyun-interface \
  decision-lab serve --port 8769
```

Open **`http://127.0.0.1:8769/`** in your browser:

1. **Scenario Setup & Progress**: Step through the guided interview cards to define your focal question, cast of agents, preference trade-offs, and matched branches—or select **Try a free example** to inspect a pre-grounded NEAR DeFi world.
2. **Configure AI & Privacy Boundaries**:
   - Choose **Offline — local rules** for instant deterministic baseline runs.
   - Choose **Local Laya (GGUF)** for zero-API-fee, on-device neural agent scoring.
   - Or import a session-only **TypeSafe (`Jev`)** or **NEAR AI Cloud** key under **AI & privacy**. Keys stay in process memory only, never enter world files or prompts, and require explicit pre-run cost/call approval.
3. **Inspect Results & Replay**: Browse the generated scenario slides, compare cash vs. utility trajectories across branches, and inspect individual round settlements and rejected actions.
4. **Anchor on NEAR Testnet**:
   - On the final slide, click **Record on NEAR testnet** to generate a salted SHA-256 commitment for your exact result bytes.
   - Click **Connect testnet wallet** in the header to connect via the **Intear NEAR Wallet Selector**, click **Review transaction for my wallet** (verifying `csl-registry-2e4069fc870d.testnet`, `register_commitment`, and the `0.01 testNEAR` storage bound), and approve in your wallet—or use the operator testnet relay.
   - Click **Verify from NEAR** at any time to confirm `final_verified` block height, timestamp, and code-hash agreement, and download your private opening file.

---

### 5.4 Workflow 3: 15–30 Minute World Construction with Coding Agents (`MCP` + `Boyun-skills`)

<table>
<tr>
<td width="50%"><img src="../readme-assets/skills-data.png" alt="Boyun Data Grounding Skill" width="100%"/></td>
<td width="50%"><img src="../readme-assets/skills-math.png" alt="Boyun Math Verification Skill" width="100%"/></td>
</tr>
<tr>
<td align="center"><b>1. Empirical Data Grounding Skill</b></td>
<td align="center"><b>2. Mathematical Mechanism Verification Skill</b></td>
</tr>
</table>

Instead of hand-writing JSON world files, connect your favorite coding agent (**Claude Code**, **Codex**, **Cursor**, **Gemini**, or **Cindy**) to Boyun's local **Model Context Protocol (MCP)** server and install [`Boyun-skills`](https://github.com/Boyun-Protocol/Boyun-skills):

```bash
# 1. Clone Boyun-skills and copy the skill packs into your agent's skills directory
git clone https://github.com/Boyun-Protocol/Boyun-skills.git

# 2. Start the Boyun-core MCP server over stdio
uv run --project engine --extra mcp decision-lab mcp --workspace engine/output/mcp
```

With `boyun-world-grounding` and `boyun-financial-reports` loaded, a complete custom study takes **15 to 30 minutes** of guided interaction:
1. **Your AI Agent Interviews You**: It asks focused questions about your project goal, capital tiers, timeline, and target venues, displaying a live progress tracker on the question surface.
2. **Data Skill Grounding**: The agent queries live market data sources (DeFiLlama TVL, GeckoTerminal / Rhea DEX volume, Birdeye / DexScreener launch cohorts, TokenTerminal filings) and compiles a dated **Evidence Register** where every parameter has an `as-of` timestamp, unit, and source citation (reporting gaps explicitly rather than inventing numbers).
3. **Math Skill Verification**: The agent derives the exact AMM price impact, bonding-curve reserve equations, kinked borrow rates, and health factor formulas for your venue, writes the world configuration, and runs `validate_strategic_world` and `game_construction_audit` via MCP to verify conservation laws before execution.
4. **5-Report Package Synthesis**: Once `Boyun-core` finishes executing and replaying the Agent Swarm trajectories, the `boyun-financial-reports` skill compiles a structured five-volume research casebook:
   - **`01-WORLD-CREATION`**: Problem formulation, dated evidence register, Agent Swarm personas, preference weights, Social Graph topology, and declared assumptions.
   - **`02-BEAR-CASE`**: Downside and drawdown trajectory analysis, liquidity/collateral stress points, and capital preservation rules.
   - **`03-BULL-CASE`**: High-demand and expansion trajectory analysis, fee/utilization capture, and capacity bottlenecks.
   - **`04-TECHNICAL-REPORT`**: Step-by-step ledger accounting, option-score distributions $q_{i,t}(a)$, slippage/liquidation rejection logs, and bit-identical offline replay verification.
   - **`05-DECISION-RECORD`**: Matched-branch comparison matrix, mechanical invariants vs. model-sensitive conclusions, and concrete pre-launch action checklist.

![Boyun 5-Report Analytical Package](../readme-assets/report-package.png)

---

## 6. Empirical Evaluation & Full-Horizon Case Studies

To establish what Boyun verifies mechanically and how it behaves at scale, we evaluated the framework across **six synthetic mechanism benchmarks**, **two full-horizon DeFi case studies executed locally with `Laya`**, and a **matched-brief comparison with `MiroFish`**.

### 6.1 Six Reproducible Mechanism Benchmarks

Executed completely offline (`python3 -m pytest engine/tests tools/tests`), six controlled experiments verify that Boyun's mathematical kernels match hand-calculated ground truth byte for byte:

1. **Normal-Form Game Solver**: On a $2 \times 2$ game with payoffs $U_1(A,C)=4, U_1(A,D)=1, U_1(B,C)=2, U_1(B,D)=3$ and opponent beliefs $\pi_1(C)=1/3, \pi_1(D)=2/3$, reproduces exact expected utilities $\mathrm{EU}_1(A)=2.0$, $\mathrm{EU}_1(B)=2.6667$, best response $B$, deviation regret $\mathrm{Reg}_1(A)=0.6667$, and pure Nash equilibrium $(B,D)$.
2. **Sequential Bayesian Updating**: For balanced priors $(0.5, 0.5)$ and likelihoods $(0.8, 0.2)$, reproduces exact posteriors $(0.8, 0.2)$ after one signal and $(16/17, 1/17) \approx (0.941176, 0.058824)$ after two signals.
3. **Two-Round Synchronous Settlement & Replay**: Verifies exact cash conservation ($200\text{¢}$ initial cash $= 80\text{¢}$ retained $+ 120\text{¢}$ spent), metric clamping $[0,10]$, round-$t+1$ message arrival, and bit-identical offline replay.
4. **Proper Scoring Rules**: Confirms exact Brier ($0.0625$) and log-loss ($0.287682$) calculations against a chronological training baseline ($0.25$ and $0.693147$).
5. **Social Graph Delivery vs. Joint-Rule Ablation**: Isolates information flow from payoff coupling—removing the joint-action rule lowers readiness from $6$ to $3$ without changing Bob's action, whereas removing the Social Graph edge $(A \to B)$ causes Bob to `wait` so readiness stays at $1$.
6. **Numeric Preference Weights vs. Persona Prose**: Demonstrates in an 8-role world that shifting a risk weight from $-500$ to $-5{,}000$ flips the actor's decision and reduces cast spending from $120{,}000\text{¢}$ to $110{,}000\text{¢}$, whereas rewriting all persona biographies to emphasize caution while keeping numeric weights fixed changes nothing.

---

### 6.2 Case Study 1: 14-Day Token Launch Microstructure Matrix (24 Worlds · 16-Agent Swarm · 136,841 Local `Laya` Decisions)

![24-World Token Price Trajectories](../readme-assets/price-paths.png)

We modeled a 14-day (336-hour) token launch on a `pump.fun`-style bonding curve and constant-product AMM across **24 matched policy worlds**:
- **Experimental Design**: $2 \text{ regimes (\textit{BULL} / \textit{BEAR})} \times 3 \text{ capital tiers (\$5K, \$10K, \$15K)} \times 2 \text{ cost structures (low / high upfront)} \times 2 \text{ crash-response policies (\textit{Pause \& Observe} vs. \textit{Staged Exit})}$.
- **Swarm & Execution Scale**: A **16-agent swarm** (founder, marketing operator, liquidity pool, whale cohorts, momentum traders, and retail cohorts) communicating over a directed Social Graph across dated catalyst events. All **24 worlds** completed all **336 hours** (**8,064 simulated path-hours**, **8,754 decision points**, and **136,841 local `Laya` inference calls**) on local hardware at **$0.00 API cost**, settling **50,251 filled trades** ($16.77M total traded notional) and recording **11,350 atomic slippage rejections**.
- **Key Analytical Finding (Realized Cash vs. Terminal Pool Price)**:
  - Across all 12 matched branch pairs, the **Staged Exit** policy (selling tranches when trailing 6-hour volume drops below threshold) yielded **$1,546.54 to $10,330.65 more realized founder cash** than **Pause & Observe**, because tranche sales convert inventory into cash directly.
  - However, plotting the **24 simulated pool price trajectories** reveals the exact trade-off: **Pause & Observe** preserves pool reserves and supports substantially higher terminal token prices (**28.6 $\mu\$$, 51.2 $\mu\$$, and 95.6 $\mu\$$** for the $5K, $10K, and $15K tiers at Hour 336) compared to **Staged Exit** (**11.9–13.2 $\mu\$$**), where automated tranche sales depress the AMM price curve by 54% to 88%. When unsold inventory is valued at terminal pool quotes, Pause & Observe exceeds Staged Exit in 6 of the 12 pairs. Boyun makes this mechanical tension between liquid treasury extraction and market price support explicit before launch.

---

### 6.3 Case Study 2: 90-Day Collateralized Lending Launch on NEAR (4 Worlds · 20-Agent Swarm)

![90-Day NEAR Lending Simulation](../readme-assets/lending-paths.png)

We evaluated a 90-day (2,160-hour) launch of a **NEAR-collateralized USDC lending market** with a **20-agent swarm** (protocol operator, institutional and retail USDC suppliers, leveraged and conservative NEAR borrowers, liquidators, and a competing venue reference):
- **Experimental Design**: Four 90-day policy worlds comparing base ($100K) vs. expanded ($200K) supplier points budgets, standard vs. conservative kinked interest-rate curves, and historical NEAR hourly closes vs. a stressed **35% collateral drawdown** scenario, all scored locally by `Laya` (**2,880 decision points**, **21,600 agent decisions**, **$0 API cost**).
- **Key Analytical Finding (Mechanical Invariants vs. Behavioral Sensitivity)**:
  - Active USDC supply grew from **$1.25M to $1.95M** while borrowed principal reached **$0.29M** (capped by per-borrower debt limits), generating **$4,296.46 to $4,707.01** in accrued interest.
  - In the 35% NEAR price drawdown world, borrower health factors $h_\ell$ fell below $1.0$, triggering **13 automated liquidations** that repaid **$89,259.68** of debt and seized **$96,400.45** of NEAR collateral with **zero bad debt** under the tested liquidator cash and market depth assumptions.
  - Crucially, Boyun's Technical Report separates **mechanical conclusions** (kinked rate math, borrower caps, and liquidation thresholds) from **behavioral sensitivities** (where `Laya`'s uncalibrated option scores favored borrowing across both rate curves, motivating empirical borrower-elasticity calibration before sizing points budgets).

---

### 6.4 Matched-Brief Comparison: `Boyun` and `MiroFish`

Running the exact same token-launch brief on both upstream **MiroFish** (40 rounds on OASIS with Gemini 2.5 Flash over 37 social personas) and **Boyun** demonstrates how the two systems complement one another:
- **MiroFish** excels at open-ended **social discourse**, generating **1,111 free-text posts and comments** capturing community skepticism, creator pushback, and narrative nuance—but settles **0 trades** and tracks no cash balances or pool reserves.
- **Boyun** organizes participants as a **constrained Agent Swarm over a directed Social Graph** and settles **50,251 trades** with exact reserve accounting, slippage rejections, price trajectories, and bit-identical offline replay—while using structured action menus rather than free-text essays.

---

## 7. Evidence Boundaries, Verification Suite & Open-Source Links

Boyun is built on scientific transparency. Its outputs are **conditional scenario explorations under explicit rules and declared assumptions**, not calibrated market forecasts or financial advice. Neither local `Laya` nor hosted `Jev` option scores $q_{i,t}(a)$ represent empirical real-world odds; establishing predictive forecasting skill requires prospective, pre-registered resolution studies scored via Brier and log-loss against historical base rates.

### Run the Automated Verification Suite

Every claim in `Boyun-core` is backed by **1,918+ automated unit and integration tests**, AST-verified source anchors, and Rust smart contract tests:

```bash
# 1. Run the full Python engine, ledger, adapter, and report test suite
uv run --project engine --extra pdf --with-editable ../Boyun-interface \
  python -m pytest engine/tests tools/tests -q

# 2. Verify all 64 AST source symbols and documentation links
python3 tools/build_evidence_docs.py --check

# 3. Run the NEAR Commitment Registry smart contract tests
cargo test --locked --manifest-path contracts/commitment-registry/Cargo.toml
```

### Explore Boyun

- **Live Website, Interactive Demo & Paper**: [https://boyun-protocol.github.io/](https://boyun-protocol.github.io/)
- **Boyun-core (Engine, Ledgers, CLI, MCP, NEAR Contract)**: [https://github.com/Boyun-Protocol/Boyun-core](https://github.com/Boyun-Protocol/Boyun-core)
- **Boyun-interface (Browser Workbench & NEAR Wallet UI)**: [https://github.com/Boyun-Protocol/Boyun-interface](https://github.com/Boyun-Protocol/Boyun-interface)
- **Boyun-skills (Agent Grounding & Reporting Skills)**: [https://github.com/Boyun-Protocol/Boyun-skills](https://github.com/Boyun-Protocol/Boyun-skills)
