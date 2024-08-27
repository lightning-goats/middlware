from typing import List, Optional
from datetime import datetime
from fastapi import FastAPI, HTTPException, Path, Query, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from googleapiclient.discovery import build
from googleapiclient.discovery_cache.base import Cache
from urllib.parse import quote
from dotenv import load_dotenv
import messaging
import asyncio
import aiosqlite
import httpx
import json
import os
import logging
import math
import random
import time
from databases import Database
import websockets

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# FastAPI app setup
app = FastAPI()

# Globals
balance = None  # Global variable for balance
trigger_amount = None  # Global variable for trigger amount

# Pydantic models
class HookData(BaseModel):
    payment_hash: str
    description: Optional[str] = None
    amount: Optional[float] = 0

class CyberHerdData(BaseModel):
    display_name: Optional[str] = 'Anon'
    event_id: str
    kinds: List[int] = []
    pubkey: str
    nprofile: str
    lud16: str
    notified: Optional[str] = None
    payouts: float = 0.0

class CyberHerdTreats(BaseModel):
    pubkey: str
    amount: int

class InvoiceRequest(BaseModel):
    amount: int
    memo: str
    key: Optional[str] = None

class Message(BaseModel):
    content: str

# Environment and Configuration
def load_env_vars(required_vars):
    load_dotenv()
    missing_vars = [var for var in required_vars if os.getenv(var) is None]
    if missing_vars:
        raise ValueError(f"Missing environment variables: {', '.join(missing_vars)}")
    return {var: os.getenv(var) for var in required_vars}

required_env_vars = ['OH_AUTH_1', 'HERD_KEY', 'GOOGLE_API_KEY', 'NOS_SEC', 'CYBERHERD_KEY']
config = load_env_vars(required_env_vars)

LNBITS_URL = os.getenv('LNBITS_URL', 'http://127.0.0.1:3002')
OPENHAB_URL = os.getenv('OPENHAB_URL', 'http://10.8.0.6:8080')
HERD_WEBSOCKET = "wss://lnb.bolverker.com/api/v1/ws/036ad4bb0dcb4b8c952230ab7b47ea52"

# Cache Management
class MemoryCache(Cache):
    _CACHE = {}

    def get(self, url):
        return MemoryCache._CACHE.get(url)

    def set(self, url, content):
        MemoryCache._CACHE[url] = content

class Cache:
    def __init__(self):
        self.data = {}

    async def get(self, key, default=None):
        item = self.data.get(key)
        if item is None or item['expires_at'] < time.time():
            return default
        return item['value']

    async def set(self, key, value, ttl=300):
        self.data[key] = {'value': value, 'expires_at': time.time() + ttl}

cache = Cache()

# WebSockets ###
async def connect_to_websocket(uri: str):
    backoff = 1
    max_backoff = 60
    while True:
        try:
            async with websockets.connect(uri) as websocket:
                logger.info(f"Connected to WebSocket: {uri}")
                await listen_for_messages(websocket)
                return
        except (websockets.exceptions.ConnectionClosedError, websockets.exceptions.InvalidURI) as e:
            logger.error(f"WebSocket connection error: {e}")
        except Exception as e:
            logger.error(f"Unexpected error during connection: {e}")
        
        logger.info(f"Reconnecting in {backoff} seconds...")
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, max_backoff)

