"""
Gmail SMTP integration.

Only ever uses a dedicated sender account's App Password (never a user's
personal Gmail password, and never the account's normal login password).
Credentials are read from environment variables and must never be hard-coded
or committed to source control.
"""
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from . import config


def send_email(to_email: str, subject: str, body: str) -> None:
    if not config.SMTP_USERNAME or not config.SMTP_APP_PASSWORD:
        raise RuntimeError(
            "SMTP is not configured. Set SMTP_USERNAME and SMTP_APP_PASSWORD "
            "(a Gmail App Password, not your normal password) in your .env file."
        )

    msg = MIMEMultipart()
    msg["From"] = f"ShadowChat <{config.SMTP_USERNAME}>"
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    context = ssl.create_default_context()
    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT) as server:
        server.starttls(context=context)
        server.login(config.SMTP_USERNAME, config.SMTP_APP_PASSWORD)
        server.sendmail(config.SMTP_USERNAME, to_email, msg.as_string())


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
        f"User {sender_username} wants to start a private conversation with you.\n\n"
        "Log into ShadowChat to accept or reject this request.\n\n"
        "This invitation will expire automatically."
    )
    send_email(to_email, subject, body)


def send_invitation_rejected_email(to_email: str, receiver_username: str) -> None:
    subject = "Private chat request declined"
    body = (
        "ShadowChat Notification\n\n"
        f"User {receiver_username} declined your private chat request."
    )
    send_email(to_email, subject, body)
