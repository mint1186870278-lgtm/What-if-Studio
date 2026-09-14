from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

from fastapi.testclient import TestClient

from src.config import settings
from src.main import app


def _jwt(subject: str, secret: str) -> str:
    def enc(value: dict) -> str:
        raw = json.dumps(value, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    header = enc({"alg": "HS256", "typ": "JWT"})
    payload = enc({"sub": subject, "exp": int(time.time()) + 300})
    body = f"{header}.{payload}"
    signature = hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest()
    return f"{body}.{base64.urlsafe_b64encode(signature).decode().rstrip('=')}"


def test_production_jwt_binds_project_owner(monkeypatch) -> None:
    old_debug = settings.debug
    old_secret = settings.auth_secret
    old_allow_header = settings.auth_allow_unverified_user_header
    secret = "test-auth-secret"
    monkeypatch.setattr(settings, "debug", False)
    monkeypatch.setattr(settings, "auth_secret", secret)
    monkeypatch.setattr(settings, "auth_allow_unverified_user_header", False)

    try:
        with TestClient(app) as client:
            alice = {"Authorization": f"Bearer {_jwt('alice', secret)}"}
            bob = {"Authorization": f"Bearer {_jwt('bob', secret)}"}
            created = client.post(
                "/api/projects",
                headers=alice,
                json={"name": "owned-project", "prompt": "修改结局"},
            )
            assert created.status_code == 201, created.text
            project_id = created.json()["id"]

            assert client.get(f"/api/projects/{project_id}", headers=alice).status_code == 200
            assert client.get(f"/api/projects/{project_id}", headers=bob).status_code == 403
            assert client.get(f"/api/projects/{project_id}").status_code == 401
            assert client.get("/api/gateway/invocations").status_code == 401
            listed = client.get("/api/projects", headers=alice)
            assert listed.status_code == 200
            assert any(item["id"] == project_id for item in listed.json())
            bob_projects = client.get("/api/projects", headers=bob).json()
            assert all(item["id"] != project_id for item in bob_projects)
    finally:
        settings.debug = old_debug
        settings.auth_secret = old_secret
        settings.auth_allow_unverified_user_header = old_allow_header


def test_feedback_session_scope_checks_owner(monkeypatch) -> None:
    old_debug = settings.debug
    monkeypatch.setattr(settings, "debug", True)
    try:
        with TestClient(app) as client:
            alice = {"X-User-ID": "feedback-alice"}
            bob = {"X-User-ID": "feedback-bob"}
            project = client.post(
                "/api/projects",
                headers=alice,
                json={"name": "feedback-owner", "prompt": "反馈"},
            ).json()
            session = client.post(
                "/api/sessions",
                headers=alice,
                json={"project_id": project["id"], "prompt": "反馈"},
            ).json()
            response = client.post(
                "/api/feedback",
                headers=bob,
                json={"session_id": session["id"], "rating": 1},
            )
            assert response.status_code == 403
    finally:
        settings.debug = old_debug
