herd_profile = "nostr:nprofile1qqsxd84men85p8hqgearxes2az8azljn08nydeqa0s3klayk8u7rddshkxjm3"  #should be set in .env

cyber_herd_dict = {
    0: "{name} has joined the ⚡ CyberHerd ⚡. {thanks_part} The feeder will activate in {difference} sats.\n\n https://lightning-goats.com\n\n",
    1: "Welcome, {name}. {thanks_part} The ⚡ CyberHerd ⚡ grows. {difference} sats are required for the next feeding cycle.\n\n https://lightning-goats.com\n\n",
    2: "{name} has been added to the ⚡ CyberHerd ⚡. {thanks_part} The feeder activation countdown is at {difference} sats.\n\n https://lightning-goats.com\n\n",
    3: "A warm welcome to {name} for joining the ⚡ CyberHerd ⚡. {thanks_part} {difference} sats until treat dispensation.\n\n https://lightning-goats.com\n\n",
    4: "{name} is now a member of the ⚡ CyberHerd ⚡. {thanks_part} {difference} sats remaining until the feeder is triggered.\n\n https://lightning-goats.com\n\n",
    5: "The herd welcomes {name}. {thanks_part} Feeder activation will occur in {difference} sats.\n\n https://lightning-goats.com\n\n",
    6: "{name} has been successfully added to the ⚡ CyberHerd ⚡. {thanks_part} {difference} sats until treats are dispensed.\n\n https://lightning-goats.com\n\n",
    7: "Welcome, {name}, to the ⚡ CyberHerd ⚡. {thanks_part} The feeder requires {difference} more sats to activate.\n\n https://lightning-goats.com\n\n",
    8: "The ⚡ CyberHerd ⚡ has a new member: {name}. {thanks_part} {difference} sats until the next feeding event.\n\n https://lightning-goats.com\n\n",
    9: "{name}, you are now officially part of the ⚡ CyberHerd ⚡. {thanks_part} Please note, {difference} sats remain for feeder activation.\n\n https://lightning-goats.com\n\n",
    10: "{name} has entered the ⚡ CyberHerd ⚡. {thanks_part} {difference} sats are pending for the next feeding cycle.\n\n https://lightning-goats.com\n\n"
}


cyber_herd_info_dict = {
    0:"",
}

thank_you_variations = [
    "Thank you for the contribution of {new_amount} sats.",
    "Your {new_amount} sat contribution has been received and supports the herd.",
    "We have received your contribution of {new_amount} sats.",
    "Thank you for your support. Your {new_amount} sat transaction is confirmed.",
    "Your {new_amount} sat contribution is greatly appreciated.",
    "The herd thanks you for your contribution of {new_amount} sats.",
    "Your {new_amount} sat contribution to the project has been received.",
    "We appreciate your support with a {new_amount} sat contribution.",
    "Thank you. Your {new_amount} sats help power the Lightning Goats project.",
    "Contribution of {new_amount} sats confirmed. Thank you for your support.",
    "Your {new_amount} sats have been successfully contributed to the herd.",
    "Thank you for participating in the Lightning Goats project with {new_amount} sats.",
    "Your contribution of {new_amount} sats is valuable to our project.",
    "Every sat counts. Thank you for the {new_amount} sats.",
    "The Lightning Goats project is powered by contributions like your {new_amount} sats. Thank you."
]

cyber_herd_treats_dict = {
    0: "{name} has received a reward of {new_amount} sats from the ⚡ CyberHerd ⚡ distribution.\n\n https://lightning-goats.com\n\n",
    1: "A distribution of {new_amount} sats has been sent to {name} as part of their ⚡ CyberHerd ⚡ membership.\n\n https://lightning-goats.com\n\n",
    2: "Transaction notice: {name} has been credited with {new_amount} sats from the ⚡ CyberHerd ⚡ reward protocol.\n\n https://lightning-goats.com\n\n",
    3: "{name} has received a {new_amount} sat distribution, courtesy of the ⚡ CyberHerd ⚡.\n\n https://lightning-goats.com\n\n",
    4: "As a member of the ⚡ CyberHerd ⚡, {name} has been allocated {new_amount} sats.\n\n https://lightning-goats.com\n\n",
    5: "Deposit confirmed: {new_amount} sats have been transferred to {name} from the ⚡ CyberHerd ⚡ system.\n\n https://lightning-goats.com\n\n",
    6: "Your daily ⚡ CyberHerd ⚡ reward has been processed: {name} receives {new_amount} sats.\n\n https://lightning-goats.com\n\n",
    7: "Reward unlocked: {name} has earned {new_amount} sats through ⚡ CyberHerd ⚡ participation.\n\n https://lightning-goats.com\n\n",
    8: "Your wallet balance has increased, {name}. {new_amount} sats received from the ⚡ CyberHerd ⚡.\n\n https://lightning-goats.com\n\n",
    9: "The daily dividend has been distributed: {name} is credited with {new_amount} sats via the ⚡ CyberHerd ⚡ algorithm.\n\n https://lightning-goats.com\n\n"
}



interface_info_dict = {
    1: "To send the goats treats, scan the QR Code in the upper right corner with a Lightning wallet and choose the sats you'd like to contribute. Once the feeder reaches 100%, the ⚡ Lightning Goats ⚡ will get a mixture of timothy hay pellets and goat granola.",
    2: "Support the herd on Nostr! Nostr users can send treats to the goats by zapping ⚡ Lightning Goats ⚡ notes. Zaps contribute to triggering the feeder and dispense cool goat facts.",
    3: "Each goat has his own Lightning address. Sats sent to the goats on Nostr are forwarded to the herd and contribute to triggering the feeder.",
    4: "Watch the goats live and participate in feeding them by sending sats via the Lightning Network. The more sats, the closer the feeder gets to being triggered, giving the goats a tasty treat.",
    5: "⚡ CyberHerd ⚡ functionality is here to reward Nostr users who interact with the herd. Zap TODAY'S #CyberHerd note with 10+ sats to grab one of the 3 available spots for the day. When the herd gets treats, so will you - receiving 10% of feeder payments!",
    6: "Be sure to like and subscribe to our channel on YouTube. The goats enjoy their jobs and like helping to educate people about Bitcoin and Lightning.",
    7: "⚡ Lightning Goats ⚡ runs on 100% open-source software, and is powered by solar energy. We're online during daylight hours as soon as our batteries are charged enough to broadcast.",
    8: "With a few seconds of video broadcast lag, you can interact with the goats in real-time using the Lightning Network. By sending sats, viewers can trigger the feeder, creating an interactive experience that bridges the digital and natural worlds.",
    9: "The ⚡ Lightning Goats ⚡ project is not just for entertainment; it's also an educational tool. The goat feeder provides a practical, fun way to experience Bitcoin and the Lightning Network.",
    10: "Emphasizing sustainability, the ⚡ Lightning Goats ⚡ showcase how renewable energy and regenerative practices can be integrated with Bitcoin.",
    11: "Sats donated to the ⚡ Lightning Goats ⚡ feeder not only send the goats treats, they also contribute towards buying hay, and help development and other operational costs.",
    12: "By participating in the ⚡ Lightning Goats ⚡ experience, you’re not only feeding the goats but also contributing to a real world Bitcoin experiment, demonstrating the real-world power of microtransactions.",
    13: "You can follow the goats’ live streams and contribute directly to their feeding schedule. Every sat brings the feeder closer to activation, where the goats enjoy nutritious treats.",
    14: "Zapping the ⚡ Lightning Goats ⚡ on Nostr supports the herd while promoting decentralized social interaction. Your contributions help trigger the feeder and send treats directly to the goats.",
    15: "⚡ Lightning Goats ⚡ is designed to create a symbiotic relationship between technology and nature. By sending sats, you're helping the goats while engaging in the global Bitcoin ecosystem.",
    16: "Interact with the goats in real-time by sending sats. Your contribution via the Lightning Network triggers the feeder and helps provide the herd with daily sustenance.",
    17: "Support sustainability and innovation by sending sats to the ⚡ Lightning Goats ⚡ project. Your donations help cover operational costs and ensure the goats get the treats they deserve.",
    18: "The ⚡ Lightning Goats ⚡ project is entirely community-driven. Each sat contributed helps support the goats and allows viewers to engage in a unique, Bitcoin-powered experience.",
    19: "Get involved in an interactive Bitcoin experience by sending sats to the ⚡ Lightning Goats ⚡. Every sat counts toward triggering the feeder and providing the herd with fresh treats.",
    20: "By contributing sats, you’re joining a global community that supports both animal care and innovative uses of the Lightning Network. Every donation helps keep the ⚡ Lightning Goats ⚡ well-fed and the project thriving.",
    21: "By sending sats, you’re contributing to a global, decentralized experiment that merges nature and technology. The ⚡ Lightning Goats ⚡ rely on your donations to get their next snack!",
    22: "Sats you send go toward feeding the goats, with the feeder being triggered once enough contributions are made. Watch in real-time as the ⚡ Lightning Goats ⚡ enjoy their treats!",
    23: "Did you know your sats not only feed the goats but also help fund educational content on goats, Bitcoin and Lightning? Every contribution ensures the ⚡ Lightning Goats ⚡ project stays innovative and informative.",
    24: "Become part of the ⚡ Lightning Goats ⚡ story by contributing sats. Whether you're zapping a note or scanning the QR code, your participation is key to keeping the herd happy and well-fed.",
    25: "The ⚡ Lightning Goats ⚡ feeder system is directly connected to the Lightning Network, showcasing how microtransactions can be used to create real-world change. Your sats help power this unique experiment.",
    26: "You can be a part of Bitcoin history by contributing to the ⚡ Lightning Goats ⚡. Your sats trigger the feeder, demonstrating the power of Bitcoin’s Lightning Network in action.",
    27: "Want to support the herd while learning more about Bitcoin? Watch the ⚡ Lightning Goats ⚡ live stream and see how your sats directly impact the goats’ feeding schedule.",
    28: "The ⚡ Lightning Goats ⚡ project is powered by community contributions. Every sat helps keep the goats healthy, happy, and well-fed, while also promoting Bitcoin and Lightning education.",
    29: "Your contributions make the ⚡ Lightning Goats ⚡ project possible. Each sat you send not only feeds the goats but also supports the infrastructure that powers this interactive experience.",
    30: "Want to learn how Bitcoin works in the real world? Contribute to the ⚡ Lightning Goats ⚡ feeder by sending sats and watch the goats benefit from this digital-to-physical experience.",
    31: "By participating in the ⚡ Lightning Goats ⚡ project, you’re supporting open-source software and renewable energy, both of which help keep the goats fed and the feeder system running smoothly.",
    32: "Join the herd by sending sats to the ⚡ Lightning Goats ⚡. Your contribution feeds the goats and keeps the feeder system active, all while promoting sustainability and decentralized technology.",
    33: "Every sat counts in the ⚡ Lightning Goats ⚡ project! The feeder operates using contributions from the global Bitcoin community, and you can be part of it by sending sats directly to the herd.",
    34: "Support the goats and showcase the power of microtransactions by sending sats to the ⚡ Lightning Goats ⚡ project. Your contribution directly triggers the feeder, delivering treats to the herd.",
    35: "Sats donated to the ⚡ Lightning Goats ⚡ project help cover costs for feed, technology, and educational outreach. Every contribution makes a difference for the herd and for Bitcoin awareness.",
    36: "The ⚡ Lightning Goats ⚡ are part of a unique Bitcoin project that merges technology, sustainability, and animal care. By sending sats, you help feed the goats and keep this innovation alive.",
    37: "Sending sats to the ⚡ Lightning Goats ⚡ is a fun and interactive way to experience the Bitcoin Lightning Network. Your contribution directly impacts the feeder and helps the goats get their next meal.",
    38: "By contributing sats to the ⚡ Lightning Goats ⚡, you’re supporting not only the herd but also education about Bitcoin, Lightning, and renewable energy solutions.",
    39: "Each sat you send helps feed the ⚡ Lightning Goats ⚡ and keeps the project running. Your contributions also fund hardware and development for this unique, open-source experiment.",
    40: "Support the ⚡ Lightning Goats ⚡ by sending sats! Whether you zap a note or use a Lightning wallet, your contribution brings the herd closer to their next feeding time.",
    41: "The #CyberHerd is a community of supporters who receive a share of payments each time the goat feeder is triggered. Join by zapping TODAY'S #CyberHerd note with 10+ sats. The herd resets daily at midnight UTC.",
    42: "To join the #CyberHerd, you need a valid NIP-05 identifier and a working Lightning address. Membership requires a zap of at least 10 sats to TODAY'S #CyberHerd note only - older notes don't work due to daily reset.",
    43: "When the feeder is activated, 10% of the trigger amount is distributed among all #CyberHerd members. Payouts are proportional to each member's total zap contribution.",
    44: "Your zaps to Lightning Goats content are cumulative. New members must zap TODAY'S #CyberHerd note to join, but existing members can zap ANY Lightning Goats note to increase their payout share.",
    45: "When the #CyberHerd is at its maximum capacity of 3 members, you can still join by 'headbutting' out the member with the lowest contribution.",
    46: "To displace a member via 'headbutting,' new members must zap TODAY'S #CyberHerd note with more sats than the lowest member's total. Upon a successful headbutt, you take their spot in the herd.",
    47: "Please be aware: If you are displaced from the herd via 'headbutting,' your accumulated zap total is reset to zero. You must start over to rejoin.",
    48: "To increase your security within the #CyberHerd, existing members can zap ANY Lightning Goats note to add to their total. A higher contribution makes it more difficult for another user to displace you via headbutting.",
    49: "All #CyberHerd operations, including membership, payouts, and displacements, are processed automatically by monitoring Nostr. Notifications are sent as public replies.",
    50: "The #CyberHerd resets every night at midnight UTC. All memberships and accumulated zap amounts are cleared, giving everyone a fresh start each day with a new #CyberHerd note.",
    51: "When the feeder triggers (around 850 sats), payments are split: 90% feeds the goats, 10% goes to CyberHerd members. Your share depends on your total zap contribution relative to other members.",
    52: "New to #CyberHerd? You must zap TODAY'S #CyberHerd tagged note to join. Already a member? You can zap ANY Lightning Goats note to increase your payout share and headbutt protection.",
    53: "Important: Only zaps of 10+ sats to Lightning Goats authored content count for #CyberHerd membership and payouts. Zaps to other people's notes don't qualify.",
    54: "Getting headbutted out of the #CyberHerd completely resets your accumulated zap total to zero. To rejoin, you must start fresh by zapping TODAY'S #CyberHerd note again.",
    55: "The #CyberHerd has a maximum of 3 members. When full, new members can still join by 'headbutting' - zapping more than the lowest member's total contribution to TODAY'S #CyberHerd note.",
    56: "CyberHerd payouts are proportional to your contribution. If you've zapped 500 sats and others zapped 300 and 200, you get the biggest share of the 10% CyberHerd distribution when the feeder triggers.",
    57: "Daily reset means fresh opportunities! Every day at midnight UTC, the #CyberHerd clears and a new #CyberHerd note is posted. Previous day's notes become invalid for joining.",
    58: "CyberHerd strategy tip: Build up your zap total by supporting various Lightning Goats content. More zaps = bigger payouts and better protection against headbutting attacks.",
    59: "Example #CyberHerd scenario: You zap 200 sats to TODAY'S #CyberHerd note to join, then 300 sats to a Lightning Goats educational post. Your total: 500 sats = bigger future payouts!",
    60: "Flexible zapping for existing #CyberHerd members: Support any Lightning Goats content - technical posts, goat updates, educational content. Every qualifying zap increases your payout share.",
    61: "#CyberHerd membership requires a valid NIP-05 identifier and working Lightning address. These are essential for receiving your automatic payouts when the feeder triggers.",
    62: "The #CyberHerd operates 24/7 with automatic monitoring. Your membership and contributions are updated immediately when the system detects qualifying zaps to Lightning Goats content."
}

