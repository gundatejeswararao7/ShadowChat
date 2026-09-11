import os
import sys
import time
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from dotenv import load_dotenv

load_dotenv()

from api import Api, ApiError  # noqa: E402
from ws_client import ShadowChatSocket  # noqa: E402
import crypto  # noqa: E402

console = Console()
app = typer.Typer(add_completion=False)

SERVER_WS_URL = os.getenv("SERVER_WS_URL", "ws://127.0.0.1:8000/ws")


class Session:
    def __init__(self):
        self.api = Api()
        self.token: str | None = None
        self.username: str | None = None
        self.sock: ShadowChatSocket | None = None
        self.active_room: dict | None = None  # {room_id, peer, session_key(bytes)}
        self.pending_invite_alerts: list[dict] = []
        self._drain_lock = threading.Lock()

    # ---- background draining of non-chat events (invitations, room state) ----
    def drain_background_events(self):
        """Pop any queued websocket events and update session state /
        print lightweight alerts. Called opportunistically from menus."""
        if not self.sock:
            return
        with self._drain_lock:
            while True:
                msg = self.sock.get_nowait()
                if msg is None:
                    break
                self._handle_event(msg, banner=True)

    def _handle_event(self, msg: dict, banner: bool):
        mtype = msg.get("type")
        if mtype == "invitation_received":
            self.pending_invite_alerts.append(msg)
            if banner:
                console.print(f"\n[bold yellow]>> New chat request from {msg.get('from')}[/bold yellow]")
        elif mtype == "invitation_cancelled":
            if banner:
                console.print("\n[dim]>> A chat request was cancelled by the sender.[/dim]")
        elif mtype == "invitation_expired":
            if banner:
                console.print("\n[dim]>> A pending chat request expired.[/dim]")
        elif mtype == "invitation_expired_sender":
            if banner:
                console.print("\n[dim]>> Your chat request expired. The recipient did not respond.[/dim]")
        elif mtype == "invitation_rejected":
            if banner:
                console.print(f"\n[red]>> {msg.get('by')} declined your chat request.[/red]")
        elif mtype == "room_active":
            key_hex = msg.get("session_key")
            self.active_room = {
                "room_id": msg["room_id"],
                "peer": msg["peer"],
                "session_key": bytes.fromhex(key_hex) if key_hex else None,
            }
            if banner:
                console.print(f"\n[bold green]>> Private room with {msg['peer']} is now ACTIVE.[/bold green]")
        elif mtype == "room_terminated":
            if banner:
                console.print(f"\n[bold red]>> Room terminated: {msg.get('reason')}[/bold red]")
            self.active_room = None
        elif mtype == "peer_disconnected":
            if banner:
                console.print(f"\n[yellow]>> Peer disconnected. Grace period: {msg.get('grace_seconds')}s[/yellow]")
        elif mtype == "peer_reconnected":
            if banner:
                console.print("\n[green]>> Peer reconnected.[/green]")
        elif mtype == "chat_message":
            # Chat content must NEVER surface outside the dedicated private
            # chat window (not on the main dashboard, not as a banner). If a
            # message somehow arrives while the user isn't inside the chat
            # window, it is silently dropped here rather than printed.
            pass
        elif mtype == "_connection_closed":
            if banner:
                console.print("\n[red]>> Connection to server lost.[/red]")


session = Session()


def banner(title: str) -> Panel:
    return Panel.fit(f"[bold cyan]{title}[/bold cyan]", border_style="cyan")


def header():
    console.print(Panel.fit("[bold white on grey15]  S H A D O W C H A T  [/bold white on grey15]", border_style="grey50"))


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def do_register():
    console.print(banner("CREATE ACCOUNT"))
    email = Prompt.ask("Email")
    try:
        session.api.register_start(email)
    except ApiError as e:
        console.print(f"[red]{e.message}[/red]")
        return

    console.print("\n[dim]A verification code has been sent to your email.[/dim]")
    console.print("[dim]The code will NOT be shown here -- check your inbox.[/dim]\n")

    for _ in range(5):
        otp = Prompt.ask("Enter OTP")
        try:
            result = session.api.register_verify(email, otp)
            break
        except ApiError as e:
            console.print(f"[red]{e.message}[/red]")
    else:
        console.print("[red]Too many failed attempts.[/red]")
        return

    console.print("\n[bold green]Email verified successfully.[/bold green]\n")

    verification_token = result["verification_token"]

    while True:
        username = Prompt.ask("Create your ShadowChat User ID")
        password = Prompt.ask("Create password", password=True)
        confirm = Prompt.ask("Confirm password", password=True)
        if password != confirm:
            console.print("[red]Passwords do not match. Try again.[/red]")
            continue
        try:
            session.api.register_complete(verification_token, username, password)
            console.print(f"\n[bold green]Account '{username}' created. You can now log in.[/bold green]\n")
            return
        except ApiError as e:
            console.print(f"[red]{e.message}[/red]")


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

