"""
KeyManager: ephemeral AES-256-GCM session keys for temporary chat rooms.

Design notes
------------
- Each room gets its own randomly generated 256-bit key.
- Keys live ONLY in server memory (never written to the database, never
  logged, never printed). When a room terminates, `destroy_room_key` drops
  the key from memory so old messages can no longer be decrypted.
- AES-GCM is an AEAD cipher: it provides confidentiality, integrity and
  authentication in one primitive (unlike raw/unauthenticated AES).
- A fresh random 96-bit nonce is generated for every single message and is
  never reused with the same key.
- This module intentionally isolates all crypto operations behind a small
  interface so it can later be swapped for a full end-to-end key exchange
  (e.g. X3DH + Double Ratchet) without touching the rest of the app.

Important: AES-256-GCM protects *message content*. It does not, by itself,
make network traffic anonymous or untraceable — transport security (TLS/WSS)
and message encryption are separate, complementary layers.
"""
import os
from typing import Dict

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class KeyManager:
    def __init__(self) -> None:
        self._keys: Dict[str, bytes] = {}

    def generate_room_key(self, room_id: str) -> None:
        self._keys[room_id] = AESGCM.generate_key(bit_length=256)

    def has_key(self, room_id: str) -> bool:
        return room_id in self._keys

    def export_key_hex(self, room_id: str) -> str:
        """Return the room key as hex, to be delivered once to each
        authenticated participant over their own connection. Never logged."""
        key = self._keys.get(room_id)
        if key is None:
            raise ValueError("No active encryption key for this room")
        return key.hex()

    def encrypt_message(self, room_id: str, plaintext: str) -> dict:
        key = self._keys.get(room_id)
        if key is None:
            raise ValueError("No active encryption key for this room")
        aesgcm = AESGCM(key)
        nonce = os.urandom(12)  # unique per message, never reused with this key
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
        return {"nonce": nonce.hex(), "ciphertext": ciphertext.hex()}

    def decrypt_message(self, room_id: str, nonce_hex: str, ciphertext_hex: str) -> str:
        key = self._keys.get(room_id)
        if key is None:
            raise ValueError("No active encryption key for this room")
        aesgcm = AESGCM(key)
        nonce = bytes.fromhex(nonce_hex)
        ciphertext = bytes.fromhex(ciphertext_hex)
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext.decode("utf-8")

    def destroy_room_key(self, room_id: str) -> None:
        self._keys.pop(room_id, None)


# Single shared instance used by the running server process.
key_manager = KeyManager()
