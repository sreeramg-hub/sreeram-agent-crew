import os

import resend

SENDER = "Daily Digest <digest@resend.dev>"


def send_email(subject: str, html_body: str) -> str:
    """Send the digest through Resend. Raises on any failure so the run is marked failed."""
    api_key = os.getenv("RESEND_API_KEY", "").strip()
    recipient = os.getenv("DIGEST_RECIPIENT_EMAIL", "").strip()
    if not api_key:
        raise RuntimeError("RESEND_API_KEY is not set")
    if not recipient:
        raise RuntimeError("DIGEST_RECIPIENT_EMAIL is not set")

    recipients = [r.strip() for r in recipient.split(",") if r.strip()]
    resend.api_key = api_key
    response = resend.Emails.send(
        {"from": SENDER, "to": recipients, "subject": subject, "html": html_body}
    )
    return f"Sent '{subject}' to {', '.join(recipients)} (id {response.get('id', 'unknown')})"
