import asyncio
import os
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from supabase import Client

from . import config, security, email_utils, schemas
from .database import get_db, get_supabase
from .models import (
    gen_id,
    TABLE_USERS,
    TABLE_OTP_RECORDS,
    TABLE_INVITATIONS,
    TABLE_ROOMS,
)
from .state import state, RoomState
from .key_manager import key_manager

app = FastAPI(title="ShadowChat Server")

# CORS — allow browsers from any origin (required for web terminal)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve web terminal static files
WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
if os.path.exists(WEB_DIR):
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


@app.get("/")
def serve_index():
    index_file = os.path.join(WEB_DIR, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"status": "ShadowChat server running"}


@app.get("/chat")
def serve_chat():
    chat_file = os.path.join(WEB_DIR, "chat.html")
    if os.path.exists(chat_file):
        return FileResponse(chat_file)
    return {"status": "Chat window not found"}


@app.get("/health")
def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_user_by_token(token: str, db: Client) -> dict:
    user_id = state.sessions.get(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired session token")
    res = db.table(TABLE_USERS).select("*").eq("id", user_id).execute()
    if not res.data:
        raise HTTPException(status_code=401, detail="User not found")
    return res.data[0]


async def schedule_invitation_expiry(invitation_id: str, delay_seconds: float):
    try:
        await asyncio.sleep(delay_seconds)
    except asyncio.CancelledError:
        return
    db = get_supabase()
    try:
        res = db.table(TABLE_INVITATIONS).select("*").eq("id", invitation_id).execute()
        inv = res.data[0] if res.data else None
        if inv and inv.get("status") == "PENDING":
            db.table(TABLE_INVITATIONS).update({"status": "EXPIRED"}).eq("id", invitation_id).execute()
            await state.send_to_user(inv["sender_id"], {
                "type": "invitation_expired_sender",
                "invitation_id": invitation_id,
            })
            await state.send_to_user(inv["receiver_id"], {
                "type": "invitation_expired",
                "invitation_id": invitation_id,
            })
    except Exception:
        pass
    finally:
        state.invitation_expiry_tasks.pop(invitation_id, None)


async def terminate_room(room_id: str, reason: str):
    room = state.rooms.get(room_id)
    if not room or room.status == "DELETED":
        return
    room.status = "TERMINATING"

    db = get_supabase()
    try:
        db.table(TABLE_ROOMS).update({"status": "DELETED"}).eq("id", room_id).execute()
    except Exception:
        pass

    for uid in (room.user_a, room.user_b):
        state.remove_user_from_room(uid, room_id)
        await state.send_to_user(uid, {"type": "room_terminated", "room_id": room_id, "reason": reason})

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
def register_start(req: schemas.RegisterStartRequest, db: Client = Depends(get_db)):
    res = db.table(TABLE_USERS).select("*").eq("email", req.email).execute()
    existing_user = res.data[0] if res.data else None
    if existing_user and existing_user.get("email_verified"):
        raise HTTPException(status_code=400, detail="Email already registered")

    otp = security.generate_otp()
    otp_hash = security.hash_otp(otp)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=config.OTP_EXPIRY_MINUTES)

    # Invalidate any previous unused OTPs for this email.
    db.table(TABLE_OTP_RECORDS).update({"used": True}).eq("email", req.email).eq("used", False).execute()

    record_id = gen_id()
    db.table(TABLE_OTP_RECORDS).insert({
        "id": record_id,
        "email": req.email,
        "otp_hash": otp_hash,
        "expires_at": expires_at.isoformat(),
        "attempts": 0,
        "used": False,
    }).execute()

    print(f"\n" + "=" * 55)
    print(f"  >>> [SHADOWCHAT OTP] Code for {req.email}: {otp} <<<")
    print(f"=" * 55 + "\n")

    email_delivered = False
    try:
        email_utils.send_otp_email(req.email, otp)
        email_delivered = True
    except Exception as exc:
        print(f"[!] Email dispatch notice: {exc}")

    return {
        "status": "otp_sent",
        "email_delivered": email_delivered,
        "expires_in_minutes": config.OTP_EXPIRY_MINUTES,
    }


