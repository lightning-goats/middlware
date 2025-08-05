import asyncio
import json
import logging
import re
from typing import Optional, Dict, Any, List, Tuple
import httpx
import subprocess

from subprocess import TimeoutExpired, CompletedProcess
from .helpers import DEFAULT_RELAYS

# Logging Configuration
logger = logging.getLogger(__name__)

# Semaphore for controlling subprocess concurrency
subprocess_semaphore = asyncio.Semaphore(5)  # Adjust the limit as needed

# Utility Functions
async def run_subprocess(command: list, timeout: int = 30) -> CompletedProcess:
    """
    Run a subprocess asynchronously with a timeout.
    """
    proc = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return CompletedProcess(args=command, returncode=proc.returncode, stdout=stdout, stderr=stderr)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        raise TimeoutExpired(cmd=command, timeout=timeout)

# Verifier Class
class Verifier:
    @staticmethod
    async def verify_nip05(nip05: str, expected_pubkey: str) -> bool:
        """
        Verify a NIP-05 identifier using the _well-known/nostr.json file.
        """
        if not nip05:
            logger.error("No NIP-05 identifier provided.")
            return False

        if '@' not in nip05:
            logger.error(f"Invalid NIP-05 identifier format: {nip05}")
            return False

        username, domain = nip05.split('@', 1)
        url = f"https://{domain}/.well-known/nostr.json?name={username}"
        logger.debug(f"Fetching NIP-05 verification file from: {url}")

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=10)
                response.raise_for_status()
                data = response.json()

            pubkeys = data.get("names", {}).get(username)
            if pubkeys and pubkeys == expected_pubkey:
                logger.info(f"NIP-05 verification succeeded for {nip05} -> {expected_pubkey}")
                return True
            else:
                logger.error(f"NIP-05 verification failed: {nip05} does not match {expected_pubkey}")
                return False

        except httpx.RequestError as e:
            logger.error(f"Failed to verify NIP-05 identifier: {e}")
        except json.JSONDecodeError:
            logger.error("Invalid JSON response from NIP-05 endpoint.")
        except Exception as e:
            logger.error(f"Unexpected error during NIP-05 verification: {e}")

        return False

    @staticmethod
    async def verify_lud16(lud16: str) -> bool:
        """
        Verify a lud16 (Lightning Address) format and reachability.
        """
        if not lud16:
            logger.error("No lud16 address provided.")
            return False

        lud16 = lud16.strip()
        logger.debug(f"Verifying lud16: {lud16}")

        # Validate lud16 format
        lud16_regex = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        if not re.match(lud16_regex, lud16):
            logger.error(f"Invalid lud16 format: {lud16}")
            return False

        # Attempt to fetch the metadata associated with the lud16
        try:
            username, domain = lud16.split('@')
            url = f"https://{domain}/.well-known/lnurlp/{username}"
            logger.debug(f"Fetching lud16 metadata from: {url}")

            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=10)
                response.raise_for_status()
                metadata = response.json()

            # Check required fields in metadata
            if "callback" in metadata and metadata.get("status") != "ERROR":
                logger.info(f"lud16 address {lud16} is valid and reachable.")
                return True
            else:
                logger.error(f"Invalid or unreachable lud16 metadata: {metadata}")

        except httpx.RequestError as e:
            logger.error(f"Failed to verify lud16: {e}")
        except json.JSONDecodeError:
            logger.error("Invalid JSON in lud16 response.")
        except Exception as e:
            logger.error(f"Unexpected error during lud16 verification: {e}")

        return False

# MetadataFetcher Class
def get_best_relays(relays: Optional[List[str]] = None) -> List[str]:
    """Get the best 3 relays from provided list or defaults."""
    if relays and len(relays) > 0:
        # Take up to first 3 user relays
        return relays[:3]
    return DEFAULT_RELAYS

