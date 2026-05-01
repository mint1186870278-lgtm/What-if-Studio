"""Gateway API routes: list services, invoke agents, and invocation logs/SSE."""

import json
import logging
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Body
from pydantic import BaseModel
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session as DBSession

from src.db import get_db
from src.models import ANetInvocation
from src.core.agent_gateway import agent_gateway

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/gateway/services")
async def list_services():
    """Return a simple capabilities list. In real deployment this would query the
    ANet registry or service discovery."""
    # Placeholder: return a small static list
    services = [
        {"name": "agent-director", "capability": "generate_directing_advice"},
        {"name": "agent-composer", "capability": "compose_music"},
        {"name": "agent-editor", "capability": "propose_editing_plan"},
    ]
    return {"services": services}


class InvokeRequest(BaseModel):
    service: str
    payload: dict = {}


@router.post("/gateway/invoke")
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

        # Call agent
        resp = await agent_gateway.call_agent(service, payload)

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