async def listen_for_messages(websocket):
    global balance, trigger_amount
    try:
        while True:
            message = await websocket.recv()
            payment_data = json.loads(message)
            logger.info(f"Received payment data: {payment_data}")
            
            # Use a single variable for payment data
            payment = payment_data.get('payment', {})
            payment_amount = payment.get('amount', 0)
            wallet_fiat_rate = payment.get('extra', {}).get('wallet_fiat_rate')
            wallet_balance = payment_data.get('wallet_balance')
            
            if wallet_balance is not None:
                balance = wallet_balance

            if wallet_fiat_rate is not None:
                trigger_amount = math.floor(wallet_fiat_rate)
            
            # feeder
            if balance >= trigger_amount:
                if await trigger_feeder():
                    status = await send_payment(balance)
            
                    if status['success']:
                        message = await messaging.make_messages(config['NOS_SEC'], int(payment_amount / 1000), 0, "feeder_triggered")
                        await update_message_in_db(message)
                    
            else:
                difference = round(trigger_amount - float(balance))
                min_sats = 21
                
                if payment_amount >= min_sats:
                    message = await messaging.make_messages(config['NOS_SEC'], int(payment_amount / 1000), difference, "sats_received")
                    await update_message_in_db(message)

    except websockets.ConnectionClosed:
        logger.info("WebSocket connection closed")

# Database 
database = Database('sqlite:///cyberherd.db')

@app.on_event("startup")
async def startup():
    await database.connect()
    global http_client
    http_client = httpx.AsyncClient(http2=True)
    await database.execute('''
        CREATE TABLE IF NOT EXISTS cyber_herd (
            pubkey TEXT PRIMARY KEY,
            display_name TEXT,
            event_id TEXT,
            kinds TEXT,
            nprofile TEXT,
            lud16 TEXT,
            notified TEXT,
            payouts REAL
        )
    ''')
    await database.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    asyncio.create_task(connect_to_websocket(HERD_WEBSOCKET))

@app.on_event("shutdown")
async def shutdown():
    await http_client.aclose()
    await database.disconnect()

