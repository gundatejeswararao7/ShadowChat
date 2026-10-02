"""
In-memory runtime state for the running server process.

This deliberately keeps volatile, per-session/per-connection state (session
tokens, live WebSocket connections, active rooms, pending reconnect-grace timers)
OUT of the database. Only durable records (users, invitations, room records)
live in Supabase.
"""
import asyncio
from dataclasses import dataclass, field
from typing import Dict, Optional, Set, List

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
        # user_id -> Set[WebSocket] (allows dashboard + multiple chat windows)
        self.connections: Dict[str, Set[WebSocket]] = {}
        # user_id -> Set[room_id] (allows chatting with multiple people in separate windows)
        self.user_rooms: Dict[str, Set[str]] = {}
        # room_id -> RoomState
        self.rooms: Dict[str, RoomState] = {}
        # user_id -> asyncio.Task (pending reconnect-grace termination)
        self.disconnect_grace_tasks: Dict[str, asyncio.Task] = {}
        # invitation_id -> asyncio.Task (pending expiry)
        self.invitation_expiry_tasks: Dict[str, asyncio.Task] = {}
        self.lock = asyncio.Lock()

    # --- presence -----------------------------------------------------
    def is_online(self, user_id: str) -> bool:
        conns = self.connections.get(user_id)
        return bool(conns and len(conns) > 0)

    async def register_connection(self, user_id: str, ws: WebSocket) -> None:
        async with self.lock:
            if user_id not in self.connections:
                self.connections[user_id] = set()
            self.connections[user_id].add(ws)

    async def remove_connection(self, user_id: str, ws: WebSocket) -> None:
        async with self.lock:
            if user_id in self.connections:
                self.connections[user_id].discard(ws)
                if not self.connections[user_id]:
                    self.connections.pop(user_id, None)

    async def send_to_user(self, user_id: str, message: dict) -> bool:
        ws_set = self.connections.get(user_id)
        if not ws_set:
            return False
        sent = False
        for ws in list(ws_set):
            try:
                await ws.send_json(message)
                sent = True
            except Exception:
                pass
        return sent

    # --- rooms ----------------------------------------------------------
    def add_user_to_room(self, user_id: str, room_id: str):
        if user_id not in self.user_rooms:
            self.user_rooms[user_id] = set()
        self.user_rooms[user_id].add(room_id)

    def remove_user_from_room(self, user_id: str, room_id: str):
        if user_id in self.user_rooms:
            self.user_rooms[user_id].discard(room_id)
            if not self.user_rooms[user_id]:
                self.user_rooms.pop(user_id, None)

    def get_user_rooms(self, user_id: str) -> Set[str]:
        return self.user_rooms.get(user_id, set())

    def user_active_room(self, user_id: str) -> Optional[RoomState]:
        room_ids = self.user_rooms.get(user_id, set())
        for rid in room_ids:
            room = self.rooms.get(rid)
            if room and room.status == "ACTIVE":
                return room
        return None


state = RuntimeState()
