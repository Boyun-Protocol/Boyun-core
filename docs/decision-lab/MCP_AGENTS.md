# Use Boyun from an agent client

29 October 2026. Boyun now provides a working **local stdio MCP server** using
the official Python MCP SDK. This is an interface to the existing strategic
engine, not a second simulator or a hosted agent marketplace.

## What works

An agent client can discover the guidelines and examples, construct a world
with its own preferred model, validate it, execute a bounded offline experiment,
inspect replay-verified results, and retrieve a Markdown report. Opaque run IDs
can be reopened after restarting the MCP server with the same private workspace.

The current MCP participant policy is `local-myopic-utility-v1`: it selects
the action with greatest immediate own-action utility under the reviewed
cash/metric rules. It does not interpret narrative motivations, optimize future
rounds, respond strategically to messages, or use Jev. Messages and joint rules
still execute in the world; this baseline does not reason about them.

The existing browser/CLI live TypeSafe route remains separate. This MCP version
offers no paid author/actor inference, credential import, shell command, arbitrary
file operation, wallet signing, or chain-submission tool. The connected host's
authoring model may have its own cost and privacy policy.

The discoverable guidelines and `construct_world` prompt include the
[cross-domain evidence rule](SIMULATION_EVIDENCE_STANDARD.md): every material
assumption and modeled outcome needs a specific reference or a reasonable cause,
with preserved uncertainty and input → mechanism → outcome links. Polls, votes,
forecasts, market quotes and actor scores retain distinct meanings. This guidance
does not add sidecar admission checks to `run_offline`; its existing validation
still verifies structure and execution limits, not truth or calibration.

## Start the local server

New to Boyun? Follow the step-by-step install guide first (clone, install uv, run the self-test), then register the server with your client (option D there covers Claude Code, Claude Desktop, Cursor and Codex).

From any directory, use an absolute path to your clone and a **new dedicated** private
workspace. Replace both `/ABSOLUTE/PATH/TO/...` values:

```sh
uv run --locked \
  --project /ABSOLUTE/PATH/TO/Boyun/engine \
  --extra mcp decision-lab mcp \
  --workspace /ABSOLUTE/PATH/TO/boyun-mcp
```

The workspace is created with mode `0700`; an existing directory must already
be owned by the current user and inaccessible to group/other users. Do not point
it at an existing browser/CLI output directory. One process holds its workspace
lock; use a different dedicated directory for another simultaneous client.
The process waits for MCP messages on stdin and emits protocol messages on
stdout. It is normally launched by the client, rather than used as an interactive
terminal. No HTTP listener is opened and no `.env` file is loaded.

Initial dependency installation can require network access. Engine operations
through this adapter make no model/API or chain requests. The optional extra
keeps the base engine dependency-free.

## Client configuration

For a client accepting a standard `mcpServers` JSON configuration, register the
following stdio entry. Use the full path to `uv` if that application's PATH
does not include it. There are no secrets in this configuration.

```json
{
  "mcpServers": {
    "boyun": {
      "command": "uv",
      "args": [
        "run", "--locked",
        "--project", "/ABSOLUTE/PATH/TO/Boyun/engine",
        "--extra", "mcp",
        "decision-lab", "mcp",
        "--workspace", "/ABSOLUTE/PATH/TO/boyun-mcp"
      ]
    }
  }
}
```

Use your client's own configuration editor or MCP registration UI; this task
does not overwrite global client settings. The server and official Python
client have been tested with SDK **1.30.0**, negotiating MCP **2025-11-25**.
This is not a claim of implementing the newer 2026-07-28 protocol. A specific
Codex/Gemini desktop connection still requires registering the server in that
client and confirming discovery there.

## Discoverable interface

| Primitive | Name | Purpose |
| --- | --- | --- |
| Resource | `decision-lab://capabilities` | Execution route, schema names, limits, privacy and compatibility |
| Resource | `decision-lab://guidelines` | Complete strategic-world construction contract |
| Resource | `decision-lab://examples` | Bundled synthetic example index |
| Prompt | `construct_world(question)` | Guide the connected agent's model in proposing a world; no model call by Boyun |
| Tool | `get_capabilities` | Read the capability manifest |
| Tool | `list_examples` | Discover known example IDs |
| Tool | `get_example(example_id)` | Retrieve an example's question and world |
| Tool | `inspect_game(world)` | Compact actor/budget/dependency/warning summary without saving a run |
| Tool | `inspect_actor(world, actor_id)` | First-round own-information view and partial action tradeoffs; excludes peer private preferences |
| Tool | `validate_world(world)` | Check structure and existing product execution budgets, without persisting a run |
| Tool | `run_offline(world, question, worlds, seed)` | Explicitly submit a caller-supplied world for local execution |
| Tool | `get_run(run_id)` | Poll status, completed denominator, recomputed summary and replay result |
| Tool | `list_runs` | Discover MCP-owned runs in the selected workspace |
| Tool | `export_markdown(run_id)` | Save a private report inside that run's workspace |
| Tool | `read_artifact(run_id, artifact, offset, max_chars)` | Retrieve `results_json`, `game_audit_json` or `report_markdown` in bounded chunks |

