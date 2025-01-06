from typing import List, Optional, Dict, Set
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException, Path, Query, Depends, Request, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.websockets import WebSocket, WebSocketDisconnect
from pydantic import BaseModel, validator
from urllib.parse import quote
from dotenv import load_dotenv
import asyncio
import httpx
import json
import os
import logging
import math
import random
import time
from databases import Database
import websockets
from asyncio import Lock, Event
from websockets.exceptions import (
    ConnectionClosedError,
    ConnectionClosedOK,
    InvalidURI,
    InvalidHandshake,
)
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_log,
    wait_fixed,
)

import messaging
from cyberherd_module import MetadataFetcher, Verifier, generate_nprofile, check_cyberherd_tag


# Configuration and Constants
MAX_HERD_SIZE = int(os.getenv('MAX_HERD_SIZE', 10))
PRICE = float(os.getenv('PRICE', 1.00))
LNBITS_URL = os.getenv('LNBITS_URL', 'http://127.0.0.1:3002')
OPENHAB_URL = os.getenv('OPENHAB_URL', 'http://10.8.0.6:8080')
HERD_WEBSOCKET = os.getenv('HERD_WEBSOCKET', "ws://127.0.0.1:3002/api/v1/ws/036ad4bb0dcb4b8c952230ab7b47ea52")
PREDEFINED_WALLET_ADDRESS = 'bolverker@strike.me'
PREDEFINED_WALLET_ALIAS = 'Bolverker'
PREDEFINED_WALLET_PERCENT_RESET = 100
PREDEFINED_WALLET_PERCENT_DEFAULT = 90
TRIGGER_AMOUNT_SATS = 1000

notification_semaphore = asyncio.Semaphore(5) #limit concurrant notifications

# Logging Configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# FastAPI app setup
app = FastAPI()

# Globals and State Management
class AppState:
    def __init__(self):
        self.balance: int = 0
        self.lock = Lock()

app_state = AppState()

# Track connected WebSocket clients
connected_clients: Set[WebSocket] = set()

# Pydantic Models
class HookData(BaseModel):
    payment_hash: str
    description: Optional[str] = None
    amount: Optional[float] = 0

class CyberHerdData(BaseModel):
    display_name: Optional[str] = 'Anon'
    event_id: str
    note: str
    kinds: List[int] = []
    pubkey: str
    nprofile: str
    lud16: str
    notified: Optional[str] = None
    payouts: float = 0.0

    class Config:
        extra = 'ignore'
        
    @validator('lud16')
    def validate_lud16(cls, v):
        if '@' not in v:
            raise ValueError('Invalid lud16 format')
        return v

class CyberHerdTreats(BaseModel):
    pubkey: str
    amount: int

class PaymentRequest(BaseModel):
    balance: int

def load_env_vars(required_vars):
    load_dotenv()
    missing_vars = [var for var in required_vars if os.getenv(var) is None]
    if missing_vars:
        raise ValueError(f"Missing environment variables: {', '.join(missing_vars)}")
    return {var: os.getenv(var) for var in required_vars}

required_env_vars = ['OH_AUTH_1', 'HERD_KEY', 'SAT_KEY', 'NOS_SEC', 'CYBERHERD_KEY']
config = load_env_vars(required_env_vars)

#Cors middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

from tenacity import AsyncRetrying

http_retry = retry(
    reraise=True,
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_exception_type(httpx.RequestError)
)

websocket_retry = retry(
    reraise=True,
    stop=stop_after_attempt(None),
    wait=wait_exponential(multiplier=1, min=4, max=60),
    retry=retry_if_exception_type((
        ConnectionClosedError,
        ConnectionClosedOK,
        InvalidURI,
        InvalidHandshake,
        OSError,
    )),
    before=before_log(logger, logging.WARNING)
)

db_retry = retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_fixed(2),
    retry=retry_if_exception_type((Exception,))
)

