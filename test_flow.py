import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from unittest.mock import patch

captured_emails = []


def fake_send_email(to_email, subject, body):
    captured_emails.append({"to": to_email, "subject": subject, "body": body})


with patch("server.email_utils.send_email", side_effect=fake_send_email):
    from fastapi.testclient import TestClient
    from server.main import app
    import client.crypto as crypto

    client = TestClient(app)
    client.__enter__()  # trigger startup event (creates DB tables)

    def get_last_otp(email):
        for e in reversed(captured_emails):
            if e["to"] == email and "verification code" in e["subject"]:
                m = re.search(r"\n\n(\d{6})\n\n", e["body"])
                return m.group(1)
        raise AssertionError("OTP email not found")

    def register(email, username, password):
        r = client.post("/register/start", json={"email": email})
        assert r.status_code == 200, r.text
        otp = get_last_otp(email)
        r = client.post("/register/verify", json={"email": email, "otp": otp})
        assert r.status_code == 200, r.text
        vtoken = r.json()["verification_token"]
        r = client.post("/register/complete", json={
            "verification_token": vtoken, "username": username, "password": password,
        })
        assert r.status_code == 200, r.text
        print(f"[OK] registered {username}")

    register("alice@example.com", "agent_101", "Passw0rd!")
    register("bob@example.com", "agent_204", "Passw0rd!")

    # Wrong OTP / expired handled implicitly by verify() raising -- quick negative check:
    r = client.post("/register/start", json={"email": "carol@example.com"})
    assert r.status_code == 200
    r = client.post("/register/verify", json={"email": "carol@example.com", "otp": "000000"})
    assert r.status_code == 400
    print("[OK] wrong OTP rejected")

    r = client.post("/login", json={"username": "agent_101", "password": "Passw0rd!"})
    assert r.status_code == 200, r.text
    token_a = r.json()["token"]
    print("[OK] alice logged in")

    r = client.post("/login", json={"username": "agent_204", "password": "Passw0rd!"})
    assert r.status_code == 200, r.text
    token_b = r.json()["token"]
    print("[OK] bob logged in")

    r = client.post("/login", json={"username": "agent_204", "password": "WRONG"})
    assert r.status_code == 401
    print("[OK] wrong password rejected")

    r = client.get("/search", params={"query": "agent_204", "token": token_a})
    assert r.status_code == 200 and r.json()["user_id"] == "agent_204"
    print("[OK] search works")

    r = client.get("/search", params={"query": "nobody", "token": token_a})
    assert r.status_code == 404
    print("[OK] search 404 for missing user")

    with client.websocket_connect(f"/ws?token={token_a}") as ws_a, \
         client.websocket_connect(f"/ws?token={token_b}") as ws_b:

        r = client.post("/invite", json={"token": token_a, "receiver_username": "agent_204"})
        assert r.status_code == 200, r.text
        invitation_id = r.json()["invitation_id"]
        print("[OK] invitation sent")

        evt = ws_b.receive_json()
        assert evt["type"] == "invitation_received" and evt["from"] == "agent_101"
        print("[OK] bob received invitation over websocket")

        r = client.get("/invitations", params={"token": token_b})
        assert len(r.json()["invitations"]) == 1
        print("[OK] bob sees pending invitation via REST")

        r = client.post("/invitations/respond", json={"token": token_b, "invitation_id": invitation_id, "accept": True})
        assert r.status_code == 200, r.text
        room_id = r.json()["room_id"]
        print("[OK] bob accepted invitation, room created:", room_id)

        evt_a = ws_a.receive_json()
        evt_b = ws_b.receive_json()
        assert evt_a["type"] == "room_active" and evt_a["session_key"]
        assert evt_b["type"] == "room_active" and evt_b["session_key"]
        assert evt_a["session_key"] == evt_b["session_key"]
        print("[OK] both sides received matching AES-256-GCM session key")

        session_key = bytes.fromhex(evt_a["session_key"])
        assert len(session_key) == 32
        print("[OK] session key is 256 bits")

        enc = crypto.encrypt(session_key, "Hello Bob, this is Alice.")
        ws_a.send_json({"type": "chat_message", "nonce": enc["nonce"], "ciphertext": enc["ciphertext"]})

        msg = ws_b.receive_json()
        assert msg["type"] == "chat_message" and msg["from"] == "agent_101"
        plaintext = crypto.decrypt(session_key, msg["nonce"], msg["ciphertext"])
        assert plaintext == "Hello Bob, this is Alice."
        print("[OK] encrypted message delivered and decrypted correctly:", plaintext)

        # Third-party / duplicate-invite guard: sending another invite from alice
        # while she's already in an active room is still allowed at the "send"
        # step (only accept enforces one-active-room), so just verify it's queued
        # and drain the resulting notification off bob's socket before continuing.
        r = client.post("/invite", json={"token": token_a, "receiver_username": "agent_204"})
        assert r.status_code == 200
        dup_evt = ws_b.receive_json()
        assert dup_evt["type"] == "invitation_received"
        print("[OK] duplicate invite queued and delivered as expected")

        # Bob leaves the room
        ws_b.send_json({"type": "leave_room"})
        term_b = ws_b.receive_json()
        term_a = ws_a.receive_json()
        assert term_a["type"] == "room_terminated"
        assert term_b["type"] == "room_terminated"
        print("[OK] room terminated cleanly on manual leave, both sides notified")

    # ---- one-active-room-per-user enforcement (a fresh pair of users) ----
    register("dave@example.com", "agent_305", "Passw0rd!")
    register("erin@example.com", "agent_552", "Passw0rd!")
    register("frank@example.com", "agent_777", "Passw0rd!")

    r = client.post("/login", json={"username": "agent_305", "password": "Passw0rd!"})
    token_d = r.json()["token"]
    r = client.post("/login", json={"username": "agent_552", "password": "Passw0rd!"})
    token_e = r.json()["token"]
    r = client.post("/login", json={"username": "agent_777", "password": "Passw0rd!"})
    token_f = r.json()["token"]

    with client.websocket_connect(f"/ws?token={token_d}") as ws_d, \
         client.websocket_connect(f"/ws?token={token_e}") as ws_e, \
         client.websocket_connect(f"/ws?token={token_f}") as ws_f:

        r = client.post("/invite", json={"token": token_d, "receiver_username": "agent_552"})
        inv1 = r.json()["invitation_id"]
        ws_e.receive_json()  # invitation_received
        r = client.post("/invitations/respond", json={"token": token_e, "invitation_id": inv1, "accept": True})
        assert r.status_code == 200
        ws_d.receive_json()  # room_active
        ws_e.receive_json()  # room_active
        print("[OK] dave <-> erin room active")

        # frank invites erin, who is already in an active room with dave
        r = client.post("/invite", json={"token": token_f, "receiver_username": "agent_552"})
        inv2 = r.json()["invitation_id"]
        ws_e.receive_json()  # invitation_received

        r = client.post("/invitations/respond", json={"token": token_e, "invitation_id": inv2, "accept": True})
        assert r.status_code == 409, r.text
        assert "already have an active" in r.json()["detail"]
        print("[OK] server correctly refused a second active room for the same user:", r.json()["detail"])

    print("\nALL CHECKS PASSED")
