import os
import json
import requests
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

ACCOUNT = "networkbsc"

API_URLS = [
    "https://proton.protonuk.io/v2/history/get_actions",
    "https://api-xprnetwork-main.saltant.io/v2/history/get_actions"
]

TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]

STATE_FILE = "state.json"


def load_state():
    if not os.path.exists(STATE_FILE):
        return {"seen": []}

    with open(STATE_FILE, "r") as f:
        return json.load(f)


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def send_telegram(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

    r = requests.post(
        url,
        json={
            "chat_id": CHAT_ID,
            "text": text,
            "disable_web_page_preview": True
        },
        timeout=20
    )

    r.raise_for_status()


def get_xpr_price():
    urls = [
        "https://api.coingecko.com/api/v3/simple/price",
        "https://pro-api.coingecko.com/api/v3/simple/price"
    ]

    params = {
        "ids": "xpr-network",
        "vs_currencies": "usd"
    }

    for url in urls:
        try:
            r = requests.get(
                url,
                params=params,
                timeout=10
            )

            if r.status_code == 200:
                data = r.json()

                price = data.get("xpr-network", {}).get("usd")

                if price is not None:
                    return float(price)

        except Exception as e:
            print(f"WARNING: XPR price request failed: {e}")

    print("WARNING: Could not get XPR price from CoinGecko.")
    return None


def convert_to_ist(timestamp):
    try:
        dt = datetime.fromisoformat(
            timestamp.replace("Z", "+00:00")
        )

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        ist = dt.astimezone(ZoneInfo("Asia/Kolkata"))

        return ist.strftime("%Y-%m-%d %I:%M:%S %p IST")

    except Exception as e:
        print(f"WARNING: Could not convert timestamp to IST: {e}")
        return timestamp


def get_transfers():
    params = {
        "account": ACCOUNT,
        "act_name": "transfer",
        "transfer_to": ACCOUNT,
        "sort": "desc",
        "limit": 50
    }

    last_error = None

    for api_url in API_URLS:
        for attempt in range(3):
            try:
                r = requests.get(
                    api_url,
                    params=params,
                    timeout=20
                )

                if r.status_code in (429, 500, 502, 503, 504):
                    last_error = requests.HTTPError(
                        f"{r.status_code} Server Error for {api_url}"
                    )

                    if attempt < 2:
                        import time
                        time.sleep(2 + attempt * 3)
                        continue

                    break

                r.raise_for_status()

                return r.json().get("actions", [])

            except requests.RequestException as e:
                last_error = e

                if attempt < 2:
                    import time
                    time.sleep(2 + attempt * 3)

    print(f"WARNING: XPR history APIs unavailable: {last_error}")

    return []


def main():
    state = load_state()
    seen = set(state.get("seen", []))

    actions = get_transfers()

    # First run: record existing transactions.
    # This prevents old payments from triggering alerts.
    if not seen:
        for action in actions:
            trx = action.get("trx_id")

            if trx:
                seen.add(trx)

        state["seen"] = list(seen)[-200:]
        save_state(state)

        return

    new_actions = []

    for action in actions:
        trx = action.get("trx_id")

        if not trx or trx in seen:
            continue

        seen.add(trx)
        new_actions.append(action)

    for action in reversed(new_actions):
        data = action.get("act", {}).get("data", {})

        sender = data.get("from", "unknown")
        receiver = data.get("to", ACCOUNT)
        quantity = data.get("quantity", "unknown")
        memo = data.get("memo", "")

        timestamp = action.get("timestamp", "")
        ist_time = convert_to_ist(timestamp)

        xpr_value = None

        try:
            xpr_amount = float(quantity.split()[0])
            xpr_price = get_xpr_price()

            if xpr_price is not None:
                xpr_value = xpr_amount * xpr_price

        except (ValueError, AttributeError):
            pass

        message = (
            "🔔 XPR PAYMENT RECEIVED\n\n"
            f"💰 Amount: {quantity}\n"
        )

        if xpr_value is not None:
            message += f"💵 Value: ~${xpr_value:.4f} USDT\n"

        message += (
            f"👤 From: @{sender}\n"
            f"📥 To: @{receiver}\n"
            f"🕐 Time: {ist_time}\n"
        )

        if memo:
            message += f"📝 Memo: {memo}\n"

        message += f"\n🔗 Transaction:\n{action.get('trx_id')}"

        send_telegram(message)

    state["seen"] = list(seen)[-200:]

    save_state(state)


if __name__ == "__main__":
    main()