class WebSocketManager:
    def __init__(self, uri: str, logger: logging.Logger, max_retries: Optional[int] = None):
        self.uri = uri
        self.logger = logger
        self.max_retries = max_retries
        self.websocket = None
        self.lock = Lock()
        self.should_run = True
        self.connected = Event()
        self.listen_task = None
        self._retry_count = 0

    async def connect(self):
        async with self.lock:
            while self.should_run:
                try:
                    if self.websocket:
                        await self.websocket.close()
                    
                    self.websocket = await websockets.connect(
                        self.uri,
                        ping_interval=30,
                        ping_timeout=10,
                        close_timeout=10
                    )
                    
                    self.logger.info(f"Connected to WebSocket: {self.uri}")
                    self.connected.set()
                    self._retry_count = 0
                    
                    # Start listening in a separate task
                    self.listen_task = asyncio.create_task(self.listen())
                    
                    # Wait for the listen task to complete
                    await self.listen_task

                except (ConnectionClosedError, ConnectionClosedOK, InvalidURI, InvalidHandshake, OSError) as e:
                    self.logger.warning(f"WebSocket connection error: {e}")
                    self.connected.clear()
                    
                    if self.should_run:
                        if self.max_retries is not None and self._retry_count >= self.max_retries:
                            self.logger.error("Maximum reconnection attempts reached. Stopping reconnection.")
                            break
                        
                        backoff = min(60, (2 ** self._retry_count))
                        self.logger.info(f"Attempting reconnection in {backoff} seconds (Retry {self._retry_count + 1})...")
                        self._retry_count += 1
                        await asyncio.sleep(backoff)
                    else:
                        break
                except Exception as e:
                    self.logger.error(f"Unexpected error in WebSocket connection: {e}")
                    self.connected.clear()
                    if self.should_run:
                        self.logger.info("Retrying connection in 5 seconds due to unexpected error.")
                        await asyncio.sleep(5)
                    else:
                        break

    async def listen(self):
        try:
            async for message in self.websocket:
                try:
                    self.logger.debug(f"Received message: {message}")
                    payment_data = json.loads(message)
                    background_tasks = BackgroundTasks()
                    await process_payment_data(payment_data, background_tasks)
                except json.JSONDecodeError as e:
                    self.logger.error(f"Failed to decode WebSocket message: {e}")
                except Exception as e:
                    self.logger.error(f"Error processing message: {e}")
        except (ConnectionClosedError, ConnectionClosedOK) as e:
            self.logger.warning(f"WebSocket connection closed during listen: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error in listen: {e}")
            raise

    async def disconnect(self):
        async with self.lock:
            self.should_run = False
            if self.listen_task:
                self.listen_task.cancel()
                try:
                    await self.listen_task
                except asyncio.CancelledError:
                    self.logger.debug("Listen task cancelled.")
                except Exception as e:
                    self.logger.error(f"Error while cancelling listen task: {e}")
                self.listen_task = None
            if self.websocket:
                try:
                    await self.websocket.close()
                    self.logger.info("WebSocket connection closed gracefully.")
                except Exception as e:
                    self.logger.error(f"Error during WebSocket disconnect: {e}")
                finally:
                    self.websocket = None
            self.connected.clear()

    async def wait_for_connection(self, timeout: Optional[float] = None) -> bool:
        try:
            await asyncio.wait_for(self.connected.wait(), timeout)
            return True
        except asyncio.TimeoutError:
            self.logger.warning("Timeout while waiting for WebSocket connection.")
            return False

    async def run(self):
        await self.connect()

websocket_manager = WebSocketManager(
    uri=HERD_WEBSOCKET,
    logger=logger,
    max_retries=5
)

database = Database('sqlite:///cyberherd.db')

