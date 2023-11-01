import random
import subprocess
import logging

# Initialize a logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_nostril_command(nos_sec: str, new_amount: float, difference: float, event_type: str):

    goat_names = ["Dexter", "Rowan", "Gizmo", "Nova", "Cosmo", "Newton"]

    sats_received_dict = {
    0: "The herd has received {new_amount} sats. \n\n{difference_message}\n\n Fun fact: Did you know goats, like {goat_name}, have rectangular pupils? \n\nhttps://www.youtube.com/@lightning-goats/streams",
    1: "{new_amount} sats added to the goat fund! \n\n{difference_message}\n\n Goat fact: Goats like {goat_name} can be taught their name and to come when called! \n\nhttps://www.youtube.com/@lightning-goats/streams",
    2: "A donation of {new_amount} sats have been received! \n\n{difference_message}\n\n Did you know that goats, including {goat_name}, have excellent balance? They can climb and maintain balance in the most precarious places. \n\nhttps://www.youtube.com/@lightning-goats/streams",
    3: "We're {new_amount} sats closer to feeding time! \n\n{difference_message}\n\n Interesting fact: Goats, like {goat_name}, are very social animals and live in groups called herds. \n\nhttps://www.youtube.com/@lightning-goats/streams",
    4: "Great news for the herd! We've just received {new_amount} sats. \n\n{difference_message}\n\n Goat fact: Goats like {goat_name} can jump nearly 5 feet high! \n\nhttps://www.youtube.com/@lightning-goats/streams",
    5: "The herd has benefited from your generosity! {new_amount} sats has just been donated. \n\n{difference_message}\n\n Did you know? Goats, like {goat_name}, were one of the first animals to be tamed by humans more than 9,000 years ago. \n\nhttps://www.youtube.com/@lightning-goats/streams",
    6: "Thank you for your generosity! Your donation of {new_amount} sats brings us closer to our goal. \n\n{difference_message}\n\n Fun fact: Goats like {goat_name} have an incredible ability to adapt to various climates and environments. \n\nhttps://www.youtube.com/@lightning-goats/streams",
    7: "Your gift of {new_amount} sats brings joy to the herd. \n\n{difference_message}\n\n Interesting fact: {goat_name} and other goats are natural explorers and are curious about their surroundings. \n\nhttps://www.youtube.com/@lightning-goats/streams",
    8: "{new_amount} sats received! \n\n{difference_message}\n\n Fun fact: Goats have incredible climbing abilities. {goat_name} could probably climb a tree if given the chance! \n\nhttps://www.youtube.com/@lightning-goats/streams",
    9: "Your contribution of {new_amount} sats gets us closer to feeding time! \n\n{difference_message}\n\n Did you know? Goats like {goat_name} can remember complex tasks for years. \n\nhttps://www.youtube.com/@lightning-goats/streams",
    10: "Thank you for the {new_amount} sats! \n\n{difference_message}\n\n Fun fact: Goats like {goat_name} have been proven to be as smart as dogs in some areas. \n\nhttps://www.youtube.com/@lightning-goats/streams",
    11: "A donation of {new_amount} sats! \n\n{difference_message}\n\n Interesting fact: {goat_name} and other goats can be quite affectionate and enjoy being petted. \n\nhttps://www.youtube.com/@lightning-goats/streams",
    12: "We've received {new_amount} sats from a generous donor! \n\n{difference_message}\n\n Did you know? Goats are actually quite good swimmers, much like {goat_name}! \n\nhttps://www.youtube.com/@lightning-goats/streams",
    13: "Someone just sent {new_amount} sats! \n\n{difference_message}\n\n Fun fact: Did you know {goat_name} and other goats have accents, just like humans? \n\nhttps://www.youtube.com/@lightning-goats/streams",
    14: "We're {new_amount} sats closer to feeding time! \n\n{difference_message}\n\n Goat fact: Goats like {goat_name} have around 320° field of vision! \n\nhttps://www.youtube.com/@lightning-goats/streams",
    15: "Thank you for your donation of {new_amount} sats! \n\n{difference_message}\n\n Did you know? {goat_name} and other goats can distinguish between human expressions and are drawn to happy faces. \n\nhttps://www.youtube.com/@lightning-goats/streams",
    16: "Your {new_amount} sats donation brings us closer to our goal. \n\n{difference_message}\n\n Goat fact: Goats like {goat_name} are not just cute, they are also environmentally friendly due to their preference for a diet of weeds. \n\nhttps://www.youtube.com/@lightning-goats/streams",
    17: "We've just received {new_amount} sats. \n\n{difference_message}\n\n Fun fact: Did you know that goats like {goat_name} communicate with each other by bleating? \n\nhttps://www.youtube.com/@lightning-goats/streams",
    18: "A donation of {new_amount} sats has been received! \n\n{difference_message}\n\n Interesting fact: Just like {goat_name}, all goats have unique voices. \n\nhttps://www.youtube.com/@lightning-goats/streams",
    19: "We're {new_amount} sats closer to feeding time! \n\n{difference_message}\n\n Fun fact: Did you know that goats like {goat_name} use their sense of smell to locate other goats? \n\nhttps://www.youtube.com/@lightning-goats/streams",
    20: "Thank you for the {new_amount} sats! \n\n{difference_message}\n\n Goat fact: Did you know that goats like {goat_name} are naturally immune to certain diseases? \n\nhttps://www.youtube.com/@lightning-goats/streams",
    21: "Your generous donation of {new_amount} sats is appreciated! \n\n{difference_message}\n\n Goat fact: Goats like {goat_name} don't have teeth on their upper jaw, just a strong dental pad! \n\nhttps://www.youtube.com/@lightning-goats/streams",
    22: "{new_amount} sats have been added. \n\n{difference_message}\n\n Did you know? Goats like {goat_name} can rotate their ears to listen in any direction. \n\nhttps://www.youtube.com/@lightning-goats/streams",
    23: "Thanks for the {new_amount} sats! \n\n{difference_message}\n\n https://lightning-goats.com\n\nhttps://www.youtube.com/@lightning-goats/streams",
    24: "We received {new_amount} sats from you. \n\n{difference_message}\n\n Goat fact: Goats, like {goat_name}, have four stomach chambers which help them digest tough plants. \n\nhttps://www.youtube.com/@lightning-goats/streams",
    25: "Your donation of {new_amount} sats is heartwarming! \n\n{difference_message}\n\n Did you know? Goats like {goat_name} are known to be great escape artists due to their intelligence and curiosity. \n\nhttps://www.youtube.com/@lightning-goats/streams",
    26: "Thanks for donating {new_amount} sats! \n\n{difference_message}\n\n Interesting fact: While {goat_name} might enjoy it, goats are known to consume paper but they don't actually eat it as a part of their diet! \n\nhttps://www.youtube.com/@lightning-goats/streams",
    27: "{new_amount} sats received. \n\n{difference_message}\n\n Fun fact: Contrary to popular belief, goats like {goat_name} don't really eat tin cans! \n\nhttps://www.youtube.com/@lightning-goats/streams",
    28: "We're closer to our goal with your donation of {new_amount} sats! \n\n{difference_message}\n\n Goat fact: The beard of goats, like {goat_name}, is called a 'wattle'. \n\nhttps://www.youtube.com/@lightning-goats/streams",
    29: "Your {new_amount} sats will make a difference! \n\n{difference_message}\n\n Did you know? Goats like {goat_name} have horizontal slit-shaped pupils that help them watch over for predators. \n\nhttps://www.youtube.com/@lightning-goats/streams",
    30: "Thanks for the {new_amount} sats! \n\n{difference_message}\n\n Fun fact: 'Caprine' is the scientific term for things related to goats. So, {goat_name} is a caprine creature! \n\nhttps://www.youtube.com/@lightning-goats/streams",
    31: "You've donated {new_amount} sats. \n\n{difference_message}\n\n Goat fact: Some goats, can produce spider silk protein in their milk. \n\nhttps://www.youtube.com/@lightning-goats/streams",
    32: "Thanks for the {new_amount} sats! \n\n{difference_message}\n\n Did you know? Goats were among the first animals to travel to space in the early days of space exploration. \n\nhttps://www.youtube.com/@lightning-goats/streams",
    33: "We appreciate the {new_amount} sats! \n\n{difference_message}\n\n Fun fact: Goats have a knack for problem-solving and can work together in teams to accomplish tasks. Just like {goat_name} does! \n\nhttps://www.youtube.com/@lightning-goats/streams",
    34: "{new_amount} sats received! \n\n{difference_message}\n\n Goat fact: In many parts of the world, goat milk is more commonly consumed than cow's milk. \n\nhttps://www.youtube.com/@lightning-goats/streams",
    35: "Thank you for your {new_amount} sats! \n\n{difference_message}\n\n Did you know? Fainting goats don't really faint. Their muscles freeze for a few seconds when they're startled. But don't worry, {goat_name} is fine, because the Lightning Goat herd is made of Pygmy Goats and Kinder Goats. \n\nhttps://www.youtube.com/@lightning-goats/streams",
    36: "{new_amount} sats added to the feeder. \n\n{difference_message}\n\n Interesting fact: The world record for the largest goat horn span is over 13 feet! {goat_name} might not be a record holder, but they're special to us! \n\nhttps://www.youtube.com/@lightning-goats/streams",
    37: "We're grateful for the {new_amount} sats. \n\n{difference_message}\n\n Goat fact: Goats' hooves have a soft pad that allows them to climb rocky terrains easily. {goat_name} has those nifty hooves too! \n\nhttps://www.youtube.com/@lightning-goats/streams",
    38: "Your donation of {new_amount} sats is making a difference! \n\n{difference_message}\n\n Did you know? A group of goats is called a tribe or a trip. Maybe {goat_name} is planning a trip soon? \n\nhttps://www.youtube.com/@lightning-goats/streams",
    39: "{new_amount} sats received, thank you! \n\n{difference_message}\n\n Fun fact: Goats like {goat_name} use their tails to communicate. An upright tail often means a happy goat! \n\nhttps://www.youtube.com/@lightning-goats/streams",
    40: "Thanks for the {new_amount} sats! \n\n{difference_message}\n\n Goat fact: Goats' eyes have a rectangular pupil that allows them to see a panoramic view of their surroundings. So, {goat_name} can see a lot more than you'd think! \n\nhttps://www.youtube.com/@lightning-goats/streams",
    41: "{new_amount} sats added. Many thanks! \n\n{difference_message} \n\nDid you know? Goats like {goat_name} were considered sacred in ancient Egyptian culture. \n\nhttps://www.youtube.com/@lightning-goats/streams",
    42: "We've got {new_amount} sats richer, thanks to you! \n\n{difference_message} \n\nFun fact: While many believe goats will eat anything, they are actually quite picky eaters. {goat_name} has its favorites too! \n\nhttps://www.youtube.com/@lightning-goats/streams",
    43: "Every sats counts! Thanks for the {new_amount} sats. \n\n{difference_message} \n\nInteresting fact: Just like {goat_name}, goats can recognize their reflection in a mirror. Smart creatures, aren't they? \n\nhttps://www.youtube.com/@lightning-goats/streams",
    44: "Your generous {new_amount} sats will help a lot! \n\n{difference_message} \n\nDid you know? The lifespan of a domestic goat is around 15-18 years. We hope {goat_name} has many more happy years to come! \n\nhttps://www.youtube.com/@lightning-goats/streams",
    45: "We're thrilled to receive your {new_amount} sats! \n\n{difference_message} \n\nGoat fact: The goat is one of the 12 Chinese zodiac animals. Maybe {goat_name} was born in the Year of the Goat? \n\nhttps://www.youtube.com/@lightning-goats/streams",
    46: "Thanks for the sats! We've added {new_amount} to the account. \n\n{difference_message} \n\nInteresting tidbit: {goat_name} might agree, goats have a calming presence and are used in animal therapy sessions. \n\nhttps://www.youtube.com/@lightning-goats/streams",
    47: "Heartfelt thanks for the {new_amount} sats! \n\n{difference_message} \n\nFun fact: Goats have a special enzyme that allows them to break down toxic plants that other animals can't eat. So, {goat_name} is quite the survivor! \n\nhttps://www.youtube.com/@lightning-goats/streams",
    48: "Every sats is a step closer to our goal! Your {new_amount} is appreciated. \n\n{difference_message} \n\nDid you know? While goats are social animals, they also have individual personalities, just like {goat_name}. \n\nhttps://www.youtube.com/@lightning-goats/streams",
    49: "Cheers for the {new_amount} sats! \n\n{difference_message} \n\nInteresting fact: Some goats, possibly like {goat_name}, enjoy listening to music. Who knows, they might have a favorite tune! \n\nhttps://www.youtube.com/@lightning-goats/streams",
    50: "Thanks for the {new_amount} sats! \n\n{difference_message} \n\nGoat fact: In mythology, the goat often symbolizes fertility and vitality. {goat_name} sure brings life to our herd! \n\nhttps://www.youtube.com/@lightning-goats/streams"
}


    feeder_trigger_dict = {
    0: "Feeder Trigger Alert! Random plebs have banded together to feed the herd. {goat_name} is excited! Thank you! \n\nhttps://www.youtube.com/@lightning-goats/streams",
    1: "The herd has been fed thanks to generous contributors! {goat_name} enjoyed the snack! \n\nhttps://www.youtube.com/@lightning-goats/streams",
    2: "The goats got treats right now! Join the fun at https://lightning-goats.com. {goat_name} is getting his fill!",
    3: "Snack time! The herd, including {goat_name}, is munching away thanks to our contributors. \n\nhttps://www.youtube.com/@lightning-goats/streams",
    4: "Feeding time! {goat_name} is excited for his snack. A big thanks to everyone who contributed. \n\nhttps://www.youtube.com/@lightning-goats/streams",
    5: "Thanks to your contributions, {goat_name} and the rest of the herd are enjoying a feast! Join us at https://lightning-goats.com",
    6: "Food has arrived for the herd! Watch {goat_name} and the others enjoy their treats at https://lightning-goats.com",
    7: "Happy goats over here! {goat_name} is particularly pleased with this round of feeding. Join us at https://lightning-goats.com",
    8: "Your contributions have made a meal possible for the herd! {goat_name} can't thank you enough. \n\nhttps://www.youtube.com/@lightning-goats/streams",
    9: "Feeder alert! Your contributions have filled up the feeding tray. {goat_name} is ready to eat! \n\nhttps://www.youtube.com/@lightning-goats/streams",
    10: "The herd is gathering for a meal, all thanks to you! {goat_name} is leading the charge. Join the fun at https://lightning-goats.com",
    11: "A generous crowd has provided a meal for the goats! {goat_name} is ready to tuck in. \n\nhttps://www.youtube.com/@lightning-goats/streams",
    12: "It's feeding time for the herd! {goat_name} and friends are happy and full, thanks to you. \n\nhttps://www.youtube.com/@lightning-goats/streams",
    13: "What's that sound? It's the dinner bell for the goats! {goat_name} is first in line. Thanks for contributing! \n\nhttps://www.youtube.com/@lightning-goats/streams",
    14: "Happy goats coming right up! Thanks to the contributions, {goat_name} is about to enjoy a hearty meal. \n\nhttps://www.youtube.com/@lightning-goats/streams",
    15: "It's a happy day for the herd! {goat_name} is tucking into a meal, thanks to your generosity. \n\nhttps://www.youtube.com/@lightning-goats/streams",
    16: "Feeding time is here! {goat_name} is enjoying the meal you've made possible. Join us at https://lightning-goats.com",
    17: "Dinner is served for the goats! Thanks to you, {goat_name} is full and content. \n\nhttps://www.youtube.com/@lightning-goats/streams",
    18: "The dinner bell has rung for the goats! Thanks to the contributors, {goat_name} is enjoying a nice meal. \n\nhttps://www.youtube.com/@lightning-goats/streams",
    19: "Thanks to your help, it's feeding time at the farm! {goat_name} couldn't be happier. Join us at https://lightning-goats.com",
    20: "The herd is feasting! Thanks to your contributions, {goat_name} is having a great meal. \n\nhttps://www.youtube.com/@lightning-goats/streams"
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
    10: "The wait continues: {difference} sats until feeding time."
}

    relays = {
    'primal.net': 'wss://relay.primal.net/',
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

    # Loop through each relay and execute the Nostril command
    for relay_name, relay_url in relays.items():
        logging.info(f"Sending message through relay: {relay_name}")

        command = f"/usr/local/bin/nostril --envelope --sec {nos_sec} --content \"{message}\" | websocat {relay_url}"

        process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate()

        if process.returncode != 0:
            logger.error(f"Command failed with error: {stderr.decode()}")
        else:
            logger.info(f"Command output: {stdout.decode()}")

    return process.returncode
