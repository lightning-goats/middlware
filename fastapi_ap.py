from typing import List
from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from typing import Optional
from googleapiclient.discovery import build
from urllib.parse import quote
from dotenv import load_dotenv
from messaging import make_messages
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
message_list = []

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
    # If the message_data is just a string, we'll assume it's the content of the message
    if isinstance(message_data, str):
        return {"content": message_data}
    
    # If it's already a dictionary, return as is
    elif isinstance(message_data, dict):
        return message_data
        
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

async def make_lnurl_payment(lud16: str, amount: int, description: str = None, key: str = herd_key) -> dict:
    try:
        # Define the headers for the request
        headers = {
            "accept": "application/json",
            "X-API-KEY": key,
            "Content-Type": "application/json"
        }

        # Fetch lnurl data directly from the API
        lnurl_url = f"https://lnb.bolverker.com/api/v1/lnurlscan/{lud16}"
        lnurl_response = await client.get(lnurl_url, headers=headers)
        lnurl_response.raise_for_status()
        lnurl_data = lnurl_response.json()

        # Validate the amount against minSendable and maxSendable
        if not (lnurl_data["minSendable"] <= amount <= lnurl_data["maxSendable"]):
            raise ValueError(f"Amount {amount} is not within the allowed range of {lnurl_data['minSendable']} to {lnurl_data['maxSendable']} millisatoshis.")

        # Validate the length of the comment
        #if comment and len(comment) > lnurl_data["commentAllowed"]:
        #    raise ValueError(f"Comment length exceeds the allowed limit of {lnurl_data['commentAllowed']} characters.")

        # Prepare the payload for the payment request
        payload = {
            "description_hash": lnurl_data["description_hash"],
            "callback": lnurl_data["callback"],
            "amount": amount,
            "comment":comment if comment is not None else "Cyber Herd Treats",
            "memo": description if description is not None else "Cyber Herd Treats",
            "description": description if description is not None else "Cyber Herd Treats",
            "payerData": {
                "pubkey": "669ebbcccf409ee0467a33660ae88fd17e5379e646e41d7c236ff4963f3c36b6"
            }
        }

        # Make the payment request only if amount is validated
        payment_url = "https://lnb.bolverker.com/api/v1/payments/lnurl"
        payment_response = await client.post(payment_url, headers=headers, json=payload)
        payment_response.raise_for_status()
        return payment_response.json()

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP request failed with status code: {e.response.status_code}, response: {e.response.text}")
        raise
    except httpx.RequestError as e:
        logger.error(f"HTTP request failed: {e}")
        raise
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        raise

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
        while len(message_list) > 3:
            message_list.pop(0)  # Remove the first (oldest) message

class HookData(BaseModel):
    payment_hash: str
    description: Optional[str] = None
    amount: Optional[float] = 0

class CyberHerdData(BaseModel):
    display_name: str
    event_id: str
    author_pubkey: str
    pubkey: str
    nprofile: str
    lud16: str
    notified: bool = False
    payouts: int = 0
    
def get_cyber_herd_list():
    with shelve.open('cyber_herd_data.db') as shelf:
        return shelf.get('cyber_herd_list', [])

def update_cyber_herd_list(new_data: List[dict], reset=False):  
    with shelve.open('cyber_herd_data.db', writeback=True) as shelf:
        if reset:
            # This removes the key entirely from the database
            del shelf['cyber_herd_list']
        else:
            cyber_herd_dict = {item['pubkey']: item for item in shelf.get('cyber_herd_list', [])}

            for new_item_dict in new_data:  # new_item_dict is already a dictionary
                pubkey = new_item_dict['pubkey']
                cyber_herd_dict[pubkey] = new_item_dict  # Update or add the new item

            updated_cyber_herd_list = list(cyber_herd_dict.values())[-10:]
            shelf['cyber_herd_list'] = updated_cyber_herd_list

