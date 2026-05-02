"""Pydantic schemas for the multi-agent pipeline."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class DebateTurn(BaseModel):
    """A single turn in the multi-agent debate."""

    agent_name: str = Field(description="Name of the speaking agent")
    content: str = Field(description="Message content")
    type: Literal["debate", "task_assignment", "production_update", "system", "video_progress"] = "debate"
    round: int = Field(default=0, description="Debate round number")
    metadata: dict[str, Any] = Field(default_factory=dict)


class DebateResult(BaseModel):
    """Structured output from the Critic agent after debate convergence."""

    final_script: str = Field(description="The finalized narrative script after debate")
    edit_instructions: str = Field(description="Editing guidelines: transitions, pacing, visual rhythm")
    audio_design: str = Field(description="Audio/soundtrack design: cues, mood, instrumentation")
    new_shot_description: str = Field(description="New shots or scene modifications to generate")


class ProductionState(BaseModel):
    """State passed through the LangGraph production workflow."""

    final_script: str = ""
    edit_instructions: str = ""
    audio_design: str = ""
    new_shot_description: str = ""
    material_urls: list[str] = Field(default_factory=list)
    t2v_prompts: list[str] = Field(default_factory=list)
    i2v_frames: list[str] = Field(default_factory=list)
    video_results: list[VideoResult] = Field(default_factory=list)
    error: str | None = None


class VideoResult(BaseModel):
    """Result of a single video generation task."""

    task_type: Literal["t2v", "i2v"] = "t2v"
    prompt: str = ""
    video_url: str = ""
    status: Literal["pending", "running", "completed", "failed"] = "pending"
    error: str | None = None


class PipelineResult(BaseModel):
    """Final output of the entire pipeline."""

    debate: DebateResult
    production: ProductionState
    videos: list[VideoResult] = Field(default_factory=list)
    status: Literal["success", "partial", "failed"] = "success"
    error: str | None = None