sats_received_dict = {
    0: "The herd has received {new_amount} sats. {difference_message} Scientific fact: Goats, such as {goat_name}, have uniquely shaped rectangular pupils, which provide them a wide field of vision, aiding in predator detection.\n\n https://lightning-goats.com\n\n",
    1: "{new_amount} sats added to the goat fund! {difference_message} Goats, including {goat_name}, are intelligent animals capable of learning their names and responding when called.\n\n https://lightning-goats.com\n\n",
    2: "A donation of {new_amount} sats has been received! {difference_message} Did you know that goats, like {goat_name}, demonstrate exceptional balance and can navigate steep and uneven terrains with ease?\n\n https://lightning-goats.com\n\n",
    3: "We're {new_amount} sats closer to feeding time! {difference_message} Goats, such as {goat_name}, are social creatures that naturally form groups for mutual protection and social interaction.\n\n https://lightning-goats.com\n\n",
    4: "Great news for the herd! We've just received {new_amount} sats. {difference_message} Did you know? Goats, including those like {goat_name}, possess powerful leg muscles, enabling them to jump up to 5 feet high.\n\n https://lightning-goats.com\n\n",
    5: "The herd has benefited from your generosity! {new_amount} sats have just been donated. {difference_message} Historical fact: Goats, like {goat_name}, were among the first animals domesticated by humans, dating back over 9,000 years.\n\n https://lightning-goats.com\n\n",
    6: "Thank you for your generosity! Your donation of {new_amount} sats brings us closer to our goal. {difference_message} Environmental adaptation fact: Goats, including {goat_name}, exhibit remarkable adaptability to diverse climates and habitats.\n\n https://lightning-goats.com\n\n",
    7: "Your gift of {new_amount} sats brings joy to the herd. {difference_message} Ethological observation: Goats, such as {goat_name}, exhibit a natural curiosity and exploratory behavior, often investigating their environment thoroughly.\n\n https://lightning-goats.com\n\n",
    8: "{new_amount} sats received! {difference_message} Interesting fact: Goats, like {goat_name}, are adept climbers known for their ability to scale challenging terrains, including trees and rocky cliffs.\n\n https://lightning-goats.com\n\n",
    9: "Your contribution of {new_amount} sats gets us closer to feeding time! {difference_message} Cognitive fact: Goats, including those like {goat_name}, have good memory retention and can remember complex tasks over extended periods.\n\n https://lightning-goats.com\n\n",
    10: "Thank you for the {new_amount} sats! {difference_message} Intelligence fact: Goats, such as {goat_name}, show cognitive abilities comparable to dogs in certain aspects.\n\n https://lightning-goats.com\n\n",
    11: "A donation of {new_amount} sats! {difference_message} Social behavior fact: {goat_name} and other goats enjoy social interactions, including being petted, as part of their herd dynamics.\n\n https://lightning-goats.com\n\n",
    12: "We've received {new_amount} sats from a generous donor! {difference_message} Contrary to common belief, goats, including {goat_name}, are capable swimmers, though not all breeds have equal proficiency.\n\n https://lightning-goats.com\n\n",
    13: "Someone just sent {new_amount} sats! {difference_message} Communication fact: Goats like {goat_name} have distinct vocalizations or 'accents' that can vary based on their region and social environment.\n\n https://lightning-goats.com\n\n",
    14: "We're {new_amount} sats closer to feeding time! {difference_message} Vision fact: Goats, such as {goat_name}, have a field of vision of approximately 320°, thanks to their rectangular pupils, allowing for excellent peripheral vision.\n\n https://lightning-goats.com\n\n",
    15: "Thank you for your donation of {new_amount} sats! {difference_message} {goat_name} and other goats can discern human facial expressions, showing a preference for happy faces, indicating advanced social and emotional awareness.\n\n https://lightning-goats.com\n\n",
    16: "Your {new_amount} sats donation brings us closer to our goal. {difference_message} Goats, including ones like {goat_name}, contribute to ecological balance by controlling weed populations and promoting plant diversity.\n\n https://lightning-goats.com\n\n",
    17: "We've just received {new_amount} sats. {difference_message} Communication fact: Goats like {goat_name} use bleating as a primary form of communication, which varies based on their emotional state and needs.\n\n https://lightning-goats.com\n\n",
    18: "A donation of {new_amount} sats has been received! {difference_message} Each goat, including {goat_name}, has a unique voice, helping them recognize each other within the herd.\n\n https://lightning-goats.com\n\n",
    19: "We're {new_amount} sats closer to feeding time! {difference_message} Sensory fact: Goats like {goat_name} utilize their acute sense of smell to identify other goats and their environment, aiding in social bonding and navigation.\n\n https://lightning-goats.com\n\n",
    20: "Thank you for the {new_amount} sats! {difference_message} Health fact: Goats like {goat_name} have natural resistance to certain diseases, thanks to their robust immune systems.\n\n https://lightning-goats.com\n\n",
    21: "Your generous donation of {new_amount} sats is appreciated! {difference_message} Unlike many mammals, goats, including {goat_name}, lack upper front teeth, instead having a strong dental pad for grazing.\n\n https://lightning-goats.com\n\n",
    22: "{new_amount} sats have been added. {difference_message} Goats such as {goat_name} have a remarkable ability to rotate their ears in different directions, enhancing their auditory perception.\n\n https://lightning-goats.com\n\n",
    23: "Thanks for the {new_amount} sats! {difference_message} Additional fun and educational goat facts can be shared in the future.\n\n https://lightning-goats.com\n\n",
    24: "We received {new_amount} sats from you. {difference_message} Digestive fact: Goats, like {goat_name}, have a complex four-chambered stomach that efficiently breaks down fibrous plant material.\n\n https://lightning-goats.com\n\n",
    25: "Your donation of {new_amount} sats is heartwarming! {difference_message} Goats, such as {goat_name}, are known for their intelligence and inquisitive nature, often leading to their reputation as escape artists.\n\n https://lightning-goats.com\n\n",
    26: "Thanks for donating {new_amount} sats! {difference_message} Dietary misconception: While goats like {goat_name} may chew on paper out of curiosity, it is not a natural part of their diet.\n\n https://lightning-goats.com\n\n",
    27: "{new_amount} sats received. {difference_message} Diet myth debunked: Despite common myths, goats like {goat_name} do not eat inedible objects like tin cans; they are selective feeders.\n\n https://lightning-goats.com\n\n",
    28: "We're closer to our goal with your donation of {new_amount} sats! {difference_message} Anatomical fact: The beard-like feature on goats is called a 'wattle,' which varies in size and shape across different breeds.\n\n https://lightning-goats.com\n\n",
    29: "Your {new_amount} sats will make a difference! {difference_message} Vision advantage: Goats, including {goat_name}, have horizontal, slit-shaped pupils, providing a broad field of vision, useful for spotting predators and finding food.\n\n https://lightning-goats.com\n\n",
    30: "Thanks for the {new_amount} sats! {difference_message} The term 'Caprine' is scientifically used to refer to anything related to goats.\n\n https://lightning-goats.com\n\n",
    31: "You've donated {new_amount} sats. {difference_message} Biotechnological fact: Some specialized goats can produce spider silk proteins in their milk, a result of advanced genetic engineering techniques.\n\n https://lightning-goats.com\n\n",
    32: "Thanks for the {new_amount} sats! {difference_message} Space exploration fact: Goats were among the first animals to be involved in space missions, helping scientists understand the impacts of space travel on living organisms.\n\n https://lightning-goats.com\n\n",
    33: "We appreciate the {new_amount} sats! {difference_message} Goats, including {goat_name}, have shown problem-solving abilities and can cooperate in groups to achieve specific tasks.\n\n https://lightning-goats.com\n\n",
    34: "{new_amount} sats received! {difference_message} Goat milk is consumed more widely than cow's milk in many parts of the world, valued for its digestibility and nutritional profile.\n\n https://lightning-goats.com\n\n",
    35: "Thank you for your {new_amount} sats! {difference_message} Misconception correction: 'Fainting' goats do not actually faint; they have a condition called myotonia congenita, causing temporary muscle stiffness when startled.\n\n https://lightning-goats.com\n\n",
    36: "{new_amount} sats added to the feeder. {difference_message} The world record for the largest goat horn span exceeds 13 feet, showcasing the diverse physical traits within the species.\n\n https://lightning-goats.com\n\n",
    37: "We're grateful for the {new_amount} sats. {difference_message} Anatomical fact: Goats' hooves are uniquely adapted with a soft pad, enabling them to climb and balance on rugged terrains effectively.\n\n https://lightning-goats.com\n\n",
    38: "Your donation of {new_amount} sats is making a difference! {difference_message} A group of goats is often called a tribe or a trip, reflecting their social and communal living habits.\n\n https://lightning-goats.com\n\n",
    39: "{new_amount} sats received, thank you! {difference_message} Goats like {goat_name} use their tails to communicate different emotions; an upright tail often indicates a happy and content state.\n\n https://lightning-goats.com\n\n",
    40: "Thanks for the {new_amount} sats! {difference_message} Vision fact: Goats, including {goat_name}, have rectangular pupils, allowing for a wide, almost panoramic field of vision.\n\n https://lightning-goats.com\n\n",
    41: "{new_amount} sats added. Many thanks! {difference_message} Cultural fact: Goats like {goat_name} were revered in ancient Egyptian culture, often symbolizing fertility and prosperity.\n\n https://lightning-goats.com\n\n",
    42: "We've got {new_amount} sats richer, thanks to you! {difference_message} Dietary preference: While goats are often believed to eat anything, they are selective eaters, preferring specific types of plants and leaves.\n\n https://lightning-goats.com\n\n",
    43: "Every sats counts! Thanks for the {new_amount} sats. {difference_message} Cognitive ability: Goats, just like {goat_name}, can recognize their own reflection in a mirror, indicating a level of self-awareness.\n\n https://lightning-goats.com\n\n",
    44: "Your generous {new_amount} sats will help a lot! {difference_message} Lifespan fact: Domestic goats typically live for about 15-18 years, depending on their breed and living conditions.\n\n https://lightning-goats.com\n\n",
    45: "We're thrilled to receive your {new_amount} sats! {difference_message} Cultural significance: The goat is one of the 12 animals in the Chinese zodiac, symbolizing creativity and resilience.\n\n https://lightning-goats.com\n\n",
    46: "Thanks for the {new_amount} sats! {difference_message} Goats, like {goat_name}, are known for their calming effect and are used in animal therapy sessions for their soothing nature.\n\n https://lightning-goats.com\n\n",
    47: "Heartfelt thanks for the {new_amount} sats! {difference_message} Dietary resilience: Goats have a unique enzyme that allows them to digest and detoxify plants that are harmful to other animals.\n\n https://lightning-goats.com\n\n",
    48: "Every sat is a step closer to our goal! Your {new_amount} is appreciated. {difference_message} Individual personalities: While goats are social animals, each, including {goat_name}, has a distinct personality, influencing their behavior and interactions.\n\n https://lightning-goats.com\n\n",
    49: "Cheers for the {new_amount} sats! {difference_message} Musical preference: Some goats, possibly like {goat_name}, enjoy listening to music, though this can vary greatly among individual goats.\n\n https://lightning-goats.com\n\n",
    50: "Thanks for the {new_amount} sats! {difference_message} Mythological significance: In various mythologies, goats are often symbols of fertility and vitality, associated with deities of abundance.\n\n https://lightning-goats.com\n\n",
    51: "Your {new_amount} sats donation is much appreciated! {difference_message} Goats play a vital role in natural land management by controlling undergrowth and preventing bushfires.\n\n https://lightning-goats.com\n\n",
    52: "{new_amount} sats received! Thank you! {difference_message} Nutritional fact: Goat milk is not only popular globally but also easier to digest than cow's milk due to its unique protein structure.\n\n https://lightning-goats.com\n\n",
    53: "We're grateful for the {new_amount} sats! {difference_message} Reproductive fact: Female goats, known as does, can give birth to 1-4 kids per pregnancy, with twins being the most common.\n\n https://lightning-goats.com\n\n",
    54: "Your generosity of {new_amount} sats helps tremendously! {difference_message} Goats communicate using various vocalizations, which change based on their emotions and environment.\n\n https://lightning-goats.com\n\n",
    55: "Thank you for the {new_amount} sats! {difference_message} Grazing behavior: Goats prefer to browse on leaves, twigs, vines, and shrubs, showing a preference for higher vegetation over grass.\n\n https://lightning-goats.com\n\n",
    56: "Your donation of {new_amount} sats supports our herd! {difference_message} Goats have been known to adapt to various environments, from mountains to deserts, showcasing their versatility.\n\n https://lightning-goats.com\n\n",
    57: "{new_amount} sats received! {difference_message} Certain goat breeds, like the Angora and Cashmere, are renowned for their fine wool, used in high-quality textiles.\n\n https://lightning-goats.com\n\n",
    58: "We're {new_amount} sats closer to our goal, thanks to you! {difference_message} Goats have been associated with human culture for thousands of years, providing milk, meat, and wool.\n\n https://lightning-goats.com\n\n",
    59: "Heartfelt thanks for the {new_amount} sats! {difference_message} Goats are exceptional climbers, able to navigate steep and rocky terrains with ease, a skill that helps them access food and evade predators.\n\n https://lightning-goats.com\n\n",
    60: "Your {new_amount} sats are invaluable to us! {difference_message} Goats, like {goat_name}, help in managing natural landscapes by preventing bushfires and promoting biodiversity.\n\n https://lightning-goats.com\n\n",
    61: "We're thankful for the {new_amount} sats! {difference_message} Sustainable farming: Goats, including {goat_name}, play a key role in sustainable agriculture by naturally controlling weed growth.\n\n https://lightning-goats.com\n\n",
    62: "{new_amount} sats added to our mission. {difference_message} Conservation: Goats like {goat_name} help reduce the need for chemical herbicides, contributing to a healthier ecosystem.\n\n https://lightning-goats.com\n\n",
    63: "Every {new_amount} sats help! {difference_message} Biodiversity: Goats, such as {goat_name}, promote plant diversity by grazing on invasive species.\n\n https://lightning-goats.com\n\n",
    64: "Thanks for your generous {new_amount} sats! {difference_message} Soil health: Goats like {goat_name} naturally fertilize the land, enhancing soil quality and supporting sustainable land use.\n\n https://lightning-goats.com\n\n",
    65: "Your {new_amount} sats are making a green impact! {difference_message} Land conservation: Goats, including {goat_name}, are used in eco-grazing projects to maintain and restore natural habitats.\n\n https://lightning-goats.com\n\n",
    66: "We appreciate your {new_amount} sats! {difference_message} Ecosystem services: Goats, such as {goat_name}, contribute to ecological balance by controlling undergrowth in forests and grasslands.\n\n https://lightning-goats.com\n\n",
    67: "{new_amount} sats received with gratitude! {difference_message} Habitat restoration: Goats like {goat_name} play an important role in restoring degraded lands and promoting environmental health.\n\n https://lightning-goats.com\n\n",
    68: "Your {new_amount} sats help our planet! {difference_message} Natural weed control: Goats, including {goat_name}, help manage vegetation, reducing the need for mechanical cutting and preserving wildlife habitats.\n\n https://lightning-goats.com\n\n",
    69: "Grateful for the {new_amount} sats! {difference_message} Goats like {goat_name} aid in sequestering carbon through natural grazing, playing a role in soil health.\n\n https://lightning-goats.com\n\n",
    70: "Your {new_amount} sats support the herd! {difference_message} Goats, like {goat_name}, are integral to permaculture systems, contributing to soil health and plant diversity.\n\n https://lightning-goats.com\n\n",
    71: "Thanks for the {new_amount} sats! {difference_message} Goats such as {goat_name} aid in creating sustainable food systems through natural grazing.\n\n https://lightning-goats.com\n\n",
    72: "{new_amount} sats received! {difference_message} Goats, including {goat_name}, play a vital role in providing natural fertilization and land management.\n\n https://lightning-goats.com\n\n",
    73: "We appreciate your {new_amount} sats! {difference_message} Goats like {goat_name} help maintain ecological balance.\n\n https://lightning-goats.com\n\n",
    74: "Your donation of {new_amount} sats strengthens the Bitcoin Standard! {difference_message} In permaculture settings, such as {goat_name}, are used for their ability to control invasive species and enhance biodiversity.\n\n https://lightning-goats.com\n\n",
    75: "Grateful for your {new_amount} sats! {difference_message} Goats like {goat_name} are effective in permaculture systems, aiding in composting and soil improvement.\n\n https://lightning-goats.com\n\n",
    76: "Your generous {new_amount} sats aid farm growth! {difference_message} Goats, such as {goat_name}, enhance permaculture gardens by providing organic weed control.\n\n https://lightning-goats.com\n\n",
    77: "Thanks for the {new_amount} sats towards sustainable practices! {difference_message} Goats like {goat_name} are valued for their role in integrated pest management.\n\n https://lightning-goats.com\n\n",
    78: "{new_amount} sats help our project! {difference_message} Goats, including {goat_name}, are essential for creating self-sufficient and sustainable agricultural systems.\n\n https://lightning-goats.com\n\n",
    79: "Thank you for the {new_amount} sats! {difference_message} Goats' contribution to maintaining natural ecosystems through eco-grazing helps reduce soil erosion and encourages biodiversity.\n\n https://lightning-goats.com\n\n",
    80: "We've just received {new_amount} sats. {difference_message} Fun fact: Goats like {goat_name} are known for their exceptional sense of balance, helping them navigate rocky and steep terrain.\n\n https://lightning-goats.com\n\n",
    81: "Thanks for the {new_amount} sats! {difference_message} Goats, like {goat_name}, have been companions to humans for thousands of years, providing milk, meat, and wool.\n\n https://lightning-goats.com\n\n",
    82: "Your donation of {new_amount} sats is greatly appreciated! {difference_message} Did you know that goats are able to jump over obstacles up to 5 feet tall, making them excellent escape artists?\n\n https://lightning-goats.com\n\n",
    83: "The herd has just received {new_amount} sats! {difference_message} Goats like {goat_name} are capable of surviving in harsh environments, including deserts and mountainous regions.\n\n https://lightning-goats.com\n\n",
    84: "Thanks to your donation of {new_amount} sats! {difference_message} Goats, such as {goat_name}, play a vital role in regenerating ecosystems by controlling invasive plant species.\n\n https://lightning-goats.com\n\n",
    85: "{new_amount} sats have been received! {difference_message} Goats are well-suited for mountainous terrain, where their hooves help them grip rocks and avoid slipping.\n\n https://lightning-goats.com\n\n",
    86: "The goats appreciate your donation of {new_amount} sats! {difference_message} Goats are highly social animals and form strong bonds with members of their herd and human caregivers.\n\n https://lightning-goats.com\n\n",
    87: "{new_amount} sats have been added to the fund! {difference_message} Goats are playful creatures, often seen jumping and running, especially when they’re happy and well-fed.\n\n https://lightning-goats.com\n\n",
    88: "Thank you for your {new_amount} sats! {difference_message} Did you know? Goats' four-chambered stomachs allow them to efficiently digest fibrous plant material.\n\n https://lightning-goats.com\n\n",
    89: "We're {new_amount} sats closer to our goal! {difference_message} Goats like {goat_name} are valuable contributors to sustainable land management practices.\n\n https://lightning-goats.com\n\n",
    90: "Your donation of {new_amount} sats brings us closer to feeding time! {difference_message} Goats, such as {goat_name}, possess unique horns made of keratin, which they use for defense and display.\n\n https://lightning-goats.com\n\n",
    91: "We've just received {new_amount} sats. {difference_message} Goats' remarkable sense of smell helps them navigate their environment and identify food sources.\n\n https://lightning-goats.com\n\n",
    92: "Thank you for your {new_amount} sats! {difference_message} Did you know? Goats, like {goat_name}, can live in a wide variety of climates, from hot deserts to cold mountains.\n\n https://lightning-goats.com\n\n",
    93: "{new_amount} sats have been received! {difference_message} Goats like {goat_name} are adept at climbing trees and cliffs to reach food that other animals can't.\n\n https://lightning-goats.com\n\n",
    94: "The herd has received {new_amount} sats! {difference_message} Goats have unique social structures within their herds, with established hierarchies based on age and dominance.\n\n https://lightning-goats.com\n\n",
    95: "Thanks for the {new_amount} sats! {difference_message} Goats like {goat_name} play a crucial role in maintaining the health of ecosystems through their selective browsing habits.\n\n https://lightning-goats.com\n\n",
    96: "Your {new_amount} sats donation is greatly appreciated! {difference_message} Goats are naturally curious animals, and they often explore their surroundings by nibbling on various objects.\n\n https://lightning-goats.com\n\n",
    97: "We've received {new_amount} sats from a kind donor! {difference_message} Did you know? Goats have horizontal pupils, allowing them to see predators from nearly all angles.\n\n https://lightning-goats.com\n\n",
    98: "The goats thank you for your {new_amount} sats donation! {difference_message} Goats like {goat_name} have a highly developed sense of smell, which helps them find food and recognize members of their herd.\n\n https://lightning-goats.com\n\n",
    99: "{new_amount} sats added! {difference_message} Goats’ ability to thrive in diverse environments makes them one of the most versatile livestock animals in the world.\n\n https://lightning-goats.com\n\n",
    100: "Thanks for donating {new_amount} sats! {difference_message} Goats have remarkable balance, allowing them to scale narrow ledges and steep cliffs with ease.\n\n https://lightning-goats.com\n\n",
    101: "{new_amount} sats received! {difference_message} Goats like {goat_name} communicate with each other using a variety of vocalizations, including bleats and grunts.\n\n https://lightning-goats.com\n\n",
    102: "We've received {new_amount} sats! {difference_message} Goats are incredibly agile creatures, and their strong legs help them jump, climb, and balance on uneven terrain.\n\n https://lightning-goats.com\n\n",
    103: "Thanks for the {new_amount} sats! {difference_message} Goats are highly intelligent and can learn to recognize the voices of their human caretakers.\n\n https://lightning-goats.com\n\n",
    104: "{new_amount} sats have been added to the fund! {difference_message} Goats, like {goat_name}, play a key role in reducing wildfires by consuming dry brush and weeds.\n\n https://lightning-goats.com\n\n",
    105: "The herd has received {new_amount} sats! {difference_message} Goats can live in herds ranging from just a few individuals to over a hundred, depending on their environment and needs.\n\n https://lightning-goats.com\n\n",
    106: "Thank you for the {new_amount} sats! {difference_message} Goats are incredibly social animals, and they form strong bonds with other goats and even humans.\n\n https://lightning-goats.com\n\n",
    107: "We've just received {new_amount} sats! {difference_message} Goats like {goat_name} have been used in regenerative agriculture practices to restore degraded lands.\n\n https://lightning-goats.com\n\n",
    108: "Your donation of {new_amount} sats is greatly appreciated! {difference_message} Did you know? Goats have been domesticated for over 10,000 years, making them one of the earliest livestock animals.\n\n https://lightning-goats.com\n\n",
    109: "{new_amount} sats received! {difference_message} Goats are known for their diverse dietary preferences, and they are often used to manage invasive plant species.\n\n https://lightning-goats.com\n\n",
    110: "The herd has received {new_amount} sats! {difference_message} Goats' ability to thrive in extreme climates has made them a vital resource for many communities around the world.\n\n https://lightning-goats.com\n\n",
    111: "We've just received {new_amount} sats! {difference_message} Goats, like {goat_name}, are known for their inquisitive nature and will often explore their environment by nibbling on objects.\n\n https://lightning-goats.com\n\n",
    112: "{new_amount} sats have been received! {difference_message} Goats are renowned for their problem-solving abilities, and they can figure out how to open gates and navigate obstacles.\n\n https://lightning-goats.com\n\n",
    113: "Thanks for your {new_amount} sats donation! {difference_message} Goats, like {goat_name}, play a key role in maintaining the health of ecosystems through their selective grazing habits.\n\n https://lightning-goats.com\n\n",
    114: "Your donation of {new_amount} sats brings us closer to feeding time! {difference_message} Goats' strong herd instinct ensures that they stay close to their companions, providing protection and socialization.\n\n https://lightning-goats.com\n\n",
    115: "We've just received {new_amount} sats! {difference_message} Goats have been used in fire prevention efforts, as their grazing helps reduce the risk of wildfires by clearing dry brush.\n\n https://lightning-goats.com\n\n",
    116: "Thank you for your {new_amount} sats! {difference_message} Goats, like {goat_name}, have a natural curiosity that leads them to explore and investigate new environments.\n\n https://lightning-goats.com\n\n",
    117: "{new_amount} sats received! {difference_message} Goats' remarkable digestive systems allow them to process a wide variety of plant materials that are inedible to many other animals.\n\n https://lightning-goats.com\n\n",
    118: "We've just received {new_amount} sats! {difference_message} Goats like {goat_name} are excellent climbers, using their strong legs and hooves to navigate steep and rocky terrain.\n\n https://lightning-goats.com\n\n",
    119: "Thank you for your {new_amount} sats! {difference_message} Goats have been used in sustainable farming practices to manage vegetation and promote biodiversity.\n\n https://lightning-goats.com\n\n",
    120: "The herd has received {new_amount} sats! {difference_message} Goats are known for their strong sense of community and will often stay close to their herd for protection and companionship.\n\n https://lightning-goats.com\n\n",
    121: "Your donation of {new_amount} sats helps us get closer to feeding time! {difference_message} Goats like {goat_name} are known for their ability to thrive in arid environments, making them ideal livestock in many regions.\n\n https://lightning-goats.com\n\n",
    122: "{new_amount} sats have been received! {difference_message} Goats have a natural resistance to many common livestock diseases, which helps them thrive in diverse environments.\n\n https://lightning-goats.com\n\n",
    123: "Thanks for the {new_amount} sats! {difference_message} Did you know? Goats' digestive systems allow them to break down tough, fibrous plants, making them valuable contributors to land management.\n\n https://lightning-goats.com\n\n",
    124: "Your donation of {new_amount} sats has been received! {difference_message} Goats are social animals, and they often communicate with each other through a range of vocalizations and body language.\n\n https://lightning-goats.com\n\n",
    125: "{new_amount} sats have been added to the fund! {difference_message} Goats like {goat_name} play a key role in promoting biodiversity by selectively grazing on invasive plant species.\n\n https://lightning-goats.com\n\n",
    126: "The herd has received {new_amount} sats! {difference_message} Goats have been domesticated for over 10,000 years, making them one of the earliest livestock species.\n\n https://lightning-goats.com\n\n",
    127: "We've just received {new_amount} sats! {difference_message} Goats' ability to graze on tough, woody plants helps prevent soil erosion and promotes healthy ecosystems.\n\n https://lightning-goats.com\n\n",
    128: "{new_amount} sats have been received! {difference_message} Goats' strong sense of community helps them thrive in herds, providing safety and companionship for their members.\n\n https://lightning-goats.com\n\n",
    129: "Thank you for your {new_amount} sats! {difference_message} Goats, like {goat_name}, are used in sustainable farming practices to manage vegetation and reduce the need for chemical herbicides.\n\n https://lightning-goats.com\n\n",
    130: "We've received {new_amount} sats from a generous donor! {difference_message} Goats' remarkable ability to survive in arid and mountainous environments has made them a valuable resource for human societies worldwide.\n\n https://lightning-goats.com\n\n",
    131: "Thanks for your donation of {new_amount} sats! {difference_message} Goats are known for their playful personalities, and they often engage in activities like jumping, running, and head-butting to bond with others.\n\n https://lightning-goats.com\n\n",
    132: "Your {new_amount} sats help the herd thrive! {difference_message} Goats are known for their adaptability, and they can survive in a variety of climates and environments, from deserts to mountains.\n\n https://lightning-goats.com\n\n",
    133: "Thank you for the {new_amount} sats! {difference_message} Goats' ability to climb and balance on narrow ledges makes them uniquely suited to living in mountainous terrain.\n\n https://lightning-goats.com\n\n",
    134: "We've just received {new_amount} sats! {difference_message} Goats' natural browsing behavior helps prevent the spread of invasive plants and supports the health of native ecosystems.\n\n https://lightning-goats.com\n\n",
    135: "{new_amount} sats received! {difference_message} Goats have a remarkable ability to adapt to different climates and are capable of surviving in both hot and cold environments.\n\n https://lightning-goats.com\n\n",
    136: "The herd has received {new_amount} sats! {difference_message} Goats are used in many cultures around the world as symbols of fertility, abundance, and strength.\n\n https://lightning-goats.com\n\n",
    137: "Your donation of {new_amount} sats helps us reach our goal! {difference_message} Goats like {goat_name} are excellent at foraging for food, often consuming a wide variety of plants, including those that are toxic to other animals.\n\n https://lightning-goats.com\n\n",
    138: "Thank you for the {new_amount} sats! {difference_message} Goats' role in sustainable agriculture is vital, as they help maintain healthy ecosystems by consuming invasive plant species.\n\n https://lightning-goats.com\n\n",
    139: "{new_amount} sats have been added to the fund! {difference_message} Goats' four-chambered stomachs allow them to efficiently digest tough plant material, providing them with the nutrients they need to thrive.\n\n https://lightning-goats.com\n\n",
    140: "Thanks for donating {new_amount} sats! {difference_message} Goats, like {goat_name}, are highly social animals that enjoy the company of their herd and will often form close bonds with others.\n\n https://lightning-goats.com\n\n",
    141: "We've received {new_amount} sats! {difference_message} Goats' ability to climb and navigate rocky terrain allows them to access food sources that are out of reach for other animals.\n\n https://lightning-goats.com\n\n",
    142: "Your donation of {new_amount} sats has been received! {difference_message} Goats have a strong herd instinct, and they rely on the protection and companionship of their fellow herd members to stay safe.\n\n https://lightning-goats.com\n\n",
    143: "{new_amount} sats have been added! {difference_message} Goats' adaptability to different environments has made them one of the most widespread livestock animals in the world.\n\n https://lightning-goats.com\n\n",
    144: "Thank you for your {new_amount} sats donation! {difference_message} Goats like {goat_name} are known for their resilience and can survive in harsh conditions, making them ideal for farming in challenging environments.\n\n https://lightning-goats.com\n\n",
    145: "We've just received {new_amount} sats! {difference_message} Goats' remarkable sense of balance and coordination allows them to scale steep cliffs and climb trees in search of food.\n\n https://lightning-goats.com\n\n",
    146: "Thanks for your donation of {new_amount} sats! {difference_message} Goats, like {goat_name}, are capable of recognizing human voices and will often respond to familiar calls.\n\n https://lightning-goats.com\n\n",
    147: "Your {new_amount} sats help us reach our goal! {difference_message} Goats' playful behavior, including jumping and head-butting, is often a sign of happiness and well-being.\n\n https://lightning-goats.com\n\n",
    148: "{new_amount} sats have been received! {difference_message} Goats are known for their problem-solving abilities and can figure out how to open gates, navigate obstacles, and find food sources.\n\n https://lightning-goats.com\n\n",
    149: "Thank you for the {new_amount} sats! {difference_message} Goats like {goat_name} contribute to sustainable farming by helping manage overgrown vegetation and supporting ecosystem balance.\n\n https://lightning-goats.com\n\n"
}

