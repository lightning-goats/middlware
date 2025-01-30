# nostr_signing.py

import json
import time
import hashlib
from typing import Optional, List
from ecdsa import SigningKey, SECP256k1

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
    sk = SigningKey.from_string(bytes.fromhex(private_key_hex), curve=SECP256k1)
    signature = sk.sign_deterministic(event_hash)
    return signature.hex()

def update_event_with_id_and_sig(event: dict, event_hash: bytes, signature_hex: str) -> dict:
    """
    Populate 'id' and 'sig' fields using the computed hash and signature.
    """
    event["id"] = event_hash.hex()
    event["sig"] = signature_hex
    return event

async def sign_event(event: dict, private_key_hex: str) -> dict:
    """
    High-level convenience function: remove existing id/sig,
    serialize, hash, sign, then update event with 'id' & 'sig'.
    """
    unsigned_event = remove_id_and_sig(event)
    serialized = serialize_event(unsigned_event)
    event_hash = compute_event_hash(serialized)
    signature_hex = sign_event_hash(event_hash, private_key_hex)
    return update_event_with_id_and_sig(event, event_hash, signature_hex)


##########################
# LNURL Zap (NIP-57) Logic
##########################

def build_zap_event(
    msat_amount: int,
    zapper_pubkey: str,
    zapped_pubkey: str,
    note_id: Optional[str] = None,
    relays: Optional[List[str]] = None,
    content: str = "LNURL Zap"
) -> dict:
    """
    Constructs a *kind=9734* NIP-57 Zap event with appropriate tags:
      ["relays", ...],
      ["amount", "<msats>"],
      ["p", zapped_pubkey],
    optionally:
      ["e", note_id, relay_url, "root"] for a specific note zap.

    :param msat_amount: Amount in millisats
    :param zapper_pubkey: The pubkey of the user doing the zap (should match your private key)
    :param zapped_pubkey: The pubkey of the user receiving the zap
    :param note_id: (Optional) if zapping a specific note
    :param relays: (Optional) list of relay URLs
    :param content: (Optional) content/message of the zap event
    :return: An *unsigned* (no 'id', no 'sig') Nostr event (dict)
    """
    if not relays:
        relays = [
            "wss://primal.net",
            "wss://relay.damus.io",
            "wss://relay.nostr.band/"
        ]

    # Basic set of NIP-57 zap tags
    tags = [
        ["relays", *relays],
        ["amount", str(msat_amount)],
        ["p", zapped_pubkey]
    ]

    # If referencing a specific note
    if note_id:
        # "root" marker is typical if zapping an original post
        tags.append(["e", note_id, relays[0], "root"])

    # Build the partial event
    event = {
        "kind": 9734,
        "content": content,
        "created_at": int(time.time()),
        "tags": tags,
        # The pubkey who is *sending* the zap
        "pubkey": zapper_pubkey,
    }

    # We do NOT add 'id' or 'sig' here. That's done after signing.
    return event

async def sign_zap_event(
    msat_amount: int,
    zapper_pubkey: str,
    zapped_pubkey: str,
    private_key_hex: str,
    note_id: Optional[str] = None,
    relays: Optional[List[str]] = None,
    content: str = "LNURL Zap"
) -> dict:
    """
    Builds and *signs* a NIP-57 LNURL Zap event in one step.
    Returns the fully-signed event (including 'id' & 'sig').

    Example usage:
        event = await sign_zap_event(
            msat_amount=1234,
            zapper_pubkey="YOUR_PUBLIC_KEY_HEX",
            zapped_pubkey="TARGET_PUBLIC_KEY_HEX",
            private_key_hex=YOUR_PRIVATE_KEY,
            note_id="id-of-note-if-zapping-specific-post",
            relays=["wss://relay.damus.io"],
            content="Great post!"
        )
    """
    # 1. Build an unsigned zap event
    unsigned_event = build_zap_event(
        msat_amount,
        zapper_pubkey,
        zapped_pubkey,
        note_id=note_id,
        relays=relays,
        content=content
    )
    # 2. Sign the event
    signed = await sign_event(unsigned_event, private_key_hex)
    return signed
