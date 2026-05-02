from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("ANET_TOKEN", "test-token")
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")
os.environ.setdefault("OPENAI_BASE_URL", "https://api.openai.com/v1")
os.environ.setdefault("OPENAI_MODEL", "gpt-4o-mini")

from src.db import Base, get_db
from src.main import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    storage_projects = tmp_path / "storage" / "projects"
    storage_projects.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("src.api.assets.settings.storage_projects_path", storage_projects)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def create_project(client):
    def _create_project(name: str = "unit-project", prompt: str = "让主角逆转结局") -> str:
        response = client.post(
            "/projects",
            json={
                "name": name,
                "prompt": prompt,
                "style_preference": "auto",
            },
        )
        assert response.status_code == 201, response.text
        return str(response.json()["id"])

    return _create_project
