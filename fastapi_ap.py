from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
import httpx
from googleapiclient.discovery import build
import logging
from urllib.parse import quote
from dotenv import load_dotenv
import os
from nostril_command import run_nostril_command
import asyncio

# Set to keep track of processed payment hashes
processed_payment_hashes = set()

# Load the environment variables
load_dotenv()

ohauth1 = os.getenv('OH_AUTH_1')
api_key = os.getenv('API_KEY')
wallet_id = os.getenv('WALLET_ID')
api_url = os.getenv('API_URL')
google_api_key = os.getenv('GOOGLE_API_KEY')
nos_sec = os.getenv('NOS_SEC')

# List all the environment variables that your application depends on
required_env_vars = ['OH_AUTH_1', 'API_KEY', 'WALLET_ID', 'API_URL', 'GOOGLE_API_KEY', 'NOS_SEC']

# Check which environment variables are set
missing_vars = [var for var in required_env_vars if os.getenv(var) is None]

# If there are any missing variables, raise an error and log or print their names
if missing_vars:
    missing_vars_str = ', '.join(missing_vars)
    raise ValueError(f"The following environment variables are missing: {missing_vars_str}")

# Define headers for the HTTP request
headers = {
    'accept': '*/*',
    'Content-Type': 'application/json',
}

# Read environment
app_env = os.getenv('APP_ENV', 'production')

# Initialize a logger
logger = logging.getLogger(__name__)

# Set up logging
if app_env == 'development':
    logging.basicConfig(level=logging.DEBUG)
    logger.debug("Running in Development mode")
