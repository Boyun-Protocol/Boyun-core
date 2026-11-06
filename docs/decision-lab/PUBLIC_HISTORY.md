# Public-only history collection

The selected route is **public sources only, accumulating observations forward**.
No CoinGecko subscription/key is needed or read. The older authenticated connector
remains in the codebase as an unused explicit opt-in path; it is not a fallback.

## What is running

The local numeric collector reads the four pools in
`engine/examples/public-pools.json`: three NEAR pools and a separate Solana pool.
It makes bounded public GeckoTerminal GET requests, with five seconds between
pools, then waits at least 60 seconds before the next collection cycle. These
are recent slices, not historical backfill requests. No model infers trades or
fills missing history.

On HTTP429 it stops the pass and waits at least five minutes before another
cycle, incorporating a bounded Retry-After delay when supplied. The actual first
watch cycle encountered a rate limit, retained the failure and entered cooldown.
No immediate request retry occurs. An advisory process lock prevents two watchers
for the same archive. The watch command currently requires a POSIX platform,
including this Mac; other CLI and analysis commands remain available separately.

A thread heartbeat checks collector health every six hours and can restart an
absent watcher. It stays quiet while unchanged/healthy. This app-level health
check is separate from the lightweight numeric polling process. Collection needs
the Mac awake and the process running; a health check is not an always-on server
or a guarantee of collection during sleep or app shutdown.

## Archive and evidence

`engine/output/public-history/history.sqlite` is the local SQLite archive. New
files are mode 0600, created under a private directory. Each successful capture
records its source, retrieval time, raw/new/duplicate counts and observed range.
Failures keep sanitized codes instead of raw errors. Event insertion and capture
metadata commit atomically. The archive has no automatic deletion or retention
pruning, so storage grows over time.

Events deduplicate by network + pool + provider event ID. Different swaps in one
transaction remain distinct. Conflicting versions of an event reject that
capture rather than silently rewriting history. Immutable pool metadata prevents
an address from being reassigned to another token pair. Read-only UI requests
use a consistent SQLite snapshot while the collector may be writing.

The original public observations were seeded into the archive. The first fresh
collection on **24 October 2026, approximately 09:02 Vietnam time**, succeeded for
all four pools, taking the archive to **1,063 unique swaps**. It detected a
possible discontinuity in the Solana pool. Later counts can change as new
captures arrive; inspect current status instead of treating this number as fixed.

Possible gap detection is deliberately incomplete. A full recent slice of 300
events with no overlap beyond the previous latest event flags a possible gap.
Overlapping slices do not prove continuity, and elapsed time does not establish
30-day completeness. Pool-specific last successes, failures, polling intervals
and first/last observed events remain visible. High-activity pools can lose
events between polls; provider lag or corrections can introduce other gaps.

## Commands

```sh
# Start one numeric watcher; Ctrl-C stops it without removing history.
uv run --project engine decision-lab public-data watch \
  --pools engine/examples/public-pools.json \
  --archive engine/output/public-history/history.sqlite \
  --allow-network --interval 60

# Inspect locally; no network request.
uv run --project engine decision-lab public-data status \
  --archive engine/output/public-history/history.sqlite

# Export up to 1,000 newest retained observations within the 30-day target window.
# Existing output files are never overwritten.
uv run --project engine decision-lab public-data export \
  --archive engine/output/public-history/history.sqlite \
  --network near --output engine/output/public-history/near-export.json

# Show archive-backed profiles and status in the local UI.
uv run --project engine decision-lab serve --port 8769 \
  --public-archive engine/output/public-history/history.sqlite
```

`public-data collect` makes one pass with the same pools/archive arguments.
`public-data ingest --input ... --archive ...` adds an already retained valid
public snapshot without making requests. Configurations are explicitly bounded
to four pools per network/eight total; no token discovery or paid fallback occurs.

## UI

Refresh the workbench. In **People → Observed wallets**, the public-history panel
shows capture counts, failures and gaps. **Refresh collection status** reads only
the local database. Select **NEAR · accumulating public archive** or the separate
Solana source and load it to recompute profiles from current retained data.

The profile view/export is capped at 1,000 recent records and additional byte/node
budgets; it is not the full growing archive. Earlier saved snapshots remain
separate choices. Nothing here automatically changes simulation capital, rules,
wallet identity or event odds.

## Verification

792 Python tests and eight JavaScript checks pass. Tests cover atomic overlap
deduplication, conflicting-event rollback, fractional chronology, read-only
access, concurrent-reader consistency, bounded exports, origin checks, opt-in,
request caps, failed captures, rate-limit stop/cooldown and duplicate watcher
locks. The real public endpoint pass and browser archive-backed profile/status
flow succeeded; desktop/phone layouts were inspected. An isolated installed
wheel served the actual read-only archive and computed a normal core world.
