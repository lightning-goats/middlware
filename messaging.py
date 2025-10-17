import asyncio
import json
import random
import logging
import os
from typing import Any, Optional, List, Dict
from dotenv import load_dotenv
from utils.helpers import DEFAULT_RELAYS, format_nostr_event_reference

# Load environment variables
load_dotenv()

# Configure relays based on testing mode
TESTING_MODE = os.getenv('TESTING_MODE', 'false').lower() == 'true' or os.getenv('TESTING', 'false').lower() == 'true'
LOCAL_RELAY_URL = os.getenv('LOCAL_RELAY_URL', 'ws://127.0.0.1:7000')

# Configure nak binary path
NAK_PATH = os.getenv('NAK_PATH', 'nak')  # Default to 'nak' to use PATH, or set specific path

# Configure command testing mode
TEST_COMMANDS = os.getenv('TEST_COMMANDS', 'false').lower() == 'true'

if TESTING_MODE:
    RELAY_URLS = LOCAL_RELAY_URL
    logger = logging.getLogger(__name__)
    logging.basicConfig(level=logging.INFO)
    logger.info(f"MESSAGING - TESTING MODE: Using only local relay at {LOCAL_RELAY_URL}")
else:
    # Use centralized relay configuration, converting to space-separated string format for nak
    RELAY_URLS = ' '.join(DEFAULT_RELAYS) + ' ws://127.0.0.1:3002/nostrrelay/666'
    logger = logging.getLogger(__name__)
    logging.basicConfig(level=logging.INFO)
    logger.info("MESSAGING - PRODUCTION MODE: Using centralized relays")

