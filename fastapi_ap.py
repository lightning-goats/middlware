from typing import List
from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from typing import Optional
from googleapiclient.discovery import build
from urllib.parse import quote
from dotenv import load_dotenv
import messaging
import asyncio
import shelve
import httpx
import json
import os
import logging
import math
import os
import random
import time

def validate_env_vars(required_vars):
    missing_vars = [var for var in required_vars if os.getenv(var) is None]
    if missing_vars:
        missing_vars_str = ', '.join(missing_vars)
        raise ValueError(f"The following environment variables are missing: {missing_vars_str}")

# lnbits url
lnbits = 'http://127.0.0.1:3002'

#openhab url
openhab ='http://10.8.0.6:8080'

# Load the environment variables
load_dotenv()

# List all the environment variables that your application depends on
required_env_vars = ['OH_AUTH_1', 'API_KEY', 'HERD_KEY', 'SAT_KEY', 'GOOGLE_API_KEY', 'NOS_SEC', 'CYBERHERD_KEY']
validate_env_vars(required_env_vars)

ohauth1 = os.getenv('OH_AUTH_1')
api_key = os.getenv('API_KEY')
herd_key = os.getenv('HERD_KEY')
sat_key = os.getenv('SAT_KEY')
google_api_key = os.getenv('GOOGLE_API_KEY')
nos_sec = os.getenv('NOS_SEC')
cyberherd_key = os.getenv('CYBERHERD_KEY')

cyber_herd_list = []
message_list = []

# Cache for balance with an expiration time
balance_cache = {
    'balance': None,
    'expires_at': 0
}

conversion_cache = {
    'usd_to_sats': {},
    'expires_at': 0
}

trigger_amount_cache = {
    'trigger_amount': None,
    'expires_at': 0
}

live_video_cache = {
    'video_id': None,
    'date': None,
    'expires_at': 0
}

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

def convert_to_dict(message_data):
    # If the message_data is just a string, assume it's the content of the message
    if isinstance(message_data, str):
        return {"content": message_data}
    
    # If it's already a dictionary, return as is
    elif isinstance(message_data, dict):
        return message_data

def get_trigger_amount():
    return trigger_amount_cache['trigger_amount']

async def update_and_get_trigger_amount(client: httpx.AsyncClient, amount_in_usd: float = 1.25, force_refresh=False):
    current_time = time.time()
    cached_trigger_amount = trigger_amount_cache['trigger_amount']
    expires_at = trigger_amount_cache['expires_at']

    # Check if the cache is valid and not expired
    if cached_trigger_amount is not None and current_time < expires_at and not force_refresh:
        return cached_trigger_amount

    try:
        sats = await convert_to_sats(client, amount_in_usd)
        if sats is not None and sats != 0:
            trigger_amount_cache['trigger_amount'] = sats
            trigger_amount_cache['expires_at'] = current_time + 300  # Cache expires in 300 seconds
            return sats
        else:
            return get_trigger_amount()
    except Exception as e:
        logger.error(f'Failed to update and get trigger amount: {e}')
        return get_trigger_amount()

async def get_live_video_id(api_key, channel_id):
    current_time = time.time()
    today = datetime.now().date()
    cached_video_id = live_video_cache['video_id']
    cached_date = live_video_cache['date']
    expires_at = live_video_cache['expires_at']

    # Check if the cache is valid and not expired, and the date matches today
    if cached_video_id is not None and current_time < expires_at and cached_date == today:
        return cached_video_id

    # If no valid cached ID or the cache is expired, fetch a new one
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
            # Update the cache with the new video ID, date, and set an expiration time (12 hours)
            live_video_cache['video_id'] = video_id
            live_video_cache['date'] = today
            live_video_cache['expires_at'] = current_time + 43200  # Cache expires in 12 hours
            return video_id

    return None

async def get_balance(client: httpx.AsyncClient, force_refresh=False):
    current_time = time.time()
    cached_balance = balance_cache['balance']
    expires_at = balance_cache['expires_at']

    # Check if the cache is valid and not expired
    if cached_balance is not None and current_time < expires_at and not force_refresh:
        return cached_balance

    try:
        response = await client.get(F'{lnbits}/api/v1/wallet', headers={'X-Api-Key': api_key})
        if response.status_code == 200:
            balance = response.json().get('balance')
            if balance is not None:
                balance_cache['balance'] = balance
                balance_cache['expires_at'] = current_time + 300  # Cache expires in 300 seconds
                return balance
            else:
                return cached_balance  # Return the cached balance if the new balance is None
        else:
            logger.error(f'Failed to retrieve balance, status code: {response.status_code}')
    except httpx.RequestError as e:
        logger.error(f'Failed to retrieve balance: {e}')

    return cached_balance  # Return the cached balance if the request fails

