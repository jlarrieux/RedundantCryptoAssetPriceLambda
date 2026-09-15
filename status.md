# PriceService — Project Status

**Last updated:** 2026-09-15 (chg_priceservice_005 — GitHub PAT switched to a BuildKit secret mount, dead AWS Lightsail credential declarations deleted; deployed, Nomad job version 38; see Completed stage)
**Anchor:** main @ 8c26fe7 (v1.0.9, deployed 2026-09-15, Nomad job version 38, healthy)
**Status:** active

> Descriptive, not normative. Specs/ADRs/README/Akasha win on conflict; disagreement means THIS file is stale.

## At a glance

| Question | Current state |
| --- | --- |
| Service health | 25/25 Nomad allocations healthy after canary promotion (2026-08-31) |
| Current deployment | Job version 36, image release v1.0.7 |
| Latest change | Added `KNOWN_UNRESOLVABLE_ASSETS` allowlist (btrfly/cnc/dpx/jpeg/rdpx); a single-price miss on these no longer increments `price_service_complete_batch_failures_total{type="single"}` |
| Verification | 24 tests passed; live: 3 real HTTP requests (2 known-unresolvable, 1 genuinely unexpected symbol) produced exactly 1 counter increment |
| Top risk | None for this change — an unrelated symbol's miss was independently confirmed to still increment the counter, so this does not create a blanket miss-suppression hole |

## What this project is

PriceService provides cached cryptocurrency prices. The authoritative definition
of done for the most recent change is [Akasha task
"PricePopulator/Ferengi: suppress persistent-failure alerting for
CoinGecko-delisted assets"](http://192.168.1.252:8686/api/items/6a95acef868bdef65eec6244)
in the Cryptofund20x project.

## Completed stage

**Release-path git push gap fixed (2026-09-14, `chg_priceservice_004`, Talit hotfix, genuine dual LGTM round 1, auto-merged; commit `171b1f3`).** Closes the PriceService slice of the fleet-wide consolidated task `6aa896cd41aedd9912183b8a`, applying the exact fix already proven in Ferengi/Saver/PricePopulator: `build_docker.sh` committed and tagged version bumps entirely locally, with no push step anywhere in the release path. Now runs `git push origin main` and `git push origin --tags` immediately after the local commit/tag step, warning and continuing on failure rather than aborting the build.

**All 7 historical tags** (`v1.0.1`-`v1.0.7` — this repo's entire tag history) were missing from `origin` before this fix, confirmed via `git ls-remote --tags`. Running the real `./build_docker.sh` caught up every one as a side effect of the new unconditional `--tags` push, alongside the new `v1.0.8` tag. Full suite independently re-run: 24 passed, 0 regressions.

**Deployed 2026-09-15** (Nomad job version 37, healthy) once server1's DNS issue was root-caused and fixed (Ferengi's `status.md`, Akasha `6aa896da41aedd9912183b8b`). No functional difference from v1.0.7: this change touches only `build_docker.sh`, zero application code.

**GitHub PAT/AWS credential build-args fixed (2026-09-15, `chg_priceservice_005`, Talit hotfix, genuine dual LGTM round 1, auto-merged; commit `8c26fe7`).** Closes the PriceService slice of `6aa8add341aedd9912183b93`. `Dockerfile`'s builder stage switched from a plain `ARG GIT_PAT` to a BuildKit `--secret id=git_pat,env=PAT` mount (already-multi-stage build meant no temp-file trick was needed, unlike PricePopulator's single-stage case). `ARG AWS_LIGHTSAIL_ACCESS_KEY_ID`/`ARG AWS_LIGHTSAIL_SECRET_ACCESS_KEY`/`ENV AWS_ACCESS_KEY_ID`/`ENV AWS_SECRET_ACCESS_KEY` deleted outright — confirmed dead (zero `boto3`/AWS usage anywhere in this codebase). `build_docker.sh` now `export`s `PAT` and builds with `sudo --preserve-env=PAT docker build --secret id=git_pat,env=PAT`.

