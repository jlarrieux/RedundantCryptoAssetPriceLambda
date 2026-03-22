## ADDED Requirements

### Requirement: url_util.open_url_async SHALL support non-retryable HTTP statuses
`url_util.open_url_async()` SHALL accept an optional `non_retryable_statuses` parameter (default: empty set). When `response.raise_for_status()` raises `aiohttp.ClientResponseError` and the response status is in `non_retryable_statuses`, the function SHALL re-raise the exception immediately without retrying.

#### Scenario: 404 with non_retryable_statuses={404}
- **WHEN** `open_url_async(url, non_retryable_statuses={404})` receives a 404 response
- **THEN** the function raises `ClientResponseError` immediately without retrying
- **AND** the total elapsed time is approximately one request timeout, not retries * delay

#### Scenario: 404 without non_retryable_statuses (default behavior unchanged)
- **WHEN** `open_url_async(url)` receives a 404 response (no non_retryable_statuses passed)
- **THEN** the function retries as before (up to max_retries with delay between attempts)

#### Scenario: 500 with non_retryable_statuses={404}
- **WHEN** `open_url_async(url, non_retryable_statuses={404})` receives a 500 response
- **THEN** the function retries normally (500 is not in the non-retryable set)

### Requirement: price_client SHALL pass non_retryable_statuses={404} for single-asset lookups
`__get_asset_price_remote_async()` in `price_client.py` SHALL pass `non_retryable_statuses={404}` to `url_util.open_url_async()`. The batch function `get_asset_price_list_async()` calls `/prices` which returns HTTP 200 with partial results (missing assets in `failed_list`), so the 404 fast-path does not apply to the batch path.

#### Scenario: Single asset cache miss returns None immediately
- **WHEN** `get_asset_price_async("unknown_token")` calls `GET /price/unknown_token` and receives 404
- **THEN** `__get_asset_price_remote_async` receives the `ClientResponseError` immediately (no retries) and returns `None`
- **AND** total elapsed time is under 3 seconds (single request, no retries)

#### Scenario: Batch request uses existing 200 partial-success contract
- **WHEN** `get_asset_price_list_async(["eth", "unknown_token"])` calls `GET /prices?assets=eth,unknown_token`
- **THEN** PriceService returns HTTP 200 with `{"prices": [{"eth": {...}}, ["unknown_token"]]}`
- **AND** the client parses `loaded['prices'][0]` for the success dict as before (no 404 involved)

### Requirement: Existing retry behavior SHALL be preserved for non-404 errors
All HTTP errors other than those in `non_retryable_statuses` SHALL continue to be retried with the existing backoff logic in `url_util.open_url_async`.

#### Scenario: 503 still retried
- **WHEN** `open_url_async(url, non_retryable_statuses={404})` receives a 503 response
- **THEN** the function retries up to max_retries with the configured delay

#### Scenario: Connection timeout still retried
- **WHEN** `open_url_async(url, non_retryable_statuses={404})` encounters a connection timeout
- **THEN** the function retries as before (timeouts are not HTTP status codes)

### Requirement: Shared library update SHALL follow the standard deploy sequence
The `non_retryable_statuses` change in `url_util.open_url_async` and the `{404}` usage in `price_client.py` SHALL be committed and pushed to Cryptofund20xShared before building Docker images for PriceService, Ferengi, or Saver. Each downstream repo SHALL `pip install` the updated library before its Docker build.

#### Scenario: Deploy sequence
- **WHEN** implementing this change
- **THEN** the sequence is: Cryptofund20xShared commit+push → pip install in each repo → Docker build → Nomad deploy
- **AND** no downstream Docker image is built with the old shared library version
