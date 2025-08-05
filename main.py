"""
CyberHerd Payment System - Simplified LNURL-Only Implementation

IMPORTANT: As of August 2025, this system has been simplified to use ONLY simple LNURL payments 
for all CyberHerd distributions. The complex Nostr zap functionality has been removed to improve 
reliability and reduce failure rates.

Key Changes:
- enhanced_zap_lud16() now uses only make_simple_lnurl_payment()
- zap_predefined_wallet_directly() uses only simple LNURL payments
- Removed complex Nostr zap detection and fallback logic
- Eliminated HTTP 500 errors from complex callback URLs
- Improved payment success rates by using proven LNURL-only approach

This ensures more reliable CyberHerd distributions without the complexity and failure points 
of Nostr zap integration.
"""

from math import floor
import os
import json
import time
import math
import asyncio
import random
import logging
import httpx
import hashlib
import websockets
from typing import List, Optional, Dict, Set, Union, Tuple, Any
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
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

# Global HTTP client
http_client: httpx.AsyncClient = None

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
from utils.helpers import calculate_payout, parse_kinds, DEFAULT_RELAYS
from utils.database import (
    init_database,
    is_zap_event_processed,
    mark_zap_event_processing,
    mark_zap_event_completed,
    mark_zap_event_failed,
    cleanup_failed_zap_events,
    DatabaseCache,
    cleanup_cache,
    database
)
from utils.headbutt import EnhancedHeadbuttService
from utils.database_service import CyberherdDatabaseService
from utils.messaging_service import HeadbuttMessagingService

# Configuration and Constants
MAX_HERD_SIZE = 3
PREDEFINED_WALLET_PERCENT_RESET = 100
TRIGGER_AMOUNT_SATS = 850
HEADBUTT_MIN_SATS = 10

# Use centralized relay configuration from utils.helpers
RELAYS = DEFAULT_RELAYS

def load_env_vars(required_vars):
    load_dotenv()
    missing_vars = [var for var in required_vars if os.getenv(var) is None]
    if missing_vars:
        raise ValueError(f"Missing environment variables: {', '.join(missing_vars)}")
    return {var: os.getenv(var) for var in required_vars}

required_env_vars = ['OH_AUTH_1', 'HERD_KEY', 'SAT_KEY', 'NOS_SEC', 'HEX_KEY', 'CYBERHERD_KEY', 'LNBITS_URL', 'OPENHAB_URL', 'HERD_WEBSOCKET', 'PREDEFINED_WALLET_ADDRESS','PREDEFINED_WALLET_ALIAS']
optional_env_vars = []  # Removed USE_DIRECT_ZAP_PAYMENTS since we only use zaps now
config = load_env_vars(required_env_vars)

# Add optional environment variables with defaults
for var in optional_env_vars:
    config[var] = os.getenv(var, 'false').lower() == 'true'

notification_semaphore = asyncio.Semaphore(6)  # limit concurrent notifications
http_request_semaphore = asyncio.Semaphore(5)  # limit concurrent HTTP requests to LNBits
payment_processing_semaphore = asyncio.Semaphore(2)  # limit concurrent payment processing

# Logging Configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global http_client
    # Configure HTTP client with connection limits to prevent pool exhaustion
    limits = httpx.Limits(
        max_keepalive_connections=10,  # Limit persistent connections
        max_connections=20,            # Total connection limit
        keepalive_expiry=30.0         # Close idle connections after 30s
    )
    timeout = httpx.Timeout(
        connect=10.0,   # Connection timeout
        read=30.0,      # Read timeout
        write=10.0,     # Write timeout
        pool=5.0        # Pool acquisition timeout
    )
    http_client = httpx.AsyncClient(limits=limits, timeout=timeout)

    # Start WebSocket manager
    websocket_task = asyncio.create_task(websocket_manager.connect())
    connected = await websocket_manager.wait_for_connection(timeout=30)
    if not connected:
        logger.warning("Initial WebSocket connection attempt timed out")

    # Connect to database and create tables
    logger.info("🔧 Initializing database...")
    await init_database()
    
    # Run comprehensive database setup and verification
    try:
        logger.info("🔧 Running database setup and verification...")
        # Import and run the database setup functions directly
        from add_processed_events import create_missing_tables, verify_database_integrity
        
        # Create missing tables if needed
        tables_created = await create_missing_tables()
        if not tables_created:
            logger.error("❌ Failed to create required database tables")
            raise RuntimeError("Database table creation failed")
        
        # Verify integrity
        integrity_ok = await verify_database_integrity()
        if not integrity_ok:
            logger.error("❌ Database integrity verification failed")
            raise RuntimeError("Database integrity check failed")
            
        logger.info("✅ Database setup and verification completed successfully")
        
    except Exception as e:
        logger.error(f"❌ Database setup failed: {e}")
        # Continue with fallback verification

    # Ensure all required tables exist with proper migrations
    try:
        # Add status column if it doesn't exist
        await database.execute('ALTER TABLE processed_zap_events ADD COLUMN status TEXT DEFAULT "completed"')
        logger.info("Added status column to processed_zap_events table")
    except Exception as e:
        # Column likely already exists, which is fine
        logger.debug(f"Status column migration: {e}")
    
    try:
        # Add event_type column if it doesn't exist  
        await database.execute('ALTER TABLE processed_events ADD COLUMN event_type TEXT DEFAULT "unknown"')
        logger.info("Added event_type column to processed_events table")
    except Exception as e:
        # Column likely already exists, which is fine
        logger.debug(f"Event_type column migration: {e}")
    
    # Verify critical tables exist
    try:
        # More robust table verification - check that tables actually exist
        required_tables = ['cyber_herd', 'processed_events', 'processed_zap_events', 'cache']
        
        # Check if all required tables exist
        for table_name in required_tables:
            table_check_query = """
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name=:table_name
            """
            result = await database.fetch_one(table_check_query, values={'table_name': table_name})
            if not result:
                logger.error(f"❌ Table {table_name} does not exist")
                raise RuntimeError(f"Critical database table {table_name} is missing - run add_processed_events.py")
        
        # Verify tables are accessible by doing simple queries
        await database.fetch_one("SELECT COUNT(*) as count FROM cyber_herd LIMIT 1")
        await database.fetch_one("SELECT COUNT(*) as count FROM processed_events LIMIT 1") 
        await database.fetch_one("SELECT COUNT(*) as count FROM processed_zap_events LIMIT 1")
        await database.fetch_one("SELECT COUNT(*) as count FROM cache LIMIT 1")
        
        logger.info("✅ All database tables verified and accessible")
    except Exception as e:
        logger.error(f"❌ Database table verification failed: {e}")
        # Try to call the setup script automatically
        try:
            logger.info("🔧 Attempting to create missing tables...")
            from add_processed_events import create_missing_tables
            await create_missing_tables()
            logger.info("✅ Database tables created successfully")
        except Exception as setup_error:
            logger.error(f"❌ Failed to create database tables: {setup_error}")
            raise RuntimeError("Critical database tables are missing and could not be created automatically - run add_processed_events.py manually")

    try:
        # Initial balance fetch - only HTTP call needed, WebSocket will handle all updates
        logger.info("📊 Fetching initial balance from LNBits API (one-time startup only)")
        balance_value = await get_balance(force_refresh=True)
        app_state.balance = math.floor(balance_value / 1000)  # Convert from millisats to sats
        logger.info(f"✅ Initial balance: {app_state.balance} sats (subsequent updates via WebSocket)")
        
        # Initialize goat_sats_state cache
        await get_goat_sats_sum_today()
        
        # Clean up any failed zap events from previous runs
        await cleanup_failed_zap_events()
        
        # Run startup zap recovery in background to avoid blocking startup
        asyncio.create_task(recover_missed_zaps_on_startup())
        
    except Exception as e:
        logger.error(f"Failed to initialize states: {e}. Defaulting to 0.")
        app_state.balance = 0

    # Start background tasks
    asyncio.create_task(cleanup_cache())
    asyncio.create_task(schedule_daily_reset())
    asyncio.create_task(periodic_informational_messages())
    
    yield
    
    # Shutdown
    logger.info("Starting application shutdown...")
    
    # Close all WebSocket connections first
    if connected_clients:
        logger.info(f"Closing {len(connected_clients)} WebSocket connections...")
        async with clients_lock:
            for client in list(connected_clients):
                try:
                    await asyncio.wait_for(client.close(), timeout=2.0)
                except Exception as e:
                    logger.warning(f"Error closing WebSocket client: {e}")
            connected_clients.clear()
    
    # Disconnect WebSocket manager with timeout
    try:
        await asyncio.wait_for(websocket_manager.disconnect(), timeout=5.0)
        logger.info("WebSocket manager disconnected")
    except asyncio.TimeoutError:
        logger.warning("WebSocket manager disconnect timed out")
    except Exception as e:
        logger.warning(f"Error disconnecting WebSocket manager: {e}")
    
    # Close HTTP client with timeout
    if 'http_client' in globals() and http_client:
        try:
            await asyncio.wait_for(http_client.aclose(), timeout=5.0)
            logger.info("HTTP client closed")
        except asyncio.TimeoutError:
            logger.warning("HTTP client close timed out")
        except Exception as e:
            logger.warning(f"Error closing HTTP client: {e}")
    
    # Disconnect from database with timeout
    try:
        await asyncio.wait_for(database.disconnect(), timeout=5.0)
        logger.info("Database disconnected")
    except asyncio.TimeoutError:
        logger.warning("Database disconnect timed out")
    except Exception as e:
        logger.warning(f"Error disconnecting database: {e}")
    
    logger.info("Application shutdown complete")

