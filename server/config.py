import os
from dotenv import load_dotenv

load_dotenv()

# Render and Railway commonly provide PORT and require binding to 0.0.0.0.
# Keep local defaults for local dev while making production deployment safe.
HOST = os.getenv("HOST", "0.0.0.0" if os.getenv("RENDER") or os.getenv("RAILWAY_ENVIRONMENT") else "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))

# --- Supabase Database ---
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "") or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

# --- HTTP Email APIs (Recommended for Render / Cloud hosts to bypass SMTP port blocking) ---
EMAIL_PROVIDER = os.getenv("EMAIL_PROVIDER", "resend").strip().lower()
BREVO_API_KEY = os.getenv("BREVO_API_KEY", "")  # Free 300 emails/day, no credit card
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")  # Free 100 emails/day
EMAIL_FROM = os.getenv("EMAIL_FROM", "")

# --- Gmail REST API (OAuth2, HTTPS over Port 443) ---
GMAIL_CLIENT_ID = os.getenv("GMAIL_CLIENT_ID", "")
GMAIL_CLIENT_SECRET = os.getenv("GMAIL_CLIENT_SECRET", "")
GMAIL_REFRESH_TOKEN = os.getenv("GMAIL_REFRESH_TOKEN", "")
GMAIL_FROM_EMAIL = os.getenv("GMAIL_FROM_EMAIL", "")

# --- Gmail SMTP (Legacy fallback only; not recommended for Render) ---
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_APP_PASSWORD = os.getenv("SMTP_APP_PASSWORD")

# --- Security / OTP Policy ---
OTP_EXPIRY_MINUTES = int(os.getenv("OTP_EXPIRY_MINUTES", "5"))
OTP_MAX_ATTEMPTS = int(os.getenv("OTP_MAX_ATTEMPTS", "5"))
OTP_RESEND_COOLDOWN_SECONDS = int(os.getenv("OTP_RESEND_COOLDOWN_SECONDS", "30"))
EMAIL_VERIFICATION_TOKEN_TTL_MINUTES = int(os.getenv("EMAIL_VERIFICATION_TOKEN_TTL_MINUTES", "10"))

INVITATION_EXPIRY_MINUTES = int(os.getenv("INVITATION_EXPIRY_MINUTES", "5"))
RECONNECT_GRACE_SECONDS = int(os.getenv("RECONNECT_GRACE_SECONDS", "30"))
