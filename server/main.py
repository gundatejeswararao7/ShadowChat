import asyncio
from datetime import datetime, timedelta

from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
from sqlalchemy import or_

from . import config, security, email_utils, schemas
from .database import init_db, get_db
from .models import User, OTPRecord, Invitation, Room
from .state import state, RoomState
from .key_manager import key_manager

app = FastAPI(title="ShadowChat Server")


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/health")
def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_user_by_token(token: str, db: Session) -> User:
    user_id = state.sessions.get(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired session token")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


async def schedule_invitation_expiry(invitation_id: str, delay_seconds: float):
    try:
        await asyncio.sleep(delay_seconds)
    except asyncio.CancelledError:
        return
    from .database import SessionLocal
    db = SessionLocal()
    try:
        inv = db.query(Invitation).filter(Invitation.id == invitation_id).first()
        if inv and inv.status == "PENDING":
            inv.status = "EXPIRED"
            db.commit()
            await state.send_to_user(inv.sender_id, {
                "type": "invitation_expired_sender",
                "invitation_id": invitation_id,
            })
            await state.send_to_user(inv.receiver_id, {
                "type": "invitation_expired",
                "invitation_id": invitation_id,
            })
    finally:
        db.close()
        state.invitation_expiry_tasks.pop(invitation_id, None)


async def terminate_room(room_id: str, reason: str):
    room = state.rooms.get(room_id)
    if not room or room.status == "DELETED":
        return
    room.status = "TERMINATING"

    from .database import SessionLocal
    db = SessionLocal()
    try:
        db_room = db.query(Room).filter(Room.id == room_id).first()
        if db_room:
            db_room.status = "DELETED"
            db.commit()
    finally:
        db.close()

    for uid in (room.user_a, room.user_b):
        state.active_room_of_user.pop(uid, None)
        await state.send_to_user(uid, {"type": "room_terminated", "reason": reason})

    task = state.disconnect_grace_tasks.pop(room.user_a, None) or state.disconnect_grace_tasks.pop(room.user_b, None)
    if task:
        task.cancel()

    key_manager.destroy_room_key(room_id)
    room.status = "DELETED"
    state.rooms.pop(room_id, None)


async def schedule_disconnect_grace(user_id: str, room_id: str, grace_seconds: int):
    try:
        await asyncio.sleep(grace_seconds)
    except asyncio.CancelledError:
        return
    # Still disconnected after grace period -> terminate the room.
    await terminate_room(room_id, "Reconnection timeout reached. Room terminated.")
    state.disconnect_grace_tasks.pop(user_id, None)


# ---------------------------------------------------------------------------
# Registration / OTP
# ---------------------------------------------------------------------------

@app.post("/register/start")
def register_start(req: schemas.RegisterStartRequest, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.email == req.email).first()
    if existing_user and existing_user.email_verified:
        raise HTTPException(status_code=400, detail="Email already registered")

    otp = security.generate_otp()
    otp_hash = security.hash_otp(otp)
    expires_at = datetime.utcnow() + timedelta(minutes=config.OTP_EXPIRY_MINUTES)

    # Invalidate any previous unused OTPs for this email.
    db.query(OTPRecord).filter(OTPRecord.email == req.email, OTPRecord.used == False).update({"used": True})  # noqa: E712

    record = OTPRecord(email=req.email, otp_hash=otp_hash, expires_at=expires_at)
    db.add(record)
    db.commit()

    # The OTP is sent ONLY by email. It is never returned in this response
    # and must never be printed by any client.
    email_utils.send_otp_email(req.email, otp)

    return {"status": "otp_sent", "expires_in_minutes": config.OTP_EXPIRY_MINUTES}


@app.post("/register/verify")
def register_verify(req: schemas.RegisterVerifyRequest, db: Session = Depends(get_db)):
    record = (
        db.query(OTPRecord)
        .filter(OTPRecord.email == req.email, OTPRecord.used == False)  # noqa: E712
        .order_by(OTPRecord.created_at.desc())
        .first()
    )
    if not record:
        raise HTTPException(status_code=400, detail="No pending verification for this email")

    if datetime.utcnow() > record.expires_at:
        raise HTTPException(status_code=400, detail="OTP expired. Please request a new one")

    if record.attempts >= config.OTP_MAX_ATTEMPTS:
        raise HTTPException(status_code=429, detail="Too many attempts. Please request a new OTP")

    record.attempts += 1

    if not security.verify_otp_hash(req.otp, record.otp_hash):
        db.commit()
        raise HTTPException(status_code=400, detail="Incorrect OTP")

    record.used = True
    db.commit()

    token = security.generate_token()
    state.email_verification_tokens[token] = {
        "email": req.email,
        "expires_at": datetime.utcnow() + timedelta(minutes=config.EMAIL_VERIFICATION_TOKEN_TTL_MINUTES),
    }
    return {"status": "verified", "verification_token": token}


@app.post("/register/complete")
def register_complete(req: schemas.RegisterCompleteRequest, db: Session = Depends(get_db)):
    entry = state.email_verification_tokens.get(req.verification_token)
    if not entry or datetime.utcnow() > entry["expires_at"]:
        raise HTTPException(status_code=400, detail="Verification token invalid or expired")

    email = entry["email"]

    if db.query(User).filter(User.username == req.username).first():
        raise HTTPException(status_code=400, detail="Username already taken")
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        username=req.username,
        email=email,
        password_hash=security.hash_password(req.password),
        email_verified=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    state.email_verification_tokens.pop(req.verification_token, None)

    return {"status": "account_created", "user_id": user.id, "username": user.username}


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

@app.post("/login")
def login(req: schemas.LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == req.username).first()
    if not user or not security.verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    if not user.email_verified:
        raise HTTPException(status_code=403, detail="Email not verified")

    token = security.generate_token()
    state.sessions[token] = user.id
    return {"status": "access_granted", "token": token, "username": user.username}


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

@app.get("/search")
def search_user(query: str, token: str, db: Session = Depends(get_db)):
    me = get_user_by_token(token, db)
    found = db.query(User).filter(User.username == query).first()
    if not found or found.id == me.id:
        raise HTTPException(status_code=404, detail=f'No user with ID "{query}"')
    return {
        "user_id": found.username,
        "status": "ONLINE" if state.is_online(found.id) else "OFFLINE",
    }


# ---------------------------------------------------------------------------
# Invitations
# ---------------------------------------------------------------------------

@app.post("/invite")
async def send_invitation(req: schemas.InviteRequest, db: Session = Depends(get_db)):
    sender = get_user_by_token(req.token, db)
    receiver = db.query(User).filter(User.username == req.receiver_username).first()
    if not receiver:
        raise HTTPException(status_code=404, detail=f'No user with ID "{req.receiver_username}"')
    if receiver.id == sender.id:
        raise HTTPException(status_code=400, detail="You cannot invite yourself")

    existing = (
        db.query(Invitation)
        .filter(
            Invitation.sender_id == sender.id,
            Invitation.receiver_id == receiver.id,
            Invitation.status == "PENDING",
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="An invitation to this user is already pending")

    expires_at = datetime.utcnow() + timedelta(minutes=config.INVITATION_EXPIRY_MINUTES)
    invitation = Invitation(sender_id=sender.id, receiver_id=receiver.id, status="PENDING", expires_at=expires_at)
    db.add(invitation)
    db.commit()
    db.refresh(invitation)

    email_utils.send_invitation_email(receiver.email, sender.username)

    await state.send_to_user(receiver.id, {
        "type": "invitation_received",
        "invitation_id": invitation.id,
        "from": sender.username,
    })

    task = asyncio.create_task(
        schedule_invitation_expiry(invitation.id, config.INVITATION_EXPIRY_MINUTES * 60)
    )
    state.invitation_expiry_tasks[invitation.id] = task

    return {"status": "invitation_sent", "invitation_id": invitation.id, "expires_in_minutes": config.INVITATION_EXPIRY_MINUTES}


@app.get("/invitations")
def list_invitations(token: str, db: Session = Depends(get_db)):
    me = get_user_by_token(token, db)
    rows = (
        db.query(Invitation)
        .filter(Invitation.receiver_id == me.id, Invitation.status == "PENDING")
        .order_by(Invitation.created_at.asc())
        .all()
    )
    out = []
    for inv in rows:
        sender = db.query(User).filter(User.id == inv.sender_id).first()
        out.append({
            "invitation_id": inv.id,
            "from": sender.username if sender else "unknown",
            "status": inv.status,
        })
    return {"invitations": out}


@app.post("/invitations/respond")
async def respond_invitation(req: schemas.RespondInvitationRequest, db: Session = Depends(get_db)):
    me = get_user_by_token(req.token, db)
    inv = db.query(Invitation).filter(Invitation.id == req.invitation_id).first()
    if not inv or inv.receiver_id != me.id:
        raise HTTPException(status_code=404, detail="Invitation not found")
    if inv.status != "PENDING":
        raise HTTPException(status_code=400, detail=f"Invitation is no longer pending (status: {inv.status})")

    task = state.invitation_expiry_tasks.pop(inv.id, None)
    if task:
        task.cancel()

    if not req.accept:
        inv.status = "REJECTED"
        db.commit()
        sender = db.query(User).filter(User.id == inv.sender_id).first()
        if sender:
            email_utils.send_invitation_rejected_email(sender.email, me.username)
            await state.send_to_user(sender.id, {
                "type": "invitation_rejected",
                "invitation_id": inv.id,
                "by": me.username,
            })
        return {"status": "rejected"}

    # ACCEPT path -- enforce "one active room per user" on the server.
    if me.id in state.active_room_of_user:
        raise HTTPException(
            status_code=409,
            detail="You already have an active private chat. Leave the current room before joining another conversation.",
        )
    sender = db.query(User).filter(User.id == inv.sender_id).first()
    if not sender:
        raise HTTPException(status_code=404, detail="Sender no longer exists")
    if sender.id in state.active_room_of_user:
        inv.status = "EXPIRED"
        db.commit()
        raise HTTPException(status_code=409, detail=f"{sender.username} is already in another active chat")

    inv.status = "ACCEPTED"
    db.commit()

    db_room = Room(user_a_id=sender.id, user_b_id=me.id, status="ACTIVE")
    db.add(db_room)
    db.commit()
    db.refresh(db_room)

    key_manager.generate_room_key(db_room.id)  # never logged, never persisted
    session_key_hex = key_manager.export_key_hex(db_room.id)

    room = RoomState(room_id=db_room.id, user_a=sender.id, user_b=me.id, status="ACTIVE")
    state.rooms[db_room.id] = room
    state.active_room_of_user[sender.id] = db_room.id
    state.active_room_of_user[me.id] = db_room.id

    # The AES-256-GCM session key is delivered once, directly to each
    # authenticated participant's own connection, over the transport-secured
    # (WSS in production) channel. The server does not keep using it to
    # decrypt traffic -- clients encrypt/decrypt at the edges; the server
    # only ever relays ciphertext.
    await state.send_to_user(sender.id, {
        "type": "room_active", "room_id": db_room.id, "peer": me.username, "session_key": session_key_hex,
    })
    await state.send_to_user(me.id, {
        "type": "room_active", "room_id": db_room.id, "peer": sender.username, "session_key": session_key_hex,
    })

    return {"status": "accepted", "room_id": db_room.id, "peer": sender.username}


@app.post("/invitations/cancel")
async def cancel_invitation(req: schemas.CancelInvitationRequest, db: Session = Depends(get_db)):
    me = get_user_by_token(req.token, db)
    inv = db.query(Invitation).filter(Invitation.id == req.invitation_id).first()
    if not inv or inv.sender_id != me.id:
        raise HTTPException(status_code=404, detail="Invitation not found")
    if inv.status != "PENDING":
        raise HTTPException(status_code=400, detail=f"Invitation is no longer pending (status: {inv.status})")

    task = state.invitation_expiry_tasks.pop(inv.id, None)
    if task:
        task.cancel()

    inv.status = "CANCELLED"
    db.commit()

    await state.send_to_user(inv.receiver_id, {"type": "invitation_cancelled", "invitation_id": inv.id})
    return {"status": "cancelled"}


# ---------------------------------------------------------------------------
# WebSocket: notifications + real-time encrypted chat
# ---------------------------------------------------------------------------

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str):
    user_id = state.sessions.get(token)
    if not user_id:
        await websocket.close(code=4401)
        return

    await websocket.accept()
    await state.register_connection(user_id, websocket)

    # Cancel any pending "room termination on disconnect" timer -- this is a reconnect.
    grace_task = state.disconnect_grace_tasks.pop(user_id, None)
    if grace_task:
        grace_task.cancel()
        room = state.user_active_room(user_id)
        if room:
            await state.send_to_user(room.other(user_id), {"type": "peer_reconnected"})
            await state.send_to_user(user_id, {"type": "room_active", "room_id": room.room_id, "peer": "peer"})

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "chat_message":
                await handle_chat_message(user_id, data)
            elif msg_type == "leave_room":
                await handle_leave_room(user_id)
            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})
            else:
                await websocket.send_json({"type": "error", "message": f"Unknown message type: {msg_type}"})

    except WebSocketDisconnect:
        await state.remove_connection(user_id)
        room = state.user_active_room(user_id)
        if room:
            peer = room.other(user_id)
            await state.send_to_user(peer, {
                "type": "peer_disconnected",
                "grace_seconds": config.RECONNECT_GRACE_SECONDS,
            })
            task = asyncio.create_task(
                schedule_disconnect_grace(user_id, room.room_id, config.RECONNECT_GRACE_SECONDS)
            )
            state.disconnect_grace_tasks[user_id] = task


async def handle_chat_message(user_id: str, data: dict):
    room = state.user_active_room(user_id)
    if not room or room.status != "ACTIVE":
        await state.send_to_user(user_id, {"type": "error", "message": "You are not in an active room"})
        return

    nonce = data.get("nonce")
    ciphertext = data.get("ciphertext")
    if not nonce or not ciphertext:
        await state.send_to_user(user_id, {"type": "error", "message": "Malformed encrypted message"})
        return

    # The server never sees plaintext here: the client already encrypted the
    # message locally with the room's AES-256-GCM session key. The server
    # only routes the ciphertext to the peer and never logs message content.
    from .database import SessionLocal
    db = SessionLocal()
    try:
        sender = db.query(User).filter(User.id == user_id).first()
        sender_name = sender.username if sender else user_id
    finally:
        db.close()

    peer = room.other(user_id)
    await state.send_to_user(peer, {
        "type": "chat_message",
        "from": sender_name,
        "nonce": nonce,
        "ciphertext": ciphertext,
    })


async def handle_leave_room(user_id: str):
    room = state.user_active_room(user_id)
    if not room:
        await state.send_to_user(user_id, {"type": "error", "message": "You are not in a room"})
        return
    await terminate_room(room.room_id, "The other participant left the room.")