async def recover_missed_zaps_on_startup():
    """
    Find today's CyberHerd notes and search for missed zaps to those notes.
    Uses non-blocking approach similar to herd3.py structure.
    """
    try:
        # Check if missed zap recovery is disabled via environment variable
        if os.getenv('DISABLE_MISSED_ZAP_RECOVERY', 'false').lower() == 'true':
            logger.info("ℹ️ Missed zap recovery is disabled via DISABLE_MISSED_ZAP_RECOVERY environment variable")
            return
            
        logger.info("🔍 Starting one-time missed zap recovery on startup...")
        
        # Calculate midnight today timestamp
        from datetime import datetime
        now = datetime.now()
        midnight = datetime.combine(now.date(), datetime.min.time())
        midnight_timestamp = int(midnight.timestamp())
        
        # Use a subset of relays for faster recovery (first 2 relays only)
        recovery_relays = RELAYS[:2]  # Use only first 2 relays for speed
        relays_str = " ".join(recovery_relays)
        
        # Use hex key from existing config
        our_hex_key = config['HEX_KEY']
        
        logger.info(f"📡 Using {len(recovery_relays)} relays for recovery: {recovery_relays}")
        
        # Step 1: One-time search for today's CyberHerd notes (non-streaming)
        logger.info("📝 One-time search for today's CyberHerd notes (non-streaming)...")
        cyberherd_notes_command = (
            f"/usr/local/bin/nak req -k 1 -t t=CyberHerd -a {our_hex_key} "
            f"--since {midnight_timestamp} --limit 10 {relays_str}"
        )
        
        logger.debug(f"Executing command: {cyberherd_notes_command}")
        
        # Execute command to get CyberHerd notes with timeout
        try:
            proc = await asyncio.create_subprocess_shell(
                cyberherd_notes_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Add timeout to prevent worker timeout (max 10 seconds for note search)
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), 
                timeout=10.0
            )
            
        except asyncio.TimeoutError:
            logger.warning("⚠️ CyberHerd notes search timed out after 10 seconds - skipping recovery")
            try:
                proc.kill()
                await proc.wait()
            except:
                pass
            return
        except Exception as e:
            logger.error(f"❌ Failed to execute CyberHerd notes search: {e}")
            return
        
        if proc.returncode != 0:
            error_output = stderr.decode().strip()
            logger.error(f"❌ Failed to fetch CyberHerd notes (return code {proc.returncode}): {error_output}")
            return
        
        # Log raw output for debugging
        raw_output = stdout.decode().strip()
        logger.debug(f"Raw nak output ({len(raw_output)} chars): {raw_output[:200]}...")
        
        # Parse CyberHerd notes and collect their IDs
        cyberherd_note_ids = []
        lines_processed = 0
        for line in raw_output.split('\n'):
            if not line.strip():
                continue
            
            lines_processed += 1
            try:
                note_data = json.loads(line)
                note_id = note_data.get('id')
                if note_id:
                    cyberherd_note_ids.append(note_id)
                    logger.debug(f"Found CyberHerd note: {note_id}")
            except json.JSONDecodeError as e:
                logger.debug(f"JSON decode error on line {lines_processed}: {line[:50]}... - {e}")
                continue
        
        logger.info(f"📊 Processed {lines_processed} lines from nak output")
        
        if not cyberherd_note_ids:
            logger.info("ℹ️ No CyberHerd notes found for today - no zaps to recover")
            return
        
        logger.info(f"📝 Found {len(cyberherd_note_ids)} CyberHerd notes from today")
        
        # Step 2: Search for zaps to each CyberHerd note (non-blocking)
        recovered_count = 0
        processed_count = 0
        max_notes_to_process = 10  # Limit notes to prevent long startup times
        
        for i, note_id in enumerate(cyberherd_note_ids[:max_notes_to_process]):
            if i >= max_notes_to_process:
                logger.info(f"⚠️ Reached maximum note processing limit ({max_notes_to_process}) - remaining notes will be processed on next startup")
                break
            
            logger.info(f"⚡ One-time search for zaps to CyberHerd note {note_id[:16]}... (non-streaming)")
            
            # One-time search for zaps to this specific note (non-streaming)
            zap_search_command = (
                f"/usr/local/bin/nak req -k 9735 -e {note_id} "
                f"--since {midnight_timestamp} --limit 20 {relays_str}"
            )
            
            try:
                # Execute zap search with shorter timeout per note
                proc = await asyncio.create_subprocess_shell(
                    zap_search_command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), 
                    timeout=8.0  # 8 seconds per note
                )
                
                if proc.returncode != 0:
                    error_output = stderr.decode().strip()
                    logger.warning(f"Failed to fetch zaps for note {note_id[:16]} (return code {proc.returncode}): {error_output}")
                    continue
                
                # Log raw zap output for debugging
                raw_zap_output = stdout.decode().strip()
                logger.debug(f"Raw zap output for note {note_id[:16]} ({len(raw_zap_output)} chars): {raw_zap_output[:100]}...")
                
                # Process zaps for this note
                note_recovered = 0
                note_processed = 0
                zap_lines_processed = 0
                
                for line in raw_zap_output.split('\n'):
                    if not line.strip():
                        continue
                    
                    zap_lines_processed += 1
                    try:
                        zap_data = json.loads(line)
                        zap_id = zap_data.get('id')
                        
                        if not zap_id:
                            continue
                        
                        # Check if this zap was already processed or is currently being processed
                        if await is_zap_event_processed(zap_id):
                            logger.debug(f"✅ Zap {zap_id[:16]}... already processed")
                            note_processed += 1
                            continue
                        
                        # Also check if it's currently being processed (within last 10 minutes)
                        query = "SELECT status, processed_at FROM processed_zap_events WHERE zap_event_id = :zap_event_id"
                        existing_record = await database.fetch_one(query, values={"zap_event_id": zap_id})
                        if existing_record:
                            if existing_record['status'] == 'processing':
                                # Check if it's recent processing (less than 10 minutes old)
                                if time.time() - existing_record['processed_at'] < 600:  # 10 minutes
                                    logger.debug(f"⏳ Zap {zap_id[:16]}... currently being processed (recent)")
                                    note_processed += 1
                                    continue
                                else:
                                    logger.info(f"♻️ Zap {zap_id[:16]}... stuck in processing, will retry")
                            elif existing_record['status'] == 'failed':
                                logger.info(f"🔄 Zap {zap_id[:16]}... previously failed, will retry")
                            # For other statuses, continue with processing
                        
                        # Process this missed zap
                        logger.info(f"🎯 Found unprocessed zap {zap_id[:16]}... for note {note_id[:16]}...")
                        
                        try:
                            await process_missed_zap_event(zap_data)
                            note_recovered += 1
                            
                            # Small delay to prevent overwhelming the system
                            await asyncio.sleep(0.05)
                            
                        except Exception as e:
                            logger.error(f"❌ Error processing missed zap {zap_id[:16]}...: {e}")
                            continue
                        
                    except json.JSONDecodeError as e:
                        logger.debug(f"JSON decode error on zap line {zap_lines_processed}: {line[:50]}... - {e}")
                        continue
                
                logger.info(f"📊 Note {note_id[:16]}: processed {zap_lines_processed} zap lines")
                recovered_count += note_recovered
                processed_count += note_processed
                
                if note_recovered > 0 or note_processed > 0:
                    logger.info(f"📝 Note {note_id[:16]}: {note_recovered} recovered, {note_processed} already processed")
                
            except asyncio.TimeoutError:
                logger.warning(f"⚠️ Zap search for note {note_id[:16]} timed out after 8 seconds - skipping")
                try:
                    proc.kill()
                    await proc.wait()
                except:
                    pass
                continue
            except Exception as e:
                logger.error(f"❌ Error searching zaps for note {note_id[:16]}: {e}")
                continue
        
        total_found = recovered_count + processed_count
        
        if total_found > 0:
            logger.info(f"✅ One-time zap recovery complete: {total_found} total found, {processed_count} already processed, {recovered_count} newly recovered")
        else:
            logger.info("ℹ️ One-time recovery found no zap events for today's CyberHerd notes")
            
    except Exception as e:
        logger.error(f"❌ Error in startup zap recovery: {e}", exc_info=True)

async def process_missed_zap_event(zap_data: dict):
    """
    Process a missed zap event found during startup recovery.
    Validates the zap and either adds to cyberherd (if for cyberherd note) 
    or processes as regular payment with appropriate messaging.
    """
    try:
        try:
            from bolt11 import decode as bolt11_decode
            from bolt11.exceptions import Bolt11Exception
        except ImportError:
            logger.error("bolt11 library not available - cannot process missed zaps")
            return
            
        from utils.cyberherd_module import MetadataFetcher, generate_nprofile, lookup_relay_list, Verifier
        
        current_event_id = zap_data.get('id')
        
        if not current_event_id:
            logger.error("Missed zap event missing 'id'")
            return
        
        logger.info(f"🔄 Processing missed zap: {current_event_id[:16]}...")
        
        # Atomic check - only process if we can claim it
        if not await mark_zap_event_processing(current_event_id, "startup_recovery", current_event_id, 0):
            logger.info(f"⏭️ Missed zap {current_event_id[:16]}... already being processed")
            return
            
        try:
            # Extract amount from BOLT11 tag
            def get_tag_value(tags, tag_name):
                for tag in tags:
                    if len(tag) > 1 and tag[0] == tag_name:
                        return tag[1]
                return None
            
            bolt11_invoice_str = get_tag_value(zap_data.get('tags', []), 'bolt11')
            if not bolt11_invoice_str:
                logger.error(f"Missed zap {current_event_id[:16]}... missing bolt11 tag")
                await mark_zap_event_failed(current_event_id, "Missing bolt11 tag")
                return
            
            # Decode amount from invoice
            try:
                decoded_invoice = bolt11_decode(bolt11_invoice_str)
                if decoded_invoice.amount_msat is not None:
                    zap_amount_msats = int(decoded_invoice.amount_msat)
                    zap_amount_sats = zap_amount_msats // 1000
                    if zap_amount_sats < 10:
                        logger.warning(f"Missed zap {current_event_id[:16]}... amount {zap_amount_sats} sats too small")
                        await mark_zap_event_completed(current_event_id)
                        return
                else:
                    logger.warning(f"Missed zap {current_event_id[:16]}... has no explicit amount")
                    zap_amount_sats = 0
            except Bolt11Exception as e:
                logger.error(f"Failed to decode BOLT11 for missed zap {current_event_id[:16]}...: {e}")
                await mark_zap_event_failed(current_event_id, f"BOLT11 decode error: {e}")
                return
            
            # Extract zapper info from description tag
            description_json_str = get_tag_value(zap_data.get('tags', []), 'description')
            if not description_json_str:
                logger.error(f"Missed zap {current_event_id[:16]}... missing description tag")
                await mark_zap_event_failed(current_event_id, "Missing description tag")
                return
            
            try:
                description_data = json.loads(description_json_str)
            except json.JSONDecodeError:
                logger.error(f"Failed to parse description JSON for missed zap {current_event_id[:16]}...")
                await mark_zap_event_failed(current_event_id, "Invalid description JSON")
                return
            
            zapper_pubkey = description_data.get('pubkey')
            zap_request_tags = description_data.get('tags', [])
            
            if not zapper_pubkey:
                logger.warning(f"Missed zap {current_event_id[:16]}... missing zapper pubkey")
                await mark_zap_event_failed(current_event_id, "Missing zapper pubkey")
                return
            
            # Validate zap is for us
            zap_recipient_pubkey = get_tag_value(zap_request_tags, 'p')
            if zap_recipient_pubkey != config['HEX_KEY']:
                logger.debug(f"Missed zap {current_event_id[:16]}... not for our key")
                await mark_zap_event_completed(current_event_id)
                return
            
            # Get the zapped event ID for context
            zapped_event_id = get_tag_value(zap_request_tags, 'e')
            if not zapped_event_id:
                logger.warning(f"Missed zap {current_event_id[:16]}... missing zapped event ID ('e' tag)")
                await mark_zap_event_failed(current_event_id, "Missing zapped event ID")
                return
            
            # Check if this is a zap to a cyberherd note OR if the zapper is an existing member
            is_cyberherd_zap = await check_cyberherd_tag(zapped_event_id, RELAYS)
            
            # Check if this is an existing CyberHerd member (for any-note zapping)
            is_existing_member = False
            check_query = "SELECT pubkey FROM cyber_herd WHERE pubkey = :pubkey"
            member_record = await database.fetch_one(check_query, values={"pubkey": zapper_pubkey})
            is_existing_member = member_record is not None
            
            # Process if: 1) CyberHerd note (for new or existing members) OR 2) Existing member zapping any note
            should_process_as_cyberherd = is_cyberherd_zap or is_existing_member
            
            zap_type = "CyberHerd note" if is_cyberherd_zap else "member increase (any note)" if is_existing_member else "Regular"
            member_status = "existing member" if is_existing_member else "new member" if is_cyberherd_zap else "non-member"
            
            logger.info(f"💎 Processing valid missed zap: {zap_amount_sats} sats from {zapper_pubkey[:16]}... ({zap_type} from {member_status})")
            
            if should_process_as_cyberherd:
                # Process as CyberHerd zap - get metadata and add to herd
                metadata_fetcher = MetadataFetcher()
                metadata = await metadata_fetcher.lookup_metadata(zapper_pubkey, RELAYS)
                
                if not metadata:
                    logger.warning(f"No metadata for zapper {zapper_pubkey[:16]}... in missed cyberherd zap")
                    await mark_zap_event_failed(current_event_id, "No zapper metadata")
                    return
                
                lud16 = metadata.get('lud16')
                display_name = metadata.get('display_name', 'Anon')
                picture = metadata.get('picture', '')
                
                if not lud16:
                    logger.warning(f"Missing lud16 for zapper {display_name} in missed cyberherd zap")
                    await mark_zap_event_failed(current_event_id, "Missing zapper lud16")
                    return
                
                # Generate nprofile
                nprofile = await generate_nprofile(zapper_pubkey)
                
                # Create CyberHerdData object and process via existing pipeline
                cyberherd_data = CyberHerdData(
                    display_name=display_name,
                    event_id=zapped_event_id,
                    note=current_event_id,
                    kinds=[9735],
                    pubkey=zapper_pubkey,
                    nprofile=nprofile or "",
                    lud16=lud16,
                    amount=zap_amount_sats,
                    picture=picture,
                    relays=RELAYS[:2]
                )
                
                logger.info(f"🎯 Processing missed CyberHerd zap via pipeline: {zap_amount_sats} sats from {display_name}")
                
                # Before processing through pipeline, check if this user is already in the cyberherd
                # During recovery, we should only process zaps from new users, not updates to existing users
                existing_member_query = "SELECT amount FROM cyber_herd WHERE pubkey = :pubkey"
                existing_member = await database.fetch_one(existing_member_query, values={"pubkey": zapper_pubkey})
                
                if existing_member:
                    logger.info(f"⏭️ Skipping recovery for existing member {display_name} (already has {existing_member['amount']} sats)")
                    await mark_zap_event_completed(current_event_id)
                    return
                
                # Process through existing cyber_herd logic (skip duplicate check since recovery already claimed it)
                await process_single_cyberherd_item(cyberherd_data, skip_duplicate_check=True)
                
            else:
                # Process as regular payment - update goat sats and generate message
                logger.info(f"💰 Processing missed zap as regular payment: {zap_amount_sats} sats")
                
                # Update goat sats (same as regular payment processing)
                if zap_amount_sats > 0:
                    await update_goat_sats(zap_amount_sats)
                
                # Update balance
                async with app_state.lock:
                    app_state.balance += zap_amount_sats
                    app_state.last_balance_update = time.time()
                
                # No need for HTTP balance sync - WebSocket provides accurate updates
                
                # Generate regular payment message
                if zap_amount_sats >= 10:
                    difference = TRIGGER_AMOUNT_SATS - app_state.balance
                    message, _ = await messaging.make_messages(
                        config['NOS_SEC'], 
                        zap_amount_sats, 
                        difference, 
                        "sats_received",
                        relays=RELAYS
                    )
                    await messaging.send_to_websocket_clients(message)
                    logger.info(f"📢 Sent regular payment message for {zap_amount_sats} sats")
                
                # Check if this regular payment triggers the feeder
                if zap_amount_sats > 0 and not await is_feeder_override_enabled():
                    if app_state.balance >= TRIGGER_AMOUNT_SATS:
                        if await trigger_feeder():
                            logger.info("🎯 Missed zap triggered feeder!")
                            
                            payment_amount = app_state.balance
                            
                            # Use direct zap payments 
                            payment_result = await pay_cyberherd_members_with_splits(payment_amount)
                            
                            if payment_result['success']:
                                logger.info(f"✅ CyberHerd payment successful from missed zap trigger")
                                
                                # Reset balance after successful payment
                                async with app_state.lock:
                                    app_state.balance = 0
                                    app_state.last_balance_update = time.time()
                                
                                # Send feeder triggered message
                                feeder_msg, _ = await messaging.make_messages(
                                    config['NOS_SEC'], 
                                    zap_amount_sats, 
                                    0, 
                                    "feeder_triggered",
                                    relays=RELAYS
                                )
                                await messaging.send_to_websocket_clients(feeder_msg)
                            else:
                                logger.error(f"❌ CyberHerd payment failed from missed zap trigger")
            
            # Mark as completed
            await mark_zap_event_completed(current_event_id)
            logger.info(f"✅ Successfully processed missed zap {current_event_id[:16]}...")
            
        except Exception as e:
            logger.error(f"❌ Error processing missed zap {current_event_id[:16]}...: {e}")
            await mark_zap_event_failed(current_event_id, str(e))
            
    except Exception as e:
        logger.error(f"❌ Critical error in process_missed_zap_event: {e}", exc_info=True)

