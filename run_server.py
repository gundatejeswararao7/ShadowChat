"""
Run ONLY the ShadowChat server -- this is what you run on the always-on
host/server machine in a real deployment. It never spawns a client; each
user runs the client independently on their own computer (see
client/cli.py or the packaged ShadowChat.bat / .exe), pointed at this
server's address via SERVER_HTTP_URL / SERVER_WS_URL in their own .env.

Usage:
    python run_server.py
    python run_server.py --host 0.0.0.0 --port 8000
"""
import argparse
import os
import sys

from dotenv import load_dotenv

load_dotenv()


def main():
    parser = argparse.ArgumentParser(description="Run the ShadowChat server")
    parser.add_argument("--host", default=os.getenv("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8000")))
    parser.add_argument("--reload", action="store_true", help="Auto-reload on code changes (development only)")
    args = parser.parse_args()

    import uvicorn

    print(f"Starting ShadowChat server on {args.host}:{args.port}")
    if args.host == "0.0.0.0":
        print("NOTE: 0.0.0.0 exposes this server on your network/internet.")
        print("Put it behind TLS (WSS/HTTPS) before accepting real traffic from other machines.\n")

    uvicorn.run("server.main:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    sys.exit(main() or 0)