class Message(BaseModel):
    content: str

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
            message = await make_messages(nos_sec, amount, difference, event)
            update_message_in_db(message)
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

    # Add the payment hash to the set and schedule its removal klunk work around for lnbits bug
    processed_payment_hashes.add(data.payment_hash)
    asyncio.create_task(remove_payment_hash_after_delay(data.payment_hash, 5))
        
    if await is_feeder_on(client):
        logger.info('Feeder off, skipping...')
        return 'feeder_off'
    
    description = data.description
    amount = int(data.amount / 1000) if data.amount else 0
    balance = int(await get_balance(client)) / 1000
    trigger = await update_and_get_trigger_amount(client)

    if await should_trigger_feeder(balance, trigger):
        if await trigger_feeder(client):
            cyber_herd_list = get_cyber_herd_list()
            cyber_herd_dict = {item['lud16']: item for item in cyber_herd_list}
            num_members = len(cyber_herd_dict)
            
            if num_members > 0:
                random_factor = random.uniform(0.25, 0.48)
                payment_per_member = (trigger * random_factor) / num_members

                for lud16, item in cyber_herd_dict.items():
                    payment_response = await make_lnurl_payment(lud16, int(payment_per_member),'Cyber Herd Treats')

                    # Check if the payment was successful
                    if 'payment_hash' in payment_response:
                        item['payouts'] += payment_per_member / 1000
                        
                        update_cyber_herd_list(list(cyber_herd_dict.values()))
                        
                    await asyncio.sleep(.25) # wait a little bit before sending the next payment
                
            await send_payment(amount, 0, "feeder_triggered") #reset herd wallet
            
            #TODO:message = await make_messages(nos_sec, 0, 0, "cyber_herd_treats", cyber_herd_list)
            #TODO:update_message_in_db(message)
    else:
        difference = round(trigger - float(balance))
        if amount >= float(await convert_to_sats(client, 0.01)):  # only send nostr notifications of a cent or more to reduce spamming
            message = await make_messages(nos_sec, amount, difference, "sats_received")
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

@app.post("/cyber_herd")
async def update_cyber_herd(data: List[CyberHerdData]):
    # Retrieve the current cyber herd list from the shelve database
    cyber_herd_list = get_cyber_herd_list()

    balance = float(await get_balance(client)) / 1000
    trigger = await update_and_get_trigger_amount(client)
    difference = round(trigger - float(balance))

    # Create a dictionary for quick lookup using pubkey
    cyber_herd_dict = {item['pubkey']: item for item in cyber_herd_list}

    # Append new items to the list
    for item in data:
        item_dict = item.dict()
        pubkey = item_dict['pubkey']
        
        # Check if the item is new or if its notified status is False
        if pubkey not in cyber_herd_dict or not cyber_herd_dict[pubkey].get('notified', False):
            item_dict['notified'] = False  # Set notified to False for new items
            cyber_herd_dict[pubkey] = item_dict  # Update or add the item in the dictionary

            # Send message and update notified status
            if not item_dict['notified']:
                message = await make_messages(nos_sec, 0, difference, "cyber_herd", item_dict)
                update_message_in_db(message)
                item_dict['notified'] = True  # Update notified status

    # Update the list from the dictionary and trim to the last 10 records
    updated_cyber_herd_list = list(cyber_herd_dict.values())[-10:]

    # Update the cyber herd list in the database
    update_cyber_herd_list(updated_cyber_herd_list)

    return {"status": "success"}


@app.get("/get_cyber_herd")
async def get_cyber_herd():
    return get_cyber_herd_list()

@app.get("/reset_cyber_herd")
async def reset_cyber_herd():
    update_cyber_herd_list([], reset=True)

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

@app.get("/messages/info")
async def create_info_message():
    global message_list
    
    try:
        # Create a new informational message
        message_data = await make_messages(nos_sec, 0, 0, "interface_info")
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


