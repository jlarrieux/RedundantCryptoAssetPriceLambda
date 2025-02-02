import json
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from cryptofund20x_services import url_service
from prometheus_client import REGISTRY

from coin_price_provider.coin_gecko_price_provider import CoingeckoClient

# Update these imports based on your project structure

# Mock coin list response from Coingecko
MOCK_COIN_LIST = [
    {"id": "bitcoin", "symbol": "btc", "name": "Bitcoin"},
    {"id": "ethereum", "symbol": "eth", "name": "Ethereum"},
    {"id": "magic", "symbol": "magic", "name": "Magic"},
]

# Mock price response from Coingecko
MOCK_PRICE_RESPONSE = {
    "ethereum": {
        "usd": 2500.0,
        "usd_24h_vol": 1000000.0,
        "usd_market_cap": 300000000.0
    }
}


def clean_prometheus_registry():
    """Clean up any existing metrics from the registry."""
    collectors = list(REGISTRY._collector_to_names.keys())
    for collector in collectors:
        REGISTRY.unregister(collector)


@pytest.fixture(autouse=True)
def reset_prometheus():
    """Fixture to reset Prometheus registry before each test."""
    clean_prometheus_registry()
    yield


# And update the fixture in your test file:
@pytest.fixture
async def coingecko_client():
    """Fixture to create a CoingeckoClient instance for each test."""
    client = CoingeckoClient()
    try:
        yield client
    finally:
        # Cleanup
        await url_service.close_session()


# Also add this configuration to conftest.py
def pytest_configure(config):
    config.addinivalue_line(
        "markers", "asyncio: mark test as async"
    )


@pytest.mark.asyncio
async def test_get_full_coin_list_caching(coingecko_client):
    """Test that coin list caching works correctly."""
    with patch('cryptofund20x_services.url_service.open_url_async') as mock_url:
        # Set up mock response
        mock_url.return_value = json.dumps(MOCK_COIN_LIST)

        # First call should fetch from API
        result1 = await coingecko_client.get_full_coin_list()
        assert mock_url.call_count == 1
        assert result1 == MOCK_COIN_LIST

        # Second call should use cache
        result2 = await coingecko_client.get_full_coin_list()
        assert mock_url.call_count == 1  # Still 1, didn't call API again
        assert result2 == MOCK_COIN_LIST

        # Wait for cache to expire
        coingecko_client._last_coin_list_update = (
                datetime.now() - coingecko_client.coin_list_cache_duration - timedelta(minutes=1)
        )

        # Third call should fetch fresh data
        result3 = await coingecko_client.get_full_coin_list()
        assert mock_url.call_count == 2
        assert result3 == MOCK_COIN_LIST


@pytest.mark.asyncio
async def test_get_single_price(coingecko_client):
    """Test fetching single price with mocked responses."""
    with patch('cryptofund20x_services.url_service.open_url_async') as mock_url, \
            patch('coin_price_provider.db_cache_service.get_cached_price_async') as mock_cache_get, \
            patch('coin_price_provider.db_cache_service.store_price') as mock_cache_store:
        # Setup mocks
        mock_cache_get.return_value = None  # No cached data
        mock_url.side_effect = [
            json.dumps(MOCK_COIN_LIST),  # First call for coin list
            json.dumps(MOCK_PRICE_RESPONSE)  # Second call for price data
        ]

        # Test successful price fetch
        result = await coingecko_client.get_single_price("eth")
        assert result is not None
        price, volume, market_cap = result
        assert price == 2500.0
        assert volume == 1000000.0
        assert market_cap == 300000000.0

        # Verify cache interaction
        mock_cache_store.assert_called_once()


@pytest.mark.asyncio
async def test_get_batch_prices(coingecko_client):
    """Test fetching multiple prices in batch."""
    with patch('cryptofund20x_services.url_service.open_url_async') as mock_url, \
            patch('coin_price_provider.db_cache_service.get_cached_price_async') as mock_cache_get, \
            patch('coin_price_provider.db_cache_service.store_price') as mock_cache_store:
        # Setup mocks
        mock_cache_get.return_value = None
        mock_url.side_effect = [
            json.dumps(MOCK_COIN_LIST),
            json.dumps({
                "bitcoin": {
                    "usd": 35000.0,
                    "usd_24h_vol": 2000000.0,
                    "usd_market_cap": 600000000.0
                },
                "ethereum": {
                    "usd": 2500.0,
                    "usd_24h_vol": 1000000.0,
                    "usd_market_cap": 300000000.0
                }
            })
        ]

        # Test batch price fetch
        results = await coingecko_client.get_batch_prices(["btc", "eth"])
        assert len(results) == 2
        assert all(result is not None for result in results.values())

        # Verify cache interactions
        assert mock_cache_store.call_count == 2  # Called for each asset


@pytest.mark.asyncio
async def test_error_handling(coingecko_client):
    """Test error handling scenarios."""
    with patch('cryptofund20x_services.url_service.open_url_async') as mock_url:
        # Test invalid JSON response
        mock_url.return_value = "invalid json"
        with pytest.raises(Exception) as exc_info:
            await coingecko_client.get_full_coin_list()
        assert "Invalid response format" in str(exc_info.value)

        # Test network error
        mock_url.side_effect = Exception("Network error")
        with pytest.raises(Exception) as exc_info:
            await coingecko_client.get_single_price("eth")
        assert "Coingecko API error" in str(exc_info.value)


@pytest.mark.asyncio
async def test_cache_interaction():
    """Test interaction with cache service."""
    client = CoingeckoClient()  # Create client directly in the test
    cached_data = (2400.0, 900000.0, 290000000.0)

    try:
        with patch('coin_price_provider.db_cache_service.get_cached_price_async') as mock_cache_get:
            # Test cache hit
            mock_cache_get.return_value = cached_data
            result = await client.get_single_price("eth")
            assert result == cached_data

            # Test cache miss
            mock_cache_get.return_value = None
            with patch('cryptofund20x_services.url_service.open_url_async') as mock_url:
                mock_url.side_effect = [
                    json.dumps(MOCK_COIN_LIST),
                    json.dumps(MOCK_PRICE_RESPONSE)
                ]
                result = await client.get_single_price("eth")
                assert result is not None
                assert result != cached_data  # Should be fresh data
    finally:
        await url_service.close_session()
