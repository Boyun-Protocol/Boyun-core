# NEAR AI Cloud author adapter

`decision_lab.near_ai.NearAITextModel` supplies the world-author role. It uses
the fixed `https://cloud-api.near.ai/v1/chat/completions` endpoint and an explicit
canonical `organization/model` ID. Shorthand and moving `latest` selectors are
rejected. The request sends `x-no-aliasing: true`, disables streaming, requests a
JSON object and supplies the selected key only in the Bearer header.

Construction does not contact NEAR AI. A call to `generate(messages)` makes one
inference request. The two messages must have the `system` and `user` roles, in
that order. Generation returns `{"value": <JSON object>, "receipt": <metadata>}`,
matching the existing text-model interface. The caller must still validate the
world schema and obtain the explicit author-call approval before dispatch.

The default timeout is 180 seconds and the requested output limit is 8192 tokens.
The caller may select a timeout from 1–300 seconds and an output limit from
1–16384 tokens. Responses are bounded to 1 MiB. The default transport disables
redirects, environment proxies and automatic retries. Injected transports must
preserve those restrictions.

HTTP failures expose `NearAIError`, a `ModelFailure` subclass, with `status`,
`retry_after_seconds` and `safe_details()`. The safe details distinguish key,
credit, access, rate-limit and server failures without reflecting provider
bodies. A `Retry-After` header is converted to a delay capped at one day; the
adapter never retries automatically. After a timeout, remote execution and
billing remain unknown.

For an explicit metadata read, call `get_models()`. This makes a separate GET to
`https://cloud-api.near.ai/v1/models`; it is never called by construction or
generation. It returns sanitized model IDs, recognized capability flags, numeric
pricing fields and available context/output limits. Unknown prose is omitted.
The result marks `model_requests: 0`, `catalog_only: true` and metadata as
provider reported and unverified. Price field names are retained as supplied;
the adapter does not infer price units or calculate an inference bill.

Each inference receipt records declared and reported model IDs, the provider's
completion ID when supplied, request/response/output hashes, elapsed time and
validated token usage. Missing usage stays unknown. A missing or different
reported model fails closed. Cost stays unknown, and token limits are provider
requests rather than a hard local dollar cap. Selected-key reflections are
rejected before output or metadata can be exported.

Privacy is **UNVERIFIED**. This adapter sends plaintext over HTTPS and performs
no attestation, response-signature verification or client encryption. The host
and provider receive the prompt. A matching model string is a provider
declaration, and a receipt does not establish confidential inference or a TEE
boundary. direct TypeSafe remains a separate provider with its own disclosure and
billing boundary.

Keep the key in the caller's private session and release the imported author
when the session ends. Do not embed it in a world, report, shell argument or
repository file. No live NEAR AI inference or account access is part of the
offline adapter test suite:

```sh
cd engine
.venv/bin/python -m pytest tests/test_near_ai.py -q
```

Provider references: [OpenAI compatibility](https://docs.near.ai/cloud/guides/openai-compatibility),
[model catalog](https://docs.near.ai/cloud/models),
[verification](https://docs.near.ai/cloud/verification/cloud-api).

## Browser, server and terminal setup

See the full journey for import,
operator flags and CLI commands. `POST /api/product/author-access` configures
this role independently from Jev; `POST /api/product/author-models` explicitly
reads metadata with no inference. Hosted imports require host trust plus CSRF.
The credential commit is bound to the current preview session generation and
expiry, including requests delayed across logout or gateway timeouts.

On 26 October the authenticated catalog succeeded and exposed supported_features,
max_output_length, is_ready and pricing metadata. The adapter maps the first two
to sanitized capabilities/max_output_tokens. One real author request returned
HTTP402; no retry or fallback occurred. The user deferred funded live acceptance.
No successful live author generation is claimed by this milestone.
