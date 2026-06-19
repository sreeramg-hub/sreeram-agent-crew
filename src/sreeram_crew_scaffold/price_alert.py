"""
Standalone price alert script — no LLM, no agents.
Runs hourly via GitHub Actions. Sends an alert if gold or silver moves
more than $PRICE_ALERT_THRESHOLD_USD from the previous close (up or down).

Notifications:
  - Email via Resend (set RESEND_API_KEY + DIGEST_RECIPIENT_EMAIL)
  - Push notification via ntfy.sh (set NTFY_TOPIC) — free, no account needed
    Install the ntfy app on your phone and subscribe to your topic.
"""

import os
import sys
from datetime import datetime, timezone

import requests
import resend
from dotenv import load_dotenv

load_dotenv()

THRESHOLD = float(os.getenv("PRICE_ALERT_THRESHOLD_USD", "75"))

METALS = {
    "Gold":   {"ticker": "GC%3DF", "unit": "oz"},
    "Silver": {"ticker": "SI%3DF", "unit": "oz"},
}


def fetch_price(ticker: str) -> tuple[float, float]:
    """Returns (current_price, previous_close)."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=2d"
    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
    resp.raise_for_status()
    meta = resp.json()["chart"]["result"][0]["meta"]
    return meta["regularMarketPrice"], meta["chartPreviousClose"]


def send_email_alert(subject: str, html: str) -> None:
    api_key = os.getenv("RESEND_API_KEY", "").strip()
    recipient = os.getenv("DIGEST_RECIPIENT_EMAIL", "").strip()
    if not api_key or not recipient:
        print("Skipping email: RESEND_API_KEY or DIGEST_RECIPIENT_EMAIL not set.")
        return
    recipients = [r.strip() for r in recipient.split(",") if r.strip()]
    resend.api_key = api_key
    resend.Emails.send({
        "from": "Gold & Silver Agent <digest@resend.dev>",
        "to": recipients,
        "subject": subject,
        "html": html,
    })
    print(f"Email alert sent: {subject}")


def send_push_notification(title: str, message: str, priority: str = "high") -> None:
    """Send a push notification via ntfy.sh — free, no account needed.
    Install the ntfy app (iOS/Android), subscribe to your NTFY_TOPIC.
    Use a long random string as your topic to keep it private.
    """
    topic = os.getenv("NTFY_TOPIC", "").strip()
    if not topic:
        print("Skipping push notification: NTFY_TOPIC not set.")
        return
    try:
        requests.post(
            f"https://ntfy.sh/{topic}",
            data=message.encode("utf-8"),
            headers={
                "Title": title,
                "Priority": priority,
                "Tags": "rotating_light,chart_with_upwards_trend",
            },
            timeout=10,
        )
        print(f"Push notification sent: {title}")
    except Exception as e:
        print(f"Push notification failed: {e}", file=sys.stderr)


def build_alert_html(alerts: list[dict], checked_at: str) -> str:
    rows = ""
    for a in alerts:
        arrow = "▲" if a["change"] > 0 else "▼"
        color = "#cc0000" if a["change"] < 0 else "#007700"
        label = "Rise" if a["change"] > 0 else "Drop"
        rows += f"""
        <tr>
          <td style="padding:12px;font-weight:bold;">{a['metal']}</td>
          <td style="padding:12px;">${a['current']:.2f}/{a['unit']}</td>
          <td style="padding:12px;">${a['prev_close']:.2f}/{a['unit']}</td>
          <td style="padding:12px;color:{color};font-weight:bold;">
            {arrow} ${abs(a['change']):.2f} ({label})
          </td>
        </tr>"""

    return f"""
<html>
<body style="font-family:Arial,sans-serif;max-width:600px;margin:auto;padding:20px;">
  <h2 style="color:#cc0000;">🚨 Price Alert — {checked_at}</h2>
  <p>The following metal(s) have moved more than <strong>${THRESHOLD:.0f}</strong>
     from the previous close:</p>
  <table style="border-collapse:collapse;width:100%;margin:20px 0;">
    <thead>
      <tr style="background:#f0f0f0;">
        <th style="padding:12px;text-align:left;">Metal</th>
        <th style="padding:12px;text-align:left;">Current</th>
        <th style="padding:12px;text-align:left;">Prev Close</th>
        <th style="padding:12px;text-align:left;">Move</th>
      </tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>
  <p style="color:#888;font-size:12px;margin-top:30px;">
    This is an automated alert from your Gold &amp; Silver Agent.
    Prices sourced from Yahoo Finance. Not financial advice.
  </p>
</body>
</html>"""


def main() -> None:
    checked_at = datetime.now(timezone.utc).strftime("%B %d, %Y at %H:%M UTC")
    alerts = []
    errors = []

    for metal, cfg in METALS.items():
        try:
            current, prev_close = fetch_price(cfg["ticker"])
            change = current - prev_close
            print(f"{metal}: current=${current:.2f}, prev_close=${prev_close:.2f}, change=${change:+.2f}")
            if abs(change) > THRESHOLD:
                alerts.append({
                    "metal": metal,
                    "current": current,
                    "prev_close": prev_close,
                    "change": change,
                    "unit": cfg["unit"],
                })
        except Exception as e:
            errors.append(f"{metal}: {e}")
            print(f"ERROR fetching {metal}: {e}", file=sys.stderr)

    if alerts:
        metals_str = " & ".join(a["metal"] for a in alerts)
        directions = []
        for a in alerts:
            direction = "up" if a["change"] > 0 else "down"
            directions.append(f"{a['metal']} {direction} ${abs(a['change']):.2f}")
        summary = ", ".join(directions)

        subject = f"🚨 Price Alert: {metals_str} — {checked_at}"
        html = build_alert_html(alerts, checked_at)

        send_email_alert(subject, html)
        send_push_notification(
            title=f"🚨 {metals_str} Price Alert",
            message=f"{summary} from previous close. Check your digest for details.",
        )
    else:
        print(f"No alerts triggered. Threshold: ±${THRESHOLD:.0f} from previous close.")

    if errors:
        print(f"Errors: {errors}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
