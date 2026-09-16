import asyncio
import logging
from typing import List, Dict, Any

from cryptofund20x_misc.custom_formatter import CustomFormatter
from prometheus_client import Counter, Histogram

from pricing import redis_cache_service
from pricing.redis_cache_service import get_cached_prices_batch

# Metrics
PRICE_SERVICE_BATCH_REDIS_ERRORS = Counter(
    'price_service_batch_redis_errors_total',
    'Number of Redis errors while fetching a batch',
)
PRICE_SERVICE_SINGLE_CACHE_MISSES = Counter(
    'price_service_single_cache_miss_total',
    'Number of unexpected single-asset cache misses',
)
PRICE_SERVICE_REQUEST_TIME = Histogram('price_service_request_duration_seconds',
                                       'Time spent processing complete request')

# These assets are permanently unresolvable on CoinGecko. They remain valid
# caller inputs, but expected cache misses must not inflate the unexpected-
# failure signal.
KNOWN_UNRESOLVABLE_ASSETS = frozenset({
    'btrfly', 'cnc', 'dpx', 'jpeg', 'rdpx',
})


class PriceService:
    def __init__(self):
        # Setup logging
        self.logger = logging.getLogger("PriceService")
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(CustomFormatter())
            self.logger.addHandler(handler)
        self.logger.propagate = False

    async def get_prices(self, assets: List[str]) -> tuple[dict[str, dict], list[str]]:
        """Get prices for a list of assets using Redis pipeline."""
        with PRICE_SERVICE_REQUEST_TIME.time():
            success_dict, missed_assets, errored_assets = await get_cached_prices_batch(assets)

            for asset in success_dict:
                self.logger.debug(f"Found cached price for {asset}")

            for asset in missed_assets:
                self.logger.warning(f"Asset {asset} not found in redis cache in batch mode")

            if errored_assets:
                self.logger.error(f"Redis errors for assets in batch mode: {errored_assets}")
                PRICE_SERVICE_BATCH_REDIS_ERRORS.inc()

            failed_assets = missed_assets + errored_assets
            if failed_assets:
                self.logger.warning(f"Failed assets: {failed_assets}")

            return success_dict, failed_assets

    async def get_single_price(self, asset: str) -> dict | tuple[None, str]:
        """Get price for a single asset with fallback and error handling."""
        with PRICE_SERVICE_REQUEST_TIME.time():
            self.logger.debug(f"Fetching single price for {asset}")
            try:
                cached_data = await redis_cache_service.get_cached_price_async(asset)
                if cached_data:
                    self.logger.debug(f"Found cached price for {asset}")
                    return cached_data
                self.logger.debug(f"Asset {asset} not found in redis cache")
                if asset in KNOWN_UNRESOLVABLE_ASSETS:
                    self.logger.warning(
                        f"Known unresolvable asset {asset} missed in redis cache"
                    )
                else:
                    PRICE_SERVICE_SINGLE_CACHE_MISSES.inc()
                return None
            except Exception as e:
                self.logger.error(f"Error fetching price for {asset}: {str(e)}")

    @staticmethod
    def _create_result_dict(asset: str, price: float, volume: float, marketcap: float) -> Dict:
        return {
            "asset": asset,
            "usd_price": price,
            "volume_last_24_hours": volume,
            "current_marketcap_usd": marketcap
        }


if __name__ == '__main__':
    pr = PriceService()
    result = asyncio.run(pr.get_single_price("sdai"))
    print(result)
    print(f"asset: {result['asset']}\t usd_price: {result['usd_price']}")
