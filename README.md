# PriceService

PriceService is the Cryptofund20x HTTP service that reads cached cryptocurrency
prices from Redis and exposes single-asset and batch-price endpoints.

## Price responses

`GET /price/<asset>` returns `asset`, `usd_price`, `volume_last_24_hours`, and
`current_marketcap_usd`. `GET /prices?assets=...` keeps the
`{"prices": [success_dict, failed_list]}` envelope and returns successful
Redis hashes with their existing fields, including `timestamp`. Both endpoints
include `observed_at` unchanged when the hash contains it and omit the key when
it is absent. The producer's value is an aware UTC ISO-8601 timestamp with an
explicit `+00:00` offset; it records when the producer prepared the cache
write, not when CoinGecko sampled the data. Freshness decisions belong to the
consumer.

## Local verification

Install `requirements.txt` in the project environment, then run:

```bash
pytest -q
```

## Operations

The service exposes `GET /` for health, `GET /price/<asset>` for one cached
price, `GET /prices?assets=...` for batch prices, and `GET /metrics` for
Prometheus. `GET /transform-asset` was removed because its copied mapping had
drifted and no caller was found in the audited scope. Its Nomad job is deployed
from the homelab jobs checkout using `deploy.sh` with
`cryptofund20x/price-service.hcl`.

`PriceService()` is constructed by request handlers. Its named `PriceService`
logger is therefore configured defensively: construction keeps one local stream
handler and disables propagation, preventing repeated requests from multiplying
each log event.

High-frequency successful-request narration is logged at DEBUG. Warnings and
errors remain at their existing levels, while Prometheus request metrics retain
production-facing observability without creating one INFO event per cache hit.

## Known-unresolvable assets

`price_service.py`'s `KNOWN_UNRESOLVABLE_ASSETS` frozenset (`btrfly`, `cnc`,
`dpx`, `jpeg`, `rdpx`) names symbols confirmed permanently absent from
CoinGecko's coin list. A single-price cache miss for one of these logs a
warning and returns `None` exactly as any other miss does, but does not
 increment `price_service_single_cache_miss_total` — these
assets will never populate the cache, so counting their misses as failures
only produced a persistent, misleading alert signal. Any other symbol's miss
still increments that counter normally. Batch Redis errors are tracked
separately by `price_service_batch_redis_errors_total`; this is a fixed
allowlist, not a general miss-suppression path.

Current project state and deployment evidence are maintained in [status.md](status.md).
