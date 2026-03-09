## 1. Core Implementation

- [x] 1.1 Remove `REDIS_HOST = 'redis://192.168.1.253:6379'` constant from `pricing/redis_cache_service.py`.
- [x] 1.2 Add imports: `from cryptofund20x_services.db_layer_caller import get_redis_url`, `import inspect`, `import time`, and `from redis.exceptions import ConnectionError as RedisConnectionError, TimeoutError as RedisTimeoutError`. Use the `redis.exceptions` aliases to distinguish from Python builtins.
- [x] 1.3 Add import-time version guard: use `inspect.signature(get_redis_url)` to verify `db` parameter exists; raise `ImportError` with clear message if absent.
- [x] 1.4 Add module-level cache variables: `_cached_redis_url = None`, `_cached_url_timestamp = 0.0`, `_URL_TTL = 300` (5 minutes — no scheduler cadence to match; service is purely request-driven).
- [x] 1.5 Update `get_redis_client()` to resolve URL from cache if valid (age < `_URL_TTL`), otherwise call `get_redis_url(db=0)` and update cache.
- [x] 1.6 Add `_invalidate_url_cache()` helper that clears `_cached_redis_url` and `_cached_url_timestamp`.
- [x] 1.7 Update `get_cached_price_async()` to catch network-level exceptions (`RedisConnectionError`, `RedisTimeoutError`, `OSError`) separately from existing error handling — call `_invalidate_url_cache()` before returning the error result. Do not invalidate on `ResponseError`, `DataError`, or other non-network `RedisError` subclasses (excluding `TimeoutError` which is carved out as network-level).

## 2. Test Infrastructure

- [x] 2.1 Create `pytest.ini` with `asyncio_mode = auto`, `asyncio_default_fixture_loop_scope = function`, and `addopts = -p no:ethereum`.
- [x] 2.2 Create `tests/__init__.py`.
- [x] 2.3 Create `tests/conftest.py` with conditional aioredis mock: `try: import aioredis except (ImportError, TypeError): sys.modules['aioredis'] = MagicMock()`.

## 3. Unit Tests (`tests/test_redis_cache_service.py`)

- [x] 3.1 Test that `get_redis_client()` calls `get_redis_url(db=0)` on first invocation (cold cache).
- [x] 3.2 Test that `get_redis_client()` reuses cached URL on subsequent calls within TTL window — mock `get_redis_url` and verify it is called only once across multiple `get_redis_client()` calls.
- [x] 3.3 Test that `get_redis_client()` re-resolves URL after TTL expires — advance time past 300s, verify `get_redis_url` is called again.
- [x] 3.4 Test cache invalidation on `RedisConnectionError` in `get_cached_price_async()` — trigger error, verify cached URL is cleared and next `get_redis_client()` call re-resolves.
- [x] 3.5 Test cache invalidation on `RedisTimeoutError` in `get_cached_price_async()`.
- [x] 3.6 Test cache invalidation on `OSError` in `get_cached_price_async()`.
- [x] 3.7 Test NO cache invalidation on `ResponseError` in `get_cached_price_async()` — verify cached URL is NOT cleared.
- [x] 3.8 Test NO cache invalidation on `DataError` in `get_cached_price_async()` — verify cached URL is NOT cleared.
- [x] 3.9 Test import-time guard rejects `get_redis_url` without `db` parameter — reload module with incompatible mock and verify `ImportError` is raised.
- [x] 3.10 Test that `get_cached_price_async()` returns parsed hash data from Redis (`usd_price`, `volume_last_24_hours`, `current_marketcap_usd`, `timestamp`).
- [x] 3.11 Test that `get_cached_price_async()` returns `None` when key does not exist.
- [x] 3.12 Test that timestamp freshness logging is preserved: mock data with timestamp > 1 hour old and verify ERROR log; mock data with timestamp > 30 minutes old and verify WARNING log.

## 4. Validation

- [x] 4.1 Run full test suite — confirm all tests pass (13/13).
- [x] 4.2 Grep `pricing/` directory for pattern `redis://192.168.1.253` — confirm no hardcoded Redis URLs remain in runtime code.
- [ ] 4.3 Post-deploy smoke test per acceptance criteria (proposal.md:33–37).
