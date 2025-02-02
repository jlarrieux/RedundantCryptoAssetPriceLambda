import asyncio
import logging
from typing import List, Dict, Tuple

from cryptofund20x_misc.custom_formatter import CustomFormatter
from prometheus_client import Counter, Histogram

from coin_price_provider.coin_gecko_price_provider import CoingeckoClient
from coin_price_provider.messari_price_provider import MessariClient

# Metrics
PRICE_SERVICE_BATCH_FAILURE = Counter('price_service_complete_batch_failures_total',
                                      'Number of times all APIs failed for a batch')
PRICE_SERVICE_FALLBACK_ATTEMPTS = Counter('price_service_fallback_attempts_total',
                                         'Number of times fallback to Messari was attempted')
PRICE_SERVICE_REQUEST_TIME = Histogram('price_service_request_duration_seconds',
                                      'Time spent processing complete request')

class PriceService:
    def __init__(self):
        self.coingecko = CoingeckoClient()
        self.messari = MessariClient()

        # Setup logging
        self.logger = logging.getLogger("PriceService")
        handler = logging.StreamHandler()
        handler.setFormatter(CustomFormatter())
        self.logger.addHandler(handler)

    async def get_prices(self, assets: List[str]) -> Tuple[List[Dict], List[Tuple[str, str]]]:
        """Get prices for a list of assets with fallback and error handling."""
        with PRICE_SERVICE_REQUEST_TIME.time():
            result_list = []
            failed_assets = []

            # Try Coingecko first for all assets
            self.logger.info(f"Attempting to fetch {len(assets)} assets from Coingecko")
            coingecko_results = await self.coingecko.get_batch_prices(assets)

            # Process Coingecko results
            for asset in assets:
                if asset in coingecko_results and coingecko_results[asset] is not None:
                    result_list.append(self._create_result_dict(asset, *coingecko_results[asset]))
                else:
                    failed_assets.append((asset, "Not found in Coingecko"))

            # Try Messari as fallback for failed assets
            if failed_assets:
                self.logger.info(f"Attempting Messari fallback for {len(failed_assets)} assets")
                PRICE_SERVICE_FALLBACK_ATTEMPTS.inc()
                still_failed = []

                for asset, _ in failed_assets:
                    try:
                        price_data = await self.messari.get_price(asset)
                        if price_data:
                            result_list.append(self._create_result_dict(asset, *price_data))
                        else:
                            still_failed.append((asset, "No data from Messari"))
                    except Exception as e:
                        self.logger.error(f"Messari fallback failed for {asset}: {str(e)}")
                        still_failed.append((asset, f"Messari error: {str(e)}"))

                failed_assets = still_failed

            if failed_assets and not result_list:
                self.logger.error("Complete batch failure - no prices retrieved from any source")
                PRICE_SERVICE_BATCH_FAILURE.inc()

            return result_list, failed_assets

    async def get_single_price(self, asset: str) -> dict | tuple[None, str]:
        """Get price for a single asset with fallback and error handling."""
        with PRICE_SERVICE_REQUEST_TIME.time():
            self.logger.info(f"Fetching single price for {asset}")

            # Try Coingecko first
            try:
                coingecko_result = await self.coingecko.get_single_price(asset)
                if coingecko_result:
                    return self._create_result_dict(asset, *coingecko_result)
            except Exception as e:
                self.logger.error(f"Coingecko failed for {asset}: {str(e)}")

            # Try Messari as fallback
            self.logger.info(f"Attempting Messari fallback for {asset}")
            PRICE_SERVICE_FALLBACK_ATTEMPTS.inc()

            try:
                messari_result = await self.messari.get_price(asset)
                if messari_result:
                    return self._create_result_dict(asset, *messari_result)
            except Exception as e:
                error_msg = f"Messari fallback failed: {str(e)}"
                self.logger.error(f"{asset}: {error_msg}")

            # If both failed
            PRICE_SERVICE_BATCH_FAILURE.inc()
            self.logger.error(f"All providers failed for {asset}")
            return None, "No data available from any provider"

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
    result = asyncio.run(pr.get_single_price("eth"))
    print(result)
    print(f"asset: {result['asset']}\t usd_price: {result['usd_price']}")