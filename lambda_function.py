import datetime
import json
import os
from typing import Any
from typing import Dict
from typing import List
from typing import Tuple
from typing import Union
import time
import boto3
from six.moves import urllib
from six.moves.urllib.error import HTTPError
import util
from json.decoder import JSONDecodeError
import re

messari_url = "https://data.messari.io/api/v1/assets/{}/metrics?fields=id,symbol,market_data/price_usd," \
              "market_data/real_volume_last_24_hours,market_data/volume_last_24_hours,marketcap/current_marketcap_usd "

coingecko_base = "https://api.coingecko.com/api/v3/"
coingecko_suffix = "simple/price?ids={}&vs_currencies=usd&include_market_cap=true&include_24hr_vol=true"
region = "us-east-1"
dynamodb = boto3.client('dynamodb', region_name=region)
tableName = "crypto_price"
elapsed_time_threshold = 90


def lambda_handler(event: Any, context: Any) -> Dict[str, Union[int, str]]:
    start_time = time.time()
    if event["httpMethod"] == "GET":
        asset = event["queryStringParameters"]["asset"]
        if asset is None:
            print_elapsed_time(start_time)
            return build_response(400, "asset must be provided in query parameter string!")

        if "items" in asset:
            asset_new = fix_string(asset.replace("items=", ""))
            asset_list = list(json.loads(asset_new))
            return handle_list_asset(asset_list, start_time)
        elif isinstance(asset, str):
            return handle_string_asset(asset, start_time)

        elif isinstance(asset, list):
            return handle_list_asset(asset, start_time)

    else:
        print_elapsed_time(start_time)
        return build_response(400, "Must be a GET request!")


def handle_string_asset(asset: str, start_time: time) -> dict:
    result = get_price(asset)
    if not result:
        print_elapsed_time(start_time)
        return build_response(503,
                              f"Both messari crypto and coingecko could not find "
                              f"{asset} or could not be reach!")
    print_elapsed_time(start_time)
    return build_response(200, build_body(asset, result))


def print_elapsed_time(start_time: time) -> None:
    print(f"\n\nTook {util.format_numbers(time.time() - start_time)} seconds to execute.\n")


def fix_string(messed_up_string: str) -> str:
    return messed_up_string.replace("{", "").replace("}", "").replace("'", "")


def handle_list_asset(asset_list: list, start_time: time) -> dict:
    print(f"asset list!!!: {asset_list}")
    result_list = coingecko_metric_list(asset_list)
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


def trials(asset: str) -> (Tuple[float, float, float], None):
    result = coingecko_metric(asset)
    if result:
        return result
    return messari_metric(asset)


def messari_metric(asset: str) -> (Tuple[float, float, float], None):
    # Rate limit of 20 requests per minute.
    try:
        coin = execute_and_get_json(messari_url.format(asset))

        data = coin["data"]
        market_data = data["market_data"]

        usd_price = market_data["price_usd"]
        usd_volume = market_data["volume_last_24_hours"]
        usd_marketcap = data["marketcap"]["current_marketcap_usd"]
        if usd_price is None or usd_volume is None or usd_marketcap is None:
            return None
        return usd_price, usd_volume, usd_marketcap
    except HTTPError as error:
        return None


def coingecko_get_full_coin_list() -> list:
    # Rate limit of 100 requests per minutes.
    coin_list_url = os.path.join(coingecko_base, "coins/", "list")
    coin_list = execute_and_get_json(coin_list_url)
    return coin_list


def coingecko_metric(asset: str) -> (Tuple[float, float, float], None):
    coin_needed = get_coingecko_coin_needed(coingecko_get_full_coin_list(), asset)
    if coin_needed is None:
        return None
    coin_needed_id_ = coin_needed["id"]
    print(f"Coin id: {coin_needed_id_}")
    suffix = coingecko_suffix.format(coin_needed_id_)
    full_url = os.path.join(coingecko_base, suffix)
    coin_data = execute_and_get_json(full_url)
    print(f"single asset full url: {full_url}")
    if len(coin_data) == 0:
        return None
    market_data = coin_data[str(coin_needed_id_).lower()]
    usd_price = market_data["usd"]
    usd_volume = market_data["usd_24h_vol"]
    usd_marketcap = market_data["usd_market_cap"]
    return usd_price, usd_volume, usd_marketcap


def get_coingecko_coin_needed(coin_list: list, asset: str):
    coin_needed = None
    for coin in coin_list:
        if coin["name"] == asset or coin["symbol"] == asset or coin["id"] == asset:
            coin_needed = coin
            break
    return coin_needed