headbutt_info_dict = {
    0: "⚡headbutt⚡: The ⚡ CyberHerd ⚡ is currently at full capacity. To join, a contribution of {required_sats} sats is needed to displace the member with the lowest contribution, {victim_name}.\n\n https://lightning-goats.com\n\n",
    1: "⚡headbutt⚡: The ⚡ CyberHerd ⚡ is at capacity. A contribution greater than {required_sats} sats will grant you {victim_name}'s position.\n\n https://lightning-goats.com\n\n",
    2: "⚡headbutt⚡: The ⚡ CyberHerd ⚡ is full. To become a member, you must contribute more than the lowest member's amount of {required_sats} sats, currently held by {victim_name}.\n\n https://lightning-goats.com\n\n",
    3: "⚡headbutt⚡: Membership in the ⚡ CyberHerd ⚡ is currently full. You can gain a spot by contributing at least {required_sats} sats, which will displace {victim_name}.\n\n https://lightning-goats.com\n\n",
    4: "⚡headbutt⚡: There are no available spots in the ⚡ CyberHerd ⚡. A contribution of {required_sats} sats or more is required to take the place of {victim_name}.\n\n https://lightning-goats.com\n\n"
}

headbutt_success_dict = {
    0: "⚡headbutt⚡: A new member has joined the ⚡ CyberHerd ⚡. {attacker_name} ({attacker_amount} sats) has displaced {victim_name} ({victim_amount} sats).\n\n https://lightning-goats.com\n\n",
    1: "⚡headbutt⚡: The ⚡ CyberHerd ⚡ roster has been updated. {attacker_name} ({attacker_amount} sats) has taken the position previously held by {victim_name} ({victim_amount} sats).\n\n https://lightning-goats.com\n\n",
    2: "⚡headbutt⚡: Membership change: {attacker_name} has entered the ⚡ CyberHerd ⚡ with a contribution of {attacker_amount} sats, displacing {victim_name} ({victim_amount} sats).\n\n https://lightning-goats.com\n\n",
    3: "⚡headbutt⚡: A position in the ⚡ CyberHerd ⚡ has been filled by {attacker_name} ({attacker_amount} sats). The previous member, {victim_name} ({victim_amount} sats), has been removed.\n\n https://lightning-goats.com\n\n",
    4: "⚡headbutt⚡: Update: {attacker_name} is now a member of the ⚡ CyberHerd ⚡ with a {attacker_amount} sat contribution, replacing {victim_name} ({victim_amount} sats).\n\n https://lightning-goats.com\n\n"
}

