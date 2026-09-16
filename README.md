# PriceService

PriceService is the Cryptofund20x HTTP service that reads cached cryptocurrency
prices from Redis and exposes single-asset and batch-price endpoints.

## Local verification

Install `requirements.txt` in the project environment, then run:

```bash
pytest -q
```

## Operations

The service exposes `/` for health and `/metrics` for Prometheus. Its Nomad job
is deployed from the homelab jobs checkout using `deploy.sh` with
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
