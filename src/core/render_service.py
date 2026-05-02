"""Shared render service for session-driven video generation."""

from __future__ import annotations

from sqlalchemy.orm import Session as DBSession

from src.config import settings
from src.core.video_pipeline import call_seedance
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
    output_path = await call_seedance(
        api_url=settings.seedance_api_url,
        script=script,
        assets=asset_paths,
    )

    return {
        "project_id": session.project_id,
        "session_id": session.id,
        "script": script,
        "assets": asset_paths,
        "output_path": output_path,
    }
