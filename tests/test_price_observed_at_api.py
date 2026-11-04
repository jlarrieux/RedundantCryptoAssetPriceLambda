from datetime import datetime, timedelta, timezone

import pytest

from price_app import app
from pricing import redis_cache_service


class FakePipeline:
    def __init__(self, hashes):
        self.hashes = hashes
        self.keys = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        return False

    def hgetall(self, key):
        self.keys.append(key)

    async def execute(self):
        return [self.hashes.get(key, {}) for key in self.keys]


class FakeRedis:
    def __init__(self, hashes):
        self.hashes = hashes

    async def hgetall(self, key):
        return self.hashes.get(key, {})

    def pipeline(self, transaction=False):
        return FakePipeline(self.hashes)


def install_fake_redis(monkeypatch, hashes):
    client = FakeRedis(hashes)

    async def get_redis_client():
        return client

    monkeypatch.setattr(
        redis_cache_service, "get_redis_client", get_redis_client
    )
    return app.test_client()


def price_hash(observed_at=None, include_observed_at=True):
    data = {
        "usd_price": "3210.5",
        "volume_last_24_hours": "123456.7",
        "current_marketcap_usd": "987654321.0",
        "timestamp": datetime.now().isoformat(timespec="microseconds"),
    }
    if include_observed_at:
        data["observed_at"] = observed_at
    return data


@pytest.mark.asyncio
async def test_single_route_returns_observed_at_verbatim(monkeypatch):
    observed_at = "2026-11-03T01:02:03.456789+00:00"
    client = install_fake_redis(
        monkeypatch,
        {"price:eth": price_hash(observed_at)},
    )

    response = await client.get("/price/eth")

    assert response.status_code == 200
    assert await response.get_json() == {
        "asset": "eth",
        "usd_price": "3210.5",
        "volume_last_24_hours": "123456.7",
        "current_marketcap_usd": "987654321.0",
        "observed_at": observed_at,
    }


@pytest.mark.asyncio
async def test_single_route_omits_absent_observed_at_without_clock_substitute(
    monkeypatch,
):
    client = install_fake_redis(
        monkeypatch,
        {"price:eth": price_hash(include_observed_at=False)},
    )

    response = await client.get("/price/eth")

    assert response.status_code == 200
    body = await response.get_json()
    assert body == {
        "asset": "eth",
        "usd_price": "3210.5",
        "volume_last_24_hours": "123456.7",
        "current_marketcap_usd": "987654321.0",
    }
    assert "observed_at" not in body


@pytest.mark.asyncio
async def test_batch_route_preserves_presence_envelope_and_legacy_timestamp(
    monkeypatch,
):
    present_time = "2026-11-03T01:02:03.456789+00:00"
    present_hash = price_hash(present_time)
    absent_hash = price_hash(include_observed_at=False)
    client = install_fake_redis(
        monkeypatch,
        {
            "price:eth": present_hash,
            "price:btc": absent_hash,
        },
    )

    response = await client.get("/prices?assets=eth,btc")

    assert response.status_code == 200
    body = await response.get_json()
    assert list(body) == ["prices"]
    assert isinstance(body["prices"], list)
    assert len(body["prices"]) == 2
    success_dict, failed_list = body["prices"]
    assert failed_list == []
    assert success_dict["eth"]["observed_at"] == present_time
    assert "observed_at" not in success_dict["btc"]
    assert success_dict["eth"]["timestamp"] == present_hash["timestamp"]
    assert success_dict["btc"]["timestamp"] == absent_hash["timestamp"]


@pytest.mark.asyncio
async def test_stale_observed_at_is_returned_and_age_is_derived(monkeypatch):
    now = datetime.now(timezone.utc)
    observed_time = now - timedelta(minutes=15)
    observed_at = observed_time.isoformat(timespec="microseconds")
    client = install_fake_redis(
        monkeypatch,
        {"price:eth": price_hash(observed_at)},
    )

    response = await client.get("/price/eth")

    assert response.status_code == 200
    body = await response.get_json()
    assert body["observed_at"] == observed_at
    parsed_time = datetime.fromisoformat(body["observed_at"])
    age_seconds = (datetime.now(timezone.utc) - parsed_time).total_seconds()
    assert 895 <= age_seconds <= 905


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "observed_at",
    ["", "not-an-iso-timestamp"],
)
@pytest.mark.parametrize("endpoint", ["single", "batch"])
async def test_malformed_observed_at_is_passed_through_unchanged(
    monkeypatch, endpoint, observed_at
):
    client = install_fake_redis(
        monkeypatch,
        {"price:eth": price_hash(observed_at)},
    )

    path = "/price/eth" if endpoint == "single" else "/prices?assets=eth"
    response = await client.get(path)

    assert response.status_code == 200
    body = await response.get_json()
    if endpoint == "single":
        assert body["observed_at"] == observed_at
    else:
        success_dict, failed_list = body["prices"]
        assert success_dict["eth"]["observed_at"] == observed_at
        assert failed_list == []