feeder_trigger_dict = {
    0: "Feeder Trigger Alert! {new_amount} sats added. Goats, like {goat_name}, have a remarkable digestive system with four chambers, which helps them break down tough plant material.\n\n https://lightning-goats.com\n\n",
    1: "The feeder has been triggered with {new_amount} sats! Fun fact: Goats have horizontal, rectangular pupils, which give them an expansive field of vision to spot predators.\n\n https://lightning-goats.com\n\n",
    2: "{new_amount} sats received! {goat_name} and the herd are enjoying a treat. Did you know? Goats have a strong sense of smell that helps them recognize other goats and identify food.\n\n https://lightning-goats.com\n\n",
    3: "The herd is happily munching away thanks to {new_amount} sats! Fun fact: Goats have an excellent memory and can remember people, locations, and routes for a long time.\n\n https://lightning-goats.com\n\n",
    4: "Feeder activated with {new_amount} sats! Goats like {goat_name} are incredibly agile and can climb steep terrain with ease.\n\n https://lightning-goats.com\n\n",
    5: "The feeder has been triggered with {new_amount} sats! Goats are known to be social animals, forming strong bonds with their herd and their human caretakers.\n\n https://lightning-goats.com\n\n",
    6: "{new_amount} sats have just been added to the feeder! Did you know? Goats’ coats can range from short and smooth to long and woolly, depending on the breed and environment.\n\n https://lightning-goats.com\n\n",
    7: "{goat_name} and the herd are feasting, thanks to {new_amount} sats! Goats’ ability to climb trees and steep cliffs helps them access food that other animals can’t reach.\n\n https://lightning-goats.com\n\n",
    8: "The goats are enjoying a feast, thanks to {new_amount} sats! Fun fact: Goats are browsers, meaning they prefer eating shrubs and leaves over grazing on grass like sheep and cows.\n\n https://lightning-goats.com\n\n",
    9: "Snack time for the goats with {new_amount} sats! Did you know? Goats can distinguish between different colors and have a preference for red and orange.\n\n https://lightning-goats.com\n\n",
    10: "Feeder triggered with {new_amount} sats! Goats like {goat_name} are incredibly curious and will explore their surroundings by sniffing and nibbling on objects.\n\n https://lightning-goats.com\n\n",
    11: "The goats are happily feasting on treats after {new_amount} sats were added! Did you know? Goats are capable of recognizing and responding to their own names, similar to dogs.\n\n https://lightning-goats.com\n\n",
    12: "{new_amount} sats received! Goats are enjoying their treats. Fun fact: Goats have scent glands located near their horns, which they use to mark their territory and attract mates.\n\n https://lightning-goats.com\n\n",
    13: "The herd is munching away on treats, thanks to {new_amount} sats! Goats have an exceptional sense of balance, which helps them climb and navigate rocky terrain.\n\n https://lightning-goats.com\n\n",
    14: "{new_amount} sats just filled the feeder! Goats like {goat_name} are known to be natural climbers and can scale cliffs, rocks, and even trees to find food.\n\n https://lightning-goats.com\n\n",
    15: "{new_amount} sats added! The herd is happily feasting. Did you know? A group of goats is called a trip, and they use various vocalizations to communicate within the herd.\n\n https://lightning-goats.com\n\n",
    16: "The goats are enjoying a meal thanks to {new_amount} sats! Goats are one of the oldest domesticated animals, having been used by humans for over 10,000 years.\n\n https://lightning-goats.com\n\n",
    17: "The feeder is full with {new_amount} sats! Goats are known for their playful behavior and often engage in activities like jumping and head-butting to pass the time.\n\n https://lightning-goats.com\n\n",
    18: "Snack time for the herd, thanks to {new_amount} sats! Goats are highly adaptable animals and can live in a variety of environments, from deserts to mountainous regions.\n\n https://lightning-goats.com\n\n",
    19: "The goats are munching on their treats after {new_amount} sats were added! Did you know? Goats have an excellent digestive system that allows them to eat a wide variety of plant materials.\n\n https://lightning-goats.com\n\n",
    20: "Feeder triggered with {new_amount} sats! Goats are browsers by nature and prefer eating bushes, leaves, and twigs over grass.\n\n https://lightning-goats.com\n\n",
    21: "The feeder has been filled with {new_amount} sats! Goats like {goat_name} are known to be very social animals, often bonding closely with other goats and their caretakers.\n\n https://lightning-goats.com\n\n",
    22: "The goats are happily munching away thanks to {new_amount} sats! Did you know? Goats’ hooves are divided into two toes, which helps them balance on rocky surfaces.\n\n https://lightning-goats.com\n\n",
    23: "{new_amount} sats just triggered the feeder! Goats are very intelligent animals and can learn to solve simple puzzles to get food rewards.\n\n https://lightning-goats.com\n\n",
    24: "Feeder activated with {new_amount} sats! Goats have a natural resistance to many diseases, which makes them hardy and adaptable animals.\n\n https://lightning-goats.com\n\n",
    25: "{new_amount} sats received! The herd is feasting. Did you know? Goat milk is naturally homogenized, meaning the cream does not separate as it does in cow’s milk.\n\n https://lightning-goats.com\n\n",
    26: "The goats are enjoying their treats after {new_amount} sats were added! Goats have scent glands that they use to mark territory and communicate with other goats.\n\n https://lightning-goats.com\n\n",
    27: "{new_amount} sats just triggered the feeder! Goats, like {goat_name}, are highly curious animals and will often investigate anything new in their environment.\n\n https://lightning-goats.com\n\n",
    28: "The feeder is full with {new_amount} sats! Did you know? Goats can live in harsh environments and have been bred to survive in climates ranging from arid deserts to high mountains.\n\n https://lightning-goats.com\n\n",
    29: "{new_amount} sats received! The goats are happily munching away. Goats are known for their strong sense of hierarchy within their herds.\n\n https://lightning-goats.com\n\n",
    30: "The goats are feasting after {new_amount} sats were added! Fun fact: Goats can recognize the emotions of other goats and even humans through body language.\n\n https://lightning-goats.com\n\n",
    31: "{new_amount} sats have just been added to the feeder! Goats are known for their playfulness and will often engage in head-butting contests with each other.\n\n https://lightning-goats.com\n\n",
    32: "The herd is munching on treats, thanks to {new_amount} sats! Did you know? Goats have a natural preference for eating high-fiber plants, such as twigs and leaves.\n\n https://lightning-goats.com\n\n",
    33: "Feeder activated with {new_amount} sats! Goats are known for their ability to climb and jump over obstacles, earning them a reputation as escape artists.\n\n https://lightning-goats.com\n\n",
    34: "The goats are happily feasting thanks to {new_amount} sats! Goats have excellent hearing and can detect sounds that are far away from their herd.\n\n https://lightning-goats.com\n\n",
    35: "{new_amount} sats received! The herd is enjoying their treats. Fun fact: Goats have horizontal pupils that allow them to see nearly 360 degrees around their bodies.\n\n https://lightning-goats.com\n\n",
    36: "The feeder is full with {new_amount} sats! Did you know? Goats have an exceptional sense of smell, which helps them find food and recognize other goats.\n\n https://lightning-goats.com\n\n",
    37: "Feeding time has arrived with {new_amount} sats! Goats can climb trees and steep cliffs to access food that other animals cannot reach.\n\n https://lightning-goats.com\n\n",
    38: "The feeder has been triggered with {new_amount} sats! Goats, like {goat_name}, are intelligent animals that can solve problems and navigate complex environments.\n\n https://lightning-goats.com\n\n",
    39: "{new_amount} sats have been added to the feeder! Goats are often used in sustainable farming to clear invasive plants and maintain biodiversity.\n\n https://lightning-goats.com\n\n",
    40: "Feeder triggered with {new_amount} sats! Did you know? Goats have strong social bonds within their herds and will often groom each other as a sign of affection.\n\n https://lightning-goats.com\n\n",
    41: "{new_amount} sats received! The goats are happily feasting. Goats are one of the few animals that are capable of swimming, though they do not typically need to do so in the wild.\n\n https://lightning-goats.com\n\n",
    42: "Feeder activated with {new_amount} sats! Goats are excellent climbers, and their strong legs and hooves allow them to navigate rocky terrain with ease.\n\n https://lightning-goats.com\n\n",
    43: "The goats are munching away thanks to {new_amount} sats! Fun fact: Goats can rotate their ears independently to better detect sounds from different directions.\n\n https://lightning-goats.com\n\n",
    44: "The herd is feasting after {new_amount} sats were added! Did you know? Goats have a unique ability to digest plants that are toxic to many other animals.\n\n https://lightning-goats.com\n\n",
    45: "{new_amount} sats received! The goats are enjoying their treats. Goats, like {goat_name}, are naturally curious and will often nibble on objects just to explore them.\n\n https://lightning-goats.com\n\n",
    46: "The feeder is full with {new_amount} sats! Goats’ ability to balance on small ledges and climb trees makes them one of the most agile domestic animals.\n\n https://lightning-goats.com\n\n",
    47: "Feeder triggered with {new_amount} sats! Did you know? Goats are used in fire prevention programs to clear dry brush and reduce the risk of wildfires.\n\n https://lightning-goats.com\n\n",
    48: "{new_amount} sats received! The goats are happily munching away. Goats have a keen sense of direction and can remember routes and locations for long periods of time.\n\n https://lightning-goats.com\n\n",
    49: "The feeder has been filled with {new_amount} sats! Goats can recognize individual human faces and will often form strong bonds with their caretakers.\n\n https://lightning-goats.com\n\n",
    50: "{new_amount} sats just triggered the feeder! Goats’ ability to eat a wide variety of plants helps maintain the health of grazing land and promote biodiversity.\n\n https://lightning-goats.com\n\n",
    51: "The goats are feasting after {new_amount} sats were added! Goats can produce up to a gallon of milk per day, depending on their breed and diet.\n\n https://lightning-goats.com\n\n",
    52: "Feeder activated with {new_amount} sats! Did you know? Goats can survive in environments with limited water and food, making them well-suited for arid climates.\n\n https://lightning-goats.com\n\n",
    53: "{new_amount} sats received! The goats are enjoying their meal. Fun fact: Goats use their strong front legs to rear up and knock down branches to access food.\n\n https://lightning-goats.com\n\n",
    54: "The feeder is full with {new_amount} sats! Goats’ wool is highly prized for its quality, with breeds like Angora and Cashmere producing some of the finest fibers.\n\n https://lightning-goats.com\n\n",
    55: "The herd is munching on their treats after {new_amount} sats were added! Goats, like {goat_name}, have a diverse diet and can eat over 500 different types of plants.\n\n https://lightning-goats.com\n\n",
    56: "{new_amount} sats just triggered the feeder! Goats are natural climbers, and their hooves are specially adapted to grip rocks and steep surfaces.\n\n https://lightning-goats.com\n\n",
    57: "The goats are happily feasting after {new_amount} sats were added! Goats’ ability to browse on thorny plants makes them valuable for clearing overgrown land.\n\n https://lightning-goats.com\n\n",
    58: "{new_amount} sats received! The goats are munching on their treats. Goats are highly intelligent and can learn complex tasks, such as opening gates and solving puzzles.\n\n https://lightning-goats.com\n\n",
    59: "Feeder triggered with {new_amount} sats! Goats are known for their ability to adapt to various climates, making them one of the most versatile farm animals.\n\n https://lightning-goats.com\n\n",
    60: "The goats are feasting after {new_amount} sats were added! Goats can live in large herds, and they maintain complex social structures within the group.\n\n https://lightning-goats.com\n\n",
    61: "Feeder activated with {new_amount} sats! Did you know? Goats can be trained to pull carts and perform light farm work, making them useful in agricultural settings.\n\n https://lightning-goats.com\n\n",
    62: "{new_amount} sats received! The goats are enjoying their treats. Goats, like {goat_name}, prefer to eat higher-growing plants, such as shrubs and leaves, over grass.\n\n https://lightning-goats.com\n\n",
    63: "The feeder is full with {new_amount} sats! Goats’ excellent sense of balance allows them to graze on steep hillsides and rocky cliffs where other animals cannot.\n\n https://lightning-goats.com\n\n",
    64: "Feeder triggered with {new_amount} sats! Did you know? Goats are used in many cultures for ceremonial purposes, often symbolizing fertility and abundance.\n\n https://lightning-goats.com\n\n",
    65: "The goats are munching away after {new_amount} sats were added! Goats can rotate their ears to better hear sounds, helping them detect predators.\n\n https://lightning-goats.com\n\n",
    66: "{new_amount} sats received! The herd is feasting. Goats have individual personalities, and their temperaments can range from shy and quiet to bold and curious.\n\n https://lightning-goats.com\n\n",
    67: "The feeder has been triggered with {new_amount} sats! Goats’ ability to digest fibrous plants has made them essential for managing grazing lands and promoting soil health.\n\n https://lightning-goats.com\n\n",
    68: "{new_amount} sats received! The goats are happily feasting. Did you know? Goats are capable of discerning human facial expressions and tend to prefer happy faces.\n\n https://lightning-goats.com\n\n",
    69: "The feeder is full with {new_amount} sats! Goats’ strong front legs allow them to rear up and knock down branches to reach food that is high up.\n\n https://lightning-goats.com\n\n",
    70: "Feeder triggered with {new_amount} sats! Did you know? Goats' horns continue to grow throughout their lives, and they use them for defense, dominance displays, and temperature regulation.\n\n https://lightning-goats.com\n\n",
    71: "The goats are munching on their treats after {new_amount} sats were added! Goats’ ability to browse on thorny and woody plants helps them survive in environments where food is scarce.\n\n https://lightning-goats.com\n\n",
    72: "The feeder has been filled with {new_amount} sats! Goats, like {goat_name}, are naturally inquisitive animals and will often explore new environments by nibbling on objects.\n\n https://lightning-goats.com\n\n",
    73: "{new_amount} sats just triggered the feeder! Goats’ social nature makes them excellent therapy animals, often helping reduce stress and anxiety in humans.\n\n https://lightning-goats.com\n\n",
    74: "Feeder activated with {new_amount} sats! Goats can recognize the voices of their human caretakers and will respond to familiar calls.\n\n https://lightning-goats.com\n\n",
    75: "{new_amount} sats received! The goats are happily feasting. Goats' ability to rotate their ears allows them to detect sounds from multiple directions at once.\n\n https://lightning-goats.com\n\n",
    76: "The feeder is full with {new_amount} sats! Did you know? Goats' strong digestive systems allow them to eat plants that are toxic to many other animals.\n\n https://lightning-goats.com\n\n",
    77: "{new_amount} sats received! The herd is munching away. Goats' ability to thrive in a variety of climates has made them a valuable resource for people worldwide.\n\n https://lightning-goats.com\n\n",
    78: "The feeder has been triggered with {new_amount} sats! Goats' unique ability to climb steep cliffs and trees makes them one of the most agile farm animals.\n\n https://lightning-goats.com\n\n",
    79: "Feeder activated with {new_amount} sats! Goats' playful behavior, such as jumping and spinning, is often a sign of excitement and happiness.\n\n https://lightning-goats.com\n\n",
    80: "The goats are munching away after {new_amount} sats were added! Goats' four-chambered stomach helps them efficiently digest fibrous plants and extract nutrients.\n\n https://lightning-goats.com\n\n",
    81: "The feeder is full with {new_amount} sats! Goats are natural climbers, and their ability to balance on narrow ledges allows them to reach food that other animals can't.\n\n https://lightning-goats.com\n\n",
    82: "Feeder triggered with {new_amount} sats! Did you know? Goats' ability to recognize individual voices and faces allows them to form strong bonds with their caretakers.\n\n https://lightning-goats.com\n\n",
    83: "{new_amount} sats just triggered the feeder! Goats are one of the few animals that can see in both low-light and bright conditions, thanks to their horizontal pupils.\n\n https://lightning-goats.com\n\n",
    84: "The herd is feasting after {new_amount} sats were added! Goats' adaptability to different environments has made them one of the most widespread farm animals in the world.\n\n https://lightning-goats.com\n\n",
    85: "Feeder activated with {new_amount} sats! Goats' wool is highly prized in the textile industry, with certain breeds producing fibers like mohair and cashmere.\n\n https://lightning-goats.com\n\n",
    86: "The goats are munching on their treats after {new_amount} sats were added! Goats are known for their social behavior, often forming strong bonds with other goats and even humans.\n\n https://lightning-goats.com\n\n",
    87: "Feeder triggered with {new_amount} sats! Did you know? Goats' digestive systems allow them to eat plants that are considered toxic to many other animals.\n\n https://lightning-goats.com\n\n",
    88: "The herd is munching away after {new_amount} sats were added! Goats' keen sense of smell helps them locate food and identify other goats within their herd.\n\n https://lightning-goats.com\n\n",
    89: "The feeder has been triggered with {new_amount} sats! Goats' ability to climb steep slopes and cliffs makes them one of the most versatile farm animals.\n\n https://lightning-goats.com\n\n",
    90: "Feeder activated with {new_amount} sats! Goats' strong legs and hooves allow them to climb trees and rocky surfaces, making them adept at finding food in difficult environments.\n\n https://lightning-goats.com\n\n",
    91: "{new_amount} sats received! The goats are feasting happily. Did you know? Goats can live in herds ranging from small family groups to large herds of over 100 animals.\n\n https://lightning-goats.com\n\n",
    92: "The herd is munching away thanks to {new_amount} sats! Goats are used in many cultures as symbols of fertility, strength, and abundance.\n\n https://lightning-goats.com\n\n",
    93: "{new_amount} sats just triggered the feeder! Goats' ability to eat high-fiber plants helps them thrive in environments where food sources are limited.\n\n https://lightning-goats.com\n\n",
    94: "The goats are munching on their treats after {new_amount} sats were added! Goats are capable of recognizing individual human voices and will respond to their caretakers.\n\n https://lightning-goats.com\n\n",
    95: "Feeder activated with {new_amount} sats! Goats' natural climbing ability allows them to access food that other animals cannot, helping them survive in harsh environments.\n\n https://lightning-goats.com\n\n",
    96: "The feeder is full with {new_amount} sats! Goats' playful behavior, such as jumping and spinning, is often a sign of excitement and joy.\n\n https://lightning-goats.com\n\n",
    97: "Feeder triggered with {new_amount} sats! Goats are one of the most intelligent farm animals, capable of solving problems and learning complex tasks.\n\n https://lightning-goats.com\n\n",
    98: "The goats are happily munching away thanks to {new_amount} sats! Goats' ability to thrive in different climates has made them a valuable asset to people all over the world.\n\n https://lightning-goats.com\n\n",
    99: "{new_amount} sats received! The herd is feasting. Goats' ability to form strong social bonds with other goats and humans makes them excellent companions.\n\n https://lightning-goats.com\n\n"
}