# FastAPI app setup
app = FastAPI(lifespan=lifespan)

# Add middleware to log all requests including WebSocket upgrade attempts
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    
    # Enhanced logging for cyber_herd endpoint calls
    if request.url.path == "/cyber_herd":
        client_host = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "unknown")
        content_type = request.headers.get("content-type", "unknown")
        logger.warning(f"🚨 CYBER_HERD ENDPOINT CALLED: {request.method} from {client_host}, User-Agent: {user_agent}, Content-Type: {content_type}")
        
        # Log all headers for debugging
        for header_name, header_value in request.headers.items():
            logger.warning(f"   Header: {header_name}: {header_value}")
    
    response = await call_next(request)
    process_time = time.time() - start_time
    logger.info(f"{request.method} {request.url.path} - {response.status_code} - {process_time:.3f}s")
    return response

# Globals and State Management
class AppState:
    def __init__(self):
        self.balance: int = 0
        self.lock = Lock()
        self.cyberherd_lock = Lock()

app_state = AppState()

# Initialize HeadbuttService components
cyberherd_db_service = CyberherdDatabaseService(database)
headbutt_messaging_service = HeadbuttMessagingService(
    private_key=config.get('NOS_SEC', ''),
    websocket_clients=None  # Will be set to connected_clients after it's defined
)
headbutt_service = EnhancedHeadbuttService(
    database_service=cyberherd_db_service,
    messaging_service=headbutt_messaging_service,
    max_herd_size=MAX_HERD_SIZE,
    headbutt_min_sats=HEADBUTT_MIN_SATS,
    config=config,
    send_messages_to_clients_func=None,  # Will be set after function is defined
    make_messages_func=None  # Will be set after messaging is imported
)

# Track connected WebSocket clients
connected_clients: Set[WebSocket] = set()
clients_lock = Lock() # FIX: Add a lock for managing the connected_clients set

# Initialize messaging module with WebSocket clients
messaging.set_websocket_clients(connected_clients, clients_lock)

# Set HeadbuttService function references now that they're available
headbutt_messaging_service.websocket_clients = connected_clients
# Note: make_messages functions will be set later

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
    @classmethod
    def validate_lud16(cls, v):
        if '@' not in v:
            raise ValueError('Invalid lud16 format')
        return v

class CyberHerdTreats(BaseModel):
    lud16: str  # Lightning address (LUD16)
    amount: int

    @validator('lud16')
    @classmethod
    def validate_lud16(cls, v):
        if '@' not in v:
            raise ValueError('Invalid lud16 format')
        return v

class SetGoatSatsData(BaseModel):
    new_amount: int

class PaymentRequest(BaseModel):
    balance: int

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

http_retry = retry(
    reraise=True,
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_exception_type(httpx.RequestError)
)

# Rate-limited HTTP retry decorator for LNBits requests
def lnbits_http_retry(func):
    """Decorator that combines rate limiting with retry logic for LNBits API calls"""
    @http_retry
    async def wrapper(*args, **kwargs):
        async with http_request_semaphore:  # Rate limit concurrent requests
            # Add small delay to prevent request storms
            await asyncio.sleep(0.1)
            return await func(*args, **kwargs)
    return wrapper

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
        self.processed_payments = set()  # Track processed payment hashes
        self.payment_lock = Lock()  # Lock for payment processing

    async def connect(self):
        async with self.lock:
            while self.should_run:
                try:
                    if self.websocket and not self.websocket.closed:
                        await self.websocket.close()
                    
                    self.websocket = await websockets.connect(
                        self.uri,
                        ping_interval=20,  # More frequent pings
                        ping_timeout=15,   # Longer timeout
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
                        # Remove max retry limit for continuous reconnection
                        backoff = min(60, (2 ** min(self._retry_count, 6)))  # Cap at 64s max
                        self.logger.info(f"Attempting reconnection in {backoff} seconds (Attempt {self._retry_count + 1})...")
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
                    
                    # Check for payment hash to prevent duplicate processing
                    payment_hash = payment_data.get('payment', {}).get('payment_hash')
                    if payment_hash:
                        async with self.payment_lock:
                            if payment_hash in self.processed_payments:
                                self.logger.debug(f"Skipping duplicate payment: {payment_hash}")
                                continue
                            # Atomic add to prevent race conditions
                            self.processed_payments.add(payment_hash)
                            # Limit size of processed payments set
                            if len(self.processed_payments) > 1000:
                                # Remove oldest 100 entries
                                oldest_entries = list(self.processed_payments)[:100]
                                for entry in oldest_entries:
                                    self.processed_payments.discard(entry)
                    
                    # Rate limit payment processing to prevent overwhelming LNBits
                    async with payment_processing_semaphore:
                        await process_payment_data(payment_data)
                except json.JSONDecodeError as e:
                    self.logger.error(f"Failed to decode WebSocket message: {e}")
                except Exception as e:
                    self.logger.error(f"Error processing message: {e}")
                    # Continue processing other messages even if one fails
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
    max_retries=None  # Unlimited retries for continuous reconnection
)

# Use the database instance from utils.database for consistency
# (database object is imported from utils.database above)

async def schedule_daily_reset():
    while True:
        now = datetime.utcnow()
        next_midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        sleep_seconds = (next_midnight - now).total_seconds()
        await asyncio.sleep(sleep_seconds)

        try:
            # Reset CyberHerd
            result = await reset_cyber_herd()
            logger.info(f"Daily CyberHerd reset completed: {result}")
            
            # Reset payment metrics
            await payment_metrics.reset_metrics()
            logger.info("Daily payment metrics reset completed")
            
            # Send notification about daily reset
            reset_message, _ = await messaging.make_messages(
                config['NOS_SEC'], 0, 0, "daily_reset", relays=RELAYS
            )
            await messaging.send_to_websocket_clients(json.dumps({
                "type": "system_status",
                "message": reset_message,
                "reset_type": "daily_reset",
                "timestamp": datetime.now().isoformat()
            }))
            
            logger.info("✅ Daily system reset completed successfully")
        except Exception as e:
            logger.error(f"Daily reset failed: {e}")

cache = DatabaseCache(database)

# Initialize messaging with WebSocket clients - this will be done after connected_clients is defined
# Set HeadbuttService messaging function references now that they're defined
headbutt_service.make_messages = messaging.make_messages


async def periodic_informational_messages():
    """Send weather information and interface info via WebSockets periodically."""
    while True:
        await asyncio.sleep(60)
        
        # Only send messages if there are connected clients
        async with clients_lock:
            if not connected_clients:
                continue  # Skip this cycle if no clients are connected
        
        if random.random() < 0.3:  # 30% chance of sending a message
            # Determine message type based on probability
            message_choice = random.random()
            
            if message_choice < 0.5:  # 50% chance - weather information
                try:
                    # Get weather data from the weather service
                    weather_response = await http_client.get('http://192.168.1.161:5000/get_received_data')
                    weather_response.raise_for_status()
                    weather_data = weather_response.json()
                    
                    if weather_data:
                        # Handle both formats: array of weather objects or single weather object
                        latest_weather = weather_data if isinstance(weather_data, dict) else (weather_data[-1] if weather_data else {})
                        
                        # Extract outdoor weather information - try both formats
                        temp_f = (latest_weather.get('AmbientWeatherWS2902A_WeatherDataWs2902a_Temperature') or 
                                 latest_weather.get('tempf', 0))
                        humidity = (latest_weather.get('AmbientWeatherWS2902A_WeatherDataWs2902a_RelativeHumidity') or 
                                   latest_weather.get('humidity', 0))
                        wind_speed = (latest_weather.get('AmbientWeatherWS2902A_WindSpeed') or 
                                     latest_weather.get('windspeedmph', 0))
                        wind_gust = (latest_weather.get('AmbientWeatherWS2902A_WindGust') or 
                                    latest_weather.get('windgustmph', 0))
                        rainfall_today = (latest_weather.get('AmbientWeatherWS2902A_RainFallDay') or 
                                         latest_weather.get('dailyrainin', 0))
                        uv_index = (latest_weather.get('AmbientWeatherWS2902A_UVIndex') or 
                                   latest_weather.get('uv', 0))
                        solar_radiation = (latest_weather.get('AmbientWeatherWS2902A_SolarRadiation') or 
                                          latest_weather.get('solarradiation', 0))
                        wind_direction = latest_weather.get('AmbientWeatherWS2902A_WindDirectionCardinal', '')
                        
                        # Prepare data for centralized formatting
                        weather_data_formatted = {
                            'temperature_f': int(temp_f) if temp_f else 0,
                            'humidity': int(humidity) if humidity else 0,
                            'wind_speed': int(wind_speed) if wind_speed else 0,
                            'wind_direction': wind_direction,
                            'uv_index': int(uv_index) if uv_index else 0
                        }
                        
                        # Use centralized messaging for weather status
                        message, _ = await messaging.make_messages(
                            config['NOS_SEC'], 0, 0, 
                            "weather_status", 
                            cyber_herd_item=weather_data_formatted,
                            relays=RELAYS
                        )
                        
                        await messaging.send_to_websocket_clients(message)
                        logger.debug(f"🌤️ Sent weather status: {temp_f}°F, {humidity}% humidity, {wind_speed} mph wind")
                        
                    else:
                        # No weather data available, fall back to interface info
                        message, _ = await messaging.make_messages(config['NOS_SEC'], 0, 0, "interface_info", relays=RELAYS)
                        await messaging.send_to_websocket_clients(message)
                        
                except Exception as e:
                    logger.error(f"Error getting weather data: {e}")
                    # Fall back to regular interface info
                    message, _ = await messaging.make_messages(config['NOS_SEC'], 0, 0, "interface_info", relays=RELAYS)
                    await messaging.send_to_websocket_clients(message)
                    
            else:  # 50% chance - regular interface info
                message, _ = await messaging.make_messages(config['NOS_SEC'], 0, 0, "interface_info", relays=RELAYS)
                await messaging.send_to_websocket_clients(message)

