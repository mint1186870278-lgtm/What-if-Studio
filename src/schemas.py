"""Pydantic schemas for request/response validation"""

from datetime import datetime
from typing import Optional, List, Any, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


# Project schemas
class ProjectCreate(BaseModel):
    """Create project request"""

    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    prompt: Optional[str] = None
    style_preference: Optional[str] = "auto"


class ProjectUpdate(BaseModel):
    """Update project request"""

    name: Optional[str] = None
    description: Optional[str] = None
    prompt: Optional[str] = None
    style_preference: Optional[str] = None
    output_type: Optional[str] = None


class ProjectResponse(BaseModel):
    """Project response"""

    id: UUID
    name: str
    description: Optional[str]
    prompt: Optional[str]
    style_preference: str
    script: Optional[str]
    discussion_history: List[Any]
    discussion_status: str
    output_type: str
    storyboard: Optional[dict] = None
    last_opened_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    metadata_: dict

    model_config = ConfigDict(from_attributes=True)


# Asset schemas
class AssetMetadata(BaseModel):
    """Asset metadata"""

    duration: Optional[float] = None  # For video/audio
    resolution: Optional[str] = None  # For video/image
    width: Optional[int] = None
    height: Optional[int] = None
    format: Optional[str] = None


class AssetResponse(BaseModel):
    """Asset response"""

    id: UUID
    project_id: UUID
    file_type: str
    file_name: str
    file_path: str
    file_size: int
    metadata_: dict
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# Session schemas
class DiscussionTurn(BaseModel):
    """Single turn in discussion"""

    speaker: str
    role: str  # 'guardian', 'director', 'crew'
    content: str
    stage: str  # 'briefing', 'topic-1', 'topic-2', 'topic-3', 'finalize'
    ts: int  # timestamp in ms


class SessionCreate(BaseModel):
    """Create session request"""

    project_id: str
    prompt: str = Field(..., min_length=1)
    style_preference: str = Field(default="auto")


class SessionResponse(BaseModel):
    """Session response"""

    id: UUID
    project_id: UUID
    prompt: str
    style_preference: str
    status: str
    script: Optional[str]
    # Lifecycle events such as awaiting_input/paused are persisted alongside
    # director turns so a refreshed client can reconstruct a resumable run.
    discussion_history: List[Any]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# VideoJob schemas
class VideoJobCreate(BaseModel):
    """Create video job request"""

    session_id: str
    asset_ids: List[str] = Field(default_factory=list)


class VideoJobResponse(BaseModel):
    """Video job response"""

    id: UUID
    session_id: UUID
    phase: str
    status: str
    script: Optional[str]
    output_path: Optional[str]
    error: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# Gateway schemas
class ANetInvocationResponse(BaseModel):
    """ANet invocation log response"""

    id: UUID
    service_name: str
    status: str
    payload: Optional[dict]
    response: Optional[dict]
    error: Optional[str]
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)


class GatewayCapability(BaseModel):
    """Gateway capability description"""

    name: str
    service_name: str
    description: str
    input_schema: dict
    output_schema: dict


class GatewayService(BaseModel):
    """Registered service in gateway"""

    name: str
    endpoint: str
    status: str  # 'active', 'inactive'
    tags: List[str]


# Feedback schemas
class FeedbackRequest(BaseModel):
    """Explicit user feedback on a discussion/script"""

    session_id: Optional[str] = None
    project_id: Optional[str] = None
    user_id: Optional[str] = None
    rating: int = Field(..., ge=1, le=5)
    comments: Optional[str] = None
    liked_aspects: List[str] = Field(default_factory=list)
    disliked_aspects: List[str] = Field(default_factory=list)


class FeedbackResponse(BaseModel):
    """Feedback acknowledgement"""

    status: str = "ok"
    message: str
    feedback_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Personalization / user memory schemas
# ---------------------------------------------------------------------------

class UserProfileResponse(BaseModel):
    """Authoritative structured long-term profile for one user."""

    id: UUID
    user_id: str
    ending_tendency: Optional[str] = None
    emotional_style: Optional[str] = None
    original_fidelity: Optional[str] = None
    profile_data: dict = Field(default_factory=dict)
    version: int = 1
    evidence_count: int = 0
    last_evidence_source: Optional[str] = None
    last_evidence_ref: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserProfileUpdate(BaseModel):
    """Explicit profile update; omitted fields are left unchanged."""

    ending_tendency: Optional[str] = None
    emotional_style: Optional[str] = None
    original_fidelity: Optional[str] = None
    profile_data: Optional[dict] = None
    evidence_source: str = "user_expression"
    evidence_ref: Optional[str] = None


