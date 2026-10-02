"""
Database table constants and entity models for Supabase.
"""
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


def gen_id() -> str:
    """Generate a random UUID string."""
    return str(uuid.uuid4())


# Table Names in Supabase
TABLE_USERS = "users"
TABLE_OTP_RECORDS = "otp_records"
TABLE_INVITATIONS = "chat_invitations"
TABLE_ROOMS = "rooms"


@dataclass
class User:
    id: str
    username: str
    email: str
    password_hash: str
    email_verified: bool = False
    created_at: Optional[str] = None


@dataclass
class OTPRecord:
    id: str
    email: str
    otp_hash: str
    expires_at: str
    attempts: int = 0
    used: bool = False
    created_at: Optional[str] = None


@dataclass
class Invitation:
    id: str
    sender_id: str
    receiver_id: str
    status: str  # PENDING, ACCEPTED, REJECTED, EXPIRED, CANCELLED
    expires_at: str
    created_at: Optional[str] = None


@dataclass
class Room:
    id: str
    user_a_id: str
    user_b_id: str
    status: str  # ACTIVE, TERMINATING, DELETED
    created_at: Optional[str] = None
