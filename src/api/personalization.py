"""User profile, preference and creative-experience API.

These routes expose the auditable personalization store without exposing Mem0
internals.  Every write requires a user-originated evidence source; generated
director/script text is rejected by the service layer.
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from src.db import get_db
from src.models import UserPreference
from src.schemas import (
    ExperienceCreate,
    ExperienceResponse,
    PreferenceObservationCreate,
    UserPreferenceResponse,
    UserProfileResponse,
    UserProfileUpdate,
)
from src.core.personalization_service import (
    extract_user_observations,
    personalization_service,
)
from src.api.auth import require_user_scope

router = APIRouter(dependencies=[Depends(require_user_scope)])


def _user_id_or_400(user_id: str) -> str:
    # Service performs the full validation; this keeps route errors as 4xx.
    if not user_id or len(user_id) > 255:
        raise HTTPException(status_code=400, detail="Invalid user_id")
    return user_id


@router.get("/users/{user_id}/profile", response_model=UserProfileResponse)
def get_user_profile(user_id: str, db: Session = Depends(get_db)):
    user_id = _user_id_or_400(user_id)
    profile = personalization_service.get_profile(db, user_id)
    if profile is None:
        # A profile is a stable container; creating it on first read makes the
        # API idempotent and lets clients render an empty profile immediately.
        profile = personalization_service.ensure_profile(db, user_id)
        db.commit()
        db.refresh(profile)
    return profile


@router.put("/users/{user_id}/profile", response_model=UserProfileResponse)
def update_user_profile(
    user_id: str,
    payload: UserProfileUpdate,
    db: Session = Depends(get_db),
):
    user_id = _user_id_or_400(user_id)
    values = payload.model_dump(exclude_none=True)
    source = values.pop("evidence_source", "user_expression")
    evidence_ref = values.pop("evidence_ref", None)
    observations = []
    for key in ("ending_tendency", "emotional_style", "original_fidelity"):
        if key in values:
            observations.append(
                {
                    "key": key,
                    "value": values[key],
                    "scope": "global",
                    "source": source,
                    "evidence_source": source,
                    "evidence_ref": evidence_ref,
                }
            )
    for key, value in (values.get("profile_data") or {}).items():
        if value is not None:
            observations.append(
                {
                    "key": str(key),
                    "value": str(value),
                    "scope": "global",
                    "source": source,
                    "evidence_source": source,
                    "evidence_ref": evidence_ref,
                }
            )
    try:
        personalization_service.apply_observations(db, user_id, observations)
        profile = personalization_service.get_profile(db, user_id)
        assert profile is not None
        return profile
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/users/{user_id}/preferences", response_model=List[UserPreferenceResponse])
def list_user_preferences(
    user_id: str,
    include_inactive: bool = Query(False),
    scope: Optional[str] = Query(None),
    project_id: Optional[str] = Query(None),
    session_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    try:
        return personalization_service.list_preferences(
            db,
            _user_id_or_400(user_id),
            include_inactive=include_inactive,
            scope=scope,
            project_id=project_id,
            session_id=session_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/users/{user_id}/preferences", response_model=UserPreferenceResponse, status_code=status.HTTP_201_CREATED)
def create_user_preference(
    user_id: str,
    payload: PreferenceObservationCreate,
    db: Session = Depends(get_db),
):
    try:
        rows = personalization_service.apply_observations(
            db,
            _user_id_or_400(user_id),
            [
                {
                    "key": payload.key,
                    "value": payload.value,
                    "scope": payload.scope,
                    "project_id": payload.project_id,
                    "session_id": payload.session_id,
                    "applicability_condition": payload.applicability_condition,
                    "source": payload.source,
                    "evidence_source": payload.source,
                    "evidence_ref": payload.evidence_ref,
                    "confidence": payload.confidence,
                }
            ],
        )
        if not rows:
            raise HTTPException(status_code=400, detail="No preference observation supplied")
        return rows[-1]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/users/{user_id}/observations", response_model=List[UserPreferenceResponse], status_code=status.HTTP_201_CREATED)
def create_user_observations(
    user_id: str,
    text: str = Query(..., min_length=1, description="User-authored expression/choice/edit"),
    source: str = Query("user_expression"),
    scope: str = Query("global"),
    project_id: Optional[str] = Query(None),
    session_id: Optional[str] = Query(None),
    evidence_ref: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    try:
        rows = personalization_service.record_user_text(
            db,
            _user_id_or_400(user_id),
            text,
            source=source,
            scope=scope,
            project_id=project_id,
            session_id=session_id,
            evidence_ref=evidence_ref,
        )
        return rows
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/users/{user_id}/preferences/{preference_id}", status_code=status.HTTP_204_NO_CONTENT)
def invalidate_user_preference(user_id: str, preference_id: str, db: Session = Depends(get_db)):
    try:
        row = (
            db.query(UserPreference)
            .filter(UserPreference.id == preference_id, UserPreference.user_id == _user_id_or_400(user_id))
            .one_or_none()
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Preference not found")
        row.status = "invalid"
        row.version = (row.version or 0) + 1
        db.commit()
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/users/{user_id}/experiences", response_model=List[ExperienceResponse])
def list_user_experiences(
    user_id: str,
    include_inactive: bool = Query(False),
    db: Session = Depends(get_db),
):
    try:
        return personalization_service.list_experiences(
            db, _user_id_or_400(user_id), include_inactive=include_inactive
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/users/{user_id}/experiences", response_model=ExperienceResponse, status_code=status.HTTP_201_CREATED)
def create_user_experience(
    user_id: str,
    payload: ExperienceCreate,
    db: Session = Depends(get_db),
):
    try:
        return personalization_service.record_experience(
            db,
            _user_id_or_400(user_id),
            applicable_condition=payload.applicable_condition,
            advice=payload.advice,
            user_evidence=payload.user_evidence,
            evidence_source=payload.evidence_source,
            evidence_ref=payload.evidence_ref,
            project_id=payload.project_id,
            session_id=payload.session_id,
            confidence=payload.confidence,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/users/{user_id}/experiences/{experience_id}", response_model=ExperienceResponse)
def invalidate_user_experience(user_id: str, experience_id: str, db: Session = Depends(get_db)):
    try:
        row = personalization_service.invalidate_experience(db, _user_id_or_400(user_id), experience_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Experience not found")
    return row


@router.get("/users/{user_id}/personalization-context")
def get_personalization_context(
    user_id: str,
    current_request: str = Query(""),
    project_id: Optional[str] = Query(None),
    session_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    try:
        return personalization_service.build_context(
            db,
            _user_id_or_400(user_id),
            current_request=current_request,
            project_id=project_id,
            session_id=session_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
