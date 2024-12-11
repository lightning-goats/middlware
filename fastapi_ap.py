from typing import List, Optional, Dict
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException, Path, Query, Depends, Request, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel, validator
from urllib.parse import quote
from dotenv import load_dotenv
import messaging
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
    AsyncRetrying,
    wait_fixed,
)

# Configuration and Constants
MAX_HERD_SIZE = int(os.getenv('MAX_HERD_SIZE', 10))
PRICE = float(os.getenv('PRICE', 1.00))
LNBITS_URL = os.getenv('LNBITS_URL', 'http://127.0.0.1:3002')
OPENHAB_URL = os.getenv('OPENHAB_URL', 'http://10.8.0.6:8080')
HERD_WEBSOCKET = os.getenv('HERD_WEBSOCKET', "ws://127.0.0.1:3002/api/v1/ws/036ad4bb0dcb4b8c952230ab7b47ea52")
PREDEFINED_WALLET_ADDRESS = 'bolverker@strike.me' 
PREDEFINED_WALLET_ALIAS = 'Bolverker'             
PREDEFINED_WALLET_PERCENT_RESET = 100             
PREDEFINED_WALLET_PERCENT_DEFAULT = 80           

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
        self.balance = None
        self.trigger_amount = None
        self.lock = Lock()

    async def set_daily_trigger_amount(self):
        """Set the trigger amount for the day."""
        try:
            trigger_amount = await convert_to_sats(PRICE)
            async with self.lock:
                self.daily_trigger_amount = trigger_amount
                logger.info(f"Daily trigger amount set to: {trigger_amount}")
        except Exception as e:
            logger.error(f"Failed to set daily trigger amount: {e}")

app_state = AppState()

# Pydantic models
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
        # Add validation logic for lud16
        if '@' not in v:
            raise ValueError('Invalid lud16 format')
        return v

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

required_env_vars = ['OH_AUTH_1', 'HERD_KEY', 'SAT_KEY', 'NOS_SEC', 'CYBERHERD_KEY']
config = load_env_vars(required_env_vars)

# Define Retry Decorators

# Retry decorator for HTTP requests using httpx
http_retry = retry(
    reraise=True,  # Re-raise the last exception if all retries fail
    stop=stop_after_attempt(5),  # Stop after 5 attempts
    wait=wait_exponential(multiplier=1, min=4, max=10),  # Exponential backoff: 4s, 8s, 16s, etc.
    retry=retry_if_exception_type(httpx.RequestError)  # Retry on specific exceptions
)

# Retry decorator for WebSocket connections
websocket_retry = retry(
    reraise=True,
    stop=stop_after_attempt(None),  # Infinite retries
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

# Retry decorator for Database operations
db_retry = retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_fixed(2),  # Wait 2 seconds between retries
    retry=retry_if_exception_type((Exception,))  # Adjust exception types as needed
)

# WebSockets ###
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
                    self._retry_count = 0  # Reset retry count on successful connection
                    
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
                    # Continue listening even if processing fails
        except (ConnectionClosedError, ConnectionClosedOK) as e:
            self.logger.warning(f"WebSocket connection closed during listen: {e}")
            # Propagate to trigger reconnection
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
        """Wait for the WebSocket to be connected within the specified timeout."""
        try:
            await asyncio.wait_for(self.connected.wait(), timeout)
            return True
        except asyncio.TimeoutError:
            self.logger.warning("Timeout while waiting for WebSocket connection.")
            return False

    async def run(self):
        """Convenience method to start the connection management."""
        await self.connect()

# Initialize WebSocket Manager
websocket_manager = WebSocketManager(
    uri=HERD_WEBSOCKET,
    logger=logger,
    max_retries=5
)

# Database
database = Database('sqlite:///cyberherd.db')

