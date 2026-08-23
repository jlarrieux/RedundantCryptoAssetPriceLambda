# PriceService batch-failure investigation evidence

Investigation: `chg_priceservice_003`  
Observed: 2026-08-23, approximately 13:34–13:45 UTC  
Scope: read-only Prometheus, Elasticsearch, MongoDB, Redis, and source inspection

## Conclusion

The persistent 8.33% signal is not a Redis pipeline failure and is not a
`type="batch"` failure in the live service. The live Prometheus series is
`price_service_complete_batch_failures_total{type="single"}` on all 25 current
PriceService allocations; there is no `type="batch"` series in the last seven
days. The signal is produced by single-price cache misses after callers fall
back from a missing `/prices` result to `/price/<asset>`.

Confidence is **high (at least 99%)** that no batch Redis-error path is causing
the observed counter. Confidence is **high (at least 95%)** that the observed
counter is the mislabeled single-cache-miss path. Confidence is **high (at
least 90%)** that the recurring missing keys are a caller/asset-universe and
provider-admission problem, not a read/write race.

This investigation does not decide the PriceService instance count. It does
remove this signal as evidence of capacity pressure or Redis instability. The
right-sizing task should use correctly scoped request/error signals while the
asset-universe/provider issue is handled separately.

## Prometheus evidence

Queries were run against live Prometheus at `http://192.168.1.252:9090`, not
Thanos.

The following query returned an empty result:

```promql
last_over_time(price_service_complete_batch_failures_total{type="batch"}[7d])
```

The current metric inventory had 25 `type="single"` series and zero
`type="batch"` series. A direct live allocation scrape also exposed:

```text
# HELP price_service_complete_batch_failures_total Number of times all APIs failed for a batch
# TYPE price_service_complete_batch_failures_total counter
price_service_complete_batch_failures_total{type="single"} 1028.0
```

The ratio that looks like the reported 8.33% is reproducible only when the
counter is divided by the combined request-duration count, not by the
`/prices` endpoint count:

| Window | `increase(failure counter)` / `increase(request duration count)` |
| --- | ---: |
| 1h | 8.333333% |
| 6h | 8.333333% |
| 24h | 8.332289% |
| 7d | 8.332258% |

For the same query time, the 7-day increases were approximately:

```text
failure counter:             652.20
all request observations:  7,827.38
/prices requests:          4,729.43
/price/<asset> requests:  3,097.94
```

Thus the counter is approximately 13.79% of `/prices` requests and 21.05% of
single-price requests, while it is 8.33% of the combined request histogram.
The metric name/help text and the observed label are therefore misleading for
this diagnosis.

The source confirms the semantic mismatch. `price_service.py` increments the
same counter with `type="batch"` only when `get_cached_prices_batch()` returns
`errored_assets` (lines 39–41), but increments it with `type="single"` whenever
`get_cached_price_async()` returns no data (lines 54–60).

## Elasticsearch path evidence

Logs were queried in `filebeat-nomad-*` at
`http://192.168.1.252:9200`, filtered to `nomad.task.name="price-service"`
and the rolling seven-day window.

The five requested batch-error signatures all returned zero documents,
including the counter-incrementing line:

| Signature | Documents |
| --- | ---: |
| `Redis error for ...` | 0 |
| `Invalid timestamp for ...` | 0 |
| `Pipeline-level Redis failure ...` | 0 |
| `Unexpected error in batch price lookup ...` | 0 |
| `Redis errors for assets in batch mode: ...` | 0 |

The batch reader did emit ordinary cache-miss warnings. The observed
`No cached data found ...` counts were:

| Asset | Batch-reader miss log events |
| --- | ---: |
| `dpx` | 8,587 |
| `cnc` | 4,554 |
| `lyra` | 4,034 |
| `jpeg` | 4,033 |
| `xgrail` | 3,547 |
| `rdpx` | 3,023 |
| `btrfly` | 2,537 |
| `stake_dao` | 2,016 |
| `ndx` | 27 |

The corresponding single-reader miss events were concentrated on the same
unavailable assets:

| Asset | Single-reader miss log events |
| --- | ---: |
| `dpx` | 6,570 |
| `rdpx` | 3,023 |
| `btrfly` | 2,537 |
| `cnc` | 2,537 |
| `jpeg` | 2,016 |
| `ndx` | 27 |

Representative batch log events occurred at exactly five-minute boundaries:

