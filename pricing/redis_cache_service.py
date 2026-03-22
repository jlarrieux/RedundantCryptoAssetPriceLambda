import inspect
import logging
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import aioredis
from cryptofund20x_misc.custom_formatter import CustomFormatter
from cryptofund20x_services.db_layer_caller import get_redis_url
from redis.exceptions import (
    ConnectionError as RedisConnectionError,
    ResponseError as RedisResponseError,
    TimeoutError as RedisTimeoutError,
)

# Import-time version guard
_sig = inspect.signature(get_redis_url)
if 'db' not in _sig.parameters:
    raise ImportError(
        "Installed Cryptofund20xShared is too old: get_redis_url() "
        "lacks 'db' parameter. Requires >= 0.9.0."
    )

# Constants
PRICE_KEY_PREFIX = "price:"

# URL cache (TTL = 300s / 5 minutes — no scheduler cadence to match;
# service is purely request-driven)
_cached_redis_url = None
_cached_url_timestamp = 0.0
_URL_TTL = 300

# Setup logging
logger = logging.getLogger("redis_cache")
handler = logging.StreamHandler()
handler.setFormatter(CustomFormatter())
logger.addHandler(handler)


def _invalidate_url_cache():
    global _cached_redis_url, _cached_url_timestamp
    _cached_redis_url = None
    _cached_url_timestamp = 0.0


async def get_redis_client():
    global _cached_redis_url, _cached_url_timestamp
    now = time.monotonic()
    if _cached_redis_url is None or (now - _cached_url_timestamp) >= _URL_TTL:
        _cached_redis_url = get_redis_url(db=0)
        _cached_url_timestamp = now
    return aioredis.from_url(_cached_redis_url, decode_responses=True, db=0)


async def get_cached_price_async(asset: str) -> Optional[Dict]:
    """Get cached price for a single asset from the hash map."""
    try:
        redis_client = await get_redis_client()
        key = f"{PRICE_KEY_PREFIX}{asset}"
        logger.info(f"About to retrieve using key: {key}")
        cached_data = await redis_client.hgetall(key)

        if cached_data:
            logger.info(f"got data: {cached_data}")
            cached_time = datetime.fromisoformat(cached_data.get('timestamp'))
            current_time = datetime.now()
            time_diff = current_time - cached_time

            if time_diff.total_seconds() > 3600:
                logger.error(
                    f"Cache item for {asset} is more than 1 hour old."
                )
            elif time_diff.total_seconds() > 1800:
                logger.warning(
                    f"Cache item for {asset} is more than 30 minutes old."
                )

            return cached_data
        else:
            logger.warning(f"No cached data found for {asset}.")
            return None
    except (RedisConnectionError, RedisTimeoutError, OSError) as e:
        _invalidate_url_cache()
        logger.error(f"Error getting cached price for {asset}: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Error getting cached price for {asset}: {str(e)}")
        return None


async def get_cached_prices_batch(
    assets: List[str],
) -> Tuple[Dict[str, Dict], List[str], List[str]]:
    """Get cached prices for multiple assets using a Redis pipeline."""
    success_dict: Dict[str, Dict] = {}
    missed_assets: List[str] = []
    errored_assets: List[str] = []

    try:
        redis_client = await get_redis_client()
        keys = [f"{PRICE_KEY_PREFIX}{asset}" for asset in assets]

        async with redis_client.pipeline(transaction=False) as pipe:
            for key in keys:
                pipe.hgetall(key)
            results = await pipe.execute()

        for asset, result in zip(assets, results):
            if isinstance(result, (RedisResponseError, Exception)):
                logger.error(f"Redis error for {asset}: {result}")
                errored_assets.append(asset)
                continue

            if not result:
                logger.warning(f"No cached data found for {asset}.")
                missed_assets.append(asset)
                continue

            try:
                cached_time = datetime.fromisoformat(result.get('timestamp'))
                current_time = datetime.now()
                time_diff = current_time - cached_time

                if time_diff.total_seconds() > 3600:
                    logger.error(
                        f"Cache item for {asset} is more than 1 hour old."
                    )
                elif time_diff.total_seconds() > 1800:
                    logger.warning(
                        f"Cache item for {asset} is more than 30 minutes old."
                    )
            except (TypeError, ValueError) as e:
                logger.error(
                    f"Invalid timestamp for {asset}: {e}"
                )
                errored_assets.append(asset)
                continue

            success_dict[asset] = result

    except (RedisConnectionError, RedisTimeoutError, OSError) as e:
        _invalidate_url_cache()
        logger.error(f"Pipeline-level Redis failure: {str(e)}")
        errored_assets = list(assets)
        success_dict = {}
        missed_assets = []
    except Exception as e:
        logger.error(f"Unexpected error in batch price lookup: {str(e)}")
        errored_assets = list(assets)
        success_dict = {}
        missed_assets = []

    return success_dict, missed_assets, errored_assets
