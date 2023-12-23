import asyncio
from nak_command import run_nostr_command

async def test_run_nostr_command():
    # Example test data
    nos_sec = "9f1467b2d360e294e3cc74b2f8ef62e728b8ccca7fbfa7b06200a03e68e99038"
    event_id="93f3929637d20b7a0df8b10fdc95c83642b3829a3deea83f91bfa8580f5592ec"
    npub="npub1s6sx3jta428aascy2cu3frjc8fnydguuhjs6zlsys3sgvxau5p6ser8ehw"
    pubkey="86a068c97daa8fdec3045639148e583a6646a39cbca1a17e048460861bbca075"
    new_amount = 50.0
    difference = 2158
    event_types = ["cyber_herd"] #"sats_received", "feeder_triggered", 

    # Simulating each event type
    for event_type in event_types:
        print(f"\nTesting event type: {event_type}\n")
        if event_type == "cyber_herd":
            message = await run_nostr_command(nos_sec, new_amount, difference, event_type, event_id, pubkey, npub)
        else:
            message = await run_nostr_command(nos_sec, new_amount, difference, event_type)

        print(f"{message}")

# Run the test
asyncio.run(test_run_nostr_command())

