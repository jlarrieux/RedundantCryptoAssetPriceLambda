# PriceService API Surface Specification

## Purpose

Define PriceService's supported HTTP routes and behavior for requests to
routes it does not expose.
## Requirements
### Requirement: PriceService SHALL expose its supported GET route surface

PriceService SHALL expose `GET /` for the existing health response,
`GET /price/<asset>` for one cached price, `GET /prices` for batch cached
prices, and `GET /metrics` for Prometheus exposition. PriceService SHALL NOT
expose `GET /transform-asset`.

#### Scenario: Request to the retired transform route

- **WHEN** a client sends `GET /transform-asset?asset=BTC`
- **THEN** PriceService responds with HTTP 404
- **AND** the status, content type, and response body match those of another
  unregistered GET path
- **AND** the request does not produce application request, error, or latency
  metric samples for the `transform-asset` endpoint

