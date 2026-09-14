"""SQLAlchemy ORM models"""

from datetime import datetime, timezone
from uuid import uuid4
import uuid
from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    Boolean,
    DateTime,
    Text,
    JSON,
    ForeignKey,
    Enum,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import relationship
import enum

from src.db import Base


def _utcnow() -> datetime:
    """Return a naive UTC timestamp for SQLAlchemy's DateTime columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Project(Base):
    """Video editing project"""

    __tablename__ = "projects"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)
    prompt = Column(Text, nullable=True)
    style_preference = Column(String(50), default="auto", nullable=False)
    script = Column(Text, nullable=True)
    discussion_history = Column(JSON, default=list, nullable=False)
    discussion_status = Column(String(50), default="idle", nullable=False)
    output_type = Column(String(50), default="script_only", nullable=False)
    storyboard = Column(JSON, default=None, nullable=True)
    last_opened_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_utcnow, nullable=False)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)
    metadata_ = Column(JSON, default=dict, nullable=False)  # Custom fields

    assets = relationship("Asset", back_populates="project", cascade="all, delete-orphan")
    sessions = relationship("Session", back_populates="project", cascade="all, delete-orphan")


class Asset(Base):
    """Project asset (video, audio, image, text)"""

    __tablename__ = "assets"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False, index=True)
    file_type = Column(String(50), nullable=False)  # 'video', 'audio', 'image', 'text'
    file_name = Column(String(255), nullable=False)
    file_path = Column(String(512), nullable=False, unique=True)
    file_size = Column(Integer, nullable=False)  # bytes
    metadata_ = Column(JSON, default=dict, nullable=False)  # resolution, duration, etc.
    created_at = Column(DateTime, default=_utcnow, nullable=False)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    project = relationship("Project", back_populates="assets")


class Session(Base):
    """Creative session for a project"""

    __tablename__ = "sessions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False, index=True)
    prompt = Column(Text, nullable=False)  # User's input prompt
    style_preference = Column(String(50), default="auto", nullable=False)
    status = Column(String(50), default="active", nullable=False)  # 'active', 'completed', 'failed'
    script = Column(Text, nullable=True)  # Markdown format script (initially empty)
    discussion_history = Column(JSON, default=list, nullable=False)  # List of DiscussionTurn
    created_at = Column(DateTime, default=_utcnow, nullable=False)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    project = relationship("Project", back_populates="sessions")
    video_jobs = relationship("VideoJob", back_populates="session", cascade="all, delete-orphan")


class VideoJob(Base):
    """Video generation task"""

    __tablename__ = "video_jobs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    session_id = Column(String(36), ForeignKey("sessions.id"), nullable=False, index=True)
    phase = Column(
        String(50),
        default="collect",
        nullable=False,
    )  # 'collect', 'analyze', 'discuss', 'edit', 'render', 'deliver'
    status = Column(String(50), default="pending", nullable=False)  # 'pending', 'running', 'done', 'failed'
    script = Column(Text, nullable=True)  # Markdown script
    output_path = Column(String(512), nullable=True)  # Final video file path
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_utcnow, nullable=False)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    session = relationship("Session", back_populates="video_jobs")


class ANetInvocation(Base):
    """ANet agent service invocation log"""

    __tablename__ = "anet_invocations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    service_name = Column(String(255), nullable=False, index=True)
    status = Column(String(50), nullable=False)  # 'pending', 'success', 'error'
    payload = Column(JSON, nullable=True)
    response = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=_utcnow, nullable=False, index=True)


# ---------------------------------------------------------------------------
# New models for refactored system (LangGraph + Memory)
# ---------------------------------------------------------------------------


class UserPreference(Base):
    """A versioned, evidence-backed user preference.

    The SQL row is the authoritative representation of a preference.  Mem0 is
    only used for semantic retrieval of historical cases and must never be
    treated as the source of truth for these fields.  ``scope`` deliberately
    distinguishes a one-off request from a durable preference so an explicit
    exception cannot silently overwrite a user's long-term profile.
    """

    __tablename__ = "user_preferences"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(255), nullable=False, index=True)
    preference_key = Column(String(255), nullable=False)
    preference_value = Column(Text, nullable=True)
    # global = durable preference; project/session/request are bounded
    # observations and must be considered only in that context.
    scope = Column(String(32), default="global", nullable=False, index=True)
    project_id = Column(String(36), nullable=True, index=True)
    session_id = Column(String(36), nullable=True, index=True)
    applicability_condition = Column(Text, nullable=True)
    evidence_source = Column(String(64), nullable=True)
    evidence_ref = Column(String(255), nullable=True)
    confidence = Column(Float, default=0.5, nullable=False)
    source = Column(String(50), default="user_expression", nullable=False)
    version = Column(Integer, default=1, nullable=False)
    status = Column(String(32), default="active", nullable=False, index=True)
    # Kept as an explicit flag for callers that do not want to interpret scope.
    is_long_term = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=_utcnow, nullable=False)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow, nullable=False)

    __table_args__ = (
        Index("ix_user_preferences_lookup", "user_id", "preference_key", "scope", "status"),
    )


class UserProfile(Base):
    """Structured long-term profile (the authoritative user record).

    Values are intentionally nullable: absence is different from a user
    explicitly choosing a value.  ``profile_data`` can hold provider-specific
    extensions while the three core dimensions remain queryable columns.
    """

    __tablename__ = "user_profiles"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(255), nullable=False, unique=True, index=True)
    ending_tendency = Column(String(128), nullable=True)
    emotional_style = Column(String(128), nullable=True)
    original_fidelity = Column(String(128), nullable=True)
    # Alias-friendly JSON for additional dimensions (e.g. pacing, dialogue).
    profile_data = Column(JSON, default=dict, nullable=False)
    version = Column(Integer, default=1, nullable=False)
    evidence_count = Column(Integer, default=0, nullable=False)
    last_evidence_source = Column(String(64), nullable=True)
    last_evidence_ref = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=_utcnow, nullable=False)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow, nullable=False)


class CreativeExperience(Base):
    """Incremental ACE-style experience handbook entry.

    Each entry has the shape ``applicable_condition → advice → user_evidence``
    and is revisionable/invalidatable without deleting history.
    """

    __tablename__ = "creative_experiences"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(255), nullable=False, index=True)
    applicable_condition = Column(Text, nullable=False)
    advice = Column(Text, nullable=False)
    user_evidence = Column(Text, nullable=False)
    evidence_source = Column(String(64), default="user_feedback", nullable=False)
    evidence_ref = Column(String(255), nullable=True)
    project_id = Column(String(36), nullable=True, index=True)
    session_id = Column(String(36), nullable=True, index=True)
    confidence = Column(Float, default=0.5, nullable=False)
    version = Column(Integer, default=1, nullable=False)
    status = Column(String(32), default="active", nullable=False, index=True)
    usage_count = Column(Integer, default=0, nullable=False)
    last_used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_utcnow, nullable=False)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow, nullable=False)

    __table_args__ = (
        Index("ix_creative_experiences_lookup", "user_id", "status"),
    )


# Public compatibility names used by the personalization layer and clients.
UserPreferenceObservation = UserPreference
ExperienceRecord = CreativeExperience


class ScriptVector(Base):
    """Metadata for scripts stored in Chroma vector DB."""

    __tablename__ = "script_vectors"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    chroma_doc_id = Column(String(255), nullable=False, unique=True, index=True)
    project_id = Column(String(36), nullable=True, index=True)
    user_id = Column(String(255), nullable=True, index=True)
    style = Column(String(50), nullable=True)
    prompt_hash = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=_utcnow, nullable=False)


class DiscussionCheckpoint(Base):
    """LangGraph discussion checkpoint metadata."""

    __tablename__ = "discussion_checkpoints"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    session_id = Column(String(36), nullable=False, index=True)
    thread_id = Column(String(255), nullable=False, unique=True, index=True)
    checkpoint_data = Column(JSON, nullable=False)  # Serialized LangGraph checkpoint
    status = Column(String(50), default="active")  # 'active', 'completed', 'interrupted'
    created_at = Column(DateTime, default=_utcnow, nullable=False)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)
