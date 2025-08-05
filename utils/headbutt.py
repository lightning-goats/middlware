"""
Enhanced HeadbuttService for CyberHerd with main.py compatibility.
Migrates headbutt logic from main.py to a proper service architecture.
"""
import asyncio
import json
import logging
import time
from typing import Dict, Any, List, Optional, TYPE_CHECKING

from .helpers import DEFAULT_RELAYS, calculate_payout, parse_kinds
from .database_service import CyberherdDatabaseService
from .messaging_service import HeadbuttMessagingService

# Import the messaging module for WebSocket communication
import messaging

if TYPE_CHECKING:
    from main import CyberHerdData

logger = logging.getLogger(__name__)


class EnhancedHeadbuttService:
    """
    Enhanced HeadbuttService that orchestrates the "bump / head‑butt" admission mechanic 
    for the ⚡ CyberHerd ⚡ with compatibility for main.py data structures.
    """

    COOLDOWN_SECONDS = 5  # 5 second lock‑out after a successful bump

    def __init__(
        self,
        database_service: CyberherdDatabaseService,
        messaging_service: HeadbuttMessagingService,
        max_herd_size: int = 3,
        headbutt_min_sats: int = 10,
        config: Dict[str, str] = None,
        send_messages_to_clients_func = None,  # Deprecated - use messaging module
        make_messages_func = None
    ):
        self.db = database_service
        self.messaging = messaging_service
        self.max_herd_size = max_herd_size
        self.headbutt_min_sats = headbutt_min_sats
        self.config = config or {}
        # Deprecated function references - using messaging module directly now
        self.send_messages_to_clients = send_messages_to_clients_func
        self.make_messages = make_messages_func
        self.send_cyberherd_update = None  # Will be set by main.py
        self._lock = asyncio.Lock()
        self._last_bump_ts = 0.0

    async def process_headbutting_attempts(self, attempts: List['CyberHerdData']) -> List[Dict[str, Any]]:
        """
        Process multiple headbutt attempts when the herd is full.
        Sorts attempts by amount and processes them sequentially.
        Returns list of successful headbutt results.
        """
        headbutt_attempts = [item for item in attempts if 9735 in item.kinds and item.amount and item.amount > 0]
        
        if not headbutt_attempts:
            logger.info("No valid headbutt attempts found (need zap receipts with amount > 0)")
            return []
        
        headbutt_attempts.sort(key=lambda x: x.amount, reverse=True)
        successful_headbutts = []
        
        for attempt in headbutt_attempts:
            result = await self.attempt_headbutt(attempt)
            
            if result:
                logger.info(f"Headbutt processed successfully: {result}")
                successful_headbutts.append(result)
            else:
                logger.info(f"Headbutt attempt for {attempt.pubkey} did not result in a change.")
        
        return successful_headbutts

    async def attempt_headbutt(self, attacker: 'CyberHerdData') -> Optional[Dict[str, Any]]:
        """
        Attempt to headbutt the member with the lowest zap amount.
        Compatible with main.py CyberHerdData structure.
        Returns headbutt result dict if successful, None if failed.
        """
        async with self._lock:
            try:
                if self._in_cooldown():
                    logger.info("Head‑butt skipped – still cooling down…")
                    return None

                # Check if attacker is already a member
                existing_members = await self.db.get_all_cyberherd_members()
                for member in existing_members:
                    if member['pubkey'] == attacker.pubkey:
                        logger.info(f"Attacker {attacker.pubkey} is already a member. This should have been a cumulative update.")
                        return None

                # Short‑circuit if there is still room
                current_size = await self.db.get_cyberherd_size()
                if current_size < self.max_herd_size:
                    logger.debug("No head‑butt needed – free spots available.")
                    return None

                # Find the lowest member
                lowest_member = await self._get_lowest_member()
                if not lowest_member:
                    logger.error("No members found to headbutt, which shouldn't happen if herd is full.")
                    return None

                required_amount = max(self.headbutt_min_sats, lowest_member['amount'] + 1)

                if attacker.amount < required_amount:
                    logger.info(f"Headbutt failed: {attacker.pubkey} zap of {attacker.amount} sats is not enough (needs {required_amount}).")
                    await self._send_headbutt_failure_notification(attacker, lowest_member, required_amount)
                    return None

                logger.info(f"Headbutt successful: {attacker.pubkey} ({attacker.amount} sats) is replacing {lowest_member['pubkey']} ({lowest_member['amount']} sats).")

                # Remove the victim and add the attacker
                await self.db.delete_cyberherd_member_by_pubkey(lowest_member['pubkey'])
                await self._add_new_headbutt_member(attacker)
                
                self._set_cooldown()

                # Create result data
                headbutt_result = {
                    "attacker": attacker.pubkey,
                    "victim": lowest_member['pubkey'],
                    "attacker_amount": attacker.amount,
                    "victim_amount": lowest_member['amount'],
                    "attacker_name": attacker.display_name or "Anon",
                    "victim_name": lowest_member['display_name'] or "Anon",
                    "attacker_nprofile": attacker.nprofile,
                    "victim_nprofile": lowest_member['nprofile']
                }

                # Send success notifications
                await self._send_headbutt_success_notifications(attacker, lowest_member, headbutt_result)

                return headbutt_result

            except Exception as e:
                logger.error(f"An unexpected error occurred during the headbutt attempt: {e}")
                return None

    async def _get_lowest_member(self) -> Optional[Dict[str, Any]]:
        """Get the member with the lowest amount."""
        members = await self.db.get_all_cyberherd_members()
        if not members:
            return None
        return min(members, key=lambda m: (m.get("amount", 0), m.get("pubkey", "")))

    def _in_cooldown(self) -> bool:
        """Check if still in cooldown period."""
        return (time.time() - self._last_bump_ts) < self.COOLDOWN_SECONDS

    def _set_cooldown(self):
        """Set the cooldown timestamp."""
        self._last_bump_ts = time.time()

    async def _add_new_headbutt_member(self, member: 'CyberHerdData'):
        """Add a new member who successfully headbutted someone."""
        relays = member.relays or DEFAULT_RELAYS[:2]
        
        if isinstance(member.kinds, list):
            kinds_str = ','.join(map(str, member.kinds))
        else:
            kinds_str = str(member.kinds)
        
        kinds_int = parse_kinds(member.kinds)
        payouts = calculate_payout(member.amount) if 9735 in kinds_int else 0.0
        
        member_data = {
            "pubkey": member.pubkey,
            "display_name": member.display_name or "Anon",
            "event_id": member.event_id,
            "note": member.note,
            "kinds": kinds_str,
            "nprofile": member.nprofile,
            "lud16": member.lud16,
            "notified": None,
            "payouts": payouts,
            "amount": member.amount,
            "picture": member.picture,
            "relays": json.dumps(relays)
        }
        
        await self.db.add_cyberherd_member(member_data)

    async def _send_headbutt_failure_notification(self, attacker: 'CyberHerdData', victim: Dict[str, Any], required_amount: int):
        """Send notification when headbutt attempt fails due to insufficient zaps."""
        if not self.make_messages:
            logger.debug("Make messages function not available, skipping failure notification")
            return
            
        try:
            message_data = {
                'attacker_name': attacker.display_name or 'Anon',
                'attacker_amount': attacker.amount,
                'victim_name': victim['display_name'] or 'Anon',
                'victim_amount': victim['amount'],
                'required_amount': required_amount,
                'attacker_pubkey': attacker.pubkey,
                'victim_pubkey': victim['pubkey'],
                'event_id': attacker.event_id,
                'attacker_nprofile': attacker.nprofile,
                'victim_nprofile': victim['nprofile']
            }
            
            message_content, _ = await self.make_messages(
                self.config.get('NOS_SEC', ''),
                attacker.amount,
                0,
                "headbutt_failure",
                message_data,
                0,
                relays=DEFAULT_RELAYS
            )
            
            # Use messaging module for WebSocket communication
            await messaging.send_to_websocket_clients(message_content)
            logger.info(f"Sent headbutt failure notification for {attacker.pubkey}")
        except Exception as e:
            logger.error(f"Failed to send headbutt failure notification: {e}")

    async def _send_headbutt_success_notifications(self, attacker: 'CyberHerdData', victim: Dict[str, Any], headbutt_result: Dict[str, Any]):
        """Send notifications for successful headbutt."""
        if not self.make_messages:
            logger.debug("Make messages function not available, skipping success notification")
            return
            
        try:
            final_herd_size = await self.db.get_cyberherd_size()

            message_data = {
                'attacker_name': headbutt_result['attacker_name'],
                'attacker_amount': headbutt_result['attacker_amount'],
                'victim_name': headbutt_result['victim_name'],
                'victim_amount': headbutt_result['victim_amount'],
                'attacker_pubkey': headbutt_result['attacker'],
                'victim_pubkey': headbutt_result['victim'],
                'event_id': attacker.event_id,
                'attacker_nprofile': headbutt_result['attacker_nprofile'],
                'victim_nprofile': victim['nprofile']
            }
            
            message_content, _ = await self.make_messages(
                self.config.get('NOS_SEC', ''),
                attacker.amount,
                0,
                "headbutt_success",
                message_data,
                final_herd_size,
                relays=DEFAULT_RELAYS
            )
            
            # Use messaging module for WebSocket communication
            await messaging.send_to_websocket_clients(message_content)
            logger.info(f"Sent headbutt success notification for {attacker.pubkey} replacing {victim['pubkey']}")

            # Send CyberHerd update to show new member lineup using messaging module
            await messaging.send_cyberherd_update(attacker.pubkey, self.db.database)
            logger.info(f"Sent CyberHerd update after headbutt success")

            # Mark the new member as notified
            members = await self.db.get_all_cyberherd_members()
            for member in members:
                if member['pubkey'] == attacker.pubkey:
                    # Update notification status (would need a database method for this)
                    logger.info(f"Marked new member {attacker.pubkey} (from headbutt) as notified.")
                    break

        except Exception as e:
            logger.error(f"Failed to send and update headbutt success notification: {e}")