```text
2026-08-23T13:30:00Z  Failed assets: ['dpx']
2026-08-23T13:35:00Z  Failed assets: ['lyra', 'jpeg', 'cnc']
2026-08-23T13:40:00Z  Failed assets: ['dpx', 'xgrail']
```

There were 288 populated five-minute buckets in the preceding 24 hours, each
with seven PriceService failure-log events. These are missing assets, not
pipeline failures; the batch function classifies an empty HGETALL result as
`missed_assets` and does not increment the batch counter.

## PricePopulator and storage evidence

PricePopulator's source schedules a refresh every four minutes and writes a
complete hash through one Redis `HSET` mapping. The live logs confirm 360
successful refresh completions in the preceding 24 hours and 2,507 in the
rolling seven-day query. Recent completions were:

```text
2026-08-23T13:32:20Z
2026-08-23T13:36:20Z
2026-08-23T13:40:21Z
```

The live Redis read was read-only. `price:dpx`, `price:btrfly`, `price:cnc`,
`price:xgrail`, `price:lyra`, `price:jpeg`, `price:rdpx`, `price:stake_dao`,
and `price:ndx` all returned Redis type `none`; `price:weth` returned a
four-field hash with a current timestamp. This is persistent absence, not a
malformed timestamp or a transient partial hash.

The active-asset MongoDB read showed:

```text
btrfly    active=false
cnc       active=false
dpx       active=false
jpeg      active=true
lyra      active=true
rdpx      active=true
weth      active=true
xgrail    no row
stake_dao no row
ndx       no row
```

PricePopulator logs identify why the three active missing symbols are never
written. Over the rolling seven-day query, the worker logged:

```text
No matching coin found for lyra-finance       2,508
No matching coin found for jpeg-d             2,508
No matching coin found for dopex-rebate-token 2,508
```

There were zero `Stored price data` events for `lyra`, `jpeg`, or `rdpx` in
that window. The worker's list-first CoinGecko admission returns `None` when
the transformed identity is absent, before the `store_price()` call. The
PricePopulator status also records that `btrfly`, `cnc`, and `dpx` were
deliberately retired/deactivated while `rdpx` remained active but lacked a
matching provider identity.

The cadence comparison does show occasional ordering overlap, but it does not
support the race as the cause. At one recent cycle:

```text
PriceService missing-asset logs:       13:40:00
PricePopulator no-match logs:           13:40:05–13:40:10
PricePopulator refresh completion:      13:40:21
```

The same no-match pattern repeats every four minutes while the reader observes
missing symbols every five minutes. Because the provider rejects these assets,
there is no HSET for a reader to race with. A Redis HSET mapping is also one
atomic command, so a mid-write reader would not explain a key that remains
absent across thousands of refresh cycles.

## Root-cause chain

1. Downstream callers request a mixed/stale asset universe containing retired,
   absent, or provider-unadmitted symbols.
2. `get_cached_prices_batch()` reads those keys and correctly classifies empty
   hashes as cache misses. It emits `No cached data found ...` and returns the
   assets in `missed_assets`; it does not emit a Redis error or increment the
   batch counter.
3. The shared `PriceInterface` path first requests a one-asset `/prices` batch
   when extra price data is needed. If that result is absent, it falls back to
   `/price/<asset>`.
4. The single reader sees the same absent key, returns `None`, and increments
   `price_service_complete_batch_failures_total{type="single"}`.

This explains the observed counter without any Redis connection failure,
pipeline timeout, per-command Redis error, invalid timestamp, or write/read
race.

## Recommendation

1. Correct dashboards and alerts to select `type="batch"` explicitly. Treat
   the absence of that series as zero batch Redis-error events; do not use the
   current 8.33% combined-request ratio as instance-count evidence.
2. Handle the asset-universe problem separately: stop sending retired
   `btrfly`, `cnc`, and `dpx`, and either resolve valid provider identities for
   active `lyra`, `jpeg`, and `rdpx` or make their caller behavior explicit.
   `xgrail`, `stake_dao`, and `ndx` also need caller/source reconciliation.
3. In a separately scoped instrumentation change, split the misleading
   counter into bounded outcome categories such as batch cache miss, single
   cache miss, per-command Redis error, and pipeline Redis failure. Avoid an
   unbounded asset label; retain asset detail in logs or bounded diagnostic
   aggregation.
4. Re-evaluate the instance-count question using request latency, concurrency,
   and correctly scoped Redis-error metrics after the telemetry and asset
   universe are corrected. No deployment, code change, Redis mutation,
   Nomad/Consul mutation, or instance-count decision was made here.

