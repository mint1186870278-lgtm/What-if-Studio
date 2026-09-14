"""Regression tests for native LangGraph pause/resume session lifecycle."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from src.main import app


def _sse_events(body: str) -> list[dict]:
    events: list[dict] = []
    for frame in body.split("\n\n"):
        if not frame.startswith("data: "):
            continue
        events.append(json.loads(frame[len("data: ") :]))
    return events


def _new_session(client: TestClient) -> tuple[str, str]:
    project = client.post(
        "/api/projects",
        json={"name": "pause-resume-test", "prompt": "测试暂停恢复"},
    )
    assert project.status_code == 201, project.text
    project_id = str(project.json()["id"])
    session = client.post(
        "/api/sessions",
        json={"project_id": project_id, "prompt": "测试暂停恢复"},
    )
    assert session.status_code == 201, session.text
    return project_id, str(session.json()["id"])


def test_native_pause_is_persisted_and_resume_completes(monkeypatch) -> None:
    async def fake_initial(**kwargs):
        yield {"type": "requirements_parsed", "requirements": {}}
        yield {
            "type": "turn",
            "speaker": "NarrativeDirector",
            "role": "director",
            "content": "先确认结局方向",
            "stage": "debate",
            "ts": 1,
        }
        yield {
            "type": "awaiting_input",
            "question": {
                "id": "q_test_direction",
                "question": "选择方向",
                "options": ["保持当前方向", "更忠实原作"],
                "allow_free_text": True,
                "allow_decide": True,
            },
            "question_id": "q_test_direction",
            "session_id": kwargs.get("session_id"),
        }
        yield {
            "type": "paused",
            "session_id": kwargs.get("session_id"),
            "stop_reason": "awaiting_user",
        }

    async def fake_resume(*, session_id: str, user_input):
        yield {
            "type": "answer_applied",
            "question_id": "q_test_direction",
            "answer": user_input,
        }
        yield {
            "type": "turn",
            "speaker": "VisualDirector",
            "role": "director",
            "content": "按用户选择继续",
            "stage": "debate",
            "ts": 2,
        }
        yield {"type": "script", "script": "最终脚本"}
        yield {"type": "task_result", "stop_reason": "critic_finished"}

    monkeypatch.setattr("src.api.sessions._discuss_stream", fake_initial)
    monkeypatch.setattr("src.api.sessions._resume_stream", fake_resume)

    with TestClient(app) as client:
        project_id, session_id = _new_session(client)

        first = client.post(f"/api/sessions/{session_id}/discuss/stream")
        assert first.status_code == 200, first.text
        first_events = _sse_events(first.text)
        assert [event["type"] for event in first_events][-2:] == ["awaiting_input", "paused"]

        session = client.get(f"/api/sessions/{session_id}").json()
        assert session["status"] == "paused"
        project = client.get(f"/api/projects/{project_id}").json()
        assert project["discussion_status"] == "paused"

        resumed = client.post(
            f"/api/sessions/{session_id}/resume",
            json={"selected_option": "更忠实原作"},
        )
        assert resumed.status_code == 200, resumed.text
        resumed_events = _sse_events(resumed.text)
        assert [event["type"] for event in resumed_events] == [
            "answer_applied",
            "turn",
            "script",
            "task_result",
        ]
        assert resumed_events[0]["answer"] == "更忠实原作"

        session = client.get(f"/api/sessions/{session_id}").json()
        assert session["status"] == "completed"
        assert session["script"] == "最终脚本"
        project = client.get(f"/api/projects/{project_id}").json()
        assert project["discussion_status"] == "completed"
        assert project["script"] == "最终脚本"


def test_resume_requires_an_answer(monkeypatch) -> None:
    # The validation happens before graph access, so this test does not need a
    # real checkpoint or a configured model provider.
    monkeypatch.setattr("src.api.sessions._resume_stream", lambda **_: None)
    with TestClient(app) as client:
        _, session_id = _new_session(client)
        response = client.post(f"/api/sessions/{session_id}/resume", json={})
        assert response.status_code == 422
        assert "answer" in response.text.lower()


def test_project_script_stream_pause_and_project_resume(monkeypatch) -> None:
    """The browser's project-level flow has the same resumable contract."""

    async def fake_initial(**kwargs):
        yield {"type": "awaiting_input", "question": {"id": "q_project"}}
        yield {"type": "paused", "session_id": kwargs.get("session_id")}

    async def fake_resume(*, session_id: str, user_input):
        assert user_input == "保持当前方向"
        yield {"type": "answer_applied", "question_id": "q_project", "answer": user_input}
        yield {"type": "script", "script": "项目脚本"}
        yield {"type": "task_result", "stop_reason": "critic_finished"}

    monkeypatch.setattr("src.api.projects._discuss_stream", fake_initial)
    monkeypatch.setattr("src.api.projects._resume_stream", fake_resume)

    with TestClient(app) as client:
        project = client.post(
            "/api/projects",
            json={"name": "project-flow", "prompt": "项目流"},
        )
        assert project.status_code == 201
        project_id = str(project.json()["id"])

        first = client.post(f"/api/projects/{project_id}/script/stream")
        assert first.status_code == 200, first.text
        assert [event["type"] for event in _sse_events(first.text)][-2:] == ["awaiting_input", "paused"]
        assert client.get(f"/api/projects/{project_id}").json()["discussion_status"] == "paused"

        resumed = client.post(
            f"/api/projects/{project_id}/script/resume",
            json={"answer": "保持当前方向"},
        )
        assert resumed.status_code == 200, resumed.text
        assert [event["type"] for event in _sse_events(resumed.text)] == [
            "answer_applied",
            "script",
            "task_result",
        ]
        project_after = client.get(f"/api/projects/{project_id}").json()
        assert project_after["discussion_status"] == "completed"
        assert project_after["script"] == "项目脚本"


