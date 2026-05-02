"""Shared render service for session-driven video generation."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session as DBSession

from src.config import settings
from src.core.video_pipeline import generate_video_from_script
from src.models import Asset, Session


async def render_video_from_session(
    db: DBSession,
    session_id: str,
    asset_ids: list[str] | None = None,
) -> dict[str, object]:
    """Render video from a session script and project assets."""

    session = db.query(Session).filter(Session.id == session_id).first()
    if not session:
        raise ValueError(f"Session {session_id} not found")

    script = session.script or ""
    if not script:
        raise RuntimeError("session has no discussion script yet")

    selected_asset_ids = asset_ids or []
    if selected_asset_ids:
        assets = db.query(Asset).filter(Asset.id.in_(selected_asset_ids)).all()
    else:
        assets = db.query(Asset).filter(Asset.project_id == session.project_id).all()

    asset_paths = [asset.file_path for asset in assets]

    # Write output to project outputs directory
    output_dir = settings.storage_projects_path / str(session.project_id) / "outputs"
    output_path = str(output_dir / f"session_{session_id}.mp4")

    result_path = await generate_video_from_script(script, output_path)

    return {
        "project_id": session.project_id,
        "session_id": session.id,
        "script": script,
        "assets": asset_paths,
        "output_path": result_path,
    }
