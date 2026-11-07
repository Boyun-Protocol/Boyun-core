# Install Boyun

Boyun runs on your own machine. Nothing is hosted for you: the website is a demonstration, and the engine is what you download. This guide takes you from nothing to a first result, then offers five ways to run it.

**How long it takes.** Installing takes about 10 minutes. Setting up a real world (the questions, the actors, the inputs) usually takes **15 to 30 minutes**. A full report then takes **a few hours**, depending on the size of the world and the number of actors and agents inside it. The bundled free example is small and runs on local rules, so it finishes much sooner.

## Step 1: Prerequisites

You need three things.

| Tool | Why | Check it |
| --- | --- | --- |
| Git | to download Boyun | `git --version` |
| Python 3.11 or newer | the engine is Python | `python3 --version` |
| [uv](https://docs.astral.sh/uv/) | installs the locked dependencies | `uv --version` |

Install uv if you don't have it:

```sh
# macOS or Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Open a new terminal afterwards so `uv` is on your PATH. Docker is only needed for the container option.

## Step 2: Download Boyun

```sh
git clone https://github.com/Boyun-Protocol/Boyun-core.git
cd Boyun-core
```

Every command below is run from this `Boyun-core` folder.

## Step 3: Install the engine and run the self-test

```sh
uv sync --project engine --extra pdf --extra mcp --dev
uv run --project engine --extra pdf --extra mcp --dev pytest engine/tests -q
```

The tests make no model calls and need no keys. If they pass, the engine works on your machine.

## Step 4: Choose how to run it

All five options use the same engine and the same recorded results. Pick one now; you can try the others later.

| Option | Best for | Needs a key? |
| --- | --- | --- |
| [A. Web app](#a-web-app) | most people; guided questions in a browser | no, for the free example |
| [B. Command line](#b-command-line) | scripts, servers, no browser | no, for the free example |
| [C. Container](#c-container) | a clean install without Python on your machine | no, for the free example |
| [D. From an AI agent (MCP)](#d-from-an-ai-agent-mcp) | Claude, Codex, Cursor or any MCP client builds the world | no |
| [E. A local model](#e-a-local-model-laya-or-ollama) | actor decisions without an API fee | no |

### A. Web app

1. Start the local server:

   ```sh
   uv run --project engine --extra pdf decision-lab serve --port 8769
   ```

2. Open **http://127.0.0.1:8769/** in your browser.
3. Choose **Start a scenario**, then **Try a free example**. This uses local deterministic rules, so it spends nothing and sends nothing.
4. Answer the questions one at a time. Review the world. Approve the run. Read the results, replay them, and export Markdown or PDF.

If port 8769 is in use, choose another with `--port`. Only `127.0.0.1` is supported; do not expose this app directly to the internet.

**Using real model decisions (Jev).** Create a key, put it in a private `.env` file, and tell the server which variable to read:

```sh
cp .env.example .env
# edit .env and set TYPESAFE_API_KEY=...
uv run --project engine --extra pdf decision-lab serve --port 8769 \
  --typesafe-env-file .env --typesafe-api-key-env TYPESAFE_API_KEY \
  --typesafe-http-client curl
```

Then, in the app, open **AI & privacy**, select Jev, run the free model-catalog check, review the actor-call limit and the input-cost estimate, and approve. There is no automatic retry and no model fallback. `.env` is gitignored; never commit it.

### B. Command line

The guided journey is the same flow in a terminal:

```sh
uv run --project engine --extra pdf decision-lab journey \
  --offline --format both --output-dir engine/output/my-first-journey
```

Answer the one-at-a-time choices. After reviewing the world, type `RUN` to approve it. The output directory must be new; use another name for a second attempt. It will contain `scenario-report.md` and `scenario-report.pdf`. These files are private and not encrypted.

Other commands (`decision-lab --help` lists all of them): `report` exports a recorded run without inference, `agents simulate` runs communicating model roles on a world you wrote, and `world`, `scenario`, `campaign` and `timeline` cover longer experiments.

### C. Container

```sh
docker compose up --build -d
docker compose logs --tail 20 boyun
```

Open **http://127.0.0.1:8769/** and choose **Start a scenario**, then **Try a free example**. Sessions and reports go to the `boyun-data` Docker volume. To use a key, copy `.env.example` to `.env`, set `TYPESAFE_API_KEY`, and restart. To reach it from another machine, use an SSH tunnel (`ssh -L 8769:127.0.0.1:8769 user@your-server`) instead of a wider bind. Details: [CONTAINER.md](decision-lab/CONTAINER.md).

### D. From an AI agent (MCP)

Boyun includes a local MCP server. Your agent writes the world with its own model; Boyun validates it, runs it offline on your machine, and returns replay-verified results. The server makes no model or chain calls of its own.

1. Pick an **absolute** path for a new, private workspace folder, for example `/home/you/boyun-mcp` (macOS: `/Users/you/boyun-mcp`). Do not use an existing output folder. One workspace belongs to one running client.
2. Register the server with your client. Replace `/ABSOLUTE/PATH/TO/Boyun` and the workspace path.

   **Claude Code**

   ```sh
   claude mcp add boyun -- uv run --locked \
     --project /ABSOLUTE/PATH/TO/Boyun/engine --extra mcp \
     decision-lab mcp --workspace /ABSOLUTE/PATH/TO/boyun-mcp
   ```

   **Claude Desktop, Cursor and other clients that read an `mcpServers` JSON file**

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

   If the app cannot find `uv`, replace `"uv"` with its full path (`which uv`).

   **Codex** (`~/.codex/config.toml`)

   ```toml
   [mcp_servers.boyun]
   command = "uv"
   args = ["run", "--locked", "--project", "/ABSOLUTE/PATH/TO/Boyun/engine", "--extra", "mcp",
           "decision-lab", "mcp", "--workspace", "/ABSOLUTE/PATH/TO/boyun-mcp"]
   ```

3. Restart the client and check that it lists the `boyun` server and its eleven tools (`get_capabilities`, `list_examples`, `get_example`, `inspect_game`, `inspect_actor`, `validate_world`, `run_offline`, `get_run`, `list_runs`, `export_markdown`, `read_artifact`).
4. Ask it something like: *"Use Boyun to examine whether earlier disclosure changes coordination under two risk assumptions. Read its guidelines, propose a small explicit world, show me the rules, and wait for my approval before running it."*

The configuration holds no secrets. Artifacts you return to the agent are visible to that agent's model provider. Full tool list, limits and privacy notes: [MCP_AGENTS.md](decision-lab/MCP_AGENTS.md). You can verify the server on your machine with:

```sh
uv run --locked --project engine --extra mcp python -m pytest \
  engine/tests/test_mcp_adapter.py engine/tests/test_mcp_stdio.py -q
```

### E. A local model (Laya or Ollama)

You can have actors decide with a model that runs on your own computer, with no per-call API fee. You still pay for electricity and hardware.

**E1. Laya (installed from Hugging Face)**

1. Install the optional dependency (it pulls in the model runtime, so allow several minutes and several gigabytes):

   ```sh
   uv sync --project engine --extra laya --extra pdf
   ```

2. Run the bundled example world with Laya. The first run downloads the `convaiinnovations/laya-typed-decisions` checkpoint; later runs are local:

   ```sh
   uv run --project engine --extra laya decision-lab agents simulate \
     --world engine/examples/jev-actor-world.public.json \
     --transport laya --model convaiinnovations/laya-typed-decisions \
     --allow-model --max-calls 10 --output-dir engine/output/laya-example
   ```

   Use a new output directory each time.

3. Optional: serve Laya over a local endpoint, then point runs at it.

   ```sh
   # terminal 1
   uv run --project engine --extra laya python -m decision_lab.laya_server
   # terminal 2
   uv run --project engine --extra laya decision-lab agents simulate \
     --world engine/examples/jev-actor-world.public.json \
     --transport laya-http --model convaiinnovations/laya-typed-decisions \
     --allow-model --max-calls 10 --output-dir engine/output/laya-http-example
   ```

Know the limits before relying on it. Laya's context is 1024 tokens, so long actor histories are rejected rather than truncated. It accepts worlds you authored; it does not create worlds. Its published fine-tuning covered four synthetic workflows (agent observability, customer service, invoice processing and security incidents), **not financial markets**, and its confidence scores are not probabilities of market events. Benchmark it against held-out decisions before you trust a result. More in [LOCAL_ACTOR_MODEL.md](decision-lab/LOCAL_ACTOR_MODEL.md).

**E2. Any model you serve with Ollama**

If you have installed [Ollama](https://ollama.com) and pulled a model, Boyun can use it through the same menu of allowed actions:

```sh
ollama serve            # if it is not already running
uv run --project engine decision-lab agents simulate \
  --world engine/examples/jev-actor-world.public.json \
  --transport ollama --model YOUR_MODEL_NAME \
  --allow-model --max-calls 10 --output-dir engine/output/ollama-example
```

Boyun talks to Ollama at `http://127.0.0.1:11434`.

**Fine-tuning your own model.** Boyun does not include a training pipeline, and the Laya adapter only loads its reviewed checkpoint. The practical route today is to fine-tune a model with your own tools, serve it with Ollama, and run it with `--transport ollama`, then compare it with the bundled rules and with Laya on the same world. Treat a fine-tuned model's choices as model decisions, not forecasts.

## If something goes wrong

| Symptom | Try |
| --- | --- |
| `uv: command not found` | open a new terminal, or run `~/.local/bin/uv` |
| Python older than 3.11 | `uv python install 3.12`, then repeat Step 3 |
| Port already in use | add `--port 8770` (any free port) |
| `output directory exists` | give `--output-dir` a new name; Boyun never overwrites a run |
| MCP client shows no tools | use absolute paths; restart the client; run the two MCP tests above |
| Laya download fails | check your network and disk space; the first run needs both |
| Tests fail on a fresh clone | run `uv sync --project engine --extra pdf --extra mcp --dev` again, then open an issue with the output |

## What Boyun is, and is not

Boyun is a conditional decision tool. It is not a validated market forecaster or an automated trader, and the website demonstrates its questions without running anything. Read [the whitepaper](whitepaper/README.md) for methods and limits, and [NOTICE](../NOTICE) for upstream attribution (it began as an AGPL-3.0 fork of MiroFish).
