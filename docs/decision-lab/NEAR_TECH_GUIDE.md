# NEAR AI Cloud and the technologies around it

Checked against official documentation on 26 October 2026. Proposed integration
plan; no new provider call, registration, transaction or deployment was made.

## Separate the jobs

NEAR AI Cloud runs model requests. Jev makes typed persona decisions through a
separate provider. Our Python engine validates and executes the world. NEAR
contracts record state and enforce contract rules. Agent Market sells jobs.
Intents obtains/settles asset routes. Chain Signatures authorizes external-chain
transactions. These are independent capabilities, not one automatic stack.

The existing app has direct TypeSafe, local rules, an optional Gemini development
world author, a pinned NEAR AI Cloud author connector with separate credentials,
a frozen observed-NEAR starter and a live testnet result registry. Cloud catalog
access succeeded; funded live generation is pending after HTTP402. The other
technologies below remain proposals unless explicitly marked implemented. See
the current end-to-end evidence.

## NEAR AI Cloud

An online model service with the OpenAI-compatible base URL
`https://cloud-api.near.ai/v1`. The usual onboarding path is a Cloud account,
Cloud credits and a Cloud API key. These are separate from direct TypeSafe actor billing and its key. Blockchain testnet balances do not pay an ordinary
Cloud API invoice. Account/API access is distinct from our testnet registry.

Useful capabilities:

- Chat, reasoning, streaming, structured outputs and tool calling on supported models.
- `/v1/models` metadata: canonical IDs, feature support, context/output limits and pricing.
- Embeddings and reranking for retrieving relevant articles or past cases.
- Additional image/audio routes, which are not needed for our first integration.
- Stateless Responses with client-managed history and `store: false`; this is not
  a blanket statement about every operational log or other endpoint's retention.
- Attestation and response-signature verification; optional client encryption on
  compatible NEAR-serving paths. These require explicit integration and checks.

### What the privacy labels mean

A TEE is a hardware-isolated execution environment. Attestation is signed evidence
about that environment's measured configuration. It does not prove the model's
reasoning, truthfulness or forecasting quality.

The model catalog distinguishes:

1. Confidential TEE: model execution on NEAR AI's confidential GPU infrastructure.
2. 3P Confidential TEE: a third-party enclave, with its own evidence/client limits.
3. Incognito: routing through the NEAR gateway to an upstream model provider;
   model-level TEE guarantees do not extend to that provider.

Some introductory pages describe privacy broadly. Use the selected model's
catalog tier and route-specific evidence, not that blanket wording, for product
claims. The catalog notes that its Python SDK's third-party verification can be
gateway-only where the JavaScript SDK verifies the relevant model evidence.

There are separate properties to verify: gateway deployment, model deployment,
live TLS connection binding, exact response integrity and software-image policy.
A completion ID or downloaded raw attestation report alone proves none of them.

For compatible E2EE Chat Completions: verify fresh model-attestation candidates
and nonce, select an accepted public key, encrypt locally to it, pin the canonical
model/key/no-aliasing route, decrypt the response and verify available signatures.
The documented client-E2EE path fails if a compatible NEAR serving route is absent;
it is not a transparent feature for every catalog model. The Responses endpoint
does not support encrypted input messages. Avoid implementing custom crypto when
an appropriate verified SDK can satisfy the exact required properties.

Our own host still sees any plaintext it receives before encryption. direct TypeSafe
still sees its separately supplied persona state. Protecting world authoring
alone cannot make the entire pipeline confidential or make the creator anonymous.

### Integration into this codebase

Recommended role: **world architect**. Given the question, selected perspectives,
evidence and capability guidelines, propose a structured world and ask material
follow-ups. The user reviews; code validates; Jev supplies actor decisions;
Python performs settlement/replay. Explanation can summarize numeric results,
but models must not silently recalculate balances or invent calibrated odds.

Implemented for the basic HTTPS route:

1. `near_ai.py` pins the Cloud endpoint, exact model ID, JSON output, bounded
   no-redirect/no-retry transport and sanitized errors/catalog/usage receipts.
2. `configure_author()` and `configure_access()` keep imported author/actor keys
   independent and process-only. Hosted use requires host consent; logout,
   expiry and rotation invalidate even delayed credential commits.
3. Browser and CLI separately approve authoring and persona execution. The
   selected-provider disclosure replaces Gemini-only wording for Cloud; the
   Gemini development route retains its public/fictional restriction.
4. Results retain replay, cost accounting, private MD/PDF and the existing
   verified NEAR testnet commitment. Read-only source context can be frozen
   through the observed-NEAR starter.

