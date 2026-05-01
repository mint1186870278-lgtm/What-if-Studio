"""Project management API routes"""

import logging
from uuid import UUID
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.db import get_db
from src.models import Project, Asset, Session as DBSession
from src.schemas import ProjectCreate, ProjectUpdate, ProjectResponse

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
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )
    return project


@router.get("/projects", response_model=List[ProjectResponse])
async def list_projects(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    """List all projects with pagination"""
    projects = db.query(Project).offset(skip).limit(limit).all()
    return projects


@router.put("/projects/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: UUID,
    project_update: ProjectUpdate,
    db: Session = Depends(get_db),
):
    """Update project"""
    project = db.query(Project).filter(Project.id == project_id).first()
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
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project {project_id} not found",
            )

        # Delete associated sessions and assets
        db.query(Asset).filter(Asset.project_id == project_id).delete()
        db.query(DBSession).filter(DBSession.project_id == project_id).delete()

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
