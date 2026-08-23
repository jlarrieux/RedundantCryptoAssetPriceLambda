# Talit investigation: root-cause the persistent ~8.3% "complete batch failure" rate

## Context

`price_service_complete_batch_failures_total` (labelled `batch`) has been incrementing at a
**persistent, steady-state ~8.33% rate** of `get_prices()` calls for at least the last 7 days
(1h/6h/24h/7d windows all ≈8.33% — confirmed against live Prometheus directly, not just Thanos;
see the Thanos-vs-Prometheus discrepancy note below). This is Akasha task
`6a87ac17278e761a4e26d0c1` in the "Nomad fleet resource right-sizing" increment
(`69e3c0d13e6e93c5be05816a`), surfaced during an unrelated Nomad resource audit. It currently
`blocks` a separate task (`6a880ed2278e761a4e26d0db`, revisiting price-service's instance count) —
**this investigation is the prerequisite for that decision, not the decision itself.**

Already ruled out: resource starvation. Latency stays fast throughout (live Prometheus: p50 3.7ms,
p95 11.8ms, p99 22.4ms) and concurrency is very low (Little's Law estimate <1 concurrent request at
peak). This is not a capacity problem.

**Correction to the existing Akasha task's own working hypothesis — verify this yourself, don't
inherit it**: the task description guesses "all upstream APIs failed together" (implying multiple
external price-data sources). Reading `price_service.py` directly shows this is wrong. The counter
is driven entirely by `pricing/redis_cache_service.py::get_cached_prices_batch()` — a **Redis
pipeline read**, not any external API call:

```python
# price_service.py
if errored_assets:
    self.logger.error(f"Redis errors for assets in batch mode: {errored_assets}")
    PRICE_SERVICE_FAILURE.labels('batch').inc()
```

`get_cached_prices_batch()` can populate `errored_assets` two structurally different ways, and the
metric does not distinguish which one fired:

1. **Per-asset**: a pipelined `hgetall` result is itself an error/exception object, or the cached
   entry's `timestamp` field fails `datetime.fromisoformat` (`TypeError`/`ValueError`) — one bad
   asset among many requested still increments the whole-batch counter once.
2. **Pipeline-level**: `RedisConnectionError`, `RedisTimeoutError`, `OSError`, or any other
   exception during the pipeline itself — in which case `errored_assets = list(assets)` (every
   requested asset in that call is marked errored).

These have very different implications (a single flaky asset's stale cache entry vs. a real Redis
connection/timeout problem recurring on a schedule) and the current metric conflates them.

**A testable hypothesis worth checking, not to be assumed as the answer**: `PricePopulator`
(`~/programming/python/cryptofund20x/PricePopulator/pricing/redis_cache_saver_service.py`) writes
to the same `price:` key prefix (`PRICE_KEY_PREFIX = "price:"`, confirmed shared with
`redis_cache_service.py`) on its own refresh cycle. If `PriceService` reads happen to catch specific
keys mid-write during that refresh window, that could produce a periodic, roughly-consistent failure
ratio depending on relative call cadence. This may or may not be the actual cause — verify against
real evidence (logs, timing correlation) rather than accepting it.

## Known confound: Thanos is unreliable for this exact metric

The prior investigation (`chg_nomad_jobs_006`) found Thanos and live Prometheus report materially
different totals for `price_service_complete_batch_failures_total` over 7 days (Prometheus
~652/644, Thanos ~28190 — roughly 44x higher), suspected `replica`-label double-counting in Thanos.
**Use live Prometheus (`http://192.168.1.252:9090`) for exact counts and ratios. Thanos is fine only
for "is this nonzero / does this pattern exist" checks, never for exact totals**, per the
`nomad-resource-audit` skill's documented caveat.

## What to do

1. **Determine which failure path is actually firing**, using real log evidence (Elasticsearch —
   `mcp__homelab-mcp__es_search_logs` or equivalent), not just re-reading the code. Search for the
   specific log lines each path produces:
   - `"Redis error for {asset}: {result}"` (per-asset pipeline result error)
   - `"Invalid timestamp for {asset}"` (per-asset bad timestamp)
   - `"Pipeline-level Redis failure"` (connection/timeout, all assets)
   - `"Unexpected error in batch price lookup"` (any other pipeline exception, all assets)
   - `"Redis errors for assets in batch mode: {errored_assets}"` (the actual counter-incrementing
     line — check how many assets are typically listed per occurrence; a consistently short list
     points to path 1, a consistently full/large list points to path 2)
2. **If it's a specific asset (or small set of assets) recurring**, identify which one(s) and why
   their cached entry is invalid or errors — a stale/malformed write, a missing key, a
   PricePopulator-side bug affecting only certain assets.
3. **If it's a genuine Redis connection/timeout issue**, check whether it correlates with anything
   periodic — a specific time-of-cycle, a specific Redis load pattern, node-level Redis metrics
   during those windows.
4. **Test the write/read race hypothesis** if the evidence points toward per-asset staleness/missing
   keys: compare `PriceService`'s call cadence against `PricePopulator`'s refresh cycle timing
   (read-only inspection of `PricePopulator` is fine under standing read access; do not modify
   anything there).
5. **State a specific, evidence-backed root cause**, or say explicitly that the evidence is
   insufficient to determine one and what additional instrumentation would be needed.

## Deliverable

ONE artifact, posted with your first handoff: the log evidence you found (with counts/examples, not
just a restatement of this directive's hypotheses), which failure path is actually responsible (with
a confidence level), the specific mechanism if identified, and a recommendation for the fix (or for
what to instrument next if the evidence is inconclusive). This directly determines whether the
blocked instance-count task can proceed and what, if anything, needs fixing before it does.

## Hard bars — read-only investigation only

1. **NO code changes, NO Redis mutation, NO Nomad/Consul mutation, NO deployment of any kind.**
2. Read-only inspection of `PricePopulator` (a different repo) is permitted under standing read
   access; no edits, commits, or mutation there.
3. Writes are limited to this repo (documentation/artifact only) and your Hermes artifact.
