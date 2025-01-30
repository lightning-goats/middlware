from math import floor
from typing import List, Optional, Dict, Set, Union, Tuple
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException, Path, Query, Depends, Request
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
    AsyncRetrying,
)

import messaging
from utils.cyberherd_module import MetadataFetcher, Verifier, generate_nprofile, check_cyberherd_tag
from utils.nostr_signing import sign_event, sign_zap_event

# Configuration and Constants
MAX_HERD_SIZE = int(os.getenv('MAX_HERD_SIZE', 10))
PREDEFINED_WALLET_PERCENT_RESET = 100
PREDEFINED_WALLET_PERCENT_DEFAULT = 80
TRIGGER_AMOUNT_SATS = 1000

def load_env_vars(required_vars):
    load_dotenv()
    missing_vars = [var for var in required_vars if os.getenv(var) is None]
    if missing_vars:
        raise ValueError(f"Missing environment variables: {', '.join(missing_vars)}")
    return {var: os.getenv(var) for var in required_vars}

required_env_vars = ['OH_AUTH_1', 'HERD_KEY', 'SAT_KEY', 'NOS_SEC', 'HEX_KEY', 'CYBERHERD_KEY', 'LNBITS_URL', 'OPENHAB_URL', 'HERD_WEBSOCKET', 'PREDEFINED_WALLET_ADDRESS','PREDEFINED_WALLET_ALIAS']
config = load_env_vars(required_env_vars)

notification_semaphore = asyncio.Semaphore(6)  # limit concurrent notifications

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
    amount: Optional[int] = 0

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

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

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
                    await process_payment_data(payment_data)
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
    uri=config['HERD_WEBSOCKET'],
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

    # Connect to database and create tables
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
            payouts REAL,
            amount INTEGER
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

        status = await reset_cyber_herd()
        
        if status['success'] and app_state.balance:
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

def calculate_payout(amount: float) -> float:
    units = (amount + 99) // 100  # ceiling division for multiples of 100
    units = min(units, 10)       # cap at 10 units (for 1000 sats or more)
    return units * 0.1

@http_retry
async def fetch_cyberherd_targets():
    url = f'{config["LNBITS_URL"]}/splitpayments/api/v1/targets'
    headers = {
        'accept': 'application/json',
        'X-API-KEY': config['CYBERHERD_KEY']
    }
    response = await http_client.get(url, headers=headers)
    response.raise_for_status()
    return response.json()

