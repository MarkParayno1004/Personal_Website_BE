"""Transactional email via Resend's HTTP API; logs the message instead when RESEND_API_KEY is unset."""
import logging
import os
import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("mailer")

RESEND_API_KEY = os.getenv("RESEND_API_KEY")
EMAIL_FROM = os.getenv("EMAIL_FROM", "Portfolio <onboarding@resend.dev>")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/")
IS_PRODUCTION = os.getenv("APP_ENV", "development").lower() == "production"


def send_email(to: str, subject: str, text: str) -> bool:
    """Send a plain-text email. Never raises: callers run this in a background task."""
    if not RESEND_API_KEY:
        if IS_PRODUCTION:
            logger.error(f"[Mailer] RESEND_API_KEY is not set; email '{subject}' to {to} was not sent")
        else:
            logger.info(f"[Mailer] (dev, not sent) To: {to} | Subject: {subject}\n{text}")
        return False
    try:
        res = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
            json={"from": EMAIL_FROM, "to": [to], "subject": subject, "text": text},
            timeout=10,
        )
        res.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"[Mailer] Sending '{subject}' to {to} failed: {e}")
        return False


def send_verification_email(to: str, token: str) -> None:
    link = f"{FRONTEND_URL}/verify-email?token={token}"
    send_email(to, "Verify your email", f"Confirm your email address by opening this link:\n\n{link}\n\nThe link expires in 24 hours.")


def send_password_reset_email(to: str, token: str) -> None:
    link = f"{FRONTEND_URL}/reset-password?token={token}"
    send_email(
        to,
        "Reset your password",
        f"Reset your password by opening this link:\n\n{link}\n\n"
        "The link expires in 30 minutes and works once. If you did not ask for this, ignore this email.",
    )
