# Staged authoring for large persona casts

Large casts no longer require one Gemini response containing every biography,
private-information statement and action description. The product can author a
frozen world scaffold, then request **up to 20 persona profiles per call**, and
publish a usable world only after all assigned profiles pass validation.

This uses the actual configured `author_client.generate(messages)` interface.
It does not replace missing model responses with templates or fabricate a
completed world. Gemini writes the profiles; the deterministic engine still owns
resource constraints, information delivery and settlement. Jev remains the typed
actor decision model, not the world author.

## User-reviewed request and budget

The existing small-cast `POST /api/product/sessions` request is unchanged.
A staged request adds `authoring_plan`:

```json
{
  "mode": "author",
  "example_id": null,
  "question": "A fictional NEAR project with $10,000 creator capital needs 100 explicitly hypothetical participants, sparse information links and two rounds.",
  "public_input": true,
  "authoring_plan": {
    "mode": "batched",
    "actor_count": 100,
    "batch_size": 20,
    "max_calls": 6,
    "creator_capital_cents": 1000000
  }
}
```

The interface must show the author call ceiling before its explicit construction
button is pressed. Navigation, sliders, polling and server startup never authorize
a new generation. The Gemini development route requires public/fictional input.

`actor_count` is 2–100. `batch_size` is exactly 20. Required calls are
`1 + ceil(actor_count / 20)`: one scaffold plus one call per profile batch. A
reviewed `max_calls` below that number or above six is rejected before a worker
or provider request starts. The browser uses staged authoring for larger casts;
the API also accepts a tiny cast for bounded integration checks.

`creator_capital_cents` is optional and numeric. When present, the first roster
actor is the initiating user/team and must receive exactly that starting cash.
The code checks it before requesting any profiles. Other participants' funds
remain separate, explicit scenario assumptions. `total_initial_cash_cents` in
the scaffold must equal the sum of all roster allocations. Persona batches
cannot change either the initiating budget or other supplied allocations.

A 100-persona initial build consumes the full six-call authoring ceiling.
Clarification or revision cannot silently trigger another six calls. A staged
session's `/say` rejects implicit revisions; submit a new question containing the
answers/change and explicitly review its new author plan. If the scaffold needs
material clarification, the pipeline stops after that first call with questions
and no world. The interface can carry the answers into that new reviewed brief.
Dollar billing for Gemini authoring is unknown; these are call limits, not an
invented USD or Jev input-cost estimate.

## Why the stages exist

| Stage | Model output | Validation and purpose |
|---|---|---|
| Plan | User-requested count, batch size, call ceiling and optional creator cash | Fix the scope and spending authorization before generation. |
| Scaffold | World metadata, metrics, events, interactions; compact roster and numeric action menus | Establish the common rules and explicit resource allocations once. Check all IDs, edges, references, bounds, wait actions and cash sum before paying for profiles. |
| Profile batches | Exact assigned IDs; motivations, goals, own information, action descriptions and canned messages | Add role detail in bounded responses. Freeze action IDs/order, cash, utility weights, subscriptions, costs and metric effects. Reject extra fields, missing profiles and cross-batch substitutions. |
| Merge | All complete profiles in the frozen roster order | Require exact complete coverage, revalidate every action menu, then validate the whole world and future prompt bounds. Partial cast data never becomes a ready simulation. |
| User review | Complete merged world | The user inspects the actual personas/rules before separately authorizing any Jev/Gemini actor calls. |

The roster is not an empirical wallet population. Every motivation, utility,
cost, numeric effect and private-information assumption needs the same explicit
hypothetical provenance required by the strategic engine. More profiles cannot
silently create money, population weight or market share.

## Wire contracts

The scaffold response is:

```text
{schema_version:"strategic-scaffold.v1", context_sha256, summary, questions,
 world, roster, total_initial_cash_cents, limitations}
```

`world` contains the ordinary `strategic-world.v2` metadata, metrics, events and
interaction rules, with `actors` moved into `roster`. Each roster entry contains
`id`, `name`, `role`, `initial_cash_cents`, `utility_weights`, `subscriptions`,
`provenance` and a fixed action menu. Those actions contain `id`, `label`,
`cost_cents`, `effects` and `provenance`; they contain no biography, description or
message yet. The scaffold is capped at 200,000 canonical JSON bytes.

The code temporarily uses clearly labelled inert pending strings to validate the
skeleton's schema/references. Those strings are never model completions, never
sent to actor inference and never published as a ready proposal.

A profile batch response is:

```text
{schema_version:"strategic-profile-batch.v1", context_sha256, scaffold_sha256,
 profiles:[{id,motivation,goal,information,
            actions:[{id,description,message}]}]}
```

