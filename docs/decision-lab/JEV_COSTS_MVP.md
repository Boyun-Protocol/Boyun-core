# Direct TypeSafe Jev cost estimates

Checked 28 October 2026. The [official model reference](https://docs.typesafe.ai/models)
lists Jev input at **$0.042 per million input tokens** and **$0 for output tokens**.
The active default model is `jev-latest`. This is published list-price arithmetic,
not an account-specific quote, invoice, purchase minimum or billing guarantee.

```text
input estimate USD = input tokens × 0.042 / 1,000,000
actor-call ceiling = actors × rounds × sampled worlds
```

| Illustrative usage | Input tokens | Input estimate USD |
| --- | ---: | ---: |
| One actor request | 2,000 | 0.000084 |
| 20 requests at 2,000 tokens each | 40,000 | 0.00168 |
| 200 requests at 2,000 tokens each | 400,000 | 0.0168 |
| 800 requests at 2,000 tokens each | 1,600,000 | 0.0672 |
| Token volume with $5 of input list-price usage | about 119.05 million | 5 |
| Token volume with $10 of input list-price usage | about 238.10 million | 10 |

The 2,000-token request is an explicit hypothetical input, not a measured native
average. Longer histories and larger observations change token usage. These
figures exclude authoring, other providers, hosting, storage, tax and payment fees.
They do not establish that $5/$10 purchases are available or how many complete
experiments a funded account can run.

The review's `typesafe_estimate` uses the maximum future canonical request bytes
as a conservative one-token-per-byte planning estimate. Provider framing and
tokenization may differ. Its input cost estimate is not an enforced dollar cap;
`max_calls` is the dispatch control. The invite preview separately reserves one
call per validated operator-funded dispatch and defaults to 200 calls per reviewer.
Failed or unknown requests retain reservations until operator reconciliation.

Earlier retired-provider pilot records are not direct TypeSafe acceptance;
native live acceptance pending. Historical call counts, durations and billing
units are not measurements of the direct native tariff. Saved artifacts remain
unchanged; this migration made no live inference request and no historical rerun.

See [native setup and exact limits](JEV_INTEGRATION.md),
scale bounds and pricing status.
