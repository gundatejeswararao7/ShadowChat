@echo off
REM Double-click this to launch the ShadowChat client.
REM Point .env's SERVER_HTTP_URL / SERVER_WS_URL at whichever server is running.

cd /d "%~dp0"

if exist .venv\Scripts\python.exe (
    .venv\Scripts\python.exe client\cli.py
) else if exist venv\Scripts\python.exe (
    venv\Scripts\python.exe client\cli.py
) else (
    python client\cli.py
)

pause
