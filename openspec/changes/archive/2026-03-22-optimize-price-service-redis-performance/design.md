## Context

PriceService is a read-only price query service (25 Nomad instances) that reads from Redis db=0 (populated by PricePopulator every 4 minutes). It serves two endpoints: `/price/<asset>` (single) and `/prices?assets=a,b,c` (batch). Upstream callers are primarily Ferengi instances (via `price_client.py` in Cryptofund20xShared) during Saver's 5-minute orchestration cycle.

**Current state:**
- `redis_cache_service.get_cached_price_async()` creates a new `aioredis.from_url()` client per call (URL is cached 5 min, but the client object is not). Each call does one `HGETALL price:<asset>`.
- `PriceService.get_prices()` loops sequentially: `for asset in assets: await get_cached_price_async(asset)`.
- On cache miss, PriceService returns 404 (single) or includes the asset in `failed_assets` (batch). But `price_client.py` calls `url_util.open_url_async()` with `max_retries=5, initial_delay=2`, which retries the 404 five times with 2s delays = ~8s wasted per miss.
- The `/prices` endpoint returns `jsonify({"prices": result})` where `result` is a tuple `(success_dict, failed_list)`. The client does `loaded['prices'][0]`.

## Goals / Non-Goals

**Goals:**
- Eliminate the ~8s retry cycle on price cache misses by making `price_client.py` treat 404 as a terminal (non-retryable) response
- Parallelize batch Redis lookups to reduce `/prices` latency by ~45%
- Reduce Redis connection overhead within batch requests
- Define explicit batch failure semantics distinguishing cache misses from infrastructure errors

