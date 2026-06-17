import os
import pathlib
from typing import Type

import resend
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

DIGEST_FILE = pathlib.Path("digest.html")


class SendEmailInput(BaseModel):
    subject: str = Field(..., description="Email subject line.")


class SendEmailTool(BaseTool):
    name: str = "send_email"
    description: str = (
        "Sends the daily digest email. Reads the HTML body from digest.html "
        "automatically — you only need to provide the subject line. "
        "Input: subject (string)."
    )
    args_schema: Type[BaseModel] = SendEmailInput

    def _run(self, subject: str) -> str:
        api_key = os.getenv("RESEND_API_KEY", "").strip()
        recipient = os.getenv("DIGEST_RECIPIENT_EMAIL", "").strip()

        if not api_key:
            return "ERROR: RESEND_API_KEY is not set. Email not sent."
        if not recipient:
            return "ERROR: DIGEST_RECIPIENT_EMAIL is not set. Email not sent."

        # Support comma-separated list of recipients
        recipients = [r.strip() for r in recipient.split(",") if r.strip()]

        if not DIGEST_FILE.exists():
            return f"ERROR: {DIGEST_FILE} not found. Compose task may not have run yet."

        html_body = DIGEST_FILE.read_text(encoding="utf-8")

        resend.api_key = api_key

        try:
            response = resend.Emails.send({
                "from": "Daily Digest <digest@resend.dev>",
                "to": recipients,
                "subject": subject,
                "html": html_body,
            })
            return (
                f"Email sent successfully. "
                f"ID: {response.get('id', 'unknown')}. "
                f"Subject: '{subject}' → {', '.join(recipients)}"
            )
        except Exception as e:
            return f"Failed to send email: {e}"
