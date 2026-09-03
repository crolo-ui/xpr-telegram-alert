import os
import json
import requests

ACCOUNT = "velav"
API_URL = "https://proton.protonuk.io/v2/history/get_actions"

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


def get_transfers():
    params = {
        "account": ACCOUNT,
        "act_name": "transfer",
        "transfer_to": ACCOUNT,
        "sort": "desc",
        "limit": 50
    }

    r = requests.get(API_URL, params=params, timeout=20)
    r.raise_for_status()

    return r.json().get("actions", [])


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

        message = (
            "🔔 XPR PAYMENT RECEIVED\n\n"
            f"💰 Amount: {quantity}\n"
            f"👤 From: @{sender}\n"
            f"📥 To: @{receiver}\n"
        )

        if memo:
            message += f"📝 Memo: {memo}\n"

        message += f"\n🔗 Transaction:\n{action.get('trx_id')}"

        send_telegram(message)

    state["seen"] = list(seen)[-200:]
    save_state(state)


if __name__ == "__main__":
    main()