def do_login() -> bool:
    console.print(banner("LOGIN"))
    username = Prompt.ask("User ID")
    password = Prompt.ask("Password", password=True)
    try:
        result = session.api.login(username, password)
    except ApiError as e:
        console.print(f"[red]{e.message}[/red]")
        return False

    session.token = result["token"]
    session.username = result["username"]

    console.print("\n[dim]Authenticating...[/dim]")
    console.print("[bold green]ACCESS GRANTED[/bold green]")
    console.print(f"\nWelcome, [bold]{session.username}[/bold]\n")

    session.sock = ShadowChatSocket(SERVER_WS_URL, session.token)
    if not session.sock.start(timeout=5.0):
        console.print("[yellow]Warning: could not establish real-time connection. Some features may be limited.[/yellow]")
    return True


# ---------------------------------------------------------------------------
# Main terminal
# ---------------------------------------------------------------------------

def main_terminal():
    while True:
        session.drain_background_events()

        try:
            invites = session.api.list_invitations(session.token)["invitations"]
        except ApiError:
            invites = []

        status_lines = (
            f"[bold]USER:[/bold] {session.username}\n"
            f"[bold]STATUS:[/bold] ONLINE\n"
            f"[bold]NOTIFICATIONS:[/bold] {len(invites)}"
        )
        if session.active_room:
            status_lines += f"\n[bold]ACTIVE CHAT:[/bold] {session.active_room['peer']}"
        console.print(Panel(status_lines, title="SHADOWCHAT", border_style="cyan"))

        console.print("[1] Search User")
        console.print("[2] Notifications")
        console.print("[3] Active Chat")
        console.print("[4] Help")
        console.print("[5] Logout")

        choice = Prompt.ask("\nSelect", choices=["1", "2", "3", "4", "5"], show_choices=False)

        if choice == "1":
            search_user_flow()
        elif choice == "2":
            notifications_flow()
        elif choice == "3":
            if session.active_room:
                chat_room_flow()
            else:
                console.print("[dim]You have no active chat. Accept an invitation first.[/dim]")
        elif choice == "4":
            help_flow()
        elif choice == "5":
            console.print("\n[dim]Logging out...[/dim]")
            return


def search_user_flow():
    console.print(banner("SEARCH USER"))
    query = Prompt.ask("Enter User ID")
    try:
        result = session.api.search(query, session.token)
    except ApiError as e:
        console.print(f"\n[red]USER NOT FOUND[/red]\n{e.message}\n")
        return

    console.print(f"\n[bold green]USER FOUND[/bold green]")
    console.print(f"User ID : {result['user_id']}")
    console.print(f"Status  : {result['status']}\n")

    if Prompt.ask("Request private chat? [1] YES  [2] NO", choices=["1", "2"], show_choices=False) == "1":
        if session.active_room:
            console.print("\n[red]ACCESS DENIED -- you already have an active private chat.[/red]")
            return
        try:
            invite_result = session.api.invite(session.token, query)
            console.print("\n[dim]Creating private chat request...[/dim]")
            console.print(f"[green]Invitation sent to {query}.[/green]\n")
        except ApiError as e:
            console.print(f"\n[red]{e.message}[/red]\n")
            return

        wait_for_invitation(invite_result["invitation_id"], query)


