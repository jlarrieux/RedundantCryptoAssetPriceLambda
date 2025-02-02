from datetime import datetime
from typing import Tuple, Dict

import aioboto3

import util

elapsed_time_threshold = 180
tableName = "crypto_price"
region = "us-east-1"


async def get_cached_price_async(asset: str) -> (Tuple[float, float, float], None):
    all_assets = await get_all_db_assets_async()
    if asset in all_assets.keys():
        print(f"'{asset}' found in db!")
        elapsed = (datetime.now() - all_assets[asset][1]).total_seconds()
        print(f"elapsed time between database insert of '{asset}' and now:  {util.format_numbers(elapsed)} seconds")
        if elapsed < elapsed_time_threshold:
            current = all_assets[asset]
            print(current)
            return current[0], current[2], current[3]
        else:
            print(f"'{asset}' is stale since {elapsed} seconds is greater than threshold of {elapsed_time_threshold} "
                  f"seconds, will update!")
    return None


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


async def store_price(asset: str, price: float, volume: float, marketcap: float):
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
                    ":d": {"S": str(datetime.now())},
                    ":v": {"N": str(volume)},
                    ":m": {"N": str(marketcap)},
                }
            )
    except Exception as e:
        print(f"Error updating database for {asset}: {str(e)}")
        raise
