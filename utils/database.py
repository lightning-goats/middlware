import asyncio
import json
import logging
import time
from typing import Dict, List, Any
from databases import Database
from asyncio import Lock

logger = logging.getLogger(__name__)

import os

# Database URL configuration
if os.getenv("PYTEST_CURRENT_TEST") or os.getenv("TESTING_MODE") == "true":
    DATABASE_URL = "sqlite:///test_cyberherd.db"
else:
    DATABASE_URL = "sqlite:///cyberherd.db"

database = Database(DATABASE_URL)

# ==============================================================================
# CORE DATABASE AND MIGRATION FUNCTIONS
# ==============================================================================

async def init_database():
    """Initialize the database connection and apply PRAGMA settings for performance."""
    if not database.is_connected:
        await database.connect()
    
    pragmas = {
        "busy_timeout": 30000,
        "journal_mode": "WAL",
        "synchronous": "NORMAL",
        "wal_autocheckpoint": 1000,
        "temp_store": "MEMORY"
    }
    
    for key, value in pragmas.items():
        try:
            await database.execute(f"PRAGMA {key}={value};")
        except Exception as e:
            logger.warning(f"Could not set PRAGMA {key}={value}: {e}")

async def comprehensive_database_setup():
    """
    Comprehensive database setup and verification.
    Combines table creation, migrations, and integrity verification.
    """
    logger.info("🔧 Running comprehensive database setup and verification...")
    try:
        await create_missing_tables()
        await apply_database_migrations()
        await verify_database_integrity()
        logger.info("✅ Comprehensive database setup completed successfully")
        return True
    except Exception as e:
        logger.error(f"❌ Comprehensive database setup failed: {e}", exc_info=True)
        raise RuntimeError("Critical database setup failed. Application cannot start.")

async def create_missing_tables():
    """Create all required database tables if they do not already exist."""
    logger.info("🔧 Ensuring all database tables exist...")
    
    table_schemas = {
        "processed_events": '''
            CREATE TABLE IF NOT EXISTS processed_events (
                event_id TEXT PRIMARY KEY,
                processed_at REAL NOT NULL,
                event_type TEXT DEFAULT 'unknown'
            )
        ''',
        "cyber_herd": '''
            CREATE TABLE IF NOT EXISTS cyber_herd (
                pubkey TEXT PRIMARY KEY,
                display_name TEXT,
                event_id TEXT,
                note TEXT,
                kinds TEXT,
                nprofile TEXT,
                lud16 TEXT,
                notified TEXT,
                payouts REAL DEFAULT 0.0,
                amount INTEGER DEFAULT 0,
                picture TEXT,
                relays TEXT,
                metadata_last_checked_at INTEGER,
                is_active INTEGER DEFAULT 0
            )
        ''',
        "cache": '''
            CREATE TABLE IF NOT EXISTS cache (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                expires_at REAL NOT NULL
            )
        ''',
        "processed_zap_events": '''
            CREATE TABLE IF NOT EXISTS processed_zap_events (
                zap_event_id TEXT PRIMARY KEY,
                pubkey TEXT NOT NULL,
                original_event_id TEXT NOT NULL,
                processed_at REAL NOT NULL,
                amount INTEGER DEFAULT 0,
                status TEXT DEFAULT 'completed'
            )
        ''',
        "payment_metrics": '''
            CREATE TABLE IF NOT EXISTS payment_metrics (
                id INTEGER PRIMARY KEY,
                total_payments INTEGER DEFAULT 0,
                cyberherd_payments_detected INTEGER DEFAULT 0,
                regular_payments_processed INTEGER DEFAULT 0,
                feeder_triggers INTEGER DEFAULT 0,
                failed_payments INTEGER DEFAULT 0,
                session_start REAL,
                last_updated REAL
            )
        '''
    }
    
    for table_name, schema in table_schemas.items():
        await execute_with_retry(schema)
        
    await execute_with_retry('''
        INSERT OR IGNORE INTO payment_metrics (id, session_start, last_updated)
        VALUES (1, :current_time, :current_time)
    ''', values={"current_time": time.time()})
    
    logger.info("✅ All tables are present.")

# --- Critical table guards ----------------------------------------------------
PROCESSED_ZAP_EVENTS_SCHEMA = '''
    CREATE TABLE IF NOT EXISTS processed_zap_events (
        zap_event_id TEXT PRIMARY KEY,
        pubkey TEXT NOT NULL,
        original_event_id TEXT NOT NULL,
        processed_at REAL NOT NULL,
        amount INTEGER DEFAULT 0,
        status TEXT DEFAULT 'completed'
    )
'''

