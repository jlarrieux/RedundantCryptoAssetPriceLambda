## Tasks

### Cryptofund20xShared changes

- [x] Add `non_retryable_statuses` parameter to `url_util.open_url_async()` — optional set, default empty. Inside the retry loop exception handler, check if `ClientResponseError.status` is in the set; if so, re-raise immediately without retrying.
- [x] Update `price_client.py` `__get_asset_price_remote_async()` to pass `non_retryable_statuses={404}` and catch the re-raised `ClientResponseError` to return `None`.
- [x] Add tests for `url_util.open_url_async` `non_retryable_statuses`: (a) 404 with `{404}` raises immediately without retry, (b) 404 without the parameter retries as before (default behavior preserved), (c) 500 with `{404}` retries normally, (d) connection timeout retries normally.
- [ ] Add tests for `price_client.py`: (a) single-asset 404 returns `None` in < 3s, (b) batch request uses existing 200 partial-success path (no 404 involved).
- [ ] Commit and push Cryptofund20xShared to GitHub.

### PriceService changes

- [x] Add `get_cached_prices_batch(assets)` to `pricing/redis_cache_service.py` — creates one Redis client, opens a pipeline, enqueues HGETALL per asset, executes, applies timestamp staleness checks (WARNING >30min, ERROR >1hr) per result, returns `(success_dict, missed_assets, errored_assets)`. Catches pipeline-level `RedisConnectionError`/`RedisTimeoutError` at the `execute()` boundary (all assets errored, URL cache invalidated).
- [x] Update `PriceService.get_prices()` in `price_service.py` to call `get_cached_prices_batch()` instead of the sequential loop. Change logging behavior: log `missed_assets` at WARNING level (not ERROR as before), increment `PRICE_SERVICE_FAILURE` counter only for `errored_assets` and pipeline-level failures (not for cache misses). Collapse `missed_assets + errored_assets` into `failed_assets` for the response.
- [x] Pip install updated Cryptofund20xShared in PriceService repo.
- [x] Add tests for `get_cached_prices_batch`: (a) all assets found, (b) partial miss, (c) per-command error, (d) pipeline-level connection failure (all assets errored), (e) timestamp staleness logging.

### Deployment

- [ ] Build and push PriceService Docker image to ECR.
- [ ] Pip install updated Cryptofund20xShared in Ferengi and Saver repos, rebuild and push their Docker images.
- [ ] Deploy PriceService, Ferengi, and Saver via Nomad with `--pull-latest`.
- [ ] Verify in production: check that batch price lookups use pipeline (latency improvement visible in metrics), confirm 404 fast-path works (single asset miss < 3s), verify no regressions in Saver batch cycle, confirm cache misses log at WARNING (not ERROR).