Built image independently confirmed secret-free via safe length/grep-count checks only (`Config.Env`, `docker history`) — zero `SecretsUsedInArgOrEnv` warnings from `docker build` itself, down from 4. Full suite: 24 passed, 0 regressions. Deployed v1.0.9, Nomad job version 38, healthy.

The 2026-08-31 hotfix (Talit `chg_pricepopulator_006`, commit `ea0af35`) added a
5-symbol `KNOWN_UNRESOLVABLE_ASSETS` frozenset to `price_service.py`. A
single-price cache miss for `btrfly`/`cnc`/`dpx`/`jpeg`/`rdpx` — all confirmed
permanently delisted from CoinGecko — now logs a warning instead of
incrementing the failure counter; every other symbol's miss still increments
exactly as before. Release `v1.0.7` is deployed (job version 36, all 25
allocations healthy) and live-verified: the deployed container's
`price_service.py` was read directly and confirmed to contain the allowlist
before promotion, and a live before/after metrics scrape across three real
requests confirmed the counter behavior end to end, not just in unit tests.

The prior `69d97ed3df08d2f1594f0251` (INFO-log demotion) remains done and
unaffected by this change.

## Next tasks

- Monitor the source-volume reduction over normal traffic (carried over,
  unaffected by this change).
- Re-scope and re-size the remaining PricePopulator payload-log demotion slice
  (carried over, unaffected by this change).

## Work ledger

Akasha task `69d97ed3df08d2f1594f0251` is done through Talit change
`chg_priceservice_002`. The overlapping cache-hit task was reconciled so it cannot
reopen PriceService work; its remaining candidate scope is PricePopulator only.
The related handler-accumulation task is already done. There are no blocking edges.

Akasha task `6a95acef868bdef65eec6244` is done through Talit hotfix
`chg_pricepopulator_006` (2026-08-31), run against PricePopulator as the
instantiation repo with this repo touched as an authorized cross-repo dependency
(the failure counter this task fixes is defined here, not in PricePopulator).
Split from a Red-sized parent (`6a8afa8bf34fb84c8cd9a39d`) the same day; the
sibling task (`6a95acd3868bdef65eec6243`, mapping fixes for lyra/xgrail/
stake_dao/ndx) does not touch this repo.

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

**Update 2026-08-31:** job version 36 deployed via canary (all 25 allocations
converged, old version-35 allocations stopped). ECR digest
`sha256:b5b7e11cbada350e5407c5fb6081e98e06182960def469079b16a0b2f887d877`. The
canary allocation's `/app/price_service.py` was read directly via
`nomad alloc exec` and confirmed to contain `KNOWN_UNRESOLVABLE_ASSETS` before
promotion. Post-promotion, a live metrics scrape before and after three real
`/price/<asset>` requests (`btrfly`, `jpeg`, and a fabricated unmapped symbol)
showed `price_service_complete_batch_failures_total{type="single"}` incremented
by exactly 1 — the two known-unresolvable requests did not increment it, the
genuinely unexpected one did. This was also added `force_pull = true` to the
live Nomad job spec (previously unset; PricePopulator's own job already had it)
to make future `:latest` redeploys of this job reliable.

## Findings & risks

The handler multiplier is closed. This release removes the PriceService
per-request INFO floor but does not address payload-rich PricePopulator logs,
debug `print()` calls, or log-volume alerting. Separately, the 2026-08-31
change confirmed a batch-path failure counter (`PRICE_SERVICE_FAILURE.labels
('batch').inc()`, incremented only on genuine Redis pipeline errors, not on
missed_assets) was never subject to the same inflation this fix addresses —
verified by reading `get_cached_prices_batch()` directly, not assumed.

## How to update this document

Akasha is authoritative for work state; Nomad and ECR are authoritative for live
deployment state; Git and `pytest -q` are authoritative for source and test
state. Refresh this document after a release, deployment, task-status change, or
material operational finding; update the header date and change phrase with every edit.
