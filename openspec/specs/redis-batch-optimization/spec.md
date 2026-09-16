# redis-batch-optimization Specification

## Purpose
TBD - created by archiving change optimize-price-service-redis-performance. Update Purpose after archive.
## Requirements
### Requirement: Batch price lookups SHALL use a Redis pipeline
`PriceService.get_prices()` SHALL execute all `HGETALL` commands for the requested asset list in a single Redis pipeline round-trip, rather than issuing sequential per-asset commands.

#### Scenario: Batch request with multiple assets
- **WHEN** a client calls `GET /prices?assets=eth,btc,aave,crv`
- **THEN** the service issues all four `HGETALL` commands in a single Redis pipeline `execute()` call
- **AND** returns results for each asset individually (success or failure per asset)

#### Scenario: Batch request with single asset
- **WHEN** a client calls `GET /prices?assets=eth`
- **THEN** the service still uses the pipeline path (no special-casing for single asset)

### Requirement: Batch function SHALL return three-category results
The new `get_cached_prices_batch()` function SHALL return a tuple of `(success_dict, missed_assets, errored_assets)` where:
- `success_dict`: assets with valid cached data (dict of asset name to price data)
- `missed_assets`: assets where HGETALL returned empty (list of asset names)
- `errored_assets`: assets where the pipeline returned a per-command error (list of asset names)

#### Scenario: All assets found in cache
- **WHEN** all requested assets have valid Redis cache entries
- **THEN** `success_dict` contains all assets, `missed_assets` is empty, `errored_assets` is empty

#### Scenario: Some assets missing from cache
- **WHEN** some requested assets have no Redis cache entry
- **THEN** `success_dict` contains found assets, `missed_assets` contains missing asset names, `errored_assets` is empty

#### Scenario: Redis per-command error on one asset
- **WHEN** one asset's `HGETALL` returns a `ResponseError` in the pipeline result list
- **THEN** that asset is in `errored_assets`, other assets are processed normally

### Requirement: Pipeline-level failure SHALL treat all assets as errored
When `pipeline.execute()` raises `RedisConnectionError` or `RedisTimeoutError`, the batch function SHALL catch the exception, invalidate the URL cache, and return all requested assets as `errored_assets` with an empty `success_dict` and empty `missed_assets`.

#### Scenario: Redis connection failure during pipeline execute
- **WHEN** `pipeline.execute()` raises `RedisConnectionError`
- **THEN** the batch function returns `({}, [], [all_requested_assets])`
- **AND** the URL cache is invalidated

#### Scenario: Redis timeout during pipeline execute
- **WHEN** `pipeline.execute()` raises `RedisTimeoutError`
- **THEN** the batch function returns `({}, [], [all_requested_assets])`
- **AND** the URL cache is invalidated

### Requirement: The /prices endpoint SHALL preserve the existing wire format
The `/prices` endpoint SHALL continue to return `{"prices": [success_dict, failed_list]}` where `failed_list` is the concatenation of `missed_assets` and `errored_assets`. No change to the response structure.

#### Scenario: Backward-compatible response for partial success
- **WHEN** 3 of 4 assets are found and 1 is missing
- **THEN** the response is `{"prices": [{"eth": {...}, "btc": {...}, "aave": {...}}, ["crv"]]}`
- **AND** HTTP status is 200

### Requirement: Cache misses and errors SHALL have distinct log levels
Cache misses SHALL be logged at WARNING level. Redis errors (per-command or pipeline-level) SHALL be logged at ERROR level and increment the `price_service_batch_redis_errors_total` counter.

#### Scenario: Cache miss logging
- **WHEN** an asset is not found in Redis (empty HGETALL)
- **THEN** a WARNING log is emitted with the asset name

#### Scenario: Redis error logging
- **WHEN** a Redis error occurs (per-command or pipeline-level)
- **THEN** an ERROR log is emitted and `price_service_batch_redis_errors_total` counter is incremented

### Requirement: Batch function SHALL preserve timestamp staleness validation
The `get_cached_prices_batch()` function SHALL apply the same timestamp age checks as `get_cached_price_async()`: log WARNING when a cached entry is older than 30 minutes, log ERROR when older than 1 hour. These checks SHALL run per-asset on the pipeline results.

#### Scenario: Cache entry older than 30 minutes
- **WHEN** a batch lookup returns a cached entry with a timestamp older than 30 minutes but less than 1 hour
- **THEN** a WARNING log is emitted for that asset

#### Scenario: Cache entry older than 1 hour
- **WHEN** a batch lookup returns a cached entry with a timestamp older than 1 hour
- **THEN** an ERROR log is emitted for that asset

### Requirement: Single-asset endpoint SHALL remain unchanged
The `/price/<asset>` endpoint and `get_single_price()` method SHALL continue using the existing `get_cached_price_async()` function. The pipeline optimization applies only to the batch path.

#### Scenario: Single asset request unchanged
- **WHEN** a client calls `GET /price/eth`
- **THEN** the request uses the existing single-asset code path, not the pipeline batch function
