# Return the stored observation time from PriceService

## Why

PricePopulator now writes `observed_at` into each price hash as an ISO-8601 UTC timestamp with an explicit `+00:00` offset. It records when the producer prepared the Redis cache write, not when CoinGecko sampled the data. PriceService's single-price endpoint currently selects only four named fields and omits this value, so consumers cannot calculate the age of a cached price from that response.

The batch endpoint behaves differently: it returns the raw Redis hash inside its existing `{"prices": [success_dict, failed_list]}` envelope. Since the producer rollout, `observed_at` already appears there when present, but that pass-through is accidental and unspecified. This change will make it an explicit contract while preserving that envelope and every field the endpoint returns today, including the legacy `timestamp`.

## What changes

- Return the stored `observed_at` string without parsing or reformatting it from `GET /price/<asset>` when the Redis hash contains the field.
- Define absence consistently for both endpoints: omit the `observed_at` response key when the Redis hash lacks it. Do not return `null`, synthesize a request-time value, or derive a value from `timestamp`.
- Keep `/prices` returning its raw per-asset Redis hashes and its current outer response shape. Specify that `observed_at` is present verbatim when present in the hash and absent when absent; retain all other returned hash fields, including `timestamp`.
- Add an `ADDED` requirement under a new `price-observation-time` capability rather than modifying either existing capability.
- Add app-level regression tests using Quart's test client and a fake Redis boundary, and document the endpoint contracts in README.md.

## Contract decisions and compatibility

**Absent field.** Both endpoints omit `observed_at` when the Redis hash has no such key. The response still contains the price data under the existing success behavior. Omission makes lack of observation evidence unambiguous to clients and is consistent with the batch endpoint's existing raw-hash behavior. A client can classify the missing field as unavailable without confusing it with a real timestamp. PriceService will not substitute the current time or use the naive-local `timestamp`.

**Batch response.** `/prices` remains a raw-hash pass-through. Today it returns `observed_at` where the producer has written it, plus fields such as `timestamp`; this change specifies and tests that behavior. A found hash without `observed_at` remains in `success_dict` and simply lacks that key. The established `{"prices": [success_dict, failed_list]}` shape and per-asset failure behavior remain unchanged.

**Malformed stored values.** PriceService passes any stored `observed_at` value through unchanged, including an empty or non-ISO string. The service does not parse, validate, or normalize this field on the request path; the consumer decides whether the value is usable or malformed. This preserves the producer's exact serialized value and avoids request failures or invented semantics. The producer's contract expects an aware UTC ISO-8601 string ending in `+00:00`, but the reader does not repair values that violate that format.

**Implementation location.** The endpoint handlers do not share a response builder. Add a conditional copy to the single endpoint's existing response dictionary. Leave the batch path as its raw hash pass-through. A shared helper would add indirection to the batch path without changing its data, and building a new batch dictionary risks dropping existing hash fields.

**Existing callers.** A read-only search of the sibling Cryptofund20x repositories found the sole production `/prices` URL construction in `Cryptofund20xShared/cryptofund20x_services/price_client.py`. It reads `loaded['prices'][0]` and its `_build_final_price_dict()` explicitly selects `usd_price`, `volume_last_24_hours`, and `current_marketcap_usd`; additional fields, including `timestamp` and `observed_at`, are ignored rather than rejected. `PriceInterface` calls that adapter for batch reads and stores either the numeric price or those same three selected fields. Ferengi consumes `PriceInterface` through `protocols/fluid_arbitrum.py`, `protocols/fluid_ethereum.py`, and `protocols/interfaces/token_creator.py`; these paths likewise do not validate an exact Redis-hash key set. No other direct `/prices` URL construction was found in the checked-in Python source under the sibling project directory. The additive field therefore leaves these consumers' current projections unchanged, while a future direct reader can use it.

The producer writes `timestamp` and `observed_at` in the same HSET mapping. The existing batch behavior for a missing or unparseable legacy `timestamp` remains unchanged: that asset follows the current error path. This change does not define a hash containing `observed_at` but no legacy `timestamp`, nor does it alter any cache-miss or batch error accounting.

## Scope

In scope:

- The single and batch response contracts for `observed_at`, including the absent and malformed-value behavior above.
- A new capability spec, Quart app-level regression tests, and one short README section.
- Verification of verbatim values, old-hash absence, stale values, legacy batch fields, and unchanged response shape.

Out of scope:

- PricePopulator or any other repository, the Redis connection code, Cerberus, `/transform-asset`, cache-miss behavior, batch error accounting, metrics, expiry, and stale-price rejection.
- Any freshness policy. The response exposes the producer timestamp; consumers decide whether a price is fresh enough.
- Changes to existing fields, field values, or the `/prices` response shape.
- Build, publication, deployment, status.md, or version-file changes.

## Verification approach

The new tests will exercise both HTTP endpoints through `app.test_client`, replacing Redis at its service boundary so no test contacts Redis, MongoDB, or the network. Coverage will include exact string equality for a present timestamp with microseconds and `+00:00`; omission when absent with the single endpoint's four existing fields unchanged; batch responses with one present and one absent value; preservation of the batch envelope and legacy `timestamp`; and an old timestamp 15 minutes in the past that remains unchanged and can be parsed with Python 3.10's `datetime.fromisoformat()` to derive its age. Tests will assert that an absent value does not become a request-time clock value.

The focused verification scope will be the new test file plus `tests/test_redis_cache_service.py`. The full suite will run twice using the required commands, including one run with `-p no:randomly`. The five requested mutants will be applied one at a time and restored between runs: omit the single field, reformat it, synthesize a value when absent, drop the batch legacy timestamp, and alter the batch outer shape. Each mutant must fail a named regression test.