variations = {
    0: "{difference} sats are required for feeder activation.",
    1: "The next feeding cycle will begin in {difference} sats.",
    2: "Awaiting a remaining {difference} sats to trigger the feeder.",
    3: "{difference} sats needed before the goats receive their treats.",
    4: "The feeder is {difference} sats away from activation.",
    5: "The feeding protocol will initiate after {difference} more sats.",
    6: "The system requires an additional {difference} sats to dispense treats.",
    7: "The feeder activation is pending {difference} more sats.",
    8: "{difference} sats remaining until the next scheduled feeding.",
    9: "Please note: {difference} more sats are needed for the next feeding.",
    10: "The feeder will dispense treats once {difference} more sats are contributed."
}

headbutt_failure_dict = {
    0: "⚡headbutt⚡: Contribution unsuccessful. {attacker_name}'s contribution of {attacker_amount} sats was not sufficient to join the ⚡ CyberHerd ⚡. A minimum of {required_amount} sats is required.\n\n https://lightning-goats.com\n\n",
    1: "⚡headbutt⚡: Your contribution of {attacker_amount} sats is less than the {required_amount} sats required to displace the lowest member of the ⚡ CyberHerd ⚡. Please try again with a larger amount.\n\n https://lightning-goats.com\n\n",
    2: "⚡headbutt⚡: The attempt by {attacker_name} to join the ⚡ CyberHerd ⚡ was unsuccessful. The contribution of {attacker_amount} sats did not meet the required {required_amount} sats.\n\n https://lightning-goats.com\n\n",
    3: "⚡headbutt⚡: Entry to the ⚡ CyberHerd ⚡ denied. Your {attacker_amount} sat contribution is below the current minimum of {required_amount} sats to join.\n\n https://lightning-goats.com\n\n",
    4: "⚡headbutt⚡: The submitted amount of {attacker_amount} sats from {attacker_name} is insufficient. To join the full herd, a contribution of {required_amount} sats or more is necessary.\n\n https://lightning-goats.com\n\n"
}