async def convert_to_sats(client: httpx.AsyncClient, amount: float, force_refresh=False):
    current_time = time.time()
    cached_conversion = conversion_cache['usd_to_sats'].get(amount)
    expires_at = conversion_cache['expires_at']

    # Check if the cache is valid and not expired
    if cached_conversion is not None and current_time < expires_at and not force_refresh:
        return cached_conversion

    try:
        payload = {
            "from_": "usd",
            "amount": amount,
            "to": "sat"
        }
        response = await client.post(f'{lnbits}/api/v1/conversion', headers=headers, json=payload)
        if response.status_code == 200:
            sats = response.json()['sats']
            if sats is not None:
                conversion_cache['usd_to_sats'][amount] = sats
                conversion_cache['expires_at'] = current_time + 300  # Cache expires in 300 seconds
                return sats
            else:
                return cached_conversion  # Return the cached conversion rate if the new rate is None
        else:
            logger.error(f'Failed to convert amount, status code: {response.status_code}')
    except httpx.RequestError as e:
        logger.error(f'Failed to convert amount: {e}')

    return cached_conversion  # Return the cached conversion rate if the request fails

async def create_invoice(client: httpx.AsyncClient, amount: int, memo: str, key: str = cyberherd_key): # key is to wallet
    try:
        url = f'{lnbits}/api/v1/payments'

        headers = {
            "accept": "application/json",
            "X-API-KEY": key,
            "Content-Type": "application/json"
        }

        data = {
            "unit": "sat",
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
        url = f'{lnbits}/api/v1/payments'

        headers = {
            "accept": "application/json",
            "X-API-KEY": key,
            "Content-Type": "application/json"
        }

        data = {
            "unit": "sat",
            "out": True,
            "bolt11": payment_request
        }

        response = await client.post(url, json=data, headers=headers)
        
        if response.status_code == 201:
            logger.info('Invoice payment successful.')
            return 201
        else:
            logger.error(f'Failed to pay invoice, status code: {response.status_code}')
            return response.status_code
    except httpx.RequestError as e:
        logger.error(f'Failed to pay invoice: {e}')
        return None

def retrieve_messages():
    try:
        json_data = json.dumps(message_list)
        #message_list.clear()  # Reset the list
        return json_data
    except Exception as e:
        logger.error(f"Error retrieving messages: {e}")
        return json.dumps({"error": str(e)})
        
def update_message_in_db(new_message=None):
    global message_list
    
    formatted_message = ''
    if new_message:
        formatted_message = new_message.replace('\n', ' ')

    if new_message:
        message_list.append(formatted_message)

        # If the number of messages exceeds 3, remove the oldest one
        while len(message_list) > 5:
            message_list.pop(0)  # Remove the first (oldest) message

class HookData(BaseModel):
    payment_hash: str
    description: Optional[str] = None
    amount: Optional[float] = 0

class CyberHerdData(BaseModel):
    display_name: str
    event_id: str
    kind: str = None
    pubkey: str
    nprofile: str
    lud16: str
    notified: str = None
    payouts: int = 0
    
class CyberHerdTreats(BaseModel):
    pubkey: str
    amount: int
    
class InvoiceRequest(BaseModel):
    amount: int
    memo: str
    key: str = herd_key  # Optional in the request body; will use herd_key if not provided
    
class Message(BaseModel):
    content: str
    

async def fetch_cyberherd_targets(client: httpx.AsyncClient):
    url = f'{lnbits}/splitpayments/api/v1/targets'
    headers = {
        'accept': 'application/json',
        'X-API-KEY': cyberherd_key  # Use the cyberherd_key from the environment variables
    }
    response = await client.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        return {'error': 'Request failed with status code {}'.format(response.status_code)}

async def create_cyberherd_targets(client: httpx.AsyncClient, new_targets_data, initial_targets):
    fetched_wallets = {item['wallet']: item for item in initial_targets}
    
    # Predefined wallet
    predefined_wallet = {'wallet': 'sat@bolverker.com', 'alias': 'Sat', 'percent': 80}
    
    # Initialize combined_wallets with any wallet not the predefined, to avoid duplication
    combined_wallets = []
    
    for item in new_targets_data:
        wallet = item['wallet']
        name = item.get('alias', 'Unknown')
        if wallet not in fetched_wallets and wallet != predefined_wallet['wallet']:
            combined_wallets.append({'wallet': wallet, 'alias': name})
    
    # Add fetched wallets, excluding the predefined one to avoid duplication
    for wallet, details in fetched_wallets.items():
        if wallet != predefined_wallet['wallet']:
            combined_wallets.append({'wallet': wallet, 'alias': details.get('alias', 'Unknown')})
    
    # Ensure total percent allocation does not exceed 100%
    total_percent_allocation = predefined_wallet['percent']
    targets_list = [predefined_wallet]
    
    # Determine allocation for cyberherd splits
    if combined_wallets:
        percent_per_wallet = (100 - total_percent_allocation) // len(combined_wallets)
        for wallet in combined_wallets:
            targets_list.append({
                'wallet': wallet['wallet'], 
                'alias': wallet['alias'], 
                'percent': percent_per_wallet
            })
            total_percent_allocation += percent_per_wallet
    
    # If the total allocation is less than 100, adjust the last added wallet's percent
    if total_percent_allocation < 100 and targets_list:
        last_wallet = targets_list[-1]
        last_wallet['percent'] += (100 - total_percent_allocation)
    
    # Construct the final targets structure
    targets = {"targets": targets_list}
    
    return targets


async def update_cyberherd_targets(client: httpx.AsyncClient, targets):
    url = f'{lnbits}/splitpayments/api/v1/targets'
    headers = {
        'accept': 'application/json',
        'X-API-KEY': cyberherd_key, 
        'Content-Type': 'application/json'
    }
    
    data = json.dumps(targets)
    
    response = await client.put(url, headers=headers, content=data)
    
    if response.status_code == 200:
        print("Success:", response.json())
    else:
        print("Error:", response.text)
        
def get_cyber_herd_list():
    with shelve.open('cyber_herd_data.db') as shelf:
        return shelf.get('cyber_herd_list', [])

def update_cyber_herd_list(new_data: List[dict], reset=False):  
    db_path = 'cyber_herd_data.db'
    
    if reset:
        # Close and delete the database file
        with shelve.open(db_path) as shelf:
            shelf.close()  # Explicitly close the shelf before deleting the file
        os.remove(db_path)
        print("Database has been completely deleted.")
        return

    with shelve.open(db_path, writeback=True) as shelf:
        cyber_herd_dict = {item['pubkey']: item for item in shelf.get('cyber_herd_list', [])}

        for new_item_dict in new_data:  # new_item_dict is already a dictionary
            pubkey = new_item_dict['pubkey']
            cyber_herd_dict[pubkey] = new_item_dict  # Update or add the new item

        updated_cyber_herd_list = list(cyber_herd_dict.values())[-5:]
        shelf['cyber_herd_list'] = updated_cyber_herd_list

async def is_feeder_on(client: httpx.AsyncClient) -> bool:
    try:
        response = await client.get(f'{openhab}/rest/items/FeederOverride/state', headers=headers, auth=(ohauth1, ''))
        return 200 <= response.status_code < 300 and response.text.strip() == 'ON'
    except httpx.RequestError as e:
        logger.error(f'An error occurred while checking feeder state: {e}')
        return False

async def should_trigger_feeder(balance: float, trigger: int) -> bool:
    return balance >= (trigger - 25)

async def trigger_feeder(client: httpx.AsyncClient):
    try:
        response = await client.post(f'{openhab}/rest/rules/88bd9ec4de/runnow', headers=headers, auth=(ohauth1, ''))
        return response.status_code == 200
    except httpx.RequestError as e:
        logger.error(f'Failed to trigger the feeder rule: {e}')
        return False

async def send_payment(balance):
    withdraw = int(balance) * 0.99        
    memo = 'Reset Herd Wallet'
    payment_request = await create_invoice(client, withdraw, memo)
    
    for retry in range(3):
        payment_status = await pay_invoice(client, payment_request)

        if payment_status == 201:
            return payment_status
        else:
            logger.error(f"Failed to send payment on attempt {retry + 1}, status code: {payment_status}")

# FastAPI route definitions
@app.post('/lnurlp/hooker')
async def webhook(data: HookData):
    # Debug output for payment data
    logger.debug(f"Received payment data: {data}")
        
    if await is_feeder_on(client):
        logger.info('Feeder off, skipping...')
        return 'feeder_off'
    
    description = data.description
    amount = int(data.amount / 1000) if data.amount else 0
    balance = round(int(await get_balance(client, True)) / 1000)
    trigger = await update_and_get_trigger_amount(client, True)
    
    if await should_trigger_feeder(balance, trigger):
        if await trigger_feeder(client):
            status = await send_payment(balance)  # reset herd wallet
            
            if status == 201:
                message = await messaging.make_messages(nos_sec, amount, 0, "feeder_triggered")
                update_message_in_db(message)

    else:
        difference = round(trigger - float(balance))
        if amount >= float(await convert_to_sats(client, 0.01, True)):  # only send nostr notifications of a cent or more to reduce spamming
            message = await messaging.make_messages(nos_sec, amount, difference, "sats_received")
            update_message_in_db(message)
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

@app.post("/create-invoice/")
async def create_invoice_route(invoice_request: InvoiceRequest):
    async with httpx.AsyncClient() as client:
        # Use provided key if available, otherwise default to herd_key
        key = invoice_request.key if invoice_request.key else herd_key
        payment_request = await create_invoice(client, invoice_request.amount, invoice_request.memo, key)
        
        if payment_request:
            return {"payment_request": payment_request}
        else:
            raise HTTPException(status_code=400, detail="Failed to create invoice or payment request not found.")

@app.post("/cyber_herd")
async def update_cyber_herd(data: List[CyberHerdData]):
    cyber_herd_list = get_cyber_herd_list()

    balance = float(await get_balance(client)) / 1000
    trigger = await update_and_get_trigger_amount(client)
    difference = round(trigger - balance)

    # Fetch initial cyberherd targets to initialize
    initial_targets = await fetch_cyberherd_targets(client)
    existing_wallets = {item['wallet']: item for item in initial_targets}

    cyber_herd_dict = {item['pubkey']: item for item in cyber_herd_list}
    targets_to_create = []

    for item in data:
        item_dict = item.dict()
        pubkey = item_dict['pubkey']
        
        if pubkey not in cyber_herd_dict:
            cyber_herd_dict[pubkey] = item_dict
            cyber_herd_dict[pubkey]['notified'] = None
        
            if item_dict['lud16'] not in existing_wallets:
                targets_to_create.append({
                    'wallet': item_dict['lud16'],  # Use lud16 as wallet
                    'alias': item_dict['pubkey'],  # set pubkey as alias
                    # 'percent' will be determined later
                })

    if targets_to_create:
        targets = await create_cyberherd_targets(client, targets_to_create, initial_targets)
        if targets:
            await update_cyberherd_targets(client, targets)
    for item in data:
        item_dict = item.dict()
        pubkey = item_dict['pubkey']
        # Check if 'notified' is None or empty, indicating notification has not been sent
        if not cyber_herd_dict[pubkey].get('notified'):
            message = await messaging.make_messages(nos_sec, 0, difference, "cyber_herd", item_dict)
            update_message_in_db(message)
            cyber_herd_dict[pubkey]['notified'] = messaging.notified.get('id')

    updated_cyber_herd_list = list(cyber_herd_dict.values())[-10:]
    update_cyber_herd_list(updated_cyber_herd_list)

    return {"status": "success"}


@app.get("/get_cyber_herd")
async def get_cyber_herd():
    return get_cyber_herd_list()

@app.get("/reset_cyber_herd")
async def reset_cyber_herd():
    # Reset the cyber herd list in the database
    update_cyber_herd_list([], reset=True)

    headers = {
        'accept': 'application/json',
        'X-API-KEY': cyberherd_key  # Use the API key securely
    }
    url = f'{lnbits}/splitpayments/api/v1/targets?api-key={cyberherd_key}'

    try:
        response = await client.delete(url, headers=headers)
        if response.status_code == 200:
            # Handle successful response
            return {"status": "success", "message": "CyberHerd reset successfully."}
        else:
            # Handle non-successful responses
            return {"status": "error", "message": f"Failed to reset CyberHerd, status code: {response.status_code}"}
    except httpx.RequestError as e:
        # Log and handle request errors
        logger.error(f"Request failed: {e}")
        return {"status": "error", "message": "Request to API failed."}

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


@app.get("/messages", response_model=List[Message])
async def get_messages():
    global message_list
    
    try:
        json_messages = retrieve_messages()
        messages = json.loads(json_messages)
        formatted_messages = [Message(content=msg) for msg in messages if isinstance(msg, str)]
        return formatted_messages
    except Exception as e:
        logger.error(f"Error in /messages route: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/messages/cyberherd_treats")
async def handle_cyberherd_treats(data: CyberHerdTreats):
    try:
        pubkey = data.pubkey
        amount = data.amount
        cyber_herd_dict = {item['pubkey']: item for item in get_cyber_herd_list()}

        if pubkey in cyber_herd_dict:
            message_data = await messaging.make_messages(nos_sec, amount, 0, "cyber_herd_treats", cyber_herd_dict[pubkey])
            update_message_in_db(message_data)
            return {"status": "success"}
        else:
            return {"status": "error", "message": "Invalid pubkey"}
    except Exception as e:
        logger.error(f"Error in /messages/cyberherd_treats route: {e}")
        raise HTTPException(status_code=500, detail=str(e))
        
@app.get("/messages/info")
async def create_info_message():
    global message_list
    
    try:
        # Create a new informational message
        message_data = await messaging.make_messages(nos_sec, 0, 0, "interface_info")
        update_message_in_db(message_data)
        json_messages = retrieve_messages()
        messages = json.loads(json_messages)

        formatted_messages = [Message(content=msg) for msg in messages if isinstance(msg, str)]
        return formatted_messages
    except Exception as e:
        logger.error(f"Error in /messages/info route: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/messages/reset")
async def reset_all_mesages():
    global message_list
    message_list=[]

@app.on_event("shutdown")
async def shutdown_event():
    await client.aclose()


