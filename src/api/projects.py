"""Project management API routes"""

import hashlib
import logging
from uuid import UUID
from typing import Any, AsyncGenerator, List, Optional
from datetime import datetime, timezone
import json

from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from src.db import get_db
from src.models import Project, Asset, Session as DBSession, VideoJob, UserPreference, ScriptVector
from src.schemas import (
    ProjectCreate, ProjectUpdate, ProjectResponse,
    OutputSelectRequest, StoryboardGenerateResponse,
    StoryboardConfirmRequest, StoryboardConfirmResponse,
    SessionResumeRequest,
)
from src.core.memory_service import memory_service
from src.core.personalization_service import personalization_service
from src.core.model_router import model_router, ModelProvider
from src.api.auth import current_user_id, require_resource_owner, resolve_user_id

# Prefer LangGraph; fall back to AutoGen
try:
    from src.agents import (
        run_langgraph_discussion_stream as _discuss_stream,
        resume_langgraph_discussion_stream as _resume_stream,
        get_discussion_state as _get_discussion_state,
    )
except Exception:
    from src.agents import run_autogen_discussion_stream as _discuss_stream  # type: ignore[assignment]
    _resume_stream = None
    _get_discussion_state = None

if not callable(_discuss_stream):
    from src.agents import run_autogen_discussion_stream as _discuss_stream  # type: ignore[assignment]
if not callable(_resume_stream):
    _resume_stream = None
if not callable(_get_discussion_state):
    _get_discussion_state = None

# Compatibility hook retained for existing clients/tests.  New calls use the
# LangGraph stream above; replacing this symbol allows old integrations to
# inject a deterministic stream.
from src.agents.autogen_service import run_autogen_discussion_stream
_DEFAULT_AUTOGEN_STREAM = run_autogen_discussion_stream

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    """Return a naive UTC timestamp for SQLAlchemy DateTime columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)

router = APIRouter(dependencies=[Depends(require_resource_owner)])


@router.post("/projects", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    project_create: ProjectCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    """Create a new project"""
    try:
        project = Project(
            name=project_create.name,
            description=project_create.description,
            prompt=project_create.prompt or "",
            style_preference=project_create.style_preference or "auto",
            discussion_history=[],
            discussion_status="idle",
            metadata_=({"owner_user_id": current_user_id(request)} if current_user_id(request) else {}),
            output_type="script_only",
        )
        db.add(project)
        db.commit()
        db.refresh(project)
        logger.info(f"✅ Project created: {project.id} - {project.name}")
        return project
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Failed to create project: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create project: {str(e)}",
        )


@router.get("/projects/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: UUID,
    db: Session = Depends(get_db),
):
    """Get project by ID"""
    project_id_str = str(project_id)
    project = db.query(Project).filter(Project.id == project_id_str).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )
    project.last_opened_at = _utcnow()
    db.commit()
    db.refresh(project)
    return project


@router.get("/projects/{project_id}/discussion-state")
async def get_project_discussion_state(
    project_id: UUID,
    db: Session = Depends(get_db),
):
    """Expose the project thread's durable state for refresh/reconnect flows."""
    project = db.query(Project).filter(Project.id == str(project_id)).first()
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    if _get_discussion_state is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Native LangGraph state is unavailable",
        )
    state = await _get_discussion_state(str(project_id))
    if state is None:
        raise HTTPException(status_code=404, detail="Discussion checkpoint not found")
    return state