elif app_env == 'production':
    logging.basicConfig(
        level=logging.WARNING,
        filename='app.log',
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger.warning("Running in Production mode")
else:
    logging.basicConfig(level=logging.INFO)
    logger.info("Running in unspecified mode")
    
# Create a FastAPI app
app = FastAPI()
client = httpx.AsyncClient()

#  helper functions
async def get_live_video_id(api_key, channel_id):
    def synchronous_get_video_id():
        youtube = build('youtube', 'v3', developerKey=api_key)
        request = youtube.search().list(
            part="id",
            channelId=channel_id,
            eventType="live",
            type="video"
        )
        response = request.execute()

        if len(response['items']) > 0:
            return response['items'][0]['id']['videoId']
        else:
            return None

    return await asyncio.to_thread(synchronous_get_video_id)

async def get_balance(client: httpx.AsyncClient):
    try:
        response = await client.get(api_url, headers={'X-Api-Key': api_key})
        if response.status_code == 200:
            return response.json().get('balance')
        else:
            logger.error(f'Failed to retrieve balance, status code: {response.status_code}')
    except httpx.RequestError as e:
        logger.error(f'Failed to retrieve balance: {e}')
    return None

async def convert_to_sats(client: httpx.AsyncClient, amount: float):
    try:
        payload = {
            "from_": "usd",
            "amount": amount,
            "to": "sat"
        }
        response = await client.post('https://lnb.bolverker.com/api/v1/conversion', headers=headers, json=payload)
        if response.status_code == 200:
            return response.json()['sats']
        else:
            logger.error(f'Failed to convert amount, status code: {response.status_code}')
    except httpx.RequestError as e:
        logger.error(f'Failed to convert amount: {e}')
    return None

async def send_lnurl_payment(client: httpx.AsyncClient):
    try:
        url = 'https://lnb.bolverker.com/api/v1/payments/lnurl'
        
        # Convert to millisats, keep 2%
        balance = await get_balance(client)
        withdraw = round(balance * 0.98)
        withdraw = round(withdraw / 1000) * 1000

        headers = {
            'accept': 'application/json',
            'X-API-KEY': wallet_id,
            'Content-Type': 'application/json'
        }

        data = {
            "description_hash": "dd9f408b0ebc0a7e55c47a4ada760ff4875e0d1692f9ef5761abccda129478cc",
            "callback": "https://lnb.bolverker.com/lnurlp/api/v1/lnurl/cb/lnaddr/QzBo8z",
            "amount": withdraw,
            "comment": "⚡Lightning Goats⚡ Thank you for the treats!",
            "description": "Lightning Goats - reset herd wallet"
        }

        response = await client.post(url, headers=headers, json=data)  # Using the passed client instance
        if response.status_code == 200:
            return 200
        else:
            logger.error(f'Failed to send payment, status code: {response.status_code}')
            return response.status_code
    except httpx.RequestError as e:
        logger.error(f'Failed to send payment: {e}')
        return None

async def remove_payment_hash_after_delay(payment_hash: str, delay: int):
    await asyncio.sleep(delay)
    processed_payment_hashes.discard(payment_hash)  # Use discard to avoid KeyError if hash is not present
    logger.debug(f"Expired payment hash: {payment_hash}")


class HookData(BaseModel):
    payment_hash: str
    description: Optional[str] = None
    amount: Optional[float] = 0

async def is_feeder_on(client: httpx.AsyncClient) -> bool:
    try:
        response = await client.get('http://10.8.0.6:8080/rest/items/FeederOverride/state', headers=headers, auth=(ohauth1, ''))
        return 200 <= response.status_code < 300 and response.text.strip() == 'ON'
    except httpx.RequestError as e:
        logger.error(f'An error occurred while checking feeder state: {e}')
        return False

async def should_trigger_feeder(balance: float, trigger: int) -> bool:
    return balance >= (trigger - 50)

async def trigger_feeder(client: httpx.AsyncClient):
    try:
        response = await client.post('http://10.8.0.6:8080/rest/rules/88bd9ec4de/runnow', headers=headers, auth=(ohauth1, ''))
        return response.status_code == 200
    except httpx.RequestError as e:
        logger.error(f'Failed to trigger the feeder rule: {e}')
        return False

async def send_payment(amount: float, difference: float, event: str):
    for retry in range(3):
        payment_status = await send_lnurl_payment(client)
        if payment_status == 200:
            await run_nostril_command(nos_sec, amount, difference, event)
            break
        else:
            logger.error(f"Failed to send payment on attempt {retry + 1}, status code: {payment_status}")

# FastAPI route definitions
@app.post('/lnurlp/hooker')
async def webhook(data: HookData):
    # Debug output for payment data
    logger.debug(f"Received payment data: {data}")
    
    # Skip if payment has already been processed
    if data.payment_hash in processed_payment_hashes:
        logger.info(f'Payment with hash {data.payment_hash} already processed, skipping...')
        return 'payment_already_processed'

    # Add the payment hash to the set and schedule its removal
    processed_payment_hashes.add(data.payment_hash)
    asyncio.create_task(remove_payment_hash_after_delay(data.payment_hash, 5))
        
    if await is_feeder_on(client):
        logger.info('Feeder off, skipping...')
        return 'feeder_off'
    
    description = data.description
    amount = data.amount / 1000 if data.amount else 0
    balance = float(await get_balance(client)) / 1000
    trigger = float(await convert_to_sats(client, 1))  # dollar amount - goal to reach for triggering feeder

    if await should_trigger_feeder(balance, trigger):
        if await trigger_feeder(client):
            await send_payment(amount, 0, "feeder_triggered")
    else:
        difference = round(trigger - float(balance))
        if amount >= float(await convert_to_sats(client, 0.01)):  # only send nostr notifications of a cent or more to reduce spamming
            await run_nostril_command(nos_sec, amount, difference, "sats_received")
            return "received"
    
    
    return 'payment_processed'

@app.get("/balance")
async def balance():
    balance = await get_balance(client)
    if balance is not None:
        return balance
    else:
        logger.error("Failed to retrieve balance")
        raise HTTPException(status_code=400, detail="Failed to retrieve balance")
        
@app.get("/convert/{amount}")
async def convert(amount: float):
    sats = await convert_to_sats(client, amount)
    if sats is not None:
        return sats

@app.get("/islive/{channel_id}")
async def live_status(channel_id: str):
    api_key = google_api_key
    video_id = await get_live_video_id(api_key, channel_id)
    if video_id:
        return {'status': 'live', 'video_id': video_id}
    else:
        return {'status': 'offline'}

@app.on_event("shutdown")
async def shutdown_event():
    await client.aclose()