@app.on_event("startup")
async def startup():
    # Initialize HTTP client
    global http_client
    http_client = httpx.AsyncClient(http2=True)

    # Start WebSocket manager
    websocket_task = asyncio.create_task(websocket_manager.connect())
    connected = await websocket_manager.wait_for_connection(timeout=30)
    if not connected:
        logger.warning("Initial WebSocket connection attempt timed out")

    try:
            response = await get_balance_route(force_refresh=True)
            app_state.balance = response.get("balance", 0)
    except Exception as e:
            logger.error(f"Failed to retrieve balance in startup_event: {e}. Defaulting to 0.")
            app_state.balance = 0

    # Connect to database and create tables (no 'messages' table anymore)
    await database.connect()
    await database.execute('''
        CREATE TABLE IF NOT EXISTS cyber_herd (
            pubkey TEXT PRIMARY KEY,
            display_name TEXT,
            event_id TEXT,
            note TEXT,
            kinds TEXT,
            nprofile TEXT,
            lud16 TEXT,
            notified TEXT,
            payouts REAL
        )
    ''')
    await database.execute('''
        CREATE TABLE IF NOT EXISTS cache (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            expires_at REAL NOT NULL
        )
    ''')

    # Start cache cleanup task
    asyncio.create_task(cleanup_cache())

    # Start daily reset task
    asyncio.create_task(schedule_daily_reset())

    # Start periodic informational message task
    asyncio.create_task(periodic_informational_messages())


async def schedule_daily_reset():
    while True:
        now = datetime.utcnow()
        next_midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        sleep_seconds = (next_midnight - now).total_seconds()
        await asyncio.sleep(sleep_seconds)
        
        if app_state.balance and app_state.balance >= TRIGGER_AMOUNT_SATS:
            await send_payment(app_state.balance)
                        

class DatabaseCache:
    def __init__(self, db):
        self.db = db
        self.lock = Lock()

    async def get(self, key, default=None):
        async with self.lock:
            query = "SELECT value, expires_at FROM cache WHERE key = :key"
            row = await self.db.fetch_one(query, values={"key": key})
            if row and row["expires_at"] > time.time():
                return json.loads(row["value"])
            return default

    async def set(self, key, value, ttl=300):
        async with self.lock:
            expires_at = time.time() + ttl
            query = """
                INSERT INTO cache (key, value, expires_at)
                VALUES (:key, :value, :expires_at)
                ON CONFLICT(key) DO UPDATE SET
                    value = :value,
                    expires_at = :expires_at
            """
            await self.db.execute(query, values={
                "key": key,
                "value": json.dumps(value),
                "expires_at": expires_at
            })

cache = DatabaseCache(database)

async def cleanup_cache():
    while True:
        await asyncio.sleep(1800)
        try:
            current_time = time.time()
            query = "DELETE FROM cache WHERE expires_at < :current_time"
            await database.execute(query, values={"current_time": current_time})
        except Exception as e:
            logger.error(f"Error cleaning up cache: {e}")

async def send_messages_to_clients(message: str):
    """Send a given message to all connected WebSocket clients."""
    if not message:
        logger.warning("Attempted to send an empty message. Skipping.")
        return

    if connected_clients:
        logger.info(f"Broadcasting message to {len(connected_clients)} clients: {message}")
        for client in connected_clients.copy():
            try:
                await client.send_text(message)
            except Exception as e:
                logger.warning(f"Failed to send message to client: {e}")
                connected_clients.remove(client)
    else:
        logger.debug("No connected clients to send messages to.")

async def periodic_informational_messages():
    """Send an informational message via WebSockets with a 40% chance every minute."""
    while True:
        await asyncio.sleep(60)
        if random.random() < 0.4:  # 40% chance
            # Use the messaging.make_messages to generate the "interface_info" message
            message, _ = await messaging.make_messages(config['NOS_SEC'], 0, 0, "interface_info")
            await send_messages_to_clients(message)

