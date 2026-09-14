"""Session management API routes with SSE streaming"""

import hashlib
import json
import logging
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session as DBSession

from src.db import get_db
from src.config import settings
from src.models import Project, Session, VideoJob, UserPreference, ScriptVector
from src.schemas import (
    SessionCreate,
    SessionResponse,
    DiscussionTurn,
    InterveneRequest,
    SessionResumeRequest,
)
from src.core.memory_service import memory_service
from src.core.personalization_service import personalization_service
from src.api.auth import require_resource_owner, current_user_id, resolve_user_id

# Prefer LangGraph; fall back to AutoGen
try:
    from src.agents import (
        run_langgraph_discussion_stream as _discuss_stream,
        resume_langgraph_discussion_stream as _resume_stream,
        get_discussion_state as _get_discussion_state,
    )
    _BACKEND = "langgraph"
except Exception:
    from src.agents import run_autogen_discussion_stream as _discuss_stream  # type: ignore[assignment]
    _resume_stream = None
    _get_discussion_state = None
    _BACKEND = "autogen"

# ``src.agents`` intentionally exposes ``None`` when LangGraph dependencies
# are unavailable.  Treat that as the legacy backend as well; otherwise a
# request would fail later with an opaque ``NoneType is not callable`` error.
if not callable(_discuss_stream):
    from src.agents import run_autogen_discussion_stream as _discuss_stream  # type: ignore[assignment]
    _BACKEND = "autogen"
if not callable(_resume_stream):
    _resume_stream = None
if not callable(_get_discussion_state):
    _get_discussion_state = None

# Public compatibility wrapper.  Keeping the indirection dynamic means a
# deployment/test can replace either ``_resume_stream`` (the internal alias
# used by older code) or this public symbol without restarting the process.
async def resume_langgraph_discussion_stream(session_id: str, user_input: object):
    if _resume_stream is None:
        raise RuntimeError("Native LangGraph resume is unavailable")
    async for event in _resume_stream(session_id=session_id, user_input=user_input):
        yield event

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_resource_owner)])


def _initial_stream_iterator(
    *,
    user_request: str,
    style: str,
    session_id: str,
    user_id: Optional[str],
    memory_context: str = "",
    personalization_context: Optional[dict] = None,
):
    """Call either the new LangGraph or legacy stream signature.

    The legacy AutoGen runner predates ``session_id``/``user_id`` and several
    integrations still monkeypatch that three-argument-compatible function.
    Keep the compatibility fallback at this boundary instead of making every
    backend know about the other's metadata arguments.
    """
    try:
        return _discuss_stream(
            user_request=user_request,
            style=style,
            session_id=session_id,
            user_id=user_id,
            memory_context=memory_context,
            personalization_context=personalization_context,
        )
    except TypeError as exc:
        # Only retry for an unsupported signature.  A TypeError raised by a
        # normal synchronous factory is still useful to the caller, but the
        # old async-generator functions raise here before iteration starts.
        message = str(exc)
        if not any(token in message for token in ("unexpected keyword", "positional argument", "required positional")):
            raise
        return _discuss_stream(user_request=user_request, style=style)


def _set_discussion_status(
    db: DBSession,
    session_id: str,
    status: str,
    *,
    project_status: Optional[str] = None,
) -> tuple[Session | None, Project | None]:
    """Persist a discussion lifecycle status and return the affected rows.

    Native LangGraph interruptions are a normal, resumable state.  Keeping
    this update in one small helper makes it harder for an exception handler
    to accidentally overwrite ``awaiting_user`` with ``failed``.
    """
    session = db.query(Session).filter(Session.id == session_id).first()
    if session is None:
        return None, None
    session.status = status
    project = db.query(Project).filter(Project.id == session.project_id).first()
    if project is not None and project_status is not None:
        project.discussion_status = project_status
    db.commit()
    return session, project


