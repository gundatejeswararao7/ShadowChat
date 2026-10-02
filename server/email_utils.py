"""
Email utility supporting both HTTP REST APIs (Brevo, Resend) and Gmail SMTP.

Why HTTP APIs?
Cloud platforms like Render automatically block raw SMTP ports (25, 465, 587)
on free tiers, and Google often blocks connections from cloud datacenter IPs.
HTTP APIs (Brevo, Resend) communicate over standard HTTPS (Port 443), which is
never blocked and has near 100% deliverability.
"""
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import httpx

from . import config


def send_email_via_brevo(to_email: str, subject: str, body: str) -> None:
    """Send via Brevo (Sendinblue) HTTP API over HTTPS (Port 443).
    Bypasses all cloud SMTP port blocking. Free 300 emails/day."""
    sender_email = config.EMAIL_FROM or config.SMTP_USERNAME or "noreply@shadowchat.app"
    sender_name = "ShadowChat"
    payload = {
        "sender": {"name": sender_name, "email": sender_email},
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
    """Send via Resend HTTP API over HTTPS (Port 443)."""
    sender = config.EMAIL_FROM or "ShadowChat <onboarding@resend.dev>"
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


def send_email_via_smtp(to_email: str, subject: str, body: str) -> None:
    """Send via traditional SMTP (Gmail)."""
    if not config.SMTP_USERNAME or not config.SMTP_APP_PASSWORD:
        raise RuntimeError(
            "Email service is not configured. Set BREVO_API_KEY or SMTP_USERNAME and SMTP_APP_PASSWORD."
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
            f"SMTP failed ({exc}). Render blocks raw SMTP ports (25, 465, 587) by default, "
            "and Google blocks logins from cloud datacenter IPs. "
            "Fix: Add BREVO_API_KEY or RESEND_API_KEY to send via HTTPS (Port 443)."
        ) from exc


def send_email(to_email: str, subject: str, body: str) -> None:
    """Send an email using Brevo, Resend, or SMTP."""
    # 1. Prefer Brevo HTTP API (Port 443 - free 300 emails/day, no domain required)
    if config.BREVO_API_KEY:
        send_email_via_brevo(to_email, subject, body)
        return

    # 2. Prefer Resend HTTP API (Port 443)
    if config.RESEND_API_KEY:
        send_email_via_resend(to_email, subject, body)
        return

    # 3. Fallback to Gmail SMTP
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
