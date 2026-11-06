# Local Laya actor decisions

The native Laya adapter uses `convaiinnovations/laya-typed-decisions`, the fine-tuned English checkpoint. Install the optional dependency with `pip install '.[laya]'` from `engine/`. On first use, Laya downloads the checkpoint from Hugging Face. Subsequent inference runs locally on CPU without an inference API fee. Electricity and hardware costs remain.

```sh
engine/.venv/bin/decision-lab agents simulate \
  --world engine/examples/jev-actor-world.public.json \
  --transport laya --model convaiinnovations/laya-typed-decisions \
  --allow-model --max-calls 10 --output-dir engine/output/laya-example
```

Use a new output directory. This route accepts authored worlds; it does not create worlds. It rejects inputs if Laya would truncate the state, instructions or options. Its 1024-token context can therefore prevent longer actor histories from running. The adapter uses the package's reviewed checkpoint revision. CPU inference is synchronous and does not enforce the CLI timeout.

The [model card](https://huggingface.co/convaiinnovations/laya-typed-decisions) says the fine-tuning covered four synthetic workflows: agent observability, customer service, invoice processing and security incidents, not financial markets. It explicitly warns that its confidence is uncalibrated and that performance on other tasks may be worse. Its scores are not probabilities of market events. Benchmark against held-out Jev and grounded real-world decisions before relying on it for a simulation. Do not interpret the model's published benchmark as evidence of financial accuracy.

This adapter is for the existing agent-world actor interface and the NEAR lending case runner, which calls it in process ([runner guide](LENDING_CASE_RUNNER.md)). The web interface does not select this local backend. The separate MACRON lifecycle runner also supports local Laya; see the full-horizon audit in `docs/whitepaper/evidence/laya-only-audit-2026-11-06.json`.

## Lending cross-check with Jev (2026-11-05)

The same 90-day lending worlds were run on Laya and on Jev. They disagreed on every behavioral result. Given the option to borrow, Laya borrowed in 258 of 260 cases at an 8%+ rate and 292 of 295 at 2%. Jev borrowed in 2 of 219 and 2 of 218, with mean borrow scores of 0.157 and 0.164. Neither model changed its choices when the rate rose 2.5×. Laya's top-option score averaged 0.52–0.56; Jev's averaged 0.61. Treat behavioral results from either model as model-dependent until a second model, or real user data, agrees.

## Shared System One interface

Both clients expose `evaluate(state=..., questions=...)` and return `answers` and a provenance `receipt`. For HTTP use, start `engine/.venv/bin/python -m decision_lab.laya_server`. The local endpoint is `http://127.0.0.1:8765/v1/systemone`; the Jev endpoint is `https://api.typesafe.ai/v1/systemone`. Both accept `{model,state,questions}` and return `{model,answers,usage}` for the supported Choice/Noul subset. Supply the appropriate model identifier for the selected provider; model outputs and confidence values are not interchangeable merely because the wire shape matches. This server is deliberately bound to loopback and rejects incomplete inputs. `--transport laya-http` selects it for authored agent-world runs. MACRON continuations currently call the same Laya adapter in process.

MACRON continuation is separate from the archived Jev runner to preserve its replay hashes. `engine/tools/continue_laya_lifecycle.py` replays and verifies the Jev checkpoint before saving every new Laya decision and lifecycle state in a new output directory. The resulting path combines Jev history with Laya continuation; it is neither a wholly Laya simulation nor a forecast. `engine/tools/compare_laya_macron.py` evaluates Laya on the exact saved observations for a small matched comparison.