@app.post("/register/verify")
def register_verify(req: schemas.RegisterVerifyRequest, db: Client = Depends(get_db)):
    res = (
        db.table(TABLE_OTP_RECORDS)
        .select("*")
        .eq("email", req.email)
        .eq("used", False)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    record = res.data[0] if res.data else None
    if not record:
        raise HTTPException(status_code=400, detail="No pending verification for this email")

    exp_str = record["expires_at"].replace("Z", "+00:00")
    expires_at = datetime.fromisoformat(exp_str)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if datetime.now(timezone.utc) > expires_at:
        raise HTTPException(status_code=400, detail="OTP expired. Please request a new one")

    attempts = record.get("attempts", 0)
    if attempts >= config.OTP_MAX_ATTEMPTS:
        raise HTTPException(status_code=429, detail="Too many attempts. Please request a new OTP")

    new_attempts = attempts + 1

    if not security.verify_otp_hash(req.otp, record["otp_hash"]):
        db.table(TABLE_OTP_RECORDS).update({"attempts": new_attempts}).eq("id", record["id"]).execute()
        raise HTTPException(status_code=400, detail="Incorrect OTP")

    db.table(TABLE_OTP_RECORDS).update({"attempts": new_attempts, "used": True}).eq("id", record["id"]).execute()

    token = security.generate_token()
    state.email_verification_tokens[token] = {
        "email": req.email,
        "expires_at": datetime.utcnow() + timedelta(minutes=config.EMAIL_VERIFICATION_TOKEN_TTL_MINUTES),
    }
    return {"status": "verified", "verification_token": token}


@app.post("/register/complete")
def register_complete(req: schemas.RegisterCompleteRequest, db: Client = Depends(get_db)):
    entry = state.email_verification_tokens.get(req.verification_token)
    if not entry or datetime.utcnow() > entry["expires_at"]:
        raise HTTPException(status_code=400, detail="Verification token invalid or expired")

    email = entry["email"]

    user_check = db.table(TABLE_USERS).select("id").eq("username", req.username).execute()
    if user_check.data:
        raise HTTPException(status_code=400, detail="Username already taken")

    email_check = db.table(TABLE_USERS).select("id").eq("email", email).execute()
    if email_check.data:
        raise HTTPException(status_code=400, detail="Email already registered")

    user_id = gen_id()
    db.table(TABLE_USERS).insert({
        "id": user_id,
        "username": req.username,
        "email": email,
        "password_hash": security.hash_password(req.password),
        "email_verified": True,
    }).execute()

    state.email_verification_tokens.pop(req.verification_token, None)

    return {"status": "account_created", "user_id": user_id, "username": req.username}


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

@app.post("/login")
def login(req: schemas.LoginRequest, db: Client = Depends(get_db)):
    res = db.table(TABLE_USERS).select("*").eq("username", req.username).execute()
    user = res.data[0] if res.data else None
    if not user or not security.verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    if not user.get("email_verified"):
        raise HTTPException(status_code=403, detail="Email not verified")

    token = security.generate_token()
    state.sessions[token] = user["id"]
    return {"status": "access_granted", "token": token, "username": user["username"]}


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

@app.get("/search")
def search_user(query: str, token: str, db: Client = Depends(get_db)):
    me = get_user_by_token(token, db)
    res = db.table(TABLE_USERS).select("*").eq("username", query).execute()
    found = res.data[0] if res.data else None
    if not found or found["id"] == me["id"]:
        raise HTTPException(status_code=404, detail=f'No user with ID "{query}"')
    return {
        "user_id": found["username"],
        "status": "ONLINE" if state.is_online(found["id"]) else "OFFLINE",
    }


# ---------------------------------------------------------------------------
# Invitations
# ---------------------------------------------------------------------------

@app.post("/invite")
async def send_invitation(req: schemas.InviteRequest, db: Client = Depends(get_db)):
    sender = get_user_by_token(req.token, db)
    res = db.table(TABLE_USERS).select("*").eq("username", req.receiver_username).execute()
    receiver = res.data[0] if res.data else None
    if not receiver:
        raise HTTPException(status_code=404, detail=f'No user with ID "{req.receiver_username}"')
    if receiver["id"] == sender["id"]:
        raise HTTPException(status_code=400, detail="You cannot invite yourself")

    existing_res = (
        db.table(TABLE_INVITATIONS)
        .select("*")
        .eq("sender_id", sender["id"])
        .eq("receiver_id", receiver["id"])
        .eq("status", "PENDING")
        .execute()
    )
    if existing_res.data:
        raise HTTPException(status_code=400, detail="An invitation to this user is already pending")

    expires_at = datetime.now(timezone.utc) + timedelta(minutes=config.INVITATION_EXPIRY_MINUTES)
    invitation_id = gen_id()
    db.table(TABLE_INVITATIONS).insert({
        "id": invitation_id,
        "sender_id": sender["id"],
        "receiver_id": receiver["id"],
        "status": "PENDING",
        "expires_at": expires_at.isoformat(),
    }).execute()

    email_utils.send_invitation_email(receiver["email"], sender["username"])

    await state.send_to_user(receiver["id"], {
        "type": "invitation_received",
        "invitation_id": invitation_id,
        "from": sender["username"],
    })

    task = asyncio.create_task(
        schedule_invitation_expiry(invitation_id, config.INVITATION_EXPIRY_MINUTES * 60)
    )
    state.invitation_expiry_tasks[invitation_id] = task

    return {"status": "invitation_sent", "invitation_id": invitation_id, "expires_in_minutes": config.INVITATION_EXPIRY_MINUTES}


@app.get("/invitations")
def list_invitations(token: str, db: Client = Depends(get_db)):
    me = get_user_by_token(token, db)
    res = (
        db.table(TABLE_INVITATIONS)
        .select("*")
        .eq("receiver_id", me["id"])
        .eq("status", "PENDING")
        .order("created_at", desc=False)
        .execute()
    )
    rows = res.data or []
    out = []
    for inv in rows:
        sender_res = db.table(TABLE_USERS).select("username").eq("id", inv["sender_id"]).execute()
        sender_name = sender_res.data[0]["username"] if sender_res.data else "unknown"
        out.append({
            "invitation_id": inv["id"],
            "from": sender_name,
            "status": inv["status"],
        })
    return {"invitations": out}


@app.post("/invitations/respond")
async def respond_invitation(req: schemas.RespondInvitationRequest, db: Client = Depends(get_db)):
    me = get_user_by_token(req.token, db)
    inv_res = db.table(TABLE_INVITATIONS).select("*").eq("id", req.invitation_id).execute()
    inv = inv_res.data[0] if inv_res.data else None
    if not inv or inv["receiver_id"] != me["id"]:
        raise HTTPException(status_code=404, detail="Invitation not found")
    if inv["status"] != "PENDING":
        raise HTTPException(status_code=400, detail=f"Invitation is no longer pending (status: {inv['status']})")

    task = state.invitation_expiry_tasks.pop(inv["id"], None)
    if task:
        task.cancel()

    if not req.accept:
        db.table(TABLE_INVITATIONS).update({"status": "REJECTED"}).eq("id", inv["id"]).execute()
        sender_res = db.table(TABLE_USERS).select("*").eq("id", inv["sender_id"]).execute()
        sender = sender_res.data[0] if sender_res.data else None
        if sender:
            email_utils.send_invitation_rejected_email(sender["email"], me["username"])
            await state.send_to_user(sender["id"], {
                "type": "invitation_rejected",
                "invitation_id": inv["id"],
                "by": me["username"],
            })
        return {"status": "rejected"}

    sender_res = db.table(TABLE_USERS).select("*").eq("id", inv["sender_id"]).execute()
    sender = sender_res.data[0] if sender_res.data else None
    if not sender:
        raise HTTPException(status_code=404, detail="Sender no longer exists")

    # Check if active room already exists between sender and me
    existing_room = None
    for r_id in state.get_user_rooms(me["id"]):
        r = state.rooms.get(r_id)
        if r and r.status == "ACTIVE" and r.has_user(sender["id"]):
            existing_room = r
            break

    if existing_room:
        session_key_hex = key_manager.export_key_hex(existing_room.room_id)
        return {"status": "accepted", "room_id": existing_room.room_id, "peer": sender["username"]}

    db.table(TABLE_INVITATIONS).update({"status": "ACCEPTED"}).eq("id", inv["id"]).execute()

    room_id = gen_id()
    db.table(TABLE_ROOMS).insert({
        "id": room_id,
        "user_a_id": sender["id"],
        "user_b_id": me["id"],
        "status": "ACTIVE",
    }).execute()

    key_manager.generate_room_key(room_id)  # never logged, never persisted
    session_key_hex = key_manager.export_key_hex(room_id)

    room = RoomState(room_id=room_id, user_a=sender["id"], user_b=me["id"], status="ACTIVE")
    state.rooms[room_id] = room
    state.add_user_to_room(sender["id"], room_id)
    state.add_user_to_room(me["id"], room_id)

    # Deliver room active event with session key
    await state.send_to_user(sender["id"], {
        "type": "room_active", "room_id": room_id, "peer": me["username"], "session_key": session_key_hex,
    })
    await state.send_to_user(me["id"], {
        "type": "room_active", "room_id": room_id, "peer": sender["username"], "session_key": session_key_hex,
    })

    return {"status": "accepted", "room_id": room_id, "peer": sender["username"]}


@app.post("/invitations/cancel")
async def cancel_invitation(req: schemas.CancelInvitationRequest, db: Client = Depends(get_db)):
    me = get_user_by_token(req.token, db)
    inv_res = db.table(TABLE_INVITATIONS).select("*").eq("id", req.invitation_id).execute()
    inv = inv_res.data[0] if inv_res.data else None
    if not inv or inv["sender_id"] != me["id"]:
        raise HTTPException(status_code=404, detail="Invitation not found")
    if inv["status"] != "PENDING":
        raise HTTPException(status_code=400, detail=f"Invitation is no longer pending (status: {inv['status']})")

    task = state.invitation_expiry_tasks.pop(inv["id"], None)
    if task:
        task.cancel()

    db.table(TABLE_INVITATIONS).update({"status": "CANCELLED"}).eq("id", inv["id"]).execute()

    await state.send_to_user(inv["receiver_id"], {"type": "invitation_cancelled", "invitation_id": inv["id"]})
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

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "chat_message":
                await handle_chat_message(user_id, data)
            elif msg_type == "leave_room":
                await handle_leave_room(user_id, data)
            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})
            else:
                await websocket.send_json({"type": "error", "message": f"Unknown message type: {msg_type}"})

    except WebSocketDisconnect:
        await state.remove_connection(user_id, websocket)


