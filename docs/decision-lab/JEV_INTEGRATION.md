# Direct TypeSafe Jev integration

Updated 28 October 2026. Direct TypeSafe System One is the active Jev route.
Earlier retired-provider pilot records are not direct TypeSafe acceptance;
native live acceptance pending. Saved artifacts remain historical and are not
rewritten or rerun by this migration.

## Contract and limits

The pinned inference endpoint is `https://api.typesafe.ai/v1/systemone`, using
`Authorization: Bearer <selected key>`. The request contains `model`, `state` and
named `questions`; the native response contains `model`, `answers` and `usage`.
The default model is `jev-latest`. Explicit supported version identifiers may be
selected; a configured model is not proof of account access or model availability.

The client supports typed Choice and Noul. The strategic product asks one Choice
question over each actor's affordable actions. Jev selects structured alternatives;
it does not author worlds, biographies or free-text reports. Numeric settlement,
information filtering and replay remain under engine control. Model scores are
conditional action scores, not calibrated real-world event odds.

Conservative local bounds are 48,000 canonical UTF-8 state bytes, 65,536 request
bytes and 16 questions; each Choice has 2–32 options. The product also bounds
future prompt growth, saved artifacts and total actor calls. No prompt is silently
truncated to fit. The call cap controls dispatch. Token/list-price estimates are
not enforced dollar caps or tokenizer guarantees.

## Local server setup

Create a direct TypeSafe key in the [official console](https://console.typesafe.ai/home).
Keep it local; never paste it in chat or put the value in command arguments.
Use an explicitly selected owner-only file containing `TYPESAFE_API_KEY=...`:

```sh
uv run --project engine --extra pdf decision-lab serve --port 8769 \
  --typesafe-env-file .env --typesafe-api-key-env TYPESAFE_API_KEY \
  --typesafe-model jev-latest --typesafe-http-client curl
```

Alternatively export the selected process variable and use `--enable-typesafe`.
`--typesafe-api-key-env NAME` chooses exactly one variable. There is no automatic
search for dotenv files, evaluation of shell expressions, old-key fallback or
provider fallback. `--typesafe-http-client urllib` selects the standard-library
transport explicitly; `curl` selects the curl transport. Both use the pinned origin.

The browser's AI & privacy setup can import a direct TypeSafe key into process
memory. Hosted imports require acknowledging that the host receives the key and
scenario plaintext. Closing a tab does not delete an imported key; explicit
forget/sign-out and process exit clear the active imported access. Saved private
artifacts are separate owner-only plaintext files.

## Explicit catalog check, then execution

Startup, navigation and ordinary bootstrap polling make no provider request.
The explicit free catalog check calls `GET https://api.typesafe.ai/v1/models`.
The local endpoint is `GET /api/product/typesafe/models`; the browser receives
sanitized model names and a cached `typesafe_health` result, never credentials or
arbitrary provider metadata. This confirms catalog access, not paid inference,
a prepaid balance, throughput or forecast quality.

Review the world, actual configured actor route, model, rounds, sampled worlds
and actor-call ceiling before approving a run. Authoring is a separate provider
operation. Ready worlds require no author inference. A forced single affordable
action skips actor inference. No automatic paid retry or silent route switch occurs.

Each dispatched native response retains provider-reported model and token usage,
request/response identities and a published input list-price estimate. These are
not billing attestations. HTTP/access/rate-limit/transport errors stop the run;
unknown remote outcomes remain unknown. Cooldown checks do not dispatch a new
request. Revoking imported access prevents future dispatches and prevents an
old in-flight catalog result from becoming the current cached access check.

## Preview allowance

The invite gateway can wrap operator-funded provider calls with a persistent
per-reviewer call allowance. `--operator-jev-call-budget 200` permits at most 200
reserved native calls per reviewer across restarts. Each validated dispatch
reserves one call durably before contacting the provider; failures/timeouts are
not automatically refunded. This is neither a token allowance nor a money ledger.
Old allowance schema files fail closed rather than being reinterpreted as calls.
Operator-funded text generation uses a separate counter with its own schema,
`--operator-author-call-budget 200`, covering the author route and the Gemini
decision actor. See public-test controls.

## Acceptance and references

Injected native response fixtures test parsing, call caps, failure handling,
privacy and exact settlement replay. They do not establish authenticated direct
TypeSafe inference. A future live acceptance must preserve the native request,
returned model/token receipt and replay evidence under an explicitly approved
call budget. No such live request was made for this migration.

Official references: [quickstart](https://docs.typesafe.ai/introduction/quickstart),
[System One](https://docs.typesafe.ai/api/system-one),
[model catalog](https://docs.typesafe.ai/api/list-models),
[models and prices](https://docs.typesafe.ai/models).
[Cost arithmetic](JEV_COSTS_MVP.md) · current status.
