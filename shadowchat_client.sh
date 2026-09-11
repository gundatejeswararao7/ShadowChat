#!/usr/bin/env bash
# Launch the ShadowChat client only. Does NOT start a server -- point
# .env's SERVER_HTTP_URL / SERVER_WS_URL at whichever server your
# organization is running.
cd "$(dirname "$0")"

if [ -x "venv/bin/python" ]; then
    venv/bin/python client/cli.py
else
    python3 client/cli.py
fi
