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
        price_service.PRICE_SERVICE_FAILURE,
        "labels",
        Mock(return_value=Mock(inc=increment)),
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
        price_service.PRICE_SERVICE_FAILURE,
        "labels",
        Mock(return_value=Mock(inc=increment)),
    )

    result = await service.get_single_price("unexpected-token")

    assert result is None
    increment.assert_called_once_with()


@pytest.mark.asyncio
async def test_price_app_hot_path_messages_are_debug_and_errors_are_unchanged(
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
            }

        async def get_prices(self, assets):
            return {asset: {} for asset in assets}

    monkeypatch.setattr(price_app, "PriceService", FakePriceService)
    client = price_app.app.test_client()

    assert (await client.get("/transform-asset?asset=BTC")).status_code == 200
    assert (await client.get("/price/btc")).status_code == 200
    assert (await client.get("/prices?assets=btc,eth")).status_code == 200
    assert (await client.get("/transform-asset")).status_code == 400
    assert (await client.get("/price/%20")).status_code == 400

    assert debug.call_args_list == [
        (("Transforming asset BTC",),),
        (("Fetching price for asset: btc",),),
        (("Fetching prices for assets: ['btc', 'eth']",),),
    ]
    error.assert_called_once_with("No asset specified")
    warning.assert_called_once_with("Empty or invalid asset provided.")
