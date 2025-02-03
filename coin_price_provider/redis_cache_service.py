import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import redis
from cryptofund20x_misc.custom_formatter import CustomFormatter

# Setup Redis client
redis_client = redis.Redis(host='192.168.1.253', port=6379, decode_responses=True, db=0)

# Constants
PRICE_KEY_PREFIX = "price:"
COIN_LIST_KEY = "coingecko:coin_list"
PRICE_EXPIRE_TIME = 180  # 3 minutes
COIN_LIST_EXPIRE_TIME = 3600  # 1 hour

# Setup logging
logger = logging.getLogger("redis_cache")
handler = logging.StreamHandler()
handler.setFormatter(CustomFormatter())
logger.addHandler(handler)


async def store_price(asset: str, price: float, volume: float, marketcap: float) -> bool:
    """Store asset price data in Redis."""
    try:
        data = {
            'price': str(price),
            'volume': str(volume),
            'marketcap': str(marketcap),
            'timestamp': str(datetime.now())
        }

        key = f"{PRICE_KEY_PREFIX}{asset}"
        await redis_client.hset(key, mapping=data)
        await redis_client.expire(key, PRICE_EXPIRE_TIME)

        logger.info(f"Stored price data for {asset}")
        return True

    except Exception as e:
        logger.error(f"Error storing price for {asset}: {str(e)}")
        return False


async def get_cached_price_async(asset: str) -> Optional[Tuple[float, float, float]]:
    """Retrieve cached price data for an asset."""
    try:
        key = f"{PRICE_KEY_PREFIX}{asset}"
        data = redis_client.hgetall(key)

        if not data:
            return None

        return (
            float(data['price']),
            float(data['volume']),
            float(data['marketcap'])
        )

    except Exception as e:
        logger.error(f"Error retrieving price for {asset}: {str(e)}")
        return None


async def store_coin_list(coin_list: List[Dict]) -> bool:
    """Store Coingecko coin list in Redis."""
    try:
        await redis_client.setex(COIN_LIST_KEY, COIN_LIST_EXPIRE_TIME, json.dumps(coin_list))
        logger.info("Stored coin list")
        return True

    except Exception as e:
        logger.error(f"Error storing coin list: {str(e)}")
        return False


async def get_cached_coin_list() -> Optional[List[Dict]]:
    """Retrieve cached coin list."""
    try:
        cached_data = await redis_client.get(COIN_LIST_KEY)
        if not cached_data:
            return None

        return json.loads(cached_data)

    except Exception as e:
        logger.error(f"Error retrieving coin list: {str(e)}")
        return None