@router.get("/projects", response_model=List[ProjectResponse])
async def list_projects(
    request: Request,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    """List all projects with pagination"""
    projects = (
        db.query(Project)
        .order_by(Project.last_opened_at.desc().nullslast(), Project.updated_at.desc())
        .all()
    )
    # ``/projects`` has no path identifier for ``require_resource_owner`` to
    # inspect.  Filter here so an authenticated user cannot enumerate another
    # user's projects.  Unowned legacy projects remain visible only to the
    # anonymous/debug compatibility flow.
    identity = current_user_id(request) if request is not None else None
    if identity:
        projects = [
            project for project in projects
            if (project.metadata_ or {}).get("owner_user_id") == identity
        ]
    return projects[max(0, skip): max(0, skip) + max(0, min(limit, 1000))]


@router.put("/projects/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: UUID,
    project_update: ProjectUpdate,
    db: Session = Depends(get_db),
):
    """Update project"""
    project_id_str = str(project_id)
    project = db.query(Project).filter(Project.id == project_id_str).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )

    try:
        if project_update.name is not None:
            project.name = project_update.name
        if project_update.description is not None:
            project.description = project_update.description
        if project_update.prompt is not None:
            project.prompt = project_update.prompt
        if project_update.style_preference is not None:
            project.style_preference = project_update.style_preference

        db.commit()
        db.refresh(project)
        logger.info(f"✅ Project updated: {project.id}")
        return project
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Failed to update project: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update project: {str(e)}",
        )


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: UUID,
    db: Session = Depends(get_db),
):
    """Delete project and all associated data"""
    try:
        project_id_str = str(project_id)
        project = db.query(Project).filter(Project.id == project_id_str).first()
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project {project_id} not found",
            )

        # Delete associated sessions and assets
        db.query(Asset).filter(Asset.project_id == project_id_str).delete()
        db.query(DBSession).filter(DBSession.project_id == project_id_str).delete()

        # Delete project
        db.delete(project)
        db.commit()

        logger.info(f"✅ Project deleted: {project_id}")
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Failed to delete project: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete project: {str(e)}",
        )


async def _generate_project_discussion_stream(project: Project, db: Session, user_id: Optional[str] = None):
    turns = []
    script = ""
    paused = False
    project.discussion_status = "running"
    db.commit()
    yield f"data: {json.dumps({'type': 'system', 'content': 'discussion_started'}, ensure_ascii=False)}\n\n"
    try:
        user_request = f"{project.name}：{project.prompt or ''}" if project.name else (project.prompt or "")
        # Use project_id as session_id so WebSocket intervention can match
        sid = str(project.id)
        stream_fn = run_autogen_discussion_stream if run_autogen_discussion_stream is not _DEFAULT_AUTOGEN_STREAM else _discuss_stream
        stream_kwargs = {
            "user_request": user_request,
            "style": project.style_preference or "auto",
            "user_id": user_id,
            "session_id": sid,
        }
        if user_id:
            try:
                stream_kwargs["personalization_context"] = personalization_service.build_context(
                    db,
                    user_id,
                    current_request=user_request,
                    project_id=str(project.id),
                    session_id=None,
                )
            except Exception as exc:
                logger.debug("Structured personalization context unavailable: %s", exc)
        try:
            stream_iter = stream_fn(**stream_kwargs)
        except TypeError as exc:
            # Older AutoGen/test adapters accept only user_request/style.
            if not any(token in str(exc) for token in ("unexpected keyword", "positional argument", "required positional")):
                raise
            stream_iter = stream_fn(user_request=user_request, style=project.style_preference or "auto")
        async for event in stream_iter:
            # Map type → event for frontend compatibility
            if "type" in event and "event" not in event:
                event["event"] = event["type"]
            if event.get("type") == "turn":
                turns.append(event)
            elif event.get("type") == "user_intervention":
                if user_id:
                    try:
                        personalization_service.record_user_text(
                            db,
                            user_id,
                            str(event.get("content") or ""),
                            source="user_edit",
                            scope="project",
                            project_id=str(project.id),
                            evidence_ref=str(project.id),
                        )
                    except Exception as exc:
                        logger.debug("Unable to persist project intervention evidence: %s", exc)
            elif event.get("type") == "script":
                script = str(event.get("script", ""))
            elif event.get("type") == "awaiting_input":
                # Native LangGraph interruption is a normal resumable state;
                # never let the no-script path mark this project completed.
                paused = True
                turns.append(event)
                project.discussion_history = turns
                project.discussion_status = "awaiting_user"
                db.commit()
            elif event.get("type") == "paused":
                paused = True
                turns.append(event)
                project.discussion_history = turns
                project.discussion_status = "paused"
                db.commit()

            # Persist before yielding so a client disconnect immediately after
            # the question still observes the correct lifecycle state.
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

        if paused:
            project.discussion_history = turns
            db.commit()
            return

        project.discussion_history = turns
        project.script = script
        project.discussion_status = "completed"
        project.last_opened_at = _utcnow()
        db.commit()

        # --- Memory persistence: auto-save scripts ---
        if script:
            metadata = {
                "project_id": str(project.id),
                "style": project.style_preference or "auto",
                "user_request": user_request[:256],
                "timestamp": _utcnow().isoformat(),
            }
            if user_id:
                metadata["user_id"] = user_id
            try:
                chroma_id = await memory_service.store_script(script, metadata)
                sv = ScriptVector(
                    chroma_doc_id=chroma_id,
                    project_id=str(project.id),
                    user_id=user_id or "anonymous",
                    style=project.style_preference or "auto",
                    prompt_hash=hashlib.sha256(user_request.encode()).hexdigest()[:64],
                )
                db.add(sv)
                db.commit()
                logger.info("Script saved to memory: chroma_id=%s project=%s", chroma_id, project.id)
            except Exception as mem_exc:
                logger.warning("Failed to save script to memory: %s", mem_exc)

        # Do not learn from generated script/model output.  Long-term memory
        # may only be updated by the personalization service when it receives
        # an explicit user expression, choice, edit, or feedback event.

    except Exception as exc:
        # A generator cancellation/late transport error must not overwrite a
        # checkpoint that has already been persisted as resumable.
        if project.discussion_status not in {"awaiting_user", "paused"} and not paused:
            project.discussion_status = "failed"
            db.commit()
        logger.exception("Project discussion failed: project_id=%s", project.id)
        yield f"data: {json.dumps({'type': 'error', 'message': str(exc)}, ensure_ascii=False)}\n\n"


