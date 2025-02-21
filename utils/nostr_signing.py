import time
from typing import Dict, Any, Optional, List, Set
import json
import hashlib
from ecdsa import SigningKey, VerifyingKey, SECP256k1
from ecdsa.util import sigdecode_string, sigencode_string_canonize
import logging
from enum import IntEnum

logger = logging.getLogger(__name__)

class NostrKind(IntEnum):
    """Complete list of standardized Nostr event kinds"""
    METADATA = 0
    TEXT_NOTE = 1
    RECOMMEND_RELAY = 2
    CONTACTS = 3
    ENCRYPTED_DM = 4
    DELETE = 5
    REPOST = 6
    REACTION = 7
    ZAP_REQUEST = 9734
    ZAP_RECEIPT = 9735
    MUTE_LIST = 10000
    PIN_LIST = 10001
    RELAY_LIST = 10002
    RELAY_LIST_METADATA = 10002  # NIP-65 relay list metadata
    WALLET_INFO = 13194
    CLIENT_AUTH = 22242
    WALLET_REQUEST = 23194
    WALLET_RESPONSE = 23195
    NOSTR_CONNECT = 24133

# NIP-01: Basic event structure
REQUIRED_EVENT_FIELDS = {'id', 'pubkey', 'created_at', 'kind', 'tags', 'content', 'sig'}

# NIP-57: Lightning Zaps with NIP-65 compliant relay format
# Update DEFAULT_RELAYS to be a simple list since nak doesn't handle read/write preferences
DEFAULT_RELAYS = [
    "wss://relay.damus.io",
    "wss://nos.lol",
    "wss://relay.nostr.band"
]

# NIP-65: Relay List Metadata
VALID_RELAY_URL_SCHEMES = {'ws', 'wss'}
VALID_RELAY_TAG_MARKERS = {'read', 'write'}

class NostrSigningError(Exception):
    """Base exception for Nostr signing errors"""
    pass

def derive_public_key(private_key_hex: str) -> str:
    """Derive the public key from a private key."""
    try:
        sk = SigningKey.from_string(bytes.fromhex(private_key_hex), curve=SECP256k1)
        return sk.get_verifying_key().to_string("compressed").hex()
    except Exception as e:
        raise NostrSigningError(f"Failed to derive public key: {e}")

def verify_key_pair(private_key_hex: str, expected_pubkey: str) -> bool:
    """Verify that a private key corresponds to an expected public key."""
    try:
        derived_pubkey = derive_public_key(private_key_hex)
        return derived_pubkey == expected_pubkey
    except Exception as e:
        logger.error(f"Key pair verification failed: {e}")
        return False

def verify_event_signature(event: dict) -> bool:
    """Verify the signature of a Nostr event."""
    try:
        pubkey = event.get("pubkey")
        sig = event.get("sig")
        if not pubkey or not sig:
            return False

        event_hash = bytes.fromhex(event["id"])
        signature = bytes.fromhex(sig)
        vk = VerifyingKey.from_string(bytes.fromhex(pubkey), curve=SECP256k1)
        
        return vk.verify(signature, event_hash, sigdecode=sigdecode_string)
    except Exception as e:
        logger.error(f"Signature verification failed: {e}")
        return False

##########################
# Basic Nostr Signing API
##########################

def remove_id_and_sig(event: dict) -> dict:
    """
    Remove 'id' and 'sig' from the event so it can be signed from scratch.
    """
    return {k: v for k, v in event.items() if k not in ["id", "sig"]}

