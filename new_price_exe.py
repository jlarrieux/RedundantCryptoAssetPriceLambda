import asyncio
import datetime
import json
import os
import time
from typing import Dict, Tuple

import boto3
from cryptofund20x_services import url_service
from cryptofund20x_utils import aws_util
from six.moves.urllib.error import HTTPError

import util

messari_url = "https://data.messari.io/api/v1/assets/{}/metrics?fields=id,symbol,market_data/price_usd," \
              "market_data/real_volume_last_24_hours,market_data/volume_last_24_hours,marketcap/current_marketcap_usd "

coingecko_base = "https://api.coingecko.com/api/v3/"
coingecko_suffix = "simple/price?ids={}&vs_currencies=usd&include_market_cap=true&include_24hr_vol=true"
region = "us-east-1"
dynamodb = boto3.client('dynamodb', region_name=region)
tableName = "crypto_price"
elapsed_time_threshold = 180
coin_gecko_full_list_key = "cryptofund202x/coin_gecko_full_list.pkl"


def print_elapsed_time(start_time: time) -> None:
    print(f"\n\nTook {util.format_numbers(time.time() - start_time)} seconds to execute.\n")


def fix_string(messed_up_string: str) -> str:
    return messed_up_string.replace("{", "").replace("}", "").replace("'", "")


def handle_list_asset(asset_list: list, start_time: time) -> dict:
    print(f"asset list!!!: {asset_list}")
    result_list = coingecko_metric_list_async(asset_list)
    print_elapsed_time(start_time)
    return build_response(200, result_list)


def build_response(code: int, body: [str, dict]) -> dict:
    response = dict()
    response["statusCode"] = code
    response["headers"] = {}
    response["headers"]["Content-Type"] = "application/json"
    response["body"] = json.dumps(body)
    return response


def build_body(asset: str, result: Tuple[float, float, float]) -> dict:
    response = dict()
    response["asset"] = asset
    response["usd_price"] = result[0]
    response["volume_last_24_hours"] = result[1]
    response["current_marketcap_usd"] = result[2]
    return response


async def trials_async(asset: str) -> (Tuple[float, float, float], None):
    """Try to fetch the asset price from Coingecko first, then Messari."""
    result = await coingecko_metric_async(asset)
    if result:
        return result
    return await messari_metric_async(asset)


async def messari_metric_async(asset: str) -> (Tuple[float, float, float], None):
    """Fetch price data from Messari API."""
    url = messari_url.format(asset)
    try:
        response_text = await url_service.open_url_async(url)
        coin = json.loads(response_text)

        data = coin["data"]
        market_data = data["market_data"]

        usd_price = market_data["price_usd"]
        usd_volume = market_data["volume_last_24_hours"]
        usd_marketcap = data["marketcap"]["current_marketcap_usd"]

        if usd_price is None or usd_volume is None or usd_marketcap is None:
            return None
        return usd_price, usd_volume, usd_marketcap
    except (HTTPError, json.JSONDecodeError) as error:
        return None


async def coingecko_get_full_coin_list_async() -> list:
    """Retrieve the full coin list from Coingecko API, cached in S3. Rate limit of 100 requests per minutes so we must cache in s3"""
    now = datetime.datetime.now()
    coin_list = ""
    if now.hour == 0 and now.minute == 0:
        coin_list = await _get_coingecko_full_list_remote()
        await aws_util.save_to_s3_default_bucket_async(coin_gecko_full_list_key, coin_list)
    else:
        coin_list = await aws_util.load_from_s3_default_bucket_async(coin_gecko_full_list_key)

    return coin_list


async def _get_coingecko_full_list_remote():
    """Fetch the full coin list from Coingecko API."""
    url = os.path.join(coingecko_base, "coins/", "list")
    response_text = await url_service.open_url_async(url)
    return json.loads(response_text)


async def coingecko_metric_async(asset: str) -> (Tuple[float, float, float], None):
    """Fetch price data from Coingecko API."""
    full_coin_list = await coingecko_get_full_coin_list_async()
    coin_needed = get_coingecko_coin_needed(full_coin_list, asset)
    if coin_needed is None:
        return None

    coin_needed_id_ = coin_needed["id"]
    url = os.path.join(coingecko_base, coingecko_suffix.format(coin_needed_id_))
    response_text = await url_service.open_url_async(url)

    coin_data = json.loads(response_text)
    if coin_needed_id_ not in coin_data:
        return None

    market_data = coin_data[coin_needed_id_]
    return market_data["usd"], market_data["usd_24h_vol"], market_data["usd_market_cap"]