@http_retry
async def fetch_cyberherd_targets():
    url = f'{LNBITS_URL}/splitpayments/api/v1/targets'
    headers = {
        'accept': 'application/json',
        'X-API-KEY': config['CYBERHERD_KEY']
    }
    response = await http_client.get(url, headers=headers)
    response.raise_for_status()
    return response.json()

@http_retry
async def create_cyberherd_targets(new_targets_data, initial_targets, predefined_percent=PREDEFINED_WALLET_PERCENT_DEFAULT):
    try:
        fetched_wallets = {item['wallet']: item for item in initial_targets}
        predefined_wallet = {
            'wallet': PREDEFINED_WALLET_ADDRESS,
            'alias': PREDEFINED_WALLET_ALIAS,
            'percent': predefined_percent
        }
        combined_wallets = []

        for item in new_targets_data:
            wallet = item['wallet']
            name = item.get('alias', 'Unknown')
            payouts = item.get('payouts', 1.0)
            if wallet not in fetched_wallets and wallet != predefined_wallet['wallet']:
                combined_wallets.append({'wallet': wallet, 'alias': name, 'payouts': payouts})

        for wallet, details in fetched_wallets.items():
            if wallet != predefined_wallet['wallet']:
                payouts = details.get('payouts', 1.0)
                combined_wallets.append({'wallet': wallet, 'alias': details.get('alias', 'Unknown'), 'payouts': payouts})

        total_percent_allocation = predefined_wallet['percent']
        targets_list = [predefined_wallet]

        if combined_wallets:
            total_payouts = sum(wallet['payouts'] for wallet in combined_wallets)
            if total_payouts == 0:
                total_payouts = 1

            remaining_allocation = 100 - total_percent_allocation
            for wallet in combined_wallets:
                base_percent = remaining_allocation * (wallet['payouts'] / total_payouts)
                wallet['percent'] = max(1, round(base_percent))

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

