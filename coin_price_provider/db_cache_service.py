import logging
from datetime import datetime
from typing import Tuple, Dict, Optional
from decimal import Decimal

import aioboto3
from botocore.exceptions import ClientError
from cryptofund20x_misc.custom_formatter import CustomFormatter

import util

# Constants
ELAPSED_TIME_THRESHOLD = 180
TABLE_NAME = "crypto_price"
REGION = "us-east-1"

# Set up logging
logger = logging.getLogger(__name__)
handler = logging.StreamHandler()
handler.setFormatter(CustomFormatter())
logger.addHandler(handler)
logger.setLevel(logging.INFO)


def validate_asset_data(asset: str, price: float, volume: float, marketcap: float) -> bool:
    """
    Validate input parameters for asset data.

    Returns:
        bool: True if all parameters are valid, False otherwise
    """
    try:
        if not isinstance(asset, str) or not asset.strip():
            logger.error("Invalid asset name: must be a non-empty string")
            return False

        for value, name in [(price, 'price'), (volume, 'volume'), (marketcap, 'marketcap')]:
            if not isinstance(value, (int, float, Decimal)):
                logger.error(f"Invalid {name}: must be a number")
                return False
            if value < 0:
                logger.error(f"Invalid {name}: must be non-negative")
                return False

        return True
    except Exception as e:
        logger.error(f"Error validating asset data: {str(e)}")
        return False


async def get_cached_price_async(asset: str) -> Optional[Tuple[float, float, float]]:
    """
    Get cached price data for an asset if available and not stale.

    Args:
        asset: Asset name to look up

    Returns:
        Tuple of (price, volume, marketcap) if valid cached data exists, None otherwise
    """
    try:
        if not asset or not isinstance(asset, str):
            logger.error(f"Invalid asset parameter: {asset}")
            return None

        logger.info(f"Attempting to retrieve cached price for asset: {asset}")
        all_assets = await get_all_db_assets_async()

        if not all_assets:
            logger.warning("No assets retrieved from database")
            return None

        if asset in all_assets:
            logger.info(f"Asset '{asset}' found in database")
            current_data = all_assets[asset]
            elapsed = (datetime.now() - current_data[1]).total_seconds()

            logger.info(f"Time since last update for '{asset}': {util.format_numbers(elapsed)} seconds")

            if elapsed < ELAPSED_TIME_THRESHOLD:
                logger.info(f"Returning cached data for '{asset}': price={current_data[0]}, "
                            f"volume={current_data[2]}, marketcap={current_data[3]}")
                return current_data[0], current_data[2], current_data[3]
            else:
                logger.info(f"Cached data for '{asset}' is stale ({elapsed} seconds old, threshold is "
                            f"{ELAPSED_TIME_THRESHOLD} seconds)")
                return None
        else:
            logger.info(f"No cached data found for asset: {asset}")
            return None

    except Exception as e:
        logger.error(f"Error retrieving cached price for {asset}: {str(e)}")
        return None


async def get_all_db_assets_async() -> Dict:
    """
    Async function to fetch all asset items from DynamoDB.

    Returns:
        Dict containing asset data, empty dict if error occurs
    """
    session = aioboto3.Session()
    try:
        async with session.client('dynamodb', region_name=REGION) as dynamodb_local:
            logger.info("Initiating database scan for all assets")
            response = await dynamodb_local.scan(TableName=TABLE_NAME)

            result = {}
            for item in response.get("Items", []):
                try:
                    name = item["name"]["S"]
                    price = float(item["usd_price"]["N"])
                    marketcap = float(item["current_marketcap_usd"]["N"])
                    volume = float(item["volume_last_24_hours"]["N"])
                    dt = util.string_datetime_to_datetime_object(item["datetime"]["S"])

                    result[name] = (price, dt, volume, marketcap)
                    logger.debug(f"Processed asset data for {name}")
                except (KeyError, ValueError) as e:
                    logger.error(f"Error processing item from database: {str(e)}, Item: {item}")
                    continue

            logger.info(f"Successfully retrieved {len(result)} assets from database")
            return result

    except ClientError as e:
        logger.error(f"AWS ClientError in get_all_db_assets_async: {str(e)}")
        return {}
    except Exception as e:
        logger.error(f"Unexpected error in get_all_db_assets_async: {str(e)}")
        return {}


async def store_price(asset: str, price: float, volume: float, marketcap: float) -> bool:
    """
    Store asset data in the database.

    Args:
        asset: Asset name
        price: Current price in USD
        volume: 24h volume
        marketcap: Current market cap in USD

    Returns:
        bool: True if store operation was successful, False otherwise
    """
    logger.info(f"Attempting to store price data for asset: {asset}")

    if not validate_asset_data(asset, price, volume, marketcap):
        return False

    session = aioboto3.Session()
    try:
        async with session.client('dynamodb', region_name=REGION) as dynamodb:
            current_time = str(datetime.now())

            update_expression = """SET 
                usd_price = :p, 
                #datetime = :d, 
                volume_last_24_hours = :v, 
                current_marketcap_usd = :m"""

            await dynamodb.update_item(
                TableName=TABLE_NAME,
                Key={"name": {"S": asset}},
                ExpressionAttributeNames={"#datetime": "datetime"},
                UpdateExpression=update_expression,
                ExpressionAttributeValues={
                    ":p": {"N": str(price)},
                    ":d": {"S": current_time},
                    ":v": {"N": str(volume)},
                    ":m": {"N": str(marketcap)},
                }
            )

            logger.info(f"Successfully stored price data for {asset} at {current_time}")
            return True

    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_message = e.response['Error']['Message']
        logger.error(f"AWS ClientError storing price for {asset}: {error_code} - {error_message}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error storing price for {asset}: {str(e)}")
        raise