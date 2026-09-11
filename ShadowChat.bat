@echo off
REM Double-click this to launch the ShadowChat client only.
REM It does NOT start a server -- point .env's SERVER_HTTP_URL / SERVER_WS_URL
REM at whichever server your organization is running.

cd /d "%~dp0"

if exist venv\Scripts\python.exe (
    venv\Scripts\python.exe client\cli.py
) else (
    python client\cli.py
)

pause
