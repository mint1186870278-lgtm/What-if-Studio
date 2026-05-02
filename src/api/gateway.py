"""Gateway API routes: list services, invoke agents, and invocation logs/SSE."""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session as DBSession

from src.db import get_db
from src.models import ANetInvocation
from src.core.anet_gateway import call_service as anet_call_service
from src.core.render_service import render_video_from_session

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/gateway/services")
@router.get("/anet/services")
async def list_services():
    """Return a simple capabilities list. In real deployment this would query the
    ANet registry or service discovery."""
    # Backend-local AutoGen services.
    services = [
        {"name": "yinanping-studio", "capability": "multi_agent_director_debate_and_video_editing_pipeline"},
    ]
    return {"services": services}


class InvokeRequest(BaseModel):
    service: str
    payload: dict = {}


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
async def invoke_agent(req: InvokeRequest = Body(...), db: DBSession = Depends(get_db)):
    """Invoke an agent via the AgentGateway and record invocation log."""
    service = req.service
    payload = req.payload
    try:
        # Create a pending invocation record
        inv = ANetInvocation(
            service_name=service,
            status="pending",
            payload=payload,
            response=None,
            error=None,
        )
        db.add(inv)
        db.commit()
        db.refresh(inv)

        if service in {"anet.video_editing", "video-editing-api", "video-render", "seedance.render"}:
            resp = await _invoke_video_editing_service(payload, db)
        else:
            # Call autogen services through ANet-facing gateway
            resp = await anet_call_service(service, payload)

        # Update record
        inv.response = resp if isinstance(resp, dict) else {"result": resp}
        inv.status = "success"
        db.commit()

        return {"invocation_id": inv.id, "response": inv.response}
    except Exception as e:
        db.rollback()
        logger.error(f"Gateway invoke failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/gateway/invocations")
async def list_invocations(limit: int = 100, db: DBSession = Depends(get_db)):
    """List recent ANet invocations"""
    items = db.query(ANetInvocation).order_by(ANetInvocation.timestamp.desc()).limit(limit).all()
    return {"invocations": [
        {
            "id": i.id,
            "service_name": i.service_name,
            "status": i.status,
            "timestamp": i.timestamp.isoformat(),
        }
        for i in items
    ]}


async def invocations_stream(db: DBSession):
    """Simple SSE stream that polls for new invocations. In production, use
    better eventing (Redis, Kafka, DB LISTENER)."""
    import time

    last_seen = None
    while True:
        items = db.query(ANetInvocation).order_by(ANetInvocation.timestamp.asc()).all()
        new_items = []
        for i in items:
            if last_seen is None or i.timestamp.isoformat() > last_seen:
                new_items.append(i)
        for i in new_items:
            data = {
                "id": i.id,
                "service_name": i.service_name,
                "status": i.status,
                "timestamp": i.timestamp.isoformat(),
            }
            yield f"data: {json.dumps(data)}\n\n"
            last_seen = i.timestamp.isoformat()
        time.sleep(1)


@router.get("/gateway/invocations/events")
async def gateway_invocations_events(db: DBSession = Depends(get_db)):
    return StreamingResponse(invocations_stream(db), media_type="text/event-stream")