def coingecko_metric_list(asset_list: list) -> (list, None):
    coin_list = coingecko_get_full_coin_list()
    suffix = ""
    asset_mapping = dict()
    result_list = []
    found_set = set()
    for asset in asset_list:
        asset_in_database_and_not_stale = check_database(asset)
        if asset_in_database_and_not_stale is not None:
            found_set.add(asset)
            result_list.append(
                create_result_dict(asset, asset_in_database_and_not_stale[0], asset_in_database_and_not_stale[1],
                                   asset_in_database_and_not_stale[2]))
            continue

        coin_needed = get_coingecko_coin_needed(coin_list, asset)
        if coin_needed is not None:
            asset_mapping[coin_needed["id"]] = asset
            if len(suffix) > 0:
                suffix += ","
            suffix += f"{coin_needed['id']}"
    if len(suffix) > 0:
        list_suffix = coingecko_suffix.format(suffix)
        print(f"printing suffix list: {list_suffix}")
        full_url = os.path.join(coingecko_base, list_suffix)
        print(f"printing full url: {full_url}")
        coins_data = execute_and_get_json(full_url)
        print(f"printing coins data: {coins_data}")
        for key in coins_data.keys():
            coin_id = str(key).lower()
            asset = asset_mapping[coin_id]
            market_data = coins_data[coin_id]
            usd_price = market_data["usd"]
            usd_volume = market_data["usd_24h_vol"]
            usd_marketcap = market_data["usd_market_cap"]
            put_in_db(asset, usd_price, usd_volume, usd_marketcap)
            result_list.append(create_result_dict(asset, usd_price, usd_volume, usd_marketcap))
        print(f"result List: {result_list}")
    return result_list


def create_result_dict(asset: str, usd_price: float, usd_volume: float, usd_marketcap: float) -> dict:
    return {"asset": asset, "usd_price": usd_price, "volume_last_24_hours": usd_volume,
            "current_marketcap_usd": usd_marketcap}


def execute_and_get_json(url: str, header: dict = None) -> (List, Dict):
    request = urllib.request.Request(url, header)
    jay = json.loads(urllib.request.urlopen(request).read().decode())
    return jay


def get_price(asset: str) -> (Tuple[float, float, float], None):
    asset_in_database_and_not_stale = check_database(asset)
    if asset_in_database_and_not_stale is not None:
        return asset_in_database_and_not_stale

    value = trials(asset)
    if value is None:
        return None
    price_usd, volume_usd, marketap_usd = value
    put_in_db(asset, price_usd, volume_usd, marketap_usd)
    return price_usd, volume_usd, marketap_usd


def check_database(asset: str) -> (Tuple[float, float, float], None):
    all_assets = get_all_db_assets()
    if asset in all_assets.keys():
        print(f"'{asset}' found in db!")
        elapsed = (datetime.datetime.now() - all_assets[asset][1]).total_seconds()
        print(f"elapsed time between database insert of '{asset}' and now:  {util.format_numbers(elapsed)} seconds")
        if elapsed < elapsed_time_threshold:
            current = all_assets[asset]
            print(current)
            return current[0], current[2], current[3]
        else:
            print(f"'{asset}' is stale since {elapsed} seconds is greater than threshold of {elapsed_time_threshold} "
                  f"seconds, will update!")
    return None


def get_all_db_assets() -> Dict:
    response = dynamodb.scan(TableName=tableName)["Items"]
    result = dict()
    for item in response:
        name = item["name"]["S"]
        price = item["usd_price"]["N"]
        marketcap = item["current_marketcap_usd"]["N"]
        volume = item["volume_last_24_hours"]["N"]
        dt = util.string_datetime_to_datetime_object(item["datetime"]["S"])
        result[name] = (price, dt, volume, marketcap)
    return result


def put_in_db(asset: str, price: float, volume: float, marketcap: float):
    print(f"Putting {asset} in db!!!")
    dynamodb.update_item(TableName=tableName, Key={
        "name": {
            "S": asset
        }}, ExpressionAttributeNames={
        "#datetime": "datetime"},
                         UpdateExpression="set usd_price = :p, #datetime = :d, volume_last_24_hours = :v, current_marketcap_usd = :m",
                         ExpressionAttributeValues={
                             ":p": {"N": str(price)},
                             ":d": {"S": str(datetime.datetime.now())},
                             ":v": {"N": str(volume)},
                             ":m": {"N": str(marketcap)}})


if __name__ == '__main__':
    my_list = ["havven", "crv"]
    coingecko_metric_list(my_list)
    # print(trials("kyber-network"))
    # val = "ethrsiapy"
    # event = dict()
    # context = dict()
    # event["httpMethod"] = "GET"
    # asset = dict()
    # asset["asset"] = val
    # event["queryStringParameters"] = asset
    # print(lambda_handler(event=event, context=None))