class PreferenceObservationCreate(BaseModel):
    """A user-originated observation, never a generated-script inference."""

    key: str = Field(..., min_length=1, max_length=255)
    value: str = Field(..., min_length=1)
    scope: Literal["global", "project", "session", "request"] = "global"
    project_id: Optional[str] = None
    session_id: Optional[str] = None
    applicability_condition: Optional[str] = None
    source: Literal["user_expression", "user_choice", "user_edit", "explicit_feedback"] = "user_expression"
    evidence_ref: Optional[str] = None
    confidence: float = Field(default=0.8, ge=0, le=1)


class UserPreferenceResponse(BaseModel):
    id: UUID
    user_id: str
    preference_key: str
    preference_value: Optional[str] = None
    scope: str = "global"
    project_id: Optional[str] = None
    session_id: Optional[str] = None
    applicability_condition: Optional[str] = None
    evidence_source: Optional[str] = None
    evidence_ref: Optional[str] = None
    confidence: float = 0.5
    source: str = "user_expression"
    version: int = 1
    status: str = "active"
    is_long_term: bool = True
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ExperienceCreate(BaseModel):
    """ACE-style scene → advice → user evidence entry."""

    applicable_condition: str = Field(..., min_length=1)
    advice: str = Field(..., min_length=1)
    user_evidence: str = Field(..., min_length=1)
    evidence_source: Literal["user_expression", "user_choice", "user_edit", "explicit_feedback"] = "explicit_feedback"
    evidence_ref: Optional[str] = None
    project_id: Optional[str] = None
    session_id: Optional[str] = None
    confidence: float = Field(default=0.8, ge=0, le=1)


class ExperienceResponse(BaseModel):
    id: UUID
    user_id: str
    applicable_condition: str
    advice: str
    user_evidence: str
    evidence_source: str
    evidence_ref: Optional[str] = None
    project_id: Optional[str] = None
    session_id: Optional[str] = None
    confidence: float
    version: int
    status: str
    usage_count: int
    last_used_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# Output format selection
class OutputSelectRequest(BaseModel):
    """Request to set project output format preference"""

    output_type: str = Field(..., pattern=r"^(script_only|script_and_storyboard|script_and_video)$")


class StoryboardGenerateResponse(BaseModel):
    """Storyboard generation response"""

    project_id: str
    frames: list[dict]
    total_duration: str
    generated_at: Optional[datetime] = None


class StoryboardConfirmRequest(BaseModel):
    """Confirm or reject a storyboard"""

    confirmed: bool
    feedback: Optional[str] = None


class StoryboardConfirmResponse(BaseModel):
    """Response after storyboard confirmation"""

    status: str
    message: str
    job: Optional[dict] = None
    storyboard: Optional[dict] = None


class ScriptExportResponse(BaseModel):
    """Script export response"""

    project_id: str
    format: str
    content: str


class InterveneRequest(BaseModel):
    """Request to inject user intervention via REST"""

    text: str


class SessionResumeRequest(BaseModel):
    """Answer a native LangGraph interaction question.

    Clients have historically called intervention payloads ``text`` while
    the new interaction UI uses ``answer``/``selected_option``.  Accept all
    of these wire representations and normalize them at the API boundary so
    the graph always receives one plain string.
    """

    # ``Any`` is intentional: LangGraph's interrupt contract permits a JSON
    # answer object (for example ``{"selected_option": "更忠实原作"}``) as
    # well as a plain string.  The graph's answer node normalizes both forms.
    answer: Any = None
    text: Any = None
    selected_option: Any = None
    free_text: Any = None
    question_id: Optional[str] = None

    def resolved_answer(self) -> Any:
        for value in (self.answer, self.text, self.free_text, self.selected_option):
            if value is None:
                continue
            if isinstance(value, str):
                if value.strip():
                    return value.strip()
            elif value != "":
                return value
        return ""

# GEPA prompt optimisation schemas
class GEPACandidateCreate(BaseModel):
    strategy: str = Field(..., min_length=1, max_length=128)
    prompt_template: str = Field(..., min_length=1)
    model: Optional[str] = None
    budget: Optional[int] = Field(None, ge=1, le=1000)


class GEPAEvaluateRequest(BaseModel):
    cases: List[dict] = Field(default_factory=list)
    # Optional held-out set.  When ``independent`` is true this set is scored
    # instead of the training cases, while retaining backwards compatibility
    # for callers that only provide ``cases``.
    independent_cases: List[dict] = Field(default_factory=list)
    stage: Literal["profile_baseline", "experience", "optimized"] = "optimized"
    independent: bool = False


class GEPAProposalRequest(BaseModel):
    strategy: str = Field(..., min_length=1, max_length=128)
    cases: List[dict] = Field(default_factory=list)
    seed_prompt: Optional[str] = None
    model: Optional[str] = None
    budget: Optional[int] = Field(None, ge=1, le=1000)


class GEPAOptimizeRequest(GEPAProposalRequest):
    independent_cases: List[dict] = Field(default_factory=list)
    min_score: float = Field(0.7, ge=0, le=1)


class GEPAPublishRequest(BaseModel):
    min_score: float = Field(0.7, ge=0, le=1)
