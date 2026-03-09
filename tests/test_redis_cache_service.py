import importlib
import inspect
import json
import logging
import sys
import time
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from redis.exceptions import (
    ConnectionError as RedisConnectionError,
    DataError,
    ResponseError,
    TimeoutError as RedisTimeoutError,
)

from pricing import redis_cache_service


@pytest.fixture(autouse=True)
def reset_cache():
    """Clear URL cache before each test."""
    redis_cache_service._cached_redis_url = None
    redis_cache_service._cached_url_timestamp = 0.0
    yield
    redis_cache_service._cached_redis_url = None
    redis_cache_service._cached_url_timestamp = 0.0


# --- 3.1: Cold cache calls get_redis_url(db=0) ---

@patch("pricing.redis_cache_service.aioredis")
@patch("pricing.redis_cache_service.get_redis_url",
       return_value="redis://192.168.1.252:6379/0")
async def test_cold_cache_calls_get_redis_url(mock_get_url, mock_aioredis):
    await redis_cache_service.get_redis_client()
    mock_get_url.assert_called_once_with(db=0)


# --- 3.2: Reuses cached URL within TTL ---

@patch("pricing.redis_cache_service.aioredis")
@patch("pricing.redis_cache_service.get_redis_url",
       return_value="redis://192.168.1.252:6379/0")
async def test_reuses_cached_url_within_ttl(mock_get_url, mock_aioredis):
    await redis_cache_service.get_redis_client()
    await redis_cache_service.get_redis_client()
    await redis_cache_service.get_redis_client()
    mock_get_url.assert_called_once()


# --- 3.3: Re-resolves after TTL expires ---

@patch("pricing.redis_cache_service.aioredis")
@patch("pricing.redis_cache_service.get_redis_url",
       return_value="redis://192.168.1.252:6379/0")
@patch("pricing.redis_cache_service.time")
async def test_re_resolves_after_ttl(mock_time, mock_get_url, mock_aioredis):
    mock_time.monotonic.side_effect = [0.0, 100.0, 400.0]
    await redis_cache_service.get_redis_client()
    await redis_cache_service.get_redis_client()
    assert mock_get_url.call_count == 1
    await redis_cache_service.get_redis_client()
    assert mock_get_url.call_count == 2


# --- 3.4: Cache invalidation on RedisConnectionError ---

@patch("pricing.redis_cache_service.get_redis_url",
       return_value="redis://192.168.1.252:6379/0")
@patch("pricing.redis_cache_service.aioredis")
async def test_connection_error_invalidates_cache(
        mock_aioredis, mock_get_url):
    mock_client = AsyncMock()
    mock_client.hgetall.side_effect = RedisConnectionError("refused")
    mock_aioredis.from_url.return_value = mock_client
    await redis_cache_service.get_cached_price_async("eth")
    assert redis_cache_service._cached_redis_url is None


# --- 3.5: Cache invalidation on RedisTimeoutError ---

@patch("pricing.redis_cache_service.get_redis_url",
       return_value="redis://192.168.1.252:6379/0")
@patch("pricing.redis_cache_service.aioredis")
async def test_timeout_error_invalidates_cache(
        mock_aioredis, mock_get_url):
    mock_client = AsyncMock()
    mock_client.hgetall.side_effect = RedisTimeoutError("timed out")
    mock_aioredis.from_url.return_value = mock_client
    await redis_cache_service.get_cached_price_async("eth")
    assert redis_cache_service._cached_redis_url is None


# --- 3.6: Cache invalidation on OSError ---

@patch("pricing.redis_cache_service.get_redis_url",
       return_value="redis://192.168.1.252:6379/0")
@patch("pricing.redis_cache_service.aioredis")
async def test_os_error_invalidates_cache(
        mock_aioredis, mock_get_url):
    mock_client = AsyncMock()
    mock_client.hgetall.side_effect = OSError("network unreachable")
    mock_aioredis.from_url.return_value = mock_client
    await redis_cache_service.get_cached_price_async("eth")
    assert redis_cache_service._cached_redis_url is None


# --- 3.7: NO invalidation on ResponseError ---

@patch("pricing.redis_cache_service.get_redis_url",
       return_value="redis://192.168.1.252:6379/0")
@patch("pricing.redis_cache_service.aioredis")
async def test_response_error_no_invalidation(
        mock_aioredis, mock_get_url):
    mock_client = AsyncMock()
    mock_client.hgetall.side_effect = ResponseError("WRONGTYPE")
    mock_aioredis.from_url.return_value = mock_client
    await redis_cache_service.get_cached_price_async("eth")
    assert redis_cache_service._cached_redis_url is not None


