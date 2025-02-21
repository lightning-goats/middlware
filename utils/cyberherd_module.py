import asyncio
import json
import logging
import re
from typing import Optional, Dict, Any, List, Set
import httpx
import subprocess
from subprocess import TimeoutExpired, CompletedProcess
import tenacity
import dns.resolver
import dns.exception
from urllib.parse import urlparse, urljoin
import idna
from binascii import unhexlify
from dataclasses import dataclass
from enum import IntEnum

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

# Add validation utilities
def is_valid_pubkey(pubkey: str) -> bool:
    """Validate hex pubkey format per NIP-01."""
    if not isinstance(pubkey, str):
        return False
    
    # Strip npub prefix if present (NIP-19)
    if pubkey.startswith('npub'):
        # In production, you'd decode the bech32 here
        return False
        
    try:
        # Must be 64 characters of hex
        if len(pubkey) != 64:
            return False
        unhexlify(pubkey)
        return True
    except:
        return False

def is_valid_metadata_content(content: Dict) -> bool:
    """Validate metadata content format per NIP-01."""
    if not isinstance(content, dict):
        return False

    # Required fields must be strings if present
    string_fields = ['name', 'display_name', 'about', 'picture', 'banner', 
                    'nip05', 'lud06', 'lud16']
    
    for field in string_fields:
        if field in content and not isinstance(content[field], str):
            return False
            
    # Website must be valid URL if present
    if 'website' in content:
        try:
            parsed = urlparse(content['website'])
            if not all([parsed.scheme, parsed.netloc]):
                return False
        except:
            return False
            
    return True

def parse_nostr_uri(uri: str) -> Optional[Dict[str, str]]:
    """Parse nostr: URI scheme per NIP-21."""
    if not uri.startswith('nostr:'):
        return None
    
    try:
        parsed = urlparse(uri)
        if parsed.scheme != 'nostr':
            return None
            
        # Handle different entity types
        entity = parsed.path
        if entity.startswith('npub1'):
            return {'type': 'pubkey', 'data': entity}
        elif entity.startswith('note1'):
            return {'type': 'note', 'data': entity}
        elif entity.startswith('nprofile1'):
            return {'type': 'profile', 'data': entity}
    except:
        return None
    
    return None

async def resolve_domain(domain: str) -> bool:
    """
    Resolve domain using dnspython.
    Returns True if domain resolves successfully.
    """
    try:
        resolver = dns.resolver.Resolver()
        # Try both A and AAAA records
        try:
            resolver.resolve(domain, 'A')
            return True
        except dns.resolver.NoAnswer:
            try:
                resolver.resolve(domain, 'AAAA')
                return True
            except dns.resolver.NoAnswer:
                return False
    except (dns.resolver.NXDOMAIN, dns.resolver.NoNameservers, 
            dns.exception.DNSException) as e:
        logger.error(f"DNS resolution failed for {domain}: {e}")
        return False

# Verifier Class
class Verifier:
    @staticmethod
    async def verify_nip05(nip05: str, expected_pubkey: str) -> bool:
        """
        Verify a NIP-05 identifier using the _well-known/nostr.json file.
        Includes DNS resolution and proper URL handling.
        """
        if not nip05 or not expected_pubkey:
            logger.error("Missing NIP-05 identifier or pubkey")
            return False

        try:
            # Parse and normalize the NIP-05 identifier
            nip05 = nip05.lower().strip()
            if '@' not in nip05:
                logger.error(f"Invalid NIP-05 identifier format: {nip05}")
                return False

            username, domain = nip05.split('@', 1)
            
            # Handle IDN domains
            try:
                ascii_domain = idna.encode(domain).decode('ascii')
            except Exception as e:
                logger.error(f"Invalid domain name encoding: {e}")
                return False

            # Verify domain resolves using dnspython
            if not await resolve_domain(ascii_domain):
                logger.error(f"Domain {ascii_domain} does not resolve")
                return False

            # Build and validate URL
            for scheme in ['https', 'http']:
                base_url = f"{scheme}://{ascii_domain}"
                try:
                    parsed = urlparse(base_url)
                    if not all([parsed.scheme, parsed.netloc]):
                        continue
                    
                    url = urljoin(base_url, '/.well-known/nostr.json')
                    params = {'name': username}

                    async with httpx.AsyncClient(follow_redirects=True) as client:
                        response = await client.get(url, params=params, timeout=10)
                        response.raise_for_status()
                        
                        try:
                            data = response.json()
                        except json.JSONDecodeError:
                            logger.error("Invalid JSON response from NIP-05 endpoint")
                            continue

                        names = data.get("names", {})
                        if not isinstance(names, dict):
                            logger.error("Invalid 'names' field in NIP-05 response")
                            continue

                        pubkey = names.get(username)
                        if not pubkey:
                            logger.error(f"Username {username} not found in NIP-05 response")
                            continue

                        if pubkey == expected_pubkey:
                            logger.info(f"NIP-05 verification succeeded for {nip05}")
                            return True
                        else:
                            logger.error(f"Pubkey mismatch: expected {expected_pubkey}, got {pubkey}")

                except httpx.RequestError as e:
                    logger.error(f"HTTP request failed: {e}")
                    continue

            return False

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

