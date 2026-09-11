"""
Security primitives for ShadowChat.

- Passwords are hashed with Argon2id (argon2-cffi), never stored in plaintext.
- OTPs are generated with `secrets` (cryptographically secure), never with `random`.
- Only the OTP's hash is ever stored; the plaintext OTP exists only in the
  outbound email and is never logged or printed to any terminal.
"""
import secrets
import hashlib

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHash

_ph = PasswordHasher()


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _ph.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHash):
        return False


def generate_otp() -> str:
    """6-digit OTP using a cryptographically secure RNG."""
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_otp(otp: str) -> str:
    return hashlib.sha256(otp.encode("utf-8")).hexdigest()


def verify_otp_hash(otp: str, otp_hash: str) -> bool:
    return secrets.compare_digest(hash_otp(otp), otp_hash)


def generate_token(n_bytes: int = 32) -> str:
    """Generic secure random token used for session tokens and
    short-lived email-verification tokens."""
    return secrets.token_urlsafe(n_bytes)
