#payment_utils.py
import httpx
import logging
import json
import time
from event_utils import sign_event

logger = logging.getLogger(__name__)

async def make_lnurl_payment(lud16: str, amount: int, description: str = None, key: str = herd_key) -> dict:
    try:
        headers = {
            "accept": "application/json",
            "X-API-KEY": key,
            "Content-Type": "application/json"
        }

        lnurl_url = f"https://lnb.bolverker.com/api/v1/lnurlscan/{lud16}"
        lnurl_response = await httpx.get(lnurl_url, headers=headers)
        lnurl_response.raise_for_status()
        lnurl_data = lnurl_response.json()

        if not (lnurl_data['minSendable'] <= abs(amount) <= lnurl_data['maxSendable']):
            logger.error(f"{lud16}: amount {amount} is out of bounds (min: {lnurl_data['minSendable']}, max: {lnurl_data['maxSendable']})")
            return None

        payload = {
            "description_hash": lnurl_data["description_hash"],
            "callback": lnurl_data["callback"],
            "amount": amount,
            "comment": "Cyber Herd Treats",
            "memo": description if description is not None else "Cyber Herd Treats",
            "description": description if description is not None else "Cyber Herd Treats"
        }

        if lnurl_data["allowsNostr"] and lnurl_data["nostrPubkey"]:
            relays = ['wss://nostr-pub.wellorder.net', 'wss://relay.damus.io', 'wss://relay.primal.net']
            event_details = {
                "kind": 9734,
                "content": description if description is not None else "Cyber Herd Treats",
                "created_at": round(time.time()),
                "tags": [
                    ["relays", *relays],
                    ["amount", str(amount)],
                    ["p", lnurl_data["nostrPubkey"]]
                ],
                "pubkey": "669ebbcccf409ee0467a33660ae88fd17e5379e646e41d7c236ff4963f3c36b6"
            }
            signed_event = await sign_event(event_details, nos_sec)
            payload["nostr"] = json.dumps(signed_event)
            logger.info(f"{signed_event}")
            
        payment_url = "https://lnb.bolverker.com/api/v1/payments/lnurl"
        response = await httpx.post(payment_url, headers=headers, json=payload)
        response.raise_for_status()

        return response.json()

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP request failed with status code: {e.response.status_code}, response: {e.response.text}")
        return None

    except httpx.RequestError as e:
        logger.error(f"HTTP request failed: {e}")
        return None

    except ValueError as e:
        logger.error(f"Validation error: {e}")
        return None
        
async def create_invoice(client: httpx.AsyncClient, amount: int, memo: str, key: str = sat_key):
    try:
        url = "https://lnb.bolverker.com/api/v1/payments"

        headers = {
            "accept": "application/json",
            "X-API-KEY": key,
            "Content-Type": "application/json"
        }

        data = {
            "unit": "sat",
            "internal": False,
            "out": False,
            "amount": amount,
            "memo": memo,
        }

        response = await client.post(url, json=data, headers=headers)
        
        if response.status_code == 201:
            response_data = response.json()
            payment_request = response_data.get("payment_request")
            if payment_request:
                logger.info('Invoice created successfully.')
                return payment_request
            else:
                logger.error('Payment request not found in the response.')
                return None
        else:
            logger.error(f'Failed to create invoice, status code: {response.status_code}')
            return None
    except httpx.RequestError as e:
        logger.error(f'Failed to create invoice: {e}')
        return None
        
async def pay_invoice(client: httpx.AsyncClient, payment_request: str, key: str = herd_key):
    try:
        url = "https://lnb.bolverker.com/api/v1/payments"

        headers = {
            "accept": "application/json",
            "X-API-KEY": key,
            "Content-Type": "application/json"
        }

        data = {
            "unit": "sat",
            "internal": True,
            "out": True,
            "bolt11": payment_request
        }

        response = await client.post(url, json=data, headers=headers)
        
        if response.status_code == 201:
            logger.info('Invoice payment successful.')
            return 201
        else:
            logger.error(f'Failed to pay invoice, status code: {response.status_code}')
            return None
    except httpx.RequestError as e:
        logger.error(f'Failed to pay invoice: {e}')
        return None

async def send_payment():
    for retry in range(3):
         # Convert to millisats, keep 10%
        balance = await get_balance(client)
        withdraw = int(round(balance * 0.98) / 1000)
        memo = 'Reset Herd Wallet'

        payment_request = await create_invoice(client, withdraw, memo)
        payment_status = await pay_invoice(client, payment_request)

        if payment_status == 201:
            return payment_status
        else:
            logger.error(f"Failed to send payment on attempt {retry + 1}, status code: {payment_status}")