@router.post("/sessions", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    session_create: SessionCreate,
    request: Request,
    db: DBSession = Depends(get_db),
):
    """Create a new session"""
    project = db.query(Project).filter(Project.id == session_create.project_id).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {session_create.project_id} not found",
        )
    identity = current_user_id(request)
    owner = (project.metadata_ or {}).get("owner_user_id")
    if identity and owner and owner != identity:
        raise HTTPException(status_code=403, detail="Project belongs to another user")
    if identity and not owner and not settings.debug:
        raise HTTPException(status_code=403, detail="Project ownership is not established")

    try:
        session = Session(
            project_id=session_create.project_id,
            prompt=session_create.prompt,
            style_preference=session_create.style_preference,
            status="active",
            discussion_history=[],
            script="",
        )
        db.add(session)
        db.commit()
        db.refresh(session)

        logger.info(f"Session created: {session.id}")
        return session

    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create session: {str(e)}",
        )


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    db: DBSession = Depends(get_db),
):
    """Get session by ID"""
    session = db.query(Session).filter(Session.id == session_id).first()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )
    return session


@router.get("/sessions/{session_id}/discussion-state")
async def get_session_discussion_state(
    session_id: str,
):
    """Return the durable LangGraph state, including an active question.

    A browser can call this after a refresh instead of relying on an SSE frame
    that was already consumed before the page disconnected.
    """
    if _get_discussion_state is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Native LangGraph state is unavailable",
        )
    state = await _get_discussion_state(session_id)
    if state is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Discussion checkpoint not found")
    return state


async def generate_discussion_stream(
    session_id: str,
    db: DBSession,
    user_id: Optional[str] = None,
) -> AsyncGenerator[str, None]:
    """Generate SSE stream for discussion"""
    paused = False
    turns: list[dict] = []
    script = ""
    resolved_user: Optional[str] = user_id
    try:
        session = db.query(Session).filter(Session.id == session_id).first()
        if not session:
            yield f"data: {json.dumps({'error': 'Session not found'})}\n\n"
            return
        project = db.query(Project).filter(Project.id == session.project_id).first()

        # A project id is not a user identity.  Falling back to it would make
        # an anonymous request appear authenticated to the memory layer and
        # could leak one project's history into another caller's context.
        # Without an explicit user id, keep memory disabled/isolated.
        resolved_user = user_id

        # Mark the run as active before opening the response.  A native
        # interrupt will transition this to ``awaiting_user``/``paused``
        # below; those are resumable lifecycle states, not failures.
        session.status = "active"
        if project is not None:
            project.discussion_status = "running"
        db.commit()

        structured_context = None
        if resolved_user:
            try:
                structured_context = personalization_service.build_context(
                    db,
                    resolved_user,
                    current_request=session.prompt,
                    project_id=str(session.project_id) if session.project_id else None,
                    session_id=session_id,
                )
            except Exception as exc:
                logger.debug("Structured personalization context unavailable: %s", exc)

        stream_iterator = _initial_stream_iterator(
            user_request=session.prompt,
            style=session.style_preference,
            session_id=session_id,
            user_id=resolved_user,
            personalization_context=structured_context,
        )
        async for event in stream_iterator:
            if event.get("type") == "turn":
                turns.append(event)
            elif event.get("type") == "user_intervention":
                # Real-time edits are explicit user evidence. Keep them
                # session-scoped so a one-off correction cannot rewrite the
                # long-term profile for later projects.
                if resolved_user:
                    try:
                        personalization_service.record_user_text(
                            db,
                            resolved_user,
                            str(event.get("content") or ""),
                            source="user_edit",
                            scope="session",
                            project_id=str(session.project_id) if session.project_id else None,
                            session_id=session_id,
                            evidence_ref=session_id,
                        )
                    except Exception as exc:
                        logger.debug("Unable to persist session intervention evidence: %s", exc)
            elif event.get("type") == "script":
                script = str(event.get("script", ""))
            elif event.get("type") == "awaiting_input":
                # Persist the checkpoint state at the exact point at which
                # the client sees the question.  This also makes a page
                # refresh safe: GET /sessions/{id} reports that the run is
                # waiting instead of presenting a misleading failure.
                paused = True
                turns.append(event)
                session.status = "awaiting_user"
                session.discussion_history = turns
                if project is not None:
                    project.discussion_status = "awaiting_user"
                    project.discussion_history = turns
                db.commit()

            elif event.get("type") == "paused":
                paused = True
                turns.append(event)
                session.status = "paused"
                session.discussion_history = turns
                if project is not None:
                    project.discussion_status = "paused"
                    project.discussion_history = turns
                db.commit()

            # Persist lifecycle/history before yielding.  ``yield`` suspends
            # this generator; doing it first would leave an awaiting session
            # marked active if an SSE client disconnects immediately after
            # receiving the event.
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

        # The graph intentionally ends its first stream after an interrupt,
        # before a script exists.  Do not convert that normal state into an
        # exception (and consequently ``failed``).
        if paused:
            session.discussion_history = turns
            if project is not None:
                project.discussion_history = turns
            db.commit()
            return

        if not script.strip():
            raise RuntimeError("Discussion completed without a valid script.")
        session.script = script
        session.discussion_history = turns
        session.status = "completed"
        if project is not None:
            project.script = script
            project.discussion_history = turns
            project.discussion_status = "completed"
        db.commit()

        # --- Memory persistence: auto-save scripts ---
        if script:
            metadata = {
                "project_id": session.project_id,
                "session_id": session_id,
                "style": session.style_preference or "auto",
                "user_request": session.prompt[:256],
                "timestamp": str(session.created_at) if session.created_at else "",
            }
            if resolved_user:
                metadata["user_id"] = resolved_user
            try:
                chroma_id = await memory_service.store_script(script, metadata)
                sv = ScriptVector(
                    chroma_doc_id=chroma_id,
                    project_id=session.project_id,
                    user_id=resolved_user or "anonymous",
                    style=session.style_preference or "auto",
                    prompt_hash=hashlib.sha256(session.prompt.encode()).hexdigest()[:64],
                )
                db.add(sv)
                db.commit()
                logger.info("Script saved to memory: chroma_id=%s session=%s", chroma_id, session_id)
            except Exception as mem_exc:
                logger.warning("Failed to save script to memory: %s", mem_exc)

        # Generated scripts are not user evidence.  Preference learning occurs
        # only through explicit user-expression/choice/edit/feedback routes.

        logger.info(f"Discussion stream completed for session {session_id}")

    except Exception as e:
        failed_session = db.query(Session).filter(Session.id == session_id).first()
        # A client may close/reconnect immediately after receiving the pause
        # event.  Preserve the resumable state even if the stream wrapper
        # reports a late exception while it is being torn down.
        if failed_session and failed_session.status not in {"awaiting_user", "paused"} and not paused:
            failed_session.status = "failed"
            if failed_session.project_id:
                failed_project = db.query(Project).filter(Project.id == failed_session.project_id).first()
                if failed_project:
                    failed_project.discussion_status = "failed"
            db.commit()
        logger.error(f"Discussion stream error: {e}")
        yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"