# LNbits splits functionality removed - using direct zap payments only

@http_retry
# LNbits splits functionality removed - using direct zap payments only

@lnbits_http_retry
async def get_balance(force_refresh=False):
    """
    HTTP balance fetch - used only for startup initialization and diagnostic endpoints.
    Real-time balance updates are handled via WebSocket wallet_balance field to prevent
    HTTP connection issues that can cause LNBits to freeze.
    """
    try:
        if http_client is None:
            raise HTTPException(status_code=500, detail="HTTP client not initialized")
            
        response = await http_client.get(
            f'{config["LNBITS_URL"]}/api/v1/wallet',
            headers={'X-Api-Key': config['HERD_KEY']}
        )
        response.raise_for_status()
        balance_data = response.json()
        balance = balance_data['balance']
        async with app_state.lock:
            app_state.balance = math.floor(balance / 1000)
            app_state.last_balance_update = time.time()
        return balance
    except httpx.HTTPError as e:
        logger.error(f"HTTP error retrieving balance: {e}")
        # Try to use cached balance if available
        if hasattr(app_state, 'balance') and app_state.balance is not None:
            cached_balance_msat = app_state.balance * 1000
            logger.warning(f"Using cached balance: {app_state.balance} sats ({cached_balance_msat} millisats) (external service unavailable)")
            return cached_balance_msat
        
        if hasattr(e, 'response') and e.response:
            status_code = e.response.status_code
        else:
            status_code = 500
        raise HTTPException(
            status_code=status_code,
            detail="Failed to retrieve balance"
        )
    except Exception as e:
        logger.error(f"Error retrieving balance: {e}")
        # Try to use cached balance if available
        if hasattr(app_state, 'balance') and app_state.balance is not None:
            cached_balance_msat = app_state.balance * 1000
            logger.warning(f"Using cached balance: {app_state.balance} sats ({cached_balance_msat} millisats) (error fallback)")
            return cached_balance_msat
        
        raise HTTPException(status_code=500, detail="Internal Server Error")

@http_retry
async def get_lnbits_fee_settings():
    """
    Get current LNbits fee and reserve settings from the admin API.
    
    Returns:
        dict: Fee settings including reserve percentages and service fees
    """
    try:
        if http_client is None:
            logger.warning("HTTP client not initialized, using fallback fee settings")
            return None
            
        # Try to get admin settings (requires admin key)
        response = await http_client.get(
            f'{config["LNBITS_URL"]}/admin/api/v1/settings',
            headers={'X-Api-Key': config['HERD_KEY']}
        )
        response.raise_for_status()
        settings_data = response.json()
        
        # Extract relevant fee settings
        fee_settings = {
            'reserve_fee_min': settings_data.get('lnbits_reserve_fee_min', 2000),  # msats
            'reserve_fee_percent': settings_data.get('lnbits_reserve_fee_percent', 1.0),  # percent
            'service_fee': settings_data.get('lnbits_service_fee', 0),  # percent
            'service_fee_max': settings_data.get('lnbits_service_fee_max', 0),  # sats
            'service_fee_wallet': settings_data.get('lnbits_service_fee_wallet'),
            'service_fee_ignore_internal': settings_data.get('lnbits_service_fee_ignore_internal', True)
        }
        
        logger.debug(f"Retrieved LNbits fee settings: {fee_settings}")
        return fee_settings
        
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 403:
            logger.warning("Admin API access denied - using fallback fee calculation")
        else:
            logger.warning(f"Failed to get LNbits settings (HTTP {e.response.status_code}) - using fallback")
        return None
    except Exception as e:
        logger.warning(f"Error getting LNbits fee settings: {e} - using fallback")
        return None

@http_retry
async def get_fee_reserve_for_amount(amount_msat: int):
    """
    Get fee reserve calculation from LNbits for a specific amount.
    Uses LNbits' built-in fee calculation API.
    
    Args:
        amount_msat: Amount in millisats
        
    Returns:
        int: Total fee reserve in millisats, or None if API unavailable
    """
    try:
        if http_client is None:
            return None
            
        # Create a dummy invoice to get fee calculation
        # First create an invoice for the amount
        invoice_response = await http_client.post(
            f'{config["LNBITS_URL"]}/api/v1/payments',
            headers={'X-Api-Key': config['CYBERHERD_KEY']},
            json={
                'out': False,
                'amount': amount_msat // 1000,  # Convert to sats
                'unit': 'sat',
                'memo': 'Fee calculation probe'
            }
        )
        invoice_response.raise_for_status()
        invoice_data = invoice_response.json()
        bolt11_invoice = invoice_data.get('bolt11')
        
        if not bolt11_invoice:
            return None
            
        # Now get fee reserve for this invoice
        fee_response = await http_client.get(
            f'{config["LNBITS_URL"]}/api/v1/payments/fee-reserve',
            headers={'X-Api-Key': config['HERD_KEY']},
            params={'invoice': bolt11_invoice}
        )
        fee_response.raise_for_status()
        fee_data = fee_response.json()
        
        total_fee_reserve = fee_data.get('fee_reserve', 0)  # in msats
        
        logger.debug(f"LNbits fee reserve for {amount_msat} msat: {total_fee_reserve} msat")
        return total_fee_reserve
        
    except Exception as e:
        logger.debug(f"Could not get LNbits fee reserve calculation: {e}")
        return None

async def calculate_available_balance_with_reserves(total_balance_msat: int) -> int:
    """
    Calculate available balance accounting for LNbits reserves and fees.
    Uses dynamic LNbits settings when available, falls back to conservative estimates.
    
    Args:
        total_balance_msat: Total wallet balance in millisats
    
    Returns:
        Available balance in millisats that can be safely spent
    """
    try:
        # Try to get current LNbits fee settings
        fee_settings = await get_lnbits_fee_settings()
        
        if fee_settings:
            # Use dynamic settings from LNbits
            reserve_percent = fee_settings['reserve_fee_percent'] / 100.0  # Convert to decimal
            reserve_min_msat = fee_settings['reserve_fee_min']
            
            # Calculate reserve fee based on LNbits settings
            reserve_msat = max(
                int(total_balance_msat * reserve_percent),
                reserve_min_msat
            )
            
            # Get service fee info
            service_fee_percent = fee_settings['service_fee'] / 100.0
            service_fee_max_msat = fee_settings['service_fee_max'] * 1000  # Convert sats to msat
            
            # Calculate estimated service fee for a typical payment
            estimated_payment_msat = total_balance_msat // 2  # Assume half balance payment
            service_fee_msat = int(estimated_payment_msat * service_fee_percent)
            if service_fee_max_msat > 0:
                service_fee_msat = min(service_fee_msat, service_fee_max_msat)
            
            # Total fees and reserves
            total_fees_msat = reserve_msat + service_fee_msat
            available_msat = max(0, total_balance_msat - total_fees_msat)
            
            logger.debug(f"💰 Dynamic balance calculation: Total={total_balance_msat/1000:.0f} sats, "
                        f"Reserve={reserve_msat/1000:.1f} sats ({reserve_percent*100:.1f}%), "
                        f"Service fee≈{service_fee_msat/1000:.1f} sats ({service_fee_percent*100:.1f}%), "
                        f"Available={available_msat/1000:.0f} sats")
            
            return available_msat
            
        else:
            # Fallback to conservative estimates if API unavailable
            logger.debug("Using fallback fee calculation (LNbits API unavailable)")
            
            # Conservative fallback: 1% reserve + 10 sats routing buffer
            reserve_msat = int(total_balance_msat * 0.01)  # 1% reserve
            routing_buffer_msat = 10000  # 10 sats buffer
            
            available_msat = max(0, total_balance_msat - reserve_msat - routing_buffer_msat)
            
            logger.debug(f"💰 Fallback balance calculation: Total={total_balance_msat/1000:.0f} sats, "
                        f"Reserve={reserve_msat/1000:.1f} sats (1%), "
                        f"Routing buffer=10 sats, "
                        f"Available={available_msat/1000:.0f} sats")
            
            return available_msat
            
    except Exception as e:
        logger.error(f"Error in dynamic balance calculation: {e}")
        # Ultra-conservative fallback
        available_msat = max(0, int(total_balance_msat * 0.9))  # Keep 10% as buffer
        logger.debug(f"💰 Emergency fallback: {available_msat/1000:.0f} sats (90% of total)")
        return available_msat

