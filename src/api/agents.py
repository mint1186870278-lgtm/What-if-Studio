"""Agent catalog API routes."""

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException


router = APIRouter()


@router.get("/agents")
async def list_agents():
    repo_root = Path(__file__).resolve().parents[2]
    candidates = [
        repo_root / "web" / "public" / "mock" / "agents.json",
        repo_root / "web" / "dist" / "mock" / "agents.json",
    ]
    for path in candidates:
        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return {"agents": data}
            raise HTTPException(status_code=500, detail="agents catalog format invalid")
    raise HTTPException(status_code=404, detail="agents catalog not found")