def serialize_event(event: dict) -> bytes:
    """
    Serialize a Nostr event for signing:
    [0, pubkey, created_at, kind, tags, content]
    """
    return json.dumps(
        [
            0,
            event["pubkey"],
            event["created_at"],
            event["kind"],
            event.get("tags", []),
            event.get("content", "")
        ],
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")

def compute_event_hash(serialized_event: bytes) -> bytes:
    """
    Compute the SHA-256 hash of the serialized event.
    """
    return hashlib.sha256(serialized_event).digest()

def sign_event_hash(event_hash: bytes, private_key_hex: str) -> str:
    """
    Sign the event hash with a Nostr private key (hex).
    Uses deterministic ECDSA (RFC6979) via ecdsa library.
    """
    try:
        sk = SigningKey.from_string(bytes.fromhex(private_key_hex), curve=SECP256k1)
        signature = sk.sign_deterministic(
            event_hash,
            sigencode=sigencode_string_canonize
        )
        return signature.hex()
    except Exception as e:
        raise NostrSigningError(f"Failed to sign event hash: {e}")

def update_event_with_id_and_sig(event: dict, event_hash: bytes, signature_hex: str) -> dict:
    """
    Populate 'id' and 'sig' fields using the computed hash and signature.
    """
    event["id"] = event_hash.hex()
    event["sig"] = signature_hex
    return event

def verify_event_structure(event: Dict[str, Any]) -> bool:
    """Verify event structure according to NIP-01"""
    try:
        # Check required fields exist
        if not all(field in event for field in REQUIRED_EVENT_FIELDS):
            return False

        # Validate field types
        if not isinstance(event['created_at'], int):
            return False
        if not isinstance(event['kind'], int):
            return False
        if not isinstance(event['tags'], list):
            return False
        if not isinstance(event['content'], str):
            return False
        if not all(isinstance(tag, list) for tag in event['tags']):
            return False

        # Validate string fields are hex
        for field in ['id', 'pubkey', 'sig']:
            try:
                bytes.fromhex(event[field])
            except ValueError:
                return False

        return True
    except Exception:
        return False

async def sign_event(event: Dict[str, Any], private_key_hex: str) -> Dict[str, Any]:
    """
    Sign a Nostr event according to NIP-01 specification.
    """
    try:
        # Remove existing id and signature if present
        unsigned_event = remove_id_and_sig(event)
        
        # Serialize event
        serialized = serialize_event(unsigned_event)
        event_hash = compute_event_hash(serialized)
        
        # Sign event
        signature_hex = sign_event_hash(event_hash, private_key_hex)
        signed_event = update_event_with_id_and_sig(event, event_hash, signature_hex)
        
        # Verify structure and signature
        if not verify_event_structure(signed_event):
            raise NostrSigningError("Invalid event structure")
        if not verify_event_signature(signed_event):
            raise NostrSigningError("Invalid event signature")
            
        return signed_event
    except Exception as e:
        raise NostrSigningError(f"Event signing failed: {e}")

##########################
# LNURL Zap (NIP-57) Logic
##########################

def build_zap_request(
    msat_amount: int,
    zapper_pubkey: str,
    zapped_pubkey: str,
    note_id: Optional[str] = None,
    relays: Optional[List[str]] = None,  # Simple list for nak compatibility
    content: str = "",
    lnurl_callback: Optional[str] = None
) -> Dict[str, Any]:
    """
    Build a NIP-57 compliant zap request event.
    """
    if msat_amount <= 0:
        raise ValueError("Amount must be positive")
    
    if not relays:
        relays = DEFAULT_RELAYS.copy()
    
    tags = [
        ["p", zapped_pubkey],  # Recipient
        ["amount", str(msat_amount)],
        ["relays", *relays]  # Use relays directly as list
    ]

    # Optional note reference
    if note_id:
        tags.append(["e", note_id, relays[0], "root"])
    
    # Optional LNURL callback
    if lnurl_callback:
        tags.append(["lnurl", lnurl_callback])

    return {
        "kind": NostrKind.ZAP_REQUEST,
        "created_at": int(time.time()),
        "content": content,
        "tags": tags,
        "pubkey": zapper_pubkey
    }

def build_zap_receipt(
    payment_hash: str,
    bolt11: str,
    zapper_pubkey: str,
    zapped_pubkey: str,
    amount: int,
    note_id: Optional[str] = None,
    content: str = ""
) -> Dict[str, Any]:
    """
    Build a NIP-57 compliant zap receipt event.
    """
    tags = [
        ["p", zapped_pubkey],
        ["bolt11", bolt11],
        ["description", content],
        ["preimage", payment_hash]
    ]

    if note_id:
        tags.append(["e", note_id])

    return {
        "kind": NostrKind.ZAP_RECEIPT,
        "created_at": int(time.time()),
        "content": "",  # Content should be empty per NIP-57
        "tags": tags,
        "pubkey": zapper_pubkey
    }

async def sign_zap_event(
    msat_amount: int,
    zapper_pubkey: str,
    zapped_pubkey: str,
    private_key_hex: str,
    note_id: Optional[str] = None,
    relays: Optional[List[str]] = None,
    content: str = ""
) -> dict:
    """
    Creates and signs a NIP-57 Zap Request event.
    
    Validates the key pair and creates a properly signed zap request
    that can be used in an LNURL-pay request.
    """
    # Verify the key pair
    if not verify_key_pair(private_key_hex, zapper_pubkey):
        raise NostrSigningError("Private key does not match zapper pubkey")
        
    try:
        # Build unsigned zap request
        unsigned_event = build_zap_request(
            msat_amount=msat_amount,
            zapper_pubkey=zapper_pubkey,
            zapped_pubkey=zapped_pubkey,
            note_id=note_id,
            relays=relays,
            content=content
        )
        
        # Sign the event
        signed = await sign_event(unsigned_event, private_key_hex)
        return signed
    except Exception as e:
        raise NostrSigningError(f"Failed to create zap event: {e}")

##########################
# NIP-65: Relay List Logic
##########################

def validate_relay_url(url: str) -> bool:
    """Validate relay URL according to NIP-65"""
    try:
        parsed = urlparse(url)
        return (
            parsed.scheme in VALID_RELAY_URL_SCHEMES and
            parsed.netloc and
            len(url) <= 2048  # reasonable URL length limit
        )
    except Exception:
        return False


