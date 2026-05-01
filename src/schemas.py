"""Pydantic schemas for request/response validation"""

from datetime import datetime
from typing import Optional, List, Any
from uuid import UUID
from pydantic import BaseModel, Field


# Project schemas
class ProjectCreate(BaseModel):
    """Create project request"""

    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None


class ProjectUpdate(BaseModel):
    """Update project request"""

    name: Optional[str] = None
    description: Optional[str] = None


class ProjectResponse(BaseModel):
    """Project response"""

    id: UUID
    name: str
    description: Optional[str]
    created_at: datetime
    updated_at: datetime
    metadata_: dict

    class Config:
        from_attributes = True


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

    class Config:
        from_attributes = True


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
    discussion_history: List[DiscussionTurn]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


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

    class Config:
        from_attributes = True


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

    class Config:
        from_attributes = True


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