@http_retry
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
        raise HTTPException(status_code=e.response.status_code if e.response else 500, detail="Failed to update cyberherd targets")
    except Exception as e:
        logger.error(f"Error updating cyberherd targets: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

async def notify_new_members(new_members, difference, current_herd_size):
    async with notification_semaphore:
        for item_dict in new_members:
            try:
                # Log the start of the notification process
                logger.info(f"Notifying member with pubkey: {item_dict['pubkey']}")

                # Calculate spots remaining dynamically
                spots_remaining = MAX_HERD_SIZE - current_herd_size

                # Generate a message using `messaging.make_messages`
                message_content, raw_command_output = await messaging.make_messages(
                    config['NOS_SEC'],
                    0,  # Amount placeholder
                    difference,
                    "cyber_herd",
                    item_dict,
                    spots_remaining
                )
                await send_messages_to_clients(message_content)

                # Parse `raw_command_output` for the note_id
                try:
                    command_output_json = json.loads(raw_command_output)
                    note_id = command_output_json.get("id")
                except json.JSONDecodeError:
                    logger.error(f"Invalid JSON from messaging.make_messages: {raw_command_output}")
                    continue

                # Update the database with the note_id if available
                if note_id:
                    update_query = """
                    UPDATE cyber_herd
                    SET notified = :notified
                    WHERE pubkey = :pubkey
                    """
                    await database.execute(
                        update_query,
                        values={"notified": note_id, "pubkey": item_dict['pubkey']}
                    )
                    logger.info(f"Database updated for pubkey: {item_dict['pubkey']}")
                else:
                    logger.error(f"No note_id found in command output for pubkey: {item_dict['pubkey']}")

            except Exception as e:
                logger.exception(f"Error while notifying and updating for pubkey: {item_dict.get('pubkey', 'unknown')}")


@http_retry
async def get_balance(force_refresh=False):
    try:
        response = await http_client.get(f'{LNBITS_URL}/api/v1/wallet', headers={'X-Api-Key': config['HERD_KEY']})
        response.raise_for_status()
        balance = response.json()['balance']
        
        async with app_state.lock:
            app_state.balance = balance
        return balance
            
    except httpx.HTTPError as e:
        logger.error(f"HTTP error retrieving balance: {e}")
        raise HTTPException(status_code=e.response.status_code if e.response else 500, detail="Failed to retrieve balance")
    except Exception as e:
        logger.error(f"Error retrieving balance: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@http_retry
async def fetch_btc_price():
    try:
        response = await http_client.get(
            f'{OPENHAB_URL}/rest/items/BTC_Price_Output/state',
            auth=(config['OH_AUTH_1'], '')
        )
        response.raise_for_status()
        btc_price = float(response.text)
        return btc_price
    except httpx.HTTPError as e:
        logger.error(f"HTTP error fetching BTC price: {e}")
        raise HTTPException(status_code=e.response.status_code if e.response else 500, detail="Failed to fetch BTC price")
    except Exception as e:
        logger.error(f"Error fetching BTC price: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@http_retry
async def convert_to_sats(amount: float):
    try:
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

@http_retry
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
        raise
    except Exception as e:
        logger.error(f"Error creating invoice: {e}")
        raise

@http_retry
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
        raise
    except Exception as e:
        logger.error(f"Error paying invoice: {e}")
        raise

@http_retry
async def is_feeder_override_enabled():
    try:
        response = await http_client.get(f'{OPENHAB_URL}/rest/items/FeederOverride/state', auth=(config['OH_AUTH_1'], ''))
        response.raise_for_status()
        return response.text.strip() == 'ON'
    except httpx.HTTPError as e:
        logger.error(f"HTTP error checking feeder status: {e}")
        raise HTTPException(status_code=e.response.status_code if e.response else 500, detail="Failed to check feeder status")
    except Exception as e:
        logger.error(f"Error checking feeder status: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@http_retry
async def trigger_feeder():
    try:
        response = await http_client.post(f'{OPENHAB_URL}/rest/rules/88bd9ec4de/runnow', auth=(config['OH_AUTH_1'], ''))
        response.raise_for_status()
        return response.status_code == 200
    except httpx.HTTPError as e:
        logger.error(f"HTTP error triggering feeder: {e}")
        raise HTTPException(status_code=e.response.status_code if e.response else 500, detail="Failed to trigger the feeder rule")
    except Exception as e:
        logger.error(f"Error triggering the feeder rule: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(Exception)
)

async def process_payment_data(payment_data, background_tasks: BackgroundTasks):
    try:
        payment = payment_data.get('payment', {})
        payment_amount = payment.get('amount', 0)

        wallet_balance = payment_data.get('wallet_balance')

        async with app_state.lock:
            app_state.balance = wallet_balance

        # Check for Nostr data and handle CyberHerd addition
        nostr_data_raw = payment.get('extra', {}).get('nostr')
        zap_matched_cyberherd = False  # Track if zap matches CyberHerd tag

        if nostr_data_raw and payment_amount >= 21000:
            try:
                nostr_data = json.loads(nostr_data_raw)
                pubkey = nostr_data.get('pubkey')
                note = nostr_data.get('id')  # Set 'note' to the zap event's ID
                kinds = [9734]  # Example: Assigning kind 9734 for now

                # Extract the 'e' tag (zapped note ID)
                event_id = next((tag[1] for tag in nostr_data.get('tags', []) if tag[0] == 'e'), None)

                if pubkey and event_id:
                    # Check for CyberHerd tag using the module function
                    if await check_cyberherd_tag(event_id):
                        zap_matched_cyberherd = True
                        # Fetch metadata for the pubkey
                        metadata_fetcher = MetadataFetcher()
                        metadata = await metadata_fetcher.lookup_metadata(pubkey)

                        if metadata:
                            lud16 = metadata.get('lud16')
                            nip05 = metadata.get('nip05')
                            display_name = metadata.get('display_name', 'Anon')

                            # Verify lud16 and nip05
                            is_valid_lud16 = lud16 and await Verifier.verify_lud16(lud16)
                            is_valid_nip05 = nip05 and await Verifier.verify_nip05(nip05, pubkey)

                            if not is_valid_lud16 or not is_valid_nip05:
                                logger.warning(
                                    f"Record rejected for pubkey {pubkey}: "
                                    f"Valid lud16={is_valid_lud16}, Valid nip05={is_valid_nip05}"
                                )
                            else:
                                nprofile = await generate_nprofile(pubkey)
                                if not nprofile:
                                    logger.warning(f"Failed to generate nprofile for pubkey: {pubkey}")

                                    # Create CyberHerdData instance
                                    new_member_data = CyberHerdData(
                                        display_name=display_name,
                                        event_id=event_id,  # Set to the zapped note ID
                                        note=note,          # Set to the zap event's ID
                                        kinds=kinds,
                                        pubkey=pubkey,
                                        nprofile=nprofile,
                                        lud16=lud16,
                                        notified=None,
                                        payouts=0.0,
                                        amount=payment_amount
                                    )

                                    # Add new cyberherd member
                                    result = await update_cyber_herd([new_member_data], background_tasks)
                        else:
                            logger.warning(f"Metadata lookup failed for pubkey: {pubkey}")
                    else:
                        logger.info(f"No 'CyberHerd' tag found for event_id: {event_id}")
                else:
                    logger.warning("Missing pubkey or event_id in Nostr data. Processing as a normal payment.")
            except json.JSONDecodeError:
                logger.error("Invalid JSON in Nostr data.")
            except Exception as e:
                logger.error(f"Error processing Nostr data: {e}")

        # Check for feeder trigger. (always checked regardless)
        if payment_amount > 0 and not await is_feeder_override_enabled():
            if app_state.balance >= TRIGGER_AMOUNT_SATS:
                if await trigger_feeder():
                    status = await send_payment(app_state.balance)
                    if status['success']:
                        # Send a message to websockets
                        message, _ = await messaging.make_messages(
                            config['NOS_SEC'],
                            int(payment_amount / 1000), 0, "feeder_triggered"
                        )
                        await send_messages_to_clients(message)

            # Execute "sats_received" logic for non-zaps or zaps without CyberHerd match
            elif not zap_matched_cyberherd:
                difference = round(TRIGGER_AMOUNT_SATS - app_state.balance)
                if (payment_amount / 1000) >= 10:
                    message, _ = await messaging.make_messages(
                        config['NOS_SEC'], 
                        int(payment_amount / 1000), 
                        difference, 
                        "sats_received"
                    )
                    await send_messages_to_clients(message)
        else:
            logger.info("Feeder override is ON or payment amount is non-positive. Skipping.")

    except Exception as e:
        logger.error(f"Error processing payment data: {e}")
        raise

@http_retry
async def send_payment(balance: int):
    balance = balance * 1000
    withdraw = int(balance / 1000)
    memo = 'Reset Herd Wallet'
    
    try:
        payment_request = await create_invoice(withdraw, memo)
        payment_status = await pay_invoice(payment_request)
        return {"success": True, "data": payment_status}
    except HTTPException as e:
        logger.error(f"Failed to send payment: {e.detail}")
        return {"success": False, "message": "Failed to send payment"}
    except Exception as e:
        logger.error(f"Failed to send payment: {e}")
        return {"success": False, "message": "Failed to send payment"}

@app.get("/balance")
async def get_balance_route(force_refresh: bool = False):
    balance_value = await get_balance(force_refresh)
    return {"balance": balance_value}

@app.post("/create-invoice/{amount}")
async def create_invoice_route(
    amount: int = Path(..., description="The amount for the invoice in satoshis"),
    memo: str = Query("Default memo", description="The memo for the invoice")
):
    try:
        payment_request = await create_invoice(amount, memo)
        return {"payment_request": payment_request}
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error in /create-invoice route: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@app.post("/cyber_herd")
async def update_cyber_herd(data: List[CyberHerdData], background_tasks: BackgroundTasks):
    try:
        # Get the current herd size
        query = "SELECT COUNT(*) as count FROM cyber_herd"
        result = await database.fetch_one(query)
        current_herd_size = result['count']

        # Check if the herd is already at or above max size
        if current_herd_size >= MAX_HERD_SIZE:
            logger.info(f"Herd full: {current_herd_size} members")
            return {"status": "herd full"}

        # Prepare lists for new members and new targets
        new_members = []
        targets_to_create = []

        # Calculate the difference for 'notify_new_members'
        difference = round(TRIGGER_AMOUNT_SATS - app_state.balance)

        # Iterate over each incoming item
        for item in data:
            item_dict = item.dict()
            pubkey = item_dict['pubkey']

            # Check if this pubkey is already in the database
            check_query = "SELECT COUNT(*) as count FROM cyber_herd WHERE pubkey = :pubkey"
            result = await database.fetch_one(check_query, values={"pubkey": pubkey})

            # If not in DB and we haven't hit MAX_HERD_SIZE, add to the new_members list
            if result['count'] == 0 and current_herd_size < MAX_HERD_SIZE:
                item_dict['notified'] = None
                # Convert list of kinds to a comma-separated string
                item_dict['kinds'] = ','.join(map(str, item_dict['kinds']))
                new_members.append(item_dict)

                # If there is an lud16, prepare a target entry
                if item_dict['lud16']:
                    targets_to_create.append({
                        'wallet': item_dict['lud16'],
                        'alias': item_dict['pubkey'],
                    })

                # Increase herd count
                current_herd_size += 1

        # If we have new members, insert them into the DB
        if new_members:
            insert_query = """
            INSERT INTO cyber_herd (pubkey, display_name, event_id, note, kinds, nprofile, lud16, notified, payouts)
            VALUES (:pubkey, :display_name, :event_id, :note, :kinds, :nprofile, :lud16, :notified, :payouts)
            """
            await database.execute_many(insert_query, new_members)

        # If we have new targets to create, do so and then update them
        if targets_to_create:
            # create_cyberherd_targets returns the newly created targets or None
            targets = await create_cyberherd_targets(targets_to_create, [])
            if targets:
                await update_cyberherd_targets(targets)

        # Launch the notification task explicitly (rather than using BackgroundTasks)
        task = asyncio.create_task(notify_new_members(new_members, difference, current_herd_size))
        task.add_done_callback(
            lambda t: logger.error(f"notify_new_members encountered an error: {t.exception()}") 
            if t.exception() else None
        )

        return {"status": "success", "new_members_added": len(new_members)}
    except HTTPException as e:
        # Pass through HTTPExceptions without wrapping
        raise e
    except Exception as e:
        # Any other exception, log and raise 500
        logger.error(f"Failed to update cyber herd: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@app.get("/get_cyber_herd")
async def get_cyber_herd():
    try:
        query = "SELECT * FROM cyber_herd"
        rows = await database.fetch_all(query)
        return rows
    except Exception as e:
        logger.error(f"Error retrieving cyber herd: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@app.get("/reset_cyber_herd")
async def reset_cyber_herd():
    try:
        # Clear the `cyber_herd` table
        await database.execute("DELETE FROM cyber_herd")
        logger.info("CyberHerd table cleared successfully.")

        # Reset LNBits targets
        headers = {
            'accept': 'application/json',
            'X-API-KEY': config['CYBERHERD_KEY']
        }
        url = f"{LNBITS_URL}/splitpayments/api/v1/targets"

        # Delete all existing targets
        response = await http_client.delete(url, headers=headers)
        response.raise_for_status()
        logger.info("Existing CyberHerd targets deleted successfully.")

        # Add predefined wallet target with 100% allocation
        predefined_wallet = {
            'wallet': PREDEFINED_WALLET_ADDRESS,
            'alias': PREDEFINED_WALLET_ALIAS,
            'percent': PREDEFINED_WALLET_PERCENT_RESET
        }
        new_targets = {"targets": [predefined_wallet]}

        create_response = await http_client.put(
            url,
            headers={
                'accept': 'application/json',
                'X-API-KEY': config['CYBERHERD_KEY'],
                'Content-Type': 'application/json'
            },
            content=json.dumps(new_targets)
        )
        create_response.raise_for_status()
        logger.info("Predefined CyberHerd target created with 100% allocation.")

        return {
            "status": "success",
            "message": "CyberHerd reset successfully with predefined target at 100% allocation."
        }

    except httpx.HTTPError as e:
        logger.error(f"HTTP error during CyberHerd reset: {e}")
        raise HTTPException(status_code=500, detail="HTTP request to CyberHerd API failed.")
    except Exception as e:
        logger.error(f"Error resetting CyberHerd: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@app.delete("/cyber_herd/delete/{lud16}")
async def delete_cyber_herd(lud16: str):
    try:
        logger.info(f"Attempting to delete record with lud16: {lud16}")

        # Check if the record exists in the database
        select_query = "SELECT * FROM cyber_herd WHERE lud16 = :lud16"
        record = await database.fetch_one(select_query, values={"lud16": lud16})

        if not record:
            logger.warning(f"No record found with lud16: {lud16}")
            raise HTTPException(status_code=404, detail="Record not found")

        # Delete the record from the cyber_herd table
        delete_query = "DELETE FROM cyber_herd WHERE lud16 = :lud16"
        await database.execute(delete_query, values={"lud16": lud16})
        logger.info(f"Record with lud16 {lud16} deleted successfully.")

        return {"status": "success", "message": f"Record with lud16 {lud16} deleted successfully."}
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Failed to delete record: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@app.get("/trigger_amount")
async def get_trigger_amount_route():
    async with app_state.lock:
        return {"trigger_amount": TRIGGER_AMOUNT_SATS}

@app.get("/convert/{amount}")
async def convert(amount: float):
    try:
        sats = await convert_to_sats(amount)
        return {"sats": sats}
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error in /convert route: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@app.get("/feeder_status")
async def feeder_status():
    try:
        status = await is_feeder_override_enabled()
        return {"feeder_override_enabled": status}
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error in /feeder_status route: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@app.post("/send-payment")
async def send_payment_route(payment_request: PaymentRequest):
    try:
        result = await send_payment(payment_request.balance)
        return result
    except HTTPException as e:
        logger.error(f"HTTPException occurred: {e.detail}")
        raise HTTPException(status_code=500, detail="Failed to process payment request.")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")

@app.get("/cyberherd/spots_remaining")
async def get_cyberherd_spots_remaining():
    try:
        query = "SELECT COUNT(*) as count FROM cyber_herd"
        result = await database.fetch_one(query)
        current_spots_taken = result['count']
        spots_remaining = MAX_HERD_SIZE - current_spots_taken
        return {"spots_remaining": spots_remaining}
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error retrieving remaining CyberHerd spots: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@app.get("/ws")
async def redirect_ws():
    return {"message": "Redirecting to /ws/"}

@app.websocket("/ws/")
async def websocket_endpoint(websocket: WebSocket):
    logger.debug(f"WebSocket Headers: {websocket.headers}")
    await websocket.accept()
    connected_clients.add(websocket)
    logger.info(f"Client connected. Total clients: {len(connected_clients)}")

    try:
        while True:
            # We don't process client messages here currently, but we could if needed
            await websocket.receive_text()
    except Exception as e:
        logger.warning(f"WebSocket connection error: {e}")
    finally:
        connected_clients.remove(websocket)
        logger.info(f"Client disconnected. Total clients: {len(connected_clients)}")

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    logger.error(f"HTTPException: {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception occurred", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error"}
    )

