import asyncio
import json
import logging
import os
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta

from cryptofund20x_misc.custom_formatter import CustomFormatter
from cryptofund20x_services import url_service
from prometheus_client import Counter, Histogram

import transformer
from coin_price_provider import db_cache_service


class CoingeckoClient:
    def __init__(self):
        self.base_url = "https://api.coingecko.com/api/v3/"
        self.price_suffix = "simple/price?ids={}&vs_currencies=usd&include_market_cap=true&include_24hr_vol=true"
        self._cached_coin_list = None
        self._last_coin_list_update = None
        self.coin_list_cache_duration = timedelta(hours=1)

        # Setup logging
        self.logger = logging.getLogger("CoingeckoClient")
        handler = logging.StreamHandler()
        handler.setFormatter(CustomFormatter())
        self.logger.addHandler(handler)

        # Metrics
        self.requests = Counter('coingecko_requests_total', 'Total Coingecko API requests', ['status', 'type'])
        self.request_time = Histogram('coingecko_request_duration_seconds', 'Time spent in Coingecko API', ['type'])

    async def get_full_coin_list(self) -> List[Dict]:
        """Retrieve the full coin list from Coingecko with caching."""
        try:
            current_time = datetime.now()

            # Return cached list if it's fresh
            if (self._cached_coin_list is not None and
                    self._last_coin_list_update is not None and
                    current_time - self._last_coin_list_update < self.coin_list_cache_duration):
                self.logger.info("Using cached coin list")
                return self._cached_coin_list

            self.logger.info("Fetching fresh coin list from Coingecko")
            coin_list_url = os.path.join(self.base_url, "coins/", "list")
            response_text = await url_service.open_url_async(coin_list_url)
            coin_list = json.loads(response_text)

            if not isinstance(coin_list, list):
                raise ValueError("Expected list response from Coingecko")

            self._cached_coin_list = coin_list
            self._last_coin_list_update = current_time
            return coin_list

        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse Coingecko coin list: {str(e)}")
            raise Exception("Invalid response format from Coingecko") from e
        except Exception as e:
            self.logger.error(f"Failed to fetch Coingecko coin list: {str(e)}")
            raise Exception("Failed to get coin list from Coingecko") from e

        finally:
            await url_service.close_session()

    async def get_single_price(self, asset: str) -> Optional[Tuple[float, float, float]]:
        """Fetch price data for a single asset with DB caching."""
        with self.request_time.labels('single').time():
            try:
                self.logger.info(f"Getting price for asset: {asset}")

                # First check DB cache
                cached_data = await db_cache_service.get_cached_price_async(asset)
                if cached_data:
                    self.logger.info(f"Found cached price for {asset}")
                    return cached_data

                # Transform asset name
                transformed_asset = transformer.transform_asset(asset)
                self.logger.info(f"Transformed {asset} to {transformed_asset}")

                # Get coin ID
                coin_list = await self.get_full_coin_list()
                coin_id = self.get_coin_id(coin_list, transformed_asset)

                if not coin_id:
                    self.logger.warning(f"No matching coin found for {transformed_asset}")
                    self.requests.labels('failure', 'single').inc()
                    return None

                # Fetch from API
                self.logger.info(f"Fetching price for coin_id: {coin_id}")
                suffix = self.price_suffix.format(coin_id)
                url = os.path.join(self.base_url, suffix)
                response_text = await url_service.open_url_async(url)
                coin_data = json.loads(response_text)

                if coin_id not in coin_data:
                    self.logger.warning(f"No data returned for {coin_id}")
                    self.requests.labels('failure', 'single').inc()
                    return None

                # Parse and cache result
                market_data = coin_data[coin_id]
                result = self.parse_market_data(market_data)
                await db_cache_service.store_price(asset, *result)

                self.logger.info(f"Successfully fetched and cached price for {asset}")
                self.requests.labels('success', 'single').inc()
                return result

            except Exception as e:
                self.logger.error(f"Error getting price for {asset}: {str(e)}")
                self.requests.labels('failure', 'single').inc()
                raise Exception(f"Coingecko API error: {str(e)}")
            finally:
                await url_service.close_session()

    async def get_batch_prices(self, assets: List[str]) -> Dict[str, Optional[Tuple[float, float, float]]]:
        """Fetch prices for multiple assets with transformation and error handling."""
        with self.request_time.labels('batch').time():
            try:
                self.logger.info(f"Getting batch prices for {len(assets)} assets")
                result = {}
                to_fetch = []
                asset_to_transformed = {}

                # First check DB cache for all assets
                for asset in assets:
                    cached_data = await db_cache_service.get_cached_price_async(asset)
                    if cached_data:
                        self.logger.info(f"Found cached price for {asset}")
                        result[asset] = cached_data
                    else:
                        transformed = transformer.transform_asset(asset)
                        asset_to_transformed[transformed] = asset
                        to_fetch.append(transformed)

                if not to_fetch:
                    self.logger.info("All prices found in cache")
                    return result

                # Get coin IDs for assets we need to fetch
                coin_list = await self.get_full_coin_list()
                asset_to_coin_id = {}
                for transformed_asset in to_fetch:
                    coin_id = self.get_coin_id(coin_list, transformed_asset)
                    if coin_id:
                        asset_to_coin_id[coin_id] = transformed_asset
                    else:
                        self.logger.warning(f"No matching coin found for {transformed_asset}")
                        original_asset = asset_to_transformed[transformed_asset]
                        result[original_asset] = None

                if not asset_to_coin_id:
                    self.logger.warning("No valid coin IDs found for batch")
                    self.requests.labels('failure', 'batch').inc()
                    return result

                # Fetch prices for found coin IDs
                suffix = self.price_suffix.format(','.join(asset_to_coin_id.keys()))
                url = os.path.join(self.base_url, suffix)
                response_text = await url_service.open_url_async(url)
                coin_data = json.loads(response_text)

                # Process results
                for coin_id, market_data in coin_data.items():
                    try:
                        transformed_asset = asset_to_coin_id[coin_id]
                        original_asset = asset_to_transformed[transformed_asset]
                        price_data = self.parse_market_data(market_data)
                        await db_cache_service.store_price(original_asset, *price_data)
                        result[original_asset] = price_data
                    except Exception as e:
                        self.logger.error(f"Error processing data for {coin_id}: {str(e)}")
                        if transformed_asset in asset_to_transformed:
                            result[asset_to_transformed[transformed_asset]] = None

                self.requests.labels('success', 'batch').inc()
                return result

            except Exception as e:
                self.logger.error(f"Batch request failed: {str(e)}")
                self.requests.labels('failure', 'batch').inc()
                raise Exception(f"Coingecko API error: {str(e)}")
            finally:
                await url_service.close_session()

    @staticmethod
    def parse_market_data(market_data: Dict) -> Tuple[float, float, float]:
        """Parse market data into price, volume, and market cap."""
        return (
            market_data["usd"],
            market_data["usd_24h_vol"],
            market_data["usd_market_cap"]
        )

    @staticmethod
    def get_coin_id(coin_list: List[Dict], asset: str) -> Optional[str]:
        """Find coin ID in Coingecko's list."""
        for coin in coin_list:
            if asset == "magic" and coin['id'] == asset:
                return coin['id']
            if coin["name"] == asset or coin["symbol"] == asset or coin["id"] == asset:
                return coin['id']
        return None