class MetadataFetcher:
    def __init__(self):
        self.subprocess_semaphore = subprocess_semaphore

    async def lookup_metadata(self, pubkey: str, relays: Optional[List[str]] = None) -> Optional[Dict[str, Optional[str]]]:
        """
        Asynchronously look up metadata for a given pubkey.
        
        Args:
            pubkey: The public key to look up
            relays: Optional list of relay URLs to use. Falls back to defaults if None.
        """
        selected_relays = get_best_relays(relays)
        logger.debug(f"Looking up metadata for pubkey: {pubkey} using relays: {selected_relays}")
        metadata_command = [
            "/usr/local/bin/nak",
            "req",
            "-k",
            "0",  # Explicitly fetch kind: 0 (metadata events)
            "-a",
            pubkey
        ]
        metadata_command.extend(selected_relays)

        logger.debug(f"Executing command: {' '.join(metadata_command)}")

        async with self.subprocess_semaphore:
            try:
                result = await run_subprocess(metadata_command, timeout=15)
                if result.returncode != 0:
                    logger.error(f"Error fetching metadata: {result.stderr.decode().strip()}")
                    return None

                most_recent_metadata = None

                for meta_line in result.stdout.decode().splitlines():
                    try:
                        meta_data = json.loads(meta_line)
                        if meta_data.get("kind") == 0:  # Ensure it's a metadata event
                            content = json.loads(meta_data.get("content", '{}'))
                            created_at = meta_data.get('created_at', 0)
                            
                            if content.get('lud16'):
                                if (most_recent_metadata is None or created_at > most_recent_metadata['created_at']):
                                    most_recent_metadata = {
                                        'content': content,
                                        'created_at': created_at
                                    }
                    except json.JSONDecodeError as e:
                        logger.error(f"Error parsing metadata line: {e}")

                if most_recent_metadata:
                    content = most_recent_metadata['content']
                    return {
                        'nip05': content.get('nip05', None),
                        'lud16': content.get('lud16', None),
                        'display_name': content.get('display_name', content.get('name', 'Anon')),
                        'picture': content.get('picture', None)  # Add picture field
                    }
                else:
                    logger.warning(f"No valid metadata found for pubkey: {pubkey}")

            except TimeoutExpired:
                logger.error("Timeout while fetching metadata.")
            except Exception as e:
                logger.error(f"Unexpected error during metadata lookup: {e}")

            return None

    async def lookup_metadata_with_stored_relays(self, pubkey: str, stored_relays: Optional[List[str]] = None) -> Optional[Dict[str, Optional[str]]]:
        """
        Look up metadata using stored relays first, then fall back to user's 10002, then DEFAULT_RELAYS
        """
        # Try stored relays first if available
        if stored_relays:
            metadata = await self.lookup_metadata(pubkey, stored_relays)
            if metadata:
                return metadata

        # Try user's relay list from 10002
        user_relays = await lookup_relay_list(pubkey)
        if user_relays:
            metadata = await self.lookup_metadata(pubkey, user_relays)
            if metadata:
                return metadata

        # Fall back to DEFAULT_RELAYS
        return await self.lookup_metadata(pubkey, DEFAULT_RELAYS)

# Encapsulated nprofile Generation
async def generate_nprofile(pubkey: str) -> Optional[str]:
    """
    Generate an nprofile using the nak command.
    """
    nprofile_command = ['/usr/local/bin/nak', 'encode', 'nprofile', pubkey]
    async with subprocess_semaphore:
        try:
            result = await run_subprocess(nprofile_command, timeout=10)
            if result.returncode != 0:
                logger.error(f"Error generating nprofile: {result.stderr.decode().strip()}")
                return None
            return result.stdout.decode().strip()
        except asyncio.TimeoutError as e:
            logger.error(f"Timeout generating nprofile for pubkey {pubkey}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error generating nprofile: {e}")
        return None