# --- 3.8: NO invalidation on DataError ---

@patch("pricing.redis_cache_service.get_redis_url",
       return_value="redis://192.168.1.252:6379/0")
@patch("pricing.redis_cache_service.aioredis")
async def test_data_error_no_invalidation(
        mock_aioredis, mock_get_url):
    mock_client = AsyncMock()
    mock_client.hgetall.side_effect = DataError("invalid data")
    mock_aioredis.from_url.return_value = mock_client
    await redis_cache_service.get_cached_price_async("eth")
    assert redis_cache_service._cached_redis_url is not None


# --- 3.9: Import-time guard ---

def test_import_guard_rejects_missing_db_param():
    """Reload the module with a get_redis_url lacking db param;
    verify ImportError is raised by the real guard logic."""
    def fake_get_redis_url():
        return "redis://localhost:6379/0"

    with patch.dict(sys.modules, {'aioredis': MagicMock()}):
        with patch(
            "cryptofund20x_services.db_layer_caller.get_redis_url",
            fake_get_redis_url
        ):
            mod_name = "pricing.redis_cache_service"
            saved = sys.modules.pop(mod_name, None)
            try:
                with pytest.raises(ImportError, match="lacks 'db' parameter"):
                    importlib.import_module(mod_name)
            finally:
                if saved is not None:
                    sys.modules[mod_name] = saved


# --- 3.10: Returns parsed hash data ---

@patch("pricing.redis_cache_service.get_redis_url",
       return_value="redis://192.168.1.252:6379/0")
@patch("pricing.redis_cache_service.aioredis")
async def test_get_cached_price_returns_hash_data(
        mock_aioredis, mock_get_url):
    mock_client = AsyncMock()
    now = datetime.now().isoformat()
    mock_client.hgetall.return_value = {
        'usd_price': '2000.5',
        'volume_last_24_hours': '1000000.0',
        'current_marketcap_usd': '50000000.0',
        'timestamp': now,
    }
    mock_aioredis.from_url.return_value = mock_client
    result = await redis_cache_service.get_cached_price_async("eth")
    assert result['usd_price'] == '2000.5'
    assert result['volume_last_24_hours'] == '1000000.0'
    assert result['current_marketcap_usd'] == '50000000.0'
    assert result['timestamp'] == now


# --- 3.11: Returns None when key does not exist ---

@patch("pricing.redis_cache_service.get_redis_url",
       return_value="redis://192.168.1.252:6379/0")
@patch("pricing.redis_cache_service.aioredis")
async def test_get_cached_price_returns_none_for_missing_key(
        mock_aioredis, mock_get_url):
    mock_client = AsyncMock()
    mock_client.hgetall.return_value = {}
    mock_aioredis.from_url.return_value = mock_client
    result = await redis_cache_service.get_cached_price_async("nonexistent")
    assert result is None


# --- 3.12: Timestamp freshness logging ---

@patch("pricing.redis_cache_service.get_redis_url",
       return_value="redis://192.168.1.252:6379/0")
@patch("pricing.redis_cache_service.aioredis")
async def test_timestamp_freshness_error_over_1_hour(
        mock_aioredis, mock_get_url, caplog):
    mock_client = AsyncMock()
    old_time = (datetime.now() - timedelta(hours=2)).isoformat()
    mock_client.hgetall.return_value = {
        'usd_price': '100',
        'volume_last_24_hours': '100',
        'current_marketcap_usd': '100',
        'timestamp': old_time,
    }
    mock_aioredis.from_url.return_value = mock_client
    with caplog.at_level(logging.ERROR, logger="redis_cache"):
        await redis_cache_service.get_cached_price_async("eth")
    assert any("more than 1 hour old" in r.message for r in caplog.records)


@patch("pricing.redis_cache_service.get_redis_url",
       return_value="redis://192.168.1.252:6379/0")
@patch("pricing.redis_cache_service.aioredis")
async def test_timestamp_freshness_warning_over_30_min(
        mock_aioredis, mock_get_url, caplog):
    mock_client = AsyncMock()
    old_time = (datetime.now() - timedelta(minutes=45)).isoformat()
    mock_client.hgetall.return_value = {
        'usd_price': '100',
        'volume_last_24_hours': '100',
        'current_marketcap_usd': '100',
        'timestamp': old_time,
    }
    mock_aioredis.from_url.return_value = mock_client
    with caplog.at_level(logging.WARNING, logger="redis_cache"):
        await redis_cache_service.get_cached_price_async("eth")
    assert any("more than 30 minutes old" in r.message for r in caplog.records)
