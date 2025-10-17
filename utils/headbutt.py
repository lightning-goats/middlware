"""
Enhanced HeadbuttService for CyberHerd with main.py compatibility.
This service manages the "headbutt" logic for the active daily herd.
"""
import asyncio
import json
import logging
import time
from typing import Dict, Any, List, Optional, TYPE_CHECKING

from utils.helpers import DEFAULT_RELAYS, calculate_payout, format_nostr_event_reference
from .database_service import CyberherdDatabaseService
from .messaging_service import HeadbuttMessagingService

import messaging

if TYPE_CHECKING:
    from main import CyberHerdData

logger = logging.getLogger(__name__)

class EnhancedHeadbuttService:
    """
    Enhanced HeadbuttService that orchestrates the "bump / head‑butt" admission mechanic
    for the daily ACTIVE ⚡ CyberHerd ⚡.
    """
    COOLDOWN_SECONDS = 5

    def __init__(
        self,
        database_service: CyberherdDatabaseService,
        messaging_service: HeadbuttMessagingService,
        max_herd_size: int = 3,
        headbutt_min_sats: int = 10,
        config: Dict[str, str] = None,
        make_messages_func = None
    ):
        self.db = database_service
        self.messaging = messaging_service
        self.max_herd_size = max_herd_size
        self.headbutt_min_sats = max(0, headbutt_min_sats)
        self.config = config or {}
        self.make_messages = make_messages_func
        self.send_cyberherd_update = None
        self._lock = asyncio.Lock()
        self._last_bump_ts = 0.0

    async def process_headbutting_attempts(self, attempts: List['CyberHerdData']) -> List[Dict[str, Any]]:
        headbutt_attempts = [
            item
            for item in attempts
            if 9735 in item.kinds and item.amount and item.amount >= self.headbutt_min_sats
        ]
        if not headbutt_attempts:
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
        async with self._lock:
            try:
                if self._in_cooldown():
                    logger.info("Head‑butt skipped – still cooling down…")
                    return None

                active_members = await self.db.get_active_cyberherd_members()
                
                if any(member['pubkey'] == attacker.pubkey for member in active_members):
                    logger.warning(f"Attacker {attacker.pubkey} is already active. This should be a cumulative update.")
                    return None

                current_active_size = len(active_members)
                if current_active_size < self.max_herd_size:
                    logger.info("No head‑butt needed – free spot in active herd. Activating member.")
                    if attacker.amount < self.headbutt_min_sats:
                        logger.info(
                            "Head‑butt skipped – zap amount %s sats below minimum threshold %s.",
                            attacker.amount,
                            self.headbutt_min_sats,
                        )
                        return None
                    admission_status = await self._handle_attacker_admission(attacker)
                    await messaging.send_cyberherd_update(attacker.pubkey, self.db.database)
                    return {"newly_activated": attacker.pubkey, "reason": "Free spot", "status": admission_status}

                lowest_active_member = self._get_lowest_member(active_members)
                if not lowest_active_member:
                    logger.error("No active members found to headbutt, which shouldn't happen if herd is full.")
                    return None

                required_amount = lowest_active_member['amount'] + 1
                required_threshold = max(required_amount, self.headbutt_min_sats)

                if attacker.amount < required_threshold:
                    logger.info(
                        "Headbutt failed: %s zap of %s sats is not enough (needs %s).",
                        attacker.pubkey,
                        attacker.amount,
                        required_threshold,
                    )
                    await self._send_headbutt_failure_notification(attacker, lowest_active_member, required_threshold)
                    return None

                logger.info(f"Headbutt successful: {attacker.pubkey} ({attacker.amount} sats) is replacing {lowest_active_member['pubkey']} ({lowest_active_member['amount']} sats).")

                await self.db.deactivate_cyberherd_member(lowest_active_member['pubkey'])
                admission_status = await self._handle_attacker_admission(attacker)
                self._set_cooldown()

                headbutt_result = {
                    "attacker": attacker.pubkey, "victim": lowest_active_member['pubkey'],
                    "attacker_amount": attacker.amount, "victim_amount": lowest_active_member['amount'],
                    "attacker_name": attacker.display_name or "Anon", "victim_name": lowest_active_member['display_name'] or "Anon",
                    "attacker_nprofile": attacker.nprofile, "victim_nprofile": lowest_active_member['nprofile'],
                    "status": admission_status
                }

                await self._send_headbutt_success_notifications(attacker, lowest_active_member, headbutt_result)
                return headbutt_result

            except Exception as e:
                logger.error(f"An unexpected error occurred during headbutt attempt: {e}", exc_info=True)
                return None

    def _get_lowest_member(self, active_members: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not active_members:
            return None
        return min(active_members, key=lambda m: (m.get("amount", 0), m.get("pubkey", "")))

    def _in_cooldown(self) -> bool:
        return (time.time() - self._last_bump_ts) < self.COOLDOWN_SECONDS

    def _set_cooldown(self):
        self._last_bump_ts = time.time()
        
    async def _handle_attacker_admission(self, attacker: 'CyberHerdData') -> str:
        """
        Handles admitting an attacker to the herd.
        Returns 'new' if the member was just created, or 'reactivated' if an existing
        member was made active.
        """
        existing_user = await self.db.get_cyberherd_member_by_pubkey(attacker.pubkey)
        payouts = calculate_payout(attacker.amount)
        
        if existing_user:
            await self.db.update_and_activate_member(attacker.pubkey, attacker.amount, payouts)
            return "reactivated"
        else:
            await self._add_new_member(attacker, payouts)
            return "new"

    async def _add_new_member(self, member: 'CyberHerdData', payouts: float):
        kinds_str = ','.join(map(str, member.kinds)) if isinstance(member.kinds, list) else str(member.kinds)
        member_data = {
            "pubkey": member.pubkey, "display_name": member.display_name or "Anon",
            "event_id": member.event_id, "note": member.note, "kinds": kinds_str,
            "nprofile": member.nprofile, "lud16": member.lud16,
            "payouts": payouts, "amount": member.amount, "picture": member.picture,
            "relays": json.dumps(member.relays or DEFAULT_RELAYS[:2]),
        }
        await self.db.add_new_active_member(member_data)

    async def _send_headbutt_failure_notification(self, attacker: 'CyberHerdData', victim: Dict[str, Any], required_amount: int):
        if not self.make_messages: return
        try:
            message_data = {
                'attacker_name': attacker.display_name or 'Anon', 'attacker_amount': attacker.amount,
                'victim_name': victim['display_name'] or 'Anon', 'victim_amount': victim['amount'],
                'required_amount': required_amount, 'attacker_pubkey': attacker.pubkey, 'victim_pubkey': victim['pubkey'],
                'event_id': attacker.event_id, 'attacker_nprofile': attacker.nprofile, 'victim_nprofile': victim['nprofile'],
                'tracked_event_reference': format_nostr_event_reference(attacker.event_id),
            }
            message_content, _ = await self.make_messages(
                self.config.get('NOS_SEC', ''), attacker.amount, 0, "headbutt_failure",
                cyber_herd_item=message_data, relays=DEFAULT_RELAYS,
                reply_to_30311_event=attacker.event_id if getattr(attacker, 'a_tag', '').startswith('30311:') else None,
                reply_to_30311_a_tag=getattr(attacker, 'a_tag', None) if getattr(attacker, 'a_tag', '').startswith('30311:') else None
            )
            await messaging.send_to_websocket_clients(message_content)
        except Exception as e:
            logger.error(f"Failed to send headbutt failure notification: {e}")

    async def _send_headbutt_success_notifications(self, attacker: 'CyberHerdData', victim: Dict[str, Any], headbutt_result: Dict[str, Any]):
        if not self.make_messages: return
        try:
            # The 'status' field in headbutt_result can now be used to determine
            # the correct message type. For example, you could have a condition in
            # your make_messages function like:
            # message_type = "new_member_welcome" if headbutt_result.get("status") in ["new", "reactivated"] else "headbutt_success"
            
            final_active_herd_size = await self.db.get_active_cyberherd_size()
            message_data = {
                'attacker_name': headbutt_result['attacker_name'], 'attacker_amount': headbutt_result['attacker_amount'],
                'victim_name': headbutt_result['victim_name'], 'victim_amount': headbutt_result['victim_amount'],
                'attacker_pubkey': headbutt_result['attacker'], 'victim_pubkey': headbutt_result['victim'],
                'event_id': attacker.event_id, 'attacker_nprofile': headbutt_result['attacker_nprofile'],
                'victim_nprofile': victim['nprofile'],
                'tracked_event_reference': format_nostr_event_reference(attacker.event_id),
            }
            
            message_content, _ = await self.make_messages(
                self.config.get('NOS_SEC', ''), attacker.amount, 0, "headbutt_success",
                cyber_herd_item=message_data,
                spots_remaining=max(0, self.max_herd_size - final_active_herd_size),
                relays=DEFAULT_RELAYS,
                reply_to_30311_event=attacker.event_id if getattr(attacker, 'a_tag', '').startswith('30311:') else None,
                reply_to_30311_a_tag=getattr(attacker, 'a_tag', None) if getattr(attacker, 'a_tag', '').startswith('30311:') else None
            )
            
            await messaging.send_to_websocket_clients(message_content)
            logger.info(f"Sent headbutt success notification for {attacker.pubkey} replacing {victim['pubkey']}")

            await messaging.send_cyberherd_update(attacker.pubkey, self.db.database)
            logger.info("Sent CyberHerd update after headbutt success")
        except Exception as e:
            logger.error(f"Failed to send headbutt success notification: {e}")