# Updated MetadataFetcher Class
class MetadataFetcher:
    def __init__(self):
        self.subprocess_semaphore = subprocess_semaphore
        self.default_relays: Set[str] = {
            "wss://relay.damus.io",
            "wss://relay.primal.net",
            "wss://nos.lol",
            "wss://relay.nostr.band"
        }

    @tenacity.retry(
        wait=tenacity.wait_fixed(1),
        stop=tenacity.stop_after_attempt(3),
        retry=tenacity.retry_if_exception_type(TimeoutExpired),
        reraise=True
    )
    async def _lookup_metadata_attempt(self, pubkey: str, metadata_command: list) -> CompletedProcess:
        """
        A helper method that performs a single attempt at fetching metadata.
        This method will be retried by tenacity if a TimeoutExpired exception is raised.
        """
        async with self.subprocess_semaphore:
            return await run_subprocess(metadata_command, timeout=15)

    async def get_relay_list(self, pubkey: str) -> Set[str]:
        """Get relay list per NIP-65"""
        relay_command = [
            "/usr/local/bin/nak",
            "req",
            "-k",
            str(NostrKind.RELAY_LIST),
            "-a",
            pubkey,
            *self.default_relays
        ]
        
        try:
            result = await self._lookup_metadata_attempt(pubkey, relay_command)
            if result.returncode != 0:
                return self.default_relays

            relays: Set[str] = set()
            if result.stdout:
                events = [json.loads(line) for line in result.stdout.decode().splitlines()]
                # Get most recent NIP-65 event
                valid_events = [NostrEvent.from_dict(e) for e in events]
                if not valid_events:
                    return self.default_relays
                    
                latest_event = max(valid_events, key=lambda x: x.created_at)
                
                # Extract relay URLs from 'r' tags
                for tag in latest_event.tags:
                    if len(tag) >= 2 and tag[0] == 'r':
                        relay_url = tag[1]
                        try:
                            parsed = urlparse(relay_url)
                            if parsed.scheme in ['ws', 'wss']:
                                relays.add(relay_url)
                        except Exception:
                            continue

            return relays if relays else self.default_relays
        except Exception as e:
            logger.error(f"Error fetching relay list: {e}")
            return self.default_relays

    async def lookup_metadata(self, pubkey: str) -> Optional[Dict[str, Optional[str]]]:
        """Lookup metadata per NIP-01"""
        if not is_valid_pubkey(pubkey):
            return None

        metadata_command = [
            "/usr/local/bin/nak",
            "req",
            "-k",
            str(NostrKind.METADATA),
            "-a",
            pubkey
        ]

        try:
            # Get user's preferred relays first
            user_relays = await self.get_relay_list(pubkey)
            metadata_command.extend(user_relays)

            result = await self._lookup_metadata_attempt(pubkey, metadata_command)
            if result.returncode != 0:
                return None

            events = []
            for line in result.stdout.decode().splitlines():
                try:
                    event_dict = json.loads(line)
                    if event := NostrEvent.from_dict(event_dict):
                        if event.kind == NostrKind.METADATA:
                            events.append(event)
                except Exception:
                    continue

            if not events:
                return None

            # Get most recent valid metadata
            latest_event = max(events, key=lambda x: x.created_at)
            try:
                content = json.loads(latest_event.content)
                if not is_valid_metadata_content(content):
                    return None
                    
                return {
                    'nip05': content.get('nip05'),
                    'lud16': content.get('lud16'),
                    'display_name': content.get('display_name') or content.get('name', 'Anon'),
                    'picture': content.get('picture')
                }
            except json.JSONDecodeError:
                return None

        except Exception as e:
            logger.error(f"Error in metadata lookup: {e}")
            return None