async def _generate_project_resume_stream(
    project: Project,
    user_input: Any,
    db: Session,
    user_id: Optional[str] = None,
) -> AsyncGenerator[str, None]:
    """Resume the LangGraph thread used by the project-level UI stream.

    ``/projects/{id}/script/stream`` historically used the project id as the
    graph ``thread_id`` (rather than creating a Session row first).  Keep that
    contract and expose a matching project resume endpoint so the browser can
    answer an interaction question without switching APIs mid-flow.
    """
    project_id = str(project.id)
    turns = [item for item in (project.discussion_history or []) if isinstance(item, dict)]
    script = ""
    paused = False
    terminal_event: str | None = None
    stream_error: Exception | None = None

    try:
        if _resume_stream is None:
            raise RuntimeError("Native LangGraph resume is unavailable")

        project.discussion_status = "running"
        db.commit()

        try:
            stream_iter = _resume_stream(session_id=project_id, user_input=user_input)
        except TypeError as exc:
            # Compatibility with early adapters that used positional names or
            # accepted only a plain ``text`` argument.
            if not any(token in str(exc) for token in ("unexpected keyword", "positional argument", "required positional")):
                raise
            stream_iter = _resume_stream(project_id, user_input)

        async for event in stream_iter:
            if not isinstance(event, dict):
                continue
            event_type = event.get("type")
            if event_type == "turn":
                turns.append(event)
            elif event_type == "answer_applied":
                answer = str(event.get("answer") or "").strip()
                if user_id and answer:
                    try:
                        personalization_service.apply_observations(
                            db,
                            user_id,
                            [{
                                "key": "creative_decision",
                                "value": answer,
                                "scope": "project",
                                "project_id": str(project.id),
                                "applicability_condition": f"interaction:{event.get('question_id') or 'decision'}",
                                "source": "user_choice",
                                "evidence_source": "user_choice",
                                "evidence_ref": event.get("question_id") or str(project.id),
                            }],
                        )
                    except Exception as exc:
                        logger.debug("Unable to persist project interaction choice: %s", exc)
            elif event_type == "script":
                script = str(event.get("script", ""))
            elif event_type == "awaiting_input":
                paused = True
                terminal_event = "awaiting_input"
                turns.append(event)
                project.discussion_status = "awaiting_user"
                project.discussion_history = turns
                db.commit()
            elif event_type == "paused":
                paused = True
                terminal_event = "paused"
                turns.append(event)
                project.discussion_status = "paused"
                project.discussion_history = turns
                db.commit()

            # Save a script as soon as it is emitted; this makes completion
            # durable even if the SSE client drops before task_result.
            if event_type == "script" and script.strip():
                project.script = script
                project.discussion_history = turns
                db.commit()
            if event_type in {"task_result", "error"}:
                terminal_event = str(event_type)

            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

        if paused:
            project.discussion_history = turns
            db.commit()
            return
        if not script.strip():
            raise RuntimeError("Resumed discussion completed without a valid script.")

        project.script = script
        project.discussion_history = turns
        project.discussion_status = "completed"
        project.last_opened_at = _utcnow()
        db.commit()
    except Exception as exc:
        stream_error = exc
        # Preserve an already-persisted resumable state if transport cleanup
        # raises after the pause event reached the client.
        if project.discussion_status not in {"awaiting_user", "paused"} and not paused:
            project.discussion_status = "failed"
            db.commit()
        logger.exception("Project resume failed: project_id=%s", project_id)

    if stream_error:
        yield f"data: {json.dumps({'type': 'error', 'message': str(stream_error)}, ensure_ascii=False)}\n\n"
    elif paused and terminal_event != "paused":
        yield f"data: {json.dumps({'type': 'paused', 'session_id': project_id, 'stop_reason': 'awaiting_user'}, ensure_ascii=False)}\n\n"
    elif not paused and terminal_event != "task_result":
        yield f"data: {json.dumps({'type': 'task_result', 'stop_reason': 'critic_finished'}, ensure_ascii=False)}\n\n"