async def calculate_max_payment_amount(total_amount_sats: int, num_payments: int = 1) -> int:
    """
    Calculate the maximum amount we can distribute given the total trigger amount,
    accounting for multiple payments and their individual fees using dynamic LNbits settings.
    
    Args:
        total_amount_sats: Total amount to distribute in sats
        num_payments: Number of separate payments that will be made
    
    Returns:
        Maximum distributable amount in sats
    """
    total_amount_msat = total_amount_sats * 1000
    
    try:        
        # Try to get precise fee calculation from LNbits API first
        total_fee_reserve_msat = 0
        
        # Method 1: Try using the fee-reserve API for accurate calculation
        api_fee_reserve = await get_fee_reserve_for_amount(total_amount_msat)
        
        if api_fee_reserve:
            # Scale the fee reserve for multiple payments
            total_fee_reserve_msat = api_fee_reserve * num_payments
            logger.debug(f"📊 API-based fee calculation: {total_fee_reserve_msat/1000:.1f} sats total fees for {num_payments} payments")
            
        else:
            # Method 2: Try to get dynamic settings from admin API
            fee_settings = await get_lnbits_fee_settings()
            
            if fee_settings:
                # Use dynamic LNbits settings
                service_fee_percent = fee_settings['service_fee'] / 100.0
                service_fee_max_msat = fee_settings['service_fee_max'] * 1000  # Convert sats to msat
                reserve_percent = fee_settings['reserve_fee_percent'] / 100.0
                reserve_min_msat = fee_settings['reserve_fee_min']
                
                # Calculate fees for each payment
                estimated_payment_msat = total_amount_msat // max(1, num_payments)
                
                for i in range(num_payments):
                    # Service fee per payment
                    service_fee_msat = int(estimated_payment_msat * service_fee_percent)
                    if service_fee_max_msat > 0:
                        service_fee_msat = min(service_fee_msat, service_fee_max_msat)
                    
                    # Reserve fee per payment
                    reserve_fee_msat = max(
                        int(estimated_payment_msat * reserve_percent),
                        reserve_min_msat
                    )
                    
                    total_fee_reserve_msat += service_fee_msat + reserve_fee_msat
                
                logger.debug(f"📊 Settings-based calculation: {total_fee_reserve_msat/1000:.1f} sats total fees")
                
            else:
                # Method 3: Conservative fallback
                # Based on your test: 29 sats fee for 850 sats ≈ 3.4% fee rate
                # But we need extra buffer for failed payments that increase final payment size
                estimated_fee_rate = 0.05  # 5% to account for payment failures and consolidation
                total_fee_reserve_msat = int(total_amount_msat * estimated_fee_rate * num_payments)
                logger.debug(f"📊 Conservative fallback: {total_fee_reserve_msat/1000:.1f} sats total fees (5% × {num_payments})")
        
        # Add extra buffer for payment failure scenarios
        # When CyberHerd payments fail, the predefined wallet gets a larger payment
        # This larger payment has higher fees, so we need extra reserves
        failure_buffer_msat = int(total_amount_msat * 0.02)  # Additional 2% buffer
        total_fee_reserve_msat += failure_buffer_msat
        
        # Calculate distributable amount
        max_distributable_msat = total_amount_msat - total_fee_reserve_msat
        max_distributable_sats = max(0, max_distributable_msat // 1000)
        
        efficiency_percent = (max_distributable_sats / total_amount_sats * 100) if total_amount_sats > 0 else 0
        
        logger.debug(f"📊 Final calculation: {max_distributable_sats} sats distributable "
                    f"({efficiency_percent:.1f}% efficiency, {total_fee_reserve_msat/1000:.1f} sats fees + buffer)")
        
        return max_distributable_sats
        
    except Exception as e:
        logger.error(f"Error in dynamic payment calculation: {e}")
        # Ultra-conservative fallback: Use actual fee data from your logs
        # Your logs showed 29 sats fee for 850 sats, so ~3.4% fee rate
        fallback_fee_rate = 0.07  # 7% to be extra safe and account for failures
        fallback_fees = int(total_amount_sats * fallback_fee_rate * num_payments)
        fallback_amount = max(0, total_amount_sats - fallback_fees)
        logger.debug(f"📊 Emergency fallback: {fallback_amount} sats (reserved {fallback_fees} sats)")
        return fallback_amount

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
        from math import floor
        
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

async def update_split_targets_from_herd():
    """
    Update LNbits split payment targets based on current CyberHerd members' payouts.
    This should be called whenever payouts change for any member.
    """
    try:
        # Get all current herd members with their payouts
        query = "SELECT lud16, display_name, payouts FROM cyber_herd WHERE lud16 IS NOT NULL AND lud16 != ''"
        herd_members = await database.fetch_all(query)
        
        if not herd_members:
            logger.info("No CyberHerd members with Lightning addresses found")
            return
        
        # Convert herd members to targets format for create_cyberherd_targets
        new_targets_data = []
        for member in herd_members:
            member_dict = dict(member)
            new_targets_data.append({
                'wallet': member_dict['lud16'],
                'alias': member_dict['display_name'] or 'Unknown',
                'payouts': float(member_dict['payouts']) if member_dict['payouts'] else 1.0
            })
        
        # Create the targets with proper distribution
        targets_data = await create_cyberherd_targets(new_targets_data, [])
        
        # Update the split payment targets - send the full dict as LNbits expects
        await update_cyberherd_targets(targets_data)
        
        logger.info(f"✅ Updated split payment targets for {len(new_targets_data)} CyberHerd members")
        
    except Exception as e:
        logger.error(f"Error updating split targets from herd: {e}")
        # Don't raise the exception to avoid breaking the main flow
        # The split payment update is supplementary to the core functionality

@http_retry
async def update_cyberherd_targets(targets):
    try:
        url = f'{config["LNBITS_URL"]}/splitpayments/api/v1/targets'
        headers = {
            'accept': 'application/json',
            'X-API-KEY': config['CYBERHERD_KEY'],
            'Content-Type': 'application/json'
        }
        
        # Log the data being sent for debugging the 400 error
        logger.info(f"📤 Updating LNbits targets: {targets}")
        logger.info(f"📤 Data type: {type(targets)}, Length: {len(targets) if isinstance(targets, list) else 'N/A'}")
        
        data = json.dumps(targets)
        response = await http_client.put(url, headers=headers, content=data)
        
        # Log response details for 400 errors
        if response.status_code != 200:
            logger.error(f"❌ LNbits API returned {response.status_code}: {response.text}")
        
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as e:
        logger.error(f"HTTP error updating cyberherd targets: {e}")
        if hasattr(e, 'response') and e.response:
            logger.error(f"Response status: {e.response.status_code}, Response text: {e.response.text}")
        raise HTTPException(
            status_code=e.response.status_code if e.response else 500,
            detail="Failed to update cyberherd targets"
        )
    except Exception as e:
        logger.error(f"Error updating cyberherd targets: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@lnbits_http_retry
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

@lnbits_http_retry
async def send_split_payment(balance: int):
    """Send payment to CyberHerd split wallet using invoice creation and payment."""
    memo = 'CyberHerd Distribution'
    try:
        # Create invoice with the CyberHerd (splits) wallet
        payment_request = await create_invoice(balance, memo, config['CYBERHERD_KEY'])
        
        # Small delay to prevent potential deadlock between invoice creation and payment
        await asyncio.sleep(0.5)
        
        # Pay the invoice from the main wallet
        payment_status = await pay_invoice(payment_request, config['HERD_KEY'])
        
        logger.info(f"✅ Split payment successful: {balance} sats sent to CyberHerd wallet")
        return {"success": True, "data": payment_status}
    except HTTPException as e:
        logger.error(f"Failed to send split payment: {e.detail}")
        return {"success": False, "message": f"Failed to send split payment: {e.detail}"}
    except Exception as e:
        logger.error(f"Failed to send split payment: {e}")
        return {"success": False, "message": f"Failed to send split payment: {str(e)}"}

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

def encode_lnurl(lightning_address: str) -> str:
    """
    Convert a lightning address to LNURL format per LNURL specification.
    
    Args:
        lightning_address: Lightning address like user@domain.com
        
    Returns:
        LNURL encoded string with 'lnurl' prefix
    """
    try:
        # Convert lightning address to URL
        user, domain = lightning_address.split('@', 1)
        url = f"https://{domain}/.well-known/lnurlp/{user}"
        
        # Encode URL as bytes
        url_bytes = url.encode('utf-8')
        
        # Convert to 5-bit groups for bech32 encoding
        def convertbits(data, frombits, tobits, pad=True):
            acc = 0
            bits = 0
            ret = []
            maxv = (1 << tobits) - 1
            max_acc = (1 << (frombits + tobits - 1)) - 1
            for value in data:
                if value < 0 or (value >> frombits):
                    return None
                acc = ((acc << frombits) | value) & max_acc
                bits += frombits
                while bits >= tobits:
                    bits -= tobits
                    ret.append((acc >> bits) & maxv)
            if pad:
                if bits:
                    ret.append((acc << (tobits - bits)) & maxv)
            elif bits >= frombits or ((acc << (tobits - bits)) & maxv):
                return None
            return ret
        
        # Convert to 5-bit groups
        spec = convertbits(url_bytes, 8, 5)
        if spec is None:
            return ""
            
        # LNURL uses bech32 encoding with 'lnurl' prefix
        alphabet = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
        encoded = ''.join(alphabet[i] for i in spec)
        
        return f"lnurl{encoded}"
    except Exception as e:
        logger.error(f"Failed to encode LNURL for {lightning_address}: {e}")
        return ""

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
            "unit": "sat",
            "memo": memo
        }
        response = await http_client.post(url, json=data, headers=headers)
        response.raise_for_status()
        response_data = response.json()
        return response_data.get('bolt11')
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
            "unit": "sat",
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
class ZapMessageGenerator:
    """Enhanced zap message generator with context-aware messages."""
    
    @staticmethod
    async def get_feeding_message(amount_sats: int, display_name: str, context: str = "regular") -> str:
        """Generate contextual feeding payout messages using messaging.py."""
        # Map context to messaging event types
        context_mapping = {
            "regular": "feeding_regular",
            "bonus": "feeding_bonus", 
            "remainder": "feeding_remainder"
        }
        
        event_type = context_mapping.get(context, "feeding_regular")
        cyber_herd_item = {"display_name": display_name}
        
        message, _ = await messaging.make_messages(
            config['NOS_SEC'], amount_sats, 0, event_type, 
            cyber_herd_item=cyber_herd_item, relays=RELAYS
        )
        return message
    
    @staticmethod
    async def get_fallback_message(amount_sats: int, reason: str = "remainder") -> str:
        """Generate fallback/predefined wallet messages using messaging.py."""
        cyber_herd_item = {"display_name": "member"}
        
        message, _ = await messaging.make_messages(
            config['NOS_SEC'], amount_sats, 0, "feeding_fallback",
            cyber_herd_item=cyber_herd_item, relays=RELAYS
        )
        return message

async def enhanced_zap_lud16(
    lud16: str, 
    sats: int, 
    text: str = None,
    context: str = "regular",
    display_name: str = "member"
) -> dict:
    """
    Simplified LNURL payment function for CyberHerd distributions.
    Uses only simple LNURL payments without complex Nostr zap functionality.
    
    Args:
        lud16: Lightning address
        sats: Amount in sats
        text: Custom message (optional)
        context: Message context for generation
        display_name: Display name for personalized messages
    
    Returns:
        Result dictionary with payment status
    """
    msat_amount = sats * 1000
    
    # Generate contextual message if none provided
    if text is None:
        text = await ZapMessageGenerator.get_feeding_message(sats, display_name, context)
    
    start_time = time.time()
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
        # Handle different types of httpx errors
        if hasattr(e, 'response') and e.response:
            status_code = e.response.status_code
        else:
            status_code = 500
        raise HTTPException(
            status_code=status_code,
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
        raise HTTPException(status_code=500, detail="Unexpected error retrieving GoatFeedings state")

@http_retry
async def update_goat_sats(sats_received: int):
    """Update GoatSats state in both cache and OpenHAB with race condition protection."""
    try:
        # Use a lock to prevent concurrent updates from causing inconsistencies
        async with app_state.lock:
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
            
            # Update cache without TTL - both operations under same lock
            await cache.set("goat_sats_state", new_state)
            logger.info(f"Updated GoatSats state to {new_state} (cache + OpenHAB)")
    
    except httpx.HTTPError as e:
        logger.error(f"HTTP error updating GoatSats in OpenHAB: {e}")
    except Exception as e:
        logger.error(f"Unexpected error updating GoatSats: {e}")

async def safe_balance_sync(force_refresh: bool = False):
    """
    DEPRECATED: WebSocket-only balance management eliminates need for HTTP sync.
    WebSocket payments include wallet_balance field which provides accurate, real-time balance.
    This function is now a no-op to maintain compatibility.
    """
    logger.debug("Balance sync skipped - using WebSocket-only balance updates")
    return

# Payment processing metrics tracking
class PaymentMetrics:
    def __init__(self):
        # Initialize from database on startup
        self._initialized = False
    
    async def _ensure_initialized(self):
        """Ensure metrics are loaded from database"""
        if not self._initialized:
            await self._load_from_database()
            self._initialized = True
    
    async def _load_from_database(self):
        """Load current metrics from database"""
        try:
            query = "SELECT * FROM payment_metrics WHERE id = 1"
            result = await database.fetch_one(query)
            if result:
                self.total_payments = result['total_payments'] or 0
                self.cyberherd_payments_detected = result['cyberherd_payments_detected'] or 0
                self.regular_payments_processed = result['regular_payments_processed'] or 0
                self.feeder_triggers = result['feeder_triggers'] or 0
                self.failed_payments = result['failed_payments'] or 0
                self.session_start = result['session_start'] or time.time()
                logger.info(f"✅ Loaded payment metrics from database: {self.total_payments} total payments")
            else:
                # Initialize with defaults if no record exists
                await self._create_initial_record()
        except Exception as e:
            logger.error(f"Error loading payment metrics: {e}")
            # Fall back to in-memory defaults
            self.total_payments = 0
            self.cyberherd_payments_detected = 0
            self.regular_payments_processed = 0
            self.feeder_triggers = 0
            self.failed_payments = 0
            self.session_start = time.time()
    
    async def _create_initial_record(self):
        """Create initial metrics record in database"""
        current_time = time.time()
        self.total_payments = 0
        self.cyberherd_payments_detected = 0
        self.regular_payments_processed = 0
        self.feeder_triggers = 0
        self.failed_payments = 0
        self.session_start = current_time
        
        query = '''
            INSERT OR REPLACE INTO payment_metrics 
            (id, total_payments, cyberherd_payments_detected, regular_payments_processed, 
             feeder_triggers, failed_payments, session_start, last_updated) 
            VALUES (:id, :total_payments, :cyberherd_payments_detected, :regular_payments_processed,
                    :feeder_triggers, :failed_payments, :session_start, :last_updated)
        '''
        await database.execute(query, values={
            "id": 1,
            "total_payments": self.total_payments,
            "cyberherd_payments_detected": self.cyberherd_payments_detected, 
            "regular_payments_processed": self.regular_payments_processed,
            "feeder_triggers": self.feeder_triggers, 
            "failed_payments": self.failed_payments,
            "session_start": current_time,
            "last_updated": current_time
        })
        logger.info("✅ Created initial payment metrics record")
    
    async def _save_to_database(self):
        """Save current metrics to database"""
        try:
            query = '''
                UPDATE payment_metrics 
                SET total_payments = :total_payments,
                    cyberherd_payments_detected = :cyberherd_payments_detected,
                    regular_payments_processed = :regular_payments_processed,
                    feeder_triggers = :feeder_triggers,
                    failed_payments = :failed_payments,
                    last_updated = :last_updated
                WHERE id = 1
            '''
            await database.execute(query, values={
                "total_payments": self.total_payments,
                "cyberherd_payments_detected": self.cyberherd_payments_detected,
                "regular_payments_processed": self.regular_payments_processed,
                "feeder_triggers": self.feeder_triggers,
                "failed_payments": self.failed_payments,
                "last_updated": time.time()
            })
        except Exception as e:
            logger.error(f"Error saving payment metrics: {e}")
    
    async def record_payment(self, is_cyberherd: bool = False, triggered_feeder: bool = False, failed: bool = False):
        """Record a payment event and persist to database"""
        await self._ensure_initialized()
        
        self.total_payments += 1
        if is_cyberherd:
            self.cyberherd_payments_detected += 1
        else:
            self.regular_payments_processed += 1
        if triggered_feeder:
            self.feeder_triggers += 1
        if failed:
            self.failed_payments += 1
        
        # Save to database after each update
        await self._save_to_database()
    
    async def get_stats(self) -> dict:
        """Get current payment statistics"""
        await self._ensure_initialized()
        
        uptime = time.time() - self.session_start
        return {
            "total_payments": self.total_payments,
            "cyberherd_payments": self.cyberherd_payments_detected,
            "regular_payments": self.regular_payments_processed,
            "feeder_triggers": self.feeder_triggers,
            "failed_payments": self.failed_payments,
            "uptime_seconds": uptime,
            "session_start": self.session_start,
            "cyberherd_detection_rate": (
                self.cyberherd_payments_detected / max(1, self.total_payments) * 100
            )
        }
    
    async def reset_metrics(self):
        """Reset all metrics and update database"""
        await self._ensure_initialized()
        
        current_time = time.time()
        self.total_payments = 0
        self.cyberherd_payments_detected = 0
        self.regular_payments_processed = 0
        self.feeder_triggers = 0
        self.failed_payments = 0
        self.session_start = current_time
        
        await self._save_to_database()
        logger.info("✅ Payment metrics reset")

payment_metrics = PaymentMetrics()

async def process_cyberherd_zap_from_payment(payment_data: dict, zap_request: dict):
    """
    Process CyberHerd zap directly from payment data.
    Extracts zap information and processes it through the cyber_herd logic.
    """
    try:
        import messaging
        
        # Extract payment information
        payment = payment_data.get('payment', {})
        amount_msat = payment.get('amount', 0)
        amount_sats = amount_msat // 1000
        
        # Extract zap request information
        zapper_pubkey = zap_request.get('pubkey', '')
        event_id = ''
        
        # Find the event being zapped
        for tag in zap_request.get('tags', []):
            if isinstance(tag, list) and len(tag) >= 2 and tag[0] == 'e':
                event_id = tag[1]
                break
        
        if not event_id or not zapper_pubkey:
            logger.error("Missing event_id or zapper_pubkey in CyberHerd zap")
            return
        
        # Get zap receipt ID from the zap request itself (not the payment description)
        # The zap_request parameter should contain the actual zap request event
        zap_receipt_id = zap_request.get('id', '')
        
        if not zap_receipt_id:
            logger.error("Missing zap receipt ID from zap request")
            return
        
        # Fetch user metadata using existing cyberherd module
        from utils.cyberherd_module import MetadataFetcher, generate_nprofile
        
        metadata_fetcher = MetadataFetcher()
        user_metadata = await metadata_fetcher.lookup_metadata(zapper_pubkey, RELAYS)
        
        if not user_metadata:
            logger.error(f"Failed to fetch metadata for pubkey {zapper_pubkey}")
            return
        
        # Extract user information
        display_name = user_metadata.get('display_name') or user_metadata.get('name', 'Anon')
        lud16 = user_metadata.get('lud16', '')
        picture = user_metadata.get('picture', '')
        
        if not lud16:
            logger.error(f"User {display_name} has no Lightning address (lud16)")
            return
        
        # Generate nprofile
        nprofile = await generate_nprofile(zapper_pubkey)
        
        # Create CyberHerdData object
        cyberherd_data = CyberHerdData(
            display_name=display_name,
            event_id=event_id,
            note=zap_receipt_id,
            kinds=[9735],
            pubkey=zapper_pubkey,
            nprofile=nprofile,
            lud16=lud16,
            amount=amount_sats,
            picture=picture,
            relays=RELAYS[:2]
        )
        
        logger.info(f"🎯 Processing CyberHerd zap from payment: {amount_sats} sats from {display_name}")
        
        # Process through the existing cyber_herd logic
        await process_single_cyberherd_item(cyberherd_data)
        
    except Exception as e:
        logger.error(f"Error processing CyberHerd zap from payment: {e}", exc_info=True)

async def process_single_cyberherd_item(item: CyberHerdData, skip_duplicate_check: bool = False):
    """
    Process a single CyberHerd item through the existing logic.
    This mirrors the main cyber_herd endpoint logic but for a single item.
    
    Args:
        item: CyberHerd data to process
        skip_duplicate_check: If True, skips the duplicate zap check (used for recovery scenarios)
    """
    async with database.transaction():
        try:
            import messaging
            
            query = "SELECT COUNT(*) as count FROM cyber_herd"
            result = await database.fetch_one(query)
            current_herd_size = result['count']

            members_to_notify = []
            unprocessed_items = []

            item_dict = item.dict()
            pubkey = item_dict['pubkey']
            note_id = item_dict.get('note')
            event_id = item_dict.get('event_id')
            
            logger.info(f"🔍 Processing zap - pubkey: {pubkey[:16]}..., note: {note_id}, event_id: {event_id}, amount: {item_dict.get('amount', 0)}")

            should_process = True
            if note_id and not skip_duplicate_check:
                # Check if this zap should be processed (atomic duplicate prevention)
                logger.info(f"🔍 Checking if zap {note_id} from {pubkey[:16]}... should be processed")
                should_process = await mark_zap_event_processing(note_id, pubkey, item_dict.get('event_id', ''), item_dict.get('amount', 0), database)
                if not should_process:
                    logger.info(f"DUPLICATE ZAP PREVENTED: Zap event {note_id} from {pubkey} already being processed or processed, skipping.")
                    return
                else:
                    logger.info(f"✅ Zap {note_id} marked for processing")
            elif skip_duplicate_check:
                logger.info(f"✅ Skipping duplicate check for recovery - zap {note_id} from {pubkey[:16]}... already claimed")

            try:
                check_query = "SELECT * FROM cyber_herd WHERE pubkey = :pubkey"
                member_record = await database.fetch_one(check_query, values={"pubkey": pubkey})
                is_existing_member = member_record is not None

                if is_existing_member:
                    await process_existing_member(item_dict, item, member_record, members_to_notify)
                elif not is_existing_member and current_herd_size < MAX_HERD_SIZE:
                    await process_new_member(item_dict, members_to_notify)
                    current_herd_size += 1
                elif not is_existing_member:
                    logger.info(f"🥊 Adding to headbutt queue (herd full)")
                    unprocessed_items.append(item)

                if note_id and not skip_duplicate_check:
                    await mark_zap_event_completed(note_id, database)
                elif note_id and skip_duplicate_check:
                    # For recovery scenarios, the completion is handled by the recovery process
                    logger.debug(f"✅ Zap {note_id} completion will be handled by recovery process")

            except Exception as e:
                logger.error(f"Error processing item for {pubkey}: {e}")
                if note_id and not skip_duplicate_check:
                    await mark_zap_event_failed(note_id, str(e), database)
                elif note_id and skip_duplicate_check:
                    # For recovery scenarios, failure handling is done by the recovery process
                    logger.debug(f"❌ Zap {note_id} failure will be handled by recovery process")
                return

            # Handle headbutting if needed
            if unprocessed_items:
                logger.info(f"Herd full: {current_herd_size} members - attempting headbutting with {len(unprocessed_items)} candidates.")
                await headbutt_service.process_headbutting_attempts(unprocessed_items)
                # Update split payment targets after headbutting since herd composition may have changed
                await update_split_targets_from_herd()
            
            await update_system_balance()
            difference = max(0, TRIGGER_AMOUNT_SATS - app_state.balance)

            if members_to_notify:
                # Get current herd size for notifications
                final_herd_count_query = "SELECT COUNT(*) as count FROM cyber_herd"
                final_count_result = await database.fetch_one(final_herd_count_query)
                final_herd_count = final_count_result['count'] if final_count_result else 0
                await process_notifications(members_to_notify, difference, final_herd_count)

        except Exception as e:
            logger.error(f"Failed to process CyberHerd item: {e}", exc_info=True)
            raise

@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(Exception)
)
async def process_payment_data(payment_data):
    """
    Processes incoming payment data from WebSocket.
    This function handles general payments. CyberHerd zaps are detected and
    processed directly within this function via process_cyberherd_zap_from_payment().
    """
    feeder_triggered = False
    is_cyberherd = False
    
    try:
        payment = payment_data.get('payment', {})
        description = payment.get('description', '')
        extra = payment.get('extra', {})

        # CyberHerd zap detection using proper Nostr event tag checking
        if description:
            try:
                zap_receipt = json.loads(description)
                if zap_receipt.get('kind') == 9735:
                    for tag in zap_receipt.get('tags', []):
                        if isinstance(tag, list) and len(tag) >= 2 and tag[0] == 'description':
                            try:
                                zap_request = json.loads(tag[1])
                                zapper_pubkey = zap_request.get('pubkey', '')
                                
                                # Check if this is an existing CyberHerd member
                                is_existing_member = False
                                if zapper_pubkey:
                                    check_query = "SELECT pubkey FROM cyber_herd WHERE pubkey = :pubkey"
                                    member_record = await database.fetch_one(check_query, values={"pubkey": zapper_pubkey})
                                    is_existing_member = member_record is not None
                                
                                for req_tag in zap_request.get('tags', []):
                                    if isinstance(req_tag, list) and len(req_tag) >= 2 and req_tag[0] == 'e':
                                        event_id = req_tag[1]
                                        is_cyberherd_note = await check_cyberherd_tag(event_id)
                                        
                                        # Process if: 1) CyberHerd note (for new or existing members)
                                        # OR 2) Existing member zapping any note
                                        if is_cyberherd_note or is_existing_member:
                                            zap_type = "CyberHerd note" if is_cyberherd_note else "member increase (any note)"
                                            member_status = "existing member" if is_existing_member else "new member"
                                            logger.info(f"CyberHerd zap detected in description - {zap_type} from {member_status} - processing directly")
                                            is_cyberherd = True
                                            await payment_metrics.record_payment(is_cyberherd=True)
                                            
                                            # Process CyberHerd zap directly here
                                            await process_cyberherd_zap_from_payment(payment_data, zap_request)
                                            return
                            except (json.JSONDecodeError, IndexError):
                                continue
                        
            except json.JSONDecodeError: 
                pass

        if extra and 'nostr' in extra:
            try:
                nostr_data = extra['nostr']
                zap_request = json.loads(nostr_data) if isinstance(nostr_data, str) else nostr_data
                if zap_request.get('kind') == 9734:
                    zapper_pubkey = zap_request.get('pubkey', '')
                    
                    # Check if this is an existing CyberHerd member
                    is_existing_member = False
                    if zapper_pubkey:
                        check_query = "SELECT pubkey FROM cyber_herd WHERE pubkey = :pubkey"
                        member_record = await database.fetch_one(check_query, values={"pubkey": zapper_pubkey})
                        is_existing_member = member_record is not None
                    
                    for tag in zap_request.get('tags', []):
                        if isinstance(tag, list) and len(tag) >= 2 and tag[0] == 'e':
                            event_id = tag[1]
                            is_cyberherd_note = await check_cyberherd_tag(event_id)
                            
                            # Process if: 1) CyberHerd note (for new or existing members)
                            # OR 2) Existing member zapping any note
                            if is_cyberherd_note or is_existing_member:
                                zap_type = "CyberHerd note" if is_cyberherd_note else "member increase (any note)"
                                member_status = "existing member" if is_existing_member else "new member"
                                logger.info(f"CyberHerd zap detected in payment - {zap_type} from {member_status} - processing directly")
                                is_cyberherd = True
                                await payment_metrics.record_payment(is_cyberherd=True)
                                
                                # Process CyberHerd zap directly here
                                await process_cyberherd_zap_from_payment(payment_data, zap_request)
                                return
            except (json.JSONDecodeError, KeyError, TypeError, IndexError): 
                pass

        logger.info("No CyberHerd zap detected - proceeding with normal payment processing.")
        
        payment_amount = payment.get('amount', 0)
        sats_received = payment_amount // 1000
        logger.info(f"Received non-herd payment of {sats_received} sats.")

        if sats_received > 0:
            await update_goat_sats(sats_received)

        # Use WebSocket wallet_balance for accurate balance updates
        wallet_balance_sats = payment_data.get('wallet_balance')
        if wallet_balance_sats is not None and wallet_balance_sats >= 0:
            async with app_state.lock:
                old_balance = app_state.balance
                app_state.balance = wallet_balance_sats
                app_state.last_balance_update = time.time()
                balance_change = wallet_balance_sats - old_balance
                logger.info(f"💰 Balance updated via WebSocket: {old_balance} → {wallet_balance_sats} sats (change: {balance_change:+d})")
        else:
            # Fallback: estimate balance based on payment amount if wallet_balance missing
            logger.warning(f"⚠️ Missing wallet_balance in WebSocket data, using fallback calculation")
            async with app_state.lock:
                old_balance = app_state.balance
                app_state.balance += sats_received
                app_state.last_balance_update = time.time()
                logger.info(f"💰 Balance estimated (fallback): {old_balance} → {app_state.balance} sats (+{sats_received})")
        
        # No need for HTTP balance sync - WebSocket provides accurate balance

        if sats_received > 0 and not await is_feeder_override_enabled():
            if app_state.balance >= TRIGGER_AMOUNT_SATS:
                if await trigger_feeder():
                    logger.info("Feeder triggered successfully.")
                    feeder_triggered = True
                    
                    payment_amount = app_state.balance
                    
                    # Use direct zap payments (LNbits splits functionality removed)
                    logger.info(f"Using direct zap payments for {payment_amount} sats")
                    payment_result = await pay_cyberherd_members_with_splits(payment_amount)
                    
                    if payment_result['success']:
                        logger.info(f"✅ CyberHerd payment successful: {payment_result.get('method', 'unknown')} method")
                        if payment_result.get('method') == 'direct_zap_payments':
                            logger.info(f"Zapped {payment_result.get('total_paid', 0)}/{payment_amount} sats to {payment_result.get('successful_payments', 0)} members")
                        
                        # Reset balance after successful payment
                        async with app_state.lock:
                            app_state.balance = 0
                            app_state.last_balance_update = time.time()
                        
                        feeder_msg, _ = await messaging.make_messages(config['NOS_SEC'], sats_received, 0, "feeder_triggered")
                        await messaging.send_to_websocket_clients(feeder_msg)
                    else:
                        logger.error(f"❌ CyberHerd payment failed: {payment_result.get('error', 'Unknown error')}")
                        # Don't reset balance if payment failed - keep it for retry
            else:
                difference = TRIGGER_AMOUNT_SATS - app_state.balance
                if sats_received >= 10:
                    # Use proper messaging system for sats_received messages
                    try:
                        # Generate proper message using messaging.py templates
                        message, command = await messaging.make_messages(
                            config['NOS_SEC'],
                            sats_received, 
                            difference,
                            "sats_received"
                        )
                        
                        # Send formatted client message
                        client_message = await messaging.format_client_message(message, "sats_received")
                        await messaging.send_to_websocket_clients(client_message)
                        
                    except Exception as e:
                        logger.error(f"❌ Error generating sats_received message: {e}")
                        # Fallback to simple message if messaging system fails
                        simple_message = {
                            "type": "sats_received",
                            "amount": sats_received,
                            "difference": difference,
                            "message": f"⚡ {sats_received} sats received! Thanks for supporting the goats! 🐐"
                        }
                        await messaging.send_to_websocket_clients(json.dumps(simple_message))
        else:
            logger.info("Feeder override is ON or payment amount is non-positive. Skipping feeder logic.")

        # Record successful payment processing
        await payment_metrics.record_payment(is_cyberherd=is_cyberherd, triggered_feeder=feeder_triggered)

    except Exception as e:
        logger.error(f"Error processing payment data: {e}")
        await payment_metrics.record_payment(is_cyberherd=is_cyberherd, failed=True)
        raise


@http_retry
# LNbits splits send_payment function removed - using direct zap payments only

async def pay_cyberherd_members_with_splits(total_amount_sats: int):
    """
    Simple CyberHerd payment using LNbits split payments extension.
    Just sends payment to the CyberHerd wallet which distributes automatically.
    
    Args:
        total_amount_sats: Total amount in sats to distribute
    
    Returns:
        dict: Payment result
    """
    start_time = time.time()
    payment_session_id = f"splits_{int(start_time)}"
    
    try:
        logger.info(f"💰 Using split payments for {total_amount_sats} sats (session: {payment_session_id})")
        
        # Send payment to CyberHerd split wallet
        result = await send_split_payment(total_amount_sats)
        
        duration = time.time() - start_time
        
        if result['success']:
            logger.info(f"✅ CyberHerd split payment successful: {total_amount_sats} sats distributed")
            return {
                "success": True,
                "method": "split_payments",
                "amount_distributed": total_amount_sats,
                "duration": round(duration, 2)
            }
        else:
            logger.error(f"❌ CyberHerd split payment failed: {result.get('message', 'Unknown error')}")
            return {
                "success": False,
                "method": "split_payments_failed",
                "error": result.get('message', 'Split payment failed'),
                "duration": round(duration, 2)
            }
    
    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"❌ Error in split payment processing: {e}")
        return {
            "success": False,
            "method": "split_payments_error",
            "error": str(e),
            "duration": round(duration, 2)
        }

