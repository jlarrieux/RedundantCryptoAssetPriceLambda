# PriceService — Project Status

**Last updated:** 2026-08-14 (INFO-log demotion hotfix deployed and verified)
**Anchor:** main @ 0062571
**Status:** active

> Descriptive, not normative. Specs/ADRs/README/Akasha win on conflict; disagreement means THIS file is stale.

## At a glance

| Question | Current state |
| --- | --- |
| Service health | 25/25 Nomad allocations healthy (2026-08-14) |
| Current deployment | Job version 34, image release v1.0.6 |
| Latest change | Six hot-path narrative messages demoted from INFO to DEBUG |
| Verification | 22 tests passed; fresh allocation source and live `/price/weth` verified |
| Top risk | Payload-rich PricePopulator INFO logs remain a separate source-volume concern |

## What this project is

PriceService provides cached cryptocurrency prices. The authoritative definition
of done for this release is [Akasha task "PriceService: demote per-request INFO logs
to DEBUG"](http://192.168.1.252:8686/api/items/69d97ed3df08d2f1594f0251) in the
Cryptofund20x project.

## Completed stage

The 2026-08-14 hotfix commit `276e32c` changes six successful-request narratives
to DEBUG while preserving warnings, errors, metrics, and request behavior. Release
`v1.0.6` is deployed and live-verified.

## Next tasks

- Monitor the source-volume reduction over normal traffic.
- Re-scope and re-size the remaining PricePopulator payload-log demotion slice.

## Work ledger

Akasha task `69d97ed3df08d2f1594f0251` is done through Talit change
`chg_priceservice_002`. The overlapping cache-hit task was reconciled so it cannot
reopen PriceService work; its remaining candidate scope is PricePopulator only.
The related handler-accumulation task is already done. There are no blocking edges.

## Live state

On 2026-08-14, Nomad deployment `0396ccd8` completed job version 34 with 25/25
healthy allocations. Fresh allocation `8ac6b243` contains all six intended
`logger.debug` calls and no retained INFO form for the cache-hit or single-request
messages; this proves deployed-artifact content rather than health alone. Release
`v1.0.6` was pushed with ECR digest
`sha256:4e054780f73d83a5e8b2022e9b4c34a2295536b658f423cd9a406545fb5ecf4e`.
A live `/price/weth` request returned WETH price data, and Elasticsearch found zero
former hot-path message documents for that fresh allocation (verification window:
allocation start through 2026-08-14 20:38 UTC).

## Findings & risks

The handler multiplier is closed. This release removes the PriceService
per-request INFO floor but does not address payload-rich PricePopulator logs,
debug `print()` calls, or log-volume alerting.

## How to update this document

Akasha is authoritative for work state; Nomad and ECR are authoritative for live
deployment state; Git and `pytest -q` are authoritative for source and test
state. Refresh this document after a release, deployment, task-status change, or
material operational finding; update the header date and change phrase with every edit.
