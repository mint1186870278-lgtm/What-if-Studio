"""Project management API routes"""

import logging
import asyncio
from uuid import UUID
from typing import List
from datetime import datetime
import json

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from src.db import get_db
from src.models import Project, Asset
from src.schemas import ProjectCreate, ProjectUpdate, ProjectResponse
from src.agents import run_autogen_discussion_stream

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/projects", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    project_create: ProjectCreate,
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
            metadata_={},
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
    project.last_opened_at = datetime.utcnow()
    db.commit()
    db.refresh(project)
    return project


@router.get("/projects", response_model=List[ProjectResponse])
async def list_projects(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    """List all projects with pagination"""
    projects = (
        db.query(Project)
        .order_by(Project.last_opened_at.desc().nullslast(), Project.updated_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return projects


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

        db.query(Asset).filter(Asset.project_id == project_id_str).delete()

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


async def _prepare_project_stream(project: Project, db: Session):
    turns = []
    script = ""
    project.discussion_status = "running"
    db.commit()
    try:
        async for event in run_autogen_discussion_stream(
            user_request=project.prompt or "",
            style=project.style_preference or "auto",
        ):
            # Keep the API intentionally thin: frontend receives AutoGen events as-is.
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            if event.get("type") == "turn":
                turns.append(event)
            elif event.get("type") == "turn_chunk":
                turns.append(event)
            elif event.get("type") == "script":
                script = str(event.get("script", ""))

        project.discussion_history = turns
        project.script = script
        project.discussion_status = "completed"
        project.last_opened_at = datetime.utcnow()
        db.commit()
    except Exception as exc:
        project.discussion_status = "failed"
        db.commit()
        logger.exception("Project discussion failed: project_id=%s", project.id)
        yield f"data: {json.dumps({'type': 'error', 'message': str(exc)}, ensure_ascii=False)}\n\n"


@router.post("/{project_id}/prepare")
async def prepare_project(
    project_id: UUID,
    db: Session = Depends(get_db),
):
    project_id_str = str(project_id)
    project = db.query(Project).filter(Project.id == project_id_str).first()
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    if not (project.prompt or "").strip():
        raise HTTPException(status_code=400, detail="Project prompt is empty")
    return StreamingResponse(
        _prepare_project_stream(project, db),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _generate_project_stream(project: Project, db: Session):
    phases = [
        ("collect", "收集工程素材与剧本"),
        ("analyze", "分析镜头、声音和素材约束"),
        ("edit", "生成剪辑执行计划"),
        ("render", "等待视频生成服务接入位置"),
        ("deliver", "写入成片地址"),
    ]
    try:
        for index, (phase, message) in enumerate(phases, start=1):
            yield f"data: {json.dumps({'type': 'progress', 'event': 'progress', 'phase': phase, 'message': message, 'progress': index / len(phases)}, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0)

        project.product = f"/storage/projects/{project.id}/product.mp4"
        project.last_opened_at = datetime.utcnow()
        db.commit()
        yield f"data: {json.dumps({'type': 'complete', 'event': 'complete', 'phase': 'deliver', 'product': project.product, 'result': {'type': 'video-mp4-fallback', 'publicUrl': project.product}}, ensure_ascii=False)}\n\n"
    except Exception as exc:
        db.rollback()
        logger.exception("Project generation failed: project_id=%s", project.id)
        yield f"data: {json.dumps({'type': 'error', 'event': 'error', 'message': str(exc)}, ensure_ascii=False)}\n\n"


@router.post("/{project_id}/generate")
async def generate_project(
    project_id: UUID,
    db: Session = Depends(get_db),
):
    project_id_str = str(project_id)
    project = db.query(Project).filter(Project.id == project_id_str).first()
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    if not (project.script or "").strip():
        raise HTTPException(status_code=409, detail="Project script not generated yet")
    return StreamingResponse(
        _generate_project_stream(project, db),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
