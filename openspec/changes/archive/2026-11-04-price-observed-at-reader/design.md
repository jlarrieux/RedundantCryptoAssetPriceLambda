# Design: return the producer observation time

## Data flow and existing behavior

PricePopulator writes `observed_at` in the same Redis `HSET` mapping as the
price fields and legacy `timestamp`. Its value is an ISO-8601 timestamp
generated from an aware UTC datetime with an explicit `+00:00` offset. It
records when the producer prepared the cache write, not when CoinGecko sampled
the data. The producer does not backfill existing hashes; an older or
unrefreshed hash can therefore lack the field until another successful write.

The two PriceService routes take different paths:

1. `GET /price/<asset>` reads a decoded Redis hash through
   `PriceService.get_single_price()`, but `price_app.price_single` builds a
   response from only `asset`, `usd_price`, `volume_last_24_hours`, and
   `current_marketcap_usd`. The hash's `observed_at` is currently discarded.
2. `GET /prices?assets=...` calls `PriceService.get_prices()` and returns the
   successful per-asset Redis hashes inside the established
   `{"prices": [success_dict, failed_list]}` response. It already passes
   `observed_at` and the legacy `timestamp` through when present. That behavior
   is currently incidental and unspecified.

The batch cache reader still parses the legacy `timestamp` for its existing
age logging. A hash with a missing or unparseable legacy `timestamp` follows
the existing errored-asset path. PricePopulator writes both timestamp fields
together, so a hash with `observed_at` but no `timestamp` is not a state the
producer writes. This change neither defines that state nor changes batch
error accounting.

## Response contract

### Present value

When the Redis hash contains the `observed_at` key, both endpoints expose its
stored value under the same response key. The value is copied verbatim: the
reader does not parse it, validate it, normalize it, or serialize a datetime
back to text. The producer's expected form is an aware UTC ISO-8601 string
ending in `+00:00`, but the reader does not enforce that format.

### Absent value

When an existing price hash lacks `observed_at`, both responses omit that key.
The single endpoint still returns its four existing fields. The batch asset
still appears in `success_dict` and keeps every field that exists in its hash.
Omission distinguishes unavailable observation evidence from a timestamp
value and matches the current batch pass-through behavior. Neither endpoint
returns JSON `null`, substitutes request time, or derives a value from the
legacy naive-local `timestamp`. A cache miss remains governed by the existing
404 or partial-failure behavior; this rule concerns a found hash without the
field.

### Malformed or stale value

An empty, malformed, or otherwise unexpected stored value is still a present
field and is passed through unchanged. PriceService will not add parsing that
can reject a request or invent a repair rule. The consumer can classify an
unusable value as malformed. A stale value is also returned unchanged; there
is no freshness rejection or stale status in this change. A reader can parse a
valid value using Python 3.10 `datetime.fromisoformat()` and calculate its
age. The response must not contain a request-time clock value in either the
present or absent case.

The same presence rule on both routes keeps their contracts aligned:

| Redis hash state | `GET /price/<asset>` | `GET /prices` success entry |
| --- | --- | --- |
| `observed_at` key present | Return its value unchanged | Raw hash retains its value unchanged |
| `observed_at` key absent | Omit the response key | Raw hash has no such key |

## Implementation shape

Add a conditional copy in `price_app.price_single` when constructing its
existing response dictionary: if `observed_at` is a key in the returned hash,
copy that value into the response. Keep the four existing fields and their
values unchanged.

Leave the `/prices` response construction and raw-hash batch path unchanged.
Do not rebuild each asset dictionary: doing so would create another field
allowlist and could accidentally remove fields the endpoint returns today,
including `timestamp`. The handlers do not share a response builder, so a
shared helper would add indirection to one route without reducing duplicated
logic. The conditional copy at the single response boundary is the smallest
change that keeps the per-route semantics explicit.

## Caller compatibility

