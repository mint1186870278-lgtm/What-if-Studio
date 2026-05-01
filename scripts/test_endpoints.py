"""Quick runtime tests using FastAPI TestClient"""

import sys
from pathlib import Path

# Ensure project root is on sys.path so `src` can be imported
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from src.main import app

client = TestClient(app)


def run_tests():
    print("GET /api/health")
    r = client.get("/api/health")
    print(r.status_code, r.json())

    print("POST /api/projects")
    r = client.post("/api/projects", json={"name": "ci-test", "description": "test project"})
    print(r.status_code, r.json())
    proj = r.json()
    proj_id = proj["id"] if isinstance(proj, dict) and "id" in proj else None

    print("GET /api/projects")
    r = client.get("/api/projects")
    print(r.status_code, r.json())

    if proj_id:
        print("POST /api/sessions")
        r = client.post("/api/sessions", json={"project_id": proj_id, "prompt": "make hopeful", "style_preference": "warmHealing"})
        print(r.status_code, r.json())
        sess = r.json()
        sess_id = sess.get("id")

        print("GET /api/sessions/{id}")
        r = client.get(f"/api/sessions/{sess_id}")
        print(r.status_code, r.json())

        print("Invoke gateway mock agent")
        r = client.post("/api/gateway/invoke", json={"service": "agent-director", "payload": {"prompt": "short"}})
        print(r.status_code, r.json())

        print("Create video job")
        r = client.post("/api/video-jobs", json={"session_id": sess_id, "asset_ids": []})
        print(r.status_code, r.json())


if __name__ == '__main__':
    run_tests()
