# Development agents and verified model access

For **external agents using Boyun**, see [MCP and agent support](MCP_AGENTS.md).
The remainder of this document concerns the engineering agents that built the
software, a separate role from MCP clients and simulated personas.

**Current routing (2026-10-23): Gemini and Codex only, as requested by the user.** Do not launch OpenCode jobs, Copilot setup or further credit/connection experiments. Preserve previous attempts as historical evidence. Codex implements and reviews code; Gemini Flash supplies bounded critiques and a public synthetic policy pilot through the already working Antigravity CLI. The GitHub findings are historical account research, not an active dependency or available product inference budget.

User clarification: their GitHub Pro comes from Education. Copilot activation/allowance was not verified. No GitHub inference or spend occurred. Paid-plan references below must not be treated as available student model routing; no further setup is requested now.

Current execution and acceptance gates: work status, core commands. Older routing and connection evidence below is retained as a chronological record, not an instruction to resume those tools.

Checked locally on 23 October 2026. This concerns agents **building the software**, separate from personas inside simulations.

| Worker | Task | Actual status |
|---|---|---|
| Codex controller | Event runner, retained beliefs, keyed randomness, CLI, integration and regression fixes | Implemented and locally tested |
| Codex finance worker + independent reviewer | Conserved integer ledger, AMM, LP shares/locks, atomic replay | Implemented; independently reviewed |
| Codex actor/policy worker | Scenario cast, role bindings, finite attention, bounded policy proposals | Implemented; focused tests verified |
| Codex whole-core reviewer | Find integration defects across accounting, visibility and comparison | Found campaign evidence leakage, role-description mismatch and forgotten observations; fixes required before acceptance |
| Antigravity `gemini-3.8-flash-high` | Adversarial design review and negative-case suggestions | A real model response was obtained and inspected; useful suggestions accepted only after verification |
| OpenCode `opencode/glm-5.3-flash-free` | Intended financial negative-test proposals | Original worker task failed providerHTTP403; retry profile prepared, no model contribution counted |
| OpenCode `opencode/deepseek-v4.1-flash-free` | Intended interaction/visibility negative-test proposals | Original worker task failed providerHTTP403; retry profile prepared, no model contribution counted |

## Routing rationale

Codex owns authority-sensitive financial code and integration because it can inspect the repository, execute regressions and review the exact resulting changes. Gemini Flash receives small public synthetic specifications for independent critique, where lower latency is useful and every suggestion remains untrusted until checked. GLM/DeepSeek are provisional choices for bounded candidate tests, not empirically ranked winners; runtime access must be proven before they receive work. Smaller models may help propose cases and documentation, but never decide financial settlement.

Antigravity's installed model list includes Gemini Flash variants, Claude Sonnet/Opus variants and GPT-OSS. Only `gemini-3.8-flash-high` was used successfully for a substantive review. One recorded response took76.24seconds and reported7,303input/7,034output tokens, including thinking as reported by the CLI. The account did not expose a dollar-price guarantee; this is **not** a claim that Antigravity calls are free. An additional follow-up attempt produced no captured response and is not counted as a contribution.

OpenCode v2.0.12 lists several free model IDs, including GLM5.3FlashFree and DeepSeek4.1FlashFree. The provider nevertheless rejects CLI requests with “OpenCode's free tier can only be used from within OpenCode.” Both standalone and ordinary CLI modes were checked. The user reports their app works and will provide its normal connection method; no provider restriction, credentials or global configuration were bypassed, and no paid fallback was selected.

