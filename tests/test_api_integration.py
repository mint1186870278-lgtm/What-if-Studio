from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from src.main import app


def _create_project(client: TestClient, name: str = "itest-project") -> str:
    resp = client.post(
        "/api/projects",
        json={
            "name": name,
            "description": "integration test project",
            "prompt": "让主角逆转结局",
            "style_preference": "auto",
        },
    )
    assert resp.status_code == 201, resp.text
    return str(resp.json()["id"])


def test_health_endpoints() -> None:
    with TestClient(app) as client:
        r1 = client.get("/health")
        r2 = client.get("/api/health")
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json()["service"] == "whatif-studio"
        assert r2.json()["service"] == "whatif-studio"


def test_agents_endpoint() -> None:
    with TestClient(app) as client:
        resp = client.get("/api/agents")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert isinstance(data.get("agents"), list)
        assert len(data["agents"]) > 0


def test_projects_crud_and_project_extensions(monkeypatch) -> None:
    async def fake_discussion_stream(user_request: str, style: str = "auto", performance_notes=None):
        _ = (user_request, style, performance_notes)
        yield {"type": "turn", "speaker": "NarrativeDirector", "content": "我愿意参与。", "stage": "briefing"}
        yield {"type": "script", "script": "# 剧本\n\n这是测试剧本。"}

    monkeypatch.setattr("src.api.projects.run_autogen_discussion_stream", fake_discussion_stream)

    with TestClient(app) as client:
        project_id = _create_project(client, "itest-project-crud")

        get_resp = client.get(f"/api/projects/{project_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == project_id

        list_resp = client.get("/api/projects")
        assert list_resp.status_code == 200
        assert any(item["id"] == project_id for item in list_resp.json())

        upd_resp = client.put(
            f"/api/projects/{project_id}",
            json={
                "name": "itest-project-updated",
                "prompt": "更新后的需求",
                "style_preference": "warmHealing",
            },
        )
        assert upd_resp.status_code == 200
        assert upd_resp.json()["name"] == "itest-project-updated"

        stream_resp = client.post(f"/api/projects/{project_id}/script/stream")
        assert stream_resp.status_code == 200
        body = stream_resp.text
        assert "data:" in body
        assert "script" in body

        create_job_without_script = client.post(
            f"/api/projects/{_create_project(client, 'itest-no-script')}/video-jobs"
        )
        assert create_job_without_script.status_code == 409

        create_job_resp = client.post(f"/api/projects/{project_id}/video-jobs")
        assert create_job_resp.status_code == 200
        assert create_job_resp.json()["job"]["jobId"]

        del_resp = client.delete(f"/api/projects/{project_id}")
        assert del_resp.status_code == 204


def test_assets_endpoints(tmp_path: Path) -> None:
    with TestClient(app) as client:
        project_id = _create_project(client, "itest-project-assets")

        file_content = b"fake video bytes"
        upload_resp = client.post(
            f"/api/projects/{project_id}/assets",
            files={"file": ("sample.mp4", file_content, "video/mp4")},
            data={"asset_type": "video"},
        )
        assert upload_resp.status_code == 201, upload_resp.text
        asset = upload_resp.json()
        asset_id = str(asset["id"])

        list_resp = client.get(f"/api/projects/{project_id}/assets")
        assert list_resp.status_code == 200
        assert any(item["id"] == asset_id for item in list_resp.json())

        get_resp = client.get(f"/api/assets/{asset_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == asset_id

        download_resp = client.get(f"/api/assets/{asset_id}/download")
        assert download_resp.status_code == 200
        assert download_resp.content == file_content

        del_resp = client.delete(f"/api/assets/{asset_id}")
        assert del_resp.status_code == 204


def test_project_script_stream_persists_script(monkeypatch) -> None:
    async def fake_discussion_stream(user_request: str, style: str = "auto", performance_notes=None):
        _ = (user_request, style, performance_notes)
        yield {
            "type": "turn",
            "speaker": "VisualDirector",
            "role": "director",
            "content": "先确定节奏。",
            "stage": "topic-1",
            "ts": 1,
        }
        yield {
            "type": "script",
            "script": "# 脚本\n\n测试",
            "final": {"final_script": "# 脚本\n\n测试"},
        }

    monkeypatch.setattr("src.api.projects.run_autogen_discussion_stream", fake_discussion_stream)

    with TestClient(app) as client:
        project_id = _create_project(client, "itest-project-script-stream")
        stream_resp = client.post(f"/api/projects/{project_id}/script/stream")
        assert stream_resp.status_code == 200
        assert "data:" in stream_resp.text

        get_resp = client.get(f"/api/projects/{project_id}")
        assert get_resp.status_code == 200
        assert "测试" in (get_resp.json().get("script") or "")


def test_video_jobs_endpoints(monkeypatch, tmp_path: Path) -> None:
    async def fake_process_video_job_background(job_id: str, session_id: str, asset_ids: list[str], db):
        _ = (session_id, asset_ids)
        from src.models import VideoJob

        job = db.query(VideoJob).filter(VideoJob.id == job_id).first()
        assert job is not None
        out = tmp_path / f"{job_id}.mp4"
        out.write_bytes(b"mp4-data")
        job.phase = "deliver"
        job.status = "done"
        job.output_path = str(out)
        db.commit()

    monkeypatch.setattr("src.api.jobs.process_video_job_background", fake_process_video_job_background)
    async def fake_discussion_stream(user_request: str, style: str = "auto", performance_notes=None):
        _ = (user_request, style, performance_notes)
        yield {"type": "turn", "speaker": "NarrativeDirector", "content": "测试讨论", "stage": "briefing"}
        yield {"type": "script", "script": "# 脚本\n\n用于视频任务测试。"}

    monkeypatch.setattr("src.api.projects.run_autogen_discussion_stream", fake_discussion_stream)

    with TestClient(app) as client:
        project_id = _create_project(client, "itest-project-jobs")
        script_resp = client.post(f"/api/projects/{project_id}/script/stream")
        assert script_resp.status_code == 200

        create_resp = client.post(f"/api/projects/{project_id}/video-jobs")
        assert create_resp.status_code == 200, create_resp.text
        job_id = str(create_resp.json()["job"]["id"])

        get_resp = client.get(f"/api/video-jobs/{job_id}")
        assert get_resp.status_code == 200
        assert str(get_resp.json()["id"]) == job_id

        events_resp = client.get(f"/api/video-jobs/{job_id}/events")
        assert events_resp.status_code == 200
        assert "complete" in events_resp.text or "progress" in events_resp.text

        output_resp = client.get(f"/api/video-jobs/{job_id}/output")
        assert output_resp.status_code == 200
        assert output_resp.content == b"mp4-data"


def test_gateway_endpoints(monkeypatch) -> None:
    async def fake_call_service(service_name: str, payload: dict):
        return {"service": service_name, "status": "ok", "payload": payload}

    monkeypatch.setattr("src.api.gateway.anet_call_service", fake_call_service)

    with TestClient(app) as client:
        services_resp = client.get("/api/gateway/services")
        assert services_resp.status_code == 200
        assert any(s["name"] == "autogen-discussion" for s in services_resp.json()["services"])

        alias_resp = client.get("/api/anet/services")
        assert alias_resp.status_code == 200

        invoke_resp = client.post(
            "/api/gateway/invoke",
            json={"service": "autogen-discussion", "payload": {"prompt": "hello"}},
        )
        assert invoke_resp.status_code == 200
        invocation_id = invoke_resp.json()["invocation_id"]
        assert invocation_id

        invoke_alias_resp = client.post(
            "/api/anet/invoke",
            json={"service": "autogen-edit", "payload": {"prompt": "edit"}},
        )
        assert invoke_alias_resp.status_code == 200

        list_inv_resp = client.get("/api/gateway/invocations")
        assert list_inv_resp.status_code == 200
        assert isinstance(list_inv_resp.json()["invocations"], list)

        endpoint_registered = any(
            route.path == "/api/gateway/invocations/events" and "GET" in route.methods
            for route in app.routes
        )
        assert endpoint_registered
