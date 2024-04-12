#event_utils.py
import json
import hashlib
from ecdsa import SigningKey, SECP256k1
from typing import Dict

def serialize_event(event):
    return json.dumps(event, sort_keys=True)

def remove_id_and_sig(event: Dict) -> Dict:
    return {k: v for k, v in event.items() if k not in ['id', 'sig']}

def serialize_event(event: Dict) -> bytes:
    return json.dumps([
        0,
        event['pubkey'],
        event['created_at'],
        event['kind'],
        event.get('tags', []),
        event.get('content', '')
    ], separators=(',', ':'), ensure_ascii=False).encode('utf-8')

def compute_event_hash(serialized_event: bytes) -> bytes:
    return hashlib.sha256(serialized_event).digest()

def sign_event_hash(event_hash: bytes, private_key_hex: str) -> str:
    sk = SigningKey.from_string(bytes.fromhex(private_key_hex), curve=SECP256k1)
    signature = sk.sign_deterministic(event_hash)
    return signature.hex()

def update_event_with_id_and_sig(event: Dict, event_hash: bytes, signature_hex: str) -> Dict:
    event['id'] = event_hash.hex()
    event['sig'] = signature_hex
    return event

async def sign_event(event: Dict, private_key_hex: str) -> Dict:
    event_to_sign = remove_id_and_sig(event)
    serialized_event = serialize_event(event_to_sign)
    event_hash = compute_event_hash(serialized_event)
    signature_hex = sign_event_hash(event_hash, private_key_hex)
    signed_event = update_event_with_id_and_sig(event, event_hash, signature_hex)
    return signed_event