def get_coingecko_coin_needed(coin_list: list, asset: str):
    """Find the correct coin entry in Coingecko's list."""
    for coin in coin_list:
        if asset == "magic" and coin['id'] == asset:
            return coin
        if coin["name"] == asset or coin["symbol"] == asset or coin["id"] == asset:
            return coin
    return None


async def coingecko_metric_list_async(asset_list: list) -> list:
    """Fetch market data for a list of assets asynchronously, with database caching."""
    coin_list = await coingecko_get_full_coin_list_async()
    asset_mapping = {}
    suffix = ""
    result_list = []
    found_set = set()

    for asset in asset_list:
        asset_in_database_and_not_stale = await check_database_async(asset)
        if asset_in_database_and_not_stale is not None:
            found_set.add(asset)
            print(f'already found: {asset} in db, adding to result...')
            result_list.append(create_result_dict(
                asset,
                asset_in_database_and_not_stale[0],  # usd_price
                asset_in_database_and_not_stale[1],  # volume_last_24_hours
                asset_in_database_and_not_stale[2]  # current_marketcap_usd
            ))
            continue

        print(f'{asset} not found in db, adding to coingecko list ...')
        coin_needed = get_coingecko_coin_needed(coin_list, asset)
        if coin_needed:
            asset_mapping[coin_needed["id"]] = asset
            suffix += f",{coin_needed['id']}" if suffix else coin_needed["id"]

    # If all assets were in DB, return result immediately
    if not suffix:
        return result_list

    # Fetch remaining assets from Coingecko
    url = os.path.join(coingecko_base, coingecko_suffix.format(suffix))
    response_text = await url_service.open_url_async(url)
    coins_data = json.loads(response_text)

    for coin_id, market_data in coins_data.items():
        asset = asset_mapping.get(coin_id)
        if asset and market_data:
            print(f"market_data for {asset}: {market_data}")  # Debug line
            await put_in_db(asset, market_data["usd"], market_data["usd_24h_vol"], market_data["usd_market_cap"])
            result_list.append(create_result_dict(asset, market_data["usd"], market_data["usd_24h_vol"],
                                                  market_data["usd_market_cap"]))

    return result_list


def create_result_dict(asset: str, usd_price: float, usd_volume: float, usd_marketcap: float) -> dict:
    """Format result dictionary."""
    return {"asset": asset, "usd_price": usd_price, "volume_last_24_hours": usd_volume,
            "current_marketcap_usd": usd_marketcap}


async def get_price_async(asset: str) -> (Tuple[float, float, float], None):
    """Fetch price for a single asset asynchronously."""
    asset_in_database_and_not_stale = await check_database_async(asset)
    if asset_in_database_and_not_stale is not None:
        return asset_in_database_and_not_stale

    value = await trials_async(asset)
    if value is None:
        return None

    price_usd, volume_usd, marketcap_usd = value
    await put_in_db(asset, price_usd, volume_usd, marketcap_usd)
    return price_usd, volume_usd, marketcap_usd


import aioboto3


async def get_all_db_assets_async() -> Dict:
    """Async version of get_all_db_assets that fetches items from DynamoDB."""
    session = aioboto3.Session()
    async with session.client('dynamodb', region_name=region) as dynamodb_local:
        response = await dynamodb_local.scan(TableName=tableName)

    result = {}
    for item in response["Items"]:
        name = item["name"]["S"]
        price = float(item["usd_price"]["N"])
        marketcap = float(item["current_marketcap_usd"]["N"])
        volume = float(item["volume_last_24_hours"]["N"])
        dt = util.string_datetime_to_datetime_object(item["datetime"]["S"])
        result[name] = (price, dt, volume, marketcap)
    return result


