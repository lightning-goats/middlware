import asyncio
import random
import subprocess
import logging

# Initialize a logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def run_nostril_command(nos_sec: str, new_amount: float, difference: float, event_type: str):
    goat_names = ["Dexter", "Rowan", "Gizmo", "Nova", "Cosmo", "Newton"]

    sats_received_dict = {
    0: "The herd has received {new_amount} sats. \n\n{difference_message}\n\n Fun fact: Did you know goats, like {goat_name}, have rectangular pupils? \n\nWatch live and get up to date progress at:  https://lightning-goats.com",
    1: "{new_amount} sats added to the goat fund! \n\n{difference_message}\n\n Goat fact: Goats like {goat_name} can be taught their name and to come when called! \n\nWatch live and get up to date progress at:  https://lightning-goats.com",
    2: "A donation of {new_amount} sats have been received! \n\n{difference_message}\n\n Did you know that goats, including {goat_name}, have excellent balance? They can climb and maintain balance in the most precarious places. \n\nWatch live and get up to date progress at:  https://lightning-goats.com",
    3: "We're {new_amount} sats closer to feeding time! \n\n{difference_message}\n\n Interesting fact: Goats, like {goat_name}, are very social animals and live in groups called herds. \n\nWatch live and get up to date progress at:  https://lightning-goats.com",
    4: "Great news for the herd! We've just received {new_amount} sats. \n\n{difference_message}\n\n Goat fact: Goats like {goat_name} can jump nearly 5 feet high! \n\nWatch live and get up to date progress at:  https://lightning-goats.com",
    5: "The herd has benefited from your generosity! {new_amount} sats has just been donated. \n\n{difference_message}\n\n Did you know? Goats, like {goat_name}, were one of the first animals to be tamed by humans more than 9,000 years ago. \n\nWatch live and get up to date progress at:  https://lightning-goats.com",
    6: "Thank you for your generosity! Your donation of {new_amount} sats brings us closer to our goal. \n\n{difference_message}\n\n Fun fact: Goats like {goat_name} have an incredible ability to adapt to various climates and environments. \n\nWatch live and get up to date progress at:  https://lightning-goats.com",
    7: "Your gift of {new_amount} sats brings joy to the herd. \n\n{difference_message}\n\n Interesting fact: {goat_name} and other goats are natural explorers and are curious about their surroundings. \n\nWatch live and get up to date progress at:  https://lightning-goats.com",
    8: "{new_amount} sats received! \n\n{difference_message}\n\n Fun fact: Goats have incredible climbing abilities. {goat_name} could probably climb a tree if given the chance! \n\nWatch live and get up to date progress at:  https://lightning-goats.com",
    9: "Your contribution of {new_amount} sats gets us closer to feeding time! \n\n{difference_message}\n\n Did you know? Goats like {goat_name} can remember complex tasks for years. \n\nWatch live and get up to date progress at:  https://lightning-goats.com",
    10: "Thank you for the {new_amount} sats! \n\n{difference_message}\n\n Fun fact: Goats like {goat_name} have been proven to be as smart as dogs in some areas. \n\nWatch live and get up to date progress at:  https://lightning-goats.com",
    11: "A donation of {new_amount} sats! \n\n{difference_message}\n\n Interesting fact: {goat_name} and other goats can be quite affectionate and enjoy being petted. \n\nWatch live and get up to date progress at:  https://lightning-goats.com",
    12: "We've received {new_amount} sats from a generous donor! \n\n{difference_message}\n\n Did you know? Goats are actually quite good swimmers, much like {goat_name}! \n\nWatch live and get up to date progress at:  https://lightning-goats.com",
    13: "Someone just sent {new_amount} sats! \n\n{difference_message}\n\n Fun fact: Did you know {goat_name} and other goats have accents, just like humans? \n\nWatch live and get up to date progress at:  https://lightning-goats.com",
    14: "We're {new_amount} sats closer to feeding time! \n\n{difference_message}\n\n Goat fact: Goats like {goat_name} have around 320° field of vision! \n\nWatch live and get up to date progress at:  https://lightning-goats.com",
    15: "Thank you for your donation of {new_amount} sats! \n\n{difference_message}\n\n Did you know? {goat_name} and other goats can distinguish between human expressions and are drawn to happy faces. \n\nWatch live and get up to date progress at:  https://lightning-goats.com",
    16: "Your {new_amount} sats donation brings us closer to our goal. \n\n{difference_message}\n\n Goat fact: Goats like {goat_name} are not just cute, they are also environmentally friendly due to their preference for a diet of weeds. \n\nWatch live and get up to date progress at:  https://lightning-goats.com",
    17: "We've just received {new_amount} sats. \n\n{difference_message}\n\n Fun fact: Did you know that goats like {goat_name} communicate with each other by bleating? \n\nWatch live and get up to date progress at:  https://lightning-goats.com",
    18: "A donation of {new_amount} sats has been received! \n\n{difference_message}\n\n Interesting fact: Just like {goat_name}, all goats have unique voices. \n\nWatch live and get up to date progress at:  https://lightning-goats.com",
    19: "We're {new_amount} sats closer to feeding time! \n\n{difference_message}\n\n Fun fact: Did you know that goats like {goat_name} use their sense of smell to locate other goats? \n\nWatch live and get up to date progress at:  https://lightning-goats.com",
    20: "Thank you for the {new_amount} sats! \n\n{difference_message}\n\n Goat fact: Did you know that goats like {goat_name} are naturally immune to certain diseases? \n\nWatch live and get up to date progress at:  https://lightning-goats.com",
    21: "Your generous donation of {new_amount} sats is appreciated! \n\n{difference_message}\n\n Goat fact: Goats like {goat_name} don't have teeth on their upper jaw, just a strong dental pad! \n\nWatch live and get up to date progress at:  https://lightning-goats.com",
    22: "{new_amount} sats have been added. \n\n{difference_message}\n\n Did you know? Goats like {goat_name} can rotate their ears to listen in any direction. \n\nWatch live and get up to date progress at:  https://lightning-goats.com",
    23: "Thanks for the {new_amount} sats! \n\n{difference_message}\n\n Watch live and get up to date progress at:  https://lightning-goats.com\n\nWatch live and get up to date progress at:  https://lightning-goats.com",
    24: "We received {new_amount} sats from you. \n\n{difference_message}\n\n Goat fact: Goats, like {goat_name}, have four stomach chambers which help them digest tough plants. \n\nWatch live and get up to date progress at:  https://lightning-goats.com",
    25: "Your donation of {new_amount} sats is heartwarming! \n\n{difference_message}\n\n Did you know? Goats like {goat_name} are known to be great escape artists due to their intelligence and curiosity. \n\nWatch live and get up to date progress at:  https://lightning-goats.com",
    26: "Thanks for donating {new_amount} sats! \n\n{difference_message}\n\n Interesting fact: While {goat_name} might enjoy it, goats are known to consume paper but they don't actually eat it as a part of their diet! \n\nWatch live and get up to date progress at:  https://lightning-goats.com",
    27: "{new_amount} sats received. \n\n{difference_message}\n\n Fun fact: Contrary to popular belief, goats like {goat_name} don't really eat tin cans! \n\nWatch live and get up to date progress at:  https://lightning-goats.com",
    28: "We're closer to our goal with your donation of {new_amount} sats! \n\n{difference_message}\n\n Goat fact: The beard of goats, like {goat_name}, is called a 'wattle'. \n\nWatch live and get up to date progress at:  https://lightning-goats.com",
    29: "Your {new_amount} sats will make a difference! \n\n{difference_message}\n\n Did you know? Goats like {goat_name} have horizontal slit-shaped pupils that help them watch over for predators. \n\nWatch live and get up to date progress at:  https://lightning-goats.com",
    30: "Thanks for the {new_amount} sats! \n\n{difference_message}\n\n Fun fact: 'Caprine' is the scientific term for things related to goats. So, {goat_name} is a caprine creature! \n\nWatch live and get up to date progress at:  https://lightning-goats.com",
    31: "You've donated {new_amount} sats. \n\n{difference_message}\n\n Goat fact: Some goats, can produce spider silk protein in their milk. \n\nWatch live and get up to date progress at:  https://lightning-goats.com",
    32: "Thanks for the {new_amount} sats! \n\n{difference_message}\n\n Did you know? Goats were among the first animals to travel to space in the early days of space exploration. \n\nWatch live and get up to date progress at:  https://lightning-goats.com",
    33: "We appreciate the {new_amount} sats! \n\n{difference_message}\n\n Fun fact: Goats have a knack for problem-solving and can work together in teams to accomplish tasks. Just like {goat_name} does! \n\nWatch live and get up to date progress at:  https://lightning-goats.com",
    34: "{new_amount} sats received! \n\n{difference_message}\n\n Goat fact: In many parts of the world, goat milk is more commonly consumed than cow's milk. \n\nWatch live and get up to date progress at:  https://lightning-goats.com",
    35: "Thank you for your {new_amount} sats! \n\n{difference_message}\n\n Did you know? Fainting goats don't really faint. Their muscles freeze for a few seconds when they're startled. But don't worry, {goat_name} is fine, because the Lightning Goat herd is made of Pygmy Goats and Kinder Goats. \n\nWatch live and get up to date progress at:  https://lightning-goats.com",
    36: "{new_amount} sats added to the feeder. \n\n{difference_message}\n\n Interesting fact: The world record for the largest goat horn span is over 13 feet! {goat_name} might not be a record holder, but they're special to us! \n\nWatch live and get up to date progress at:  https://lightning-goats.com",
    37: "We're grateful for the {new_amount} sats. \n\n{difference_message}\n\n Goat fact: Goats' hooves have a soft pad that allows them to climb rocky terrains easily. {goat_name} has those nifty hooves too! \n\nWatch live and get up to date progress at:  https://lightning-goats.com",
    38: "Your donation of {new_amount} sats is making a difference! \n\n{difference_message}\n\n Did you know? A group of goats is called a tribe or a trip. Maybe {goat_name} is planning a trip soon? \n\nWatch live and get up to date progress at:  https://lightning-goats.com",
    39: "{new_amount} sats received, thank you! \n\n{difference_message}\n\n Fun fact: Goats like {goat_name} use their tails to communicate. An upright tail often means a happy goat! \n\nWatch live and get up to date progress at:  https://lightning-goats.com",
    40: "Thanks for the {new_amount} sats! \n\n{difference_message}\n\n Goat fact: Goats' eyes have a rectangular pupil that allows them to see a panoramic view of their surroundings. So, {goat_name} can see a lot more than you'd think! \n\nWatch live and get up to date progress at:  https://lightning-goats.com",
    41: "{new_amount} sats added. Many thanks! \n\n{difference_message} \n\nDid you know? Goats like {goat_name} were considered sacred in ancient Egyptian culture. \n\nWatch live and get up to date progress at:  https://lightning-goats.com",
    42: "We've got {new_amount} sats richer, thanks to you! \n\n{difference_message} \n\nFun fact: While many believe goats will eat anything, they are actually quite picky eaters. {goat_name} has its favorites too! \n\nWatch live and get up to date progress at:  https://lightning-goats.com",
    43: "Every sats counts! Thanks for the {new_amount} sats. \n\n{difference_message} \n\nInteresting fact: Just like {goat_name}, goats can recognize their reflection in a mirror. Smart creatures, aren't they? \n\nWatch live and get up to date progress at:  https://lightning-goats.com",
    44: "Your generous {new_amount} sats will help a lot! \n\n{difference_message} \n\nDid you know? The lifespan of a domestic goat is around 15-18 years. We hope {goat_name} has many more happy years to come! \n\nWatch live and get up to date progress at:  https://lightning-goats.com",
    45: "We're thrilled to receive your {new_amount} sats! \n\n{difference_message} \n\nGoat fact: The goat is one of the 12 Chinese zodiac animals. Maybe {goat_name} was born in the Year of the Goat? \n\nWatch live and get up to date progress at:  https://lightning-goats.com",
    46: "Thanks for the sats! We've added {new_amount} to the account. \n\n{difference_message} \n\nInteresting tidbit: {goat_name} might agree, goats have a calming presence and are used in animal therapy sessions. \n\nWatch live and get up to date progress at:  https://lightning-goats.com",
    47: "Heartfelt thanks for the {new_amount} sats! \n\n{difference_message} \n\nFun fact: Goats have a special enzyme that allows them to break down toxic plants that other animals can't eat. So, {goat_name} is quite the survivor! \n\nWatch live and get up to date progress at:  https://lightning-goats.com",
    48: "Every sats is a step closer to our goal! Your {new_amount} is appreciated. \n\n{difference_message} \n\nDid you know? While goats are social animals, they also have individual personalities, just like {goat_name}. \n\nWatch live and get up to date progress at:  https://lightning-goats.com",
    49: "Cheers for the {new_amount} sats! \n\n{difference_message} \n\nInteresting fact: Some goats, possibly like {goat_name}, enjoy listening to music. Who knows, they might have a favorite tune! \n\nWatch live and get up to date progress at:  https://lightning-goats.com",
    50: "Thanks for the {new_amount} sats! \n\n{difference_message} \n\nGoat fact: In mythology, the goat often symbolizes fertility and vitality. {goat_name} sure brings life to our herd! \n\nWatch live and get up to date progress at:  https://lightning-goats.com"
}


    feeder_trigger_dict = {
    0: "Feeder Trigger Alert! Random plebs have banded together to feed the herd. {goat_name} is excited! Thank you! \n\nWatch live and get up to date progress at:  https://lightning-goats.com",
    1: "The herd has been fed thanks to generous contributors! {goat_name} enjoyed the snack! \n\nWatch live and get up to date progress at:  https://lightning-goats.com",
    2: "The goats got treats right now! Join the fun, watch live, and get up to date progress at:  https://lightning-goats.com. {goat_name} is getting his fill!",
    3: "Snack time! The herd, including {goat_name}, is munching away thanks to our contributors. \n\nWatch live and get up to date progress at:  https://lightning-goats.com",
    4: "Feeding time! {goat_name} is excited for his snack. A big thanks to everyone who contributed. \n\nWatch live and get up to date progress at:  https://lightning-goats.com",
    5: "Thanks to your contributions, {goat_name} and the rest of the herd are enjoying a feast! Watch live and get up to date progress at:  https://lightning-goats.com",
    6: "Food has arrived for the herd! Watch {goat_name} and the others enjoy their treats and get up to date progress at:  https://lightning-goats.com",
    7: "Happy goats over here! {goat_name} is particularly pleased with this round of feeding. Watch live and get up to date progress at:  https://lightning-goats.com",
    8: "Your contributions have made a meal possible for the herd! {goat_name} can't thank you enough. \n\nWatch live and get up to date progress at:  https://lightning-goats.com",
    9: "Feeder alert! Your contributions have filled up the feeding tray. {goat_name} is ready to eat! \n\nWatch live and get up to date progress at:  https://lightning-goats.com",
    10: "The herd is gathering for a meal, all thanks to you! {goat_name} is leading the charge. Join the fun aand watch live and get up to date progress at:  https://lightning-goats.com",
    11: "A generous crowd has provided a meal for the goats! {goat_name} is ready to tuck in. \n\nWatch live and get up to date progress at:  https://lightning-goats.com",
    12: "It's feeding time for the herd! {goat_name} and friends are happy and full, thanks to you. \n\nWatch live and get up to date progress at:  https://lightning-goats.com",
    13: "What's that sound? It's the dinner bell for the goats! {goat_name} is first in line. Thanks for contributing! \n\nWatch live and get up to date progress at:  https://lightning-goats.com",
    14: "Happy goats coming right up! Thanks to the contributions, {goat_name} is about to enjoy a hearty meal. \n\nWatch live and get up to date progress at:  https://lightning-goats.com",
    15: "It's a happy day for the herd! {goat_name} is tucking into a meal, thanks to your generosity. \n\nWatch live and get up to date progress at:  https://lightning-goats.com",
    16: "Feeding time is here! {goat_name} is enjoying the meal you've made possible. Watch live and get up to date progress at:  https://lightning-goats.com",
    17: "Dinner is served for the goats! Thanks to you, {goat_name} is full and content. \n\nWatch live and get up to date progress at:  https://lightning-goats.com",
    18: "The dinner bell has rung for the goats! Thanks to the contributors, {goat_name} is enjoying a nice meal. \n\nWatch live and get up to date progress at:  https://lightning-goats.com",
    19: "Thanks to your help, it's feeding time at the farm! {goat_name} couldn't be happier. Watch live and get up to date progress at:  https://lightning-goats.com",
    20: "The herd is feasting! Thanks to your contributions, {goat_name} is having a great meal. \n\nWatch live and get up to date progress at:  https://lightning-goats.com"
}
    variations = {
    1: "{difference} sats left until feeding time.",
    2: "{difference} sats until it's time to feed.",
    3: "Only {difference} sats remaining until feeding time.",
    4: "You've got {difference} sats before it's feeding time.",
    5: "Just {difference} more sats until the goats feed.",
    6: "Feeding time in {difference} sats.",
    7: "Counting down: {difference} sats until feeding.",
    8: "Prepare to feed in {difference} sats.",
    9: "Almost there! {difference} sats until feeding.",
    10: "The wait continues: {difference} sats until feeding time.",
    11: "{difference} sats to go before it's grub time.",
    12: "Hang tight, {difference} sats until chow time.",
    13: "Closing in: {difference} sats to feeding time.",
    14: "The countdown is on: {difference} sats to go.",
    15: "T-minus {difference} sats until it's mealtime.",
    16: "Feeding time is approaching in {difference} sats.",
    17: "Mark your clocks and check your blocks: {difference} sats left for feeding.",
    18: "On the horizon: {difference} sats to feeding.",
    19: "Brace yourselves: {difference} sats until it's feeding time.",
    20: "The moment is near: {difference} sats till feeding."
}

    relays = {
    'lnb.bolverker.com': 'wss://lnb.bolverker.com/nostrclient/api/v1/relay',
}


    if event_type == "sats_received":
        message_dict = sats_received_dict
    elif event_type == "feeder_triggered":
        message_dict = feeder_trigger_dict

    message = message_dict[random.randint(0, len(message_dict) - 1)]
    goat_name = random.choice(goat_names)
    
    variation_message = variations[random.randint(1, len(variations))]
    difference_message = variation_message.format(difference=difference)

    # Format the message with the available variables
    message = message.format(new_amount=new_amount, goat_name=goat_name, difference_message=difference_message)

    # Loop through each relay and execute the Nostril command asynchronously
    for relay_name, relay_url in relays.items():
        logger.info(f"Sending message through relay: {relay_name}")

        command = f"/usr/local/bin/nostril --envelope --sec {nos_sec} --content \"{message}\" | websocat {relay_url}"

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

    return process.returncode