member_increase_dict = {
    0: "⚡CyberHerd⚡: {member_name} has increased their contribution by {increase_amount} sats, bringing their total to {new_total}. Biological fact: Goats are ruminants with a four-chambered stomach, allowing them to efficiently digest fibrous plants.\n\n https://lightning-goats.com\n\n",
    1: "⚡CyberHerd⚡: With an additional {increase_amount} sats, {member_name}'s new total is {new_total}. Did you know? The rectangular pupils of a goat provide a wide, 320-340 degree field of vision, aiding in predator detection.\n\n https://lightning-goats.com\n\n",
    2: "⚡CyberHerd⚡: {member_name} adds {increase_amount} sats, for a total of {new_total}. Historical fact: Goats were among the first animals to be domesticated by humans, approximately 10,000 years ago.\n\n https://lightning-goats.com\n\n",
    3: "⚡CyberHerd⚡: The fund grows as {member_name} contributes {increase_amount} more sats, reaching {new_total}. Social observation: Goats are herd animals and can become depressed if kept in isolation.\n\n https://lightning-goats.com\n\n",
    4: "⚡CyberHerd⚡: {member_name} has raised their contribution to {new_total} sats with an added {increase_amount}. Anatomical fact: Goats use their prehensile lips to be selective eaters, often choosing the most nutritious parts of a plant.\n\n https://lightning-goats.com\n\n",
    5: "⚡CyberHerd⚡: An additional {increase_amount} sats from {member_name} brings their total to {new_total}. Behavioral insight: Goats are known for their curiosity and intelligence, often exploring new things and solving simple problems.\n\n https://lightning-goats.com\n\n",
    6: "⚡CyberHerd⚡: {member_name}'s contribution has grown to {new_total} sats with {increase_amount} more. Did you know? Different goat breeds produce unique fibers, such as cashmere from Cashmere goats and mohair from Angora goats.\n\n https://lightning-goats.com\n\n",
    7: "⚡CyberHerd⚡: With a new contribution of {increase_amount} sats, {member_name}'s total is now {new_total}. Communication fact: Mother goats and their kids can recognize each other's calls, a bond that helps keep the young safe.\n\n https://lightning-goats.com\n\n",
    8: "⚡CyberHerd⚡: {member_name} has added {increase_amount} sats to the herd, for a new total of {new_total}. Agility fact: Goats are excellent climbers, with hooves adapted for gripping steep and rocky terrain.\n\n https://lightning-goats.com\n\n",
    9: "⚡CyberHerd⚡: The total from {member_name} is now {new_total} sats after contributing another {increase_amount}. Cognitive fact: Studies have shown that goats can differentiate between human facial expressions and prefer happy faces.\n\n https://lightning-goats.com\n\n",
    10: "⚡CyberHerd⚡: {member_name} contributes {increase_amount} more, bringing their total to {new_total}. Health fact: Goat milk is often considered easier to digest than cow's milk because it has smaller fat globules and is naturally homogenized.\n\n https://lightning-goats.com\n\n",
    11: "⚡CyberHerd⚡: A contribution of {increase_amount} sats from {member_name} increases their total to {new_total}. Did you know? 'Fainting' goats have a genetic condition called myotonia congenita, which causes their muscles to stiffen when startled.\n\n https://lightning-goats.com\n\n",
    12: "⚡CyberHerd⚡: {member_name} has increased their total to {new_total} sats by adding {increase_amount}. Environmental fact: Goats are effective browsers and are often used for land management to clear brush and control invasive plant species.\n\n https://lightning-goats.com\n\n",
    13: "⚡CyberHerd⚡: With {increase_amount} more sats, {member_name}'s total contribution is now {new_total}. Communication fact: Goats may develop 'accents,' with their bleats changing to sound like those of their social group.\n\n https://lightning-goats.com\n\n",
    14: "⚡CyberHerd⚡: {member_name} adds another {increase_amount} sats, reaching a total of {new_total}. Anatomical fact: Unlike sheep, the tails of most goat breeds point upwards unless the goat is sick or distressed.\n\n https://lightning-goats.com\n\n",
    15: "⚡CyberHerd⚡: {member_name} now has a total of {new_total} sats contributed after adding {increase_amount}. Did you know? A male goat is called a 'buck' or 'billy,' a female is a 'doe' or 'nanny,' and a young goat is a 'kid.'\n\n https://lightning-goats.com\n\n",
    16: "⚡CyberHerd⚡: The contribution from {member_name} grows by {increase_amount} sats to {new_total}. Historical legend: Coffee was supposedly discovered when an Ethiopian goat herder noticed his goats became energetic after eating coffee cherries.\n\n https://lightning-goats.com\n\n",
    17: "⚡CyberHerd⚡: {member_name} adds {increase_amount} more sats, for a new total of {new_total}. Dietary fact: Goats are selective feeders and will often refuse to eat hay that is soiled or has been trampled on.\n\n https://lightning-goats.com\n\n",
    18: "⚡CyberHerd⚡: {member_name}'s total contribution is now {new_total} sats after an increase of {increase_amount}. Did you know? Goats do not have teeth on their upper front jaw; instead, they have a hard dental pad.\n\n https://lightning-goats.com\n\n",
    19: "⚡CyberHerd⚡: With an added {increase_amount} sats, {member_name}'s total is now {new_total}. Behavioral insight: Goats dislike rain and puddles and will seek shelter to avoid getting wet.\n\n https://lightning-goats.com\n\n",
    20: "⚡CyberHerd⚡: {member_name} has increased their support with {increase_amount} more sats, reaching {new_total}. Global fact: More people worldwide consume goat milk than cow's milk.\n\n https://lightning-goats.com\n\n",
    21: "⚡CyberHerd⚡: An additional {increase_amount} sats from {member_name} brings their total to {new_total}. Social fact: Within a herd, goats form complex social structures and hierarchies.\n\n https://lightning-goats.com\n\n",
    22: "⚡CyberHerd⚡: {member_name} contributes {increase_amount} sats, bringing their total to {new_total}. Did you know? Goats can be taught their name and to come when called.\n\n https://lightning-goats.com\n\n",
    23: "⚡CyberHerd⚡: The total for {member_name} is now {new_total} sats after an addition of {increase_amount}. Anatomical fact: The beard-like appendages on a goat's neck are called wattles and serve no known purpose.\n\n https://lightning-goats.com\n\n",
    24: "⚡CyberHerd⚡: {member_name} has raised their contribution to {new_total} with {increase_amount} more sats. Cognitive fact: Goats have demonstrated long-term memory, remembering learned tasks for at least 10 months.\n\n https://lightning-goats.com\n\n",
    25: "⚡CyberHerd⚡: {member_name}'s contribution total is now {new_total} after adding {increase_amount} sats. Did you know? Goats use a sneeze-like sound to warn other herd members of potential danger.\n\n https://lightning-goats.com\n\n",
    26: "⚡CyberHerd⚡: By adding {increase_amount} sats, {member_name}'s total is now {new_total}. Environmental fact: Goats' grazing habits can help prevent wildfires by reducing the amount of flammable brush.\n\n https://lightning-goats.com\n\n",
    27: "⚡CyberHerd⚡: {member_name} has increased their contribution to {new_total} sats. Did you know? The lifespan of a domestic goat is typically between 15 and 18 years.\n\n https://lightning-goats.com\n\n",
    28: "⚡CyberHerd⚡: With another {increase_amount} sats, {member_name}'s total reaches {new_total}. Social fact: Mother goats will often call to their kids to ensure they remain close by in the herd.\n\n https://lightning-goats.com\n\n",
    29: "⚡CyberHerd⚡: {member_name} adds {increase_amount} sats to their total, which is now {new_total}. Did you know? The term 'scapegoat' originates from an ancient Hebrew tradition involving goats.\n\n https://lightning-goats.com\n\n",
    30: "⚡CyberHerd⚡: The total from {member_name} has grown to {new_total} sats with an additional {increase_amount}. Anatomical fact: A goat's horns are made of living bone surrounded by keratin and are used for defense, dominance, and thermoregulation.\n\n https://lightning-goats.com\n\n",
    31: "⚡CyberHerd⚡: {member_name}'s new total is {new_total} sats after a contribution of {increase_amount}. Behavioral fact: Goats are playful animals, especially when young, and engage in activities like climbing and jumping for enjoyment.\n\n https://lightning-goats.com\n\n",
    32: "⚡CyberHerd⚡: An increase of {increase_amount} sats brings {member_name}'s total to {new_total}. Did you know? There are over 210 breeds of goats in the world.\n\n https://lightning-goats.com\n\n",
    33: "⚡CyberHerd⚡: {member_name}'s contribution now stands at {new_total} sats after adding {increase_amount}. Sensory fact: Goats have an excellent sense of smell, which they use to find food and recognize other goats.\n\n https://lightning-goats.com\n\n",
    34: "⚡CyberHerd⚡: With an additional {increase_amount} sats, {member_name} has a new total of {new_total}. Did you know? Genetically engineered goats can produce spider silk protein in their milk, which has valuable applications.\n\n https://lightning-goats.com\n\n",
    35: "⚡CyberHerd⚡: {member_name} has added {increase_amount} sats, bringing their contribution to {new_total}. Ecological fact: In permaculture systems, goats are valued for their ability to clear land and provide manure for fertilizer.\n\n https://lightning-goats.com\n\n",
    36: "⚡CyberHerd⚡: The total from {member_name} is now {new_total} sats after contributing {increase_amount} more. Health fact: Goat meat is leaner and has less cholesterol than beef, pork, or even chicken.\n\n https://lightning-goats.com\n\n",
    37: "⚡CyberHerd⚡: {member_name} boosts their contribution by {increase_amount} sats, for a total of {new_total}. Did you know? A goat giving birth is said to be 'kidding.'\n\n https://lightning-goats.com\n\n",
    38: "⚡CyberHerd⚡: A new contribution of {increase_amount} sats brings {member_name}'s total to {new_total}. Vision fact: The unique shape of their pupils gives goats good night vision.\n\n https://lightning-goats.com\n\n",
    39: "⚡CyberHerd⚡: {member_name} has increased their support with another {increase_amount} sats, for a total of {new_total}. Agricultural fact: Goats play a vital role in sustainable agriculture by managing weeds without the need for herbicides.\n\n https://lightning-goats.com\n\n"
}

