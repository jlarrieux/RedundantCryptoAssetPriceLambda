# Tasks: remove the stale transform endpoint

## Task gate

- [x] 0.1 Run `openspec validate --strict` for this change at the Task gate and address any reported issue.
- [x] 0.2 Rehearse `openspec archive` in a scratch copy outside the repository and confirm the synced main spec has a substantive Purpose rather than a TBD placeholder.

## Implementation

- [x] 1.1 Remove the `transformer` import, `/transform-asset` handler, and route-specific request, error, and latency metric emissions from `price_app.py`; delete `transformer.py`. Leave the price routes, `/`, `/metrics`, Redis behavior, error accounting, and `observed_at` behavior unchanged.
- [x] 1.2 Replace the two `/transform-asset` assertions in `tests/test_price_service_logging.py` with Quart `app.test_client()` coverage. Prove the removed path matches another unregistered path in status, content type, and body; does not add application request, error, or latency metrics; and does not produce a transform endpoint series. Cover unchanged `/price`, `/prices`, `/`, `/health`, and `/metrics` behavior using a fake `PriceService`, without Redis, MongoDB, or network access.
- [x] 1.3 Update `README.md` with the remaining route list and a sentence explaining the removal of `/transform-asset` because its copied mapping drifted and no caller was found in the audited scope.
- [x] 1.4 Add `openspec/specs/price-service-api-surface/spec.md` with a real capability Purpose only, so archive syncs the approved ADDED requirement without a TBD Purpose or duplicate requirement. Keep the approved change spec delta unchanged.

## Verification

- [x] 2.1 Run the focused scope `tests/test_price_service_logging.py` and report its result.
- [x] 2.2 Run the full suite twice with no path argument: `env -u PYTHONSAFEPATH python -m pytest -q -W ignore -o log_cli=false` and `env -u PYTHONSAFEPATH python -m pytest -q -W ignore -o log_cli=false -p no:randomly`. Compare each count with the 33-test baseline and report any failure output as pre-existing or new.
- [x] 2.3 Run both removal mutants separately and restore each before the next: temporarily re-add `/transform-asset` and show the new unknown-route test fails; then temporarily remove `usd_price` from the `/price/<asset>` response and show its preservation test fails. Compile each changed Python file with Python 3.10 semantics.

## Deliverables

- `price_app.py` remove the retired route and its endpoint-specific metric emissions.
- `transformer.py` delete the stale local mapping copy.
- `tests/test_price_service_logging.py` replace the retired-route assertions with real app-client regression coverage.
- `README.md` (checklist: readme) describe the shipped behavior.
- `openspec/changes/price-service-transform-asset-disposition/specs/price-service-api-surface/spec.md` retain the approved API-surface requirement delta unchanged.
- `openspec/specs/price-service-api-surface/spec.md` add a substantive Purpose seed for archive sync.
- `openspec/changes/price-service-transform-asset-disposition/tasks.md` track this change's implementation and verification work.
