import os
import shutil
import subprocess
import sys
import threading
import time

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
        # room_id -> {room_id, peer, session_key (bytes), session_key_hex (str)}
        self.active_rooms: dict[str, dict] = {}
        self.pending_invite_alerts: list[dict] = []
        self._drain_lock = threading.Lock()

    @property
    def active_room(self) -> dict | None:
        """Returns the most recent active room (for backward compatibility)."""
        if self.active_rooms:
            return next(iter(self.active_rooms.values()))
        return None

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
                console.print(f"\n[bold yellow]>> New chat request from @{msg.get('from')}[/bold yellow]")
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
                console.print(f"\n[red]>> @{msg.get('by')} declined your chat request.[/red]")
        elif mtype == "room_active":
            key_hex = msg.get("session_key")
            room_id = msg["room_id"]
            room_info = {
                "room_id": room_id,
                "peer": msg["peer"],
                "session_key": bytes.fromhex(key_hex) if key_hex else None,
                "session_key_hex": key_hex,
            }
            self.active_rooms[room_id] = room_info
            if banner:
                console.print(f"\n[bold green]>> Private room with @{msg['peer']} is now ACTIVE.[/bold green]")
        elif mtype == "room_terminated":
            rid = msg.get("room_id")
            if rid:
                self.active_rooms.pop(rid, None)
            else:
                self.active_rooms.clear()
            if banner:
                console.print(f"\n[bold red]>> Room terminated: {msg.get('reason')}[/bold red]")
        elif mtype == "peer_disconnected":
            if banner:
                console.print(f"\n[yellow]>> Peer disconnected. Grace period: {msg.get('grace_seconds')}s[/yellow]")
        elif mtype == "peer_reconnected":
            if banner:
                console.print("\n[green]>> Peer reconnected.[/green]")
        elif mtype == "chat_message":
            # Chat content is routed to the dedicated chat window.
            pass
        elif mtype == "_connection_closed":
            if banner:
                console.print("\n[red]>> Connection to server lost.[/red]")


session = Session()


def set_terminal_title(title: str):
    """Set terminal window title."""
    if sys.platform == "win32":
        try:
            os.system(f'title {title}')
        except Exception:
            pass
    sys.stdout.write(f"\033]0;{title}\a")
    sys.stdout.flush()


def spawn_chat_window(room_id: str, peer: str, session_key_hex: str):
    """Spawns an independent terminal window for this specific active conversation."""
    python_exe = sys.executable
    script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chat_window.py")
    title = f"Terminal - @{peer}"

    args = [
        python_exe,
        f'"{script_path}"',
        "--token", f'"{session.token}"',
        "--username", f'"{session.username}"',
        "--room-id", f'"{room_id}"',
        "--peer", f'"{peer}"',
        "--session-key", f'"{session_key_hex}"',
        "--ws-url", f'"{SERVER_WS_URL}"',
    ]

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    try:
        if sys.platform == "win32":
            cmd_line = f'start "{title}" {" ".join(args)}'
            subprocess.Popen(cmd_line, shell=True, cwd=project_root)
            console.print(f"[bold green]>> Opened separate conversation window: {title}[/bold green]\n")
            return True
        elif sys.platform == "darwin":
            command = f'cd "{project_root}" && {" ".join(args)}'
            script = f'tell application "Terminal" to do script "{command}"'
            subprocess.Popen(["osascript", "-e", script])
            console.print(f"[bold green]>> Opened separate conversation window: {title}[/bold green]\n")
            return True
        else:
            candidates = ["gnome-terminal", "konsole", "xfce4-terminal", "xterm"]
            for term in candidates:
                if shutil.which(term):
                    subprocess.Popen([term, "--title", title, "-e", " ".join(args)], cwd=project_root)
                    console.print(f"[bold green]>> Opened separate conversation window: {title}[/bold green]\n")
                    return True
    except Exception as e:
        console.print(f"[yellow]Could not spawn external window ({e}). Opening inline...[/yellow]")

    # Fallback to inline chat room if window spawn is unsupported
    chat_room_flow(room_id=room_id)
    return False


def banner(title: str) -> Panel:
    return Panel.fit(f"[bold cyan]{title}[/bold cyan]", border_style="cyan")


def header():
    set_terminal_title("ShadowChat - Secure Terminal")
    console.print(Panel.fit("[bold white on grey15]  S H A D O W C H A T  [/bold white on grey15]", border_style="grey50"))


# ---------------------------------------------------------------------------
# Registration flow
# ---------------------------------------------------------------------------

