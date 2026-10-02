"""Email delivery helpers for ShadowChat.

The app prefers HTTPS REST APIs instead of SMTP because Render and similar cloud
platforms commonly block raw outbound SMTP ports (25, 465, 587). These helpers
support Brevo, Resend, and Gmail REST API (OAuth2) over HTTPS on port 443.
"""
import base64
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import httpx

from . import config


def _gmail_oauth_credentials():
    try:
        from google.oauth2.credentials import Credentials
    except ImportError as exc:
        raise RuntimeError(
            "Gmail REST API dependencies are not installed. Run: pip install google-api-python-client google-auth google-auth-httplib2 google-auth-oauthlib"
        ) from exc

    if not config.GMAIL_CLIENT_ID or not config.GMAIL_CLIENT_SECRET or not config.GMAIL_REFRESH_TOKEN:
        raise RuntimeError("Gmail REST API credentials missing. Set GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET and GMAIL_REFRESH_TOKEN.")
    return Credentials(
        token=None,
        refresh_token=config.GMAIL_REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=config.GMAIL_CLIENT_ID,
        client_secret=config.GMAIL_CLIENT_SECRET,
        scopes=["https://www.googleapis.com/auth/gmail.send"],
    )


def send_email_via_brevo(to_email: str, subject: str, body: str) -> None:
    """Send through Brevo's HTTP API over HTTPS (port 443)."""
    sender_email = config.EMAIL_FROM or config.GMAIL_FROM_EMAIL or config.SMTP_USERNAME or "noreply@shadowchat.app"
    payload = {
        "sender": {"name": "ShadowChat", "email": sender_email},
        "to": [{"email": to_email}],
        "subject": subject,
        "textContent": body,
    }
    response = httpx.post(
        "https://api.brevo.com/v3/smtp/email",
        headers={
            "api-key": config.BREVO_API_KEY,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        json=payload,
        timeout=10.0,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"Brevo API error ({response.status_code}): {response.text}")


def send_email_via_resend(to_email: str, subject: str, body: str) -> None:
    """Send through Resend's HTTP API over HTTPS (port 443)."""
    sender = config.EMAIL_FROM or config.GMAIL_FROM_EMAIL or "ShadowChat <onboarding@resend.dev>"
    payload = {
        "from": sender,
        "to": [to_email],
        "subject": subject,
        "text": body,
    }
    response = httpx.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {config.RESEND_API_KEY}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=10.0,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"Resend API error ({response.status_code}): {response.text}")


def send_email_via_gmail_rest(to_email: str, subject: str, body: str) -> None:
    """Send mail through Gmail REST API using OAuth2 tokens over HTTPS (port 443)."""
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise RuntimeError(
            "Gmail REST API dependencies are not installed. Run: pip install google-api-python-client google-auth google-auth-httplib2 google-auth-oauthlib"
        ) from exc

    service = build("gmail", "v1", credentials=_gmail_oauth_credentials())
    sender = config.GMAIL_FROM_EMAIL or config.EMAIL_FROM or config.SMTP_USERNAME
    if not sender:
        raise RuntimeError("Gmail REST email requires GMAIL_FROM_EMAIL or EMAIL_FROM to be configured.")

    message = MIMEMultipart()
    message["From"] = sender
    message["To"] = to_email
    message["Subject"] = subject
    message.attach(MIMEText(body, "plain"))

    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
    service.users().messages().send(
        userId="me",
        body={"raw": raw_message},
    ).execute()


def send_email_via_smtp(to_email: str, subject: str, body: str) -> None:
    """Legacy SMTP fallback for local testing only."""
    if not config.SMTP_USERNAME or not config.SMTP_APP_PASSWORD:
        raise RuntimeError(
            "Email service is not configured. Set BREVO_API_KEY, RESEND_API_KEY, or Gmail REST API credentials."
        )

    msg = MIMEMultipart()
    msg["From"] = f"ShadowChat <{config.SMTP_USERNAME}>"
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    context = ssl.create_default_context()
    try:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=10) as server:
            server.starttls(context=context)
            server.login(config.SMTP_USERNAME, config.SMTP_APP_PASSWORD)
            server.sendmail(config.SMTP_USERNAME, to_email, msg.as_string())
    except (smtplib.SMTPConnectError, smtplib.SMTPAuthenticationError, TimeoutError, OSError) as exc:
        raise RuntimeError(
            f"SMTP failed ({exc}). Render blocks raw SMTP ports (25, 465, 587) by default. "
            "Configure BREVO_API_KEY, RESEND_API_KEY, or Gmail OAuth credentials instead."
        ) from exc


def send_email(to_email: str, subject: str, body: str) -> None:
    """Send an email using HTTPS APIs by default, with SMTP as a local fallback."""
    provider = (config.EMAIL_PROVIDER or "").strip().lower()

    if provider == "brevo" and config.BREVO_API_KEY:
        send_email_via_brevo(to_email, subject, body)
        return
    if provider == "resend" and config.RESEND_API_KEY:
        send_email_via_resend(to_email, subject, body)
        return
    if provider == "gmail_rest" and (
        config.GMAIL_CLIENT_ID and config.GMAIL_CLIENT_SECRET and config.GMAIL_REFRESH_TOKEN
    ):
        send_email_via_gmail_rest(to_email, subject, body)
        return

    if config.BREVO_API_KEY:
        send_email_via_brevo(to_email, subject, body)
        return
    if config.RESEND_API_KEY:
        send_email_via_resend(to_email, subject, body)
        return
    if config.GMAIL_CLIENT_ID and config.GMAIL_CLIENT_SECRET and config.GMAIL_REFRESH_TOKEN:
        send_email_via_gmail_rest(to_email, subject, body)
        return

    send_email_via_smtp(to_email, subject, body)


def send_otp_email(to_email: str, otp: str) -> None:
    subject = "Your ShadowChat verification code"
    body = (
        f"Your ShadowChat verification code is:\n\n"
        f"{otp}\n\n"
        f"This code expires in {config.OTP_EXPIRY_MINUTES} minutes.\n\n"
        f"If you did not request this code, ignore this email."
    )
    send_email(to_email, subject, body)


def send_invitation_email(to_email: str, sender_username: str) -> None:
    subject = "New private chat request"
    body = (
        "ShadowChat Notification\n\n"
        f"User @{sender_username} wants to start a private conversation with you.\n\n"
        "Log into ShadowChat to accept or reject this request.\n\n"
        "This invitation will expire automatically."
    )
    send_email(to_email, subject, body)


def send_invitation_rejected_email(to_email: str, receiver_username: str) -> None:
    subject = "Private chat request declined"
    body = (
        "ShadowChat Notification\n\n"
        f"User @{receiver_username} declined your private chat request."
    )
    send_email(to_email, subject, body)