Official model/config references consulted: [OpenCode models](https://opencode.ai/v2/docs/console/models/), [configuration](https://opencode.ai/v2/docs/config/), [agents](https://opencode.ai/v2/docs/agents/). Local executable help takes precedence over stale skill examples: the installed version uses `agents`/`permissions`, does not support `--pure`/`--dir`, and the tested prompt is a direct positional argument without a `--` separator.

## Review adjudication

Accepted Gemini recommendations: isolate policies from hidden global state; use independently keyed external draws for matched plans; enforce minimum output at execution; deduplicate claim origins; specify deterministic execution ordering. Existing tests and new integration regressions verify these mechanisms.

Rejected or corrected recommendations:

- AMM reserve product need not increase across LP withdrawals; removing liquidity reduces reserves by design. Swap arithmetic and share accounting require separate invariants.
- Ending cash minus initial contributed capital already reflects paid expenses and LP deposits. Subtracting LP contribution again double-counts cash outflow; clipping negative profit to zero hides losses.
- A claimed zero-cost rounding drain was not demonstrated. The runner requires positive output; fee-retaining integer floors and conservation are tested. Zero-minimum primitive calls are allowed to donate dust, so callers must supply a meaningful minimum.

## Working protocol

Each task receives the minimum synthetic context, an exact file scope or return format, and a review gate. External reviews receive only public synthetic task context, without API keys, private plans or wallet material. The public profile permits exact-input read and requests approval for other tools; effective runtime authority is not attested. Raw development logs and task briefs stay in gitignored `.orchestration/`; this document preserves the sanitized outcome. A response is counted only when captured and inspected, never from an empty exit or a listed model ID.

The project-local OpenCode agent configuration still denies all tools. The optional public-review worker profile stages only public task input in a separate workspace and uses approval-gated permissions. This is not an OS sandbox. Accept model suggestions only after local tests and independent review.

## Follow-up connection evidence

The user supplied actual shell output from inside OpenCode: native2.0.12 returned READY from GLM5.3FlashFree. Thus the model works in that legitimate context; Codex-origin failures do not establish account-wide unavailability.

Retested from Codex: native2.0.12, app-bundled2.1.3, shared service2.1.3, and the supported mini/TUI flow all returned the same403. The app identifies its connection as sidecar, separate from the shared CLI service. Targeted app-listener checks did not find an unauthenticated documented v2 endpoint. No auth material was read and no origin/header was forged. Native UI could read the working app, but attempted controls did not create a new session; the user's existing chat was not messaged.

The local-file worker was subsequently launched by the user inside OpenCode. Both original tasks failed403 under the deny-all profile. The user bisected this configuration issue; see recovery evidence below. No successful model review has been recorded.

A later Antigravity policy-review call exited0 with a SUCCESS envelope but an empty response and zero reported tokens after about125seconds. It is counted as **no substantive response**, not an additional accepted review. The earlier substantive design response remains the verified contribution.

The bounded queue worker and instructions were in `tools/opencode_worker.py` and `tools/README.md`. The initial version had25 isolated tests and independent review; the public-profile extension brought the worker to34 cases. The two original jobs were claimed and their error results/logs are retained. Those tests inject subprocess responses and do not establish real OpenCode connectivity; inspect actual job results before updating this status. **2026-10-31: the retired worker, its tests and the project-local OpenCode configuration were deleted for the release package; the history above stands as recorded evidence.**

## Deny-all compatibility and recovery

User supplied an actual inside-OpenCode bisect: original wildcard-deny permissions produce403, while a neutral directory/custom agent without permissions or an allow policy returns READY. Invalid object-form permissions can make the custom agent disappear, so READY from a fallback agent is not a fix. The deny-all configuration was introduced by this project's development tooling; the prior context-only diagnosis was incomplete.

Codex verified both original job errors and then tested narrowed supported permissions against a disposable public fixture. Deny-all plus exact read, execute allowance, wildcard ask, and minimal configs without custom permissions still returned403 from the Codex invocation context, including outside repository ancestry. Thus removing deny-all is not a demonstrated sufficient fix here. No credentials/global configs were inspected and no client identity was spoofed. No paid model was selected.

Recovery uses an optional public-review staging profile: create a separate temporary workspace outside repository ancestry, stage only the synthetic prompt, use exact public-input read access and wildcard approval requests for other actions, and omit autoapproval. The repository's restrictive agent remains unchanged. Staging reduces initial context exposure but is not OS isolation, a guarantee against Code Mode/network effects, or an attestation of inherited runtime permissions. The author must enqueue only public synthetic material.

Retry jobs use new IDs; original `.running`, result and log files remain as evidence. Actual inference through the new profile remains unverified until the user's working OpenCode shell returns captured model text. A pending approval or timeout is not a completed contribution.

Permission syntax and limitations were checked against [official permissions](https://opencode.ai/v2/docs/permissions/) and [configuration](https://opencode.ai/v2/docs/config/).

The public profile adds9 worker regressions (34 worker cases;230 combined with the196 core tests). These inject subprocess results and make no inference calls. New `-02-public` jobs are queued; the earlier two `-01` errors remain unchanged.

Actual public-profile retry results were subsequently observed: both `-02-public` tasks returned provider.auth403, exit1, emptyresponse. Staging did not solve the provider condition. No third permission relaxation or paid switch is being applied. A direct-existing-agent review brief is ready in ignored local storage; the working OpenCode agent can review the named public files without nested CLI calls and write a separate report. This would be recorded distinctly from failed queued invocations.

## Bounded retry experiment

User subsequently supplied repeated READY evidence from identical manually invoked staged configuration and a full review that exceeded150seconds. Retrying the public profile is now an explicit, bounded experiment rather than a guarantee of provider behavior. Added up to3attempts, waits5/15seconds, and configurable30–600second CLI wait (default120; current live jobs use300). Defaults remain one attempt; legacy deny-all rejects multiple attempts.

Only completed nonzero `provider.auth`403/FreeTierError envelopes without text/thinking/tool/unknown-event evidence can retry. Actual recorded OpenCode step-start snapshot metadata is accepted. Timeouts/partial output/log-I/O/backoff errors are terminal, and timeout does not attest generation cancellation. Every attempt has exclusive logs and a checkpoint before waiting; task/config/workspace/model remain fixed.

Independent review caught and fixed misleading status after log/backoff errors and overly permissive step-envelope classification. Verification:280combined tests, including81worker tests. These tests inject subprocess/wait behavior. Two fresh `-03-bounded` public jobs are the real inference gate; old jobs are not reset. No paid fallback or auth/identity manipulation is used.

Live bounded experiment completed: both `-03-bounded` jobs exhausted3attempts with recognized provider.auth403 and no text. Six real refused requests were captured, including5/15second backoffs; no timeout occurred, so the300second generation wait was not exercised live. No successful OpenCode engineering contribution is counted. Stop automatic experiments at this budget; preserve every attempt. Direct existing-agent review remains the fallback without nested CLI calls.


## Live world integration, 24 October 2026

User correction: no UI work. New `decision-lab agents simulate` constructs a
world through a real model call, then calls the isolated actor contexts and
routes their actual messages through the world engine. This supersedes the
prior policy-only integration limit; it does not change the historical OpenCode
failures or turn earlier fixtures into live evidence.

Gemini `gemini-3.8-flash-high` completed 7 requests: 1 builder plus 3 roles × 2 rounds,
5 messages and 6 hold decisions. Retail's second actual prompt and response contain
`agent:1:analyst`. Source/context boundaries, financial execution and exact
no-inference replay are recorded in LIVE_AGENT_WORLD.md.
All data was public synthetic; no confidential plan, user API key or chain action
was used. This is developer CLI access, with unknown dollar cost, not a deployed
product API or predictive-quality result.
