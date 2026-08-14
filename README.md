# PriceService

PriceService is the Cryptofund20x HTTP service that reads cached cryptocurrency
prices from Redis and exposes single-asset and batch-price endpoints.

## Local verification

Install `requirements.txt` in the project environment, then run:

```bash
pytest -q
```

## Operations

The service exposes `/` for health and `/metrics` for Prometheus. Its Nomad job
is deployed from the homelab jobs checkout using `deploy.sh` with
`cryptofund20x/price-service.hcl`.

`PriceService()` is constructed by request handlers. Its named `PriceService`
logger is therefore configured defensively: construction keeps one local stream
handler and disables propagation, preventing repeated requests from multiplying
each log event.

Current project state and deployment evidence are maintained in [status.md](status.md).
