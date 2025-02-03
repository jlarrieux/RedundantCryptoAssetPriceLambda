import json
import logging
from datetime import datetime
from typing import Dict, List, Optional

import aioredis
from cryptofund20x_misc.custom_formatter import CustomFormatter

# Constants
REDIS_HOST = 'redis://192.168.1.253:6379'
PRICE_KEY_PREFIX = "price:"
COIN_LIST_KEY = "coingecko:coin_list"
PRICE_EXPIRE_TIME = 360  # 6 minutes

# Setup logging
logger = logging.getLogger("redis_cache")
handler = logging.StreamHandler()
handler.setFormatter(CustomFormatter())
logger.addHandler(handler)


async def get_redis_client():
    return aioredis.from_url(REDIS_HOST, decode_responses=True, db=0)


async def store_price(asset: str, price: float, volume: float, marketcap: float) -> bool:
    """Store asset price data in Redis."""
    try:
        redis_client = await get_redis_client()
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


async def store_all_prices(price_data_list: List[Dict]) -> bool:
    """Store all prices as a hash map in Redis."""
    try:
        redis_client = await get_redis_client()

        # Create mapping of asset -> price data
        price_map = {item['asset']: json.dumps(item) for item in price_data_list}

        # Store everything in a single hash
        await redis_client.hset("crypto_prices", mapping=price_map)

        # Set expiration for the entire hash
        await redis_client.expire("crypto_prices", PRICE_EXPIRE_TIME)

        logger.info(f"Stored prices for {len(price_data_list)} assets")
        return True

    except Exception as e:
        logger.error(f"Error storing prices: {str(e)}")
        return False


async def get_cached_price_async(asset: str) -> Optional[Dict]:
    """Get cached price for a single asset from the hash map."""
    try:
        redis_client = await get_redis_client()
        cached_data = await redis_client.hget("crypto_prices", asset)
        if cached_data:
            return json.loads(cached_data)
        return None
    except Exception as e:
        logger.error(f"Error getting cached price for {asset}: {str(e)}")
        return None


async def get_all_cached_prices() -> Dict:
    """Get all cached prices at once."""
    try:
        redis_client = await get_redis_client()
        all_prices = await redis_client.hgetall("crypto_prices")
        return {k: json.loads(v) for k, v in all_prices.items()}
    except Exception as e:
        logger.error(f"Error getting all cached prices: {str(e)}")
        return {}


async def get_cached_coin_list() -> Optional[List[Dict]]:
    """Retrieve cached coin list."""
    try:
        redis_client = await get_redis_client()
        cached_data = await redis_client.get(COIN_LIST_KEY)
        if not cached_data:
            return None

        return json.loads(cached_data)

    except Exception as e:
        logger.error(f"Error retrieving coin list: {str(e)}")
        return None


async def store_coin_list(coin_list: List[Dict]) -> bool:
    """Store coin list in Redis with proper expiration."""
    try:
        redis_client = await get_redis_client()
        await redis_client.set(COIN_LIST_KEY, json.dumps(coin_list), ex=PRICE_EXPIRE_TIME)
        logger.info("coin list saved!")
        return True
    except Exception as e:
        logger.error(f"Error storing coin list: {str(e)}")
        return False
