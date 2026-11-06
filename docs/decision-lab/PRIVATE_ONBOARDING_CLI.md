# Private setup and the terminal journey

26 October 2026. The browser and CLI share ProductManager, reviewed templates,
persona controls, validated action menus, budgets, settlement, replay and reports.

## First-run choices

Open the app and choose one of:

- **Offline rules on this host:** no external model or NEAR requests. A disclosed
  deterministic policy scores each affordable action by its own immediate utility
  change, applying metric bounds and cash cost. Ties follow menu order. It ignores
  narrative motivations, peer messages, joint responses and future events. Its
  one-hot action weights are not confidence or empirically fitted odds. Repeated
  worlds can be identical. This is a local baseline, not offline Jev inference.
- **My direct TypeSafe key:** paste into the transient password field. Import validates
  the format only; it makes no provider request. A separate free access check
  checks model-catalog access. Paid execution requires the reviewed world/actor-call budget.
- **Configured operator account:** explicitly use the existing host configuration
  and shared provider account. No automatic fallback from an imported key to this account.

Direct TypeSafe is the imported actor-key integration; the world author has a separate key. Jev returns typed
answers; it does not author prose worlds. Ready worlds need no author call.
The existing local Gemini development author is available only through the
explicit operator route and remains public/fictional-input only. Arbitrary
provider URLs, model-key uploads and OS credential storage are not implemented.

## What “session-only” means

An imported key exists in the browser's password field during entry, then in the
request body to the selected backend, and in that backend's client memory. The
field is cleared after import/failure/close. It is never written to localStorage,
sessionStorage, URLs, scenario JSON, report files, access logs or command argv.
No plaintext key endpoint can read it back. Imports retain the existing exact
Origin, CSRF, JSON/body bounds and CSP restrictions. Only the fixed direct TypeSafe
HTTPS endpoint is allowed. Existing server-managed .env credentials are separate;
this feature neither overwrites nor deletes those files.

**The backend must see a usable key to call the provider.** A local installation
keeps it on your machine; a hosted preview requires an explicit host-trust
acknowledgment before key entry. HTTPS protects transit, not against the host.
Use a limited test key. The host, model provider, browser extensions, compromised
OS, swap/crash dumps or debuggers are outside a guarantee of secrecy. Python
cannot guarantee that removed strings are zeroized from RAM. No end-to-end
provider-key encryption or zero-knowledge execution is claimed.

Local keys last until **Setup → Forget imported key and switch to offline**,
reconfiguration or process shutdown. Closing a browser tab does not revoke an
already imported key. Restart requires import again. In the invite preview,
sign-out, session expiry and replacement login also release that reviewer's key.
An in-flight request can finish; further actor dispatch stops. Clearing one
reviewer's access does not clear another's. Configuration changes are refused
while model work is active, and successful changes invalidate prior reviews.
Revocation never falls back to the operator account. Removal here does not revoke
the provider-issued credential; use the provider settings for that.

Offline on a remote preview still puts scenario data on that host. Run locally
for local-only storage. Selecting offline here does not stop independently
configured public-market collectors or other software on the machine. Network
is still needed to install packages initially; use `uv run --offline` after
installation to prohibit dependency fetching as well.

## CLI: ready world to actual report

From the repository root:

```sh
uv sync --project engine --extra pdf --dev
uv run --project engine --extra pdf decision-lab journey \
  --output-dir engine/output/my-first-journey --format both
```

Choose access, a ready world, your question, focus, retail style, team priority,
rounds, world count and action-selection policy. The terminal shows the actual
cast/actions and cost ceiling. Type `RUN` to authorize execution. Enter or Ctrl-C
stops; no provider call is automatically retried. These ready templates retain
rather than interpret your free-text question. For another world, have your
chosen agent produce a validated strategic-world JSON and pass `--world`.

Key entry uses `getpass` with terminal echo disabled. A noninteractive shell
cannot fall back to an echoed password prompt. Scripts can select an existing
process variable by **name**, never by putting the key in an argument:

```sh
uv run --project engine --extra pdf decision-lab journey \
  --api-key-env TYPESAFE_API_KEY \
  --world /absolute/path/reviewed-world.json \
  --output-dir engine/output/my-imported-journey --format both
```