def do_register():
    console.print(banner("REGISTER NEW ACCOUNT"))
    email = Prompt.ask("Enter your Gmail address")

    try:
        session.api.register_start(email)
    except ApiError as e:
        console.print(f"\n[red]{e.message}[/red]\n")
        return

    console.print(f"\n[green]Verification code sent to {email}.[/green]")
    console.print("[dim]Check your inbox (and spam folder). The code expires in 5 minutes.[/dim]\n")

    vtoken = None
    for _ in range(5):
        otp = Prompt.ask("Enter the 6-digit verification code")
        try:
            res = session.api.register_verify(email, otp.strip())
            vtoken = res["verification_token"]
            console.print("[green]Email verified successfully.[/green]\n")
            break
        except ApiError as e:
            console.print(f"[red]{e.message}[/red]")
            if e.status_code == 429:
                return

    if not vtoken:
        console.print("[red]Verification aborted.[/red]\n")
        return

    while True:
        username = Prompt.ask("Choose a unique Username")
        password = Prompt.ask("Choose a password", password=True)
        confirm = Prompt.ask("Confirm password", password=True)
        if password != confirm:
            console.print("[red]Passwords do not match. Try again.[/red]\n")
            continue
        try:
            session.api.register_complete(vtoken, username, password)
            console.print(f"\n[bold green]Account created successfully for {username}![/bold green]")
            console.print("[dim]You may now log in.[/dim]\n")
            return
        except ApiError as e:
            console.print(f"[red]{e.message}[/red]\n")
            if "token" in e.message.lower():
                return


# ---------------------------------------------------------------------------
# Login flow
# ---------------------------------------------------------------------------

def do_login() -> bool:
    console.print(banner("LOGIN"))
    username = Prompt.ask("Username")
    password = Prompt.ask("Password", password=True)

    try:
        res = session.api.login(username, password)
        session.token = res["token"]
        session.username = res["username"]
    except ApiError as e:
        console.print(f"\n[red]{e.message}[/red]\n")
        return False

    console.print(f"\n[green]Welcome back, {session.username}![/green]")

    session.sock = ShadowChatSocket(SERVER_WS_URL, session.token)
    if not session.sock.start(timeout=5.0):
        console.print("[yellow]Warning: could not establish real-time push connection. Some live features may be limited.[/yellow]")

    return True


# ---------------------------------------------------------------------------
# Main dashboard
# ---------------------------------------------------------------------------

def main_terminal():
    while True:
        set_terminal_title("ShadowChat - Dashboard")
        session.drain_background_events()

        pending_count = len(session.pending_invite_alerts)
        status_lines = (
            f"USER   : {session.username}\n"
            f"STATUS : ONLINE\n"
            f"ALERTS : {pending_count} pending chat request(s)"
        )
        if session.active_rooms:
            peer_names = ", ".join(f"@{r['peer']}" for r in session.active_rooms.values())
            status_lines += f"\n[bold green]ACTIVE CHATS:[/bold green] {peer_names}"

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
            active_chat_menu()
        elif choice == "4":
            help_flow()
        elif choice == "5":
            console.print("\n[dim]Logging out...[/dim]")
            return


def active_chat_menu():
    """Manage and open active chat rooms."""
    session.drain_background_events()
    if not session.active_rooms:
        console.print("\n[dim]You have no active chats. Send or accept an invitation first.[/dim]\n")
        return

    rooms = list(session.active_rooms.values())
    if len(rooms) == 1:
        r = rooms[0]
        spawn_chat_window(r["room_id"], r["peer"], r["session_key_hex"])
        return

    table = Table(title="ACTIVE CONVERSATIONS")
    table.add_column("#")
    table.add_column("Peer")
    table.add_column("Room ID")
    for i, r in enumerate(rooms, start=1):
        table.add_row(str(i), f"@{r['peer']}", r["room_id"][:8] + "...")
    console.print(table)

    choices = [str(i) for i in range(1, len(rooms) + 1)] + ["0"]
    idx = Prompt.ask("Select conversation to open (0 to cancel)", choices=choices, show_choices=False)
    if idx == "0":
        return
    selected = rooms[int(idx) - 1]
    spawn_chat_window(selected["room_id"], selected["peer"], selected["session_key_hex"])


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
        try:
            invite_result = session.api.invite(session.token, query)
            console.print("\n[dim]Creating private chat request...[/dim]")
            console.print(f"[green]Invitation sent to {query}.[/green]\n")
        except ApiError as e:
            console.print(f"\n[red]{e.message}[/red]\n")
            return

        wait_for_invitation(invite_result["invitation_id"], query)