async def check_cyberherd_tag(event_id: str, relays: Optional[List[str]] = None) -> bool:
    """
    Check if the event identified by `event_id` has a 'CyberHerd' tag.

    Args:
        event_id (str): The ID of the event to check.
        relays (Optional[List[str]]): List of relay URLs. Defaults to DEFAULT_RELAYS.

    Returns:
        bool: True if the event has a 'CyberHerd' tag, False otherwise.
    """
    selected_relays = get_best_relays(relays)
    nak_command = ["nak", "req", "-i", event_id, *selected_relays]
    
    try:
        result = subprocess.run(nak_command, capture_output=True, text=True, check=True)
        event_data = json.loads(result.stdout)
        logger.debug(f"nak command output: {event_data}")

        # Ensure the `tags` field exists and is a list of lists
        tags = event_data.get("tags", [])
        if isinstance(tags, list) and all(isinstance(tag, list) and len(tag) >= 2 for tag in tags):
            # Check if any tag has "t" as the first element and "CyberHerd" (case insensitive) as the second
            for tag in tags:
                if tag[0] == "t" and tag[1].lower() == "cyberherd":
                    return True

        # Log unexpected format or absence of the tag
        logger.info(f"No 'CyberHerd' tag found for event_id: {event_id}")
        return False

    except subprocess.CalledProcessError as e:
        logger.error(f"Error running nak command: {e.stderr}")
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON output from nak command: {e}")
    except Exception as e:
        logger.error(f"Unexpected error while checking CyberHerd tag: {e}")

    return False

def extract_relays_from_10002_tags(tags: list) -> list:
    """Extract relay URLs specifically from Kind 10002 event tags."""
    relays = []
    if not tags:
        return relays
        
    # For Kind 10002, each relay is in a tag starting with 'r'
    # Format: ["r", "wss://relay.example.com"]
    for tag in tags:
        if not tag or len(tag) < 2:
            continue
            
        if tag[0] == 'r':  # Kind 10002 uses 'r' tags for relays
            relay_url = tag[1]
            if isinstance(relay_url, str) and relay_url.startswith(('ws://', 'wss://')):
                relays.append(relay_url)
            
    return relays  # Return raw relay URLs without sanitizing

async def lookup_relay_list(pubkey: str, relays: Optional[List[str]] = None) -> List[str]:
    """
    Look up Kind 10002 (Relay List Metadata) events for a given pubkey and extract relay URLs.
    Falls back to cached results if available.
    """
    if not pubkey:
        return DEFAULT_RELAYS

    selected_relays = get_best_relays(relays)
    logger.debug(f"Looking up kind 10002 for pubkey {pubkey} using relays: {selected_relays}")

    try:
        # First try the nak command for kind 10002
        result = await run_subprocess([
            "/usr/local/bin/nak",
            "req",
            "-k",
            "10002",
            "-a",
            pubkey,
            *selected_relays
        ], timeout=10)

        if result.returncode != 0:
            logger.warning(f"Failed to fetch relay list for {pubkey}, falling back to defaults")
            return DEFAULT_RELAYS.copy()

        most_recent = None
        most_recent_time = 0

        for line in result.stdout.decode().splitlines():
            try:
                event = json.loads(line)
                if (event.get('kind') == 10002 and 
                    event.get('pubkey') == pubkey and 
                    event.get('created_at', 0) > most_recent_time):
                    most_recent = event
                    most_recent_time = event['created_at']
            except json.JSONDecodeError:
                continue

        if most_recent:
            user_relays = []
            for tag in most_recent.get('tags', []):
                if len(tag) >= 2 and tag[0] == 'r':
                    relay_url = tag[1]
                    if isinstance(relay_url, str) and relay_url.startswith(('wss://', 'ws://')):
                        user_relays.append(relay_url)
            
            if user_relays:
                logger.info(f"Found {len(user_relays)} relays for {pubkey}")
                return user_relays

    except Exception as e:
        logger.error(f"Error looking up relays for {pubkey}: {e}")

    logger.debug(f"No valid relays found for {pubkey}, using defaults")
    return DEFAULT_RELAYS