# Goat names mapping for message personalization
goat_names_dict = {
    "Dexter": [
        "nostr:nprofile1qqsw4zlzyfx43mc88psnlse8sywpfl45kuap9dy05yzkepkvu6ca5wg7qyak5",
        "ea8be2224d58ef0738613fc327811c14feb4b73a12b48fa1056c86cce6b1da39"
    ],
    "Rowan": [
        "nostr:nprofile1qqs2w94r0fs29gepzfn5zuaupn969gu3fstj3gq8kvw3cvx9fnxmaugwur22r",
        "a716a37a60a2a32112674173bc0ccba2a3914c1728a007b31d1c30c54ccdbef1"
    ],
    "Nova": [
        "nostr:nprofile1qqsrzy7clymq5xwcfhh0dfz6zfe7h63k8r0j8yr49mxu6as4yv2084s0vf035",
        "3113d8f9360a19d84deef6a45a1273ebea3638df2390752ecdcd76152314f3d6"
    ],
    "Cosmo": [
        "nostr:nprofile1qqsq6n8u7dzrnhhy7xy78k2ee7e4wxlgrkm5g2rgjl3napr9q54n4ncvkqcsj",
        "0d4cfcf34439dee4f189e3d959cfb3571be81db744286897e33e8465052b3acf"
    ],
    "Newton": [
        "nostr:nprofile1qqszdsnpyzwhjcqads3hwfywt5jfmy85jvx8yup06yq0klrh93ldjxc26lmyx",
        "26c261209d79601d6c2377248e5d249d90f4930c72702fd100fb7c772c7ed91b"
    ]
}