@app.on_event("startup")
async def startup():
    global http_client
    http_client = httpx.AsyncClient(http2=True)
    
    # Set the daily trigger amount on startup
    await app_state.set_daily_trigger_amount()
    
    # Create and start the WebSocket manager
    websocket_task = asyncio.create_task(websocket_manager.connect())
    connected = await websocket_manager.wait_for_connection(timeout=30)
    if not connected:
        logger.warning("Initial WebSocket connection attempt timed out")
    
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
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    await database.execute('''
        CREATE TABLE IF NOT EXISTS cache (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            expires_at REAL NOT NULL
        )
    ''')

    # Start the cache cleanup task
    asyncio.create_task(cleanup_cache())
    
# Scheduled task to reset the daily trigger amount
@app.on_event("startup")
async def schedule_daily_reset():
    async def reset_trigger_amount():
        while True:
            now = datetime.utcnow()
            # Calculate the time until midnight UTC
            next_midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            sleep_seconds = (next_midnight - now).total_seconds()
            await asyncio.sleep(sleep_seconds)
            await app_state.set_daily_trigger_amount()

    asyncio.create_task(reset_trigger_amount())

@app.on_event("shutdown")
async def shutdown():
    await websocket_manager.disconnect()

# Cache Management
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

# Initialize the cache with the database instance
cache = DatabaseCache(database)

async def cleanup_cache():
    while True:
        await asyncio.sleep(1800)  # Run cleanup every 30 minutes
        try:
            current_time = time.time()
            query = "DELETE FROM cache WHERE expires_at < :current_time"
            await database.execute(query, values={"current_time": current_time})
        except Exception as e:
            logger.error(f"Error cleaning up cache: {e}")

# Database Functions
@db_retry
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

