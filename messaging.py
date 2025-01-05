import asyncio
import random
import logging
import json
from messages import (
    sats_received_dict,
    feeder_trigger_dict,
    variations,
    cyber_herd_dict,
    cyber_herd_info_dict,
    cyber_herd_treats_dict,
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
        "Dexter": ["nostr:nprofile1qqsw4zlzyfx43mc88psnlse8sywpfl45kuap9dy05yzkepkvu6ca5wg7qyak5", "ea8be2224d58ef0738613fc327811c14feb4b73a12b48fa1056c86cce6b1da39"],
        "Rowan": ["nostr:nprofile1qqs2w94r0fs29gepzfn5zuaupn969gu3fstj3gq8kvw3cvx9fnxmaugwur22r", "a716a37a60a2a32112674173bc0ccba2a3914c1728a007b31d1c30c54ccdbef1"],
        # Add other goats here
    }

    message_dict = {
        "sats_received": sats_received_dict,
        "feeder_triggered": feeder_trigger_dict,
        "cyber_herd": cyber_herd_dict,
        "cyber_herd_info": cyber_herd_info_dict,
        "interface_info": interface_info_dict,
    }

    message_templates = message_dict.get(event_type, None)

    if not message_templates:
        logger.error(f"Event type '{event_type}' not recognized.")
        return "Event type not recognized.", None

    template = random.choice(list(message_templates.values()))
    command = None

    # Handling for different event types
    if event_type == "cyber_herd":
        display_name = cyber_herd_item.get("display_name", "anon")
        event_id = cyber_herd_item.get("event_id", "")  # The zapped note ID
        pub_key = cyber_herd_item.get("pubkey", "")  # The pubkey of the new member
        nprofile = cyber_herd_item.get("nprofile", "")

        if nprofile and not nprofile.startswith("nostr:"):
            nprofile = f"nostr:{nprofile}"

        spots_info = ""
        if spots_remaining > 1:
            spots_info = f"⚡ {spots_remaining} more spots available. ⚡"
        elif spots_remaining == 1:
            spots_info = f"⚡ {spots_remaining} more spot available. ⚡"

        message = template.format(name=display_name, difference=difference, event_id=event_id) + spots_info

        # Add the `e` tag to reply to the root note (CyberHerd note that was zapped)
        command = (
            f'/usr/local/bin/nak event --sec {nos_sec} -c "{message}" '
            f'--tag e="{event_id};wss://lnb.bolverker.com/nostrrelay/666;root" '
            f'--tag t="CyberHerd" '
            f'-p {pub_key} '
            f'wss://relay.damus.io wss://relay.artx.market/ wss://relay.primal.net/ ws://127.0.0.1:3002/nostrrelay/666'
        )

    elif event_type in ["sats_received", "feeder_triggered"]:
        selected_goats = get_random_goat_names(goat_names_dict)
        goat_names = join_with_and([name for name, _, _ in selected_goats])
        goat_nprofiles = join_with_and([nprofile for _, nprofile, _ in selected_goats])
        goat_pubkeys = [pubkey for _, _, pubkey in selected_goats]

        variation_message = random.choice(list(variations.values()))
        difference_message = variation_message.format(difference=difference)

        message = template.format(new_amount=new_amount, goat_name=goat_nprofiles, difference_message=difference_message)
        pubkey_part = " ".join(f"-p {pubkey}" for pubkey in goat_pubkeys)

        command = f'/usr/local/bin/nak event --sec {nos_sec} -c "{message}"  --tag t=LightningGoats {pubkey_part} wss://relay.damus.io wss://relay.artx.market/ wss://relay.primal.net/ ws://127.0.0.1:3002/nostrrelay/666'

        message = template.format(new_amount=new_amount, goat_name=goat_names, difference_message=difference_message)

    elif event_type == "interface_info":
        message = template.format(new_amount=0, goat_name="", difference_message="")
        command = None  # No command execution needed for interface info

    async def execute_command(command):
        logger.info(f"Executing command: {command}")
        process = await asyncio.create_subprocess_shell(
            command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            logger.error(f"Command failed with error: {stderr.decode()}")
            return stderr.decode()
        else:
            logger.info(f"Command output: {stdout.decode()}")
            return stdout.decode()

    command_output = None
    if command:
        command_output = await execute_command(command)

    return message, command_output
