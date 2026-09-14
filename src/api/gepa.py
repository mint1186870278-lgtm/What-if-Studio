"""GEPA-style prompt candidate, evaluation and publishing endpoints."""

from fastapi import APIRouter, HTTPException

from src.core.gepa_service import gepa_service
from src.schemas import (
    GEPACandidateCreate,
    GEPAEvaluateRequest,
    GEPAPublishRequest,
    GEPAProposalRequest,
    GEPAOptimizeRequest,
)

router = APIRouter(prefix="/gepa", tags=["gepa"])


@router.get("/config")
def get_gepa_config():
    return gepa_service.config()


@router.get("/candidates")
def list_gepa_candidates():
    return {"candidates": gepa_service.list_candidates()}


@router.post("/candidates", status_code=201)
def create_gepa_candidate(payload: GEPACandidateCreate):
    try:
        return gepa_service.create_candidate(**payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/proposals", status_code=201)
def propose_gepa_candidate(payload: GEPAProposalRequest):
    """Create a reviewable prompt mutation from feedback/execution cases."""
    try:
        return gepa_service.propose_candidate(**payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/optimize")
def optimize_gepa(payload: GEPAOptimizeRequest):
    """Run propose → staged comparison → held-out evaluation → publish.

    Publishing is deliberately best effort: a candidate that misses the
    threshold is returned for inspection and remains in ``evaluated`` state.
    """
    try:
        if not payload.independent_cases:
            raise HTTPException(
                status_code=400,
                detail="independent_cases is required for GEPA optimization",
            )
        candidate = gepa_service.propose_candidate(
            payload.strategy,
            payload.cases,
            seed_prompt=payload.seed_prompt,
            model=payload.model,
            budget=payload.budget,
        )
        comparison = gepa_service.compare_stages(candidate.id, payload.cases)
        independent = gepa_service.evaluate(
            candidate.id,
            payload.cases,
            stage="optimized",
            independent=True,
            independent_cases=payload.independent_cases or None,
        )
        try:
            published = gepa_service.publish(candidate.id, min_score=payload.min_score)
            publish_status = "published"
        except ValueError as exc:
            published = None
            publish_status = str(exc)
        return {
            "candidate": candidate,
            "comparison": comparison,
            "independent": independent,
            "publish_status": publish_status,
            "published": published,
        }
    except HTTPException:
        raise
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/candidates/{candidate_id}/evaluate")
def evaluate_gepa_candidate(candidate_id: str, payload: GEPAEvaluateRequest):
    try:
        return gepa_service.evaluate(
            candidate_id,
            payload.cases,
            stage=payload.stage,
            independent=payload.independent,
            independent_cases=payload.independent_cases,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/candidates/{candidate_id}/compare")
def compare_gepa_candidate(candidate_id: str, payload: GEPAEvaluateRequest):
    try:
        return gepa_service.compare_stages(candidate_id, payload.cases)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/candidates/{candidate_id}/publish")
def publish_gepa_candidate(candidate_id: str, payload: GEPAPublishRequest):
    try:
        return gepa_service.publish(candidate_id, min_score=payload.min_score)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
