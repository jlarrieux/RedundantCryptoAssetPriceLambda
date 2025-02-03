import asyncio
import logging

from cryptofund20x_misc.custom_formatter import CustomFormatter
from cryptofund20x_services import url_service
from cryptofund20x_utils_second import list_utils
from prometheus_client import Counter, Gauge

from pricing.coin_gecko_price_provider import CoingeckoClient

# Setup logging
logger = logging.getLogger("redis_cache")
handler = logging.StreamHandler()
handler.setFormatter(CustomFormatter())
logger.addHandler(handler)

# Prometheus metrics
PRICE_FETCH_SUCCESS = Counter('price_fetch_success_total', 'Number of successful price fetches', ['asset_chunk'])
PRICE_FETCH_ERRORS = Counter('price_fetch_errors_total', 'Number of failed price fetches',
                             ['asset_chunk', 'error_type'])
ASSETS_PROCESSED = Gauge('assets_processed_total', 'Total number of assets processed in the latest run')
CACHE_UPDATE_DURATION = Gauge('cache_update_duration_seconds', 'Time taken to update the entire price cache')
FAILED_ASSETS = Gauge('failed_assets_total', 'Number of assets that failed to fetch prices')

all_network_price_list = ['1inch', 'aave', 'airswap', 'alcx', 'alink', 'alpha-finance', 'audio', 'bal', 'bdp',
                          'big-data-protocol', 'conic-finance', 'convex-finance', 'crv', 'curve-dao-token', 'cvxcrv',
                          'dai', 'degen', 'dopex-rebate-token', 'dpx', 'eth', 'ethereum', 'fctr', 'fpis', 'ftm', 'fxs',
                          'gearbox', 'grail', 'havven', 'hegic', 'hop', 'ilv', 'immutable-x', 'jpeg-d', 'kyber-network',
                          'link', 'lrc', 'lyra-finance', 'magic', 'matic', 'mav', 'mirror-protocol', 'mln', 'nftx',
                          'omg', 'op', 'perp', 'pls', 'plutusdao', 'premia', 'radar', 'rbn', 'rdpx', 'rgt', 'rook',
                          'rpl', 'silo-finance', 'spa', 'spell', 'stake-dao', 'susd', 'thales', 'the-graph', 'tokemak',
                          'trove', 'tusd', 'uniswap', 'usd-coin', 'usdc', 'vision', 'weth', 'wrapped-bitcoin', 'xsushi',
                          'yfi']


async def build_price_cache():
    symbol_chunks = list_utils.split_list_equally_into_n_lists(all_network_price_list, 5)
    coingecko_client = CoingeckoClient()  # Using CoingeckoClient directly

    all_successes = []
    all_failures = []

    try:
        for i, chunk in enumerate(symbol_chunks):
            chunk_name = f"chunk_{i + 1}"
            logger.info(f"\n\n\n\nProcessing chunk {chunk_name}")
            try:
                # Use the direct method that bypasses cache checking
                results = await coingecko_client.get_batch_prices_direct(chunk)

                # Split results into successes and failures
                successes = []
                failures = []
                for asset, result in results.items():
                    if result is not None:
                        successes.append(asset)
                    else:
                        failures.append(asset)

                all_successes.extend(successes)
                all_failures.extend(failures)

                PRICE_FETCH_SUCCESS.labels(asset_chunk=chunk_name).inc()
                # Only sleep if this isn't the last chunk
                if i < len(symbol_chunks) -1:
                    logger.info(f"\n\nDone with {chunk_name} so sleeping with i: {i} and {len(symbol_chunks)}")
                    await asyncio.sleep(2)

            except Exception as e:
                error_type = type(e).__name__
                logger.error(f"Error processing chunk {chunk}: {str(e)}")
                PRICE_FETCH_ERRORS.labels(asset_chunk=chunk_name, error_type=error_type).inc()
                all_failures.extend(chunk)
                continue

            # url_service already handles delays between requests

    finally:
        await url_service.close_session()

    return all_successes, all_failures


if __name__ == '__main__':
    asyncio.run(build_price_cache())