Both hashes must identify the current exact request/scaffold. Assigned actor IDs
and action IDs must match in the supplied order with complete coverage. Profile
text is bounded to 800 characters for motivation, goal and information;
descriptions to 800 and messages to 500. Wait must remain silent. A batch is
capped at 180,000 canonical bytes. Missing or additional numeric/resource fields
are errors, not ignored suggestions. The final merge independently checks action
coverage again so a zip operation cannot silently drop a frozen action.

Each profile request includes the public world rules, that batch's frozen slots
and public counterparties. Previously generated private biographies are not
copied into later batches. Authoring is distinct from actor inference: actors
still receive only their own permitted current observations once the user runs
the completed world.

## Private evidence and progress

Every stage saves owner-only files in the session's private directory:

- `author-N.request.json`: exact model input, written before dispatch.
- `author-N.receipt.json`: uncertain dispatch marker, selected model/route and
  hashes before the request; response-received or safe failure status afterward.
- `author-N.response.json`: the actual structured provider result, preserved
  even when subsequent semantic validation rejects it.
- `authoring-scaffold.validated.json`: frozen common rules/roster after checks.
- `authoring-batch-N.validated.json`: only the validated profiles for that batch.
- `authoring-merge.validated.json`: the complete merged proposal after final
  schema and future-prompt checks.

The directory is 0700 and files are 0600. No provider key enters the prompt,
browser, receipt or world. In-flight dispatches retain `remote_outcome:unknown`
until a response or explicit client failure establishes more. Progress reports
actual attempted and response-received calls, the current batch, and the planned
ceiling. Completed HTTP calls are not a claim that the whole cast passed.

## Stop, failure and restart

`POST /api/product/sessions/<id>/cancel_author` with `{}` uses the normal loopback,
Origin and CSRF checks. It asks the staged pipeline to stop before its next
request. An already running remote request can still complete and be billed;
remote cancellation and refunds are not claimed. Its response is preserved, then
the session becomes failed with `authoring_cancelled`, without dispatching the
next batch. Server shutdown sets the same stop flag for active staged sessions.

Malformed scaffold/profile output, missing profiles, changed hashes, resource
changes, storage failures, provider errors or route changes stop the workflow.
It does not retry, switch model, silently shrink the cast or fill gaps. Validated
partial batches remain private evidence and cannot be run as a finished world.
Restarted authoring is marked interrupted and is never automatically continued.
A new generation requires another explicit reviewed request.

## Verification and practical limits

Dedicated tests cover a 100-profile build through six injected `generate` calls,
fixed resources/action menus, exact hashes and IDs, all-or-nothing merge, creator
cash checks, pre-dispatch storage failures, partial failure, stopping during a
call, shutdown and restart without redispatch. Existing small-cast tests remain
in place. These fixture calls exercise the real dispatcher, artifact writer and
validators without provider spending; they are not a live 100-profile Gemini
quality or throughput benchmark.

Batching reduces response size; it does not remove provider context, timeout or
engine limits. The compact 100-slot scaffold still has to fit one response.
The development CLI has a 1 MiB response cap, a bounded timeout and no explicit
output-token or USD cap. Shared author messages have 256 KiB total and 200,000
characters per-message limits. Final worlds remain subject to sparse graph,
future observation and artifact limits. Compact profiles and fewer
rounds are still necessary. Authored worlds and scores remain conditional
hypotheses rather than calibrated forecasts.

## Real staged acceptance — 25 October 2026

A public, fictional 20-persona NEAR coordination scenario completed **two actual
Gemini/Antigravity requests**: one scaffold, then one 20-profile batch. The merged
world passed schema, references, future prompt and exact frozen-field checks.
The initiating actor retained exactly **$10,000**, and the explicitly assumed
other participants brought total scenario cash to $24,000. That second figure
is not a claim that more profile detail creates capital.

The route declared `gemini-3.8-flash-high`; receipts are provider/CLI reports,
not independent model attestation. Summed request duration was **227.947 seconds**
for this one example, not a throughput benchmark. USD billing is unknown.
There were **zero Jev requests** and no simulation or chain execution in this
acceptance. This is live 20-profile construction, not live 100-profile acceptance.

The ready session is `5c413e3bdd9d40bb8e950afdf424bd61` under the configured private
product output. Exact requests, dispatch markers, responses, validated scaffold,
profile batch and final merge remain local. The concise receipt is
`engine/output/strategic-scale-2026-10-25/live-batched-twenty.acceptance.json`.
Browser Resume opened the actual proposal and its 20 expandable profiles without
more inference. The initial 20-role summary avoids listing every name in the
question screen. Existing Jev/Gemini completed results remain independently
available in Saved results.
