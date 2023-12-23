from typing import List
from datetime import datetime
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
from googleapiclient.discovery import build
from urllib.parse import quote
from dotenv import load_dotenv
from nostril_command import run_nostril_command
import asyncio
import shelve
import httpx
import json
import os
import logging

def validate_env_vars(required_vars):
    missing_vars = [var for var in required_vars if os.getenv(var) is None]
    if missing_vars:
        missing_vars_str = ', '.join(missing_vars)
        raise ValueError(f"The following environment variables are missing: {missing_vars_str}")

# Load the environment variables
load_dotenv()

# List all the environment variables that your application depends on
required_env_vars = ['OH_AUTH_1', 'API_KEY', 'HERD_KEY', 'SAT_KEY', 'API_URL', 'GOOGLE_API_KEY', 'NOS_SEC']
validate_env_vars(required_env_vars)

ohauth1 = os.getenv('OH_AUTH_1')
api_key = os.getenv('API_KEY')
herd_key = os.getenv('HERD_KEY')
sat_key = os.getenv('SAT_KEY')
api_url= os.getenv('API_URL')
google_api_key = os.getenv('GOOGLE_API_KEY')
nos_sec = os.getenv('NOS_SEC')

cyber_herd_list = []

# Set to keep track of processed payment hashes
processed_payment_hashes = set()

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
        
def set_trigger_amount(amount):
    with shelve.open('mydata.db') as shelf:
        shelf['trigger_amount'] = amount

def get_trigger_amount():
    with shelve.open('mydata.db') as shelf:
        return shelf.get('trigger_amount')
        
async def update_and_get_trigger_amount(client: httpx.AsyncClient, amount_in_usd: float = 1.0):
    sats = await convert_to_sats(client, amount_in_usd)
    if sats is not None and sats != 0:
        set_trigger_amount(sats)
    return sats

async def get_live_video_id(api_key, channel_id):
    today = datetime.now().date()
    with shelve.open('live_video_data.db') as shelf:
        if 'video_id' in shelf and 'date' in shelf and shelf['date'] == today:
            # Return the stored video ID if it's from today
            return shelf['video_id']

    # If no valid stored ID, fetch a new one
    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "id",
        "channelId": channel_id,
        "eventType": "live",
        "type": "video",
        "key": api_key
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params)

    if response.status_code == 200:
        data = response.json()
        if 'items' in data and len(data['items']) > 0:
            video_id = data['items'][0]['id']['videoId']
            # Store the new video ID with the current date
            with shelve.open('live_video_data.db') as shelf:
                shelf['video_id'] = video_id
                shelf['date'] = today
            return video_id
    return None

async def get_balance(client: httpx.AsyncClient):
    try:
        response = await client.get(api_url, headers={'X-Api-Key': api_key})
        if response.status_code == 200:
            balance = response.json().get('balance')
            if balance != 0:
                with shelve.open('mydata.db') as shelf:
                    shelf['balance'] = balance
                return balance
            else:
                return shelf.get('balance')
        else:
            logger.error(f'Failed to retrieve balance, status code: {response.status_code}')
    except httpx.RequestError as e:
        logger.error(f'Failed to retrieve balance: {e}')

    with shelve.open('mydata.db') as shelf:
        return shelf.get('balance')

async def convert_to_sats(client: httpx.AsyncClient, amount: float):
    try:
        payload = {
            "from_": "usd",
            "amount": amount,
            "to": "sat"
        }
        response = await client.post('https://lnb.bolverker.com/api/v1/conversion', headers=headers, json=payload)
        if response.status_code == 200:
            sats = response.json()['sats']
            if sats != 0:
                with shelve.open('mydata.db') as shelf:
                    shelf['sats'] = sats
                return sats
        else:
            logger.error(f'Failed to convert amount, status code: {response.status_code}')
    except httpx.RequestError as e:
        logger.error(f'Failed to convert amount: {e}')

    with shelve.open('mydata.db') as shelf:
        return shelf.get('sats')
    
async def create_invoice(client: httpx.AsyncClient, amount: int, memo: str, key: str = sat_key): # key is to wallet
    try:
        url = "https://lnb.bolverker.com/api/v1/payments"

        headers = {
            "accept": "application/json",
            "X-API-KEY": key,
            "Content-Type": "application/json"
        }

        data = {
            "unit": "sat",
            "internal": False,
            "out": False,
            "amount": amount,
            "memo": memo,
        }

        response = await client.post(url, json=data, headers=headers)
        
        if response.status_code == 201:
            response_data = response.json()
            payment_request = response_data.get("payment_request")
            if payment_request:
                logger.info('Invoice created successfully.')
                return payment_request
            else:
                logger.error('Payment request not found in the response.')
                return None
        else:
            logger.error(f'Failed to create invoice, status code: {response.status_code}')
            return None
    except httpx.RequestError as e:
        logger.error(f'Failed to create invoice: {e}')
        return None
        
async def pay_invoice(client: httpx.AsyncClient, payment_request: str, key: str = herd_key):  # key is from wallet
    try:
        url = "https://lnb.bolverker.com/api/v1/payments"

        headers = {
            "accept": "application/json",
            "X-API-KEY": key,
            "Content-Type": "application/json"
        }

        data = {
            "unit": "sat",
            "internal": True,
            "out": True,
            "bolt11": payment_request
        }

        response = await client.post(url, json=data, headers=headers)
        
        if response.status_code == 201:
            logger.info('Invoice payment successful.')
            return 201
        else:
            logger.error(f'Failed to pay invoice, status code: {response.status_code}')
            return None
    except httpx.RequestError as e:
        logger.error(f'Failed to pay invoice: {e}')
        return None

