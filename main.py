from math import floor
from typing import List, Optional, Dict, Set, Union, Tuple, Any
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
from utils.cyberherd_module import MetadataFetcher, Verifier, generate_nprofile, check_cyberherd_tag, lookup_relay_list
from utils.nostr_signing import sign_event, sign_zap_event

# Configuration and Constants
MAX_HERD_SIZE = 3
PREDEFINED_WALLET_PERCENT_RESET = 100
TRIGGER_AMOUNT_SATS = 850
HEADBUTT_MIN_SATS = 10
HEADBUTT_COOLDOWN_SECONDS = 1

# Add relay configuration
RELAYS = [
    "wss://relay.primal.net/",
    "wss://relay.damus.io/"
]

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
        self.last_headbutt_time: float = 0  # Track last headbutt time

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
    picture: Optional[str] = None
    relays: Optional[List[str]] = RELAYS[:2]  # Default to first two relays from configuration

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

class SetGoatSatsData(BaseModel):
    new_amount: int

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
            amount INTEGER,
            picture TEXT,
            relays Text
        )
    ''')
    await database.execute('''
        CREATE TABLE IF NOT EXISTS cache (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            expires_at REAL NOT NULL
        )
    ''')

    try:
        # Initialize balance
        response = await get_balance_route(force_refresh=True)
        app_state.balance = response.get("balance", 0)
        
        # Initialize goat_sats_state cache
        await get_goat_sats_sum_today()
        
    except Exception as e:
        logger.error(f"Failed to initialize states: {e}. Defaulting to 0.")
        app_state.balance = 0

    # Start background tasks
    asyncio.create_task(cleanup_cache())
    asyncio.create_task(schedule_daily_reset())
    asyncio.create_task(periodic_informational_messages())

async def schedule_daily_reset():
    while True:
        now = datetime.utcnow()
        next_midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        sleep_seconds = (next_midnight - now).total_seconds()
        await asyncio.sleep(sleep_seconds)

        status = await reset_cyber_herd()
                        
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
            message, _ = await messaging.make_messages(config['NOS_SEC'], 0, 0, "interface_info")
            await send_messages_to_clients(message)

def calculate_payout(amount: float) -> float:
    """Calculate payout based on the amount received (e.g., for zaps)."""
    if amount < 10:
        return 0.0
    # Calculate payout units for every 10 sats (floor division)
    units = amount // 10
    payout = units * 0.01
    # Apply min/max bounds
    payout = min(payout, 1.0)
    return round(payout, 2)

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
        non_predefined = [
            item for item in new_targets_data 
            if item['wallet'] != config['PREDEFINED_WALLET_ADDRESS']
        ]
        
        # Always set predefined wallet to 90%
        predefined_wallet = {
            'wallet': config['PREDEFINED_WALLET_ADDRESS'],
            'alias': config['PREDEFINED_WALLET_ALIAS'],
            'percent': 90  # Fixed at 90%
        }
        
        # Remaining 10% to split between other wallets
        max_allocation = 10  # The remaining percentage for other wallets

        combined_wallets = []
        for item in new_targets_data:
            wallet = item['wallet']
            name = item.get('alias', 'Unknown')
            payouts = item.get('payouts', 1.0)
            if wallet != config['PREDEFINED_WALLET_ADDRESS']:
                combined_wallets.append({'wallet': wallet, 'alias': name, 'payouts': payouts})

        total_payouts = sum(w['payouts'] for w in combined_wallets) or 1
        min_percent_per_wallet = 1
        max_wallets_allowed = floor(max_allocation / min_percent_per_wallet)

        # Limit number of wallets if necessary
        if len(combined_wallets) > max_wallets_allowed:
            combined_wallets = sorted(
                combined_wallets,
                key=lambda x: x['payouts'],
                reverse=True
            )[:max_wallets_allowed]
            total_payouts = sum(w['payouts'] for w in combined_wallets) or 1

        # Initial minimum allocation
        for wallet in combined_wallets:
            wallet['percent'] = min_percent_per_wallet
        allocated = min_percent_per_wallet * len(combined_wallets)
        remaining_allocation = max_allocation - allocated

        # Distribute remaining allocation proportionally
        if remaining_allocation > 0 and combined_wallets:
            for wallet in combined_wallets:
                prop = wallet['payouts'] / total_payouts
                additional = floor(prop * remaining_allocation)
                wallet['percent'] += additional

            # Handle any leftover percent due to rounding
            current_total = sum(w['percent'] for w in combined_wallets)
            leftover = max_allocation - current_total
            
            if leftover > 0:
                # Sort by payouts and give extra percents to top contributors
                sorted_wallets = sorted(combined_wallets, key=lambda x: x['payouts'], reverse=True)
                for i in range(int(leftover)):
                    sorted_wallets[i % len(sorted_wallets)]['percent'] += 1

        targets_list = [predefined_wallet] + combined_wallets
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
        # Get the current BTC price in USD (cached at the endpoint)
        btc_price = await fetch_btc_price()

        # Calculate the number of satoshis:
        # 1 BTC = 100,000,000 sats, so:
        sats = int(round((amount / btc_price) * 100_000_000))
        return sats
    except Exception as e:
        logger.error(f"Error converting amount {amount} USD to sats: {e}")
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
            "out": False,  # Generate an invoice
            "amount": amount,
            "unit": "sat",
            "memo": memo
        }
        response = await http_client.post(url, json=data, headers=headers)
        response.raise_for_status()
        return response.json().get('bolt11')  # Return the BOLT11 invoice
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
            "out": True,  # Pay an invoice
            "unit": "sat",  # Specify the unit as "sat"
            "bolt11": payment_request  # Supply the BOLT11 invoice
        }
        response = await http_client.post(url, json=data, headers=headers)
        response.raise_for_status()
        return response.json()  # Return the payment response
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
    description: str = "",
    key: str = config['HERD_KEY']
) -> Optional[dict]:
    try:
        local_headers = {
            "accept": "application/json",
            "X-API-KEY": key,
            "Content-Type": "application/json"
        }
        
        # First get the LNURL-pay parameters
        lnurl_scan_url = f"{config['LNBITS_URL']}/api/v1/lnurlscan/{lud16}"
        logger.info(f"Scanning LNURL: {lnurl_scan_url}")
        lnurl_resp = await http_client.get(lnurl_scan_url, headers=local_headers)
        lnurl_resp.raise_for_status()
        lnurl_data = lnurl_resp.json()

        # Verify amount is within allowed range
        if not (lnurl_data["minSendable"] <= msat_amount <= lnurl_data["maxSendable"]):
            logger.error(
                f"{lud16}: {msat_amount} msat is out of bounds "
                f"(min: {lnurl_data['minSendable']}, max: {lnurl_data['maxSendable']})"
            )
            return None

        # Prepare payment payload
        payment_payload = {
            "callback": lnurl_data["callback"],
            "amount": msat_amount,
            "description_hash": lnurl_data["description_hash"],
            "description": description
        }

        # Add comment if allowed
        if lnurl_data.get("commentAllowed", 0) > 0:
            payment_payload["comment"] = description

        # Add Nostr zap data if supported
        if lnurl_data.get("allowsNostr") and lnurl_data.get("nostrPubkey"):
            zapped_pubkey = lnurl_data["nostrPubkey"]
            zapper_pubkey = config['HEX_KEY']  # Our public key
            
            signed_event = await sign_zap_event(
                msat_amount=msat_amount,
                zapper_pubkey=zapper_pubkey,
                zapped_pubkey=zapped_pubkey,
                private_key_hex=config['NOS_SEC'],
                content=description
            )
            
            payment_payload["nostr"] = json.dumps(signed_event)
            logger.info(f"Added NIP-57 zap request for {lud16}")

        # Send the payment
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
        feeder_trigger_response = await http_client.post(
            f'{config["OPENHAB_URL"]}/rest/rules/88bd9ec4de/runnow',
            auth=(config['OH_AUTH_1'], '')
        )
        feeder_trigger_response.raise_for_status()
        return feeder_trigger_response.status_code == 200
    except httpx.HTTPError as e:
        logger.error(f"HTTP error triggering feeder or GoatFeedingsIncrement rule: {e}")
        raise HTTPException(
            status_code=e.response.status_code if e.response else 500,
            detail="Failed to trigger the feeder and GoatFeedingsIncrement rule"
        )
    except Exception as e:
        logger.error(f"Error triggering the feeder and GoatFeedingsIncrement rule: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
        
@http_retry
async def get_goat_feedings():
    try:
        auth = (config['OH_AUTH_1'], '')
        headers = {"accept": "text/plain"}
        get_url = f"{config['OPENHAB_URL']}/rest/items/GoatFeedings/state"
        response = await http_client.get(get_url, headers=headers, auth=auth)
        response.raise_for_status()

        try:
            feedings = int(response.text.strip())
        except Exception as e:
            logger.warning(f"Failed to parse GoatFeedings state '{response.text.strip()}': {e}. Defaulting to 0.")
            feedings = 0

        logger.info(f"Returning latest GoatFeedings state: {feedings}")
        return feedings

    except httpx.HTTPError as e:
        logger.error(f"HTTP error retrieving GoatFeedings state from OpenHAB: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch GoatFeedings state from OpenHAB")
    except Exception as e:
        logger.error(f"Unexpected error retrieving GoatFeedings state: {e}")
        raise HTTPException(status_code=500, detail="Unexpected error retrieving GoatFeedings state")
      
@http_retry
async def get_goat_sats_sum_today():
    """Get GoatSats state, preferring cached value if available."""
    try:
        # Try to get from cache first
        cached_state = await cache.get("goat_sats_state")
        if cached_state is not None:
            logger.debug("Using cached GoatSats state")
            return {"sum_goat_sats": cached_state}

        # If not in cache, fetch from OpenHAB
        auth = (config['OH_AUTH_1'], '')
        headers = {"accept": "text/plain"}
        get_url = f"{config['OPENHAB_URL']}/rest/items/GoatSats/state"
        response = await http_client.get(get_url, headers=headers, auth=auth)
        response.raise_for_status()
        
        try:
            latest_state = int(float(response.text.strip()))
            # Cache the result without TTL
            await cache.set("goat_sats_state", latest_state)
            logger.info(f"Updated cached GoatSats state to: {latest_state}")
            return {"sum_goat_sats": latest_state}
        except Exception as e:
            logger.warning(f"Failed to parse GoatSats state '{response.text.strip()}': {e}. Defaulting to 0.")
            return {"sum_goat_sats": 0}
    
    except httpx.HTTPError as e:
        logger.error(f"HTTP error retrieving GoatSats state from OpenHAB: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch GoatSats state from OpenHAB")
    except Exception as e:
        logger.error(f"Unexpected error retrieving GoatSats state: {e}")
        raise HTTPException(status_code=500, detail="Unexpected error retrieving GoatSats state")

@http_retry
async def update_goat_sats(sats_received: int):
    """Update GoatSats state in both cache and OpenHAB."""
    try:
        # Get current state (preferring cache)
        current_state_data = await get_goat_sats_sum_today()
        current_state = current_state_data["sum_goat_sats"]
        new_state = current_state + sats_received
        
        # Update OpenHAB
        auth = (config['OH_AUTH_1'], '')
        headers = {
            "accept": "application/json",
            "Content-Type": "text/plain"
        }
        put_url = f"{config['OPENHAB_URL']}/rest/items/GoatSats/state"
        put_response = await http_client.put(put_url, headers=headers, auth=auth, content=str(new_state))
        put_response.raise_for_status()
        
        # Update cache without TTL
        await cache.set("goat_sats_state", new_state)
        logger.info(f"Updated GoatSats state to {new_state} (cache + OpenHAB)")
    
    except httpx.HTTPError as e:
        logger.error(f"HTTP error updating GoatSats in OpenHAB: {e}")
    except Exception as e:
        logger.error(f"Unexpected error updating GoatSats: {e}")

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
        sats_received = payment_amount // 1000
        wallet_balance = payment_data.get('wallet_balance')
        logger.info(f"Received payment: {payment}")

        if wallet_balance is not None:
            async with app_state.lock:
                app_state.balance = math.floor(wallet_balance)
        else:
            logger.warning("No wallet_balance provided in payment_data; skipping balance update.")

        if sats_received > 0:
            await update_goat_sats(sats_received)

        extra = payment.get('extra', {})

        feeder_triggered = False
        new_cyberherd_record_created = False

        if sats_received > 0 and not await is_feeder_override_enabled():
            if app_state.balance >= TRIGGER_AMOUNT_SATS:
                if await trigger_feeder():
                    feeder_triggered = True
                    logger.info("Feeder triggered successfully.")
                    
                    status = await send_payment(app_state.balance)

                    if status['success']:
                        feeder_msg, _ = await messaging.make_messages(
                            config['NOS_SEC'],
                            sats_received,
                            0,
                            "feeder_triggered"
                        )
                        await send_messages_to_clients(feeder_msg)

            if not feeder_triggered and not new_cyberherd_record_created:
                difference = TRIGGER_AMOUNT_SATS - app_state.balance
                if sats_received >= 10:
                    message, _ = await messaging.make_messages(
                        config['NOS_SEC'], 
                        sats_received, 
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

@app.post("/cyber_herd")
async def update_cyber_herd(data: List[CyberHerdData]):
    try:
        should_get_balance = any(9734 not in item.kinds for item in data)
        query = "SELECT COUNT(*) as count FROM cyber_herd"
        result = await database.fetch_one(query)
        current_herd_size = result['count']

        if current_herd_size >= MAX_HERD_SIZE:
            logger.info(f"Herd full: {current_herd_size} members - attempting headbutting")
            # Process headbutting attempts when herd is full
            headbutt_results = await process_headbutting_attempts(data)
            if headbutt_results:
                return {
                    "status": "headbutt_success",
                    "headbutts": headbutt_results
                }
            else:
                # Send headbutt info message when herd is full but no headbutts occurred
                await send_headbutt_info_message()
                return {"status": "herd full"}

        members_to_notify = []
        targets_to_update = []

        for item in data:
            item_dict = item.dict()
            pubkey = item_dict['pubkey']
            logger.debug(f"Processing pubkey: {pubkey} with kinds: {item_dict['kinds']}")

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

        if targets_to_update:
            await update_lnbits_targets(targets_to_update)

        if should_get_balance:
            await update_system_balance()

        difference = max(0, TRIGGER_AMOUNT_SATS - app_state.balance)

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
    """Process a new member joining the cyber herd."""
    pubkey = item_dict['pubkey']
    item_dict['notified'] = None

    # If relays not provided, use default configuration
    if 'relays' not in item_dict or not item_dict['relays']:
        item_dict['relays'] = RELAYS[:2]

    # Ensure 'kinds' is a comma-separated string
    if isinstance(item_dict['kinds'], list):
        item_dict['kinds'] = ','.join(map(str, item_dict['kinds']))
    elif isinstance(item_dict['kinds'], str):
        item_dict['kinds'] = item_dict['kinds'].strip()
    else:
        logger.warning(f"Unexpected type for 'kinds': {type(item_dict['kinds'])}")
        item_dict['kinds'] = ''

    # Parse kinds into integers and calculate payouts if kind 9734 is present
    kinds_int = parse_kinds(item_dict['kinds'])
    if 9735 in kinds_int:
        item_dict["payouts"] = calculate_payout(item_dict.get("amount", 0))
    else:
        item_dict["payouts"] = item_dict.get("payouts", 0.0)

    insert_query = """
        INSERT INTO cyber_herd (
            pubkey, display_name, event_id, note, kinds, nprofile, lud16, 
            notified, payouts, amount, picture
        ) VALUES (
            :pubkey, :display_name, :event_id, :note, :kinds, :nprofile, :lud16, 
            :notified, :payouts, :amount, :picture
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
            "payouts": item_dict["payouts"],
            "amount": item_dict.get("amount", 0),
            "picture": item_dict.get("picture")
        })
        
        members_to_notify.append({
            'pubkey': pubkey,
            'type': 'new_member',
            'data': item_dict
        })
        
        # If a valid lud16 is provided and kind 7 is not present, add to targets update list
        if item_dict['lud16'] and 7 not in kinds_int:
            targets_to_update.append({
                'wallet': item_dict['lud16'],
                'alias': pubkey,
                'payouts': item_dict["payouts"]
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
            member_data = {
                **item_dict,
                'payout_increment': payout_increment,
                'picture': item_dict.get('picture'),  # Include picture
                'relays': item_dict.get('relays', [])[:2]  # Include first 2 relays
            }
            members_to_notify.append({
                'pubkey': pubkey,
                'type': 'special_kinds',
                'data': member_data
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
    payout_increment = 0.0

    if 9735 in kinds_int:
        zap_payout = calculate_payout(float(new_amount))
        payout_increment += zap_payout

    new_special_kinds = [k for k in [6, 7] if k in kinds_int and k not in current_kinds]
    for k in new_special_kinds:
        if k == 7:
            payout_increment += 0.0
        elif k == 6:
            payout_increment += 0.2

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
            lud16 = :lud16,
            picture = :picture,
            relays = :relays
        WHERE pubkey = :pubkey
    """
    try:
        # Ensure relays are present in item_dict
        if 'relays' not in item_dict or not item_dict['relays']:
            item_dict['relays'] = RELAYS[:2]

        # Convert relays list to JSON string for storage
        relays_json = json.dumps(item_dict['relays'])
        
        await database.execute(update_query, values={
            "new_amount": new_amount,
            "payout_increment": payout_increment,
            "updated_kinds": updated_kinds,
            "event_id": item_dict.get("event_id"),
            "note": item_dict.get("note"),
            "display_name": item_dict.get("display_name") or "Anon",
            "nprofile": item_dict.get("nprofile"),
            "lud16": item_dict.get("lud16"),
            "picture": item_dict.get("picture"),
            "relays": relays_json,
            "pubkey": pubkey
        })
        logger.info(f"Updated member with pubkey: {pubkey}")
    except Exception as e:
        logger.error(f"Failed to update member with pubkey {pubkey}: {e}")

async def update_lnbits_targets(targets: List[dict]):
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

                # Ensure member_data has relays
                if not member_data.get('relays'):
                    member_data['relays'] = RELAYS[:2]

                try:
                    spots_remaining = MAX_HERD_SIZE - current_herd_size

                    message_content, raw_command_output = await messaging.make_messages(
                        config['NOS_SEC'],
                        member_data.get('amount', 0),
                        difference,
                        "cyber_herd",
                        member_data,
                        spots_remaining
                    )

                    await send_messages_to_clients(message_content)
                    await update_notified_field(pubkey, raw_command_output)

                except Exception as e:
                    logger.exception(f"Failed to process notification for {member_type} - {pubkey}: {e}")

    except Exception as e:
        logger.exception(f"process_notifications failed with an error: {e}")

async def update_notified_field(pubkey: str, raw_command_output: str):
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
    
async def get_cyberherd_list() -> List[Dict[str, any]]:
    query = "SELECT * FROM cyber_herd"
    return await database.fetch_all(query)
    
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
        await database.execute("DELETE FROM cyber_herd")
        logger.info("CyberHerd table cleared successfully.")
        headers = {
            'accept': 'application/json',
            'X-API-KEY': config['CYBERHERD_KEY']
        }
        url = f"{config['LNBITS_URL']}/splitpayments/api/v1/targets"
        response = await http_client.delete(url, headers=headers)
        response.raise_for_status()
        logger.info("Existing CyberHerd targets deleted successfully.")
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
        select_query = "SELECT * FROM cyber_herd WHERE lud16 = :lud16"
        record = await database.fetch_one(select_query, values={"lud16": lud16})
        if not record:
            logger.warning(f"No record found with lud16: {lud16}")
            raise HTTPException(status_code=404, detail="Record not found")
        delete_query = "DELETE FROM cyber_herd WHERE lud16 = :lud16"
        await database.execute(delete_query, values={"lud16": lud16})
        logger.info(f"Record with lud16 {lud16} deleted successfully.")
        return {"status": "success", "message": f"Record with lud16 {lud16} deleted successfully."}
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Failed to delete record: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
        
@app.put("/goat_sats/set")
async def set_goat_sats_endpoint(data: SetGoatSatsData):
    try:
        auth = (config['OH_AUTH_1'], '')
        headers = {
            "accept": "application/json",
            "Content-Type": "text/plain"
        }
        new_state = data.new_amount
        put_url = f"{config['OPENHAB_URL']}/rest/items/GoatSats/state"
        put_response = await http_client.put(put_url, headers=headers, auth=auth, content=str(new_state))
        put_response.raise_for_status()
        
        # Update cache without TTL
        await cache.set("goat_sats_state", new_state)
        logger.info(f"Manually set GoatSats in OpenHAB to {new_state} sats")
        return {"status": "success", "new_state": new_state}
    
    except httpx.HTTPError as e:
        logger.error(f"HTTP error setting GoatSats in OpenHAB: {e}")
        raise HTTPException(status_code=500, detail="Failed to update GoatSats in OpenHAB")
    except Exception as e:
        logger.error(f"Unexpected error setting GoatSats: {e}")
        raise HTTPException(status_code=500, detail="Unexpected error setting GoatSats")
        
@app.get("/goat_sats/sum_today")
async def get_goat_sats_sum_today_endpoint():
    return await get_goat_sats_sum_today()
    
@app.get("/goat_sats/feedings")
async def get_goat_feedings_endpoint():
    feedings = await get_goat_feedings()
    return {"goat_feedings": feedings}

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
        
@app.post("/headbutt")
async def headbutt(data: dict):
    try:
        # Extract amount from request data
        amount = data.get('amount', 0)
        
        # Check if amount meets minimum requirement
        if amount < HEADBUTT_MIN_SATS:
            return {
                "status": "error",
                "message": f"Minimum amount for headbutting is {HEADBUTT_MIN_SATS} sats"
            }
        
        # Check cooldown period
        current_time = time.time()
        async with app_state.lock:
            time_since_last_headbutt = current_time - app_state.last_headbutt_time
            
            if time_since_last_headbutt < HEADBUTT_COOLDOWN_SECONDS:
                time_left = int(HEADBUTT_COOLDOWN_SECONDS - time_since_last_headbutt)
                return {
                    "status": "error",
                    "message": f"Goats are still dizzy from the last headbutt. Try again in {time_left} seconds."
                }
                time_left = int(HEADBUTT_COOLDOWN_SECONDS - time_since_last_headbutt)
                return {
                    "status": "error",
                    "message": f"Goats are still dizzy from the last headbutt. Try again in {time_left} seconds."
                }
            
            # Process headbutt (successful)
            app_state.last_headbutt_time = current_time
        
        # Generate a fun headbutt message
        headbutt_message = f"🐐 HEADBUTT! The goats have been energized with {amount} sats!"
        
        # Send the message to all connected clients
        await send_messages_to_clients(headbutt_message)
        
        # Log the headbutt
        logger.info(f"Headbutt triggered with {amount} sats")
        
        return {
            "status": "success",
            "message": "Headbutt successful! The goats are energized!",
            "amount": amount
        }
    
    except Exception as e:
        logger.error(f"Error processing headbutt: {e}")
        raise HTTPException(status_code=500, detail="Error processing headbutt request")
@app.post("/messages/cyberherd_treats")
async def handle_cyberherd_treats(data: CyberHerdTreats):
    try:
        pubkey = data.pubkey
        amount = data.amount
        cyber_herd_list = await get_cyberherd_list()
        cyber_herd_dict = {item['pubkey']: item for item in cyber_herd_list}

        if pubkey in cyber_herd_dict:
            message, _ = await messaging.make_messages(config['NOS_SEC'], amount, 0, "cyber_herd_treats", cyber_herd_dict[pubkey])
            await send_messages_to_clients(message)
            return {"status": "success"}
        else:
            return {"status": "error", "message": "Invalid pubkey"}
    except Exception as e:
        logger.error(f"Error in /messages/cyberherd_treats route: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    
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

async def process_headbutting_attempts(data: List[CyberHerdData]) -> List[Dict[str, Any]]:
    """
    Process headbutting attempts when the herd is full.
    Only allows one headbutt attempt per cooldown period.
    """
    current_time = time.time()
    
    # Use app_state.lock to prevent concurrent headbutts
    async with app_state.lock:
        # Check cooldown
        if current_time - app_state.last_headbutt_time < HEADBUTT_COOLDOWN_SECONDS:
            remaining_cooldown = HEADBUTT_COOLDOWN_SECONDS - (current_time - app_state.last_headbutt_time)
            logger.info(f"Headbutt cooldown active. {remaining_cooldown:.1f}s remaining")
            return []
        
        results = []
        
        # Convert data to headbutt attempts and filter for valid zaps
        headbutt_attempts = []
        for item in data:
            # Only process items with zap receipts (kind 9735) that have amount > 0
            if 9735 in item.kinds and item.amount > 0:
                headbutt_attempts.append(item)
        
        if not headbutt_attempts:
            logger.info("No valid headbutt attempts found (need zap receipts with amount > 0)")
            return []
        
        # Sort attempts by amount (highest first) to give priority to bigger zappers
        headbutt_attempts.sort(key=lambda x: x.amount, reverse=True)
        
        # Process only the first (highest amount) attempt to prevent multiple messages
        if headbutt_attempts:
            attempt = headbutt_attempts[0]
            try:
                headbutt_result = await attempt_headbutt(attempt)
                if headbutt_result:
                    results.append(headbutt_result)
                    app_state.last_headbutt_time = current_time
                else:
                    # If headbutt failed, we still update the cooldown to prevent spam
                    app_state.last_headbutt_time = current_time
            except Exception as e:
                logger.error(f"Error processing headbutt attempt for {attempt.pubkey}: {e}")
        
        return results

async def attempt_headbutt(attacker: CyberHerdData) -> Optional[Dict[str, Any]]:
    """
    Attempt to headbutt the member with the lowest zap amount.
    Returns details of successful headbutt or None if failed.
    """
    try:
        # Use database transaction for atomic operations
        async with database.transaction():
            # Find the member with the lowest zap amount
            # Priority: Members with lowest amount (0 for repost-only, then lowest zaps)
            query = """
                SELECT pubkey, display_name, amount, lud16, nprofile 
                FROM cyber_herd 
                ORDER BY amount ASC, pubkey ASC 
                LIMIT 1
            """
            
            lowest_member = await database.fetch_one(query)
            
            if not lowest_member:
                logger.error("No members found to headbutt")
                return None
            
            # Check if attacker's zap amount is sufficient
            # Must be at least HEADBUTT_MIN_SATS AND exceed the lowest member's amount
            if lowest_member['amount'] == 0:
                # Repost-only member - need at least minimum zap amount
                required_amount = HEADBUTT_MIN_SATS
            else:
                # Member with zaps - need to exceed their amount AND meet minimum
                required_amount = max(HEADBUTT_MIN_SATS, lowest_member['amount'] + 1)
            
            if attacker.amount < required_amount:
                logger.info(f"Headbutt failed: {attacker.amount} sats not enough (need {required_amount} sats)")
                # Send failure notification using the messaging system
                await send_headbutt_failure_notification(attacker, required_amount)
                return None
            
            # Perform the headbutt atomically
            logger.info(f"Headbutt successful: {attacker.pubkey} ({attacker.amount} sats) replacing {lowest_member['pubkey']} ({lowest_member['amount']} sats)")
            
            # Remove the lowest member
            await database.execute(
                "DELETE FROM cyber_herd WHERE pubkey = :pubkey", 
                values={"pubkey": lowest_member['pubkey']}
            )
            
            # Add the new member
            await add_new_headbutt_member(attacker)
            
            headbutt_result = {
                "attacker": attacker.pubkey,
                "victim": lowest_member['pubkey'],
                "attacker_amount": attacker.amount,
                "victim_amount": lowest_member['amount'],
                "attacker_name": attacker.display_name or "Anon",
                "victim_name": lowest_member['display_name'] or "Anon",
                "attacker_nprofile": attacker.nprofile,
                "victim_nprofile": lowest_member['nprofile']
            }
        
        # Send notifications outside transaction (non-critical)
        try:
            await send_headbutt_success_notifications(attacker, lowest_member, headbutt_result)
        except Exception as e:
            logger.error(f"Failed to send headbutt notifications: {e}")
        
        # Update LNbits targets outside transaction (non-critical)
        try:
            await update_lnbits_targets_after_headbutt()
        except Exception as e:
            logger.error(f"Failed to update LNbits targets after headbutt: {e}")
        
        return headbutt_result
        
    except Exception as e:
        logger.error(f"Database transaction failed during headbutt: {e}")
        return None

async def add_new_headbutt_member(member: CyberHerdData):
    """Add a new member who successfully headbutted someone."""
    # Set default relays if not provided
    relays = member.relays or RELAYS[:2]
    
    # Ensure 'kinds' is a comma-separated string
    if isinstance(member.kinds, list):
        kinds_str = ','.join(map(str, member.kinds))
    else:
        kinds_str = str(member.kinds)
    
    # Calculate payouts for zap receipt
    kinds_int = parse_kinds(member.kinds)
    if 9735 in kinds_int:  # ZAP_RECEIPT
        payouts = calculate_payout(member.amount)
    else:
        payouts = 0.0
    
    insert_query = """
        INSERT INTO cyber_herd (
            pubkey, display_name, event_id, note, kinds, nprofile, lud16, 
            notified, payouts, amount, picture, relays
        ) VALUES (
            :pubkey, :display_name, :event_id, :note, :kinds, :nprofile, :lud16, 
            :notified, :payouts, :amount, :picture, :relays
        )
    """
    
    await database.execute(insert_query, values={
        "pubkey": member.pubkey,
        "display_name": member.display_name or "Anon",
        "event_id": member.event_id,
        "note": member.note,
        "kinds": kinds_str,
        "nprofile": member.nprofile,
        "lud16": member.lud16,
        "notified": None,
        "payouts": payouts,
        "amount": member.amount,
        "picture": member.picture,
        "relays": json.dumps(relays)
    })

async def send_headbutt_failure_notification(attacker: CyberHerdData, required_amount: int):
    """Send notification when headbutt attempt fails due to insufficient zaps."""
    try:
        # Create message data for headbutt failure
        message_data = {
            'attacker_name': attacker.display_name or 'Anon',
            'attacker_amount': attacker.amount,
            'required_amount': required_amount,
            'attacker_pubkey': attacker.pubkey,
            'event_id': attacker.event_id,
            'attacker_nprofile': attacker.nprofile
        }
        
        # Send via messaging system
        message_content, raw_output = await messaging.make_messages(
            config['NOS_SEC'],
            attacker.amount,
            0,
            "headbutt_failure",
            message_data,
            0
        )
        
        # Send to WebSocket clients
        await send_messages_to_clients(message_content)
        
        logger.info(f"Sent headbutt failure notification for {attacker.pubkey}")
    except Exception as e:
        logger.error(f"Failed to send headbutt failure notification: {e}")

async def send_headbutt_success_notifications(attacker: CyberHerdData, victim: dict, headbutt_result: dict):
    """Send notifications for successful headbutt."""
    try:
        # Create message data for headbutt success
        message_data = {
            'attacker_name': attacker.display_name or 'Anon',
            'attacker_amount': attacker.amount,
            'victim_name': victim['display_name'] or 'Anon',
            'victim_amount': victim['amount'],
            'attacker_pubkey': attacker.pubkey,
            'victim_pubkey': victim['pubkey'],
            'event_id': attacker.event_id,
            'attacker_nprofile': attacker.nprofile,
            'victim_nprofile': victim['nprofile']
        }
        
        # Send via messaging system
        message_content, raw_output = await messaging.make_messages(
            config['NOS_SEC'],
            attacker.amount,
            0,
            "headbutt_success",
            message_data,
            0
        )
        
        # Send to WebSocket clients
        await send_messages_to_clients(message_content)
        
        # Update the attacker's notified field
        if raw_output:
            await update_notified_field(attacker.pubkey, raw_output)
        
        logger.info(f"Sent headbutt success notifications for {attacker.pubkey} replacing {victim['pubkey']}")
    except Exception as e:
        logger.error(f"Failed to send headbutt success notifications: {e}")

async def send_headbutt_info_message():
    """Send headbutt info message when herd is full but no headbutt attempts made."""
    try:
        # Get the lowest member (potential victim)
        query = """
            SELECT pubkey, display_name, amount, lud16, nprofile 
            FROM cyber_herd 
            ORDER BY amount ASC, pubkey ASC 
            LIMIT 1
        """
        
        lowest_member = await database.fetch_one(query)
        
        if not lowest_member:
            logger.error("No members found for headbutt info")
            return
        
        # Get a recent cyberherd member's event_id to reply to
        # We'll use any member's event_id since they all represent cyberherd notes
        recent_member_query = """
            SELECT event_id
            FROM cyber_herd 
            ORDER BY ROWID DESC
            LIMIT 1
        """
        
        recent_member = await database.fetch_one(recent_member_query)
        
        if not recent_member or not recent_member['event_id']:
            logger.error("No recent cyberherd event_id found for headbutt info")
            return
        
        # Calculate required sats using same logic as headbutt
        if lowest_member['amount'] == 0:
            # Repost-only member - need at least minimum zap amount
            required_amount = HEADBUTT_MIN_SATS
        else:
            # Member with zaps - need to exceed their amount AND meet minimum
            required_amount = max(HEADBUTT_MIN_SATS, lowest_member['amount'] + 1)
        
        # Create context for the message
        victim_name = lowest_member['display_name'] or 'Anon'
        
        # Send headbutt info message via messaging system
        message_content, _ = await messaging.make_messages(
            config['NOS_SEC'],
            required_amount,
            0,
            "headbutt_info",
            {
                'required_sats': required_amount,
                'victim_name': victim_name,
                'victim_pubkey': lowest_member['pubkey'],
                'event_id': recent_member['event_id']  # Add event_id for reply
            }
        )
        
        await send_messages_to_clients(f"⚡ CyberHerd full! Send {required_amount} sats to headbutt {victim_name} out!")
        
        logger.info(f"Sent headbutt info message: {required_amount} sats to headbutt {victim_name}")
    except Exception as e:
        logger.error(f"Failed to send headbutt info message: {e}")

async def update_lnbits_targets_after_headbutt():
    """Update LNbits targets after a successful headbutt."""
    try:
        # Get all current members
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

        # Get initial targets and update
        initial_targets = await fetch_cyberherd_targets()
        updated_targets = await create_cyberherd_targets(
            new_targets_data=all_targets,
            initial_targets=initial_targets
        )
        
        if updated_targets:
            await update_cyberherd_targets(updated_targets)
            logger.info("LNbits targets updated successfully after headbutt.")
        else:
            logger.warning("No targets to update for LNbits after headbutt.")
    except Exception as e:
        logger.error(f"Failed to update LNbits targets after headbutt: {e}")