def wait_for_invitation(invitation_id: str, receiver_username: str):
    """Waiting screen for invitation sender. On acceptance, spawns a dedicated chat window."""
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
                room_id = msg["room_id"]
                session_key_hex = msg["session_key"]
                console.print(f"\n[bold green]>> @{receiver_username} accepted! Spawning dedicated chat window...[/bold green]\n")
                spawn_chat_window(room_id, receiver_username, session_key_hex)
                return
            elif mtype == "invitation_rejected" and msg.get("invitation_id") == invitation_id:
                console.print(f"\n[red]>> @{receiver_username} declined your chat request.[/red]\n")
                return
            elif mtype == "invitation_expired_sender" and msg.get("invitation_id") == invitation_id:
                console.print(f"\n[dim]The request to {receiver_username} has expired.[/dim]")
                console.print("[dim]The recipient did not respond.[/dim]\n")
                return
            else:
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
        table.add_row(str(i), f"@{inv['from']}", inv["status"])
    console.print(table)

    choices = [str(i) for i in range(1, len(invites) + 1)] + ["0"]
    idx = Prompt.ask("Select invitation (0 to go back)", choices=choices, show_choices=False)
    if idx == "0":
        return
    inv = invites[int(idx) - 1]

    console.print(f"\nCHAT REQUEST\n\nFrom:\n@{inv['from']}\n")
    decision = Prompt.ask("Do you want to join this private room? [1] YES  [2] NO", choices=["1", "2"], show_choices=False)

    try:
        result = session.api.respond_invitation(session.token, inv["invitation_id"], decision == "1")
    except ApiError as e:
        console.print(f"\n[red]{e.message}[/red]\n")
        return

    if decision == "1":
        peer = result.get('peer')
        room_id = result.get('room_id')
        console.print(f"\n[dim]Joining private room with @{peer}...[/dim]")

        # Wait briefly for session_key to arrive via WebSocket event
        session_key_hex = None
        for _ in range(50):
            session.drain_background_events()
            if room_id in session.active_rooms:
                session_key_hex = session.active_rooms[room_id].get("session_key_hex")
                break
            time.sleep(0.1)

        if session_key_hex:
            spawn_chat_window(room_id, peer, session_key_hex)
        else:
            console.print(
                "[yellow]Room created, but secure session is still being established. "
                "Select [3] Active Chat in a moment.[/yellow]\n"
            )
    else:
        console.print(f"\n[dim]Invitation rejected. @{inv['from']} will be notified.[/dim]\n")


def help_flow():
    console.print(banner("HELP"))
    console.print(
        "[1] Search User        - find another user by User ID\n"
        "[2] Notifications      - view and respond to pending chat requests\n"
        "[3] Active Chat        - open active conversation in a separate window\n"
        "[5] Logout             - end your session\n\n"
        "Inside a chat window, type [bold]/leave[/bold] to end the conversation.\n"
    )


# ---------------------------------------------------------------------------
# Fallback Inline Chat room (for headless environments)
# ---------------------------------------------------------------------------

def chat_room_flow(room_id: str | None = None):
    """Fallback inline chat window with cleaned formatting."""
    room = session.active_rooms.get(room_id) if room_id else session.active_room
    if not room:
        console.print("[dim]No active room found.[/dim]")
        return

    peer = room["peer"]
    set_terminal_title(f"Terminal - @{peer}")
    stop_event = threading.Event()

    def listener():
        while not stop_event.is_set():
            msg = session.sock.get(timeout=0.2)
            if msg is None:
                continue
            mtype = msg.get("type")

            if mtype == "chat_message":
                msg_room_id = msg.get("room_id")
                if msg_room_id and msg_room_id != room["room_id"]:
                    continue

                sender = msg.get("from", peer)
                if sender == session.username:
                    continue

                if room.get("session_key"):
                    try:
                        text = crypto.decrypt(room["session_key"], msg["nonce"], msg["ciphertext"])
                    except Exception:
                        text = "[unable to decrypt message]"

                    # Clear active prompt line before printing incoming message
                    sys.stdout.write("\r\033[K")
                    sys.stdout.flush()
                    print(f"{sender}: {text}")
                    sys.stdout.write("You: ")
                    sys.stdout.flush()

            elif mtype == "peer_disconnected":
                sys.stdout.write("\r\033[K")
                sys.stdout.flush()
                print(f"[!] @{peer} disconnected.")
                sys.stdout.write("You: ")
                sys.stdout.flush()

            elif mtype == "room_terminated":
                sys.stdout.write("\r\033[K")
                sys.stdout.flush()
                print(f"[Room terminated: {msg.get('reason')}]")
                session.active_rooms.pop(room["room_id"], None)
                stop_event.set()
            else:
                session._handle_event(msg, banner=False)

    console.print(Panel.fit(
        f"[bold]PRIVATE CHANNEL[/bold]\n"
        f"YOU : {session.username}\n"
        f"PEER: @{peer}\n"
        f"STATUS: ACTIVE\n\n"
        f"Type a message and press Enter. Type /leave to exit.",
        border_style="magenta",
    ))

    t = threading.Thread(target=listener, daemon=True)
    t.start()

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
                session.sock.send({"type": "leave_room", "room_id": room["room_id"]})
                session.active_rooms.pop(room["room_id"], None)
                console.print("[dim]Leaving room...[/dim]")
                break

            encrypted = crypto.encrypt(room["session_key"], text)
            session.sock.send({
                "type": "chat_message",
                "room_id": room["room_id"],
                "nonce": encrypted["nonce"],
                "ciphertext": encrypted["ciphertext"],
            })
    finally:
        stop_event.set()
        set_terminal_title("ShadowChat - Dashboard")
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
