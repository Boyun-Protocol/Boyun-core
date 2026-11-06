# Boyun-core

Simulation engine, CLI, local HTTP APIs, MCP integration and NEAR testnet commitment contract.

Boyun separates authored worlds, actor choices and numeric settlement. Actors receive restricted observations; adapters return structured choices; ledgers apply feasible actions and record state. Saved decisions support exact replay without repeating inference. Outputs are conditional on specified rules and model behavior, not calibrated market forecasts.

## Repositories

- [Boyun-core](https://github.com/Boyun-Protocol/Boyun-core): Python runtime, CLI, API server, adapters, ledgers, reports and contracts.
- [Boyun-interface](https://github.com/Boyun-Protocol/Boyun-interface): separately installable browser assets and UI tests.
- [Boyun-skills](https://github.com/Boyun-Protocol/Boyun-skills): first-party agent instructions, evidence standards and templates.

Marketing material, site assets, launch posts, production notes and private run archives are excluded from these repositories.

## Install and run

Requires Python 3.11+ and uv. From this repository:

```sh
uv sync --project engine --extra pdf --dev
uv run --project engine --extra pdf decision-lab journey --offline --format both --output-dir engine/output/first-journey
```

Use a new output directory for each run. The offline policy is deterministic test behavior, not a local language model. Review the world and type RUN when prompted. CLI results and PDF exports work without Boyun-interface.

For the browser app, clone Boyun-interface beside this repo, then install both:

```sh
uv run --project engine --extra pdf --with-editable ../Boyun-interface decision-lab serve --port 8769
```

Open http://127.0.0.1:8769/. The HTTP/API server belongs to core; HTML, CSS, JS and wallet assets belong to interface. Without that package, API routes continue working and page requests return an installation message. The server retains loopback and same-origin protections.

## AI and agent integration

Hosted Jev, local Laya and local Ollama actor routes have different configuration and evidence limits. Laya inference has no API fee; hardware/electricity costs remain. Local inference is a deployment boundary, not a blanket confidentiality guarantee. Model scores are not calibrated real-world probabilities.

```sh
uv run --project engine --extra mcp decision-lab mcp --workspace engine/output/mcp
```

MCP exposes the documented offline tools and records. It does not grant automatic inference spending or wallet signing. Read [MCP setup](docs/decision-lab/MCP_AGENTS.md), [local actors](docs/decision-lab/LOCAL_ACTOR_MODEL.md), and [Jev integration](docs/decision-lab/JEV_INTEGRATION.md).

## NEAR

`contracts/commitment-registry` and `tools/near-mvp` implement optional testnet result commitments and receipt checks. A commitment checks artifact integrity, not model correctness or prediction quality. Wallet integration is packaged in Boyun-interface. The NEAR AI author adapter has separate configuration and funded-generation acceptance limits. [NEAR integration](docs/decision-lab/NEAR_MVP.md).

## Technical documentation

[System design](docs/decision-lab/SYSTEM_DESIGN.md) · [Research foundations](docs/decision-lab/RESEARCH_FOUNDATIONS.md) · [Evidence standard](docs/decision-lab/SIMULATION_EVIDENCE_STANDARD.md) · [Source map](docs/decision-lab/SOURCE_MAP.md) · [Research paper](docs/whitepaper/main.pdf)

## Container

`docker build -t boyun-core .` builds the core HTTP/API runtime. It excludes browser assets; the health check probes `/api/bootstrap`. Run with a loopback port mapping and persistent output volume. For browser use, install the separate interface package as documented above. Container build execution is not part of the local split verification.

## Checks

```sh
uv run --project engine --extra pdf --with-editable ../Boyun-interface python -m pytest engine/tests tools/tests -q
python3 tools/build_evidence_docs.py --check
cargo test --locked --manifest-path contracts/commitment-registry/Cargo.toml
```

The full HTTP integration suite installs the interface; command-line and ledger APIs remain independent of it. UI regressions live in Boyun-interface. Tests verify covered mechanics, not empirical forecasting skill.

## License and attribution

AGPL-3.0-only. Boyun began from a MiroFish fork and developed a separate runtime. Preserve [NOTICE](NOTICE), the [reuse ledger](docs/decision-lab/UPSTREAM_REUSE.md), and third-party asset licenses. No MiroFish, TypeSafe or NEAR endorsement is implied.