def wait_for_invitation(invitation_id: str, receiver_username: str):
    """Dedicated waiting screen for the invitation sender. Blocks the main
    dashboard (the sender does NOT keep browsing/chatting elsewhere while
    waiting) until the recipient responds, the request expires, or the
    sender cancels it (Ctrl+C). On acceptance, transitions straight into
    the private chat window."""
    console.print(Panel.fit(
        "PRIVATE CHAT REQUEST\n\n"
        f"To: {receiver_username}\n\n"
        "Status: WAITING\n\n"
        "Waiting for recipient...\n"
        "[dim](Press Ctrl+C to cancel this request)[/dim]",
        border_style="yellow",
    ))

    try:
        while True:
            msg = session.sock.get(timeout=1.0) if session.sock else None
            if msg is None:
                continue
            mtype = msg.get("type")

            if mtype == "room_active" and msg.get("peer") == receiver_username:
                session._handle_event(msg, banner=False)
                console.print(f"\n[bold green]{receiver_username} accepted. Entering private room...[/bold green]\n")
                chat_room_flow()
                return
            elif mtype == "invitation_rejected" and msg.get("invitation_id") == invitation_id:
                console.print(f"\n[red]{receiver_username} declined your chat request.[/red]\n")
                return
            elif mtype == "invitation_expired_sender" and msg.get("invitation_id") == invitation_id:
                console.print(f"\n[dim]The request to {receiver_username} has expired.[/dim]")
                console.print("[dim]The recipient did not respond.[/dim]\n")
                return
            else:
                # Anything unrelated to this pending invitation is recorded
                # silently and surfaced later on the main dashboard.
                session._handle_event(msg, banner=False)
    except KeyboardInterrupt:
        console.print()
        confirm = Prompt.ask("Cancel request? [1] YES  [2] NO", choices=["1", "2"], show_choices=False)
        if confirm == "1":
            console.print("\n[dim]Cancelling request...[/dim]")
            try:
                session.api.cancel_invitation(session.token, invitation_id)
                console.print("[green]Request cancelled.[/green]")
                console.print("[dim]Temporary invitation removed.[/dim]\n")
            except ApiError as e:
                console.print(f"[red]{e.message}[/red]")
            return
        else:
            wait_for_invitation(invitation_id, receiver_username)


def notifications_flow():
    session.drain_background_events()
    try:
        invites = session.api.list_invitations(session.token)["invitations"]
    except ApiError as e:
        console.print(f"[red]{e.message}[/red]")
        return

    if not invites:
        console.print("\n[dim]No pending chat requests.[/dim]\n")
        return

    table = Table(title="PENDING CHAT REQUESTS")
    table.add_column("#")
    table.add_column("From")
    table.add_column("Status")
    for i, inv in enumerate(invites, start=1):
        table.add_row(str(i), inv["from"], inv["status"])
    console.print(table)

    choices = [str(i) for i in range(1, len(invites) + 1)] + ["0"]
    idx = Prompt.ask("Select invitation (0 to go back)", choices=choices, show_choices=False)
    if idx == "0":
        return
    inv = invites[int(idx) - 1]

    console.print(f"\nCHAT REQUEST\n\nFrom:\n{inv['from']}\n")
    decision = Prompt.ask("Do you want to join this private room? [1] YES  [2] NO", choices=["1", "2"], show_choices=False)

    try:
        result = session.api.respond_invitation(session.token, inv["invitation_id"], decision == "1")
    except ApiError as e:
        console.print(f"\n[red]{e.message}[/red]\n")
        return

    if decision == "1":
        console.print("\n[dim]Creating private room...[/dim]")
        console.print(f"Participants:\n{session.username}\n{result.get('peer')}\n")
        console.print("[bold green]ROOM STATUS: ACTIVE[/bold green]\n")
        # The AES-256-GCM session key arrives over the websocket asynchronously
        # (very shortly after this REST response); wait briefly for it.
        for _ in range(50):
            session.drain_background_events()
            if session.active_room and session.active_room.get("room_id") == result.get("room_id"):
                break
            time.sleep(0.1)

        if session.active_room and session.active_room.get("room_id") == result.get("room_id"):
            console.print("[dim]Entering private room...[/dim]\n")
            chat_room_flow()
        else:
            console.print(
                "[yellow]Room created, but the secure session is still being established. "
                "Select [3] Active Chat from the menu in a moment.[/yellow]\n"
            )
    else:
        console.print(f"\n[dim]Invitation rejected. {inv['from']} will be notified.[/dim]\n")