@router.post("/projects/{project_id}/script/stream")
async def generate_project_script_stream(
    project_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    user_id: Optional[str] = Query(None, description="Optional user identifier for memory features"),
):
    project_id_str = str(project_id)
    project = db.query(Project).filter(Project.id == project_id_str).first()
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    if not (project.prompt or "").strip():
        raise HTTPException(status_code=400, detail="Project prompt is empty")
    resolved_user = resolve_user_id(request, user_id)
    return StreamingResponse(
        _generate_project_discussion_stream(project, db, user_id=resolved_user),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _resolve_resume_payload(body: SessionResumeRequest) -> Any:
    answer = body.resolved_answer()
    if answer is None or (isinstance(answer, str) and not answer.strip()):
        raise HTTPException(
            status_code=getattr(status, "HTTP_422_UNPROCESSABLE_CONTENT", 422),
            detail="An answer is required to resume the discussion",
        )
    return answer


async def _project_resume_response(
    project_id: UUID,
    body: SessionResumeRequest,
    db: Session,
    user_id: Optional[str] = None,
) -> StreamingResponse:
    project = db.query(Project).filter(Project.id == str(project_id)).first()
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    if project.discussion_status == "completed":
        raise HTTPException(status_code=409, detail="Project discussion is already completed")
    answer = _resolve_resume_payload(body)
    if _resume_stream is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Native LangGraph resume is unavailable",
        )
    if body.question_id and _get_discussion_state is not None:
        try:
            state = await _get_discussion_state(str(project_id))
            active = (state or {}).get("active_question") if isinstance(state, dict) else None
            active_id = active.get("id") if isinstance(active, dict) else None
            if active_id and str(active_id) != str(body.question_id):
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Question is no longer active")
        except HTTPException:
            raise
        except Exception as exc:
            logger.debug("Unable to validate active project question %s: %s", project_id, exc)
    return StreamingResponse(
        _generate_project_resume_stream(project, answer, db, user_id=user_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/projects/{project_id}/script/resume")
async def resume_project_script(
    project_id: UUID,
    body: SessionResumeRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Answer an interaction question for the project-level script stream."""
    return await _project_resume_response(project_id, body, db, user_id=resolve_user_id(request))


@router.post("/projects/{project_id}/resume")
async def resume_project_discussion(
    project_id: UUID,
    body: SessionResumeRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Compatibility alias for project clients that omit ``script``."""
    return await _project_resume_response(project_id, body, db, user_id=resolve_user_id(request))


@router.post("/projects/{project_id}/video-jobs")
async def create_project_video_job(
    project_id: UUID,
    db: Session = Depends(get_db),
):
    project_id_str = str(project_id)
    project = db.query(Project).filter(Project.id == project_id_str).first()
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    if not (project.script or "").strip():
        raise HTTPException(status_code=409, detail="Project script not generated yet")

    session = db.query(DBSession).filter(DBSession.project_id == project_id_str).order_by(DBSession.created_at.desc()).first()
    if not session:
        session = DBSession(
            project_id=project_id_str,
            prompt=project.prompt or "",
            style_preference=project.style_preference or "auto",
            status="completed",
            script=project.script or "",
            discussion_history=project.discussion_history or [],
        )
        db.add(session)
        db.commit()
        db.refresh(session)
    else:
        session.prompt = project.prompt or ""
        session.style_preference = project.style_preference or "auto"
        session.script = project.script or ""
        session.discussion_history = project.discussion_history or []
        session.status = "completed"
        db.commit()
        db.refresh(session)

    job = VideoJob(
        session_id=str(session.id),
        phase="collect",
        status="pending",
        script=project.script or "",
        output_path=None,
    )
    db.add(job)
    project.last_opened_at = _utcnow()
    db.commit()
    db.refresh(job)
    return {"job": {"id": str(job.id), "jobId": str(job.id), "session_id": str(session.id), "status": job.status, "phase": job.phase}}


# ---------------------------------------------------------------------------
# Output format selection
# ---------------------------------------------------------------------------

@router.put("/projects/{project_id}/output/select", response_model=ProjectResponse)
async def select_output_format(
    project_id: UUID,
    req: OutputSelectRequest,
    db: Session = Depends(get_db),
):
    """Set the project's output format preference after discussion."""
    project_id_str = str(project_id)
    project = db.query(Project).filter(Project.id == project_id_str).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )
    project.output_type = req.output_type
    project.last_opened_at = _utcnow()
    db.commit()
    db.refresh(project)
    logger.info("Project %s output_type set to %s", project_id_str, req.output_type)
    return project


# ---------------------------------------------------------------------------
# Storyboard generation and confirmation
# ---------------------------------------------------------------------------

@router.post("/projects/{project_id}/storyboard/generate", response_model=StoryboardGenerateResponse)
async def generate_storyboard(
    project_id: UUID,
    db: Session = Depends(get_db),
):
    """Generate a storyboard/preview from the project's script using a text LLM."""
    project_id_str = str(project_id)
    project = db.query(Project).filter(Project.id == project_id_str).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )
    if not (project.script or "").strip():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project script not generated yet. Run the discussion first.",
        )

    try:
        storyboard = await model_router.video.generate_storyboard(
            project.script,
        )
    except Exception as e:
        logger.exception("Storyboard generation failed for project %s", project_id_str)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Storyboard generation failed: {str(e)}",
        )

    project.storyboard = storyboard
    project.last_opened_at = _utcnow()
    db.commit()

    logger.info("Storyboard generated for project %s: %d frames", project_id_str, len(storyboard.get("frames", [])))
    return StoryboardGenerateResponse(
        project_id=project_id_str,
        frames=storyboard.get("frames", []),
        total_duration=str(storyboard.get("total_duration", "")),
        generated_at=_utcnow(),
    )


