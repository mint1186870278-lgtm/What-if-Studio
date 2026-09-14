"""Feedback persistence contract: SQL first, semantic memory best effort."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.main import app


def test_feedback_survives_mem0_failure(monkeypatch) -> None:
    async def fail_mem0(*args, **kwargs):
        raise RuntimeError("Mem0 unavailable")

    monkeypatch.setattr("src.api.feedback.memory_service.record_feedback", fail_mem0)
    with TestClient(app) as client:
        response = client.post(
            "/api/feedback",
            json={
                "user_id": "feedback-user",
                "project_id": "feedback-project",
                "rating": 5,
                "liked_aspects": ["动作表达告别"],
            },
        )
        assert response.status_code == 200, response.text
        assert "preferences updated" in response.json()["message"]

        context = client.get(
            "/api/users/feedback-user/personalization-context",
            params={"project_id": "feedback-project"},
        )
        assert context.status_code == 200, context.text
        values = context.json()["preferences"]
        assert values["likes"]["value"] == "动作表达告别"


def test_feedback_sql_error_returns_failure(monkeypatch) -> None:
    def fail_sql(*args, **kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr("src.api.feedback.personalization_service.apply_observations", fail_sql)
    with TestClient(app) as client:
        response = client.post(
            "/api/feedback",
            json={"user_id": "feedback-sql-failure", "rating": 3},
        )
        assert response.status_code == 500
