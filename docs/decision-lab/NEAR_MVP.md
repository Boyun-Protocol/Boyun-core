# Live NEAR testnet commitment registry

The strategic product now has a working chain integration, separate from the
older unsigned descriptor in NEAR_RECEIPTS.md. It records a
salted commitment to exact result bytes, then verifies final execution and the
stored registry record. It does not launch a token, trade, use Intents as
anonymity, or claim that a simulation is accurate because it is on chain.

## Actual deployment and product acceptance, 25 October 2026

- Network: **NEAR testnet**; dedicated faucet-funded demo account.
- Contract: `csl-registry-2e4069fc870d.testnet`.
- Expected deployed code hash: `9Fc8Eu3Tj589sxW5oQngK4MqrmTgA2zuaU2JzK1uVcS7`.
- Wasm SHA-256: `7a9b57ae0a7144dacb46389af14dac263c0b346906711fc731455758c1e03b3c`.
- [Deployment and initialization](https://testnet.nearblocks.io/txns/31nhjUFs5ZzNevuNmgSvDMCwoPyVtd9g7x7cMBDDxvNo) reached FINAL.
- [Latest three-world Jev result, submitted through the product](https://testnet.nearblocks.io/txns/5bndMfLmVRqw33W3ZFzf7tsEJbyaGNUquf4cDwCoPFm2)
  returned **final_verified**. Recorded burnt gas cost: `220235605126700000000`
  yoctoNEAR, approximately 0.0002202356 testNEAR. Storage funding is separate.

The local receipt verifies the transaction hash, signer/receiver, exact method
and commitment argument, gas/deposit bounds, final success, receipt outcomes,
current pinned code/version and matching final record. Read verification trusts
the pinned testnet RPC; this is not a standalone light-client proof. A transient
429 initially delayed an earlier verification; explicit read verification later
succeeded without resubmitting the transaction.

## Product flow and privacy

1. Finish a run and open its presentation.
2. On the final slide, choose **Record on NEAR testnet**. This creates a private
   opening for the exact downloaded result bytes. No RPC or submission occurs.
3. Connect a testnet wallet, choose **Review transaction for my wallet**, then
   approve the reviewed transaction in that wallet. Alternatively choose the
   separately labelled **Use operator demo relay instead** to submit once from
   the operator account.
4. Read the resulting transaction/registry verification. If uncertain, use
   **Verify from NEAR** to repeat reads, never submission.
5. Keep the exact result download and private opening together. Sharing an
   opening allows candidate artifacts to be checked against its raw artifact hash.

Only a salted commitment enters contract arguments. Scenario text, API keys,
persona private observations, salt and raw result hash remain off chain. The
relayer identity, transaction and timing are public. This establishes byte
consistency when opened, not creator identity, forecasting quality, creation time
of the underlying content or anonymity from the operator/provider.

One fresh dedicated testnet credential is retained on the host, mode 0600. It
never enters a browser, prompt, process argument or repository. It is a full-
access demo key, so the account can still upgrade the contract. Current code-hash
pinning detects a different deployment at verification time; this is not a
permanently immutable-contract claim.

## Contract and runtime

Sources: `contracts/commitment-registry/`, Rust + pinned `near-sdk = 5.29.1`.
The immutable first record contains commitment, signer and decimal-string block
height/timestamp. Duplicate registration returns the existing record and refunds
attached funding. Calls attach at most **0.01 testNEAR** and 30 Tgas; actual record
storage is retained, excess is refunded, and gas is additional.

```sh
cargo test --locked --manifest-path contracts/commitment-registry/Cargo.toml
cargo build --locked --release --target wasm32-unknown-unknown \
  --manifest-path contracts/commitment-registry/Cargo.toml
npm ci --ignore-scripts --prefix tools/near-mvp
```

The Node helper uses locked `near-api-js` dependencies, explicit testnet RPC,
pre-broadcast transaction identity and owner-only operation files. It never
retries a broadcast. A shared credential lock serializes submissions across app
processes. Interrupted reservations stay inspectable and cannot cause automatic
double submission.

The submission machine already has the dedicated credential. Start the product
with these additional flags (replace the credential path with your private file):

```sh
uv run --project engine decision-lab serve --port 8769 \
  --output-dir engine/output/strategic-product-2026-10-25 \
  --typesafe-env-file .env --typesafe-api-key-env TYPESAFE_API_KEY \
  --typesafe-http-client curl \
  --near-registry-contract csl-registry-2e4069fc870d.testnet \
  --near-registry-code-hash 9Fc8Eu3Tj589sxW5oQngK4MqrmTgA2zuaU2JzK1uVcS7 \
  --near-relayer-credential-file /private/path/credential.private.json
```

Startup makes no model or chain requests. A wheel installation needs Node, the
checkout's `tools/near-mvp/` dependencies and an explicit absolute
`--near-relayer-script /checkout/tools/near-mvp/submit-testnet.mjs`; these helpers
and the Rust project are not embedded in the Python wheel. The preview module
accepts the same NEAR contract/hash/credential/script flags.

If deploying a separate operator-owned demo registry, `create-testnet.mjs` accepts
an explicit **new** private output directory; `submit-testnet.mjs deploy` accepts
that credential, a **new** operation directory and the built Wasm path. Faucet
availability and storage/gas balance remain external dependencies. Do not run
these steps again merely to open existing results.

## APIs and verification boundaries

Product POST routes end in `/near/prepare`, `/near/submit` and `/near/verify`, on
either a current session or preserved result. The browser cannot choose arbitrary
RPCs, mainnet routes, receivers or methods. Origin and CSRF checks apply. The
private `/near/opening` attachment is an explicit authenticated download in the
invite preview. No model or chain call runs when mounting a result presentation.

Tests cover finality/code/network/intent mismatches, missing or failed receipts,
exact-byte commitments, uncertain-submit recovery, cross-process credential
locks, no automatic resubmission and HTTP origin/CSRF boundaries. The chain
acceptance above is additional real testnet evidence; no live NEAR Intents,
Chain Signatures, private inference or mainnet integration is asserted.

## Browser wallet integration — 26 October 2026

The header now offers **Connect testnet wallet** using the pinned NEAR Wallet
Selector Intear adapter. This is an explicit user action, not startup behavior.
The account is displayed as a connection, not treated as authenticated ownership.
An accepted, finalized transaction is independently verified by the backend.

On the result's final slide:

1. Prepare the result commitment and connect an Intear **testnet** account.
2. Choose **Review transaction for my wallet**. The server checks the pinned
   deployed contract and produces a fresh salted wallet-specific plan. An old
   operator receipt cannot masquerade as this wallet's signature.
3. Inspect signer, receiver, `register_commitment`, public digest and funding.
   Approve only **0.01 testNEAR plus gas** to the stated testnet registry.
4. Choose **Approve in my testnet wallet**, then approve in the wallet itself.
   The server reserves one attempt; cancellation or an uncertain outcome never
   automatically retries. Plan approval expires after fifteen minutes.
5. Verify FINAL execution and matching exact commitment/signer/record. Download
   **the wallet private opening**, which is distinct from the operator opening.

Plans and private openings are stored in each reviewer's private result folder.
The browser retains only the pending plan ID/result route/transaction hash in
session storage for explicit verification after refresh. Resuming never signs or
submits. The wallet's SDK manages its own app-authentication material in browser
storage; no seed phrase/full-access private key is requested by this product or
sent to the server or model. Wallet connection/account IDs are not appended to
persona prompts. The signer and chain transaction remain public.

No callback query bypass or weaker reviewer cookie is needed: Intear uses its
wallet frame/popup and message boundary. Only the reviewed wallet frame and
fixed testnet RPC/logout bridge are added to CSP. The local build adds missing
origin/source checks to two pinned SDK listeners and rejects alternate wallet
URLs/mobile bridge mode. See `tools/near-wallet/README.md` for rebuilding,
licenses and the ten low-severity dependency audit findings (no moderate/high/
critical findings at the time checked). Do not claim the patch is upstream audit.

The local browser loaded the real connection screen; a cancelled connection
returned without submitting. The HTTPS preview served the wallet bundle and
enabled capabilities for all three isolated reviewer accounts. Wallet request/recovery verification is
covered by fixtures and HTTP boundary tests. **A human's connected wallet approval
has not yet been observed**, so this is not evidence of a completed external-
wallet transaction. The already completed operator-signed testnet transaction
above remains separate real chain evidence. Final acceptance requires the user
to connect/fund a testnet account and approve one reviewed transaction; no wallet
seed or key should be sent in chat.

MyNearWallet's site announced sunset on 31 October 2026 when checked; it is not
used as the MVP wallet dependency. The official
[Intear adapter](https://github.com/near/wallet-selector/tree/main/packages/intear-wallet)
documents testnet configuration. Keep wallet-provider availability and final
human approval explicit in a submission claim.

For the remaining NEAR integrations and submission acceptance gates, see
the 26 October readiness audit.

## Grounded pilot receipt — 26 October 2026

The four-call Jev pilot with frozen public NEAR context was recorded through
the operator relay and verified FINAL. Transaction:
[55117LoQgVA7m7o1smxibJNCV5vq1PCTxighVCRsnSCq](https://testnet.nearblocks.io/txns/55117LoQgVA7m7o1smxibJNCV5vq1PCTxighVCRsnSCq).
The result remains private; only its salted commitment and public transaction
metadata were submitted. This does not replace external browser-wallet approval.
See the current demonstration.
