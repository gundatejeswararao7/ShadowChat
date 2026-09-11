"""
Client-side AES-256-GCM message encryption.

The room's session key is received once from the server (over the
transport-secured connection) when a room becomes ACTIVE, and is held only
in memory for the lifetime of the chat -- never written to disk, never
printed. Every message uses a fresh random 96-bit nonce.
"""
import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def encrypt(session_key: bytes, plaintext: str) -> dict:
    aesgcm = AESGCM(session_key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return {"nonce": nonce.hex(), "ciphertext": ciphertext.hex()}


def decrypt(session_key: bytes, nonce_hex: str, ciphertext_hex: str) -> str:
    aesgcm = AESGCM(session_key)
    nonce = bytes.fromhex(nonce_hex)
    ciphertext = bytes.fromhex(ciphertext_hex)
    return aesgcm.decrypt(nonce, ciphertext, None).decode("utf-8")