The authenticated Cloud catalog succeeded, but the first author request returned
HTTP402. Funded live author acceptance is deferred by the user. Verification of
attestation/TLS/model responses and client E2EE remain separate future work;
there is no silent downgrade or current verified-confidential mode.

Configure `NEAR_AI_CLOUD_API_KEY` locally or use the independent author import in
Setup, never chat. See [the implemented adapter](NEAR_AI_SETUP.md) and
complete current journey.

## Other technologies and concrete product roles

| Technology | Job | Integration in this product | Priority / limit |
| --- | --- | --- | --- |
| NEAR accounts, wallet and contracts | User approval and contract-enforced state | Existing testnet result commitment; later a request/worker/delivery/refund lifecycle | Keep and finish external-wallet acceptance; existing receipt is operator-signed |
| Public RPC / chain data | Observe actual accounts/contracts at identified blocks | Read-only balances/token metadata/venue state, source references and units in reviewed input | Useful grounding; must map evidence explicitly, not infer motives or inject actor capital automatically |
| Agent Market | Sell a bounded agent service | Receive assignment, record/start it before compute, run our engine, submit Markdown/PDF link, handle revisions and delivery failures | Strong commercial extension; separate live account/token/price/payment terms; no claimed testnet support |
| NEAR Intents / 1Click | Obtain quotes and settle supported asset routes | After a decision, show a supported funding route with amounts, fees, slippage and expiry | A real `dry: true` quote is feasible; no testnet. Funded settlement needs mainnet authorization |
| Confidential Intents | Confidential asset-transfer flows | Optional privacy for an approved funding/treasury transfer | Does not encrypt our brief, API keys or Jev inference; does not establish total creator anonymity |
| Chain Signatures | MPC signing for foreign-chain accounts controlled through NEAR | Future constrained external-chain action after explicit approval | Needs target-chain payload, chain-specific derivation, fees and broadcasting; signing does not read or verify external state |
| IronClaw | Agent runtime with tools, isolated jobs, permissions and credential boundaries | Optional operator/analyst worker wrapping our engine as a constrained tool | Useful later if persistent connectors/jobs justify it; one runtime per simulated persona is unnecessary |
| Staking for Inference | Convert staking rewards into Cloud compute credits | Possible later operator funding option | Not required for MVP; yield/coverage varies and it does not automatically fund direct TypeSafe actor usage |

Agent Market does not host the underlying agent/model today. Its self-hosted
worker accepts assignments, starts them, delivers Markdown and handles revisions.
The marketplace sees submitted briefs and deliverables; the internal code and
model run on our side. Do not paste confidential full reports into a marketplace
without an explicit sharing decision. Its service/payment terms are not our own
decentralized escrow contract.

The simulated 100 personas are logical actors. They do not each need a funded
wallet, a server, a Chain Signatures account or an IronClaw installation. Add real
wallets only for actual independently authorized economic actors.

Shade Agent Framework is deprecated as standalone tooling after 19 April 2026;
it is not a sensible default dependency for a new MVP without maintenance plans.

## Recommended scope

First: fund and accept the implemented NEAR AI world-builder, retain Jev
decisions and complete a verified user-wallet testnet receipt. Next choose **one** extension based on the demo:
Agent Market for paid reports, or Intents dry quotes for a funding-decision story.
Add custom job escrow or Chain Signatures when the product needs those execution
semantics. Inference privacy, custody/execution authority and result integrity
remain separate properties throughout.

## Official references

- [Cloud quickstart](https://docs.near.ai/cloud/quickstart)
- [Cloud OpenAI-compatible API](https://docs.near.ai/cloud/guides/openai-compatibility)
- [Model capabilities and privacy tiers](https://docs.near.ai/cloud/models)
- [Gateway/model/response verification](https://docs.near.ai/cloud/verification/cloud-api)
- [E2EE protocol and limitations](https://docs.near.ai/cloud/guides/e2ee-chat-completions)
- [Agent Market worker integration](https://docs.market.near.ai/list-your-agent)
- [Intents quickstart: no testnet](https://docs.near-intents.org/integration/distribution-channels/1click-api/quickstart/introduction)
- [Intents request and dry quotes](https://docs.near-intents.org/integration/distribution-channels/1click-api/quickstart/making-a-request)
- [Chain Signatures](https://docs.near.org/chain-abstraction/chain-signatures)
- [IronClaw source](https://github.com/nearai/ironclaw)
- [Staking for Inference](https://docs.near.ai/cloud/staking-for-inference/overview)
- [Shade deprecation](https://docs.near.org/ai/shade-agents/getting-started/introduction)
