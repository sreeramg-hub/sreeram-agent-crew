"""
Standalone price alert script — no LLM, no agents.
Runs hourly via GitHub Actions. Sends an alert email if gold or silver
has dropped more than $ALERT_THRESHOLD_USD from the previous close.
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


def send_alert(subject: str, html: str) -> None:
    api_key = os.getenv("RESEND_API_KEY", "").strip()
    recipient = os.getenv("DIGEST_RECIPIENT_EMAIL", "").strip()
    if not api_key or not recipient:
        print("ERROR: RESEND_API_KEY or DIGEST_RECIPIENT_EMAIL not set.")
        return
    recipients = [r.strip() for r in recipient.split(",") if r.strip()]
    resend.api_key = api_key
    resend.Emails.send({
        "from": "Gold & Silver Agent <digest@resend.dev>",
        "to": recipients,
        "subject": subject,
        "html": html,
    })
    print(f"Alert sent: {subject}")


def build_alert_html(alerts: list[dict], checked_at: str) -> str:
    rows = ""
    for a in alerts:
        rows += f"""
        <tr>
          <td style="padding:12px;font-weight:bold;">{a['metal']}</td>
          <td style="padding:12px;">${a['current']:.2f}/{a['unit']}</td>
          <td style="padding:12px;">${a['prev_close']:.2f}/{a['unit']}</td>
          <td style="padding:12px;color:#cc0000;font-weight:bold;">
            ▼ ${a['drop']:.2f}
          </td>
        </tr>"""

    return f"""
<html>
<body style="font-family:Arial,sans-serif;max-width:600px;margin:auto;padding:20px;">
  <h2 style="color:#cc0000;">🚨 Price Drop Alert — {checked_at}</h2>
  <p>The following metal(s) have dropped more than <strong>${THRESHOLD:.0f}</strong>
     from the previous close:</p>
  <table style="border-collapse:collapse;width:100%;margin:20px 0;">
    <thead>
      <tr style="background:#f0f0f0;">
        <th style="padding:12px;text-align:left;">Metal</th>
        <th style="padding:12px;text-align:left;">Current</th>
        <th style="padding:12px;text-align:left;">Prev Close</th>
        <th style="padding:12px;text-align:left;">Drop</th>
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
            drop = prev_close - current
            print(f"{metal}: current=${current:.2f}, prev_close=${prev_close:.2f}, drop=${drop:.2f}")
            if drop > THRESHOLD:
                alerts.append({
                    "metal": metal,
                    "current": current,
                    "prev_close": prev_close,
                    "drop": drop,
                    "unit": cfg["unit"],
                })
        except Exception as e:
            errors.append(f"{metal}: {e}")
            print(f"ERROR fetching {metal}: {e}", file=sys.stderr)

    if alerts:
        metals_str = " & ".join(a["metal"] for a in alerts)
        subject = f"🚨 {metals_str} Price Drop Alert — {checked_at}"
        html = build_alert_html(alerts, checked_at)
        send_alert(subject, html)
    else:
        print(f"No alerts triggered. Threshold: ${THRESHOLD:.0f} drop from previous close.")

    if errors:
        print(f"Errors: {errors}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