@router.get("/sessions/{session_id}/stream")
async def stream_discussion(
    session_id: str,
    request: Request,
    db: DBSession = Depends(get_db),
    user_id: Optional[str] = Query(None, description="Optional user identifier for memory features"),
):
    """Stream discussion as Server-Sent Events"""
    return StreamingResponse(
        generate_discussion_stream(session_id, db, user_id=resolve_user_id(request, user_id)),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/sessions/{session_id}/discuss/stream")
async def stream_discussion_legacy(
    session_id: str,
    request: Request,
    db: DBSession = Depends(get_db),
    user_id: Optional[str] = Query(None, description="Optional user identifier for memory features"),
):
    """Stream discussion (legacy endpoint for compatibility)"""
    return StreamingResponse(
        generate_discussion_stream(session_id, db, user_id=resolve_user_id(request, user_id)),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


async def generate_resume_stream(
    session_id: str,
    user_input: str,
    db: DBSession,
    user_id: Optional[str] = None,
) -> AsyncGenerator[str, None]:
    """Resume a native LangGraph checkpoint and persist its lifecycle.

    This is deliberately a separate generator from the initial discussion
    stream.  A resumed graph must receive ``Command(resume=...)`` so LangGraph
    can continue the interrupted task; replaying the initial request would run
    completed director nodes a second time.  Events are yielded in exactly the
    same order produced by the graph, while session/project status is updated
    *before* each SSE yield.
    """
    paused = False
    script = ""
    turns: list[dict] = []
    graph_error: Exception | None = None
    terminal_event: str | None = None
    session: Session | None = None
    project: Project | None = None

    try:
        session = db.query(Session).filter(Session.id == session_id).first()
        if session is None:
            yield f"data: {json.dumps({'type': 'error', 'message': 'Session not found'}, ensure_ascii=False)}\n\n"
            return
        project = db.query(Project).filter(Project.id == session.project_id).first()

        if _resume_stream is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Native LangGraph resume is unavailable",
            )

        # A completed session cannot be resumed.  ``active`` is accepted for
        # backwards compatibility with clients that persisted status before
        # the first awaiting_input event; the graph checkpoint remains the
        # source of truth in that case.
        if session.status == "completed":
            yield f"data: {json.dumps({'type': 'error', 'message': 'Session is already completed'}, ensure_ascii=False)}\n\n"
            return

        prior_history = list(session.discussion_history or [])
        turns.extend(item for item in prior_history if isinstance(item, dict))
        session.status = "active"
        if project is not None:
            project.discussion_status = "running"
        db.commit()

        async for event in _resume_stream(session_id=session_id, user_input=user_input):
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
                                "scope": "session",
                                "project_id": str(session.project_id) if session.project_id else None,
                                "session_id": session_id,
                                "applicability_condition": f"interaction:{event.get('question_id') or 'decision'}",
                                "source": "user_choice",
                                "evidence_source": "user_choice",
                                "evidence_ref": event.get("question_id") or session_id,
                            }],
                        )
                    except Exception as exc:
                        logger.debug("Unable to persist interaction choice: %s", exc)
            elif event_type == "script":
                script = str(event.get("script", ""))
            elif event_type == "awaiting_input":
                paused = True
                terminal_event = "awaiting_input"
                turns.append(event)
                session.status = "awaiting_user"
                session.discussion_history = turns
                if project is not None:
                    project.discussion_status = "awaiting_user"
                    project.discussion_history = turns
                db.commit()
            elif event_type == "paused":
                paused = True
                terminal_event = "paused"
                turns.append(event)
                session.status = "paused"
                session.discussion_history = turns
                if project is not None:
                    project.discussion_status = "paused"
                    project.discussion_history = turns
                db.commit()

            # If a resumed graph emits a script, persist it immediately.  A
            # disconnect after this event must not lose the completed result.
            if event_type == "script" and script.strip():
                session.script = script
                if project is not None:
                    project.script = script
                db.commit()

            if event_type in {"task_result", "error"}:
                terminal_event = str(event_type)

            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

        if paused:
            session.discussion_history = turns
            db.commit()
            return

        # ``task_result`` is emitted after the critic's script event in the
        # current graph.  Be defensive for custom runners that only checkpoint
        # the script in state and do not send a script event.
        if not script.strip() and _get_discussion_state is not None:
            try:
                state = await _get_discussion_state(session_id)
                if isinstance(state, dict):
                    script = str(state.get("script") or "")
            except Exception as state_exc:
                logger.warning("Unable to read resumed graph state %s: %s", session_id, state_exc)
        if not script.strip():
            raise RuntimeError("Resumed discussion completed without a valid script.")

        session.script = script
        session.discussion_history = turns
        session.status = "completed"
        if project is not None:
            project.script = script
            project.discussion_history = turns
            project.discussion_status = "completed"
        db.commit()

    except HTTPException as exc:
        # HTTPException raised while consuming a StreamingResponse cannot be
        # converted into a normal FastAPI response.  Keep the SSE contract and
        # expose its status in the event payload instead.
        graph_error = exc
        if session is not None:
            session.status = "failed"
            if project is not None:
                project.discussion_status = "failed"
            db.commit()
    except Exception as exc:
        graph_error = exc
        # Never overwrite a resumable checkpoint with ``failed``.  This guard
        # matters when a client disconnects while the pause event is being
        # flushed or when a generator is cancelled after persisting awaiting.
        current = db.query(Session).filter(Session.id == session_id).first()
        if current is not None and current.status not in {"awaiting_user", "paused"} and not paused:
            current.status = "failed"
            current_project = db.query(Project).filter(Project.id == current.project_id).first()
            if current_project is not None:
                current_project.discussion_status = "failed"
            db.commit()
        logger.exception("Resumed discussion failed: session_id=%s", session_id)

    if graph_error:
        detail = str(getattr(graph_error, "detail", graph_error))
        yield f"data: {json.dumps({'type': 'error', 'message': detail}, ensure_ascii=False)}\n\n"
    elif paused and terminal_event != "paused":
        yield f"data: {json.dumps({'type': 'paused', 'session_id': session_id, 'stop_reason': 'awaiting_user'}, ensure_ascii=False)}\n\n"
    elif not paused and terminal_event != "task_result":
        yield f"data: {json.dumps({'type': 'task_result', 'stop_reason': 'critic_finished'}, ensure_ascii=False)}\n\n"