World schemas are `strategic-world.v1` and `strategic-world.v2`. Up to 100
participants, eight rounds, four worlds, and **800 total actor turns** are
supported, subject to smaller combined prompt/report budgets. There are at
most 32 runs per workspace. Inputs are bounded by depth, nodes, integer ranges,
and a 512 KiB world limit before execution. Validation does not fit a world
to real behavior or certify its assumptions. Some schema-valid worlds exceed
the shared product's execution/text budgets and are rejected before persistence.

## Research journey

Give the connected agent a task such as:

> Use Boyun to examine whether earlier disclosure changes coordination under
> two risk-preference assumptions. Read its guidelines and capabilities. Propose
> a small explicit world, identify assumed coefficients, and show me the rules.
> After I approve running it, validate and execute the offline baseline, then
> summarize the recorded outcomes and export Markdown. Explain which parts the
> local policy cannot assess; do not present sampled paths as real-world odds.

The client author uses its own model to produce the world JSON. Boyun never
converts prose into hidden rules inside the execution engine. A typical tool
sequence is:

```text
get_capabilities()
list_examples()
get_example(example_id=<one returned ID>)
inspect_game(world=<agent-authored JSON object>)
inspect_actor(world=<same object>, actor_id=<one actor ID>)
validate_world(world=<same object>)
run_offline(world=<same object>, question=<research question>, worlds=1, seed=42)
get_run(run_id=<returned ID>)           # poll until completed or failed
export_markdown(run_id=<same ID>)
read_artifact(run_id=<same ID>, artifact="report_markdown", offset=0, max_chars=4096)
```

For a long report, follow `next_offset` until it is null. Offsets count Unicode
code points, not UTF-8 bytes. The response includes an artifact SHA-256 so a
client can check a reassembled artifact. `results_json` contains recorded world
results, decisions and receipts; the compact summary is rebuilt from verified
results rather than trusted from a mutable display cache.

An MCP request to run the supplied world is an execution instruction. The
internal review identity freezes scope and budgets; it is not evidence that a
separate human reviewed the world. Human approval remains a host/client policy.

## Privacy and trust

Artifacts contain the complete research question, world, goals, and persona
information. Private file permissions are not encryption. Returning an artifact
to a connected agent discloses it to that host, which may send it to its model
provider. Keep private data out of public example prompts and share only with
trusted clients. Quoted scenario text and messages remain untrusted data.

The adapter rejects traversal identifiers, unknown artifact names, symbolic-link
substitutions, foreign/non-MCP runs, and mismatched reviewed worlds or decision
receipts. Recorded replay verifies arithmetic against supplied rules, not the
truth of those rules or cryptographic authenticity of owner-controlled files.
Restarting does not resume an interrupted run automatically or trigger spend.

## Verification

```sh
uv run --locked --project engine --extra mcp python -m pytest \
  engine/tests/test_mcp_adapter.py engine/tests/test_mcp_stdio.py -q
```

The stdio test launches the actual CLI subprocess with the official MCP client,
negotiates the protocol, discovers tools/resources/prompts, submits a modified
caller world, executes it, retrieves JSON/Markdown and verifies replay. Separate
tests cover private workspaces, strict types, restart integrity, corrupt caches,
foreign receipts, malformed worlds, and failed-preflight capacity behavior.
An installed-wheel check outside the source checkout also completed the journey.
Original acceptance record: SDK/protocol version,
discovered primitives, completion/replay/export, and implementation hashes.
These are transport/engine checks, not a model-generated-world quality study.

Primary protocol reference: [versioned MCP architecture](https://modelcontextprotocol.io/specification/2025-11-25/architecture).
See [native Jev](JEV_INTEGRATION.md), world method, and
[research foundations and limits](NEAR_RESEARCH_FOUNDATIONS.md).

## Construction inspection

The eleven-tool interface includes a compact construction summary and an own-information
actor view before execution. After a run is created, `game_audit_json` exposes the
private author review in bounded chunks. Never forward the author audit to persona
models: it contains every actor's declared preferences and allocations.
Role counts describe this hypothetical cast, not an observed population.
The bundled `near-pilot-eight-roles` example has eight roles sharing one fixed
$10,000 cast budget. [Construction rules and limitations](PERSONA_GAME_DESIGN.md).

The expanded eleven-tool interface and eight-role installed-package journey are
recorded separately in v0.7 acceptance.

## Scope of construction inspection

Boyun prioritizes financial/economic decision games with explicit actor goals
and incentives. `inspect_game` and `game_audit_json` inspect declared mechanics,
not Jev reasoning. The MCP policy here remains offline; the native Jev route
returns no internal reasoning trace. [Economic research and record boundaries](ECONOMIC_RELATED_WORK.md).
