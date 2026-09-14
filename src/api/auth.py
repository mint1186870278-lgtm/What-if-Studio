"""Small, development-friendly request identity and ownership checks.

There is no external identity provider in the development build.  Clients may
send ``X-User-ID``; routes bind that identity to path user IDs and to the
owner recorded in project metadata.  In debug mode an omitted header remains
backwards compatible, while production deployments must provide it.
"""
import base64
import hashlib
import hmac
import json
import time

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from src.config import settings
from src.db import get_db
from src.models import Asset, Project, Session as DBSession, VideoJob


def _decode_bearer_user_id(request: Request) -> str | None:
    """Validate an externally issued HS256 JWT when AUTH_SECRET is set."""
    authorization = request.headers.get("Authorization", "")
    if not authorization and hasattr(request, "query_params"):
        access_token = request.query_params.get("access_token")
        if access_token:
            authorization = f"Bearer {access_token}"
    if not authorization.lower().startswith("bearer ") or not settings.auth_secret:
        return None
    token = authorization[7:].strip()
    parts = token.split(".")
    if len(parts) != 3:
        raise HTTPException(status_code=401, detail="Invalid bearer token")

    def decode(part: str) -> bytes:
        try:
            return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))
        except Exception as exc:
            raise HTTPException(status_code=401, detail="Invalid bearer token") from exc

    try:
        header = json.loads(decode(parts[0]))
        payload = json.loads(decode(parts[1]))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=401, detail="Invalid bearer token") from exc
    if header.get("alg") != "HS256":
        raise HTTPException(status_code=401, detail="Unsupported bearer token algorithm")
    expected = hmac.new(
        settings.auth_secret.encode("utf-8"),
        f"{parts[0]}.{parts[1]}".encode("ascii"),
        hashlib.sha256,
    ).digest()
    if not hmac.compare_digest(expected, decode(parts[2])):
        raise HTTPException(status_code=401, detail="Invalid bearer token signature")

    now = int(time.time())
    try:
        if payload.get("exp") is not None and int(payload["exp"]) <= now:
            raise HTTPException(status_code=401, detail="Bearer token expired")
        if payload.get("nbf") is not None and int(payload["nbf"]) > now + 30:
            raise HTTPException(status_code=401, detail="Bearer token is not active")
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Invalid bearer token claims") from exc
    if settings.auth_issuer and payload.get("iss") != settings.auth_issuer:
        raise HTTPException(status_code=401, detail="Bearer token issuer mismatch")
    if settings.auth_audience:
        audience = payload.get("aud")
        audiences = audience if isinstance(audience, list) else [audience]
        if settings.auth_audience not in audiences:
            raise HTTPException(status_code=401, detail="Bearer token audience mismatch")
    subject = str(payload.get("sub") or payload.get("user_id") or "").strip()
    if not subject or len(subject) > 255:
        raise HTTPException(status_code=401, detail="Bearer token has no valid subject")
    return subject


def current_user_id(request: Request) -> str | None:
    token_identity = _decode_bearer_user_id(request)
    header_value = request.headers.get("X-User-ID")
    header_identity = header_value.strip() if header_value and header_value.strip() else None
    if token_identity and header_identity and token_identity != header_identity:
        raise HTTPException(status_code=403, detail="User identity does not match bearer token")
    if token_identity:
        return token_identity
    if settings.debug or settings.auth_allow_unverified_user_header:
        return header_identity
    # An unsigned identity header is intentionally ignored in production.
    return None


def resolve_user_id(request: Request, requested: str | None = None) -> str | None:
    """Resolve an optional query/body identity without allowing spoofing.

    Development clients may still pass ``user_id`` explicitly, but once an
    authenticated ``X-User-ID`` is present it is authoritative for every
    memory operation.  This keeps SSE URLs and JSON requests from selecting a
    different user's profile.
    """
    identity = current_user_id(request)
    requested = requested.strip() if isinstance(requested, str) else requested
    if identity and requested and identity != requested:
        raise HTTPException(status_code=403, detail="User identity does not match authenticated user")
    if identity:
        return identity
    if requested:
        if not settings.debug:
            raise HTTPException(status_code=401, detail="X-User-ID is required")
        return requested
    return None


def require_authenticated(request: Request) -> str | None:
    """Require a verified identity outside the local debug workflow.

    GEPA and gateway routes do not have a resource ID in their URL, but they
    still expose durable execution data.  Reuse the same JWT/header policy so
    production callers cannot access those endpoints anonymously.
    """
    identity = current_user_id(request)
    if identity is None and not settings.debug:
        raise HTTPException(status_code=401, detail="X-User-ID or bearer token is required")
    return identity


def require_user_scope(request: Request) -> None:
    target = request.path_params.get("user_id")
    identity = current_user_id(request)
    if identity is None:
        if not settings.debug:
            raise HTTPException(status_code=401, detail="X-User-ID is required")
        return
    if target and identity != str(target):
        raise HTTPException(status_code=403, detail="User scope does not match authenticated user")


def require_resource_owner(
    request: Request,
    db: Session = Depends(get_db),
) -> None:
    identity = current_user_id(request)
    if identity is None:
        if not settings.debug:
            raise HTTPException(status_code=401, detail="X-User-ID is required")
        return
    project_id = request.path_params.get("project_id")
    session_id = request.path_params.get("session_id")
    asset_id = request.path_params.get("asset_id")
    job_id = request.path_params.get("job_id")
    project = None
    if project_id:
        project = db.query(Project).filter(Project.id == str(project_id)).first()
    elif session_id:
        session = db.query(DBSession).filter(DBSession.id == str(session_id)).first()
        project = session.project if session else None
    elif asset_id:
        asset = db.query(Asset).filter(Asset.id == str(asset_id)).first()
        project = asset.project if asset else None
    elif job_id:
        job = db.query(VideoJob).filter(VideoJob.id == str(job_id)).first()
        project = job.session.project if job and job.session else None
    if project is None:
        return  # let the endpoint return its normal 404
    owner = (project.metadata_ or {}).get("owner_user_id")
    if owner and owner != identity:
        raise HTTPException(status_code=403, detail="Resource belongs to another user")
    if not owner and not settings.debug:
        raise HTTPException(status_code=403, detail="Resource ownership is not established")


def bind_project_owner(project: Project, request: Request) -> None:
    """Attach the request identity to newly created projects when available."""
    identity = current_user_id(request)
    if identity:
        metadata = dict(project.metadata_ or {})
        metadata.setdefault("owner_user_id", identity)
        project.metadata_ = metadata
