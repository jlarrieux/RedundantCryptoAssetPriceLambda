# Design: remove the stale `transform_asset` endpoint

## Decision

Remove `GET /transform-asset`, its import and handler in `price_app.py`, and
the copied `transformer.py` module. `/price/<asset>` and `/prices` use the
original Redis symbols and do not call the transformer, so keeping or aligning
the duplicate mapping would not change either price endpoint. Removing the
only exposed copy also removes the source of its drift. PricePopulator and all
other repositories remain untouched.

This choice follows the caller evidence in the Overlord's pack. The pack found
no matching request series in its 180-day Thanos query, although observed
PriceService samples begin only about 42 days before the audit. It also found no
dashboard or alert references and no callers in the checked family
repositories. The pack did not cover Nomad job files outside the repositories,
Midas/Cerberus or other non-family repositories, Elasticsearch access logs,
callers older than metric retention, or requests served by an instance replaced
before a scrape. These are limits, not evidence that such callers exist.

## Route and unknown-path behavior

After removal, the application route surface is:

- `GET /` for the existing `OK` health response.
- `GET /price/<asset>` for one cached price.
- `GET /prices?assets=...` for the existing batch response.
- `GET /metrics` for Prometheus exposition.

There is no dedicated `/health` route today. Quart returns the default unknown
route response for both `/health` and any other unregistered path. A local
`price_app.app.test_client()` probe, with only `PriceService` substituted to
avoid Redis, returned HTTP 404, `text/html; charset=utf-8`, and this body for
`/health`:

```html
<!doctype html>
<html lang=en>
<title>404 Not Found</title>
<h1>Not Found</h1>
<p>The requested URL was not found on the server. If you entered the URL manually please check your spelling and try again.</p>
```

The implementation test will compare `GET /transform-asset?asset=BTC` with a
separate unregistered path through the real Quart app client. Both must return
404 with the same content type and body. The probe also confirmed that an
unknown request does not change the rendered `requests_total`, `errors_total`,
or `request_latency_seconds` application metric lines. There is no unmatched-
route counter in PriceService.

For a late caller after release, the deployed Uvicorn access log is the
available signal: it records the request method, path, and 404 status. The
service starts Uvicorn without disabling access logging, and supervisord sends
its stdout and stderr to the container streams. This design does not claim
that Elasticsearch access logs were inspected or that a central retention
query is available. No new instrumentation is justified for a retired route.

## Metrics and rollback

Removing the handler stops producing its `requests_total`, `errors_total`, and
`request_latency_seconds` samples labeled with `endpoint="transform-asset"`.
The Overlord's pack found no Grafana dashboard or alert-rule consumer for those
series. Historical samples remain queryable until the existing metrics
retention expires them; no data migration or cleanup is needed.

Rollback restores the handler, its metrics instrumentation and transformer
module, then restores the related README, spec, and tests. The Overlord performs
the normal image build, push, deploy, and live verification for the existing
service. This costs one ordinary release cycle and has no persistence or data
migration cost. During a rollback rollout, callers may continue to receive
404 until their allocation is replaced.

## Repository coupling audit

This session searched tracked repository content for `transform[-_]asset` and
`transformer`, including the runtime files, build scripts, README, current
specs, active changes, and archived changes. The runtime references are only
the `price_app.py` import/handler/metric labels, `transformer.py`, and the two
route assertions in `tests/test_price_service_logging.py`. There are no matches
in `Dockerfile`, `supervisord.conf`, `requirements.txt`,
`build_docker.sh`, `push_docker.sh`, `variables.sh`, `README.md`, or
`openspec/specs/`. The repository has no `scripts/` directory. The only
archived-change match is the 2026-11-04 observation-time proposal listing
`/transform-asset` among out-of-scope behavior; it is historical prose, not a
runtime dependency. The current change's own proposal also names the route.

The Overlord's pack separately reports no caller in Ferengi, PricePopulator,
Saver, SaverDashboard, FormatterService, Cryptofund20xShared,
AssetSymbolTransformer, DBUpdater, or BackendCommons, and no matching route
reference in Grafana dashboards or alert rules. Those cross-repository and
Grafana results are from the Overlord's pack, not this repository search.

## Tests

Replace the two `/transform-asset` assertions in
`tests/test_price_service_logging.py` with app-client coverage derived from
these contracts:

1. The removed path returns the same 404 status, content type, and response
   body as another unknown path. Capture the application's request/error/
   latency metric lines before and after the unknown request and prove they do
   not change; assert there is no `transform-asset` endpoint series.
2. The existing `/price/<asset>` response and `/prices` response envelope
   remain unchanged, using a fake `PriceService` and no Redis, MongoDB, or
   network access.
3. `/health` remains the same unknown route (404 and the same body), `/`
   remains `200 OK`, and `/metrics` remains a successful Prometheus response.
4. Retain the price logging assertions while removing expectations for the
   deleted transform handler's debug and missing-asset error logs.

The focused scope is `tests/test_price_service_logging.py`. Mutation checks
will be performed during Implementation: temporarily restore the route and
confirm the new unknown-route assertion fails; restore it before temporarily
breaking `/price` and confirm the existing price route assertion fails. Each
mutant is restored before the next check.

## Specification and documentation

Add a requirement under a new `price-service-api-surface` capability; no
existing capability currently specifies this endpoint. The requirement will
name the remaining routes and state that `/transform-asset` is not exposed and
uses the same unknown-route response as other missing paths. Update README.md
to list the remaining HTTP routes and explain that `/transform-asset` was
removed because the copied mapping drifted and had no caller in the audited
scope.

Strict OpenSpec validation will run at the Spec and Task gates. Before the
Implementation handoff, rehearse `openspec archive` on a scratch copy outside
the repository and confirm the newly synced main spec has a real Purpose
instead of the `TBD` placeholder. Implementation verification will run the
focused test, the full suite twice with the specified `randomly` variants,
and compile changed Python files with Python 3.10 semantics. No build, push,
deploy, live backend access, or status/version edit is part of this change.
