import json
import logging
from datetime import datetime
from typing import Dict, Optional

import aioredis
from cryptofund20x_misc.custom_formatter import CustomFormatter

# Constants
REDIS_HOST = 'redis://192.168.1.253:6379'
PRICE_KEY_PREFIX = "price:"

# Setup logging
logger = logging.getLogger("redis_cache")
handler = logging.StreamHandler()
handler.setFormatter(CustomFormatter())
logger.addHandler(handler)


async def get_redis_client():
    return aioredis.from_url(REDIS_HOST, decode_responses=True, db=0)


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
                logger.error(f"Cache item for {asset} is more than 1 hour old.")
            elif time_diff.total_seconds() > 1800:
                logger.warning(f"Cache item for {asset} is more than 30 minutes old.")

            return cached_data
        else:
            logger.warning(f"No cached data found for {asset}.")
            return None
    except Exception as e:
        logger.error(f"Error getting cached price for {asset}: {str(e)}")
        return None

