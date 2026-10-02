"""
Run ONLY the ShadowChat server -- this is what you run on the always-on
host/server machine in a real deployment or locally during development.

Usage:
    python run_server.py
    python run_server.py --host 0.0.0.0 --port 8000
"""
import argparse
import os
import socket
import sys

from dotenv import load_dotenv

load_dotenv()


def check_port_in_use(host: str, port: int) -> bool:
    """Check if the target port is already bound."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        # 0.0.0.0 cannot be connected to directly in client mode on Windows, check 127.0.0.1
        check_host = "127.0.0.1" if host in ("0.0.0.0", "") else host
        return s.connect_ex((check_host, port)) == 0


def print_preflight_checks(host: str, port: int):
    """Verify environment variables and dependencies before booting uvicorn."""
    print("=" * 60)
    print(" ShadowChat Server - Pre-flight Health & Environment Check")
    print("=" * 60)

    # 1. Check .env file
    env_exists = os.path.exists(".env")
    if env_exists:
        print("[✓] Environment: .env file detected.")
    else:
        print("[!] Warning: .env file NOT found. Run 'copy .env.example .env' and fill your credentials.")

    # 2. Check Supabase credentials
    from server import config
    if config.SUPABASE_URL and config.SUPABASE_KEY:
        print(f"[✓] Database: Supabase configured ({config.SUPABASE_URL[:30]}...)")
    else:
        print("[!] Warning: SUPABASE_URL or SUPABASE_KEY missing in .env.")
        print("    Refer to supabase/README.md to set up your Supabase project.")

    # 3. Check SMTP credentials
    if config.SMTP_USERNAME and config.SMTP_APP_PASSWORD:
        print(f"[✓] Email/OTP: Gmail SMTP configured ({config.SMTP_USERNAME})")
    else:
        print("[!] Warning: SMTP_USERNAME or SMTP_APP_PASSWORD missing in .env.")
        print("    Registration OTP emails will fail until Google App Password is set.")

    # 4. Check Port binding
    if check_port_in_use(host, port):
        print(f"[x] Error: Port {port} on {host} is already in use by another process!")
        print(f"    Please stop the existing process or run with --port <different_port>.")
    else:
        print(f"[✓] Network: Port {port} is free and ready.")

    print("=" * 60)
    print(f"Starting ShadowChat server on http://{host}:{port}")
    if host == "0.0.0.0":
        print("NOTE: 0.0.0.0 exposes this server on your network/internet.")
        print("Put it behind TLS (WSS/HTTPS) before accepting real traffic from other machines.")
    print("=" * 60 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Run the ShadowChat server")
    parser.add_argument("--host", default=os.getenv("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8000")))
    parser.add_argument("--reload", action="store_true", help="Auto-reload on code changes (development only)")
    args = parser.parse_args()

    print_preflight_checks(args.host, args.port)

    import uvicorn
    uvicorn.run("server.main:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    sys.exit(main() or 0)