if __name__ == '__main__':
    coingecko = CoingeckoClient()
    coin_list_for_testing = ['alpha-finance', 'sand', 'tokemak', 'rook', 'tusd', 'premia', 'convex-finance', 'sushi',
                             'hop', 'ethereum', 'yfi', 'wbtc', 'kyber-network', 'mirror-protocol', 'xsushi', 'rpl',
                             '1inch', 'op', 'susd', 'plutusdao', 'rgt', 'ilv', 'trove', 'degen', 'dnt', 'alcx',
                             'lyra-finance', 'tcap', 'dai', 'ftm', 'omg', 'alink', 'dpx', 'fxs', 'fpis',
                             'conic-finance', 'dopex-rebate-token', 'big-data-protocol', 'spell', 'mln', 'magic',
                             'hegic', 'usd-coin', 'nftx', 'havven', 'the-graph', 'ulu', 'matic', 'weth', 'arch', 'link',
                             'perp', 'lrc', 'vision', 'stake-dao', 'silo-finance', 'airswap', 'bal', 'radar', 'uniswap',
                             'audio', 'mvi', 'jpeg-d', 'immutable-x', 'crv', 'rbn', 'aave', 'thales']
    # print(asyncio.run(coingecko.get_batch_prices(coin_list_for_testing)))
    print(asyncio.run(coingecko.get_single_price("mir")))
