import logging
from typing import List, Set, Tuple, Union
from typing import Optional  # Import separately to ensure it's available

# Setup logger for helper functions
logger = logging.getLogger(__name__)

# Centralized relay configuration - single source of truth
DEFAULT_RELAYS = [
    "wss://relay.primal.net/",
    "wss://nostr-pub.wellorder.net",
    "wss://relay.damus.io/",
    "wss://nostr.oxtr.dev"
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