CACHE_TABLE_SCHEMA = '''
    CREATE TABLE IF NOT EXISTS cache (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        expires_at REAL NOT NULL
    )
'''

async def ensure_processed_zap_events_table(db=None):
    db_conn = db or database
    try:
        await db_conn.execute(PROCESSED_ZAP_EVENTS_SCHEMA)
    except Exception as e:
        logger.error(f"Failed to ensure processed_zap_events table: {e}")
        raise

async def ensure_cache_table(db=None):
    db_conn = db or database
    try:
        await db_conn.execute(CACHE_TABLE_SCHEMA)
    except Exception as e:
        logger.error(f"Failed to ensure cache table: {e}")
        raise

async def apply_database_migrations():
    """Apply database migrations for schema updates idempotently."""
    logger.info("🔄 Applying database migrations...")

    expected_cyberherd_schema = {
        'pubkey': 'TEXT PRIMARY KEY', 'display_name': 'TEXT', 'event_id': 'TEXT',
        'note': 'TEXT', 'kinds': 'TEXT', 'nprofile': 'TEXT', 'lud16': 'TEXT',
        'notified': 'TEXT', 'payouts': 'REAL DEFAULT 0.0', 'amount': 'INTEGER DEFAULT 0',
        'picture': 'TEXT', 'relays': 'TEXT',
        'metadata_last_checked_at': 'INTEGER',
        'is_active': 'INTEGER DEFAULT 0'
    }
    
    try:
        table_info = await database.fetch_all("PRAGMA table_info(cyber_herd);")
        existing_columns = {row['name'] for row in table_info}

        for column_name, column_type in expected_cyberherd_schema.items():
            if column_name not in existing_columns:
                logger.info(f"Column '{column_name}' missing from 'cyber_herd'. Adding it...")
                await execute_with_retry(f'ALTER TABLE cyber_herd ADD COLUMN {column_name} {column_type}')
                logger.info(f"✅ Added column '{column_name}' to 'cyber_herd' table.")
    except Exception as e:
        logger.error(f"❌ Failed to migrate 'cyber_herd' table: {e}", exc_info=True)
        raise
    
    try:
        await execute_with_retry('ALTER TABLE processed_zap_events ADD COLUMN status TEXT DEFAULT "completed"')
    except Exception:
        pass # Column already exists
    try:
        await execute_with_retry('ALTER TABLE processed_events ADD COLUMN event_type TEXT DEFAULT "unknown"')
    except Exception:
        pass # Column already exists
    
    logger.info("✅ Database migrations completed.")

async def verify_database_integrity():
    """Verify that all required tables are accessible and can be queried."""
    logger.info("🔍 Verifying database integrity...")
    tables_to_test = ['processed_events', 'cyber_herd', 'cache', 'processed_zap_events', 'payment_metrics']
    for table_name in tables_to_test:
        try:
            await execute_with_retry(f"SELECT COUNT(*) FROM {table_name} LIMIT 1")
        except Exception as e:
            logger.error(f"❌ Table '{table_name}' verification failed: {e}")
            raise RuntimeError(f"Database integrity check failed on table: {table_name}")
    logger.info("✅ Database integrity check passed.")
    return True

async def close_database():
    """Close the database connection."""
    if database.is_connected:
        await database.disconnect()

# ==============================================================================
# GENERIC HELPERS (EVENT PROCESSING, CACHE, ETC.)
# ==============================================================================

async def is_zap_event_processed(zap_event_id: str, db=None) -> bool:
    db_conn = db or database
    query = "SELECT status FROM processed_zap_events WHERE zap_event_id = :zap_event_id"
    try:
        result = await db_conn.fetch_one(query, values={"zap_event_id": zap_event_id})
    except Exception as e:
        if "no such table: processed_zap_events" in str(e).lower():
            await ensure_processed_zap_events_table(db_conn)
            result = await db_conn.fetch_one(query, values={"zap_event_id": zap_event_id})
        else:
            raise
    return result is not None and result['status'] == 'completed'

async def mark_zap_event_processing(zap_event_id: str, pubkey: str, original_event_id: str, amount: int = 0, db=None) -> bool:
    db_conn = db or database
    query = """
        INSERT OR IGNORE INTO processed_zap_events 
        (zap_event_id, pubkey, original_event_id, processed_at, amount, status) 
        VALUES (:zap_event_id, :pubkey, :original_event_id, :processed_at, :amount, 'processing')
    """
    try:
        result = await db_conn.execute(query, values={
            "zap_event_id": zap_event_id, "pubkey": pubkey, "original_event_id": original_event_id,
            "processed_at": time.time(), "amount": amount
        })
    except Exception as e:
        if "no such table: processed_zap_events" in str(e).lower():
            await ensure_processed_zap_events_table(db_conn)
            result = await db_conn.execute(query, values={
                "zap_event_id": zap_event_id, "pubkey": pubkey, "original_event_id": original_event_id,
                "processed_at": time.time(), "amount": amount
            })
        else:
            raise
    return result > 0