from messages import (
    goat_names_dict, herd_reset_message,
    cyber_herd_dict, cyber_herd_info_dict, cyber_herd_treats_dict,
    interface_info_dict, sats_received_dict, headbutt_info_dict,
    headbutt_success_dict, feeder_trigger_dict, headbutt_failure_dict,
    member_increase_dict, thank_you_variations, variations,
    daily_reset_dict, feeding_regular_dict, feeding_bonus_dict,
    feeding_remainder_dict, feeding_fallback_dict,
    payment_metrics_dict, system_status_dict, weather_status_dict
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

notified = {}

def extract_id_from_stdout(stdout):
    try:
        data = json.loads(stdout)
        return data.get('id', None)
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing JSON from stdout: {e}")
        return None

def get_random_goat_names(goat_names_dict):
    keys = list(goat_names_dict.keys())
    selected_keys = random.sample(keys, random.randint(1, len(keys)))
    return [(key, goat_names_dict[key][0], goat_names_dict[key][1]) for key in selected_keys]

def join_with_and(items):
    if len(items) > 2:
        return ', '.join(items[:-1]) + ', and ' + items[-1]
    elif len(items) == 2:
        return ' and '.join(items)
    elif len(items) == 1:
        return items[0]
    else:
        return ''

async def execute_nostr_command_background(command: str):
    """
    Executes a shell command in the background without blocking.
    Logs the outcome for debugging.
    """
    if TEST_COMMANDS:
        logger.info(f"🧪 TEST MODE: Would execute background command: {command}")
        return
    
    try:
        process = await asyncio.create_subprocess_shell(
            command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            logger.error(f"Background Nostr command failed (code {process.returncode}): {stderr.decode().strip()}")
        else:
            # Extract and log the event ID for confirmation
            event_id = extract_id_from_stdout(stdout.decode())
            logger.info(f"✅ Background Nostr command succeeded. Event ID: {event_id}")
    except Exception as e:
        logger.error(f"Exception during background command execution: {e}")

async def make_messages(
    nos_sec: str,
    new_amount: float,
    difference: float,
    event_type: str,
    cyber_herd_item: dict = None,
    spots_remaining: int = 0,
    relays: Optional[List[str]] = None,
    reply_to_30311_event: Optional[str] = None,
    reply_to_30311_a_tag: Optional[str] = None
):
    global notified
    
    # Track goat data for client messages
    selected_goats_data = None

    message_dict = {
        "sats_received": sats_received_dict,
        "feeder_triggered": feeder_trigger_dict,
        "feeder_trigger_bolt12": feeder_trigger_dict, # Use the same message templates
        "cyber_herd": cyber_herd_dict,
        "cyber_herd_info": cyber_herd_info_dict,
        "cyber_herd_treats": cyber_herd_treats_dict,
        "headbutt_info": headbutt_info_dict,
        "headbutt_success": headbutt_success_dict,
        "headbutt_failure": headbutt_failure_dict,
        "member_increase": member_increase_dict,
        "new_member": cyber_herd_dict,
        "interface_info": interface_info_dict,
        "herd_reset": {0: herd_reset_message["message"]},
        "daily_reset": daily_reset_dict,
        "feeding_regular": feeding_regular_dict,
        "feeding_bonus": feeding_bonus_dict,
        "feeding_remainder": feeding_remainder_dict,
        "feeding_fallback": feeding_fallback_dict,
        "payment_metrics": payment_metrics_dict,
        "system_status": system_status_dict,
        "weather_status": weather_status_dict
    }

    message_templates = message_dict.get(event_type, None)
    if not message_templates:
        logger.error(f"Event type '{event_type}' not recognized.")
        return "Event type not recognized.", None

    # Randomly pick a template from whichever dict was selected
    template = random.choice(list(message_templates.values()))
    command = None
    nostr_message_content = "" # For storing the final nostr message

    # -- Handle each event_type separately --
    # CORRECTED: Consolidated "new_member" into "cyber_herd" to ensure nak command is always built.
    if event_type in ["cyber_herd", "new_member"]:
        display_name = cyber_herd_item.get("display_name", "anon") if cyber_herd_item else "anon"
        event_id = cyber_herd_item.get("event_id", "") if cyber_herd_item else ""
        pub_key = cyber_herd_item.get("pubkey", "") if cyber_herd_item else ""
        nprofile = cyber_herd_item.get("nprofile", "") if cyber_herd_item else ""
        amount = cyber_herd_item.get("amount", 0) if cyber_herd_item else 0

        # Decide on a "thank you" snippet
        if amount == 0:
            thanks_part = ""
        else:
            chosen_variation = random.choice(thank_you_variations)
            thanks_part = chosen_variation.format(new_amount=amount)

        # Ensure nprofile is well-formed
        if nprofile and not nprofile.startswith("nostr:"):
            nprofile = f"nostr:{nprofile}"

        tracked_reference = None
        if cyber_herd_item:
            tracked_reference = cyber_herd_item.get("tracked_event_reference")
        if not tracked_reference:
            tracked_reference = format_nostr_event_reference(event_id)
        nostr_name = tracked_reference or nprofile or display_name

        # Spots info
        spots_info = ""
        if spots_remaining > 1:
            spots_info = f"⚡ {spots_remaining} more spots available. ⚡"
        elif spots_remaining == 1:
            spots_info = f"⚡ {spots_remaining} more spot available. ⚡"
            
        # Headbutt info (when herd is full - spots_remaining = 0)
        headbutt_text = ""
        if spots_remaining == 0 and cyber_herd_item and cyber_herd_item.get('headbutt_info'):
            # Generate headbutt info message
            headbutt_info = cyber_herd_item['headbutt_info']
            required_sats = headbutt_info.get('required_sats', 10)
            victim_name = headbutt_info.get('victim_name', 'Anon')
            
            headbutt_message = random.choice(list(headbutt_info_dict.values()))
            headbutt_text = f" {headbutt_message.format(required_sats=required_sats, victim_name=victim_name)}"

        # Format the message for nostr
        nostr_message_content = (
            template.format(
                thanks_part=thanks_part,
                name=nostr_name,
                difference=difference,
                new_amount=amount,
                event_id=event_id
            )
            + spots_info
            + headbutt_text
        )

        # Strip promotional URL for NIP-53 chat messages
        if reply_to_30311_event and reply_to_30311_a_tag:
            nostr_message_content = nostr_message_content.replace("\n\n https://lightning-goats.com\n\n", "")

        # Build the command if we have the necessary info
        if pub_key and event_id:
            # Determine event kind: Use kind 1311 for NIP-53 chat messages (replies to 30311), else kind 1
            event_kind = 1311 if (reply_to_30311_event and reply_to_30311_a_tag) else 1
            
            # Base command with kind
            command = (
                f'{NAK_PATH} event --sec {nos_sec} --kind {event_kind} -c "{nostr_message_content}" '
                f'-t e="{event_id};wss://lnb.bolverker.com/nostrrelay/666;root" '
                f'-p {pub_key}'
            )
            
            # Add 30311 event reference tags if provided (NIP-53 compliant)
            if reply_to_30311_event and reply_to_30311_a_tag:
                command += f' -t a={reply_to_30311_a_tag}'  # Primary a tag for 30311 reference
                command += f' -t e={reply_to_30311_event}'  # e tag for direct reply
            
            command += f' {RELAY_URLS}'
        else:
            logger.warning(f"Missing pubkey or event_id for {event_type} notification. Cannot send Nostr note.")


        # Format the message for the client (websocket)
        message = (
            template.format(
                thanks_part=thanks_part,
                name=display_name,
                difference=difference,
                new_amount=amount,
                event_id=event_id
            )
            + spots_info
            + headbutt_text
        )
    
    elif event_type == "feeder_triggered":
        # Check if the selected template contains goat names
        if "{goat_name}" in template:
            # Only generate goat data if the template uses goat names
            selected_goats = get_random_goat_names(goat_names_dict)
            
            # Store goat data for client message
            selected_goats_data = [
                {
                    "name": name,
                    "imageUrl": f"images/{name.lower()}.png"
                }
                for name, _, _ in selected_goats
            ]
            
            goat_names = join_with_and([name for name, _, _ in selected_goats])
            goat_nprofiles = join_with_and([nprofile for _, nprofile, _ in selected_goats])
            goat_pubkeys = [pubkey for _, _, pubkey in selected_goats]

            variation_message = random.choice(list(variations.values()))
            difference_message = variation_message.format(difference=difference)

            # First formatting includes goat_nprofiles
            nostr_message_content = template.format(
                new_amount=new_amount,
                goat_name=goat_nprofiles,
                difference_message=difference_message
            )

            pubkey_part = " ".join(f"-p {pubkey}" for pubkey in goat_pubkeys)
            command = (
                f'{NAK_PATH} event --sec {nos_sec} -c "{nostr_message_content}" '
                f'-t t=LightningGoats {pubkey_part} '
                f'{RELAY_URLS}'
            )

            # Then reformat to show goat_names in the final message
            message = template.format(
                new_amount=new_amount,
                goat_name=goat_names,
                difference_message=difference_message
            )
        else:
            # Template doesn't use goat names, format without them
            variation_message = random.choice(list(variations.values()))
            difference_message = variation_message.format(difference=difference)
            
            message = template.format(
                new_amount=new_amount,
                difference_message=difference_message
            )
            nostr_message_content = message
            
            command = (
                f'{NAK_PATH} event --sec {nos_sec} -c "{nostr_message_content}" '
                f'-t t=LightningGoats '
                f'{RELAY_URLS}'
            )
            
            # Then reformat to show goat_names in the final message
            message = template.format(
                new_amount=new_amount,
                difference_message=difference_message
            )

    elif event_type == "feeder_trigger_bolt12":
        bolt12_prefix = "⚡BOLT12 PAYMENT⚡ "
        # Check if the selected template contains goat names
        if "{goat_name}" in template:
            # Only generate goat data if the template uses goat names
            selected_goats = get_random_goat_names(goat_names_dict)
            
            # Store goat data for client message
            selected_goats_data = [
                {
                    "name": name,
                    "imageUrl": f"images/{name.lower()}.png"
                }
                for name, _, _ in selected_goats
            ]
            
            goat_names = join_with_and([name for name, _, _ in selected_goats])
            goat_nprofiles = join_with_and([nprofile for _, nprofile, _ in selected_goats])
            goat_pubkeys = [pubkey for _, _, pubkey in selected_goats]

            variation_message = random.choice(list(variations.values()))
            difference_message = variation_message.format(difference=difference)

            # Create base messages
            base_nostr_message = template.format(
                new_amount=new_amount,
                goat_name=goat_nprofiles,
                difference_message=difference_message
            )
            base_client_message = template.format(
                new_amount=new_amount,
                goat_name=goat_names,
                difference_message=difference_message
            )
            
            # Prepend prefix
            nostr_message_content = bolt12_prefix + base_nostr_message
            message = bolt12_prefix + base_client_message

            pubkey_part = " ".join(f"-p {pubkey}" for pubkey in goat_pubkeys)
            command = (
                f'{NAK_PATH} event --sec {nos_sec} -c "{nostr_message_content}" '
                f'-t t=LightningGoats {pubkey_part} '
                f'{RELAY_URLS}'
            )
        else:
            # Template doesn't use goat names, format without them
            variation_message = random.choice(list(variations.values()))
            difference_message = variation_message.format(difference=difference)
            
            base_message = template.format(
                new_amount=new_amount,
                difference_message=difference_message
            )
            
            # Prepend prefix
            message = bolt12_prefix + base_message
            nostr_message_content = message
            
            command = (
                f'{NAK_PATH} event --sec {nos_sec} -c "{nostr_message_content}" '
                f'-t t=LightningGoats '
                f'{RELAY_URLS}'
            )
            
            message = template.format(
                new_amount=new_amount,
                difference_message=difference_message
            )

    elif event_type == "sats_received":
        # Check if the selected template contains goat names
        if "{goat_name}" in template:
            # Only generate goat data if the template uses goat names
            selected_goats = get_random_goat_names(goat_names_dict)
            
            # Store goat data for client message
            selected_goats_data = [
                {
                    "name": name,
                    "imageUrl": f"images/{name.lower()}.png"
                }
                for name, _, _ in selected_goats
            ]
            
            goat_names = join_with_and([name for name, _, _ in selected_goats])
            goat_nprofiles = join_with_and([nprofile for _, nprofile, _ in selected_goats])
            goat_pubkeys = [pubkey for _, _, pubkey in selected_goats]

            variation_message = random.choice(list(variations.values()))
            difference_message = variation_message.format(difference=difference)

            # First formatting includes goat_nprofiles
            nostr_message_content = template.format(
                new_amount=new_amount,
                goat_name=goat_nprofiles,
                difference_message=difference_message
            )

            pubkey_part = " ".join(f"-p {pubkey}" for pubkey in goat_pubkeys)
            command = (
                f'{NAK_PATH} event --sec {nos_sec} -c "{nostr_message_content}" '
                f' -t t=LightningGoats {pubkey_part} '
                f'{RELAY_URLS}'
            )

            # Then reformat to show goat_names in the final message
            message = template.format(
                new_amount=new_amount,
                goat_name=goat_names,
                difference_message=difference_message
            )
        else:
            # Template doesn't use goat names, format without them
            variation_message = random.choice(list(variations.values()))
            difference_message = variation_message.format(difference=difference)
            
            message = template.format(
                new_amount=new_amount,
                difference_message=difference_message
            )
            nostr_message_content = message
            
            command = (
                f'{NAK_PATH} event --sec {nos_sec} -c "{nostr_message_content}" '
                f' -t t=LightningGoats '
                f'{RELAY_URLS}'
            )

    elif event_type == "interface_info":
        # Simple usage
        message = template.format(new_amount=0, goat_name="", difference_message="")
        command = None

    elif event_type == "headbutt_info":
        # Handle headbutt info message formatting
        required_sats = cyber_herd_item.get("required_sats", 0)
        victim_name = cyber_herd_item.get("victim_name", "Anon")
        victim_pubkey = cyber_herd_item.get("victim_pubkey", "")
        victim_nprofile = cyber_herd_item.get("victim_nprofile", "")
        event_id = cyber_herd_item.get("event_id", "")
        
        # Ensure nprofile is well-formed
        if victim_nprofile and not victim_nprofile.startswith("nostr:"):
            victim_nprofile = f"nostr:{victim_nprofile}"
        
        # Create Nostr message with nprofile
        nostr_message_content = template.format(
            required_sats=required_sats,
            victim_name=victim_nprofile if victim_nprofile else victim_name
        )
        
        # Strip promotional URL for NIP-53 chat messages
        if reply_to_30311_event and reply_to_30311_a_tag:
            nostr_message_content = nostr_message_content.replace("\n\n https://lightning-goats.com\n\n", "")
        
        # Create client message with display name
        client_message = template.format(
            required_sats=required_sats,
            victim_name=victim_name
        )
        
        # Create Nostr command for headbutt info - reply to the cyberherd note
        if event_id:
            command = (
                f'{NAK_PATH} event --sec {nos_sec} -k {1311 if (reply_to_30311_event and reply_to_30311_a_tag) else 1} -c "{nostr_message_content}" '
                f'-t e="{event_id};wss://lnb.bolverker.com/nostrrelay/666;root" '
                f'-p {victim_pubkey} '
            )
            
            # Add 30311 event reference tags if provided (NIP-53 compliant)
            if reply_to_30311_event and reply_to_30311_a_tag:
                command += f' -t a={reply_to_30311_a_tag} -t e={reply_to_30311_event}'
            
            command += f' {RELAY_URLS}'
        else:
            # Fallback to standalone note if no event_id available
            command = (
                f'{NAK_PATH} event --sec {nos_sec} --kind {1311 if (reply_to_30311_event and reply_to_30311_a_tag) else 1} -c "{nostr_message_content}" '
                f'-t t=CyberHerd -t t=HeadbuttInfo '
            )
            
            # Add 30311 event reference tags if provided (NIP-53 compliant)
            if reply_to_30311_event and reply_to_30311_a_tag:
                command += f' -t a={reply_to_30311_a_tag} -t e={reply_to_30311_event}'
            
            command += f' {RELAY_URLS}'
        
        # Override message for client formatting
        message = client_message

    elif event_type == "cyber_herd_info":
        # Handle cyber herd info message formatting
        display_name = cyber_herd_item.get("display_name", "Anon") if cyber_herd_item else "Anon"
        amount = cyber_herd_item.get("amount", 0) if cyber_herd_item else 0
        nprofile = cyber_herd_item.get("nprofile", "") if cyber_herd_item else ""
        
        # Ensure nprofile is well-formed
        if nprofile and not nprofile.startswith("nostr:"):
            nprofile = f"nostr:{nprofile}"
            
        message = template.format(
            new_amount=amount,
            name=display_name if not nprofile else nprofile,
            difference=difference
        )
        nostr_message_content = message
        
        # Command for posting to nostr
        if cyber_herd_item and cyber_herd_item.get("pubkey"):
            pub_key = cyber_herd_item.get("pubkey")
            command = (
                f'{NAK_PATH} event --sec {nos_sec} -c "{nostr_message_content}" '
                f'-t t=CyberHerd -t t=CyberHerdInfo '
                f'-p {pub_key} '
                f'{RELAY_URLS}'
            )
        else:
            command = (
                f'{NAK_PATH} event --sec {nos_sec} -c "{nostr_message_content}" '
                f'-t t=CyberHerd -t t=CyberHerdInfo '
                f'{RELAY_URLS}'
            )

    elif event_type == "headbutt_success":
        # Handle headbutt success message formatting
        attacker_name = cyber_herd_item.get("attacker_name", "Anon") 
        attacker_amount = cyber_herd_item.get("attacker_amount", 0)
        victim_name = cyber_herd_item.get("victim_name", "Anon")
        victim_amount = cyber_herd_item.get("victim_amount", 0)
        attacker_pubkey = cyber_herd_item.get("attacker_pubkey", "")
        victim_pubkey = cyber_herd_item.get("victim_pubkey", "")
        event_id = cyber_herd_item.get("event_id", "")
        attacker_nprofile = cyber_herd_item.get("attacker_nprofile", "")
        victim_nprofile = cyber_herd_item.get("victim_nprofile", "")
        
        # Ensure nprofiles are well-formed
        if attacker_nprofile and not attacker_nprofile.startswith("nostr:"):
            attacker_nprofile = f"nostr:{attacker_nprofile}"
        if victim_nprofile and not victim_nprofile.startswith("nostr:"):
            victim_nprofile = f"nostr:{victim_nprofile}"
        
        # Check for next headbutt info to append
        next_headbutt_text = ""
        if cyber_herd_item.get('next_headbutt_info'):
            next_info = cyber_herd_item['next_headbutt_info']
            required_sats = next_info.get('required_sats', 10)
            next_victim_name = next_info.get('victim_name', 'Anon')
            
            # Generate a random headbutt info message for the next victim
            next_headbutt_message = random.choice(list(headbutt_info_dict.values()))
            next_headbutt_text = f" {next_headbutt_message.format(required_sats=required_sats, victim_name=next_victim_name)}"
        
        tracked_reference = cyber_herd_item.get("tracked_event_reference") if cyber_herd_item else None
        if not tracked_reference:
            tracked_reference = format_nostr_event_reference(event_id)
        nostr_attacker_name = tracked_reference or attacker_nprofile or attacker_name

        # Create Nostr message with event reference fallback
        nostr_message_content = template.format(
            attacker_name=nostr_attacker_name,
            attacker_amount=attacker_amount,
            victim_name=victim_nprofile if victim_nprofile else victim_name,
            victim_amount=victim_amount
        ) + next_headbutt_text
        
        # Strip promotional URL for NIP-53 chat messages
        if reply_to_30311_event and reply_to_30311_a_tag:
            nostr_message_content = nostr_message_content.replace("\n\n https://lightning-goats.com\n\n", "")
        
        # Create client message with display names
        client_message = template.format(
            attacker_name=attacker_name,
            attacker_amount=attacker_amount,
            victim_name=victim_name,
            victim_amount=victim_amount
        ) + next_headbutt_text
        
        # Create Nostr command for headbutt success - reply to the cyberherd note that was zapped
        command = (
            f'{NAK_PATH} event --sec {nos_sec} --kind {1311 if (reply_to_30311_event and reply_to_30311_a_tag) else 1} -c "{nostr_message_content}" '
            f'-t e="{event_id};wss://lnb.bolverker.com/nostrrelay/666;root" '
            f'-p {attacker_pubkey} -p {victim_pubkey} '
        )
        
        # Add 30311 event reference tags if provided (NIP-53 compliant)
        if reply_to_30311_event and reply_to_30311_a_tag:
            command += f' -t a={reply_to_30311_a_tag} -t e={reply_to_30311_event}'
        
        command += f' {RELAY_URLS}'
        
        # Override message for client formatting
        message = client_message

    elif event_type == "headbutt_failure":
        # Handle headbutt failure message formatting
        attacker_name = cyber_herd_item.get("attacker_name", "Anon")
        attacker_amount = cyber_herd_item.get("attacker_amount", 0)
        required_amount = cyber_herd_item.get("required_amount", 0)
        victim_name = cyber_herd_item.get("victim_name", "Anon")
        victim_amount = cyber_herd_item.get("victim_amount", 0)
        attacker_pubkey = cyber_herd_item.get("attacker_pubkey", "")
        victim_pubkey = cyber_herd_item.get("victim_pubkey", "")
        event_id = cyber_herd_item.get("event_id", "")
        attacker_nprofile = cyber_herd_item.get("attacker_nprofile", "")
        victim_nprofile = cyber_herd_item.get("victim_nprofile", "")
        
        # Ensure nprofiles are well-formed
        if attacker_nprofile and not attacker_nprofile.startswith("nostr:"):
            attacker_nprofile = f"nostr:{attacker_nprofile}"
        if victim_nprofile and not victim_nprofile.startswith("nostr:"):
            victim_nprofile = f"nostr:{victim_nprofile}"
        
        tracked_reference = cyber_herd_item.get("tracked_event_reference") if cyber_herd_item else None
        if not tracked_reference:
            tracked_reference = format_nostr_event_reference(event_id)
        nostr_attacker_name = tracked_reference or attacker_nprofile or attacker_name

        # Create Nostr message with event reference fallback
        nostr_message_content = template.format(
            attacker_name=nostr_attacker_name,
            attacker_amount=attacker_amount,
            victim_name=victim_nprofile if victim_nprofile else victim_name,
            victim_amount=victim_amount,
            required_amount=required_amount
        )
        
        # Strip promotional URL for NIP-53 chat messages
        if reply_to_30311_event and reply_to_30311_a_tag:
            nostr_message_content = nostr_message_content.replace("\n\n https://lightning-goats.com\n\n", "")
        
        # Create client message with display names
        client_message = template.format(
            attacker_name=attacker_name,
            attacker_amount=attacker_amount,
            victim_name=victim_name,
            victim_amount=victim_amount,
            required_amount=required_amount
        )
        
        # Create Nostr command for headbutt failure - reply to the cyberherd note that was zapped
        command = (
            f'{NAK_PATH} event --sec {nos_sec} --kind {1311 if (reply_to_30311_event and reply_to_30311_a_tag) else 1} -c "{nostr_message_content}" '
            f'-t e="{event_id};wss://lnb.bolverker.com/nostrrelay/666;root" '
            f'-p {attacker_pubkey} -p {victim_pubkey} '
        )
        
        # Add 30311 event reference tags if provided (NIP-53 compliant)
        if reply_to_30311_event and reply_to_30311_a_tag:
            command += f' -t a={reply_to_30311_a_tag} -t e={reply_to_30311_event}'
        
        command += f' {RELAY_URLS}'
        
        # Override message for client formatting
        message = client_message

    elif event_type == "cyber_herd_treats":
        # Handle cyber herd treats message formatting
        display_name = cyber_herd_item.get("display_name", "Anon")
        amount = cyber_herd_item.get("amount", 0)
        nprofile = cyber_herd_item.get("nprofile", "")
        
        # Ensure nprofile is well-formed
        if nprofile and not nprofile.startswith("nostr:"):
            nprofile = f"nostr:{nprofile}"
            
        message = template.format(
            name=nprofile if nprofile else display_name,
            new_amount=amount
        )
        nostr_message_content = message
        
        # Create simple command for treats - no specific event to reply to
        command = (
            f'{NAK_PATH} event --sec {nos_sec} -c "{nostr_message_content}" '
            f'-t t=CyberHerd -t t=Treats '
            f'{RELAY_URLS}'
        )

    elif event_type == "member_increase":
        # Handle existing member amount increase message formatting
        display_name = cyber_herd_item.get("display_name", "Anon")
        event_id = cyber_herd_item.get("event_id", "")
        pub_key = cyber_herd_item.get("pubkey", "")
        nprofile = cyber_herd_item.get("nprofile", "")
        amount = cyber_herd_item.get("amount", 0)  # This is the new total
        new_zap_amount = cyber_herd_item.get("new_zap_amount", 0)  # This is the increase amount
        
        # Ensure nprofile is well-formed
        if nprofile and not nprofile.startswith("nostr:"):
            nprofile = f"nostr:{nprofile}"
            
        # Format the message for nostr
        nostr_message_content = template.format(
            member_name=nprofile if nprofile else display_name,
            increase_amount=new_zap_amount,
            new_total=amount
        )
        
        # Strip promotional URL for NIP-53 chat messages
        if reply_to_30311_event and reply_to_30311_a_tag:
            nostr_message_content = nostr_message_content.replace("\n\n https://lightning-goats.com\n\n", "")
        
        command = (
            f'{NAK_PATH} event --sec {nos_sec} --kind {1311 if (reply_to_30311_event and reply_to_30311_a_tag) else 1} -c "{nostr_message_content}" '
            f'-t e="{event_id};wss://lnb.bolverker.com/nostrrelay/666;root" '
            f'-p {pub_key} '
        )
        
        # Add 30311 event reference tags if provided (NIP-53 compliant)
        if reply_to_30311_event and reply_to_30311_a_tag:
            command += f' -t a={reply_to_30311_a_tag} -t e={reply_to_30311_event}'
        
        command += f' {RELAY_URLS}'
        
        # Also format message for client display with display name
        message = template.format(
            member_name=display_name,
            increase_amount=new_zap_amount,
            new_total=amount
        )

    elif event_type == "daily_reset":
        # Simple message for daily reset, no special formatting needed
        message = template
        
    elif event_type == "herd_reset":
        # Simple message for herd reset, no special formatting needed
        message = template
        
    elif event_type in ["feeding_regular", "feeding_bonus", "feeding_remainder", "feeding_fallback"]:
        # Feeding messages support display_name and amount formatting
        display_name = cyber_herd_item.get("display_name", "member") if cyber_herd_item else "member"
        amount = int(new_amount) if new_amount else 0
        
        message = template.format(
            new_amount=amount,
            display_name=display_name
        )

    elif event_type == "payment_metrics":
        # Format payment metrics data using the dedicated formatter
        if cyber_herd_item:
            formatted_message = format_payment_metrics_message(cyber_herd_item)
            message = formatted_message if formatted_message else template
        else:
            message = template

    elif event_type == "system_status":
        # Format system status data using the dedicated formatter
        if cyber_herd_item:
            formatted_message = format_system_status_message(cyber_herd_item)
            message = formatted_message if formatted_message else template
        else:
            message = template

    elif event_type == "weather_status":
        # Format weather data using the dedicated formatter
        if cyber_herd_item:
            formatted_message = format_weather_message(cyber_herd_item)
            message = formatted_message if formatted_message else template
        else:
            message = template

    # Helper to run the command
    async def execute_command(command):
        if TEST_COMMANDS:
            logger.info(f"🧪 TEST MODE: Would execute command: {command}")
            # Return a mock successful response for testing
            return '{"id": "test-event-id-12345"}'
        
        process = await asyncio.create_subprocess_shell(
            command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            logger.error(f"Command failed with return code {process.returncode}: {stderr.decode()}")
            return None
        else:
            logger.info(f"Command executed successfully: {stdout.decode()}")
            return stdout.decode()

    command_output = None
    if command:
        logger.info(f"Executing Nostr command: {command}")
        raw_output = await execute_command(command)
        command_output = extract_id_from_stdout(raw_output) if raw_output else None

    client_message = await format_client_message(message, event_type, selected_goats_data)

    return client_message, command_output


async def format_client_message(message: str, event_type: str, goat_data: Optional[List[dict]] = None):
    """
    Format a given message to all connected WebSocket clients in JSON.
    
    Args:
        message: The message content to send
        event_type: The type of event (e.g., "cyber_herd", "sats_received", "feeder_triggered", etc.)
        goat_data: Optional list of goat data with name and imageUrl for accordion display
    """

    # Create base message object
    json_obj = {
        "type": event_type,
        "message": message
    }
    
    # Add goat data if available (for sats_received messages that show goats in accordion)
    if goat_data:
        json_obj["goats"] = goat_data
    
    # Wrap the message in a JSON object with type and message fields
    json_message = json.dumps(json_obj)

    return json_message


def format_payment_metrics_message(data):
    """Format payment metrics data into a human-readable message."""
    try:
        parts = []
        
        if data.get('total_payments') is not None:
            parts.append(f"💰 {data['total_payments']} total payments")
        
        if data.get('cyberherd_payments_detected') is not None:
            parts.append(f"🐐 {data['cyberherd_payments_detected']} CyberHerd payments")
        
        if data.get('feeder_triggers') is not None:
            parts.append(f"⚡ {data['feeder_triggers']} feeder triggers")
        
        if data.get('failed_payments') is not None and data['failed_payments'] > 0:
            parts.append(f"❌ {data['failed_payments']} failed payments")
        
        return ' • '.join(parts) if parts else None
    except Exception as error:
        logger.error(f"Error formatting payment metrics message: {error}")
        return None


def format_system_status_message(data):
    """Format system status data into a human-readable message."""
    try:
        parts = []
        
        if data.get('current_balance') is not None and data.get('trigger_amount') is not None:
            remaining = max(data['trigger_amount'] - data['current_balance'], 0)
            parts.append(f"⚡ {remaining} sats until next feeding")
        
        if data.get('active_connections') is not None:
            parts.append(f"👥 {data['active_connections']} active connections")
        
        if data.get('uptime_hours') is not None:
            hours = round(data['uptime_hours'] * 10) / 10
            parts.append(f"⏱️ {hours}h uptime")
        
        if data.get('cyberherd_spots') is not None:
            parts.append(f"🐐 {data['cyberherd_spots']} CyberHerd spots available")
        
        return ' • '.join(parts) if parts else None
    except Exception as error:
        logger.error(f"Error formatting system status message: {error}")
        return None


def format_weather_message(data):
    """Format weather data into a human-readable message."""
    try:
        parts = []
        
        if data.get('temperature_f') is not None:
            parts.append(f"🌡️ {data['temperature_f']}°F")
        
        if data.get('humidity') is not None:
            parts.append(f"💧 {data['humidity']}% humidity")
        
        if data.get('wind_speed') is not None:
            wind_part = f"wind 💨 {data['wind_speed']} mph"
            if data.get('wind_direction'):
                wind_part += f" {data['wind_direction']}"
            parts.append(wind_part)
        
        if data.get('uv_index') is not None:
            uv_level = ''
            uv_index = data['uv_index']
            if uv_index >= 8:
                uv_level = ' (very high!)'
            elif uv_index >= 6:
                uv_level = ' (high)'
            elif uv_index >= 3:
                uv_level = ' (moderate)'
            else:
                uv_level = ' (low)'
            parts.append(f"☀️ UV {uv_index}{uv_level}")
        
        return f"🌤️ Weather: {' • '.join(parts)}" if parts else None
    except Exception as error:
        logger.error(f"Error formatting weather message: {error}")
        return None


# WebSocket Client Messaging
# These functions will be set by main.py to handle WebSocket communication
_websocket_clients = None
_clients_lock = None

def set_websocket_clients(clients_set, lock):
    """Set the WebSocket clients and lock from main.py"""
    global _websocket_clients, _clients_lock
    _websocket_clients = clients_set
    _clients_lock = lock

async def send_to_websocket_clients(message: str):
    """Send a message to all connected WebSocket clients."""
    if not message:
        logger.warning("Attempted to send an empty message to WebSocket clients. Skipping.")
        return

    if not _websocket_clients or not _clients_lock:
        logger.warning("WebSocket clients not initialized. Cannot send message.")
        return

    async with _clients_lock:
        if _websocket_clients:
            logger.info(f"Broadcasting message to {len(_websocket_clients)} WebSocket clients: {message}")
            # Create a copy to avoid issues with modifying the set while iterating
            clients_to_send = _websocket_clients.copy()
            failed_clients = set()
            
            for client in clients_to_send:
                try:
                    await client.send_text(message)
                except Exception as e:
                    logger.warning(f"Failed to send message to WebSocket client, marking for removal: {e}")
                    failed_clients.add(client)
            
            # Remove failed clients in a separate operation to avoid race conditions
            for failed_client in failed_clients:
                _websocket_clients.discard(failed_client)
    
    if not _websocket_clients:
        logger.debug("No connected WebSocket clients to send messages to.")

async def send_cyberherd_update(newest_pubkey: str = None, database=None):
    """Send updated CyberHerd member list to all connected clients for accordion display."""
    if not database:
        logger.error("Database connection required for CyberHerd update")
        return
        
    try:
        # Get all current CyberHerd members
        query = "SELECT * FROM cyber_herd WHERE is_active = 1 ORDER BY amount DESC, payouts DESC"
        herd_members = await database.fetch_all(query)
        
        if not herd_members:
            logger.debug("No CyberHerd members to send.")
            return
        
        # Format member data for frontend accordion display
        formatted_members = []
        for member in herd_members:
            # Convert database row to dict to use .get() method
            member_dict = dict(member)
            member_data = {
                "pubkey": member_dict.get("pubkey", ""),
                "display_name": member_dict.get("display_name", "Anon"),
                "name": member_dict.get("display_name", "Anon"),  # Alias for display_name
                "picture": member_dict.get("picture", ""),
                "imageUrl": member_dict.get("picture", ""),  # Alias for picture
                "amount": member_dict.get("amount", 0),
                "payouts": member_dict.get("payouts", 0),
                "kinds": member_dict.get("kinds", ""),
                "timestamp": member_dict.get("notified", 0),
                "is_newest": newest_pubkey and member_dict.get("pubkey") == newest_pubkey
            }
            formatted_members.append(member_data)
        
        # Create cyber_herd message for frontend
        cyberherd_message = {
            "type": "cyber_herd",
            "members": formatted_members,
            "newest_pubkey": newest_pubkey,
            "total_members": len(formatted_members)
        }
        
        await send_to_websocket_clients(json.dumps(cyberherd_message))
        logger.info(f"Sent CyberHerd update with {len(formatted_members)} members")
        
    except Exception as e:
        logger.error(f"Error sending CyberHerd update: {e}")
