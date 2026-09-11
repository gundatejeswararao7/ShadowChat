import os
import httpx

SERVER_HTTP_URL = os.getenv("SERVER_HTTP_URL", "http://127.0.0.1:8000")


class ApiError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _unwrap(resp: httpx.Response) -> dict:
    try:
        data = resp.json()
    except Exception:
        data = {}
    if resp.status_code >= 400:
        raise ApiError(data.get("detail", f"Request failed ({resp.status_code})"), resp.status_code)
    return data


class Api:
    def __init__(self, base_url: str = SERVER_HTTP_URL):
        self.base_url = base_url
        self._client = httpx.Client(base_url=base_url, timeout=15.0)

    def register_start(self, email: str) -> dict:
        return _unwrap(self._client.post("/register/start", json={"email": email}))

    def register_verify(self, email: str, otp: str) -> dict:
        return _unwrap(self._client.post("/register/verify", json={"email": email, "otp": otp}))

    def register_complete(self, verification_token: str, username: str, password: str) -> dict:
        return _unwrap(self._client.post("/register/complete", json={
            "verification_token": verification_token,
            "username": username,
            "password": password,
        }))

    def login(self, username: str, password: str) -> dict:
        return _unwrap(self._client.post("/login", json={"username": username, "password": password}))

    def search(self, query: str, token: str) -> dict:
        return _unwrap(self._client.get("/search", params={"query": query, "token": token}))

    def invite(self, token: str, receiver_username: str) -> dict:
        return _unwrap(self._client.post("/invite", json={"token": token, "receiver_username": receiver_username}))

    def list_invitations(self, token: str) -> dict:
        return _unwrap(self._client.get("/invitations", params={"token": token}))

    def respond_invitation(self, token: str, invitation_id: str, accept: bool) -> dict:
        return _unwrap(self._client.post("/invitations/respond", json={
            "token": token, "invitation_id": invitation_id, "accept": accept,
        }))

    def cancel_invitation(self, token: str, invitation_id: str) -> dict:
        return _unwrap(self._client.post("/invitations/cancel", json={
            "token": token, "invitation_id": invitation_id,
        }))