# Encapsulated nprofile Generation
async def generate_nprofile(pubkey: str) -> Optional[str]:
    """
    Generate an nprofile using the nak command.
    
    Args:
        pubkey: The public key to encode
        
    Returns:
        Optional[str]: The nprofile string or None if generation fails
    """
    if not is_valid_pubkey(pubkey):
        logger.error(f"Invalid pubkey format: {pubkey}")
        return None

    nprofile_command = ['/usr/local/bin/nak', 'encode', 'nprofile', pubkey]
    async with subprocess_semaphore:
        try:
            result = await run_subprocess(nprofile_command, timeout=10)
            if result.returncode != 0:
                logger.error(f"Error generating nprofile: {result.stderr.decode().strip()}")
                return None
            
            nprofile = result.stdout.decode().strip()
            if not nprofile.startswith('nprofile'):
                logger.error(f"Invalid nprofile format generated: {nprofile}")
                return None
                
            return nprofile
        except asyncio.TimeoutError as e:
            logger.error(f"Timeout generating nprofile for pubkey {pubkey}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error generating nprofile: {e}")
        return None

async def check_cyberherd_tag(event_id: str, relay_url: str = "wss://relay.primal.net") -> bool:
    """
    Check if an event has a 'CyberHerd' tag.
    
    Args:
        event_id: The event ID to check
        relay_url: The relay URL to query (default: wss://relay.primal.net)
        
    Returns:
        bool: True if the event has a CyberHerd tag, False otherwise
    """
    if not event_id or not isinstance(event_id, str):
        logger.error("Invalid event_id provided")
        return False

    nak_command = ["/usr/local/bin/nak", "req", "-i", event_id, relay_url]
    try:
        result = await run_subprocess(nak_command, timeout=15)
        if result.returncode != 0:
            logger.error(f"nak command failed: {result.stderr.decode()}")
            return False

        event_data = json.loads(result.stdout)
        tags = event_data.get("tags", [])
        
        return any(
            len(tag) >= 2 and tag[0] == "t" and tag[1].lower() == "cyberherd"
            for tag in tags
            if isinstance(tag, list)
        )

    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON output from nak command: {e}")
    except Exception as e:
        logger.error(f"Error checking CyberHerd tag: {e}")
    
    return False

class NostrKind(IntEnum):
    """NIP-01 and other NIPs event kinds"""
    METADATA = 0
    TEXT_NOTE = 1
    RECOMMEND_RELAY = 2
    CONTACTS = 3
    ENCRYPTED_DM = 4
    DELETE = 5
    REPOST = 6
    REACTION = 7
    BADGE_AWARD = 8
    CHANNEL_CREATE = 40
    CHANNEL_MESSAGE = 42
    RELAY_LIST = 10002

@dataclass
class NostrEvent:
    """NIP-01 compliant event structure"""
    id: str
    pubkey: str
    created_at: int
    kind: int
    tags: List[List[str]]
    content: str
    sig: str

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Optional['NostrEvent']:
        """Create NostrEvent from dict, validating required fields"""
        try:
            required_fields = ['id', 'pubkey', 'created_at', 'kind', 'tags', 'content', 'sig']
            if not all(field in data for field in required_fields):
                return None
            
            # Validate types
            if not isinstance(data['created_at'], int):
                return None
            if not isinstance(data['kind'], int):
                return None
            if not isinstance(data['tags'], list):
                return None
                
            return cls(**{k: data[k] for k in required_fields})
        except Exception:
            return None

async def decode_nprofile(nprofile: str) -> Optional[str]:
    """Decode NIP-19 nprofile to get pubkey"""
    try:
        decode_command = ['/usr/local/bin/nak', 'decode', nprofile]
        result = await run_subprocess(decode_command, timeout=5)
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout)
        return data.get('pubkey')
    except Exception:
        return None
