# PriceService — Project Status

**Last updated:** 2026-08-14 (INFO-log demotion hotfix prepared for release)
**Anchor:** main @ 95d7e3a
**Status:** active

> Descriptive, not normative. Specs/ADRs/README/Akasha win on conflict; disagreement means THIS file is stale.

## At a glance

| Question | Current state |
| --- | --- |
| Service health | 25/25 Nomad allocations healthy (2026-08-14) |
| Current deployment | Job version 33, image release v1.0.5 |
| Latest change | Demotes six hot-path narrative messages from INFO to DEBUG |
| Verification | 22 local tests passed; Talit reviewer and director approved commit `276e32c` |
| Top risk | Payload-rich PricePopulator INFO logs remain a separate source-volume concern |

## What this project is

PriceService provides cached cryptocurrency prices. The authoritative definition
of done for this release is [Akasha task "PriceService: demote per-request INFO logs
to DEBUG"](http://192.168.1.252:8686/api/items/69d97ed3df08d2f1594f0251) in the
Cryptofund20x project.

## Completed stage

The 2026-08-14 hotfix commit `276e32c` changes six successful-request narratives
to DEBUG while preserving warnings, errors, metrics, and request behavior. It is
awaiting the Overlord-owned release and deployment verification.

## Next tasks

- Monitor the deployed source-volume reduction after release.
- Decide whether a separate PricePopulator payload-log demotion task is warranted.

## Work ledger

The task is active in Talit change `chg_priceservice_002`. It supersedes the
overlapping narrower cache-hit-demotion work within one PriceService change; its
related handler-accumulation task is already done. There are no blocking edges.

## Live state

On 2026-08-14, Nomad deployment `9db9c163` completed job version 33 with 25/25
healthy allocations. The deployed `price-service` allocation `ad18a0ef` imported
the released symbol and reported `PriceService handlers= 1 propagate= False`;
this proves the live artifact carries the handler guard, rather than relying on
health checks alone. The release image was pushed as `v1.0.5` (ECR digest
`sha256:9b82ff8a7333c3b888ebf5ff85084c31292b5b68991ef67b59ea219c73832539`).
A fresh `/price/weth` request at 19:47:17 UTC produced exactly one `Found cached
price for weth` document in that allocation's one-second Elasticsearch bucket.

## Findings & risks

The handler multiplier is closed. This release removes the PriceService
per-request INFO floor but does not address payload-rich PricePopulator logs,
debug `print()` calls, or log-volume alerting.

## How to update this document

Akasha is authoritative for work state; Nomad and ECR are authoritative for live
deployment state; Git and `pytest -q` are authoritative for source and test
state. Refresh this document after a release, deployment, task-status change, or
material operational finding; update the header date and change phrase with every edit.