# FastAPI Endpoints - Health and Balance

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.get("/balance")
async def get_balance_route(force_refresh: bool = False):
    """
    DIAGNOSTIC ONLY: HTTP balance endpoint for debugging and monitoring.
    Real-time balance updates are handled via WebSocket wallet_balance field.
    """
    try:
        balance_value = await get_balance(force_refresh)
        # Return balance in millisats (client will convert to sats)
        return {"balance": balance_value}
    except HTTPException:
        # If the external service is unavailable, return the cached balance from app_state
        async with app_state.lock:
            cached_balance_sats = app_state.balance
        # Convert cached sats back to millisats for the API response
        cached_balance_millisats = cached_balance_sats * 1000
        logger.warning(f"Using cached balance: {cached_balance_sats} sats ({cached_balance_millisats} millisats) (external service unavailable)")
        return {"balance": cached_balance_millisats}

@app.get("/payments/balance")
async def get_payments_balance_route(force_refresh: bool = False):
    """Client endpoint for balance - calls the main balance route"""
    return await get_balance_route(force_refresh)

@app.get("/payments/trigger_amount")
async def get_trigger_amount_route():
    """Client endpoint for trigger amount"""
    return {"trigger_amount": TRIGGER_AMOUNT_SATS}

@app.get("/trigger_amount")
async def get_trigger_amount_base_route():
    """Base endpoint for trigger amount"""
    return {"trigger_amount": TRIGGER_AMOUNT_SATS}

