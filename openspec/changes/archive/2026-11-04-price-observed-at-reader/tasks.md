# Tasks: return the cached observation time

The checkboxes below are Implementation execution items. They stay unchecked
through Task review and are completed only after the Task artifact is approved
and the change enters Implementation; completed work and verification results
are then reported against these tasks.

## Implementation

- [x] 1.1 Update `price_app.py` so `GET /price/<asset>` copies a present `observed_at` value unchanged into its response and omits the key when absent. Keep the four existing fields unchanged and leave the `/prices` raw-hash path, Redis cache logic, and batch accounting unchanged.
- [x] 1.2 Add Quart app-level tests in `tests/test_price_observed_at_api.py`. Use `app.test_client()` and fake Redis only at its boundary. Cover exact single-value preservation with microseconds and `+00:00`, absent-field omission with the four existing fields intact, batch present and absent values, the unchanged `{"prices": [success_dict, failed_list]}` envelope, the legacy `timestamp`, a 15-minute-old value whose age is derived with `datetime.fromisoformat()`, malformed values passed through unchanged, and the absence of request-time substitutes.

## Documentation and specification

- [x] 2.1 Add one short README section documenting both endpoint responses, the producer's `observed_at` format and cache-write meaning, omission when absent, and consumer-owned freshness decisions.
- [x] 2.2 Create `openspec/specs/price-observation-time/spec.md` with the approved capability Purpose and no duplicate requirement. This Purpose seed lets the later archive merge the approved ADDED requirement without generating the TBD placeholder; keep the approved change delta unchanged.

## Verification

- [x] 3.1 Run the focused scope `python -m pytest -q -W ignore -o log_cli=false tests/test_price_observed_at_api.py tests/test_redis_cache_service.py`, then run the full suite twice with no path argument: `env -u PYTHONSAFEPATH python -m pytest -q -W ignore -o log_cli=false` and `env -u PYTHONSAFEPATH python -m pytest -q -W ignore -o log_cli=false -p no:randomly`. Compare both full-suite counts with the 25-test baseline and report each failure with its output and whether it is pre-existing or new. Run each of these five mutants separately, show the failing test name, and restore the source before the next mutant: omit `observed_at` from the single response; reformat the stored value; substitute current time for an absent value; drop the batch legacy `timestamp`; change the batch outer response shape. Compile every changed Python file with Python 3.10.

## Deliverables

- `price_app.py` conditionally returns the stored observation time from the single-price endpoint.
- `tests/test_price_observed_at_api.py` exercises both HTTP routes through Quart with fake Redis at the client boundary.
- `README.md` (checklist: readme) documents the response contract and consumer-owned freshness decision.
- `openspec/changes/price-observed-at-reader/specs/price-observation-time/spec.md` records the approved ADDED capability delta.
- `openspec/specs/price-observation-time/spec.md` supplies the real Purpose used when archive applies the approved delta.
