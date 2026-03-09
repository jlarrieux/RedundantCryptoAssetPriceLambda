## Why

`pricing/redis_cache_service.py` hardcodes `redis://192.168.1.253:6379` as the Redis host. Redis has been migrated from server1 (192.168.1.253) to the NAS (192.168.1.252) via a Nomad-managed container registered in Consul. Cryptofund20xShared v0.9.0+ provides `db_layer_caller.get_redis_url(db=N)` with 3-tier Consul-based discovery (Consul → `REDIS_URL` env var → hardcoded default). This service should use it instead of its own hardcoded URL.

## What Changes

- Remove the hardcoded `REDIS_HOST = 'redis://192.168.1.253:6379'` constant and update `get_redis_client()` in `pricing/redis_cache_service.py` to use `db_layer_caller.get_redis_url(db=0)`.
- This service uses Redis database 0 for reading price cache data (written by PricePopulator). It is read-only — only `hgetall()` operations.
- The `aioredis` dependency remains — only the URL source changes.
- Add a runtime import-time guard (via `inspect.signature()`) that verifies the installed `Cryptofund20xShared` exposes `get_redis_url(db=...)`, failing fast with a clear `ImportError` if the shared library is too old. The `requirements.txt` VCS dependency (`git+https://...`) stays as-is — new Docker builds resolve the current default-branch commit (currently v0.9.2). No version pin or tag lock is needed for an internal package under our control.
- Cache the resolved Redis URL at module level with a TTL to avoid per-request Consul lookups. Although `price_app.py` starts an `AsyncIOScheduler`, no scheduled cache refresh jobs are registered — the service is purely request-driven. Unlike PricePopulator's 4-minute cron, there is no natural cadence to tie TTL to, so a 5-minute TTL provides a reasonable balance between freshness and lookup frequency. `get_cached_price_async()` is called per-asset in the `get_prices()` batch loop, so per-call resolution would block the event loop N times per request.
- Invalidate the cached URL on network-level exceptions (`redis.exceptions.ConnectionError`, `redis.exceptions.TimeoutError`, `OSError`) so the next call re-resolves via Consul. Logical Redis errors (`ResponseError`, `DataError`, and other non-network `RedisError` subclasses — excluding `TimeoutError` which is carved out as a network-level exception despite being a `RedisError` subclass) do NOT invalidate the cache.

## Capabilities

### Modified Capabilities
- `redis-connection`: Redis URL is now discovered via Consul instead of hardcoded. Connection behavior and the `get_cached_price_async` operation remain identical.

## Impact

- **Code**: `pricing/redis_cache_service.py` — primary change.
- **Dependencies**: No changes to `requirements.txt`. Runtime version guard added in code.
- **Tests**: New test file `tests/test_redis_cache_service.py` (no existing tests — test infrastructure was removed in commit `57982eb`). Add `pytest.ini` and `tests/conftest.py`.
- **Deployment**: Rebuild and redeploy Docker image.

## Acceptance Criteria

1. `redis_cache_service.py` no longer contains any hardcoded Redis URL.
2. Redis client is created using the URL from `db_layer_caller.get_redis_url(db=0)`.
3. The existing `get_cached_price_async` operation continues to function identically — function signature, return type, and data behavior unchanged.
4. Import-time guard fails fast with a clear error if the installed `Cryptofund20xShared` lacks `get_redis_url(db=...)`.
5. Unit tests verify: cold cache resolution, TTL reuse, TTL expiry re-resolution, cache invalidation on `ConnectionError`/`TimeoutError`/`OSError` (all tested per-function), non-invalidation on `ResponseError`/`DataError` (all tested per-function), and the import-time guard.
6. Post-deploy smoke test:
   - Call `db_layer_caller.get_redis_url(db=0)` and confirm returned URL targets NAS Redis (192.168.1.252).
   - Read `price:ethereum` from DB 0 to confirm connectivity (precondition: PricePopulator is running and has populated this key — verify via `HGETALL price:ethereum` before testing).
   - With `REDIS_URL` unset, temporarily block port 8500 within the service container (e.g. `iptables -A OUTPUT -p tcp --dport 8500 -j REJECT`), call `get_redis_url(db=0)`, and confirm it falls through to the hardcoded default (`redis://192.168.1.252:6379/0`) with a WARNING log. If `NET_ADMIN` capability is unavailable, alternatively set `CONSUL_HOST=127.0.0.1 CONSUL_PORT=1` to force a connection failure. Perform this test in staging or local only.