@app.get("/cyberherd/spots_remaining")
async def get_cyberherd_spots_remaining():
    """Get remaining spots in the cyber herd"""
    try:
        query = "SELECT COUNT(*) as count FROM cyber_herd"
        result = await database.fetch_one(query)
        spots_remaining = max(0, MAX_HERD_SIZE - result['count'])
        return {"spots_remaining": spots_remaining}
    except Exception as e:
        logger.error(f"Error getting cyber herd spots remaining: {e}")
        return {"spots_remaining": MAX_HERD_SIZE}

@app.get("/payment_metrics")
async def get_payment_metrics():
    """Get payment processing metrics and statistics"""
    try:
        return {"metrics": await payment_metrics.get_stats()}
    except Exception as e:
        logger.error(f"Error getting payment metrics: {e}")
        return {"metrics": {"error": "Failed to retrieve metrics"}}

@app.post("/payment_metrics/reset")
async def reset_payment_metrics():
    """Reset payment processing metrics"""
    try:
        await payment_metrics.reset_metrics()
        return {"status": "success", "message": "Payment metrics reset successfully"}
    except Exception as e:
        logger.error(f"Error resetting payment metrics: {e}")
        return {"status": "error", "message": "Failed to reset metrics"}


async def process_existing_member(item_dict: dict, item: CyberHerdData, result: dict, members_to_notify: list):
    """Process a cumulative zap for an existing herd member."""
    new_amount = result['amount'] + item_dict['amount']
    new_payouts = result['payouts'] + calculate_payout(item_dict['amount'])
    
    update_query = """
        UPDATE cyber_herd 
        SET amount = :amount, payouts = :payouts 
        WHERE pubkey = :pubkey
    """
    await database.execute(update_query, values={
        "amount": new_amount,
        "payouts": new_payouts,
        "pubkey": item_dict['pubkey']
    })
    
    logger.info(f"Updated existing member {item_dict['pubkey']} with {item_dict['amount']} sats. New total: {new_amount}")
    
    # Update split payment targets since payouts changed
    await update_split_targets_from_herd()
    
    notification_data = {
        "type": "member_increase",
        "pubkey": item_dict['pubkey'],
        "display_name": result['display_name'],
        "nprofile": result['nprofile'],
        "event_id": item_dict['event_id'],
        "amount": new_amount,
        "new_zap_amount": item_dict['amount']
    }
    members_to_notify.append(notification_data)


async def process_new_member(item_dict: dict, members_to_notify: list):
    """Process a zap from a new member when there is space in the herd."""
    payouts = calculate_payout(item_dict['amount'])
    
    insert_query = """
        INSERT INTO cyber_herd (pubkey, display_name, event_id, note, kinds, nprofile, lud16, notified, payouts, amount, picture, relays)
        VALUES (:pubkey, :display_name, :event_id, :note, :kinds, :nprofile, :lud16, :notified, :payouts, :amount, :picture, :relays)
    """
    await database.execute(insert_query, values={
        "pubkey": item_dict['pubkey'],
        "display_name": item_dict['display_name'],
        "event_id": item_dict['event_id'],
        "note": item_dict['note'],
        "kinds": ','.join(map(str, item_dict['kinds'])),
        "nprofile": item_dict['nprofile'],
        "lud16": item_dict['lud16'],
        "notified": None,
        "payouts": payouts,
        "amount": item_dict['amount'],
        "picture": item_dict['picture'],
        "relays": json.dumps(item_dict.get('relays', RELAYS[:2]))
    })
    
    logger.info(f"Added new member {item_dict['pubkey']} with {item_dict['amount']} sats.")
    
    # Update split payment targets since a new member was added
    await update_split_targets_from_herd()
    
    notification_data = {
        "type": "new_member",
        "pubkey": item_dict['pubkey'],
        "display_name": item_dict['display_name'],
        "nprofile": item_dict['nprofile'],
        "event_id": item_dict['event_id'],
        "amount": item_dict['amount']
    }
    members_to_notify.append(notification_data)


async def update_system_balance():
    """Force a refresh of the system's wallet balance."""
    await get_balance(force_refresh=True)
    logger.info(f"System balance updated to: {app_state.balance} sats")


async def process_notifications(members_to_notify: list, difference: int, final_herd_size: int):
    """Send notifications for all processed events."""
    for member_info in members_to_notify:
        try:
            member_info_copy = member_info.copy()
            message_type = member_info_copy.pop("type", None)
            if not message_type:
                logger.warning(f"Missing 'type' in notification data: {member_info}")
                continue

            message, _ = await messaging.make_messages(
                nos_sec=config['NOS_SEC'],
                new_amount=member_info_copy.get('new_zap_amount', member_info_copy.get('amount', 0)),
                difference=difference,
                event_type=message_type,
                cyber_herd_item=member_info_copy,
                spots_remaining=max(0, MAX_HERD_SIZE - final_herd_size),
                relays=RELAYS
            )
            await messaging.send_to_websocket_clients(message)

            pubkey_to_update = member_info.get('pubkey')
            if pubkey_to_update:
                update_query = "UPDATE cyber_herd SET notified = :notified_at WHERE pubkey = :pubkey"
                await database.execute(update_query, values={"notified_at": time.time(), "pubkey": pubkey_to_update})
                logger.info(f"Marked member {pubkey_to_update} as notified.")

        except Exception as e:
            logger.error(f"Failed to send or update notification for {member_info.get('pubkey')}: {e}")
    
    # After processing all notifications, send updated CyberHerd member list for accordion display
    if members_to_notify:
        # Find the newest member's pubkey (look for new_member type)
        newest_pubkey = None
        for member_info in members_to_notify:
            if member_info.get("type") == "new_member":
                newest_pubkey = member_info.get("pubkey")
                break
        await send_cyberherd_update(newest_pubkey)