async def _resume_stream_response(
    session_id: str,
    body: SessionResumeRequest,
    db: DBSession,
    user_id: Optional[str] = None,
) -> StreamingResponse:
    """Build a resumable SSE response after lightweight request validation."""
    answer = body.resolved_answer()
    if not answer:
        raise HTTPException(
            status_code=getattr(status, "HTTP_422_UNPROCESSABLE_CONTENT", 422),
            detail="An answer is required to resume the discussion",
        )
    session = db.query(Session).filter(Session.id == session_id).first()
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )
    if session.status == "completed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Session is already completed")
    if _resume_stream is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Native LangGraph resume is unavailable",
        )
    if body.question_id and _get_discussion_state is not None:
        try:
            state = await _get_discussion_state(session_id)
            active = (state or {}).get("active_question") if isinstance(state, dict) else None
            active_id = active.get("id") if isinstance(active, dict) else None
            if active_id and str(active_id) != str(body.question_id):
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Question is no longer active")
        except HTTPException:
            raise
        except Exception as exc:
            logger.debug("Unable to validate active question %s: %s", session_id, exc)
    return StreamingResponse(
        generate_resume_stream(session_id, answer, db, user_id=user_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/sessions/{session_id}/resume")
async def resume_discussion(
    session_id: str,
    body: SessionResumeRequest,
    request: Request,
    db: DBSession = Depends(get_db),
):
    """Answer the current interaction question and resume the graph.

    The endpoint intentionally returns SSE rather than a JSON acknowledgement:
    callers receive ``answer_applied`` and all subsequent director/script
    events in order, and can render a second question if policy pauses again.
    """
    return await _resume_stream_response(session_id, body, db, user_id=resolve_user_id(request))


@router.post("/sessions/{session_id}/discuss/resume")
async def resume_discussion_legacy(
    session_id: str,
    body: SessionResumeRequest,
    request: Request,
    db: DBSession = Depends(get_db),
):
    """Compatibility alias for clients using the discuss/stream namespace."""
    return await _resume_stream_response(session_id, body, db, user_id=resolve_user_id(request))


# ---------------------------------------------------------------------------
# REST intervention endpoint (fallback for WebSocket)
# ---------------------------------------------------------------------------

@router.post("/sessions/{session_id}/intervene")
async def intervene_session(
    session_id: str,
    body: InterveneRequest,
):
    """Inject user intervention into a running discussion via HTTP.

    This is a REST fallback for the WebSocket ``intervene`` action.
    """
    import asyncio as _asyncio

    from src.api.ws import intervention_flags, intervention_texts, pause_events

    text = body.text
    intervention_texts[session_id] = text

    flag = intervention_flags.get(session_id)
    if flag is None:
        flag = _asyncio.Event()
        intervention_flags[session_id] = flag
    flag.set()

    # Auto-resume if paused
    pause_evt = pause_events.get(session_id)
    if pause_evt is not None:
        pause_evt.set()

    logger.info("REST intervention for session %s: %s", session_id, text[:80])

    return {
        "status": "ok",
        "message": "Intervention queued -- will be injected at the next node boundary",
        "session_id": session_id,
    }
