"""
Dedicated Chat Window for ShadowChat.
Runs an isolated, end-to-end encrypted conversation with a specific peer
in its own separate terminal window.
"""
import argparse
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import crypto
from ws_client import ShadowChatSocket


def set_terminal_title(title: str):
    """Set the OS terminal window title."""
    if sys.platform == "win32":
        try:
            os.system(f'title {title}')
        except Exception:
            pass
    # ANSI escape code supported by Windows Terminal, modern cmd, bash, zsh, xterm, macOS
    sys.stdout.write(f"\033]0;{title}\a")
    sys.stdout.flush()


def main():
    parser = argparse.ArgumentParser(description="Dedicated ShadowChat Conversation Window")
    parser.add_argument("--token", required=True, help="Session token")
    parser.add_argument("--username", required=True, help="Current username")
    parser.add_argument("--room-id", required=True, help="Room ID")
    parser.add_argument("--peer", required=True, help="Peer username")
    parser.add_argument("--session-key", required=True, help="Hex-encoded 32-byte AES key")
    parser.add_argument("--ws-url", default=os.getenv("SERVER_WS_URL", "ws://127.0.0.1:8000/ws"))
    args = parser.parse_args()

    # 1. Set window title
    window_title = f"Terminal - @{args.peer}"
    set_terminal_title(window_title)

    session_key = bytes.fromhex(args.session_key)

    # 2. Connect to WebSocket
    sock = ShadowChatSocket(args.ws_url, args.token)
    if not sock.start(timeout=5.0):
        print(f"\n[!] Failed to connect to server at {args.ws_url}")
        input("\nPress Enter to exit...")
        return

    # 3. Print clean conversation header
    print("=" * 60)
    print(f" PRIVATE CONVERSATION: @{args.peer}")
    print(f" Logged in as : You (@{args.username})")
    print(f" Encryption   : AES-256-GCM (End-to-End Encrypted)")
    print(f" Commands     : Type /leave to close this chat window")
    print("=" * 60)
    print("Type a message and press Enter.\n")

    stop_event = threading.Event()

    def incoming_listener():
        while not stop_event.is_set():
            msg = sock.get(timeout=0.2)
            if msg is None:
                continue

            mtype = msg.get("type")

            if mtype == "chat_message":
                # Only handle messages for this specific room or from this peer
                msg_room_id = msg.get("room_id")
                if msg_room_id and msg_room_id != args.room_id:
                    continue

                sender = msg.get("from", args.peer)
                # Ignore messages sent by self
                if sender == args.username:
                    continue

                try:
                    text = crypto.decrypt(session_key, msg["nonce"], msg["ciphertext"])
                except Exception:
                    text = "[unable to decrypt message]"

                # Cleanly clear current prompt line and print incoming message
                sys.stdout.write("\r\033[K")
                sys.stdout.flush()
                print(f"{sender}: {text}")
                sys.stdout.write("You: ")
                sys.stdout.flush()

            elif mtype == "room_terminated":
                if msg.get("room_id") in (None, args.room_id):
                    sys.stdout.write("\r\033[K")
                    sys.stdout.flush()
                    print(f"\n[Room terminated: {msg.get('reason', 'Conversation ended')}]")
                    print("Press Enter to close this window...")
                    stop_event.set()

            elif mtype == "peer_disconnected":
                sys.stdout.write("\r\033[K")
                sys.stdout.flush()
                print(f"\n[!] @{args.peer} disconnected. Waiting for reconnection...")
                sys.stdout.write("You: ")
                sys.stdout.flush()

            elif mtype == "peer_reconnected":
                sys.stdout.write("\r\033[K")
                sys.stdout.flush()
                print(f"\n[✓] @{args.peer} reconnected.")
                sys.stdout.write("You: ")
                sys.stdout.flush()

    listener_thread = threading.Thread(target=incoming_listener, daemon=True)
    listener_thread.start()

    # 4. Message Input Loop
    try:
        while not stop_event.is_set():
            try:
                sys.stdout.write("You: ")
                sys.stdout.flush()
                line = sys.stdin.readline()
                if not line:
                    break
                text = line.rstrip("\r\n")
            except (KeyboardInterrupt, EOFError):
                break

            if stop_event.is_set():
                break

            if not text.strip():
                continue

            if text.strip().lower() == "/leave":
                sock.send({"type": "leave_room", "room_id": args.room_id})
                print(f"\n[You left the conversation with @{args.peer}.]")
                time.sleep(0.5)
                break

            encrypted = crypto.encrypt(session_key, text)
            sock.send({
                "type": "chat_message",
                "room_id": args.room_id,
                "nonce": encrypted["nonce"],
                "ciphertext": encrypted["ciphertext"],
            })

    finally:
        stop_event.set()
        set_terminal_title("Terminal - Closed")
        time.sleep(0.2)


if __name__ == "__main__":
    main()