async def mark_zap_event_completed(zap_event_id: str, db=None):
    db_conn = db or database
    query = "UPDATE processed_zap_events SET status = 'completed' WHERE zap_event_id = :zap_event_id"
    try:
        await db_conn.execute(query, values={"zap_event_id": zap_event_id})
    except Exception as e:
        if "no such table: processed_zap_events" in str(e).lower():
            await ensure_processed_zap_events_table(db_conn)
            await db_conn.execute(query, values={"zap_event_id": zap_event_id})
        else:
            raise

async def mark_zap_event_failed(zap_event_id: str, error_msg: str = "", db=None):
    db_conn = db or database
    query = "DELETE FROM processed_zap_events WHERE zap_event_id = :zap_event_id"
    try:
        await db_conn.execute(query, values={"zap_event_id": zap_event_id})
    except Exception as e:
        if "no such table: processed_zap_events" in str(e).lower():
            await ensure_processed_zap_events_table(db_conn)
            # Nothing to delete if just created, but keep flow consistent
        else:
            raise
    logger.warning(f"Removed failed zap event {zap_event_id} for retry. Error: {error_msg}")

async def cleanup_failed_zap_events(db=None):
    try:
        db_conn = db or database
        ten_minutes_ago = time.time() - 600
        query = "DELETE FROM processed_zap_events WHERE status = 'processing' AND processed_at < :ten_minutes_ago"
        try:
            result = await db_conn.execute(query, values={"ten_minutes_ago": ten_minutes_ago})
        except Exception as e:
            if "no such table: processed_zap_events" in str(e).lower():
                await ensure_processed_zap_events_table(db_conn)
                result = await db_conn.execute(query, values={"ten_minutes_ago": ten_minutes_ago})
            else:
                raise
        if result and result > 0:
            logger.info(f"♻️ Cleaned up and removed {result} stuck zap events.")
    except Exception as e:
        logger.error(f"Error in cleanup_failed_zap_events: {e}")

class DatabaseCache:
    def __init__(self, db):
        self.db = db
        self.lock = Lock()

    async def get(self, key, default=None):
        async with self.lock:
            query = "SELECT value, expires_at FROM cache WHERE key = :key"
            try:
                row = await self.db.fetch_one(query, values={"key": key})
            except Exception as e:
                if "no such table: cache" in str(e).lower():
                    await ensure_cache_table(self.db)
                    row = await self.db.fetch_one(query, values={"key": key})
                else:
                    raise
            if row and row["expires_at"] > time.time():
                return json.loads(row["value"])
            return default

    async def set(self, key, value, ttl=None):
        async with self.lock:
            expires_at = time.time() + ttl if ttl is not None else time.time() + 315360000
            query = """
                INSERT INTO cache (key, value, expires_at)
                VALUES (:key, :value, :expires_at)
                ON CONFLICT(key) DO UPDATE SET value = :value, expires_at = :expires_at
            """
            try:
                await self.db.execute(query, values={"key": key, "value": json.dumps(value), "expires_at": expires_at})
            except Exception as e:
                if "no such table: cache" in str(e).lower():
                    await ensure_cache_table(self.db)
                    await self.db.execute(query, values={"key": key, "value": json.dumps(value), "expires_at": expires_at})
                else:
                    raise

async def cleanup_cache(db=None):
    db_conn = db or database
    query = "DELETE FROM cache WHERE expires_at < :current_time"
    try:
        await db_conn.execute(query, values={"current_time": time.time()})
    except Exception as e:
        if "no such table: cache" in str(e).lower():
            await ensure_cache_table(db_conn)
        else:
            raise

async def background_cache_cleanup():
    while True:
        await asyncio.sleep(3600)
        try:
            await cleanup_cache()
            logger.info("Periodic database cache cleanup completed.")
        except Exception as e:
            logger.error(f"Error during periodic cache cleanup: {e}")

async def execute_with_retry(query, values=None, retries=5, db=None):
    db_conn = db or database
    for attempt in range(retries):
        try:
            return await db_conn.execute(query, values=values)
        except Exception as e:
            if "database is locked" in str(e).lower():
                await asyncio.sleep(0.2 * (attempt + 1))
            else:
                raise e
    raise Exception(f"Failed after {retries} retries: database is locked.")