async def handle_chat_message(user_id: str, data: dict):
    room_id = data.get("room_id")
    if room_id:
        room = state.rooms.get(room_id)
    else:
        room = state.user_active_room(user_id)

    if not room or not room.has_user(user_id) or room.status != "ACTIVE":
        await state.send_to_user(user_id, {"type": "error", "message": "You are not in an active room"})
        return

    nonce = data.get("nonce")
    ciphertext = data.get("ciphertext")
    if not nonce or not ciphertext:
        await state.send_to_user(user_id, {"type": "error", "message": "Malformed encrypted message"})
        return

    # The server never sees plaintext here: client encrypts with AES-256-GCM.
    db = get_supabase()
    try:
        res = db.table(TABLE_USERS).select("username").eq("id", user_id).execute()
        sender_name = res.data[0]["username"] if res.data else user_id
    except Exception:
        sender_name = user_id

    peer = room.other(user_id)
    await state.send_to_user(peer, {
        "type": "chat_message",
        "room_id": room.room_id,
        "from": sender_name,
        "nonce": nonce,
        "ciphertext": ciphertext,
    })


async def handle_leave_room(user_id: str, data: dict):
    room_id = data.get("room_id")
    if room_id:
        room = state.rooms.get(room_id)
    else:
        room = state.user_active_room(user_id)

    if not room or not room.has_user(user_id):
        await state.send_to_user(user_id, {"type": "error", "message": "You are not in that room"})
        return
    await terminate_room(room.room_id, "The other participant left the room.")
