"""
Runs the WebSocket connection on its own asyncio event loop in a background
thread, so the main thread can stay in normal blocking `input()`-driven CLI
menus (via Rich) while still receiving real-time push events (invitations,
chat messages, presence changes) as they arrive.
"""
import asyncio
import json
import queue
import threading

import websockets


class ShadowChatSocket:
    def __init__(self, ws_url: str, token: str):
        self.ws_url = f"{ws_url}?token={token}"
        self.incoming: "queue.Queue[dict]" = queue.Queue()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._ws = None
        self._thread: threading.Thread | None = None
        self._connected = threading.Event()
        self._stop = threading.Event()

    def start(self, timeout: float = 5.0) -> bool:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self._connected.wait(timeout=timeout)

    def _run(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._main())

    async def _main(self):
        try:
            async with websockets.connect(self.ws_url, ping_interval=20, ping_timeout=20) as ws:
                self._ws = ws
                self._connected.set()
                async for raw in ws:
                    try:
                        data = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    self.incoming.put(data)
        except Exception as exc:  # connection closed / failed
            self.incoming.put({"type": "_connection_closed", "error": str(exc)})
        finally:
            self._connected.clear()

    def send(self, message: dict):
        if self._loop is None or self._ws is None:
            return
        asyncio.run_coroutine_threadsafe(self._ws.send(json.dumps(message)), self._loop)

    def get_nowait(self):
        try:
            return self.incoming.get_nowait()
        except queue.Empty:
            return None

    def get(self, timeout: float | None = None):
        try:
            return self.incoming.get(timeout=timeout)
        except queue.Empty:
            return None
