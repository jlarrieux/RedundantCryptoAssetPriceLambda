import logging
from unittest.mock import AsyncMock, Mock

import pytest

import price_app
import price_service
from price_service import PriceService


@pytest.fixture
def logger():
    """Provide an isolated PriceService logger without leaking global state."""
    logger = logging.getLogger("PriceService")
    original_handlers = logger.handlers[:]
    original_propagate = logger.propagate
    logger.handlers.clear()
    try:
        yield logger
    finally:
        logger.handlers.clear()
        logger.handlers.extend(original_handlers)
        logger.propagate = original_propagate


def test_price_service_logger_handler_count_is_stable(logger):
    PriceService()
    PriceService()

    assert len(logger.handlers) == 1
    assert logger.propagate is False


@pytest.mark.asyncio
async def test_price_service_hot_path_messages_are_debug(monkeypatch, logger):
    service = PriceService()
    service.logger.debug = Mock()
    service.logger.warning = Mock()
    service.logger.error = Mock()
    monkeypatch.setattr(
        price_service,
        "get_cached_prices_batch",
        AsyncMock(return_value=({"btc": {"usd_price": 1}}, ["eth"], ["sol"])),
    )
    monkeypatch.setattr(
        price_service.redis_cache_service,
        "get_cached_price_async",
        AsyncMock(return_value={"usd_price": 1}),
    )
    batch_increment = Mock()
    monkeypatch.setattr(
        price_service.PRICE_SERVICE_BATCH_REDIS_ERRORS,
        "inc",
        batch_increment,
    )

    await service.get_prices(["btc", "eth", "sol"])
    await service.get_single_price("btc")

    assert service.logger.debug.call_args_list == [
        (("Found cached price for btc",),),
        (("Fetching single price for btc",),),
        (("Found cached price for btc",),),
    ]
    service.logger.warning.assert_any_call(
        "Asset eth not found in redis cache in batch mode"
    )
    service.logger.warning.assert_any_call("Failed assets: ['eth', 'sol']")
    service.logger.error.assert_called_once_with(
        "Redis errors for assets in batch mode: ['sol']"
    )
    batch_increment.assert_called_once_with()


def test_price_service_failure_metrics_have_unambiguous_names():
    assert (
        price_service.PRICE_SERVICE_BATCH_REDIS_ERRORS._name
        == "price_service_batch_redis_errors"
    )
    assert (
        price_service.PRICE_SERVICE_SINGLE_CACHE_MISSES._name
        == "price_service_single_cache_miss"
    )


@pytest.mark.asyncio
async def test_known_unresolvable_single_miss_does_not_increment_failure(
    monkeypatch,
):
    service = PriceService()
    monkeypatch.setattr(
        price_service.redis_cache_service,
        "get_cached_price_async",
        AsyncMock(return_value=None),
    )
    increment = Mock()
    monkeypatch.setattr(
        price_service.PRICE_SERVICE_SINGLE_CACHE_MISSES,
        "inc",
        increment,
    )

    result = await service.get_single_price("jpeg")

    assert result is None
    increment.assert_not_called()


@pytest.mark.asyncio
async def test_unexpected_single_miss_still_increments_failure(monkeypatch):
    service = PriceService()
    monkeypatch.setattr(
        price_service.redis_cache_service,
        "get_cached_price_async",
        AsyncMock(return_value=None),
    )
    increment = Mock()
    monkeypatch.setattr(
        price_service.PRICE_SERVICE_SINGLE_CACHE_MISSES,
        "inc",
        increment,
    )

    result = await service.get_single_price("unexpected-token")

    assert result is None
    increment.assert_called_once_with()


@pytest.mark.asyncio
async def test_price_app_routes_and_unknown_route_behavior_are_unchanged(
    monkeypatch,
):
    debug = Mock()
    error = Mock()
    warning = Mock()
    monkeypatch.setattr(price_app.logger, "debug", debug)
    monkeypatch.setattr(price_app.logger, "error", error)
    monkeypatch.setattr(price_app.logger, "warning", warning)

    class FakePriceService:
        async def get_single_price(self, asset):
            return {
                "usd_price": 1,
                "volume_last_24_hours": 2,
                "current_marketcap_usd": 3,
                "observed_at": "2026-11-05T12:00:00+00:00",
            }

        async def get_prices(self, assets):
            prices = {asset: {"usd_price": 1} for asset in assets}
            return prices, []

    monkeypatch.setattr(price_app, "PriceService", FakePriceService)
    client = price_app.app.test_client()

    single = await client.get("/price/btc")
    assert single.status_code == 200
    assert await single.get_json() == {
        "asset": "btc",
        "usd_price": 1,
        "volume_last_24_hours": 2,
        "current_marketcap_usd": 3,
        "observed_at": "2026-11-05T12:00:00+00:00",
    }

    batch = await client.get("/prices?assets=btc,eth")
    assert batch.status_code == 200
    assert await batch.get_json() == {
        "prices": [
            {"btc": {"usd_price": 1}, "eth": {"usd_price": 1}},
            [],
        ]
    }

    root = await client.get("/")
    assert root.status_code == 200
    assert await root.get_data(as_text=True) == "OK"

    metrics = await client.get("/metrics")
    assert metrics.status_code == 200
    assert metrics.headers["Content-Type"] == price_app.CONTENT_TYPE_LATEST
    assert b"# HELP requests_total" in await metrics.get_data()

    def application_metric_samples():
        return tuple(
            sorted(
                (
                    sample.name,
                    tuple(sorted(sample.labels.items())),
                    sample.value,
                )
                for metric in (
                    price_app.REQUEST_COUNT,
                    price_app.ERROR_COUNT,
                    price_app.REQUEST_LATENCY,
                )
                for family in metric.collect()
                for sample in family.samples
            )
        )

    before_unknown_paths = application_metric_samples()
    removed_route = await client.get("/transform-asset?asset=BTC")
    another_unknown_route = await client.get("/path-that-does-not-exist")
    health_path = await client.get("/health")
    after_unknown_paths = application_metric_samples()

    assert removed_route.status_code == another_unknown_route.status_code == 404
    assert removed_route.headers["Content-Type"] == another_unknown_route.headers[
        "Content-Type"
    ]
    assert await removed_route.get_data() == await another_unknown_route.get_data()
    assert health_path.status_code == 404
    assert health_path.headers["Content-Type"] == another_unknown_route.headers[
        "Content-Type"
    ]
    assert await health_path.get_data() == await another_unknown_route.get_data()
    assert after_unknown_paths == before_unknown_paths
    assert not any(
        dict(labels).get("endpoint") == "transform-asset"
        for _, labels, _ in after_unknown_paths
    )

    invalid_single = await client.get("/price/%20")
    assert invalid_single.status_code == 400

    assert debug.call_args_list[0].args[0].startswith(
        "Request headers for /price: "
    )
    assert debug.call_args_list[1] == (("Fetching price for asset: btc",),)
    assert debug.call_args_list[2].args[0].startswith(
        "Request headers for /prices: "
    )
    assert debug.call_args_list[3].args[0] == (
        "Fetching prices for assets: ['btc', 'eth']"
    )
    error.assert_not_called()
    warning.assert_called_once_with("Empty or invalid asset provided.")
