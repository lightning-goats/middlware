import asyncio
import json
import random
import logging
import os
from typing import Any, Optional

from messages import (
    sats_received_dict,
    feeder_trigger_dict,
    variations,
    thank_you_variations,
    cyber_herd_dict,
    cyber_herd_info_dict,
    cyber_herd_treats_dict,
    headbutt_info_dict,
    headbutt_success_dict,
    headbutt_failure_dict,
    interface_info_dict
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


async def make_messages(
    nos_sec: str,
    new_amount: float,
    difference: float,
    event_type: str,
    cyber_herd_item: dict = None,
    spots_remaining: int = 0,
):
    global notified

    goat_names_dict = {
        "Dexter":  [
            "nostr:nprofile1qqsw4zlzyfx43mc88psnlse8sywpfl45kuap9dy05yzkepkvu6ca5wg7qyak5",
            "ea8be2224d58ef0738613fc327811c14feb4b73a12b48fa1056c86cce6b1da39"
        ],
        "Rowan":   [
            "nostr:nprofile1qqs2w94r0fs29gepzfn5zuaupn969gu3fstj3gq8kvw3cvx9fnxmaugwur22r",
            "a716a37a60a2a32112674173bc0ccba2a3914c1728a007b31d1c30c54ccdbef1"
        ],
        "Nova":    [
            "nostr:nprofile1qqsrzy7clymq5xwcfhh0dfz6zfe7h63k8r0j8yr49mxu6as4yv2084s0vf035",
            "3113d8f9360a19d84deef6a45a1273ebea3638df2390752ecdcd76152314f3d6"
        ],
        "Cosmo":   [
            "nostr:nprofile1qqsq6n8u7dzrnhhy7xy78k2ee7e4wxlgrkm5g2rgjl3napr9q54n4ncvkqcsj",
            "0d4cfcf34439dee4f189e3d959cfb3571be81db744286897e33e8465052b3acf"
        ],
        "Newton":  [
            "nostr:nprofile1qqszdsnpyzwhjcqads3hwfywt5jfmy85jvx8yup06yq0klrh93ldjxc26lmyx",
            "26c261209d79601d6c2377248e5d249d90f4930c72702fd100fb7c772c7ed91b"
        ]
    }

    message_dict = {
        "sats_received": sats_received_dict,
        "feeder_triggered": feeder_trigger_dict,
        "cyber_herd": cyber_herd_dict,
        "cyber_herd_info": cyber_herd_info_dict,
        "cyber_herd_treats": cyber_herd_treats_dict,
        "headbutt_info": headbutt_info_dict,
        "headbutt_success": headbutt_success_dict,
        "headbutt_failure": headbutt_failure_dict,
        "interface_info": interface_info_dict,
    }

    message_templates = message_dict.get(event_type, None)
    if not message_templates:
        logger.error(f"Event type '{event_type}' not recognized.")
        return "Event type not recognized.", None

    # Randomly pick a template from whichever dict was selected
    template = random.choice(list(message_templates.values()))
    command = None

    # -- Handle each event_type separately --
    if event_type == "cyber_herd":
        display_name = cyber_herd_item.get("display_name", "anon")
        event_id = cyber_herd_item.get("event_id", "")
        pub_key = cyber_herd_item.get("pubkey", "")
        nprofile = cyber_herd_item.get("nprofile", "")
        amount = cyber_herd_item.get("amount", 0)

        # Decide on a "thank you" snippet
        if amount == 0:
            thanks_part = ""
        else:
            chosen_variation = random.choice(thank_you_variations)
            thanks_part = chosen_variation.format(new_amount=amount)

        # Ensure nprofile is well-formed
        if nprofile and not nprofile.startswith("nostr:"):
            nprofile = f"nostr:{nprofile}"

        # Spots info
        spots_info = ""
        if spots_remaining > 1:
            spots_info = f"⚡ {spots_remaining} more spots available. ⚡"
        elif spots_remaining == 1:
            spots_info = f"⚡ {spots_remaining} more spot available. ⚡"

        # Format the message for nostr
        message = (
            template.format(
                thanks_part=thanks_part,
                name=nprofile,
                difference=difference,
                new_amount=amount,
                event_id=event_id
            )
            + spots_info
        )

        command = (
            f'/usr/local/bin/nak event --sec {nos_sec} -c "{message}" '
            f'--tag e="{event_id};wss://lnb.bolverker.com/nostrrelay/666;root" '
            f'-p {pub_key} '
            f'wss://relay.damus.io wss://relay.artx.market/ wss://relay.primal.net/ ws://127.0.0.1:3002/nostrrelay/666'
        )

        message = (
            template.format(
                thanks_part=thanks_part,
                name=display_name,
                difference=difference,
                new_amount=amount,
                event_id=event_id
            )
            + spots_info
        )

    elif event_type in ["sats_received", "feeder_triggered"]:
        # Existing logic for handling those events
        selected_goats = get_random_goat_names(goat_names_dict)
        goat_names = join_with_and([name for name, _, _ in selected_goats])
        goat_nprofiles = join_with_and([nprofile for _, nprofile, _ in selected_goats])
        goat_pubkeys = [pubkey for _, _, pubkey in selected_goats]

        variation_message = random.choice(list(variations.values()))
        difference_message = variation_message.format(difference=difference)

        # First formatting includes goat_nprofiles
        message = template.format(
            new_amount=new_amount,    # or amount, if you prefer
            goat_name=goat_nprofiles,
            difference_message=difference_message
        )

        pubkey_part = " ".join(f"-p {pubkey}" for pubkey in goat_pubkeys)
        command = (
            f'/usr/local/bin/nak event --sec {nos_sec} -c "{message}" '
            f' --tag t=LightningGoats {pubkey_part} '
            f'wss://relay.damus.io wss://relay.artx.market/ wss://relay.primal.net/ ws://127.0.0.1:3002/nostrrelay/666'
        )

        # Then reformat to show goat_names in the final message
        message = template.format(
            new_amount=new_amount,
            goat_name=goat_names,
            difference_message=difference_message
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
        nostr_message = template.format(
            required_sats=required_sats,
            victim_name=victim_nprofile if victim_nprofile else victim_name
        )
        
        # Create client message with display name
        client_message = template.format(
            required_sats=required_sats,
            victim_name=victim_name
        )
        
        # Use nostr_message for the command
        message = nostr_message
        
        # Create Nostr command for headbutt info - reply to the cyberherd note
        if event_id:
            command = (
                f'/usr/local/bin/nak event --sec {nos_sec} -c "{message}" '
                f'--tag e="{event_id};wss://lnb.bolverker.com/nostrrelay/666;root" '
                f'-p {victim_pubkey} '
                f'wss://relay.damus.io wss://relay.artx.market/ wss://relay.primal.net/ ws://127.0.0.1:3002/nostrrelay/666'
            )
        else:
            # Fallback to standalone note if no event_id available
            command = (
                f'/usr/local/bin/nak event --sec {nos_sec} -c "{message}" '
                f'--tag t=CyberHerd --tag t=HeadbuttInfo '
                f'wss://relay.damus.io wss://relay.artx.market/ wss://relay.primal.net/ ws://127.0.0.1:3002/nostrrelay/666'
            )
        
        # Override message for client formatting
        message = client_message

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
        
        # Create Nostr message with nprofiles
        nostr_message = template.format(
            attacker_name=attacker_nprofile if attacker_nprofile else attacker_name,
            attacker_amount=attacker_amount,
            victim_name=victim_nprofile if victim_nprofile else victim_name,
            victim_amount=victim_amount
        )
        
        # Create client message with display names
        client_message = template.format(
            attacker_name=attacker_name,
            attacker_amount=attacker_amount,
            victim_name=victim_name,
            victim_amount=victim_amount
        )
        
        # Use nostr_message for the command
        message = nostr_message
        
        # Create Nostr command for headbutt success - reply to the cyberherd note that was zapped
        command = (
            f'/usr/local/bin/nak event --sec {nos_sec} -c "{message}" '
            f'--tag e="{event_id};wss://lnb.bolverker.com/nostrrelay/666;root" '
            f'-p {attacker_pubkey} -p {victim_pubkey} '
            f'wss://relay.damus.io wss://relay.artx.market/ wss://relay.primal.net/ ws://127.0.0.1:3002/nostrrelay/666'
        )
        
        # Override message for client formatting
        message = client_message

    elif event_type == "headbutt_failure":
        # Handle headbutt failure message formatting
        attacker_name = cyber_herd_item.get("attacker_name", "Anon")
        attacker_amount = cyber_herd_item.get("attacker_amount", 0)
        required_amount = cyber_herd_item.get("required_amount", 0)
        attacker_pubkey = cyber_herd_item.get("attacker_pubkey", "")
        event_id = cyber_herd_item.get("event_id", "")
        attacker_nprofile = cyber_herd_item.get("attacker_nprofile", "")
        
        # Ensure nprofile is well-formed
        if attacker_nprofile and not attacker_nprofile.startswith("nostr:"):
            attacker_nprofile = f"nostr:{attacker_nprofile}"
        
        # Create Nostr message with nprofile
        nostr_message = template.format(
            attacker_name=attacker_nprofile if attacker_nprofile else attacker_name,
            attacker_amount=attacker_amount,
            required_amount=required_amount
        )
        
        # Create client message with display name
        client_message = template.format(
            attacker_name=attacker_name,
            attacker_amount=attacker_amount,
            required_amount=required_amount
        )
        
        # Use nostr_message for the command
        message = nostr_message
        
        # Create Nostr command for headbutt failure - reply to the cyberherd note that was zapped
        command = (
            f'/usr/local/bin/nak event --sec {nos_sec} -c "{message}" '
            f'--tag e="{event_id};wss://lnb.bolverker.com/nostrrelay/666;root" '
            f'-p {attacker_pubkey} '
            f'wss://relay.damus.io wss://relay.artx.market/ wss://relay.primal.net/ ws://127.0.0.1:3002/nostrrelay/666'
        )
        
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
        
        # Create simple command for treats - no specific event to reply to
        command = (
            f'/usr/local/bin/nak event --sec {nos_sec} -c "{message}" '
            f'--tag t=CyberHerd --tag t=Treats '
            f'wss://relay.damus.io wss://relay.artx.market/ wss://relay.primal.net/ ws://127.0.0.1:3002/nostrrelay/666'
        )

    # Helper to run the command
    async def execute_command(command):
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
        command_output = await execute_command(command)

    client_message = await format_client_message(message, event_type)

    return client_message, command_output


async def format_client_message(message: str, event_type):
    """
    Format a given message to all connected WebSocket clients in JSON.
    
    Args:
        message: The message content to send
        event_type: The type of event (e.g., "cyber_herd", "sats_received", "feeder_triggered", etc.)
    """

    
    # Wrap the message in a JSON object with type and message fields
    json_message = json.dumps({
        "type": event_type,
        "message": message
    })

    return json_message