async def send_cyberherd_update(newest_pubkey: str = None):
    """Send updated CyberHerd member list to all connected clients for accordion display."""
    await messaging.send_cyberherd_update(newest_pubkey, database)

# Set the CyberHerd update function for headbutt service
headbutt_service.send_cyberherd_update = send_cyberherd_update


@app.get("/get_cyber_herd")
async def get_cyber_herd():
    """Retrieve the current members of the cyber herd."""
    query = "SELECT * FROM cyber_herd"
    herd = await database.fetch_all(query)
    return herd

@app.post("/reset_cyber_herd")
async def reset_cyber_herd():
    """
    Resets the CyberHerd by clearing the table (LNbits splits functionality removed).
    """
    try:
        async with database.transaction():
            delete_query = "DELETE FROM cyber_herd"
            await database.execute(delete_query)
            logger.info("Cyber herd table has been cleared.")

        # Update split payment targets since herd is now empty
        await update_split_targets_from_herd()

        message, _ = await messaging.make_messages(config['NOS_SEC'], 0, 0, "herd_reset", relays=RELAYS)
        await messaging.send_to_websocket_clients(message)
        
        # Send empty CyberHerd update to clear accordion display
        empty_cyberherd_message = {
            "type": "cyber_herd",
            "members": [],
            "total_members": 0,
            "message": "🐐 CyberHerd has been reset"
        }
        await messaging.send_to_websocket_clients(json.dumps(empty_cyberherd_message))

        return {"status": "Cyber herd reset successfully"}
    except Exception as e:
        logger.error(f"Failed to reset cyber herd: {e}")
        raise HTTPException(status_code=500, detail="Failed to reset cyber herd")

@app.post("/delete_cyber_herd_member/{pubkey}")
async def delete_cyber_herd_member(pubkey: str):
    """Deletes a specific member from the cyber herd by their pubkey (LNbits splits functionality removed)."""
    try:
        async with database.transaction():
            check_query = "SELECT * FROM cyber_herd WHERE pubkey = :pubkey"
            member = await database.fetch_one(check_query, values={"pubkey": pubkey})
            if not member:
                raise HTTPException(status_code=404, detail="Member not found")

            delete_query = "DELETE FROM cyber_herd WHERE pubkey = :pubkey"
            await database.execute(delete_query, values={"pubkey": pubkey})
            logger.info(f"Deleted member {pubkey} from the cyber herd.")

        # Update split payment targets since a member was removed
        await update_split_targets_from_herd()

        return {"status": f"Member {pubkey} deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete member {pubkey}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete member {pubkey}")

@app.post("/set_goat_sats")
async def set_goat_sats(data: SetGoatSatsData):
    """Manually sets the GoatSats value in OpenHAB and the local cache."""
    try:
        new_amount = data.new_amount        
        # Update OpenHAB
        auth = (config['OH_AUTH_1'], '')
        headers = {"Content-Type": "text/plain"}
        put_url = f"{config['OPENHAB_URL']}/rest/items/GoatSats/state"
        put_response = await http_client.put(put_url, headers=headers, auth=auth, content=str(new_amount))
        put_response.raise_for_status()
        
        # Update cache
        await cache.set("goat_sats_state", new_amount)
        
        logger.info(f"GoatSats manually set to {new_amount}")
        return {"status": "success", "new_amount": new_amount}
    except httpx.HTTPError as e:
        logger.error(f"HTTP error setting GoatSats in OpenHAB: {e}")
        raise HTTPException(status_code=500, detail="Failed to set GoatSats in OpenHAB")
    except Exception as e:
        logger.error(f"Unexpected error setting GoatSats: {e}")
        raise HTTPException(status_code=500, detail="Unexpected error setting GoatSats")

@app.get("/get_goat_sats")
async def get_goat_sats():
    """Retrieves the current sum of GoatSats for the day."""
    return await get_goat_sats_sum_today()

@app.get("/get_goat_feedings")
async def get_goat_feedings_route():
    """Retrieves the number of goat feedings from OpenHAB."""
    return await get_goat_feedings()


@app.post("/cyberherd/update_split_targets")
async def update_split_targets_endpoint():
    """
    Manually update LNbits split payment targets based on current CyberHerd members.
    Useful for testing or recovery scenarios.
    
    Returns:
        Status of the split target update operation
    """
    try:
        await update_split_targets_from_herd()
        return {
            "success": True,
            "message": "Split payment targets updated successfully"
        }
    except Exception as e:
        logger.error(f"Error updating split targets via endpoint: {e}")
        return {
            "success": False,
            "error": str(e),
            "message": "Failed to update split payment targets"
        }


@app.post("/cyberherd/pay_direct")
async def pay_cyberherd_direct(amount: int = 0):
    """
    Manually trigger direct CyberHerd payments using configured method.
    
    Args:
        amount: Amount to distribute (default: current balance)
    
    Returns:
        Payment results and status
    """
    try:
        payment_amount = amount if amount > 0 else app_state.balance
        
        if payment_amount <= 0:
            return {"success": False, "error": "No amount specified and balance is zero"}
        
        # Use direct zap payments (LNbits splits functionality removed)
        logger.info(f"Manual direct CyberHerd zap payment triggered for {payment_amount} sats")
        result = await pay_cyberherd_members_with_splits(payment_amount)
        
        # Reset balance if payment was successful and we used the full balance
        if result['success'] and amount == 0:
            async with app_state.lock:
                app_state.balance = 0
                app_state.last_balance_update = time.time()
        
        return result
        
    except Exception as e:
        logger.error(f"Error in manual payment: {e}")
        return {"success": False, "error": str(e)}

@app.get("/cyberherd/payment_preview")
async def preview_cyberherd_payments():
    """
    Preview how payments would be distributed to CyberHerd members
    using direct zap payments (LNbits splits removed).
    
    Returns:
        Distribution preview with amounts per member
    """
    try:
        # Get current herd members from local database
        query = "SELECT pubkey, display_name, lud16, payouts, amount FROM cyber_herd ORDER BY payouts DESC"
        herd_members = await database.fetch_all(query)
        
        payment_method = "direct_zap_payments"
        
        if not herd_members:
            return {
                "success": True,
                "payment_method": payment_method,
                "total_members": 0,
                "distribution": [],
                "fallback_wallet": {
                    "recipient": "predefined_wallet",
                    "amount": app_state.balance,
                    "reason": "No CyberHerd members found",
                    "method": "zap"
                }
            }
        
        members_list = [dict(member) for member in herd_members]
        total_payouts = sum(member.get('payouts', 0) for member in members_list)
        total_amount = app_state.balance
        
        distribution = []
        
        if total_payouts == 0:
            # Equal split among all members
            amount_per_member = total_amount // len(members_list)
            remainder = total_amount % len(members_list)
            
            for i, member in enumerate(members_list):
                member_amount = amount_per_member
                if i < remainder:
                    member_amount += 1
                
                distribution.append({
                    "pubkey": member['pubkey'],
                    "display_name": member['display_name'],
                    "lud16": member['lud16'],
                    "payouts": member['payouts'],
                    "total_contributed": member['amount'],
                    "payment_amount": member_amount,
                    "calculation": "equal_split",
                    "payment_method": "zap"
                })
        else:
            # Proportional split based on payouts
            for member in members_list:
                member_payouts = member.get('payouts', 0)
                member_amount = int((member_payouts / total_payouts) * total_amount)
                
                distribution.append({
                    "pubkey": member['pubkey'],
                    "display_name": member['display_name'],
                    "lud16": member['lud16'],
                    "payouts": member_payouts,
                    "total_contributed": member['amount'],
                    "payment_amount": member_amount,
                    "calculation": f"{member_payouts}/{total_payouts} = {(member_payouts/total_payouts)*100:.1f}%",
                    "payment_method": "zap"
                })
        
        total_distributed = sum(d['payment_amount'] for d in distribution)
        remainder = total_amount - total_distributed
        
        return {
            "success": True,
            "payment_method": payment_method,
            "total_amount": total_amount,
            "total_members": len(members_list),
            "total_distributed": total_distributed,
            "remainder": remainder,
            "distribution": distribution,
            "remainder_destination": "predefined_wallet" if remainder > 0 else None,
            "remainder_method": "zap"
        }
        
    except Exception as e:
        logger.error(f"Error previewing CyberHerd payments: {e}")
        return {"success": False, "error": str(e)}

@app.get("/cyberherd/payment_methods")
async def get_payment_methods():
    """
    Get information about available payment methods and their current configuration.
    
    Returns:
        Payment method capabilities and configuration
    """
    try:
        # Check herd members count
        query = "SELECT COUNT(*) as count FROM cyber_herd"
        result = await database.fetch_one(query)
        herd_size = result['count']
        
        # Check predefined wallet configuration
        predefined_lud16 = config.get('PREDEFINED_WALLET_ADDRESS')
        predefined_alias = config.get('PREDEFINED_WALLET_ALIAS')
        
        # Get current payment method setting
        use_direct_zaps = True  # Always use direct zaps now (splits removed)
        
        return {
            "success": True,
            "current_method": "direct_zap_payments",
            "methods": {
                "direct_zap_payments": {
                    "available": True,
                    "active": True,
                    "description": "Zap each CyberHerd member directly using proper Nostr zap flow",
                    "herd_members": herd_size,
                    "benefits": [
                        "Proper Nostr zap protocol",
                        "Individual member notifications",
                        "Better user experience",
                        "Direct member engagement",
                        "LNURL fallback support"
                    ]
                },
                "predefined_wallet": {
                    "available": bool(predefined_lud16),
                    "address": predefined_lud16,
                    "alias": predefined_alias,
                    "description": "Fallback wallet for remainders and when no herd members exist",
                    "usage": "remainder_and_fallback"
                }
            },
            "configuration": {
                "note": "LNbits splits functionality has been removed. Only direct zap payments are supported."
            },
            "current_balance": app_state.balance,
            "trigger_amount": TRIGGER_AMOUNT_SATS
        }
        
    except Exception as e:
        logger.error(f"Error getting payment methods: {e}")
        return {"success": False, "error": str(e)}

@app.get("/cyberherd/configuration")
async def get_cyberherd_configuration():
    """
    Get current CyberHerd configuration and system status.
    
    Returns:
        Configuration details and system information
    """
    try:
        # Get herd statistics
        herd_query = "SELECT COUNT(*) as count, COALESCE(SUM(amount), 0) as total_amount, COALESCE(SUM(payouts), 0) as total_payouts FROM cyber_herd"
        herd_stats = await database.fetch_one(herd_query)
        
        # Get payment method configuration - simplified to LNURL only
        
        return {
            "success": True,
            "system_info": {
                "max_herd_size": MAX_HERD_SIZE,
                "trigger_amount_sats": TRIGGER_AMOUNT_SATS,
                "headbutt_min_sats": HEADBUTT_MIN_SATS,
                "current_balance": app_state.balance
            },
            "herd_statistics": {
                "current_members": herd_stats['count'],
                "spots_remaining": max(0, MAX_HERD_SIZE - herd_stats['count']),
                "total_contributed": herd_stats['total_amount'],
                "total_payouts_earned": herd_stats['total_payouts']
            },
            "payment_configuration": {
                "method": "simple_lnurl_payments",
                "use_direct_zap_payments": False,
                "description": "Uses simple LNURL payments for reliable CyberHerd distributions"
            },
            "wallet_configuration": {
                "predefined_wallet_address": config.get('PREDEFINED_WALLET_ADDRESS'),
                "predefined_wallet_alias": config.get('PREDEFINED_WALLET_ALIAS'),
                "herd_wallet_configured": bool(config.get('HERD_KEY')),
                "cyberherd_wallet_configured": bool(config.get('CYBERHERD_KEY'))
            },
            "nostr_configuration": {
                "private_key_configured": bool(config.get('NOS_SEC')),
                "public_key_configured": bool(config.get('HEX_KEY')),
                "websocket_configured": bool(config.get('HERD_WEBSOCKET'))
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting CyberHerd configuration: {e}")
        return {"success": False, "error": str(e)}

@app.get("/ws")
async def redirect_ws():
    return {"message": "Redirecting to /ws/"}

@app.websocket("/ws/")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    async with clients_lock:
        connected_clients.add(websocket)
    logger.info(f"Client connected. Total clients: {len(connected_clients)}")

    try:
        while True:
            await websocket.receive_text()
    except Exception as e:
        logger.warning(f"WebSocket connection error: {e}")
    finally:
        async with clients_lock:
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