async def check_database_async(asset: str) -> (Tuple[float, float, float], None):
    """
    Async version of check_database that checks if an asset exists in the database
    and whether its data is fresh enough to use.

    Args:
        asset (str): The asset symbol to check

    Returns:
        Tuple[float, float, float]: (price, volume, marketcap) if asset found and fresh
        None: if asset not found or data is stale
    """
    all_assets = await get_all_db_assets_async()

    if asset in all_assets:
        print(f"'{asset}' found in db!")
        current_data = all_assets[asset]
        elapsed = (datetime.datetime.now() - current_data[1]).total_seconds()

        print(f"elapsed time between database insert of '{asset}' and now: "
              f"{util.format_numbers(elapsed)} seconds")

        if elapsed < elapsed_time_threshold:
            print(current_data)
            # Return price, volume, marketcap
            return current_data[0], current_data[2], current_data[3]
        else:
            print(f"'{asset}' is stale since {elapsed} seconds is greater than "
                  f"threshold of {elapsed_time_threshold} seconds, will update!")

    return None


async def put_in_db(asset: str, price: float, volume: float, marketcap: float):
    """Store asset data in the database."""
    if None in (asset, price, volume, marketcap):
        return

    session = aioboto3.Session()
    try:
        async with session.client('dynamodb', region_name=region) as dynamodb:
            await dynamodb.update_item(
                TableName=tableName,
                Key={"name": {"S": asset}},
                ExpressionAttributeNames={"#datetime": "datetime"},
                UpdateExpression="SET usd_price = :p, #datetime = :d, volume_last_24_hours = :v, current_marketcap_usd = :m",
                ExpressionAttributeValues={
                    ":p": {"N": str(price)},
                    ":d": {"S": str(datetime.datetime.now())},
                    ":v": {"N": str(volume)},
                    ":m": {"N": str(marketcap)},
                }
            )
    except Exception as e:
        print(f"Error updating database for {asset}: {str(e)}")
        raise

if __name__ == '__main__':
    myslit = ['alpha-finance', 'sand', 'tokemak', 'rook', 'tusd', 'premia', 'convex-finance', 'sushi', 'hop',
              'ethereum',
              'yfi', 'wbtc', 'kyber-network', 'mirror-protocol', 'xsushi', 'rpl', '1inch', 'op', 'susd', 'plutusdao',
              'rgt',
              'ilv', 'trove', 'degen', 'dnt', 'alcx', 'lyra-finance', 'tcap', 'dai', 'ftm', 'omg', 'alink', 'dpx',
              'fxs',
              'fpis', 'conic-finance', 'dopex-rebate-token', 'big-data-protocol', 'spell', 'mln', 'magic', 'hegic',
              'usd-coin', 'nftx', 'havven', 'the-graph', 'ulu', 'matic', 'weth', 'arch', 'link', 'perp', 'lrc',
              'vision',
              'stake-dao', 'silo-finance', 'airswap', 'bal', 'radar', 'uniswap', 'audio', 'mvi', 'jpeg-d',
              'immutable-x',
              'crv', 'rbn', 'aave', 'thales']
    print(asyncio.run(coingecko_metric_list_async(myslit)))
    # print(coingecko_metric_list_async(
    #     ['alpha-finance', 'sand', 'tokemak', 'rook', 'tusd', 'premia', 'convex-finance', 'sushi', 'hop', 'ethereum',
    #      'yfi', 'wbtc', 'kyber-network', 'mirror-protocol', 'xsushi', 'rpl', '1inch', 'op', 'susd', 'plutusdao', 'rgt',
    #      'ilv', 'trove', 'degen', 'dnt', 'alcx', 'lyra-finance', 'tcap', 'dai', 'ftm', 'omg', 'alink', 'dpx', 'fxs',
    #      'fpis', 'conic-finance', 'dopex-rebate-token', 'big-data-protocol', 'spell', 'mln', 'magic', 'hegic',
    #      'usd-coin', 'nftx', 'havven', 'the-graph', 'ulu', 'matic', 'weth', 'arch', 'link', 'perp', 'lrc', 'vision',
    #      'stake-dao', 'silo-finance', 'airswap', 'bal', 'radar', 'uniswap', 'audio', 'mvi', 'jpeg-d', 'immutable-x',
    #      'crv', 'rbn', 'aave', 'thales']))
