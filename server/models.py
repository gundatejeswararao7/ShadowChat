import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, Integer, ForeignKey
from .database import Base


def gen_id() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=gen_id)
    username = Column(String, unique=True, nullable=False, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    email_verified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class OTPRecord(Base):
    __tablename__ = "otp_records"

    id = Column(String, primary_key=True, default=gen_id)
    email = Column(String, nullable=False, index=True)
    otp_hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    attempts = Column(Integer, default=0)
    used = Column(Boolean, default=False)


class Invitation(Base):
    __tablename__ = "chat_invitations"

    id = Column(String, primary_key=True, default=gen_id)
    sender_id = Column(String, ForeignKey("users.id"), nullable=False)
    receiver_id = Column(String, ForeignKey("users.id"), nullable=False)
    # PENDING, ACCEPTED, REJECTED, EXPIRED, CANCELLED
    status = Column(String, default="PENDING", index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)


class Room(Base):
    __tablename__ = "rooms"

    id = Column(String, primary_key=True, default=gen_id)
    user_a_id = Column(String, ForeignKey("users.id"), nullable=False)
    user_b_id = Column(String, ForeignKey("users.id"), nullable=False)
    # ACTIVE, TERMINATING, DELETED
    status = Column(String, default="ACTIVE", index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