@router.post("/projects/{project_id}/storyboard/confirm", response_model=StoryboardConfirmResponse)
async def confirm_storyboard(
    project_id: UUID,
    req: StoryboardConfirmRequest,
    db: Session = Depends(get_db),
):
    """Confirm a storyboard (kicks off video job) or request regeneration."""
    project_id_str = str(project_id)
    project = db.query(Project).filter(Project.id == project_id_str).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )

    if req.confirmed:
        if not (project.script or "").strip():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Project script not generated yet",
            )

        session = db.query(DBSession).filter(
            DBSession.project_id == project_id_str
        ).order_by(DBSession.created_at.desc()).first()

        if not session:
            session = DBSession(
                project_id=project_id_str,
                prompt=project.prompt or "",
                style_preference=project.style_preference or "auto",
                status="completed",
                script=project.script or "",
                discussion_history=project.discussion_history or [],
            )
            db.add(session)
            db.commit()
            db.refresh(session)
        else:
            session.prompt = project.prompt or ""
            session.style_preference = project.style_preference or "auto"
            session.script = project.script or ""
            session.discussion_history = project.discussion_history or []
            session.status = "completed"
            db.commit()
            db.refresh(session)

        job = VideoJob(
            session_id=str(session.id),
            phase="collect",
            status="pending",
            script=project.script or "",
            output_path=None,
        )
        db.add(job)
        project.last_opened_at = _utcnow()
        db.commit()
        db.refresh(job)

        logger.info("Video job %s created via storyboard confirm for project %s", job.id, project_id_str)
        return StoryboardConfirmResponse(
            status="video_started",
            message="Video generation job created",
            job={
                "id": str(job.id),
                "jobId": str(job.id),
                "session_id": str(session.id),
                "status": job.status,
                "phase": job.phase,
            },
        )
    else:
        feedback = (req.feedback or "").strip()
        if not feedback:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Feedback is required when storyboard is not confirmed",
            )

        try:
            adjusted_script = f"{project.script}\n\n[导演调整意见]: {feedback}"
            storyboard = await model_router.video.generate_storyboard(
                adjusted_script,
            )
        except Exception as e:
            logger.exception("Storyboard regeneration failed for project %s", project_id_str)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Storyboard regeneration failed: {str(e)}",
            )

        project.storyboard = storyboard
        project.last_opened_at = _utcnow()
        db.commit()

        logger.info("Storyboard regenerated with feedback for project %s", project_id_str)
        return StoryboardConfirmResponse(
            status="storyboard_regenerated",
            message="Storyboard regenerated with feedback",
            storyboard=storyboard,
        )


