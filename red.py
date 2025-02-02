import os, time, json, logging
from datetime import datetime
from quart import Quart, request, jsonify
import uvicorn
from prometheus_client import CollectorRegistry, Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST, multiprocess

if "PROMETHEUS_MULTIPROC_DIR" in os.environ:
    r = CollectorRegistry()
    multiprocess.MultiProcessCollector(r)
else:
    from prometheus_client import REGISTRY as r
REQUEST_COUNT = Counter("request_count", "Total requests", ["method", "endpoint", "http_status"], registry=r)
REQUEST_LATENCY = Histogram("request_latency_seconds", "Request latency", ["endpoint"], registry=r)
logger = logging.getLogger("quart_server")
logger.setLevel(logging.INFO)
h = logging.StreamHandler()
logger.addHandler(h)
app = Quart(__name__)


@app.before_request
async def before_req():
    request.start_time = time.time()


@app.after_request
async def after_req(resp):
    lat = time.time() - request.start_time
    REQUEST_LATENCY.labels(request.path).observe(lat)
    REQUEST_COUNT.labels(request.method, request.path, resp.status_code).inc()
    return resp


@app.route("/")
async def health():
    return "OK", 200


@app.route("/metrics")
async def metrics():
    data = generate_latest(r)
    return data, 200, {"Content-Type": CONTENT_TYPE_LATEST}


@app.route("/transform-asset", methods=["GET"])
async def transform_asset():
    a = request.args.get("asset")
    if not a:
        return jsonify({"error": "No asset specified"}), 400


    return jsonify({"initial_asset": a, "transformed_asset": ta(a)}), 200


@app.route("/price", methods=["GET"])
async def price():
    a = request.args.get("asset")
    if not a:
        return jsonify({"error": "Asset query parameter missing"}), 400
        from crypto_backend import get_price, cg_metric_list
        if a.startswith("items="):
            try:
                alist = json.loads(a.replace("items=", ""))
            except Exception:
                return jsonify({"error": "Invalid asset list"}), 400
            return jsonify(cg_metric_list(alist)), 200
        r = get_price(a)
        if r is None:
            return jsonify({"error": f"Could not retrieve price for {a}"}), 503
        return jsonify(
            {"asset": a, "usd_price": r[0], "volume_last_24_hours": r[1], "current_marketcap_usd": r[2]}), 200


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
