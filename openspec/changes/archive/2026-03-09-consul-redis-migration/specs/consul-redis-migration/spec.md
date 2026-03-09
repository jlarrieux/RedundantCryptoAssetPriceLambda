## MODIFIED Requirements

### Requirement: Redis connection uses Consul-based discovery
`get_redis_client()` SHALL obtain the Redis URL from `db_layer_caller.get_redis_url(db=0)` instead of a hardcoded constant.

#### Scenario: Normal operation
- **WHEN** `get_redis_client()` is called
- **THEN** it SHALL use the cached URL from `db_layer_caller.get_redis_url(db=0)` if the cache is valid
- **AND** pass that URL to `aioredis.from_url()` with `decode_responses=True` and `db=0`

#### Scenario: First call (cold cache)
- **WHEN** `get_redis_client()` is called for the first time (no cached URL)
- **THEN** it SHALL call `db_layer_caller.get_redis_url(db=0)` to resolve the URL
- **AND** cache the result with a timestamp

#### Scenario: Consul discovery fallback
- **WHEN** Consul is unreachable
- **THEN** `db_layer_caller.get_redis_url(db=0)` handles fallback internally (env var → hardcoded default)
- **AND** `get_redis_client()` receives a valid Redis URL regardless

### Requirement: No hardcoded Redis URL
`redis_cache_service.py` SHALL NOT contain any hardcoded Redis host or URL constant. The only source of the Redis URL SHALL be `db_layer_caller.get_redis_url()`.

### Requirement: Cached URL with TTL
The resolved Redis URL SHALL be cached at module level with a 5-minute TTL (300 seconds). There is no scheduler cadence to match — the service is purely request-driven (`price_app.py` starts `AsyncIOScheduler` but registers no jobs).

#### Scenario: Cache is fresh
- **WHEN** `get_redis_client()` is called and the cached URL is less than 5 minutes old
- **THEN** the cached URL SHALL be reused without calling `db_layer_caller.get_redis_url()`

#### Scenario: Cache has expired
- **WHEN** `get_redis_client()` is called and the cached URL is 5 minutes old or older
- **THEN** `db_layer_caller.get_redis_url(db=0)` SHALL be called to re-resolve the URL
- **AND** the cache SHALL be updated with the new URL and timestamp

### Requirement: Cache invalidation on network-level connection failure
The cached URL SHALL be cleared when a Redis operation raises a network-level exception, so the next call to `get_redis_client()` re-resolves via Consul.

#### Scenario: RedisConnectionError during Redis operation
- **WHEN** a Redis operation raises `redis.exceptions.ConnectionError` (aliased as `RedisConnectionError`)
- **THEN** the cached URL SHALL be cleared
- **AND** the next call to `get_redis_client()` SHALL re-resolve via `db_layer_caller.get_redis_url(db=0)`

#### Scenario: RedisTimeoutError during Redis operation
- **WHEN** a Redis operation raises `redis.exceptions.TimeoutError` (aliased as `RedisTimeoutError`)
- **THEN** the cached URL SHALL be cleared

#### Scenario: OSError during Redis operation
- **WHEN** a Redis operation raises `OSError`
- **THEN** the cached URL SHALL be cleared

#### Scenario: Logical Redis error (no invalidation)
- **WHEN** a Redis operation raises `ResponseError`, `DataError`, or other `RedisError` subclasses that are not `ConnectionError` or `TimeoutError`
- **THEN** the cached URL SHALL NOT be cleared

Note: In redis-py, `TimeoutError` is a `RedisError` subclass. It is explicitly carved out as a network-level exception that triggers invalidation (see RedisTimeoutError scenario above).

### Requirement: Import-time version guard
At import time, `redis_cache_service.py` SHALL verify that the installed `get_redis_url` accepts a `db` parameter using `inspect.signature()`. If the parameter is absent, it SHALL raise `ImportError` with a clear message.

#### Scenario: Compatible Cryptofund20xShared installed
- **WHEN** the installed `get_redis_url` has a `db` parameter
- **THEN** the module SHALL import successfully

#### Scenario: Stale Cryptofund20xShared installed
- **WHEN** the installed `get_redis_url` lacks a `db` parameter
- **THEN** an `ImportError` SHALL be raised with a message indicating the minimum required version

### Requirement: Existing operation unchanged
`get_cached_price_async` SHALL retain its current function signature, return type, and data behavior. Cache invalidation on network-level exceptions (see above) is new internal behavior that does not affect callers.

## UNCHANGED Requirements

- Function signature for `get_cached_price_async`
- Price data retrieval format (hash with `usd_price`, `volume_last_24_hours`, `current_marketcap_usd`, `timestamp` fields)
- Key naming convention (`price:{asset}`)
- Timestamp freshness logging (ERROR > 1 hour, WARNING > 30 minutes)
- `decode_responses=True` setting on Redis client