# ---------------------------------------------------------------------------
# Script export
# ---------------------------------------------------------------------------

@router.get("/projects/{project_id}/script/export")
async def export_script(
    project_id: UUID,
    format: str = "markdown",
    db: Session = Depends(get_db),
):
    """Export the project script in the requested format (markdown, json, txt)."""
    project_id_str = str(project_id)
    project = db.query(Project).filter(Project.id == project_id_str).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )
    if not (project.script or "").strip():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project script not generated yet",
        )

    script = project.script or ""

    safe_name = project_id_str[:8]  # ASCII-safe fallback

    if format == "json":
        import json as _json
        turns = [
            {
                "speaker": t.get("speaker", ""),
                "role": t.get("role", ""),
                "content": t.get("content", ""),
                "stage": t.get("stage", ""),
            }
            for t in (project.discussion_history or [])
        ]
        content = _json.dumps({
            "project_id": project_id_str,
            "name": project.name,
            "prompt": project.prompt,
            "script": script,
            "discussion_turns": turns,
            "storyboard": project.storyboard,
        }, ensure_ascii=False, indent=2)
        headers = {"Content-Disposition": f'attachment; filename="{safe_name}_script.json"'}

    elif format == "txt":
        content = script
        headers = {"Content-Disposition": f'attachment; filename="{safe_name}_script.txt"'}

    else:  # markdown
        lines = [
            f"# {project.name}",
            "",
            f"**Prompt:** {project.prompt or '(none)'}",
            f"**Style:** {project.style_preference or 'auto'}",
            f"**Generated:** {project.updated_at.isoformat() if project.updated_at else 'N/A'}",
            "",
            "---",
            "",
            "## Discussion",
            "",
        ]
        for turn in (project.discussion_history or []):
            speaker = turn.get("speaker", "Unknown")
            role = turn.get("role", "")
            content = turn.get("content", "")
            stage = turn.get("stage", "")
            lines.append(f"### {speaker} ({role})")
            lines.append(f"*Stage: {stage}*")
            lines.append("")
            lines.append(content)
            lines.append("")

        lines.extend([
            "---", "",
            "## Final Script", "",
            script, "",
        ])

        if project.storyboard:
            lines.extend([
                "---", "",
                "## Storyboard", "",
            ])
            for i, frame in enumerate(project.storyboard.get("frames", []), 1):
                lines.append(f"### Frame {i}")
                lines.append(f"- **Description:** {frame.get('description', '')}")
                lines.append(f"- **Timing:** {frame.get('timing', '')}")
                if frame.get("visual_prompt"):
                    lines.append(f"- **Visual Prompt:** {frame.get('visual_prompt', '')}")
                lines.append("")
            lines.append(f"**Total Duration:** {project.storyboard.get('total_duration', 'N/A')}")
            lines.append("")

        content = "\n".join(lines)
        headers = {"Content-Disposition": f'attachment; filename="{safe_name}_script.md"'}

    from fastapi.responses import Response

    if format == "json":
        mt = "application/json"
    elif format == "txt":
        mt = "text/plain; charset=utf-8"
    else:
        mt = "text/plain; charset=utf-8"
    return Response(content=content, media_type=mt, headers=headers)
