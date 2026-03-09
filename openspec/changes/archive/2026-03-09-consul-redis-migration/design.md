## Context

`redis_cache_service.py` is a small async module providing a single Redis read operation for RedundantCryptoAssetPriceLambda: `get_cached_price_async()`. It creates Redis connections via `aioredis.from_url()` using a hardcoded constant `REDIS_HOST = 'redis://192.168.1.253:6379'` with `db=0`. The service is read-only — it reads price data written by PricePopulator.

Cryptofund20xShared (already a dependency) provides `db_layer_caller.get_redis_url(db=N)` which discovers Redis via Consul with a 3-tier fallback chain (Consul → `REDIS_URL` env var → hardcoded default). This service should use it instead of its own hardcoded URL.

`get_cached_price_async()` is called per-asset in the `PriceService.get_prices()` batch loop (`price_service.py:33`) and once per request in `get_single_price()` (`price_service.py:52`). Batch requests process multiple assets, meaning `get_redis_client()` is called N times per batch request. Each `get_redis_url()` call makes a synchronous HTTP request to the local Consul agent, so per-call resolution would block the event loop N times per request.

## Goals / Non-Goals

**Goals:**
- Replace hardcoded Redis URL with `db_layer_caller.get_redis_url(db=0)`
- Avoid per-request Consul lookups by caching the resolved URL with a TTL
- Invalidate the cached URL on network-level connection failures
- Add an import-time guard against stale Cryptofund20xShared versions
- Keep the change minimal — no function signature changes
- Add unit tests (none currently exist)

**Non-Goals:**
- Changing the `get_cached_price_async` operation itself
- Switching from aioredis to another Redis client
- Connection pooling
- Changing the Redis database index (stays at db=0)
- Adding write operations

## Decisions

### 1. Lazy module-level URL cache with 5-minute TTL (Option B+)

**Decision**: Cache the result of `get_redis_url(db=0)` at module level with lazy resolution and a 5-minute TTL. On first call to `get_redis_client()`, resolve the URL and cache it with a timestamp. Subsequent calls reuse the cached URL until the TTL expires, then re-resolve. At most one Consul call per TTL window, plus re-resolution on connection failure.

**Alternatives considered**:
- Per-call resolution (no cache) → rejected because `get_cached_price_async()` is called per-asset in batch loops. Per-call resolution would block the event loop N times per request with synchronous Consul HTTP queries.
- Module-level constant at import time → rejected because Consul unavailability at import would lock the process onto a fallback URL for its entire lifetime.

**TTL rationale**: Unlike PricePopulator (4-minute cron in `populator_app.py:90`), this service has no scheduled jobs — `price_app.py` starts an `AsyncIOScheduler` but registers no jobs. The service is purely request-driven, so there is no natural cadence to match. A 5-minute TTL is a reasonable default that limits Consul calls to at most ~12/hour while allowing timely re-resolution if Redis relocates.

### 2. Invalidate cache on network-level connection failure

**Decision**: If a Redis operation raises a network-level exception, clear the cached URL so the next call to `get_redis_client()` re-resolves via Consul. Only the following exception classes trigger invalidation:
- `redis.exceptions.ConnectionError` (aliased as `RedisConnectionError` to distinguish from Python builtin)
- `redis.exceptions.TimeoutError` (aliased as `RedisTimeoutError` — note: this is a `RedisError` subclass but represents a network issue, explicitly carved out)
- `OSError` (covers socket-level failures)

Logical Redis errors (`ResponseError`, `DataError`, and other `RedisError` subclasses that are not `ConnectionError` or `TimeoutError`) do **not** invalidate the cache — these indicate the server is reachable but the command failed, not that the URL is stale.

**Rationale**: If Redis moves (e.g. Nomad reschedules the container) and the cached URL becomes stale, the connection failure triggers a fresh Consul lookup on the next attempt. Scoping to network-level exceptions prevents cache thrashing on data/logic errors.

### 3. Remove the REDIS_HOST constant entirely

**Decision**: Delete the `REDIS_HOST` constant. The cached URL lives in a module-level variable managed by the caching logic.

**Rationale**: No leftover dead code. The URL source is now `db_layer_caller`.

### 4. Import-time version guard via `inspect`

**Decision**: After importing `get_redis_url`, inspect its signature to verify the `db` parameter exists. Raise `ImportError` with a clear message if absent.

**Rationale**: `inspect.signature()` is a zero-dependency way to verify the API contract at import time. Fails fast with a descriptive error before any request is served.

## Risks / Trade-offs

**[TTL choice is not tied to a natural cadence]** → Unlike PricePopulator, there is no scheduler interval to match. The 5-minute TTL is a reasonable heuristic. If Redis relocates, worst case is one failed request before re-resolution (plus immediate re-resolution via cache invalidation on connection failure).

**[Stale cached install of Cryptofund20xShared]** → The import-time guard catches this with a clear error at startup rather than a confusing `TypeError` later.

**[No existing tests]** → Test infrastructure was removed in commit `57982eb`. New `pytest.ini`, `conftest.py`, and test file must be created from scratch.

## Open Questions

None.
