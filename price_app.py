import logging
import os
import time

import prometheus_client
from cryptofund20x_misc.custom_formatter import CustomFormatter
from flask import jsonify
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST, core, ProcessCollector
from quart import request, Quart

import price_service
import transformer
from price_service import PriceService

# Enable multiprocess mode before creating any metrics
if 'PROMETHEUS_MULTIPROC_DIR' in os.environ:
    metrics_dir = os.environ.get('PROMETHEUS_MULTIPROC_DIR', '/tmp/prometheus_multiproc')
    os.makedirs(metrics_dir, exist_ok=True)
    core._use_multiprocess = True
    # Unregister default collectors
    try:
        prometheus_client.REGISTRY.unregister(prometheus_client.PROCESS_COLLECTOR)
        prometheus_client.REGISTRY.unregister(prometheus_client.PLATFORM_COLLECTOR)
        prometheus_client.REGISTRY.unregister(prometheus_client.GC_COLLECTOR)
    except KeyError:
        pass  # Ignore if collectors weren't registered

    # Register process collector
    ProcessCollector(registry=prometheus_client.REGISTRY)

# Set up logging
logger = logging.getLogger(__name__)
handler = logging.StreamHandler()
handler.setFormatter(CustomFormatter())
logger.addHandler(handler)
logger.setLevel(logging.INFO)

app = Quart(__name__)

# Prometheus Metrics
REQUEST_COUNT = Counter("requests_total", "Total number of requests", ["endpoint", "method"])
ERROR_COUNT = Counter("errors_total", "Total number of errors", ["endpoint", "error_type"])
REQUEST_LATENCY = Histogram("request_latency_seconds", "Request latency", ["endpoint"])
CURRENT_REQUESTS = Gauge("current_requests", "Number of in-progress requests")


@app.route('/')
async def health_check():
    """Health check endpoint for the service."""
    return "OK", 200


@app.route('/metrics', methods=['GET'])
async def metrics():
    """Expose Prometheus metrics."""
    return generate_latest(), 200, {'Content-Type': CONTENT_TYPE_LATEST}


@app.route('/transform-asset', methods=['GET'])
async def transform_asset():
    start_time = time.time()
    REQUEST_COUNT.labels(endpoint="transform-asset", method="GET").inc()
    CURRENT_REQUESTS.inc()

    asset = request.args.get('asset')
    if not asset:
        logger.error('No asset specified')
        ERROR_COUNT.labels(endpoint="transform-asset", error_type="missing_asset").inc()
        CURRENT_REQUESTS.dec()
        return jsonify({"error": "No asset specified"}), 400

    try:
        logger.info(f"Transforming asset {asset}")
        transformed_asset = transformer.transform_asset(asset)
        REQUEST_LATENCY.labels(endpoint="transform-asset").observe(time.time() - start_time)
        CURRENT_REQUESTS.dec()
        return jsonify({"transformed_asset": transformed_asset, "initial_asset": asset}), 200
    except Exception as e:
        logger.error(f"Error transforming asset {asset}: {e}")
        ERROR_COUNT.labels(endpoint="transform-asset", error_type="exception").inc()
        CURRENT_REQUESTS.dec()
        return jsonify({"error": "Internal server error"}), 500


@app.route('/price/<asset>', methods=['GET'])
async def price_single(asset: str):
    """Fetch the price of a single asset."""
    start_time = time.time()
    REQUEST_COUNT.labels(endpoint="price_single", method="GET", type="single").inc()
    CURRENT_REQUESTS.inc()

    try:
        logger.info(f"Fetching price for asset: {asset}")
        price_exec = PriceService()
        result = await price_exec.get_single_price(asset)

        if result is None:
            logger.warning(f"No price found for {asset}")
            ERROR_COUNT.labels(endpoint="price_single", error_type="not_found").inc()
            CURRENT_REQUESTS.dec()
            return jsonify({"error": f"Price data not found for {asset}"}), 404


        response_data = {
            "asset": asset,
            "usd_price": result["usd_price"],
            "volume_last_24_hours": result["volume_last_24_hours"],
            "current_marketcap_usd": result["current_marketcap_usd"],
        }

        REQUEST_LATENCY.labels(endpoint="price_single", type="single").observe(time.time() - start_time)
        CURRENT_REQUESTS.dec()
        return jsonify(response_data), 200

    except Exception as e:
        logger.error(f"Error fetching price for {asset}: {e}")
        ERROR_COUNT.labels(endpoint="price_single", error_type="exception").inc()
        CURRENT_REQUESTS.dec()
        return jsonify({"error": "Internal server error"}), 500


@app.route('/prices', methods=['GET'])
async def price_multiple():
    """Fetch prices for multiple assets."""
    start_time = time.time()
    REQUEST_COUNT.labels(endpoint="price_multiple", method="GET", type="list").inc()
    CURRENT_REQUESTS.inc()

    assets_param = request.args.get('assets')
    if not assets_param:
        logger.error("No assets specified")
        ERROR_COUNT.labels(endpoint="price_multiple", error_type="missing_assets").inc()
        CURRENT_REQUESTS.dec()
        return jsonify({"error": "No assets specified"}), 400

    asset_list = assets_param.split(',')
    if not asset_list:
        logger.error("Empty asset list")
        ERROR_COUNT.labels(endpoint="price_multiple", error_type="empty_list").inc()
        CURRENT_REQUESTS.dec()
        return jsonify({"error": "Asset list cannot be empty"}), 400

    try:
        logger.info(f"Fetching prices for assets: {asset_list}")
        price_exec = PriceService()
        result = await price_exec.coingecko_metric_list_async(asset_list)

        if not result:
            logger.warning(f"No price data found for assets: {asset_list}")
            ERROR_COUNT.labels(endpoint="price_multiple", error_type="not_found").inc()
            CURRENT_REQUESTS.dec()
            return jsonify({"error": "Price data not found"}), 404

        REQUEST_LATENCY.labels(endpoint="price_multiple", type="list").observe(time.time() - start_time)
        CURRENT_REQUESTS.dec()
        return jsonify({"prices": result}), 200

    except Exception as e:
        logger.error(f"Error fetching prices for assets {asset_list}: {e}")
        ERROR_COUNT.labels(endpoint="price_multiple", error_type="exception").inc()
        CURRENT_REQUESTS.dec()
        return jsonify({"error": "Internal server error"}), 500


if __name__ == '__main__':
    app.run(host="0.0.0.0", port=8080)
