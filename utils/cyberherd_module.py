import asyncio
import json
import logging
import re
from typing import Optional, Dict, Any
import httpx
import subprocess

from subprocess import TimeoutExpired, CompletedProcess

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

        nip05 = nip05.lower().strip()
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
class MetadataFetcher:
    def __init__(self):
        self.subprocess_semaphore = subprocess_semaphore

    async def lookup_metadata(self, pubkey: str) -> Optional[Dict[str, Optional[str]]]:
        """
        Asynchronously look up metadata for a given pubkey.
        """
        logger.debug(f"Looking up metadata for pubkey: {pubkey}")
        metadata_command = [
            "/usr/local/bin/nak",
            "req",
            "-k",
            "0",  # Explicitly fetch kind: 0 (metadata events)
            "-a",
            pubkey,
            "wss://relay.damus.io",
            "wss://relay.primal.net/"
        ]

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
                        'display_name': content.get('display_name', content.get('name', 'Anon'))
                    }
                else:
                    logger.warning(f"No valid metadata found for pubkey: {pubkey}")

            except TimeoutExpired:
                logger.error("Timeout while fetching metadata.")
            except Exception as e:
                logger.error(f"Unexpected error during metadata lookup: {e}")

            return None

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

async def check_cyberherd_tag(event_id: str, relay_url: str = "ws://127.0.0.1:3002/nostrrelay/666") -> bool:
    """
    Check if the event identified by `event_id` has a 'CyberHerd' tag using the nak command.

    Args:
        event_id (str): The ID of the event to check.
        relay_url (str): The relay WebSocket URL. Defaults to localhost.

    Returns:
        bool: True if the event has a 'CyberHerd' tag, False otherwise.
    """
    nak_command = ["nak", "req", "-i", event_id, relay_url]
    try:
        # Run the nak command
        result = subprocess.run(nak_command, capture_output=True, text=True, check=True)
        
        # Parse the JSON output
        event_data = json.loads(result.stdout)

        # Log the full output for debugging purposes
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