A read-only search of checked-in Python source under
`/home/jeannius/programming/python/cryptofund20x` found the production
`/prices` URL construction in
`Cryptofund20xShared/cryptofund20x_services/price_client.py`. It reads the
first element of `loaded['prices']` and `_build_final_price_dict()` selects
only `usd_price`, `volume_last_24_hours`, and `current_marketcap_usd`; it does
not reject additional keys. `PriceInterface` uses this adapter for batch
reads, then stores either the numeric price or those same selected fields.
Ferengi uses `PriceInterface` through `protocols/fluid_arbitrum.py`,
`protocols/fluid_ethereum.py`, and `protocols/interfaces/token_creator.py`;
these callers do not inspect an exact Redis-hash key set. The batch endpoint's
additional `observed_at` key therefore does not change their current
projection. This change does not modify any sibling repository.

## Verification design

Add `tests/test_price_observed_at_api.py` and exercise the real Quart routes
through `app.test_client()`. Keep `PriceService` and the Redis cache service
logic in the path; replace only the Redis client factory with a fake client at
the Redis boundary. The fake single client returns a chosen hash, and the fake
batch pipeline returns chosen hashes. No test connects to Redis, MongoDB, or
the network.

Derive regression cases from the contract rather than the implementation:

- A single response with microseconds and `+00:00` returns the exact stored
  string and retains the four existing fields and values.
- A single response for a hash without `observed_at` omits the key and retains
  the four existing fields; it does not contain a request-time substitute.
- A batch response with one hash containing `observed_at` and another without
  it preserves the present value and the absent key respectively.
- The batch response remains `{"prices": [success_dict, failed_list]}` and
  retains the legacy `timestamp` in each successful hash.
- A stored `observed_at` from 15 minutes earlier is returned byte-for-byte;
  a test reader parses it with `datetime.fromisoformat()` and derives an age
  near 900 seconds. Use the explicit `+00:00` form supported by Python 3.10,
  not a trailing `Z`.
- Empty or malformed `observed_at` values pass through unchanged, and neither
  endpoint introduces freshness rejection.

The specified mutation checks will each be expected to fail a focused test:

| Mutant | Regression test that must fail |
| --- | --- |
| Omit `observed_at` from the single response | Single present-value exact-match test |
| Reformat or truncate the single value | Single present-value exact-match test |
| Substitute current time when the single hash lacks the field | Single absent-field omission test |
| Drop the batch legacy `timestamp` | Batch envelope and legacy-field preservation test |
| Change the batch outer response shape | Batch envelope and legacy-field preservation test |

## OpenSpec and README outputs

Add the new capability delta at
`specs/price-observation-time/spec.md`; do not modify either existing
capability. Give the capability a real Purpose and an `ADDED` requirement,
`PriceService SHALL expose the cached observation time`. That requirement
will state that both endpoints return the stored `observed_at` string without
alteration when present and omit the key when it is absent. Its scenarios will
cover the single route with a present value, the single route with an absent
value, batch success entries with present and absent values, and retention of
the existing batch envelope and legacy `timestamp`. The text will identify
the producer's expected aware UTC ISO-8601 `+00:00` form and producer-write
meaning, while making clear that the reader does not validate, derive, or use
the field for freshness decisions.

Add one short README section documenting the response fields for both
endpoints: the single route's four existing fields plus optional
`observed_at`, and the batch `{"prices": [success_dict, failed_list]}` shape
with successful Redis hash fields retained, including `timestamp`. State that
`observed_at` is copied from the producer's cache-write preparation time, is
expected to be an aware UTC ISO string with `+00:00`, is omitted if absent,
and leaves freshness decisions to the consumer.

## Verification commands

The focused scope is the new file `tests/test_price_observed_at_api.py` plus
`tests/test_redis_cache_service.py`. Run:

```text
python -m pytest -q -W ignore -o log_cli=false tests/test_price_observed_at_api.py tests/test_redis_cache_service.py
```

Run the complete suite twice, with no path argument, and compare both counts
with the kickoff baseline of 25 passed. Report each failure as pre-existing or
new and include its output:

```text
env -u PYTHONSAFEPATH python -m pytest -q -W ignore -o log_cli=false
env -u PYTHONSAFEPATH python -m pytest -q -W ignore -o log_cli=false -p no:randomly
```

Run the five mutation checks above one at a time and restore each mutant
before the next. Compile every changed Python file using Python 3.10 semantics
during Implementation.
