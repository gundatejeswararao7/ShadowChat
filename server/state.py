"""
In-memory runtime state for the running server process.

This deliberately keeps volatile, per-session/per-connection state (session
tokens, live WebSocket connections, which room a user is currently in,
pending reconnect-grace timers) OUT of the database. Only durable records
(users, invitations, room existence/status) live in SQLite. This keeps
metadata minimal and ensures ephemeral session data disappears when the
server restarts.
"""
import asyncio
from dataclasses import dataclass, field
from typing import Dict, Optional, Set

from fastapi import WebSocket


@dataclass
class RoomState:
    room_id: str
    user_a: str  # user id
    user_b: str  # user id
    status: str = "ACTIVE"  # ACTIVE, TERMINATING, DELETED

    def other(self, user_id: str) -> str:
        return self.user_b if user_id == self.user_a else self.user_a

    def has_user(self, user_id: str) -> bool:
        return user_id in (self.user_a, self.user_b)


class RuntimeState:
    def __init__(self) -> None:
        # session token -> user_id
        self.sessions: Dict[str, str] = {}
        # email-verification token -> email  (short-lived, post-OTP)
        self.email_verification_tokens: Dict[str, dict] = {}
        # user_id -> WebSocket
        self.connections: Dict[str, WebSocket] = {}
        # user_id -> room_id  (a user may be in at most ONE active room)
        self.active_room_of_user: Dict[str, str] = {}
        # room_id -> RoomState
        self.rooms: Dict[str, RoomState] = {}
        # user_id -> asyncio.Task (pending reconnect-grace termination)
        self.disconnect_grace_tasks: Dict[str, asyncio.Task] = {}
        # invitation_id -> asyncio.Task (pending expiry)
        self.invitation_expiry_tasks: Dict[str, asyncio.Task] = {}
        self.lock = asyncio.Lock()

    # --- presence -----------------------------------------------------
    def is_online(self, user_id: str) -> bool:
        return user_id in self.connections

    async def register_connection(self, user_id: str, ws: WebSocket) -> None:
        async with self.lock:
            self.connections[user_id] = ws

    async def remove_connection(self, user_id: str) -> None:
        async with self.lock:
            self.connections.pop(user_id, None)

    async def send_to_user(self, user_id: str, message: dict) -> bool:
        ws = self.connections.get(user_id)
        if ws is None:
            return False
        try:
            await ws.send_json(message)
            return True
        except Exception:
            return False

    # --- rooms ----------------------------------------------------------
    def user_active_room(self, user_id: str) -> Optional[RoomState]:
        room_id = self.active_room_of_user.get(user_id)
        if room_id is None:
            return None
        return self.rooms.get(room_id)


state = RuntimeState()
