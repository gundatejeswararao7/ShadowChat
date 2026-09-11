"""
ShadowChat launcher.

Starts the FastAPI/WebSocket server in this terminal, waits until it's
actually ready, then automatically OPENS A NEW COMMAND WINDOW running the
CLI client -- so the user never has to manually type `python client/cli.py`
themselves.

Usage:
    python run.py

Works on Windows (new `cmd` window), macOS (new Terminal.app window/tab),
and Linux (tries common terminal emulators: gnome-terminal, konsole,
xfce4-terminal, xterm, x-terminal-emulator). If no graphical terminal is
available (e.g. a headless server/container), it falls back to running the
client directly in this same window so the app still works everywhere.
"""
import os
import platform
import shutil
import subprocess
import sys
import time
import urllib.request

from dotenv import load_dotenv

load_dotenv()

HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))
HEALTH_URL = f"http://{HOST}:{PORT}/health"

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
CLIENT_PATH = os.path.join(PROJECT_ROOT, "client", "cli.py")


def wait_for_server(url: str, timeout: float = 20.0, proc: subprocess.Popen | None = None):
    """Poll `url` until it responds, or return early if `proc` (the server
    subprocess) exits on its own -- e.g. because it failed to bind the port.
    Returns True (ready), False (timed out), or the proc's exit code (int)
    if it died before becoming ready."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc is not None:
            code = proc.poll()
            if code is not None:
                return code
        try:
            with urllib.request.urlopen(url, timeout=1.0) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


def is_server_already_running(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=1.0) as resp:
            return resp.status == 200
    except Exception:
        return False


def shlex_quote(s: str) -> str:
    import shlex
    return shlex.quote(s)


def open_client_in_new_window() -> bool:
    """Try to open a brand-new terminal/command window running the client.
    Returns True if a new window was successfully launched."""
    python_exe = sys.executable
    system = platform.system()

    try:
        if system == "Windows":
            # Opens a new, separate cmd.exe window.
            subprocess.Popen(
                f'start "ShadowChat Client" "{python_exe}" "{CLIENT_PATH}"',
                cwd=PROJECT_ROOT,
                shell=True,
            )
            return True

        if system == "Darwin":
            # Opens a new Terminal.app window.
            command = f'cd {shlex_quote(PROJECT_ROOT)} && {shlex_quote(python_exe)} {shlex_quote(CLIENT_PATH)}'
            script = f'tell application "Terminal" to do script "{command}"'
            subprocess.Popen(["osascript", "-e", script])
            return True

        # Linux / other Unix-likes: try common terminal emulators in order.
        candidates = [
            ["gnome-terminal", "--"],
            ["konsole", "-e"],
            ["xfce4-terminal", "-e"],
            ["mate-terminal", "-e"],
            ["lxterminal", "-e"],
            ["xterm", "-e"],
            ["x-terminal-emulator", "-e"],
        ]
        for prefix in candidates:
            emulator = prefix[0]
            if shutil.which(emulator):
                subprocess.Popen(prefix + [python_exe, CLIENT_PATH], cwd=PROJECT_ROOT)
                return True

        return False
    except Exception:
        return False


def main() -> int:
    server_proc = None

    if is_server_already_running(HEALTH_URL):
        print(f"A ShadowChat server is already running at http://{HOST}:{PORT} -- reusing it.\n")
    else:
        print("Starting ShadowChat server...")
        server_proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "server.main:app", "--host", HOST, "--port", str(PORT)],
            cwd=PROJECT_ROOT,
        )

    try:
        if server_proc is not None:
            outcome = wait_for_server(HEALTH_URL, proc=server_proc)
            if outcome is not True:
                if isinstance(outcome, int):
                    print(
                        f"\nThe server process exited (code {outcome}) before it finished starting -- "
                        f"it most likely failed to bind to {HOST}:{PORT}, commonly because a previous "
                        "run is still using that port.\n"
                    )
                else:
                    print("Server did not become ready in time. Check the server logs above.")

                if platform.system() == "Windows":
                    print(
                        "To find and stop whatever is using the port on Windows:\n"
                        f'  netstat -ano | findstr :{PORT}\n'
                        "  taskkill /PID <the PID from the last column> /F\n"
                    )
                else:
                    print(
                        "To find and stop whatever is using the port on macOS/Linux:\n"
                        f'  lsof -i :{PORT}\n'
                        "  kill -9 <the PID>\n"
                    )
                try:
                    server_proc.terminate()
                    server_proc.wait(timeout=5)
                except Exception:
                    pass
                return 1

        print(f"Server is up at http://{HOST}:{PORT}\n")

        opened = open_client_in_new_window()
        if opened:
            print("Client launched in a new window.")
            if server_proc is not None:
                print("This window will keep the server running -- close it (or Ctrl+C) to shut everything down.\n")
                server_proc.wait()
            else:
                print("(The server was already running independently, so this window will now exit.)\n")
        else:
            print("Could not open a new terminal window automatically "
                  "(no graphical terminal found on this system).")
            print("Launching the client here instead:\n")
            client_proc = subprocess.run([sys.executable, CLIENT_PATH], cwd=PROJECT_ROOT)
            return client_proc.returncode

        return 0
    except KeyboardInterrupt:
        return 0
    finally:
        if server_proc is not None:
            print("\nShutting down ShadowChat server...")
            server_proc.terminate()
            try:
                server_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server_proc.kill()


if __name__ == "__main__":
    sys.exit(main())