async def remove_payment_hash_after_delay(payment_hash: str, delay: int):
    await asyncio.sleep(delay)
    processed_payment_hashes.discard(payment_hash)  # Use discard to avoid KeyError if hash is not present
    logger.debug(f"Expired payment hash: {payment_hash}")

def retrieve_messages(db_path):
    with shelve.open(db_path) as db:
        messages = dict(db)
        return messages
        
def update_message_in_db(db_path, new_message):
    formatted_message = new_message.replace('\n', ' ')
    formatted_message = formatted_message.replace('https://lightning-goats.com', '')
    with shelve.open(db_path, writeback=True) as db:
        db.clear()
        db['latest_message'] = formatted_message
        logger.info("Updated message in database.")


class HookData(BaseModel):
    payment_hash: str
    description: Optional[str] = None
    amount: Optional[float] = 0

class CyberHerdData(BaseModel):
    event_id: str
    author_pubkey: str
    pubkey: str
    nprofile: str
    lud16: str
    notified: bool = False
    payouts: int = 0

async def is_feeder_on(client: httpx.AsyncClient) -> bool:
    try:
        response = await client.get('http://10.8.0.6:8080/rest/items/FeederOverride/state', headers=headers, auth=(ohauth1, ''))
        return 200 <= response.status_code < 300 and response.text.strip() == 'ON'
    except httpx.RequestError as e:
        logger.error(f'An error occurred while checking feeder state: {e}')
        return False

async def should_trigger_feeder(balance: float, trigger: int) -> bool:
    return balance >= (trigger - 25)

async def trigger_feeder(client: httpx.AsyncClient):
    try:
        response = await client.post('http://10.8.0.6:8080/rest/rules/88bd9ec4de/runnow', headers=headers, auth=(ohauth1, ''))
        return response.status_code == 200
    except httpx.RequestError as e:
        logger.error(f'Failed to trigger the feeder rule: {e}')
        return False

async def send_payment(amount: float, difference: float, event: str):
    for retry in range(3):
         # Convert to millisats, keep 10%
        balance = await get_balance(client)
        withdraw = int(round(balance * 0.98) / 1000)
        memo = 'Reset Herd Wallet'

        payment_request = await create_invoice(client, withdraw, memo)
        payment_status = await pay_invoice(client, payment_request)

        if payment_status == 201:
            message = await run_nostr_command(nos_sec, amount, difference, event)
            update_message_in_db('messages.db', message)
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
    amount = int(data.amount / 1000) if data.amount else 0
    balance = float(await get_balance(client)) / 1000
    trigger =await update_and_get_trigger_amount(client)

    if await should_trigger_feeder(balance, trigger):
        if await trigger_feeder(client):
            # cyber_herd payouts functionality
            cyber_herd = await get_cyber_herd()
            #TODO: implement reply to thread if notified is FALSE
            #TODO: implement cyberherd payouts - will need functions for sending to lud16 addresses and looping through records
            
            await send_payment(amount, 0, "feeder_triggered")
    else:
        difference = round(trigger - float(balance))
        if amount >= float(await convert_to_sats(client, 0.01)):  # only send nostr notifications of a cent or more to reduce spamming
            message = await run_nostr_command(nos_sec, amount, difference, "sats_received")
            update_message_in_db('messages.db', message)
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

@app.post("/cyber_herd")
async def update_cyber_herd(data: List[CyberHerdData]):
    global cyber_herd_list

    for item in data:
        item_dict = item.dict()
        if item_dict not in cyber_herd_list:
            cyber_herd_list.append(item_dict)
            # TODO: nostr notification: reply to post welcoming user to the cyberherd
    return 0

@app.get("/reset_cyber_herd")
async def reset_cyber_herd():
    cyber_herd_list.clear()
    logger.info("Cyberherd list reset")
    
@app.get("/get_cyber_herd")
async def get_cyber_herd():
    return cyber_herd_list

@app.get("/trigger_amount")
async def get_trigger_amount_route():
    trigger_amount = await update_and_get_trigger_amount(client)
    if trigger_amount is not None:
        return {"trigger_amount": trigger_amount}
    else:
        raise HTTPException(status_code=404, detail="Trigger amount not found")
        
@app.get("/convert/{amount}")
async def convert(amount: float):
    sats = await convert_to_sats(client, amount)
    if sats is not None:
        return sats

@app.get("/feeder_status")
async def feeder_status():
    status = await is_feeder_on(client)
    if status is not None:
        return status
    else:
        logger.error("Failed to retrieve feeder status")
        raise HTTPException(status_code=400, detail="Failed to retrieve feeder status")

@app.get("/islive/{channel_id}")
async def live_status(channel_id: str):
    api_key = google_api_key
    video_id = await get_live_video_id(api_key, channel_id)
    if video_id:
        return {'status': 'live', 'video_id': video_id}
    else:
        return {'status': 'offline'}

@app.get("/messages")
async def get_messages():
    try:
        messages = retrieve_messages('messages.db')
        return messages
    except Exception as e:
        return {"error": str(e)}

@app.on_event("shutdown")
async def shutdown_event():
    await client.aclose()


