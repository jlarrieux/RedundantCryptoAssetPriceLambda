# PriceService — Project Status

**Last updated:** 2026-08-14 (logger-handler hotfix deployed and Akasha task closed)
**Anchor:** main @ 95d7e3a
**Status:** active

> Descriptive, not normative. Specs/ADRs/README/Akasha win on conflict; disagreement means THIS file is stale.

## At a glance

| Question | Current state |
| --- | --- |
| Service health | 25/25 Nomad allocations healthy (2026-08-14) |
| Current deployment | Job version 33, image release v1.0.5 |
| Latest change | Prevents repeated `PriceService()` construction from accumulating logger handlers |
| Verification | 20 local tests passed; live canary and full rollout passed |
| Top risk | Per-request INFO log volume remains separately tracked in Akasha |

## What this project is

PriceService provides cached cryptocurrency prices. The authoritative definition
of done was [Akasha task "Fix PriceService logger handler accumulation"](http://192.168.1.252:8686/api/items/6a7b83caef91c58a292e2e90) in the Cryptofund20x project.

## Completed stage

The 2026-08-14 handler-accumulation hotfix is deployed. The named logger now has one process-local handler across repeated service construction.

## Next tasks

- Review the separate PriceService INFO-log demotion tasks in Akasha.

## Work ledger

As checked on 2026-08-14, the Cryptofund20x project had six open tasks before
this closeout. This handler-accumulation task and its PricePopulator twin are
the completed pair; the distinct INFO-demotion, debug-print-removal, alerting,
and unrelated Convex tasks remain open. There are no blocking edges on this task.

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

The handler multiplier is closed since this revision. Per-request INFO volume is
still a separate source-volume concern and remains tracked by the open Akasha
demotion tasks.

## How to update this document

Akasha is authoritative for work state; Nomad and ECR are authoritative for live
deployment state; Git and `pytest -q` are authoritative for source and test
state. Refresh this document after a release, deployment, task-status change, or
material operational finding; update the header date and change phrase with every edit.
