## Why

PriceService has two Redis performance issues that compound during Saver batch cycles. First, when a token is not in the Redis cache, the price lookup takes ~8 seconds per asset before returning 0. The PriceService layer (`redis_cache_service.py`) already returns `None` immediately on empty HGETALL, and `/price/<asset>` returns a fast 404. The expensive behavior is upstream: `price_client.py` in Cryptofund20xShared calls `url_util.open_url_async()` with `max_retries=5` and `initial_delay=2`, which retries the 404 through the full retry/backoff cycle. This is the layer that must change. Second, `PriceService.get_prices()` iterates assets sequentially, awaiting one `HGETALL` per asset. With 11+ tokens per batch request, this serializes Redis round-trips unnecessarily. A spike on 2026-03-22 confirmed that concurrent lookups beat sequential by ~45% (128ms vs 232ms p50).

## What Changes

- **Fail fast on cache miss (shared library)**: The fix is scoped to `Cryptofund20xShared/cryptofund20x_services/price_client.py`. When PriceService returns 404 for a missing asset, `price_client.py` must not retry — it should immediately return `None` / 0 instead of letting `url_util.open_url_async()` exhaust its retry budget. This requires a Cryptofund20xShared commit+push, `pip install` in affected repos, Docker image rebuilds, and redeployment of all services using `price_client.py` (Ferengi, Saver). The PriceService itself does not need code changes for this fix.
- **Parallelize batch Redis lookups**: Replace the sequential `for asset in assets` loop in `PriceService.get_prices()` with `asyncio.gather()` to execute all `HGETALL` calls concurrently. The current `get_redis_client()` creates a new `aioredis.from_url()` on every call (module-level URL caching, but client instantiation per call). Under `asyncio.gather`, this would create N concurrent Redis clients. The optimization must either: (a) reuse a single Redis client instance across the gather, or (b) use a Redis pipeline (single round-trip for all HGETALL commands). Design will evaluate which approach is better.
- **Batch miss contract**: The `/prices` endpoint currently returns `jsonify({"prices": result})` where `result` is a tuple of `(success_dict, failed_list)`. The shared client does `loaded['prices'][0]` to extract the success dict. The existing wire format is preserved (backward compatibility). Internally, cache misses vs Redis errors are distinguished for operational visibility (different log levels, metrics) but the API response collapses both into the existing `failed_assets` list. This is sufficient because the sole caller (Ferengi via `price_client.py`) treats both cases identically — logs and continues.

## Capabilities

### New Capabilities

- `redis-batch-optimization`: Concurrent Redis lookups for batch price requests, with explicit Redis client/connection reuse strategy to avoid connection churn across 25 PriceService instances.
- `cache-miss-fast-path`: Immediate fail-fast in the shared library's `price_client.py` when PriceService returns 404 for a cache miss. Includes the shared-library update/deploy sequence (Cryptofund20xShared push → pip install → Docker rebuild → Nomad deploy for affected services).

### Modified Capabilities

_None — no existing specs to modify._

## Impact

- **Code**: `cryptofund20x_services/price_client.py` in Cryptofund20xShared (retry bypass on 404), `price_service.py` (batch loop parallelization), `pricing/redis_cache_service.py` (Redis client reuse for gather).
- **APIs**: No endpoint signature changes. `/prices` and `/price/<asset>` return the same fields. The batch response contract (success dict + failed assets + HTTP status for partial misses) will be explicitly specified in the spec.
- **Dependencies**: No new dependencies. Uses existing `asyncio.gather` and `aioredis`.
- **Systems**: PriceService (25 Nomad instances on compute nodes). Cryptofund20xShared update affects all downstream services on next rebuild — Ferengi and Saver are the primary consumers of `price_client.py`. Deploy sequence: Cryptofund20xShared push → pip install in each repo → Docker rebuild → Nomad deploy.
- **Risk**: Low-medium. The batch parallelization is contained to PriceService. The shared library change (404 fast-path) touches retry logic used by multiple callers — needs careful scoping so only price-service 404s are fast-pathed, not all 404s from any service. Existing Ferengi error handling for missing prices must be verified against the new behavior.