async def get_cyber_herd_list() -> List[dict]:
    try:
        query = "SELECT * FROM cyber_herd"
        rows = await database.fetch_all(query)
        result = []
        for row in rows:
            row_dict = dict(row)
            try:
                row_dict['kinds'] = json.loads(row_dict['kinds']) if isinstance(row_dict['kinds'], str) else row_dict['kinds']
            except json.JSONDecodeError:
                row_dict['kinds'] = []
            result.append(row_dict)
        return result
    except Exception as e:
        logger.error(f"Error retrieving cyber herd list: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

async def update_cyber_herd_list(new_data: List[dict], reset=False):
    try:
        if reset:
            await database.execute("DELETE FROM cyber_herd")
            return

        query = '''
            INSERT OR REPLACE INTO cyber_herd
            (pubkey, display_name, event_id, kinds, nprofile, lud16, notified, payouts)
            VALUES (:pubkey, :display_name, :event_id, :kinds, :nprofile, :lud16, :notified, :payouts)
        '''
        for item in new_data:
            await database.execute(query, values={
                'pubkey': item['pubkey'],
                'display_name': item.get('display_name'),
                'event_id': item.get('event_id'),
                'kinds': json.dumps(item.get('kinds', [])),
                'nprofile': item.get('nprofile'),
                'lud16': item.get('lud16'),
                'notified': item.get('notified'),
                'payouts': item.get('payouts', 0.0)
            })
    except Exception as e:
        logger.error(f"Error updating cyber herd list: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

async def update_message_in_db(new_message: str):
    try:
        await database.execute("INSERT INTO messages (content) VALUES (:content)", values={'content': new_message})
        await database.execute("DELETE FROM messages WHERE id NOT IN (SELECT id FROM messages ORDER BY timestamp DESC LIMIT 10)")
    except Exception as e:
        logger.error(f"Error updating messages in database: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

async def retrieve_messages() -> List[str]:
    try:
        query = "SELECT content FROM messages ORDER BY timestamp DESC LIMIT 10"
        rows = await database.fetch_all(query)
        return [row['content'] for row in rows]
    except Exception as e:
        logger.error(f"Error retrieving messages from database: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

# 4. HTTP Client and External Service Interaction
async def fetch_cyberherd_targets():
    try:
        url = f'{LNBITS_URL}/splitpayments/api/v1/targets'
        headers = {
            'accept': 'application/json',
            'X-API-KEY': config['CYBERHERD_KEY']
        }
        response = await http_client.get(url, headers=headers)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as e:
        logger.error(f"HTTP error fetching cyberherd targets: {e}")
        raise HTTPException(status_code=response.status_code, detail="Failed to fetch cyberherd targets")
    except Exception as e:
        logger.error(f"Error fetching cyberherd targets: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

async def create_cyberherd_targets(new_targets_data, initial_targets):
    try:
        fetched_wallets = {item['wallet']: item for item in initial_targets}
        
        predefined_wallet = {'wallet': 'bolverker@strike.me', 'alias': 'Sat', 'percent': 90}
        
        combined_wallets = []
        
        for item in new_targets_data:
            wallet = item['wallet']
            name = item.get('alias', 'Unknown')
            payouts = item.get('payouts', 1.0)  # Default to 1.0 if payouts not provided
            if wallet not in fetched_wallets and wallet != predefined_wallet['wallet']:
                combined_wallets.append({'wallet': wallet, 'alias': name, 'payouts': payouts})
        
        for wallet, details in fetched_wallets.items():
            if wallet != predefined_wallet['wallet']:
                payouts = details.get('payouts', 1.0)  # Default to 1.0 if payouts not provided
                combined_wallets.append({'wallet': wallet, 'alias': details.get('alias', 'Unknown'), 'payouts': payouts})
        
        total_percent_allocation = predefined_wallet['percent']
        targets_list = [predefined_wallet]
        
        if combined_wallets:
            # Calculate the sum of payouts
            total_payouts = sum(wallet['payouts'] for wallet in combined_wallets)
            if total_payouts == 0:
                total_payouts = 1  # To avoid division by zero
            
            # Calculate base percentages and scale them to whole numbers
            for wallet in combined_wallets:
                base_percent = (100 - total_percent_allocation) * (wallet['payouts'] / total_payouts)
                wallet['percent'] = max(1, round(base_percent))
                
            # Adjust percentages to ensure the total is 100%
            total_percent_allocation += sum(wallet['percent'] for wallet in combined_wallets)
            
            if total_percent_allocation > 100:
                excess_allocation = total_percent_allocation - 100
                combined_wallets[-1]['percent'] -= excess_allocation
            elif total_percent_allocation < 100:
                remaining_allocation = 100 - total_percent_allocation
                combined_wallets[-1]['percent'] += remaining_allocation
            
            for wallet in combined_wallets:
                targets_list.append({
                    'wallet': wallet['wallet'], 
                    'alias': wallet['alias'], 
                    'percent': wallet['percent']
                })
        
        targets = {"targets": targets_list}
        
        return targets
    except Exception as e:
        logger.error(f"Error creating cyberherd targets: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
        
        return targets
    except Exception as e:
        logger.error(f"Error creating cyberherd targets: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

async def update_cyberherd_targets(targets):
    try:
        url = f'{LNBITS_URL}/splitpayments/api/v1/targets'
        headers = {
            'accept': 'application/json',
            'X-API-KEY': config['CYBERHERD_KEY'], 
            'Content-Type': 'application/json'
        }
        
        data = json.dumps(targets)
        
        response = await http_client.put(url, headers=headers, content=data)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as e:
        logger.error(f"HTTP error updating cyberherd targets: {e}")
        raise HTTPException(status_code=response.status_code, detail="Failed to update cyberherd targets")
    except Exception as e:
        logger.error(f"Error updating cyberherd targets: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

async def get_balance(force_refresh=False):
    try:
        global balance  # Reference the global balance variable

        if balance is not None and not force_refresh:
            return balance

        response = await http_client.get(f'{LNBITS_URL}/api/v1/wallet', headers={'X-Api-Key': config['HERD_KEY']})
        response.raise_for_status()
        balance = response.json()['balance']
        await cache.set('balance', balance, ttl=2)
        return balance
    except httpx.HTTPError as e:
        logger.error(f"HTTP error retrieving balance: {e}")
        raise HTTPException(status_code=response.status_code, detail="Failed to retrieve balance")
    except Exception as e:
        logger.error(f"Error retrieving balance: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

async def convert_to_sats(amount: float, force_refresh=False):
    try:
        if not force_refresh:
            cached_conversion = await cache.get(f'usd_to_sats_{amount}')
            if cached_conversion is not None:
                return cached_conversion

        payload = {"from_": "usd", "amount": amount, "to": "sat"}
        response = await http_client.post(f'{LNBITS_URL}/api/v1/conversion', json=payload)
        response.raise_for_status()
        sats = response.json()['sats']
        await cache.set(f'usd_to_sats_{amount}', sats, ttl=300)
        return sats
    except httpx.HTTPError as e:
        logger.error(f"HTTP error converting amount: {e}")
        raise HTTPException(status_code=response.status_code, detail="Failed to convert amount")
    except Exception as e:
        logger.error(f"Error converting amount: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

async def create_invoice(amount: int, memo: str, key: str = config['CYBERHERD_KEY']):
    try:
        url = f"{LNBITS_URL}/api/v1/payments"
        headers = {
            "X-API-KEY": key,
            "Content-Type": "application/json"
        }
        data = {
            "out": False,
            "amount": amount,
            "memo": memo,
        }
        response = await http_client.post(url, json=data, headers=headers)
        response.raise_for_status()
        return response.json()['payment_request']
    except httpx.HTTPError as e:
        logger.error(f"HTTP error creating invoice: {e}")
        raise HTTPException(status_code=response.status_code, detail="Failed to create invoice")
    except Exception as e:
        logger.error(f"Error creating invoice: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

async def pay_invoice(payment_request: str, key: str = config['HERD_KEY']):
    try:
        url = f"{LNBITS_URL}/api/v1/payments"
        headers = {
            "X-API-KEY": key,
            "Content-Type": "application/json"
        }
        data = {
            "out": True,
            "bolt11": payment_request
        }
        response = await http_client.post(url, json=data, headers=headers)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as e:
        logger.error(f"HTTP error paying invoice: {e}")
        raise HTTPException(status_code=response.status_code, detail="Failed to pay invoice")
    except Exception as e:
        logger.error(f"Error paying invoice: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

async def is_feeder_on():
    try:
        response = await http_client.get(f'{OPENHAB_URL}/rest/items/FeederOverride/state', auth=(config['OH_AUTH_1'], ''))
        response.raise_for_status()
        return response.text.strip() == 'ON'
    except httpx.HTTPError as e:
        logger.error(f"HTTP error checking feeder status: {e}")
        raise HTTPException(status_code=response.status_code, detail="Failed to check feeder status")
    except Exception as e:
        logger.error(f"Error checking feeder status: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

async def trigger_feeder():
    try:
        response = await http_client.post(f'{OPENHAB_URL}/rest/rules/88bd9ec4de/runnow', auth=(config['OH_AUTH_1'], ''))
        response.raise_for_status()
        return response.status_code == 200
    except httpx.HTTPError as e:
        logger.error(f"HTTP error triggering feeder: {e}")
        raise HTTPException(status_code=response.status_code, detail="Failed to trigger the feeder rule")
    except Exception as e:
        logger.error(f"Error triggering the feeder rule: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

# 5. Helper Functions
def get_youtube_client(api_key):
    return build('youtube', 'v3', developerKey=api_key, cache=MemoryCache())

async def should_trigger_feeder(balance: float, trigger: int) -> bool:
    return balance >= (trigger - 25)

async def send_payment(balance: int):
    for retry in range(3):
        balance = balance * 1000
        withdraw = int(round(balance * 0.99) / 1000)
        memo = 'Reset Herd Wallet'
        
        try:
            payment_request = await create_invoice(withdraw, memo)
            payment_status = await pay_invoice(payment_request)
            return {"success": True, "data": payment_status}
        except HTTPException as e:
            logger.error(f"Failed to send payment on attempt {retry + 1}: {e.detail}")
    
    return {"success": False, "message": "Failed to send payment after 3 attempts"}

# 6. API Routes

@app.get("/balance")
async def get_balance_route(force_refresh: bool = False):
    balance_value = await get_balance(force_refresh)
    return {"balance": balance_value}

@app.post("/create-invoice/{amount}")
async def create_invoice_route(
    amount: int = Path(..., description="The amount for the invoice in satoshis"),
    memo: str = Query("Default memo", description="The memo for the invoice")
):
    return {"payment_request": await create_invoice(amount, memo)}

@app.post("/cyber_herd")
async def update_cyber_herd(data: List[CyberHerdData]):
    try:
        cyber_herd_list = await get_cyber_herd_list()
        balance = float(await get_balance()) / 1000
        trigger = await get_trigger_amount_route()
        difference = round(trigger['trigger_amount'] - balance)

        initial_targets = await fetch_cyberherd_targets()
        existing_wallets = {item['wallet']: item for item in initial_targets}

        cyber_herd_dict = {item['pubkey']: item for item in cyber_herd_list}

        if len(cyber_herd_dict) >= 9:  # 10th record should still go in.
            logger.info(f"Herd full: {len(cyber_herd_dict)} members")
            return {"status": "herd full"}

        targets_to_create = []

        for item in data:
            item_dict = item.dict()
            pubkey = item_dict['pubkey']
            logger.info(f"Processing item: {item_dict}")

            if pubkey in cyber_herd_dict:
                logger.info(f"Item already exists: {pubkey}")
                continue  # Skip this item but continue processing the rest
            else:
                item_dict['notified'] = None

                if item_dict['lud16'] not in existing_wallets:
                    targets_to_create.append({
                        'wallet': item_dict['lud16'],
                        'alias': item_dict['pubkey'],
                    })

                cyber_herd_dict[pubkey] = item_dict

        if targets_to_create:
            targets = await create_cyberherd_targets(targets_to_create, initial_targets)
            if targets:
                await update_cyberherd_targets(targets)

        for item_dict in cyber_herd_dict.values():
            if item_dict.get('notified') is None or item_dict.get('notified').strip() == "":
                spots_remaining = await get_cyberherd_spots_remaining()
                spots_available = spots_remaining['spots_remaining'] - 1  # account for the new entry
                message = await messaging.make_messages(config['NOS_SEC'], 0, difference, "cyber_herd", item_dict, spots_available)
                await update_message_in_db(message)
                item_dict['notified'] = messaging.notified.get('id')
                logger.debug(f"Set notified ID: {item_dict['notified']} for pubkey: {item_dict['pubkey']}")

        await update_cyber_herd_list(list(cyber_herd_dict.values()))

        return {"status": "success"}
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Failed to update cyber herd: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@app.get("/get_cyber_herd")
async def get_cyber_herd():
    return await get_cyber_herd_list()

@app.get("/reset_cyber_herd")
async def reset_cyber_herd():
    await update_cyber_herd_list([], reset=True)

    headers = {
        'accept': 'application/json',
        'X-API-KEY': config['CYBERHERD_KEY']
    }
    url = f"{LNBITS_URL}/splitpayments/api/v1/targets?api-key={config['CYBERHERD_KEY']}"

    try:
        response = await http_client.delete(url, headers=headers)
        response.raise_for_status()
        return {"status": "success", "message": "CyberHerd reset successfully."}
    except httpx.RequestError as e:
        logger.error(f"Request failed: {e}")
        raise HTTPException(status_code=500, detail="Request to API failed.")
    except Exception as e:
        logger.error(f"Error resetting CyberHerd: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@app.delete("/cyber_herd/delete/{lud16}")
async def delete_cyber_herd(lud16: str):
    try:
        logger.info(f"Attempting to delete record with lud16: {lud16}")
        query = "DELETE FROM cyber_herd WHERE lud16 = :lud16"
        result = await database.execute(query, values={'lud16': lud16})
        if result.rowcount == 0:
            logger.warning(f"No record found with lud16: {lud16}")
            raise HTTPException(status_code=404, detail="Record not found")
        logger.info(f"Record with lud16 {lud16} deleted successfully.")
        return {"status": "success", "message": f"Record with lud16 {lud16} deleted successfully."}
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Failed to delete record: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@app.get("/trigger_amount")
async def get_trigger_amount_route():
    global trigger_amount
    if trigger_amount is not None:
        return {"trigger_amount": trigger_amount}
    else:
        try:
            # Retrieve trigger amount as before
            trigger_amount = await convert_to_sats(1.00)  # Assuming convert_to_sats fetches the amount as you want
            await cache.set('trigger_amount', trigger_amount, ttl=300)
            return {"trigger_amount": trigger_amount}
        except Exception as e:
            logger.error(f"Error retrieving trigger amount: {e}")
            raise HTTPException(status_code=500, detail="Internal Server Error")

@app.get("/convert/{amount}")
async def convert(amount: float):
    return await convert_to_sats(amount)

@app.get("/feeder_status")
async def feeder_status():
    return await is_feeder_on()

@app.get("/islive/{channel_id}")
async def live_status(channel_id: str):
    try:
        cached_video_id = await cache.get(f'live_video_{channel_id}')
        if cached_video_id:
            return {'status': 'live', 'video_id': cached_video_id}

        youtube = get_youtube_client(config['GOOGLE_API_KEY'])
        request = youtube.search().list(
            part="id,snippet",
            channelId=channel_id,
            type="video",
            eventType="live"
        )
        response = request.execute()
        
        if response['items']:
            video_id = response['items'][0]['id']['videoId']
            await cache.set(f'live_video_{channel_id}', video_id, ttl=300)
            return {'status': 'live', 'video_id': video_id}
        else:
            return {'status': 'offline'}
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Failed to check live status: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@app.get("/messages", response_model=List[Message])
async def get_messages():
    try:
        messages = await retrieve_messages()
        formatted_messages = [Message(content=msg) for msg in messages if isinstance(msg, str)]
        return formatted_messages
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error in /messages route: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@app.post("/messages/cyberherd_treats")
async def handle_cyberherd_treats(data: CyberHerdTreats):
    try:
        pubkey = data.pubkey
        amount = data.amount
        cyber_herd_list = await get_cyber_herd_list()
        cyber_herd_dict = {item['pubkey']: item for item in cyber_herd_list}
        
        if pubkey in cyber_herd_dict:
            message_data = await messaging.make_messages(config['NOS_SEC'], amount, 0, "cyber_herd_treats", cyber_herd_dict[pubkey])
            await update_message_in_db(message_data)
            return {"status": "success"}
        else:
            return {"status": "error", "message": "Invalid pubkey"}
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error in /messages/cyberherd_treats route: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@app.get("/messages/info")
async def create_info_message():
    try:
        message_data = await messaging.make_messages(config['NOS_SEC'], 0, 0, "interface_info")
        await update_message_in_db(message_data)
        messages = await retrieve_messages()
        return [Message(content=msg) for msg in messages]
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error in /messages/info route: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@app.get("/messages/reset")
async def reset_all_messages():
    try:
        await database.execute("DELETE FROM messages")
        return {"status": "success", "message": "All messages have been reset."}
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error in /messages/reset route: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@app.get("/cyberherd/spots_remaining")
async def get_cyberherd_spots_remaining():
    try:
        query = "SELECT COUNT(*) FROM cyber_herd"
        result = await database.fetch_one(query)
        current_spots_taken = result[0]
        spots_remaining = 10 - current_spots_taken
        return {"spots_remaining": spots_remaining}
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error retrieving remaining CyberHerd spots: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

# 7. Error Handling
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error"}
    )
