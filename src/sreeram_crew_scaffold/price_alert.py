"""
Standalone price alert script — no LLM, no agents.
Runs hourly via GitHub Actions.

Alert logic:
  Compares current price against the last price recorded by THIS script.
  Triggers if the move exceeds PRICE_ALERT_THRESHOLD_USD in either direction.
  After alerting, the new price becomes the baseline — so the same price
  level won't trigger again on the next run (fixes repeated weekend alerts).

Notifications: ntfy.sh push only (free, no account needed).
  Install the ntfy app, subscribe to your NTFY_TOPIC.
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

THRESHOLD = float(os.getenv("PRICE_ALERT_THRESHOLD_USD", "75"))
STATE_FILE = Path("state/price_last_seen.json")

METALS = {
    "Gold":   "GC%3DF",
    "Silver": "SI%3DF",
}


def fetch_price(ticker: str) -> float:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=1d"
    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
    resp.raise_for_status()
    return resp.json()["chart"]["result"][0]["meta"]["regularMarketPrice"]


def load_last_seen() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def save_last_seen(prices: dict) -> None:
    STATE_FILE.parent.mkdir(exist_ok=True)
    data = {**prices, "updated_at": datetime.now(timezone.utc).isoformat()}
    STATE_FILE.write_text(json.dumps(data, indent=2))


def send_push(title: str, message: str) -> None:
    topic = os.getenv("NTFY_TOPIC", "").strip()
    if not topic:
        print("Skipping push: NTFY_TOPIC not set.")
        return
    try:
        requests.post(
            f"https://ntfy.sh/{topic}",
            data=message.encode("utf-8"),
            headers={"Title": title, "Priority": "high", "Tags": "rotating_light"},
            timeout=10,
        )
        print(f"Push sent: {title}")
    except Exception as e:
        print(f"Push failed: {e}", file=sys.stderr)


def main() -> None:
    last_seen = load_last_seen()
    current_prices = {}
    alerts = []
    errors = []

    updated_state = {**last_seen}

    for metal, ticker in METALS.items():
        try:
            current = fetch_price(ticker)
            last = last_seen.get(metal)

            if last is None:
                # First run — establish baseline, no alert
                updated_state[metal] = current
                print(f"{metal}: ${current:.2f} (baseline set, no alert)")
                continue

            change = current - last
            print(f"{metal}: current=${current:.2f}, reference=${last:.2f}, change=${change:+.2f}")

            if abs(change) > THRESHOLD:
                direction = "up" if change > 0 else "down"
                alerts.append(
                    f"{metal}: ${current:.2f} ({direction} ${abs(change):.2f} from ${last:.2f})"
                )
                # Reset reference to current price so the same move doesn't re-alert
                updated_state[metal] = current
            # No alert: keep the old reference price so gradual moves accumulate

        except Exception as e:
            errors.append(f"{metal}: {e}")
            print(f"ERROR fetching {metal}: {e}", file=sys.stderr)

    save_last_seen(updated_state)

    if alerts:
        checked_at = datetime.now(timezone.utc).strftime("%b %d %H:%M UTC")
        send_push(
            title=f"🚨 Price Alert — {checked_at}",
            message="\n".join(alerts),
        )
    else:
        print(f"No alerts. Threshold: ±${THRESHOLD:.0f} from last seen price.")

    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
