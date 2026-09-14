"""Feedback API routes for explicit user ratings and preference learning."""

from __future__ import annotations

import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from src.db import get_db
from src.schemas import FeedbackRequest, FeedbackResponse
from src.models import Project, Session as DBSession
from src.core.memory_service import memory_service
from src.core.personalization_service import personalization_service
from src.core.gepa_service import gepa_service
from src.api.auth import current_user_id
from src.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(
    req: FeedbackRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Submit explicit feedback on a discussion/script.

    SQL stores authoritative preferences/experiences atomically; Mem0 receives
    a best-effort historical case after that transaction commits.
    """
    feedback_id = str(uuid4())
    identity = current_user_id(request)
    if identity and req.user_id and identity != req.user_id:
        raise HTTPException(status_code=403, detail="User identity does not match authenticated user")
    if identity is None and not settings.debug:
        raise HTTPException(status_code=401, detail="X-User-ID is required")
    if identity and (req.project_id or req.session_id):
        project = None
        if req.session_id:
            session = db.query(DBSession).filter(DBSession.id == str(req.session_id)).first()
            if session is None:
                raise HTTPException(status_code=404, detail="Session not found")
            project = session.project
            if req.project_id and str(session.project_id) != str(req.project_id):
                raise HTTPException(status_code=400, detail="Session does not belong to project")
        elif req.project_id:
            project = db.query(Project).filter(Project.id == str(req.project_id)).first()
            if project is None:
                raise HTTPException(status_code=404, detail="Project not found")
        if project is not None:
            owner = (project.metadata_ or {}).get("owner_user_id")
            if owner and owner != identity:
                raise HTTPException(status_code=403, detail="Resource belongs to another user")
            if owner is None and not settings.debug:
                raise HTTPException(status_code=403, detail="Resource ownership is not established")
    # Development keeps the historical project/anonymous fallback.  In an
    # authenticated request the header is always authoritative for SQL and
    # Mem0 tenant scoping, even when the body contains a different user_id.
    user_id = identity or req.user_id or (req.project_id or "anonymous")
    evidence_ref = req.session_id or req.project_id or feedback_id

    # Persist only explicit user evidence.  A rating is bounded to the
    # referenced session/project and therefore cannot overwrite a global
    # preference.  Aspect selections retain that same scope; they are direct
    # user choices, not model-generated inferences.
    observations: list[dict] = []
    bounded_scope = "session" if req.session_id else ("project" if req.project_id else "global")
    for liked in req.liked_aspects:
        observations.append({
            "key": "likes",
            "value": liked,
            "scope": bounded_scope,
            "project_id": req.project_id,
            "session_id": req.session_id,
            "applicability_condition": "feedback-positive",
            "source": "explicit_feedback",
            "evidence_source": "explicit_feedback",
            "evidence_ref": evidence_ref,
            "confidence": min(1.0, 0.55 + req.rating * 0.08),
        })
    for disliked in req.disliked_aspects:
        observations.append({
            "key": "dislikes",
            "value": disliked,
            "scope": bounded_scope,
            "project_id": req.project_id,
            "session_id": req.session_id,
            "applicability_condition": "feedback-negative",
            "source": "explicit_feedback",
            "evidence_source": "explicit_feedback",
            "evidence_ref": evidence_ref,
            "confidence": min(1.0, 0.55 + (6 - req.rating) * 0.08),
        })
    # Keep a bounded rating observation for audit/analytics, never as a global
    # style preference.
    observations.append({
        "key": "feedback_rating",
        "value": str(req.rating),
        "scope": bounded_scope,
        "project_id": req.project_id,
        "session_id": req.session_id,
        "applicability_condition": "feedback",
        "source": "explicit_feedback",
        "evidence_source": "explicit_feedback",
        "evidence_ref": evidence_ref,
        "confidence": 0.95,
    })

    preferences_saved = 0
    # SQL is the authoritative learning store.  Persist the profile,
    # preferences and ACE experience in one transaction before touching Mem0;
    # a remote semantic-memory outage must never lose explicit user feedback.
    try:
        saved = personalization_service.apply_observations(
            db, user_id, observations, commit=False
        )
        preferences_saved = len(saved)

        # Convert sufficiently concrete feedback into one ACE-style entry.
        # The evidence text is the user's own comment/aspect selection.
        evidence_parts = [*(f"喜欢：{x}" for x in req.liked_aspects), *(f"不喜欢：{x}" for x in req.disliked_aspects)]
        if req.comments:
            evidence_parts.append(req.comments)
        if evidence_parts:
            advice = "；".join(
                [f"保留{', '.join(req.liked_aspects)}" if req.liked_aspects else "", f"避免{', '.join(req.disliked_aspects)}" if req.disliked_aspects else ""]
            ).strip("；")
            if advice:
                personalization_service.record_experience(
                    db,
                    user_id,
                    applicable_condition=f"反馈场景 {req.project_id or req.session_id or 'general'}",
                    advice=advice,
                    user_evidence="；".join(evidence_parts),
                    evidence_source="explicit_feedback",
                    evidence_ref=evidence_ref,
                    project_id=req.project_id,
                    session_id=req.session_id,
                    confidence=min(1.0, 0.55 + req.rating * 0.08 if req.rating >= 3 else 0.75),
                    commit=False,
                )
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception("Failed to persist authoritative feedback for %s", user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to persist feedback",
        ) from exc

    # Mem0 stores a semantic historical case only (never the source of truth
    # for structured preferences).  It is deliberately best effort after the
    # SQL commit, so transient network/provider failures do not fail the API.
    try:
        await memory_service.record_feedback(
            user_id,
            evidence_ref,
            {
                "rating": req.rating,
                "comments": req.comments or "",
                "liked": req.liked_aspects,
                "disliked": req.disliked_aspects,
                "session_id": req.session_id,
                "project_id": req.project_id,
            },
        )
    except Exception as exc:
        logger.warning(
            "Semantic feedback storage unavailable for %s; SQL feedback is retained: %s",
            user_id,
            exc,
        )

    try:
        gepa_service.record_execution(
            "director_writing",
            {
                "user_id": user_id,
                "project_id": req.project_id,
                "session_id": req.session_id,
                "feedback": True,
            },
            {
                "rating": req.rating,
                "liked_aspects": req.liked_aspects,
                "disliked_aspects": req.disliked_aspects,
                "comments": (req.comments or "")[:1000],
            },
        )
    except Exception as exc:
        logger.debug("Unable to record GEPA feedback execution: %s", exc)

    logger.info(
        "Feedback %s recorded: user=%s rating=%d comments=%s",
        feedback_id, user_id, req.rating, (req.comments or "")[:60],
    )

    return FeedbackResponse(
        status="ok",
        message=f"Feedback recorded. {preferences_saved} preferences updated.",
        feedback_id=feedback_id,
    )