The CLI does not automatically source `.env`; configure the selected variable in
your shell or use the hidden terminal prompt. Avoid shell-history key assignment.
The parent process's environment remains its owner's responsibility. This route
imports no wallet seed or NEAR private key and submits no chain transaction.

A fully local baseline needs no key:

```sh
uv run --offline --project engine --extra pdf decision-lab journey \
  --offline --output-dir engine/output/my-local-journey --format both
```

Markdown has no added package dependency. PDF uses the optional, locked ReportLab
extra. PDF availability and a new, regular destination are checked before paid
work. Output directories are new/0700 and report files are exclusive/0600;
existing files and symlinked output paths are refused. Private scenario/run
artifacts remain inspectable after a stopped or failed run. A Ctrl-C during a
provider call does not establish cancellation or refund; inspect receipts first.

## Export an existing recorded run

```sh
uv run --project engine --extra pdf decision-lab report \
  --product-dir /absolute/path/to/product \
  --session SESSION_ID --run RUN_ID \
  --output /absolute/path/new-report.pdf
```

Use `.md` for Markdown. Omit `--run` to export the current session. The browser
presentation also has **Markdown** and **PDF** downloads when PDF is installed.
Exports make no model/NEAR request. PDFs use local fonts/charts only, escape
supplied markup and contain no remote resources or active JavaScript.

Reports contain the question (when retained), world, private motivations/goals,
completion denominator, metric mean/median/range, scenario actions, modeled
spending, all saved actor billing responses from that run, unknown remote
outcomes, assumptions and limitations. Failed/unattempted worlds do not become
outcomes. Unknown billing is not zero; native input list-price estimates are not
provider invoices or enforced dollar caps. Historical saved runs may lack the original user question.

Reports are **sensitive plaintext documents**, not encrypted files. Mode 0600
protects access by other ordinary OS users; it is not encryption or protection
from the machine owner/admin. Decide what to redact before sharing. On-chain
proofs remain explicit salted commitments to exact JSON results; exported PDFs
are not automatically anchored or encrypted.

## Acceptance

An actual terminal journey completed two local worlds and produced Markdown plus
a four-page PDF with local charts. Source and installed-package flows are tested
separately. The browser import test uses an invented sentinel key and performs
no provider evaluation. Tests cover key absence from files/boot responses,
review invalidation, busy rejection, host consent, reviewer isolation,
sign-out/expiry/removal, in-flight revocation, CSRF/Origin, terminal no-echo
boundary, no-overwrite/symlink rejection, replay and full-run report accounting.
No additional paid Jev call is needed to verify this increment.

The live HTTPS path also verifies host-consent enforcement, imported-key absence
from bootstrap, offline route disabling and sign-out. The sign-out form sends
a nonempty action payload so HTTPS proxies cannot strip a zero-length header
and cause a framing rejection; exact Origin and strict cookies remain required.

## Independent world-author role — 26 October 2026

Setup can now import a NEAR AI Cloud author key and exact model ID independently
from Jev. `configure_author()` / `/api/product/author-access` creates no provider
request; `/api/product/author-models` explicitly reads the catalog. Both roles
remain process-only. Logout/expiry/rotation invalidates credential commits by
session generation, including delayed requests after gateway timeout. Switching
to offline forgets imported roles and disables external requests. An operation
already authorized for dispatch can finish and be billed.

The CLI adds `--author-near-ai`, `--author-api-key-env` and `--author-model`.
`AUTHOR` approval precedes construction and `RUN` approval precedes Jev. After
construction, cancellation means no actor calls, not no author spending.
See current commands and actual live acceptance.

## Terminal clarification loop — 27 October 2026

Cloud proposals with missing material information no longer end the CLI journey
immediately. The terminal shows each validated question and its two or three
choices. It prepares selected answers locally, displays them, then requires a
fresh `AUTHOR` token before one revision request. New answers never authorize
inference by themselves. The complete validated world still needs review and
`RUN` before any Jev execution.

`--author-max-calls 3` sets a count ceiling including the initial request; one
through six are allowed. Every call retains its own confirmation. The limit is
not a dollar price, and author charges remain separate from the Jev input-token
ceiling. Failure/invalid output stops without retry. HTTP402 names Cloud billing,
and HTTP429 explains the cooldown. Budget exhaustion keeps private request and
response artifacts; this is not cross-process resume. Keys and privacy boundaries
are unchanged. Live Cloud acceptance still requires funded quota.
