"""Pydantic schemas for request/response validation"""

from datetime import datetime
from typing import Optional, List, Any
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


class ProjectResponse(BaseModel):
    """Project response"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: Optional[str]
    prompt: Optional[str]
    style_preference: str
    script: Optional[str]
    product: Optional[str] = None
    discussion_history: List[Any]
    discussion_status: str
    last_opened_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    metadata_: dict


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
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    file_type: str
    asset_type: str
    file_name: str
    file_path: str
    url: str
    file_size: int
    metadata_: dict
    created_at: datetime
    updated_at: datetime

