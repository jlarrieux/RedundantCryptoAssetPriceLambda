import asyncio
import logging

from cryptofund20x_misc.custom_formatter import CustomFormatter
from cryptofund20x_services import url_service
from cryptofund20x_utils_second import list_utils
from prometheus_client import Counter, Gauge

from price_service import PriceService
from pricing import redis_cache_service

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
    start_time = asyncio.get_event_loop().time()
    # Split into smaller chunks (e.g., 10-15 assets per chunk)
    symbol_chunks = list_utils.split_list_equally_into_n_lists(all_network_price_list, 5)
    price_service = PriceService()

    all_successes = []
    all_failures = []
    for i, chunk in enumerate(symbol_chunks):
        chunk_name = f"chunk_{i + 1}"
        logger.info(f"\n\nProcessing chunk {chunk_name}")
        try:
            # Process one chunk at a time
            successes, failures = await price_service.get_prices(chunk)
            all_successes.extend(successes)
            all_failures.extend(failures)
            PRICE_FETCH_SUCCESS.labels(asset_chunk=chunk_name).inc()
            # Add a small delay between chunks to respect rate limits
            await asyncio.sleep(1.2)  # 1.2 seconds delay between chunks

        except Exception as e:
            error_type = type(e).__name__
            logger.error(f"Error processing chunk {chunk}: {str(e)}")
            PRICE_FETCH_ERRORS.labels(asset_chunk=chunk_name, error_type=error_type).inc()
            continue
        finally:
            await url_service.close_session()

    if all_successes:
        logger.info(f"Successfully processed {len(all_successes)} chunks")
        duration = asyncio.get_event_loop().time() - start_time
        ASSETS_PROCESSED.set(len(all_successes))
        CACHE_UPDATE_DURATION.set(duration)
        FAILED_ASSETS.set(len(all_failures))
        await redis_cache_service.store_all_prices(all_successes)


if __name__ == '__main__':
    asyncio.run(build_price_cache())