def help_flow():
    console.print(banner("HELP"))
    console.print(
        "[1] Search User        - find another agent by User ID\n"
        "[2] Notifications      - view and respond to pending chat requests\n"
        "[3] Active Chat        - enter your current private room (if any)\n"
        "[5] Logout             - end your session\n\n"
        "Inside a chat room, type [bold]/leave[/bold] to end the conversation.\n"
    )


# ---------------------------------------------------------------------------
# Chat room
# ---------------------------------------------------------------------------

def chat_room_flow():
    """Dedicated, isolated private chat window.

    Everything printed in here (message history, incoming messages, system
    notices) is local to this function call and is never written to any
    shared/dashboard state. When this function returns, nothing from the
    conversation is retained or replayed anywhere else.
    """
    room = session.active_room
    if not room:
        return

    stop_event = threading.Event()

    def listener():
        while not stop_event.is_set():
            msg = session.sock.get(timeout=0.2)
            if msg is None:
                continue
            mtype = msg.get("type")

            if mtype == "chat_message":
                # Received message: displayed exactly once, as
                # "sender_username: message" -- never prefixed with our own
                # username, and never re-printed anywhere else.
                if room.get("session_key"):
                    try:
                        text = crypto.decrypt(room["session_key"], msg["nonce"], msg["ciphertext"])
                    except Exception:
                        text = "[unable to decrypt message]"
                    console.print(f"{msg.get('from')}: {text}")
            elif mtype == "peer_disconnected":
                console.print(f"[yellow]{room['peer']} disconnected. Waiting for reconnection ({msg.get('grace_seconds')}s)...[/yellow]")
            elif mtype == "peer_reconnected":
                console.print(f"[green]{room['peer']} reconnected.[/green]")
            elif mtype == "room_terminated":
                console.print(f"[bold red]Room terminated: {msg.get('reason')}[/bold red]")
                session.active_room = None
                stop_event.set()
            else:
                # Anything unrelated to this room (e.g. a new invitation from
                # a third user) must never appear inside this isolated
                # private chat window. Record it silently for later.
                session._handle_event(msg, banner=False)

    console.print(Panel.fit(
        f"[bold]PRIVATE CHANNEL[/bold]\n"
        f"YOU : {session.username}\n"
        f"PEER: {room['peer']}\n"
        f"STATUS: ACTIVE\n"
        f"PARTICIPANTS: 2\n\n"
        f"Type a message and press Enter. Type /leave to exit.",
        border_style="magenta",
    ))

    t = threading.Thread(target=listener, daemon=True)
    t.start()

    try:
        while session.active_room and not stop_event.is_set():
            try:
                # The prompt IS the sender prefix: whatever the user types is
                # echoed by the terminal right after it, so the finished line
                # reads exactly "username: message" with a single prefix --
                # no separate/duplicate local echo is printed.
                text = input(f"{session.username}: ")
            except EOFError:
                break

            if not session.active_room:
                break

            if text.strip() == "/leave":
                confirm = Prompt.ask("Leave private room? [1] YES  [2] NO", choices=["1", "2"], show_choices=False)
                if confirm == "1":
                    console.print("[dim]Leaving room...[/dim]")
                    session.sock.send({"type": "leave_room"})
                    session.active_room = None
                    console.print("[bold]Private room terminated.[/bold]")
                    console.print("[dim]Temporary room data cleanup initiated.[/dim]")
                    break
                continue

            if not text.strip():
                continue

            if not room.get("session_key"):
                console.print("[red]No session key available yet -- please wait.[/red]")
                continue

            encrypted = crypto.encrypt(room["session_key"], text)
            session.sock.send({"type": "chat_message", "nonce": encrypted["nonce"], "ciphertext": encrypted["ciphertext"]})
    finally:
        stop_event.set()
        console.print("\n[dim]Returning to main dashboard...[/dim]\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

@app.command()
def main():
    """Launch the ShadowChat secure terminal."""
    header()
    while session.token is None:
        console.print("\n[1] Register")
        console.print("[2] Login")
        console.print("[3] Exit")
        choice = Prompt.ask("\nSelect", choices=["1", "2", "3"], show_choices=False)
        if choice == "1":
            do_register()
        elif choice == "2":
            if do_login():
                break
        elif choice == "3":
            console.print("\n[dim]Goodbye.[/dim]")
            raise typer.Exit()

    main_terminal()
    console.print("\n[dim]Session ended.[/dim]")


if __name__ == "__main__":
    app()