# Special messages
herd_reset_message = {
    "message": "🐐 The herd has been reset! All goats are back to the starting gate. Time to rebuild the Lightning Goats community from scratch. Who will be the first to contribute?\n\nhttps://lightning-goats.com\n\n"
}

# Daily reset messages
daily_reset_dict = {
    0: "🌙 Daily midnight reset: CyberHerd cleared, payment metrics reset, system refreshed for a new day",
    1: "🌅 New day, fresh start: CyberHerd has been reset for another day of Lightning Network activity",
    2: "🔄 Daily cycle complete: All systems reset, CyberHerd cleared, ready for new members"
}

# Feeding payout messages for CyberHerd treats
feeding_regular_dict = {
    0: "CyberHerd Treats: {new_amount} sats! Thanks for being part of the herd! 🐐⚡",
    1: "CyberHerd Treats: {new_amount} sats for our member {display_name}! 🐐🌟",
    2: "CyberHerd Treats: {new_amount} sats delivered to {display_name}! 🐐💰",
    3: "CyberHerd Treats: {new_amount} sats! Keep being awesome {display_name}! 🐐✨"
}

feeding_bonus_dict = {
    0: "CyberHerd Treats (Bonus): {new_amount} sats for outstanding participation! 🐐⚡",
    1: "CyberHerd Treats (Special): {new_amount} sats for being amazing! 🐐🌟",
    2: "CyberHerd Treats (Extra): {new_amount} sats because you're awesome! 🐐🎁"
}

feeding_remainder_dict = {
    0: "CyberHerd Treats (Remainder): {new_amount} sats from the feeding pool! 🐐💫",
    1: "CyberHerd Treats (Final): {new_amount} sats to complete distribution! 🐐✅"
}

feeding_fallback_dict = {
    0: "CyberHerd Treats (Remainder): {new_amount} sats from feeding distribution! 🐐⚡",
    1: "CyberHerd Treats (Reserve): {new_amount} sats (no active members)! 🐐💰",
    2: "CyberHerd Treats (Backup): {new_amount} sats (distribution recovery)! 🐐🔄"
}

# Payment metrics messages
payment_metrics_dict = {
    0: "📊 Payment metrics updated - check the system status!",
    1: "💰 Payment statistics have been refreshed!",
    2: "📈 Latest payment data available!"
}

# System status messages  
system_status_dict = {
    0: "⚙️ System status updated - all systems operational!",
    1: "🔧 Current system metrics available!",
    2: "📊 System health check completed!"
}

# Weather status messages
weather_status_dict = {
    0: "🌤️ Weather update received!",
    1: "🌡️ Latest weather conditions available!",
    2: "☀️ Weather data refreshed!"
}
