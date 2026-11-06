# Observed data: what is connected

**Current source choice:** public-only collection accumulating forward. The
[public archive](PUBLIC_HISTORY.md) is now running; the authenticated historical
connector described below remains unused. A 30-day target does not imply that
30 days have already been collected or that gaps are absent.

The existing launch experiment is retained. This addition provides a separate
evidence layer, so measured activity can be inspected before anyone maps it to
simulation behavior. No language model is needed to calculate these features.

## Actual first capture

Retrieved on 23 October 2026 UTC (24 October in Vietnam). Raw public responses,
local observation envelopes and computed reports are retained under
`engine/output/intelligence-2026-10-24/`, outside Git and distributions.

| Dataset | Pools | Accepted swaps | Reported sender addresses | Actual timestamp coverage |
| --- | --- | ---: | ---: | --- |
| NEAR | BATCAT/wNEAR, JAMBO/wNEAR, PATATA/JAMBO | 364 | 99 | Earliest 22 Oct 19:24:57 UTC; latest 23 Oct 19:06:59 UTC; individual pools cover different intervals |
| Solana comparison | TRUMP/USDC | 300 | 126 | 23 Oct 19:07:04–19:08:41 UTC |
| Example topic | GDELT query `Trump cryptocurrency` | 10 article records | 5 normalized headline groups | Bounded 30-day search request; returned records are not a full archive |

These are recent trades of selected tokens, **not a representative sample of
new launches**. Pool creation metadata was not used to infer token/wallet age.
The pools were selected for a working data-access demonstration, not by a
pre-registered population-sampling procedure. Active and surviving pools alone
would produce selection bias in a forecasting evaluation.

The requested wallet lookback is 30 days. The actual public feed supplies a much
shorter recent slice; this is displayed per pool. The [official trades reference](https://docs.coingecko.com/reference/pool-trades-contract-address)
documents the default 300-trade/24-hour restriction and Analyst-or-higher access
for longer periods and pagination. The implemented historical collector
uses [fixed time-range requests](https://docs.coingecko.com/reference/pool-trades-contract-address-range),
an explicit local key and bounded pagination. No authenticated provider request
has been made, no key was provided, and no provider usage were consumed by that
connector during this implementation. Full 30-day collection remains pending
account access; a page/record budget can also leave a collection incomplete.

## Every stage has a purpose

| Stage | Retained artifact | Why it exists |
| --- | --- | --- |
| Select network, pools and cutoff | Observation envelope | Identifies which asset and period were actually examined; prevents accidental NEAR/Solana blending |
| Retain provider records | Raw trade response | Keeps original swap IDs, sender declarations, directions, timestamps and USD values available for audit |
| Validate and deduplicate | Exclusion/duplicate counters | Prevents repeated events, anomalous rows and unsupported token pairs from becoming extra activity |
| Derive wallet features | Per-address feature profile | Measures swap count, buy/sell count, median notional, activity span and share of the sampled flow |
| Describe cohorts | Cohort table + profile descriptions | Makes observed behavior understandable without inventing a biography or available capital |
| Preserve uncertainty | Coverage table + unknown traits | Distinguishes observation limits from model assumptions and unverified labels |
| Review context | News/social evidence report | Gives people source links and indexing dates before accepting a claim or connecting it to an event |
| Map evidence into behavior | **Not implemented** | Requires explicit assumptions about how observed features become rules; cash, risk and attention cannot be reconstructed from swap size alone |
| Validate predictions | Later historical holdout | Tests whether the mapped model predicts later unseen behavior better than simple baselines |

Swap identity is network + pool + provider event ID. One transaction can contain
several swaps, so transaction hash alone must not collapse them. Conversely,
cross-pool notional can count several legs of a route; it is not unique human
capital entering the ecosystem. Dollar values and sender addresses are provider
declarations, not independently reconciled RPC evidence.

Current size cohorts use median observed swap notional: at most $100, between
$100 and $10,000, and at least $10,000. These cutoffs are analyst choices. They do
not establish retail/whale identity. Both buy and sell observations do not prove
a profitable round trip: opening inventory, transfers, gas and earlier purchases
are missing.

## What is needed for richer personas

| Desired property | Additional evidence | What remains uncertain |
| --- | --- | --- |
| New wallet | Earliest account activity from a suitable historical index, with its coverage | A new address can belong to an experienced trader |
| One large vs many small wallets | Funding/transfer graph, timing, route traces, address labels | Shared funders or exchange withdrawals do not prove common control |
| Market maker or bot | Sustained multi-venue activity, liquidity changes, inventory/quote patterns, reliable labels | Fast or two-sided swaps alone are insufficient |
| KOL | A sourced association between a public account and an address; dated social posts | Influence, paid promotion and causal trade response need separate evidence |
| Available capital / P&L | Point-in-time holdings, transfers, valuation and execution costs | Observed swap notional is neither balance nor deployable capital |
| Reaction to news | Historical publication/availability times aligned with later trading | Correlation, selection effects and competing news can confound the result |

An actor can later combine an observed cohort with explicitly assumed risk,
attention and decision rules. That actor should retain field-level labels:
`observed`, `inferred`, `assumed`, or `unknown`. An LLM can propose explanations
and bounded rules, but cannot authenticate wallet identity or create measured
probabilities from missing history.

## News and social context

The current UI loads actual GDELT article metadata: title, URL, source domain and
first indexing time. It retains no full article text. Equal normalized headlines
share a group to make obvious syndication visible; this is not semantic fact
checking or a count of independent real-world events. The [GDELT DOC documentation](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/)
describes its search interface. Retrieval encountered rate limiting; the successful
response was retained rather than repeatedly querying it.

The example Trump query demonstrates context access; it is not evidence about
BATCAT, JAMBO or PATATA. Relevance and claims require review. Article tone,
frequency and virality are not automatically converted into event odds.

Social exports can be imported with a declared author, source URL, timestamp and
text. No Trump/Elon social timeline has been fetched. The [official X authentication documentation](https://docs.x.com/fundamentals/authentication/overview.md)
requires appropriate app access even for publicly available API data. An actual
connector needs account access, entity/account resolution, pagination and its own
acceptance test. Imported authorship stays unverified in this version.

## Use the connected UI

**People → Observed wallets → choose NEAR or SOLANA → Load snapshot.** Search an
address, inspect its records/unknown traits and download the computed report.
Template library and Current cast remain available separately.

**Evidence → News & social context → choose the topic → Load snapshot.** Inspect
source links and headline groups. The original chronological forecast evaluator
remains below this panel.

The server only exposes evidence files selected explicitly at startup:

```sh
uv run --project engine decision-lab serve --port 8769 \
  --wallet-observations engine/output/intelligence-2026-10-24/near-observations.json \
  --wallet-observations engine/output/intelligence-2026-10-24/solana-observations.json \
  --topic-observations engine/output/intelligence-2026-10-24/trump-topic-observations.json
```

Those paths refer to this machine's captured data, not bundled fixtures. A fresh
checkout can import its own valid files or use the documented authenticated
collector. The browser UI performs local reads/analysis only; it never reads a
provider key or silently sends a private topic to an external service.
