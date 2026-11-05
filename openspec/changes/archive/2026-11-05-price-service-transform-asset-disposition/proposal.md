# Remove the stale `transform_asset` endpoint

## Why

PriceService's local `transformer.py` copy is exposed only through
`GET /transform-asset`; neither `/price/<asset>` nor `/prices` calls it. The
kickoff evidence reports that 24 of 57 mapping keys differ from
PricePopulator's copy, including stale `lyra` and `xgrail` mappings. Keeping a
second mapping table preserves the source of the drift without serving the
price endpoints.

I recommend removing the route and its local transformer instead of aligning
the copy. The caller evidence found no active dependency in its measured
scope, and the mapping's owning service is PricePopulator. The endpoint is an
API removal; a remaining caller will receive the app's ordinary unknown-route
response.

## Caller evidence and limits

At baseline `eb0f4e8`, my repository-wide tracked-file search found source
references only in `price_app.py` (the import, route, and route metrics),
`transformer.py`, and two assertions in `tests/test_price_service_logging.py`.
There is no coupling in the Dockerfile, supervisord config, requirements,
scripts, README, or current specs. The only archived-change match is an
out-of-scope mention in the prior observation-time proposal.

The Overlord's read-only caller-audit pack reports: no `transform-asset`
`requests_total` series across jobs in its 180-day query; PriceService's
observed request series begin only about 42 days before that audit; no matching
Grafana dashboard or alert-rule reference; and no caller in the checked
repositories Ferengi, PricePopulator, Saver, SaverDashboard, FormatterService,
Cryptofund20xShared, AssetSymbolTransformer, DBUpdater, and BackendCommons.
These external results are from the Overlord's pack, not my repository reads.

This is not a claim of an exhaustive global audit. The pack did not cover
Nomad job files outside repositories, Midas/Cerberus or other non-family
repositories, Elasticsearch access logs, calls older than the observed metric
retention, or a request handled by an instance that disappeared before a
scrape. The removal should be reconsidered if any such caller is found.

## What changes

- Remove the `/transform-asset` handler and `import transformer` from
  `price_app.py`, and delete `transformer.py`.
- Replace the two old route assertions with Quart app-client coverage proving
  the removed path now matches an unknown route and checking the unchanged
  `/price`, `/prices`, `/health`, and `/metrics` behavior. The repository
  currently defines `/` as its health response; the test will also preserve
  that route and characterize `/health` as it behaves today.
- Add an `ADDED` requirement under a new `price-service-api-surface`
  capability. No existing capability currently specifies this endpoint.
- Update README.md to list the remaining API surface and explain why
  `/transform-asset` was removed.

No new unmatched-route metric is proposed. The app has no such counter, and an
unknown route does not enter the removed handler's metrics. The
`transform-asset` label series on `requests_total`, `errors_total`, and
`request_latency_seconds` will no longer be produced; the Overlord's pack found
no dashboard or alert reading them, and existing samples will age out under
current retention. A late caller can be detected only through the ordinary
HTTP access logging available in the deployed runtime, if enabled; Design will
verify the Quart response and logging behavior before finalizing that statement.

Rollback is to restore the route and module from the pre-change revision and
redeploy PriceService. It requires the normal image build, push, deploy, and
live verification, with no data migration.

## Scope and verification

In scope are the route/module removal, its app-level regression coverage, a
new API-surface spec delta, and README documentation. `/price`, `/prices`, `/`,
`/health`'s existing behavior, `/metrics`, Redis access, error accounting,
`observed_at`, status/version files, PricePopulator, and other repositories are
out of scope. The implementer will not deploy.

The focused test will use `price_app.app.test_client()` and a fake
`PriceService`, with no Redis, MongoDB, or network access. It will record the
actual unknown-route status and body from Quart, ensure that path does not
increment application request metrics, and cover the preserved endpoints. The
full suite will run twice with the specified commands, one run disabling
`randomly`; changed Python files will be checked for Python 3.10 syntax. Strict
OpenSpec validation is required at the Spec and Task gates, and archive
behavior will be rehearsed in a scratch copy outside the repository.
