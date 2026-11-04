# price-observation-time Specification

## Purpose

PriceService exposes the producer's cached price-write observation time so
consumers can calculate its age while making their own freshness decisions.
## Requirements
### Requirement: PriceService SHALL expose the cached observation time

When a Redis price hash contains the `observed_at` field, PriceService SHALL
return its stored string unchanged as `observed_at` from both
`GET /price/<asset>` and each successful asset entry in `GET /prices`. The
producer's expected value is an ISO-8601 timestamp for an aware UTC instant
with an explicit `+00:00` offset. It records when PricePopulator prepared the
cache write, not when CoinGecko sampled the data. PriceService SHALL NOT parse,
reformat, derive, or validate the value, and SHALL NOT use it to reject or mark
a price stale.

When a Redis price hash has no `observed_at` field, both endpoints SHALL omit
that response key. PriceService SHALL NOT return JSON `null`, substitute the
request-time clock, or derive a value from the legacy `timestamp` field. This
absence behavior SHALL NOT change whether a found hash is returned
successfully.

The single-price response SHALL retain its existing `asset`, `usd_price`,
`volume_last_24_hours`, and `current_marketcap_usd` fields and values. The
batch response SHALL retain its `{"prices": [success_dict, failed_list]}`
shape and every field already present in successful Redis hashes, including
the legacy `timestamp`. Existing batch handling of hashes with a missing or
unparseable legacy `timestamp` SHALL remain unchanged.

#### Scenario: Single-price response includes a present observation time

- **WHEN** `GET /price/<asset>` reads a hash containing `observed_at`
- **THEN** the response SHALL contain the exact stored string as
  `observed_at`
- **AND** the four existing single-price fields SHALL retain their names and
  values

#### Scenario: Single-price response omits an absent observation time

- **WHEN** `GET /price/<asset>` reads a hash without `observed_at`
- **THEN** the successful response SHALL omit `observed_at`
- **AND** the response SHALL retain its four existing fields and SHALL NOT
  contain a request-time substitute

#### Scenario: Batch response preserves present and absent observation times

- **WHEN** `GET /prices?assets=...` returns successful hashes where one
  contains `observed_at` and another does not
- **THEN** the first success entry SHALL retain the exact stored string
- **AND** the second success entry SHALL omit the `observed_at` key
- **AND** both found assets SHALL remain in `success_dict`

#### Scenario: Batch response retains its envelope and legacy timestamp

- **WHEN** `GET /prices?assets=...` returns successful cached hashes
- **THEN** the response SHALL retain the `{"prices": [success_dict,
  failed_list]}` shape
- **AND** each success entry SHALL retain the legacy `timestamp` and every
  other field present in its Redis hash

#### Scenario: Malformed or stale observation time is returned unchanged

- **WHEN** a successful Redis hash contains an empty, malformed, or stale
  `observed_at` string
- **THEN** the endpoint SHALL return that string unchanged
- **AND** the endpoint SHALL NOT validate it, reject the price, or replace it
  with request time