@http_retry
async def create_cyberherd_targets(new_targets_data, initial_targets):
    try:
        # Initialize predefined wallet with default percentage
        predefined_wallet = {
            'wallet': config['PREDEFINED_WALLET_ADDRESS'],
            'alias': config['PREDEFINED_WALLET_ALIAS'],
            'percent': PREDEFINED_WALLET_PERCENT_DEFAULT
        }
        combined_wallets = []

        # Collect non-predefined wallets
        for item in new_targets_data:
            wallet = item['wallet']
            name = item.get('alias', 'Unknown')
            payouts = item.get('payouts', 1.0)
            if wallet != predefined_wallet['wallet']:
                combined_wallets.append({'wallet': wallet, 'alias': name, 'payouts': payouts})

        total_payouts = sum(w['payouts'] for w in combined_wallets) or 1
        max_allocation = 100 - PREDEFINED_WALLET_PERCENT_DEFAULT
        min_percent_per_wallet = 2
        max_wallets_allowed = floor(max_allocation / min_percent_per_wallet)

        # Cap the number of wallets so each can get at least 2%
        if len(combined_wallets) > max_wallets_allowed:
            combined_wallets = sorted(
                combined_wallets,
                key=lambda x: x['payouts'],
                reverse=True
            )[:max_wallets_allowed]
            total_payouts = sum(w['payouts'] for w in combined_wallets) or 1

        # Assign baseline minimum (2%) to each wallet
        for wallet in combined_wallets:
            wallet['percent'] = min_percent_per_wallet
        allocated = min_percent_per_wallet * len(combined_wallets)
        remaining_allocation = max_allocation - allocated

        # Distribute remaining allocation proportionally
        additional_allocations = []
        for wallet in combined_wallets:
            prop = wallet['payouts'] / total_payouts
            additional = prop * remaining_allocation
            additional_allocations.append((wallet, additional))

        # Assign floor of proportional allocation
        for wallet, additional in additional_allocations:
            add_percent = floor(additional)
            wallet['percent'] += add_percent

        allocated_percent = sum(w['percent'] for w in combined_wallets)
        leftover = max_allocation - allocated_percent

        # Distribute leftover percentages one by one
        if leftover > 0:
            remainders = []
            for wallet, additional in additional_allocations:
                fractional_part = additional - math.floor(additional)
                remainders.append((fractional_part, wallet))

            # Sort descending by fractional_part
            remainders.sort(reverse=True, key=lambda x: x[0])

            num_wallets = len(remainders)
            if num_wallets > 0:
                # Round-robin distribution of leftover
                for i in range(int(leftover)):
                    index = i % num_wallets
                    remainders[index][1]['percent'] += 1


        targets_list = combined_wallets
        predefined_wallet['percent'] = 100 - sum(w['percent'] for w in targets_list)
        targets_list.insert(0, predefined_wallet)

        return {"targets": targets_list}

    except Exception as e:
        logger.error(f"Error creating cyberherd targets: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
        
@http_retry
async def update_cyberherd_targets(targets):
    try:
        url = f'{config["LNBITS_URL"]}/splitpayments/api/v1/targets'
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
        raise HTTPException(
            status_code=e.response.status_code if e.response else 500,
            detail="Failed to update cyberherd targets"
        )
    except Exception as e:
        logger.error(f"Error updating cyberherd targets: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@http_retry
async def get_balance(force_refresh=False):
    try:
        response = await http_client.get(
            f'{config["LNBITS_URL"]}/api/v1/wallet',
            headers={'X-Api-Key': config['HERD_KEY']}
        )
        response.raise_for_status()
        balance = response.json()['balance']
        
        async with app_state.lock:
            app_state.balance = math.floor(balance / 1000)
        return balance
            
    except httpx.HTTPError as e:
        logger.error(f"HTTP error retrieving balance: {e}")
        raise HTTPException(
            status_code=e.response.status_code if e.response else 500,
            detail="Failed to retrieve balance"
        )
    except Exception as e:
        logger.error(f"Error retrieving balance: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@http_retry
async def fetch_btc_price():
    try:
        response = await http_client.get(
            f'{config["OPENHAB_URL"]}/rest/items/BTC_Price_Output/state',
            auth=(config['OH_AUTH_1'], '')
        )
        response.raise_for_status()
        btc_price = float(response.text)
        return btc_price
    except httpx.HTTPError as e:
        logger.error(f"HTTP error fetching BTC price: {e}")
        raise HTTPException(
            status_code=e.response.status_code if e.response else 500,
            detail="Failed to fetch BTC price"
        )
    except Exception as e:
        logger.error(f"Error fetching BTC price: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@http_retry
async def convert_to_sats(amount: float):
    try:
        payload = {"from_": "usd", "amount": amount, "to": "sat"}
        response = await http_client.post(f'{config["LNBITS_URL"]}/api/v1/conversion', json=payload)
        response.raise_for_status()
        sats = response.json()['sats']
        await cache.set(f'usd_to_sats_{amount}', sats, ttl=300)
        return sats
    except httpx.HTTPError as e:
        logger.error(f"HTTP error converting amount: {e}")
        raise HTTPException(
            status_code=response.status_code if e.response else 500,
            detail="Failed to convert amount"
        )
    except Exception as e:
        logger.error(f"Error converting amount: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@http_retry
async def create_invoice(amount: int, memo: str, key: str = config['CYBERHERD_KEY']):
    try:
        url = f"{config['LNBITS_URL']}/api/v1/payments"
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
        url = f"{config['LNBITS_URL']}/api/v1/payments"
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
async def make_lnurl_payment(
    lud16: str,
    msat_amount: int,
    description: str = "LNURL Payment",
    key: str = config['HERD_KEY']
) -> Optional[dict]:
    """
    Attempt an LNURL payment to `lud16` using LNbits.
    :param lud16: The LNURL or LN address (e.g. 'alice@getalby.com').
    :param msat_amount: Amount in *millisatoshis* to send.
    :param description: The memo or LNURL pay 'comment'.
    :param key: LNbits wallet key (defaults to 'HERD_KEY' from config).
    :return: LNbits JSON response dict on success, or None on failure.
    """

    try:
        local_headers = {
            "accept": "application/json",
            "X-API-KEY": key,
            "Content-Type": "application/json"
        }

        # 1) LNURLscan: tell LNbits we want to pay 'lud16' LNURL
        lnurl_scan_url = f"{config['LNBITS_URL']}/api/v1/lnurlscan/{lud16}"
        logger.info(f"Scanning LNURL: {lnurl_scan_url}")
        lnurl_resp = await http_client.get(lnurl_scan_url, headers=local_headers)
        lnurl_resp.raise_for_status()
        lnurl_data = lnurl_resp.json()

        # Check if amount is in the LNURL's allowed range
        if not (lnurl_data["minSendable"] <= msat_amount <= lnurl_data["maxSendable"]):
            logger.error(
                f"{lud16}: {msat_amount} msat is out of bounds "
                f"(min: {lnurl_data['minSendable']}, max: {lnurl_data['maxSendable']})"
            )
            return None

        # 2) Build LNURL Payment Payload
        # LNbits expects 'amount' in msat
        payment_payload = {
            "description_hash": lnurl_data["description_hash"],
            "callback": lnurl_data["callback"],
            "amount": msat_amount,
            "memo": description,
            "description": description
        }

        # If LNURL pay endpoint allows 'comment', optionally include one
        comment_allowed = lnurl_data.get("commentAllowed", 0)
        if comment_allowed > 0:
            payment_payload["comment"] = description

        # 3) If LNURL supports NIP-57 “Zap” (allowsNostr & nostrPubkey),
        #    create & sign the zap event
        if lnurl_data.get("allowsNostr") and lnurl_data.get("nostrPubkey"):
            # Example import from your nostr_signing module:
            # from nostr_signing import sign_zap_event

            zapped_pubkey = lnurl_data["nostrPubkey"]
            zapper_pubkey = "669ebbcccf409ee0467a33660ae88fd17e5379e646e41d7c236ff4963f3c36b6"  # Must match the private key used in sign_zap_event TODO:  add to .env

            # sign_zap_event is a convenience function that builds & signs a kind=9734 event
            # If you only have sign_event, you'd manually build the event structure with tags,
            # then sign it. For example:
            #
            #   event = build_zap_event(
            #       msat_amount, zapper_pubkey, zapped_pubkey, content=description
            #   )
            #   signed_event = await sign_event(event, config['NOS_SEC'])
            #
            # This snippet assumes a sign_zap_event(...) function:
            signed_event = await sign_zap_event(
                msat_amount=msat_amount,
                zapper_pubkey=zapper_pubkey,
                zapped_pubkey=zapped_pubkey,
                private_key_hex=config['NOS_SEC'],
                content=description
            )

            # Attach the signed event JSON to LNbits payment payload
            payment_payload["nostr"] = json.dumps(signed_event)
            logger.info(f"NIP-57 zap event attached for {lud16}")

        # 4) POST to LNbits LNURL pay endpoint
        payment_url = f"{config['LNBITS_URL']}/api/v1/payments/lnurl"
        logger.info(f"Sending LNURL payment to {payment_url}")
        pay_resp = await http_client.post(payment_url, headers=local_headers, json=payment_payload)
        pay_resp.raise_for_status()

        result = pay_resp.json()
        logger.info(f"LNURL payment successful: {result}")
        return result

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error {e.response.status_code}: {e.response.text}")
        return None
    except httpx.RequestError as e:
        logger.error(f"Network request failed: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error in make_lnurl_payment: {e}")
        return None
        
async def zap_lud16_endpoint(lud16: str, sats: int = 1, text="CyberHerd Treats."):
    msat_amount = sats * 1000

    response = await make_lnurl_payment(
        lud16=lud16,
        msat_amount=msat_amount,
        description=text,
        key=config['HERD_KEY'] 
    )
    
    if response:
        return {"status": "success", "result": response}
    else:
        raise HTTPException(status_code=500, detail="Failed to LNURL pay.")

@http_retry
async def is_feeder_override_enabled():
    try:
        response = await http_client.get(
            f'{config["OPENHAB_URL"]}/rest/items/FeederOverride/state',
            auth=(config['OH_AUTH_1'], '')
        )
        response.raise_for_status()
        return response.text.strip() == 'ON'
    except httpx.HTTPError as e:
        logger.error(f"HTTP error checking feeder status: {e}")
        raise HTTPException(
            status_code=e.response.status_code if e.response else 500,
            detail="Failed to check feeder status"
        )
    except Exception as e:
        logger.error(f"Error checking feeder status: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@http_retry
async def trigger_feeder():
    try:
        response = await http_client.post(
            f'{config["OPENHAB_URL"]}/rest/rules/88bd9ec4de/runnow',
            auth=(config['OH_AUTH_1'], '')
        )
        response.raise_for_status()
        return response.status_code == 200
    except httpx.HTTPError as e:
        logger.error(f"HTTP error triggering feeder: {e}")
        raise HTTPException(
            status_code=e.response.status_code if e.response else 500,
            detail="Failed to trigger the feeder rule"
        )
    except Exception as e:
        logger.error(f"Error triggering the feeder rule: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(Exception)
)
async def process_payment_data(payment_data):
    try:
        payment = payment_data.get('payment', {})
        payment_amount = payment.get('amount', 0)

        wallet_balance = payment_data.get('wallet_balance')
        
        async with app_state.lock:
            app_state.balance = math.floor(wallet_balance)

        # Check for Nostr data and handle CyberHerd addition
        nostr_data_raw = payment.get('extra', {}).get('nostr')
        feeder_triggered = False
        new_cyberherd_record_created = False

        if nostr_data_raw and payment_amount >= 10000:
            try:
                nostr_data = json.loads(nostr_data_raw)
                pubkey = nostr_data.get('pubkey')
                note = nostr_data.get('id')  # Use zap event ID as note

                # Extract the event kind from the Nostr data
                event_kind = nostr_data.get('kind')
                kinds = [event_kind]

                amount_sats = payment_amount / 1000

                # Extract the 'e' tag (zapped note ID)
                event_id = next((tag[1] for tag in nostr_data.get('tags', []) if tag[0] == 'e'), None)

                if pubkey and event_id:
                    # Check for CyberHerd tag
                    if await check_cyberherd_tag(event_id):
                        # Fetch metadata for the pubkey
                        metadata_fetcher = MetadataFetcher()
                        metadata = await metadata_fetcher.lookup_metadata(pubkey)

                        if metadata:
                            lud16 = metadata.get('lud16')
                            nip05 = metadata.get('nip05')
                            display_name = metadata.get('display_name', 'Anon')

                            # Verify lud16 and nip05
                            is_valid_lud16 = lud16 and await Verifier.verify_lud16(lud16)
                            #is_valid_nip05 = nip05 and await Verifier.verify_nip05(nip05, pubkey)

                            if not is_valid_lud16:
                                logger.warning(
                                    f"Record rejected for pubkey {pubkey}: "
                                    f"Valid lud16={is_valid_lud16}"
                                )
                            else:
                                nprofile = await generate_nprofile(pubkey)
                                if not nprofile:
                                    logger.warning(f"Failed to generate nprofile for pubkey: {pubkey}")
                                else:
                                    logger.info(f"generated nprofile: {nprofile} for {pubkey}")

                                    # Create CyberHerdData instance with dynamic kinds
                                    new_member_data = CyberHerdData(
                                        display_name=display_name,
                                        event_id=event_id,
                                        note=note,
                                        kinds=kinds,
                                        pubkey=pubkey,
                                        nprofile=nprofile,
                                        lud16=lud16,
                                        notified=None,
                                        payouts=0.0,
                                        amount=amount_sats
                                    )
                                    
                                    #TODO: remove this part after implementing cyberherd payments.  (It's the splits ext)
                                    logger.info(f"Calling update_cyber_herd() with {new_member_data}")
                                    result = await update_cyber_herd([new_member_data])
                                    if result and result.get("new_members_added", 0) > 0:
                                        new_cyberherd_record_created = True
                        else:
                            logger.warning(f"Metadata lookup failed for pubkey: {pubkey}")
                    else:
                        logger.info(f"No 'CyberHerd' tag found for event_id: {event_id}")
                else:
                    logger.warning("Missing pubkey or event_id in Nostr data. Processing as normal payment.")
            except json.JSONDecodeError:
                logger.error("Invalid JSON in Nostr data.")
            except Exception as e:
                logger.error(f"Error processing Nostr data: {e}")

        # Check for feeder trigger (regardless of new membership)
        if payment_amount > 0 and not await is_feeder_override_enabled():
            if app_state.balance >= TRIGGER_AMOUNT_SATS:
                if await trigger_feeder():
                    feeder_triggered = True
                    logger.info("Feeder triggered successfully.")
                    
                    #TODO:  makes cyberherd payments
                    status = await send_payment(app_state.balance)

                    if status['success']:
                        # Send a "feeder_triggered" message
                        feeder_msg, _ = await messaging.make_messages(
                            config['NOS_SEC'],
                            int(payment_amount / 1000),
                            0,
                            "feeder_triggered"
                        )
                        await send_messages_to_clients(feeder_msg)

            # If feeder not triggered, do the usual "sats_received" fallback if no new members
            if not feeder_triggered and not new_cyberherd_record_created:
                difference = TRIGGER_AMOUNT_SATS - app_state.balance

                # default payment message (not a zap)
                if (payment_amount / 1000) >= 10:
                    message, _ = await messaging.make_messages(
                        config['NOS_SEC'], 
                        int(payment_amount / 1000), 
                        difference, 
                        "sats_received"
                    )
                    await send_messages_to_clients(message)
        else:
            logger.info("Feeder override is ON or payment amount is non-positive. Skipping feeder logic.")

    except Exception as e:
        logger.error(f"Error processing payment data: {e}")
        raise

@http_retry
async def send_payment(balance: int):
    memo = 'Reset Herd Wallet'
    try:
        payment_request = await create_invoice(balance, memo)
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

# ---------------------------------------------------------------------------
#                     REFACTORED CYBER HERD ENDPOINT & HELPERS
# ---------------------------------------------------------------------------

@app.post("/cyber_herd")
async def update_cyber_herd(data: List[CyberHerdData]):
    """
    Refactored endpoint for adding/updating CyberHerd members, using real 'amount',
    'difference', 'spots_remaining' as before. Sends 'cyber_herd' messages and 
    schedules notifications for new/special members.
    """
    try:
        should_get_balance = any(9734 not in item.kinds for item in data)

        # Get current herd size once
        query = "SELECT COUNT(*) as count FROM cyber_herd"
        result = await database.fetch_one(query)
        current_herd_size = result['count']

        if current_herd_size >= MAX_HERD_SIZE:
            logger.info(f"Herd full: {current_herd_size} members")
            return {"status": "herd full"}

        members_to_notify = []
        targets_to_update = []

        for item in data:
            item_dict = item.dict()
            pubkey = item_dict['pubkey']

            logger.debug(f"Processing pubkey: {pubkey} with kinds: {item_dict['kinds']}")

            # Check if member exists
            check_query = """
                SELECT COUNT(*) as count, kinds, notified 
                FROM cyber_herd 
                WHERE pubkey = :pubkey
            """
            member_record = await database.fetch_one(
                check_query, 
                values={"pubkey": pubkey}
            )

            if member_record['count'] == 0 and current_herd_size < MAX_HERD_SIZE:
                await process_new_member(
                    item_dict=item_dict,
                    members_to_notify=members_to_notify,
                    targets_to_update=targets_to_update
                )
                current_herd_size += 1

            elif member_record['count'] > 0:
                await process_existing_member(
                    item_dict=item_dict,
                    item=item,
                    result=member_record,
                    members_to_notify=members_to_notify,
                    targets_to_update=targets_to_update
                )

        # Recalculate LNbits targets if needed
        if targets_to_update:
            await update_lnbits_targets(targets_to_update)

        # Update balance if needed
        if should_get_balance:
            await update_system_balance()

        difference = max(0, TRIGGER_AMOUNT_SATS - app_state.balance)

        # Schedule notifications in one task
        if members_to_notify:
            await process_notifications(
                members_to_notify,
                difference,
                current_herd_size
            )

        return {
            "status": "success",
            "new_members_added": len([m for m in members_to_notify if m['type'] == 'new_member'])
        }

    except HTTPException as e:
        logger.error(f"HTTPException in update_cyber_herd: {e.detail}")
        raise e
    except Exception as e:
        logger.error(f"Failed to update cyber herd: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


async def process_new_member(
    item_dict: dict, 
    members_to_notify: list, 
    targets_to_update: list
):
    """Insert a brand-new member into the database and mark for LNbits updates."""
    pubkey = item_dict['pubkey']
    item_dict['notified'] = None
    
    # Convert 'kinds' to a comma-separated string if needed
    if isinstance(item_dict['kinds'], list):
        item_dict['kinds'] = ','.join(map(str, item_dict['kinds']))
    elif isinstance(item_dict['kinds'], str):
        item_dict['kinds'] = item_dict['kinds'].strip()
    else:
        logger.warning(f"Unexpected type for 'kinds': {type(item_dict['kinds'])}")
        item_dict['kinds'] = ''

    insert_query = """
        INSERT INTO cyber_herd (
            pubkey, display_name, event_id, note, kinds, nprofile, lud16, 
            notified, payouts, amount
        ) VALUES (
            :pubkey, :display_name, :event_id, :note, :kinds, :nprofile, 
            :lud16, :notified, :payouts, :amount
        )
    """
    try:
        await database.execute(insert_query, values={
            "pubkey": item_dict["pubkey"],
            "display_name": item_dict.get("display_name") or "Anon",
            "event_id": item_dict.get("event_id"),
            "note": item_dict.get("note"),
            "kinds": item_dict["kinds"],
            "nprofile": item_dict.get("nprofile"),
            "lud16": item_dict.get("lud16"),
            "notified": None,
            "payouts": item_dict.get("payouts", 0.0),
            "amount": item_dict.get("amount", 0)
        })
        
        # Mark this new member for notification
        members_to_notify.append({
            'pubkey': pubkey,
            'type': 'new_member',
            'data': item_dict
        })
        
        # If they have a lud16, update LNbits targets
        if item_dict['lud16']:
            targets_to_update.append({
                'wallet': item_dict['lud16'],
                'alias': pubkey,
                'payouts': item_dict.get("payouts", 0.0)
            })
        
        logger.info(f"Inserted new member with pubkey: {pubkey}")
    except Exception as e:
        logger.error(f"Failed to insert new member with pubkey {pubkey}: {e}")


async def process_existing_member(
    item_dict: dict, 
    item: CyberHerdData, 
    result: dict,
    members_to_notify: list, 
    targets_to_update: list
):
    """Handle updates to an existing member in the cyber herd."""
    pubkey = item_dict['pubkey']
    new_amount = item_dict.get('amount', 0)

    kinds_int = parse_kinds(item.kinds)
    if not kinds_int:
        return

    logger.debug(f"Parsed kinds for pubkey {pubkey}: {kinds_int}")

    # Check if new special kinds arrived
    if any(kind in [6, 7, 9734] for kind in kinds_int):
        current_kinds = parse_current_kinds(result["kinds"])
        
        payout_increment, updated_kinds_str = calculate_member_updates(
            kinds_int, current_kinds, new_amount
        )

        # Notify if the member wasn't previously "notified"
        if result["notified"] is None:
            members_to_notify.append({
                'pubkey': pubkey,
                'type': 'special_kinds',
                'data': {
                    **item_dict,
                    'payout_increment': payout_increment
                }
            })

        await update_member_record(
            pubkey=pubkey,
            new_amount=new_amount,
            payout_increment=payout_increment,
            updated_kinds=updated_kinds_str,
            item_dict=item_dict
        )

        if item_dict['lud16']:
            targets_to_update.append({
                'wallet': item_dict['lud16'],
                'alias': pubkey,
                'payouts': payout_increment
            })

def parse_kinds(kinds: Union[List[int], str]) -> List[int]:
    """Parse 'kinds' into a list of ints."""
    if isinstance(kinds, list):
        return kinds
    elif isinstance(kinds, str):
        try:
            return [int(k.strip()) for k in kinds.split(',') if k.strip().isdigit()]
        except ValueError as e:
            logger.error(f"Error parsing kinds string: {e}")
            return []
    else:
        logger.warning(f"Unexpected type for 'kinds': {type(kinds)}")
        return []

def parse_current_kinds(kinds_str: str) -> Set[int]:
    """Parse DB 'kinds' string into a set of ints."""
    if not kinds_str:
        return set()
    try:
        return set(int(k.strip()) for k in kinds_str.split(',') if k.strip().isdigit())
    except ValueError as e:
        logger.error(f"Error parsing current kinds: {e}")
        return set()

def calculate_member_updates(
    kinds_int: List[int],
    current_kinds: Set[int],
    new_amount: int
) -> Tuple[float, str]:
    """
    Recalculate how much to add to 'payouts' based on newly-seen kinds.
    - For kinds 6 & 7, we add a small bonus only once (the first time).
    - For kind 9734, we *always* add 'calculate_payout(new_amount)' 
      so repeated zaps keep raising payouts.
    """
    payout_increment = 0.0

    if 9734 in kinds_int:
        payout_increment += calculate_payout(float(new_amount))

    new_special_kinds = [k for k in [6, 7] if k in kinds_int and k not in current_kinds]
    for k in new_special_kinds:
        if k == 7:
            payout_increment += 0.1
        elif k == 6:
            payout_increment += 0.2

    # Merge new kinds into existing
    updated_kinds_set = current_kinds.union(set(kinds_int))
    updated_kinds_str = ','.join(map(str, sorted(updated_kinds_set)))

    return payout_increment, updated_kinds_str

async def update_member_record(
    pubkey: str,
    new_amount: float,
    payout_increment: float,
    updated_kinds: str,
    item_dict: dict
):
    """Perform the DB update for an existing member."""
    update_query = """
        UPDATE cyber_herd
        SET amount = amount + :new_amount,
            payouts = payouts + :payout_increment,
            kinds = :updated_kinds,
            event_id = :event_id,
            note = :note,
            display_name = :display_name,
            nprofile = :nprofile,
            lud16 = :lud16
        WHERE pubkey = :pubkey
    """
    try:
        await database.execute(update_query, values={
            "new_amount": new_amount,
            "payout_increment": payout_increment,
            "updated_kinds": updated_kinds,
            "event_id": item_dict.get("event_id"),
            "note": item_dict.get("note"),
            "display_name": item_dict.get("display_name") or "Anon",
            "nprofile": item_dict.get("nprofile"),
            "lud16": item_dict.get("lud16"),
            "pubkey": pubkey
        })
        logger.info(f"Updated member with pubkey: {pubkey}")
    except Exception as e:
        logger.error(f"Failed to update member with pubkey {pubkey}: {e}")

async def update_lnbits_targets(targets: List[dict]):
    """
    Fetch existing LNbits targets, merge with current DB data,
    and update LNbits in one shot.
    """
    try:
        initial_targets = await fetch_cyberherd_targets()
        current_members = await database.fetch_all(
            "SELECT lud16, pubkey, payouts FROM cyber_herd WHERE lud16 IS NOT NULL"
        )
        
        all_targets = [
            {
                'wallet': member['lud16'],
                'alias': member['pubkey'],
                'payouts': member['payouts']
            }
            for member in current_members
        ]

        updated_targets = await create_cyberherd_targets(
            new_targets_data=all_targets,
            initial_targets=initial_targets
        )
        
        if updated_targets:
            await update_cyberherd_targets(updated_targets)
            logger.info("LNbits targets updated successfully.")
        else:
            logger.warning("No targets to update for LNbits.")
    except Exception as e:
        logger.error(f"Failed to update LNbits targets: {e}")

async def update_system_balance():
    """Refresh the LNbits wallet balance in the global app_state."""
    try:
        response = await get_balance_route(force_refresh=True)
        balance_value = response.get("balance", 0)
        async with app_state.lock:
            app_state.balance = int(balance_value / 1000)
        logger.info(f"Updated balance to {app_state.balance}")
    except Exception as e:
        logger.error(f"Failed to update balance: {e}")

async def process_notifications(
    members_to_notify: List[dict],
    difference: int,
    current_herd_size: int
):
    try:
        async with notification_semaphore:
            for member in members_to_notify:
                pubkey = member.get('pubkey', 'unknown')
                member_type = member.get('type', 'unspecified')
                member_data = member.get('data', {})

                try:
                    spots_remaining = MAX_HERD_SIZE - current_herd_size

                    # Call make_messages for "cyber_herd"
                    message_content, raw_command_output = await messaging.make_messages(
                        config['NOS_SEC'],
                        member_data.get('amount', 0),
                        difference,
                        "cyber_herd",
                        member_data,
                        spots_remaining
                    )

                    # Broadcast the message
                    await send_messages_to_clients(message_content)

                    # Update the 'notified' field in DB
                    await update_notified_field(pubkey, raw_command_output)

                except Exception as e:
                    # Log exceptions for each individual member
                    logger.exception(f"Failed to process notification for {member_type} - {pubkey}: {e}")

    except Exception as e:
        # Log any higher-level failures in the
        logger.exception(f"process_notifications failed with an error: {e}")

async def update_notified_field(pubkey: str, raw_command_output: str):
    """
    Update the 'notified' field with the 'id' from the raw_command_output (or default).
    """
    update_notified_query = """
        UPDATE cyber_herd 
        SET notified = :notified_value 
        WHERE pubkey = :pubkey
    """
    notified_value = "notified"
    try:
        command_output_json = json.loads(raw_command_output)
        notified_value = command_output_json.get("id", "notified")
    except Exception:
        pass

    await database.execute(
        update_notified_query,
        values={"notified_value": notified_value, "pubkey": pubkey}
    )
# ---------------------------------------------------------------------------


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
        url = f"{config['LNBITS_URL']}/splitpayments/api/v1/targets"

        # Delete all existing targets
        response = await http_client.delete(url, headers=headers)
        response.raise_for_status()
        logger.info("Existing CyberHerd targets deleted successfully.")

        # Add predefined wallet target with 100% allocation
        predefined_wallet = {
            'wallet': config['PREDEFINED_WALLET_ADDRESS'],
            'alias': config['PREDEFINED_WALLET_ALIAS'],
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