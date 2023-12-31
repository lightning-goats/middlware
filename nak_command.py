import asyncio
import random
import subprocess
import logging
from messages import sats_received_dict, feeder_trigger_dict, variations, cyber_herd_dict

# Initialize a logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_random_goat_names(goat_names):
    selected_names = random.sample(goat_names, random.randint(1, len(goat_names)))
    if len(selected_names) > 1:
        return ', '.join(selected_names[:-1]) + ' and ' + selected_names[-1]
    else:
        return selected_names[0]

async def run_nostr_command(nos_sec: str, new_amount: float, difference: float, event_type: str, nostr: dict = None):
    goat_names = ["#Dexter", "#Rowan", "#Gizmo", "#Nova", "#Cosmo", "#Newton"]
    command = None
    
    if event_type == "sats_received":
        message_dict = sats_received_dict
    elif event_type == "feeder_triggered":
        message_dict = feeder_trigger_dict
    elif event_type == "cyber_herd":
        message_dict = cyber_herd_dict

    message = message_dict[random.randint(0, len(message_dict) - 1)]
    random_goat_names = get_random_goat_names(goat_names)
    variation_message = variations[random.randint(0, len(variations) - 1)]
    difference_message = variation_message.format(difference=difference)

    if event_type == "cyber_herd":
        cyber_herd_message = message
        cyber_herd_message = cyber_herd_message.format(name=nostr['npub'], difference=difference)
        message = message.format(new_amount=new_amount, cyber_herd_message=cyber_herd_message, nostr['npub'], difference=difference)
        
        event_id = nostr['event_id']
        author_id  = nostr['author_pubkey']
        pub_key = nostr['pubkey']
        
        #reply to original note with message
        command = f'/usr/local/bin/nak event --sec {nos_sec} -c "{message}" --tag t=LightningGoats -e {event_id} -p {author_id} -p {pubkey} wss://lnb.bolverker.com/nostrclient/api/v1/relay'
    else:
        message = message.format(new_amount=new_amount, goat_name=random_goat_names, difference_message=difference_message)
        command = f'/usr/local/bin/nak event --sec {nos_sec} -c "{message}" --tag t=LightningGoats wss://lnb.bolverker.com/nostrclient/api/v1/relay'

    if command != None:
        # Start the subprocess
        process = await asyncio.create_subprocess_shell(
            command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )

        # Wait for the command to complete
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            logger.error(f"Command failed with error: {stderr.decode()}")
        else:
            logger.info(f"Command output: {stdout.decode()}")
            
    return message

