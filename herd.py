import asyncio
from fastapi import FastAPI
import uvicorn
from pynostr.relay_manager import RelayManager
from pynostr.filters import FiltersList, Filters
from pynostr.event import EventKind
from pynostr.utils import get_public_key
import uuid
from datetime import datetime, timezone
from cachetools import TTLCache

app = FastAPI()

# Cache for reposts (public key and ID) with automatic expiration
repost_cache = TTLCache(maxsize=1000, ttl=43200)  # Example: 1000 items, 12 hours TTL

# Retrieve public key
identity = get_public_key('npub1v60thnx0gz0wq3n6xdnq46y069l9x70xgmjp6lprdl6fv0eux6mqgjj4rp')

# Define relays URLs
relay_urls = [
    "wss://relay.primal.net",
    "wss://relay.damus.io",
    "wss://relay.snort.social",
    "wss://nostr.bitcoiner.social",
    "wss://relay.nostriches.org",
    "wss://nostr-pub.wellorder.net",
    "wss://nos.lol",
    "wss://nostr-01.bolt.observer"
]

# Initialize RelayManager
relay_manager = RelayManager(timeout=2)
for url in relay_urls:
    relay_manager.add_relay(url)

# Set up filters for events from the start of the current day
start_of_day = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
start_time = int(start_of_day.timestamp())  # Convert to Unix timestamp
text_note_filter = Filters(since=start_time, authors=[identity.hex()], kinds=[1])
repost_filter = Filters(since=start_time, kinds=[6])
filters = FiltersList([text_note_filter, repost_filter])
subscription_id = uuid.uuid1().hex
relay_manager.add_subscription_on_all_relays(subscription_id, filters)

def filter_events_by_tag(events, tag):
    return [event for event in events if event.kind == 1 and any(t[0] == "t" and t[1] == tag for t in event.tags)]

async def check_for_reposts():
    try:
        all_events = []
        reposts = {}
        processed_event_ids = set()

        while relay_manager.message_pool.has_events():
            event_msg = relay_manager.message_pool.get_event()
            event_data = event_msg.event
            all_events.append(event_data)

            if event_data.kind == 6:
                for tag in event_data.tags:
                    if tag[0] == 'e':
                        reposts.setdefault(tag[1], []).append(event_data)

        filtered_events = filter_events_by_tag(all_events, "cyber-herd")

        for event in filtered_events:
            original_event_id = event.id
            if original_event_id not in processed_event_ids:
                processed_event_ids.add(original_event_id)
                if original_event_id in reposts:
                    for repost_event in reposts[original_event_id]:
                        pubkey = repost_event.pubkey
                        if pubkey not in repost_cache:
                            repost_cache[pubkey] = {'event_id': repost_event.id, 'timestamp': datetime.utcnow()}
                        else:
                            # Update timestamp for existing pubkey entry
                            repost_cache[pubkey]['timestamp'] = datetime.utcnow()

    except Exception as e:
        print(f"Error in check_for_reposts: {e}")
        
def clear_old_cache_entries():
    now = datetime.utcnow()
    keys_to_delete = [key for key, value in repost_cache.items() if now - value['timestamp'] > timedelta(days=1)]
    for key in keys_to_delete:
        del repost_cache[key]

async def repost_check_loop():
    while True:
        await check_for_reposts()
        await asyncio.sleep(30)  # Wait for 30 seconds before the next execution


@app.post("/check-for-reposts")
async def trigger_check_for_reposts():
    print("Triggering check_for_reposts")
    task = asyncio.create_task(check_for_reposts())
    task.add_done_callback(task_callback)
    return {"message": "Repost check initiated"}

@app.post("/clear-cache")
async def clear_cache():
    clear_old_cache_entries()
    return {"message": "Cache cleanup completed"}


@app.get("/get-reposts")
async def get_reposts():
    return dict(repost_cache)

def task_callback(task):
    try:
        task.result()
    except Exception as e:
        print(f"Error in background task: {e}")

@app.on_event("startup")
async def startup_event():
    await relay_manager.prepare_relays()
    clear_old_cache_entries()
    asyncio.create_task(repost_check_loop())  # Start the repost check loop

@app.on_event("shutdown")
async def shutdown_event():
    relay_manager.close_all_relay_connections()

if __name__ == "__main__":
    try:
        uvicorn.run(app, host="0.0.0.0", port=8000)
    except KeyboardInterrupt:
        print("Application interrupted by user, shutting down.")