def test_resume_choice_is_saved_as_scoped_user_evidence(monkeypatch) -> None:
    async def fake_initial(**kwargs):
        yield {
            "type": "awaiting_input",
            "question": {"id": "q_choice_persist", "question": "选择方向"},
            "question_id": "q_choice_persist",
        }
        yield {"type": "paused", "session_id": kwargs.get("session_id")}

    async def fake_resume(*, session_id: str, user_input):
        yield {"type": "answer_applied", "question_id": "q_choice_persist", "answer": user_input}
        yield {"type": "script", "script": "带用户决定的脚本"}
        yield {"type": "task_result", "stop_reason": "critic_finished"}

    monkeypatch.setattr("src.api.sessions._discuss_stream", fake_initial)
    monkeypatch.setattr("src.api.sessions._resume_stream", fake_resume)
    user_id = "resume-choice-user"
    headers = {"X-User-ID": user_id}
    with TestClient(app) as client:
        project = client.post(
            "/api/projects",
            headers=headers,
            json={"name": "choice-project", "prompt": "选择方向"},
        )
        project_id = project.json()["id"]
        session = client.post(
            "/api/sessions",
            headers=headers,
            json={"project_id": project_id, "prompt": "选择方向"},
        )
        session_id = session.json()["id"]
        first = client.post(f"/api/sessions/{session_id}/discuss/stream", headers=headers)
        assert first.status_code == 200
        resumed = client.post(
            f"/api/sessions/{session_id}/resume",
            headers=headers,
            json={"question_id": "q_choice_persist", "selected_option": "更忠实原作"},
        )
        assert resumed.status_code == 200, resumed.text
        context = client.get(
            f"/api/users/{user_id}/personalization-context",
            headers=headers,
            params={"session_id": session_id, "project_id": project_id},
        )
        assert context.status_code == 200, context.text
        assert context.json()["preferences"]["creative_decision"]["value"] == "更忠实原作"