@db_retry
async def update_cyber_herd_list(new_data: List[dict], reset=False):
    try:
        if reset:
            await database.execute("DELETE FROM cyber_herd")
            return

        query = '''
            INSERT OR REPLACE INTO cyber_herd
            (pubkey, display_name, event_id, note, kinds, nprofile, lud16, notified, payouts)
            VALUES (:pubkey, :display_name, :event_id, :note, :kinds, :nprofile, :lud16, :notified, :payouts)
        '''
        for item in new_data:
            await database.execute(query, values={
                'pubkey': item['pubkey'],
                'display_name': item.get('display_name'),
                'event_id': item.get('event_id'),
                'note': item.get('note'),
                'kinds': json.dumps(item.get('kinds', [])),
                'nprofile': item.get('nprofile'),
                'lud16': item.get('lud16'),
                'notified': item.get('notified'),
                'payouts': item.get('payouts', 0.0)
            })
    except Exception as e:
        logger.error(f"Error updating cyber herd list: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@db_retry
async def update_message_in_db(new_message: str):
    try:
        await database.execute("INSERT INTO messages (content) VALUES (:content)", values={'content': new_message})
        await database.execute("DELETE FROM messages WHERE id NOT IN (SELECT id FROM messages ORDER BY timestamp DESC LIMIT 10)")
    except Exception as e:
        logger.error(f"Error updating messages in database: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@db_retry
async def retrieve_messages() -> List[str]:
    try:
        query = "SELECT content FROM messages ORDER BY timestamp DESC"
        rows = await database.fetch_all(query)
        return [row['content'] for row in rows]
    except Exception as e:
        logger.error(f"Error retrieving messages from database: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

# HTTP Client and External Service Interaction
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
            'percent': predefined_percent  # Use the passed allocation percentage
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

        total_percent_allocation = predefined_wallet['percent']  # Starts at predefined_percent
        targets_list = [predefined_wallet]

        if combined_wallets:
            total_payouts = sum(wallet['payouts'] for wallet in combined_wallets)
            if total_payouts == 0:
                total_payouts = 1  # Prevent division by zero

            # Allocate the remaining percentage (e.g., 90% or 100% depending on context)
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
    for item_dict in new_members:
        spots_remaining = MAX_HERD_SIZE - current_herd_size
        try:
            message_content, command_output = await messaging.make_messages(
                config['NOS_SEC'],
                0,
                difference,
                "cyber_herd",
                item_dict,
                spots_remaining
            )
            
            await update_message_in_db(message_content)

            # Parse the command output to extract the note_id
            command_output_json = json.loads(command_output)
            note_id = command_output_json.get("id")

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
            logger.exception(f"Error while notifying and updating for pubkey: {item_dict['pubkey']}")

@http_retry
async def get_balance(force_refresh=False):
    try:
        async with app_state.lock:
            if app_state.balance is not None and not force_refresh:
                return app_state.balance

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
    """Fetches the current price of 1 BTC in USD from OpenHAB."""
    try:
        response = await http_client.get(
            f'{OPENHAB_URL}/rest/items/BTC_Price_Output/state',
            auth=(config['OH_AUTH_1'], '')
        )
        response.raise_for_status()
        btc_price = float(response.text)  # Convert to float for calculations
        return btc_price
    except httpx.HTTPError as e:
        logger.error(f"HTTP error fetching BTC price: {e}")
        raise HTTPException(status_code=e.response.status_code if e.response else 500, detail="Failed to fetch BTC price")
    except Exception as e:
        logger.error(f"Error fetching BTC price: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@http_retry
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
        raise  # Tenacity will handle the retry
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
        raise  # Tenacity will handle the retry
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

# Helper Functions

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

# API Routes
@app.get("/balance")
async def get_balance_route(force_refresh: bool = False):
    balance_value = await get_balance(force_refresh)
    #todo: change to sats instead of millisats.
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
        query = "SELECT COUNT(*) as count FROM cyber_herd"
        result = await database.fetch_one(query)
        current_herd_size = result['count']

        if current_herd_size >= MAX_HERD_SIZE:
            logger.info(f"Herd full: {current_herd_size} members")
            return {"status": "herd full"}

        balance = float(await get_balance(True)) / 1000
        trigger = await get_trigger_amount_route()
        difference = round(trigger['trigger_amount'] - balance)

        initial_targets = await fetch_cyberherd_targets()
        existing_wallets = {item['wallet']: item for item in initial_targets}

        targets_to_create = []
        new_members = []

        for item in data:
            item_dict = item.dict()
            pubkey = item_dict['pubkey']

            check_query = "SELECT COUNT(*) as count FROM cyber_herd WHERE pubkey = :pubkey"
            result = await database.fetch_one(check_query, values={"pubkey": pubkey})

            if result['count'] == 0 and current_herd_size < MAX_HERD_SIZE:
                item_dict['notified'] = None
                item_dict['kinds'] = ','.join(map(str, item_dict['kinds']))
                new_members.append(item_dict)

                if item_dict['lud16'] not in existing_wallets:
                    targets_to_create.append({
                        'wallet': item_dict['lud16'],
                        'alias': item_dict['pubkey'],
                    })

                current_herd_size += 1

        if new_members:
            insert_query = """
            INSERT INTO cyber_herd (pubkey, display_name, event_id, note, kinds, nprofile, lud16, notified, payouts)
            VALUES (:pubkey, :display_name, :event_id, :note, :kinds, :nprofile, :lud16, :notified, :payouts)
            """
            await database.execute_many(insert_query, new_members)

        if targets_to_create:
            targets = await create_cyberherd_targets(targets_to_create, initial_targets)
            if targets:
                await update_cyberherd_targets(targets)

        background_tasks.add_task(notify_new_members, new_members, difference, current_herd_size)
        return {"status": "success", "new_members_added": len(new_members)}

    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Failed to update cyber herd: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@app.get("/get_cyber_herd")
async def get_cyber_herd():
    try:
        return await get_cyber_herd_list()
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error in /get_cyber_herd route: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@app.get("/reset_cyber_herd")
async def reset_cyber_herd():
    try:
        # Step 1: Reset the CyberHerd list in the database
        await update_cyber_herd_list([], reset=True)

        # Step 2: Delete existing CyberHerd targets via the API
        headers = {
            'accept': 'application/json',
            'X-API-KEY': config['CYBERHERD_KEY']
        }
        url = f"{LNBITS_URL}/splitpayments/api/v1/targets?api-key={config['CYBERHERD_KEY']}"

        response = await http_client.delete(url, headers=headers)
        response.raise_for_status()
        logger.info("Existing CyberHerd targets deleted successfully.")

        # Step 3: Create a new CyberHerd target with predefined wallet at 100% allocation
        predefined_wallet = {
            'wallet': PREDEFINED_WALLET_ADDRESS,      # Using the constant
            'alias': PREDEFINED_WALLET_ALIAS,        # Using the constant
            'percent': PREDEFINED_WALLET_PERCENT_RESET  # 100% allocation
        }

        # Prepare the payload for creating the new target
        new_targets = {"targets": [predefined_wallet]}

        # Send the PUT request to create the new target
        create_response = await http_client.put(
            f'{LNBITS_URL}/splitpayments/api/v1/targets',
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
        raise HTTPException(status_code=500, detail="Internal Server Error.")

@app.delete("/cyber_herd/delete/{lud16}")
async def delete_cyber_herd(lud16: str):
    try:
        logger.info(f"Attempting to delete record with lud16: {lud16}")
        query = "DELETE FROM cyber_herd WHERE lud16 = :lud16"
        result = await database.execute(query, values={'lud16': lud16})
        if result == 0:
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
    try:
        async with app_state.lock:
            if app_state.daily_trigger_amount is not None:
                return {"trigger_amount": app_state.daily_trigger_amount}
        raise HTTPException(status_code=500, detail="Daily trigger amount is not set.")
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error retrieving trigger amount: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

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
@app.get("/messages", response_model=List[Message])
async def get_messages_route():   
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
            message_data, _ = await messaging.make_messages(config['NOS_SEC'], amount, 0, "cyber_herd_treats", cyber_herd_dict[pubkey])
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
        message_data, _ = await messaging.make_messages(config['NOS_SEC'], 0, 0, "interface_info")
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

# Error Handling
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

# Payment Processing Function
@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(Exception)  # Customize as needed
)
async def process_payment_data(payment_data):
    try:
        payment = payment_data.get('payment', {})
        payment_amount = payment.get('amount', 0)

        wallet_fiat_rate = payment.get('extra', {}).get('wallet_fiat_rate')
        wallet_balance = payment_data.get('wallet_balance')

        async with app_state.lock:
            app_state.balance = wallet_balance
            app_state.trigger_amount = math.floor(wallet_fiat_rate * PRICE)
        
        # Process only positive payment amounts
        if payment_amount <= 0:
            logger.info("Payment amount is non-positive, skipping processing.")
            return

        # Skip if feeder override is enabled
        if not await is_feeder_override_enabled():
            if app_state.balance >= (app_state.trigger_amount):
                if await trigger_feeder():
                    status = await send_payment(app_state.balance)
                    if status['success']:
                        message, _ = await messaging.make_messages(
                            config['NOS_SEC'],
                            int(payment_amount / 1000), 0, "feeder_triggered"
                        )
                        await update_message_in_db(message)
            else:
                difference = round(app_state.trigger_amount - app_state.balance)
                if (payment_amount / 1000) >= 10:
                    message, _ = await messaging.make_messages(
                        config['NOS_SEC'], 
                        int(payment_amount / 1000), 
                        difference, 
                        "sats_received"
                    )
                    await update_message_in_db(message)
        else:
            logger.info("Feeder override is ON, skipping feeder logic.")
    except Exception as e:
        logger.error(f"Error processing payment data: {e}")
        raise  # Let Tenacity handle the retry

