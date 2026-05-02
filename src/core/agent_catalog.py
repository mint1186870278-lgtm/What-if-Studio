"""Agent catalog loading from repository config files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _agent_id(prefix: str, raw_id: Any) -> str:
    text = str(raw_id or "").strip()
    if text.startswith("agent-"):
        return text
    return f"agent-{text}"


def _home_from_role(role: str) -> dict[str, float]:
    if role == "crew":
        return {"x": 0.18, "y": 0.74}
    return {"x": 0.76, "y": 0.2}


def _normalize_home(raw_home: Any, role: str) -> dict[str, float]:
    if isinstance(raw_home, (list, tuple)) and len(raw_home) >= 2:
        return {"x": float(raw_home[0]), "y": float(raw_home[1])}
    if isinstance(raw_home, dict):
        return {"x": float(raw_home.get("x", 0.5)), "y": float(raw_home.get("y", 0.5))}
    return _home_from_role(role)


def _home_zone_from_home(home: dict[str, float], role: str) -> str:
    if role != "crew":
        return "directors"
    if home["x"] < 0.35:
        return "edit" if home["y"] > 0.5 else "archive"
    if home["x"] > 0.6:
        return "sound"
    return "archive"


def _normalize_agent(item: dict[str, Any]) -> dict[str, Any]:
    role_type = str(item.get("role") or "director").strip() or "director"
    avatar_url = str(item.get("avatar_url") or "").strip()
    home = _normalize_home(item.get("home"), role_type)
    home_zone = _home_zone_from_home(home, role_type)
    return {
        "agentId": _agent_id(role_type, item.get("id")),
        "name": str(item.get("name") or item.get("id") or "").strip(),
        "type": role_type,
        "stance": str(item.get("stance") or item.get("description") or "").strip(),
        "avatarUrl": avatar_url,
        "homeZone": home_zone,
        "home": home,
        "interestTags": list(item.get("interest_tags") or []),
    }


def load_agents() -> list[dict[str, Any]]:
    path = repo_root() / "config" / "agents.yaml"
    if not path.exists():
        raise FileNotFoundError(f"agent config not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    raw_agents = raw.get("agents") if isinstance(raw, dict) else raw
    if not isinstance(raw_agents, list):
        return []
    return [_normalize_agent(item) for item in raw_agents if isinstance(item, dict)]


def load_agent_map() -> dict[str, dict[str, Any]]:
    return {item["agentId"]: item for item in load_agents() if item.get("agentId")}