**Non-Goals:**
- Changing the PricePopulator write path or Redis data model
- Adding new price sources or fallback APIs
- Modifying how Ferengi handles missing prices (Ferengi's error handling is out of scope; it already logs and continues on missing prices)
- Connection pooling across requests (lifecycle management adds complexity; per-request optimization is sufficient)
- Changing the `/prices` response wire format (backward compatibility is required)

## Decisions

### 1. Cache-miss fast-path: `non_retryable_statuses` parameter in `url_util.open_url_async`

**Decision:** Add an optional `non_retryable_statuses` parameter (default: empty set) to `url_util.open_url_async`. Inside the retry loop, when `response.raise_for_status()` raises `aiohttp.ClientResponseError`, check if `e.status` is in `non_retryable_statuses`. If so, re-raise immediately instead of retrying. `price_client.py` passes `non_retryable_statuses={404}`.

**Why in `url_util` and not `price_client`:** The retry logic lives inside `url_util.open_url_async` — it catches all exceptions and retries them. By the time control returns to `price_client.py`, retries have already been exhausted. The status check must happen inside the retry loop. The parameter is opt-in and general-purpose (not 404-specific), so it doesn't leak domain semantics into the utility.

**Alternative considered:** Add a separate `open_url_async_no_retry` function. Rejected because it duplicates the entire function body — the `non_retryable_statuses` check is a single `if` statement inside the existing exception handler.

### 2. Batch Redis lookups: Redis pipeline

**Decision:** Use a Redis pipeline to batch all `HGETALL` commands into a single round-trip.

**Why pipeline over `asyncio.gather`:** The `aioredis.from_url()` client creates a connection pool (default `max_connections=None`, meaning unbounded). Using `asyncio.gather` with N concurrent `HGETALL` calls would fan out across multiple pool connections — not "N commands over one connection" as originally assumed. A pipeline guarantees a single round-trip regardless of N, and avoids creating pool-managed connections per concurrent task.

**Implementation:**
- Add a new function `get_cached_prices_batch(assets: List[str])` in `redis_cache_service.py` that:
  1. Creates one Redis client
  2. Opens a pipeline: `async with client.pipeline(transaction=False) as pipe:`
  3. Enqueues `pipe.hgetall(f"price:{asset}")` for each asset
  4. Executes: `results = await pipe.execute()`
  5. Applies per-asset validation (timestamp staleness checks) to each result
  6. Returns `(success_dict, missed_assets, errored_assets)`
- `PriceService.get_prices()` calls this new batch function instead of looping.
- The existing `get_cached_price_async()` remains unchanged for single-asset callers.

**Trade-off:** The pipeline function duplicates some validation logic from `get_cached_price_async`. This is acceptable — the batch function is a distinct code path optimized for multi-asset requests, and the validation is simple (timestamp check + logging).

### 3. Batch response contract: backward-compatible, with explicit failure semantics

**Decision:** Keep the existing wire format: `{"prices": [success_dict, failed_list]}`. The tuple-serialized-as-array is the current contract and `price_client.py` reads `loaded['prices'][0]`. No format change.

**Why no format change:** PriceService, Ferengi, and Saver are separate Nomad jobs deployed independently. There is no atomic deploy across all three. A format change would require either a staged rollout with version negotiation or a deployment coordination window — both add complexity for minimal gain. The current format works; the optimization is internal.

**Scope narrowing from Proposal:** The approved Proposal called for callers to distinguish "asset not cached" from "Redis/system error." During design analysis, this requirement is narrowed to **operational visibility only** (logging + metrics), not caller-visible API fields. Rationale: the sole consumer of `/prices` is `price_client.py` in Ferengi, which treats both cases identically — logs and continues with the assets it received. Adding a caller-visible distinction would require either a breaking wire format change (rejected above) or a new backward-compatible field that no current caller would read. The operational benefit (distinct log levels, metrics) is sufficient for diagnosis. If a future caller needs the distinction, it can be added as a separate change.

**Failure semantics:** Internally, `get_cached_prices_batch` returns three categories:
- `success_dict`: assets with valid cached data
- `missed_assets`: assets where HGETALL returned empty (cache miss — asset not in Redis)
- `errored_assets`: assets where the Redis call raised an exception (connection error, timeout)

The `/prices` endpoint collapses `missed_assets` and `errored_assets` into the existing `failed_assets` list for the response (preserving backward compatibility). Logging distinguishes the two: cache misses log at WARNING level, Redis errors log at ERROR level and trigger the `price_service_complete_batch_failures_total` counter. This gives operational visibility without breaking the API contract.

**HTTP status:** 200 for full success and partial success. Callers use `failed_assets` to determine partial failures.

## Risks / Trade-offs

**[Risk] Shared library change affects all downstream services** → Mitigation: The `non_retryable_statuses` parameter defaults to empty set, so all existing callers are unaffected. Only `price_client.py` passes `{404}`. No behavior change for any other service until they opt in.

**[Risk] Pipeline failure semantics** → There are two failure modes: (1) Per-command `ResponseError` objects in the result list (e.g., wrong key type) — these are checked individually per asset and classified as `errored_assets`. (2) Pipeline-level connection/timeout failure — `execute()` raises `RedisConnectionError` or `RedisTimeoutError`, meaning no results are available. In this case, the batch function catches the exception at the `execute()` boundary, invalidates the URL cache, and returns all requested assets as `errored_assets` with an empty `success_dict`. The caller (PriceService) falls through to the existing error handling path. There is no per-asset network isolation within a pipeline — a connection failure affects the entire batch.

**[Risk] New batch function in `redis_cache_service` may diverge from single-asset function** → Mitigation: Both share the same constants (`PRICE_KEY_PREFIX`) and URL caching logic. The validation logic (timestamp staleness) is simple enough that duplication is preferable to a shared abstraction that forces both code paths through the same interface.

**[Trade-off] Pipeline vs gather** → Pipeline trades the ability to interleave per-asset business logic (logging, staleness checks between commands) for guaranteed single round-trip. Since the business logic runs after all results are returned anyway, this is the right trade-off.

## Migration Plan

1. **Cryptofund20xShared**: Add `non_retryable_statuses` to `url_util.open_url_async`. Update `price_client.py` to pass `non_retryable_statuses={404}`. Commit and push.
2. **PriceService**: Add `get_cached_prices_batch()` to `redis_cache_service.py`. Update `PriceService.get_prices()` to use it. Pip install updated shared lib. Build Docker image, push to ECR, deploy via Nomad.
3. **Ferengi + Saver**: Pip install updated Cryptofund20xShared (for the 404 fast-path in price_client). Rebuild and deploy.
4. **Rollback**: Revert the Cryptofund20xShared commit, pip install the previous version, rebuild and redeploy. The `non_retryable_statuses` default (empty set) means reverting the shared lib restores original retry behavior. PriceService's pipeline change is internal and can be reverted independently.

## Open Questions

_None — all decisions are resolved._
