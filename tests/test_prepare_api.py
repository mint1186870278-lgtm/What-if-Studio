from __future__ import annotations


def test_prepare_stream_persists_script(client, create_project, monkeypatch) -> None:
    async def fake_discussion_stream(user_request: str, style: str = "auto", performance_notes=None):
        _ = (user_request, style, performance_notes)
        yield {"type": "turn", "speaker": "导演", "content": "参与讨论", "stage": "briefing"}
        yield {"type": "script", "script": "# 测试剧本"}

    monkeypatch.setattr("src.api.projects.run_autogen_discussion_stream", fake_discussion_stream)
    project_id = create_project()

    response = client.post(f"/{project_id}/prepare")
    assert response.status_code == 200
    assert "data:" in response.text
    assert "测试剧本" in client.get(f"/projects/{project_id}").json()["script"]
