"""Gateway API routes: list services, invoke agents, and invocation logs/SSE."""

import asyncio
import json
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Body, Request
from pydantic import BaseModel, Field
from fastapi.responses import StreamingResponse
from sqlalchemy import and_
from sqlalchemy.orm import Session as DBSession

from src.db import get_db
from src.models import ANetInvocation, Session
from src.core.anet_gateway import call_service as anet_call_service
from src.core.render_service import render_video_from_session
from src.api.auth import current_user_id, require_authenticated

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_authenticated)])


@router.get("/gateway/services")
@router.get("/anet/services")
async def list_services():
    """Return a simple capabilities list. In real deployment this would query the
    ANet registry or service discovery."""
    # Backend-local AutoGen services.
    services = [
        {"name": "yinanping-studio", "capability": "multi_agent_director_debate_and_video_editing_pipeline"},
        # Stable local capability names retained for ANet/legacy clients.
        {"name": "autogen-discussion", "capability": "multi_agent_director_debate"},
        {"name": "autogen-edit", "capability": "script_editing_instructions"},
    ]
    return {"services": services}


class InvokeRequest(BaseModel):
    service: str
    payload: dict = Field(default_factory=dict)


async def _invoke_video_editing_service(payload: dict, db: DBSession) -> dict:
    session_id = payload.get("session_id")

    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required")
    asset_ids = payload.get("asset_ids") or []
    try:
        render_result = await render_video_from_session(db, session_id=session_id, asset_ids=asset_ids)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return {
        "service": "anet.video_editing",
        "status": "success",
        "project_id": str(render_result["project_id"]),
        "session_id": str(render_result["session_id"]),
        "output_path": str(render_result["output_path"]),
        "assets": render_result["assets"],
    }


@router.post("/gateway/invoke")
@router.post("/anet/invoke")
async def invoke_agent(
    request: Request,
    req: InvokeRequest = Body(...),
    db: DBSession = Depends(get_db),
):
    """Invoke an agent via the AgentGateway and record invocation log."""
    service = req.service
    payload = req.payload
    identity = current_user_id(request) if request is not None else None
    try:
        # Video rendering is resource-scoped even though the gateway payload
        # carries the session ID rather than a path parameter.  Check it here
        # before invoking the renderer or forwarding the request to a peer.
        session_id = payload.get("session_id") if isinstance(payload, dict) else None
        if session_id and identity:
            session = db.query(Session).filter(Session.id == str(session_id)).first()
            project = session.project if session else None
            if project is not None:
                owner = (project.metadata_ or {}).get("owner_user_id")
                if owner and owner != identity:
                    raise HTTPException(status_code=403, detail="Resource belongs to another user")
                if owner is None:
                    from src.config import settings
                    if not settings.debug:
                        raise HTTPException(status_code=403, detail="Resource ownership is not established")
        stored_payload = dict(payload or {})
        if identity:
            stored_payload.setdefault("owner_user_id", identity)
        # Create a pending invocation record
        inv = ANetInvocation(
            service_name=service,
            status="pending",
            payload=stored_payload,
            response=None,
            error=None,
        )
        db.add(inv)
        db.commit()
        db.refresh(inv)

        if service in {"anet.video_editing", "whatif-studio", "video-render", "seedance.render"}:
            resp = await _invoke_video_editing_service(payload, db)
        else:
            # Call autogen services through ANet-facing gateway
            resp = await anet_call_service(service, payload)

        # Update record
        inv.response = resp if isinstance(resp, dict) else {"result": resp}
        inv.status = "success"
        db.commit()

        return {"invocation_id": inv.id, "response": inv.response}
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Gateway invoke failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/gateway/invocations")
async def list_invocations(request: Request, limit: int = 100, db: DBSession = Depends(get_db)):
    """List recent ANet invocations"""
    identity = current_user_id(request)
    rows = db.query(ANetInvocation).order_by(ANetInvocation.timestamp.desc()).limit(max(1, min(limit, 1000))).all()
    items = [
        item for item in rows
        if not identity or (item.payload or {}).get("owner_user_id") == identity
    ]
    return {"invocations": [
        {
            "id": i.id,
            "service_name": i.service_name,
            "status": i.status,
            "timestamp": i.timestamp.isoformat(),
        }
        for i in items
    ]}


async def invocations_stream(db: DBSession, user_id: str | None = None):
    """SSE stream for new invocation rows using incremental polling."""
    last_seen_ts: datetime | None = None
    last_seen_id: str | None = None
    try:
        while True:
            query = db.query(ANetInvocation)
            if last_seen_ts is not None:
                query = query.filter(
                    and_(
                        ANetInvocation.timestamp >= last_seen_ts,
                    )
                )
            items = query.order_by(ANetInvocation.timestamp.asc(), ANetInvocation.id.asc()).limit(100).all()
            emitted = False
            for i in items:
                if user_id and (i.payload or {}).get("owner_user_id") != user_id:
                    continue
                if last_seen_ts is not None:
                    same_ts = i.timestamp == last_seen_ts
                    if i.timestamp < last_seen_ts:
                        continue
                    if same_ts and last_seen_id is not None and str(i.id) <= str(last_seen_id):
                        continue
                data = {
                    "id": i.id,
                    "service_name": i.service_name,
                    "status": i.status,
                    "timestamp": i.timestamp.isoformat(),
                }
                yield f"data: {json.dumps(data)}\n\n"
                emitted = True
                last_seen_ts = i.timestamp
                last_seen_id = str(i.id)
            if not emitted:
                yield ": heartbeat\n\n"
                await asyncio.sleep(1)
    except GeneratorExit:
        pass
    except Exception as exc:
        logger.warning("invocations_stream ended: %s", exc)

@router.get("/gateway/invocations/events")
async def gateway_invocations_events(request: Request, db: DBSession = Depends(get_db)):
    return StreamingResponse(
        invocations_stream(db, current_user_id(request)),
        media_type="text/event-stream",
    )
