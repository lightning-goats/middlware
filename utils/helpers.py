import logging
from typing import List, Set, Tuple, Union
from typing import Optional  # Import separately to ensure it's available

# Setup logger for helper functions
logger = logging.getLogger(__name__)

# Centralized relay configuration - single source of truth
DEFAULT_RELAYS = [
    "wss://relay.primal.net/",
    "wss://relay.damus.io/",
    "wss://nostr.oxtr.dev",
    "wss://nostr-pub.wellorder.net"
]

def calculate_payout(amount: float) -> float:
    """Calculate payout based on the amount received (e.g., for zaps)."""
    if amount < 10:
        return 0.0
    # Calculate payout units for every 10 sats (floor division)
    units = amount // 10
    payout = units * 0.01
    # Apply min/max bounds
    payout = min(payout, 1.0)
    return round(payout, 2)


def parse_kinds(kinds: Union[List[int], str]) -> List[int]:
    """
    Parses the 'kinds' field, which can be a list of integers or a
    comma-separated string, into a list of integers.
    Also handles JSON array format like '[1,2,3]'.
    """
    if isinstance(kinds, list):
        # Ensure all elements are integers if it's already a list
        try:
            return [int(k) for k in kinds]
        except (ValueError, TypeError) as e:
             logger.error(f"Error converting list elements to int in parse_kinds: {e}")
             return []
    elif isinstance(kinds, str):
        if not kinds.strip(): # Handle empty string
            return []
        try:
            # Check if it looks like a JSON array
            if kinds.strip().startswith('[') and kinds.strip().endswith(']'):
                import json
                return [int(k) for k in json.loads(kinds)]
            # Otherwise, split by comma, strip whitespace, filter out non-digits, convert to int
            return [int(k.strip()) for k in kinds.split(',') if k.strip().isdigit()]
        except (ValueError, json.JSONDecodeError, TypeError) as e:
            logger.error(f"Error parsing kinds string '{kinds}': {e}")
            return []
    else:
        logger.warning(f"Unexpected type for 'kinds' in parse_kinds: {type(kinds)}. Returning empty list.")
        return []

def parse_current_kinds(kinds_str: Optional[str]) -> Set[int]:
    """
    Parses a comma-separated string of kinds (from the database) into a set of integers.
    Handles None or empty string inputs gracefully.
    """
    if not kinds_str: # Checks for None or empty string
        return set()
    try:
        # Split by comma, strip whitespace, filter out non-digits, convert to int, store in set
        return set(int(k.strip()) for k in kinds_str.split(',') if k.strip().isdigit())
    except ValueError as e:
        logger.error(f"Error parsing current kinds string '{kinds_str}': {e}")
        return set() # Return empty set on error

def calculate_member_updates(
    incoming_kinds_list: List[int],
    current_kinds_set: Set[int],
    new_amount: int # Assumed to be in sats (e.g., zap amount)
) -> Tuple[float, str]:
    """
    Calculates the payout increment and the updated kinds string based on
    incoming kinds and the member's current kinds.

    Args:
        incoming_kinds_list: List of kinds from the current event (e.g., [6], [9734]).
        current_kinds_set: Set of kinds the member has already been credited for.
        new_amount: The amount (in sats) associated with the incoming event, if applicable (e.g., for zaps).

    Returns:
        A tuple containing:
            - payout_increment (float): The additional payout value earned from this event.
            - updated_kinds_str (str): Comma-separated string of all unique kinds (current + new).
    """
    payout_increment = 0.0

    # Calculate payout for Zaps (Kind 9735 - Zap Receipts)
    if 9735 in incoming_kinds_list:
        zap_payout = calculate_payout(float(new_amount)) # Calculate based on zap amount
        payout_increment += zap_payout
        logger.debug(f"Calculated payout increment for zap (Kind 9735): {zap_payout}")

    # Calculate payout for new engagements (Kind 6 or 7) only if not already credited
    new_engagement_kinds = {k for k in incoming_kinds_list if k in [6, 7] and k not in current_kinds_set}

    for kind in new_engagement_kinds:
        if kind == 7: # Reaction (Like)
            # Payout for Like is 0.0 according to original logic? Confirm this requirement.
             payout_increment += 0.0
             logger.debug("Adding 0.0 payout increment for new Reaction (Kind 7).")
        elif kind == 6: # Repost
            payout_increment += 0.2
            logger.debug("Adding 0.2 payout increment for new Repost (Kind 6).")

    # Combine current kinds with all incoming kinds to get the full set
    updated_kinds_set = current_kinds_set.union(set(incoming_kinds_list))

    # Create the updated comma-separated string, sorted numerically
    updated_kinds_str = ','.join(map(str, sorted(list(updated_kinds_set))))

    logger.debug(f"Final calculated payout increment: {payout_increment}, Updated kinds string: '{updated_kinds_str}'")
    return payout_increment, updated_kinds_str

# --- Nostr helpers -----------------------------------------------------------

_BECH32_CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"


def _bech32_polymod(values: List[int]) -> int:
    """Internal: Compute Bech32 checksum."""
    generator = [0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3]
    chk = 1
    for value in values:
        top = chk >> 25
        chk = ((chk & 0x1FFFFFF) << 5) ^ value
        for i in range(5):
            if (top >> i) & 1:
                chk ^= generator[i]
    return chk


def _bech32_hrp_expand(hrp: str) -> List[int]:
    """Internal: Expand HRP for checksum computation."""
    return [ord(x) >> 5 for x in hrp] + [0] + [ord(x) & 31 for x in hrp]


def _bech32_create_checksum(hrp: str, data: List[int]) -> List[int]:
    """Internal: Create checksum."""
    values = _bech32_hrp_expand(hrp) + data
    polymod = _bech32_polymod(values + [0, 0, 0, 0, 0, 0]) ^ 1
    return [(polymod >> 5 * (5 - i)) & 31 for i in range(6)]


def _bech32_encode(hrp: str, data: List[int]) -> Optional[str]:
    """Encode hrp and data into a Bech32 string."""
    if not data:
        return None
    combined = data + _bech32_create_checksum(hrp, data)
    return hrp + "1" + "".join(_BECH32_CHARSET[d] for d in combined)


def _convert_bits(data: bytes, from_bits: int, to_bits: int, pad: bool = True) -> Optional[List[int]]:
    """General power-of-two base conversion."""
    acc = 0
    bits = 0
    maxv = (1 << to_bits) - 1
    result: List[int] = []
    for value in data:
        if value < 0 or (value >> from_bits):
            return None
        acc = (acc << from_bits) | value
        bits += from_bits
        while bits >= to_bits:
            bits -= to_bits
            result.append((acc >> bits) & maxv)
    if pad:
        if bits:
            result.append((acc << (to_bits - bits)) & maxv)
    elif bits >= from_bits or ((acc << (to_bits - bits)) & maxv):
        return None
    return result


def format_nostr_event_reference(event_id: Optional[str]) -> Optional[str]:
    """
    Convert a 32-byte hex event id into a nostr:note Bech32 reference.
    Returns None if the event id cannot be encoded.
    """
    if not event_id or not isinstance(event_id, str):
        return None
    candidate = event_id.strip().lower()
    if len(candidate) != 64:
        return None
    try:
        raw = bytes.fromhex(candidate)
    except ValueError:
        logger.debug("format_nostr_event_reference: invalid hex event id '%s'", candidate)
        return None
    data = _convert_bits(raw, 8, 5)
    if not data:
        return None
    encoded = _bech32_encode("note", data)
    if not encoded:
        return None
    return f"nostr:{encoded}"
