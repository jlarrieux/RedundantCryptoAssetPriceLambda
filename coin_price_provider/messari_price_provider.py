from typing import Dict, Tuple, Optional
import json

from cryptofund20x_services import url_service
from prometheus_client import Counter, Histogram


class MessariClient:
    def __init__(self):
        self.base_url = "https://data.messari.io/api/v1/assets/{}/metrics"
        self.fields = "id,symbol,market_data/price_usd,market_data/real_volume_last_24_hours,market_data/volume_last_24_hours,marketcap/current_marketcap_usd"
        self.url_service = url_service

        # Metrics
        self.requests = Counter('messari_requests_total', 'Total Messari API requests', ['status'])
        self.request_time = Histogram('messari_request_duration_seconds', 'Time spent in Messari API')

    async def get_price(self, asset: str) -> Optional[Tuple[float, float, float]]:
        """Fetch price data for a single asset."""
        with self.request_time.time():
            try:
                url = f"{self.base_url.format(asset)}?fields={self.fields}"
                response_text = await self.url_service.open_url_async(url)
                data = json.loads(response_text)["data"]

                market_data = data["market_data"]
                price = market_data["price_usd"]
                volume = market_data["volume_last_24_hours"]
                marketcap = data["marketcap"]["current_marketcap_usd"]

                if None in (price, volume, marketcap):
                    self.requests.labels('failure').inc()
                    return None

                self.requests.labels('success').inc()
                return price, volume, marketcap

            except Exception as e:
                self.requests.labels('failure').inc()
                raise Exception(f"Messari API error: {str(e)}")