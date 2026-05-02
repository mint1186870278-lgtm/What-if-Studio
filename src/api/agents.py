"""Agent catalog API routes."""

from fastapi import APIRouter, HTTPException

from src.core.agent_catalog import load_agents


router = APIRouter()


@router.get("/agents")
async def list_agents():
    try:
        return {"agents": load_agents()}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="agents catalog format invalid") from exc
