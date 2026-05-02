"""Asset management API routes"""

import logging
import mimetypes
from pathlib import Path
from uuid import UUID
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from src.db import get_db
from src.models import Project, Asset
from src.schemas import AssetResponse
from src.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


async def extract_asset_metadata(file_path: str) -> dict:
    """Extract metadata from uploaded file"""
    metadata = {}
    file_size = Path(file_path).stat().st_size

    # Try to extract metadata based on file type
    # For now, just store basic info
    mime_type, _ = mimetypes.guess_type(file_path)
    if mime_type:
        metadata["mime_type"] = mime_type

    # TODO: Extract video duration, resolution using FFprobe
    # TODO: Extract image dimensions using PIL

    return metadata


@router.post("/projects/{project_id}/assets", response_model=AssetResponse, status_code=status.HTTP_201_CREATED)
async def upload_asset(
    project_id: UUID,
    file: UploadFile = File(...),
    asset_type: str = Form(...),
    db: Session = Depends(get_db),
):
    """Upload asset to project"""
    project_id_str = str(project_id)
    # Verify project exists
    project = db.query(Project).filter(Project.id == project_id_str).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )

    try:
        # Create project asset directory
        asset_dir = settings.storage_projects_path / project_id_str / "assets"
        asset_dir.mkdir(parents=True, exist_ok=True)

        # Save file
        file_name = file.filename or "unnamed"
        file_path = asset_dir / file_name
        file_content = await file.read()

        # Handle duplicate filenames
        if file_path.exists():
            base = file_path.stem
            ext = file_path.suffix
            counter = 1
            while file_path.exists():
                file_path = asset_dir / f"{base}_{counter}{ext}"
                counter += 1

        with open(file_path, "wb") as f:
            f.write(file_content)

        # Extract metadata
        metadata = await extract_asset_metadata(str(file_path))
        file_size = len(file_content)

        # Create asset record
        asset = Asset(
            project_id=project_id_str,
            file_type=asset_type,
            file_name=file_path.name,
            file_path=str(file_path.relative_to(settings.storage_projects_path)),
            file_size=file_size,
            metadata_=metadata,
        )
        db.add(asset)
        db.commit()
        db.refresh(asset)

        logger.info(f"✅ Asset uploaded: {asset.id} ({file_path.name})")
        return asset

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Failed to upload asset: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload asset: {str(e)}",
        )


@router.get("/projects/{project_id}/assets", response_model=List[AssetResponse])
async def list_project_assets(
    project_id: UUID,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    """List all assets in a project"""
    project_id_str = str(project_id)
    # Verify project exists
    project = db.query(Project).filter(Project.id == project_id_str).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )

    assets = (
        db.query(Asset)
        .filter(Asset.project_id == project_id_str)
        .offset(skip)
        .limit(limit)
        .all()
    )
    return assets


@router.get("/assets/{asset_id}", response_model=AssetResponse)
async def get_asset(
    asset_id: UUID,
    db: Session = Depends(get_db),
):
    """Get asset metadata"""
    asset = db.query(Asset).filter(Asset.id == str(asset_id)).first()
    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset {asset_id} not found",
        )
    return asset


@router.get("/assets/{asset_id}/download")
async def download_asset(
    asset_id: UUID,
    db: Session = Depends(get_db),
):
    """Download asset file"""
    asset = db.query(Asset).filter(Asset.id == str(asset_id)).first()
    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset {asset_id} not found",
        )

    file_path = settings.storage_projects_path / asset.file_path
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset file not found on disk",
        )

    return FileResponse(
        path=file_path,
        filename=asset.file_name,
        media_type="application/octet-stream",
    )


@router.delete("/assets/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_asset(
    asset_id: UUID,
    db: Session = Depends(get_db),
):
    """Delete asset"""
    try:
        asset = db.query(Asset).filter(Asset.id == str(asset_id)).first()
        if not asset:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Asset {asset_id} not found",
            )

        # Delete file from disk
        file_path = settings.storage_projects_path / asset.file_path
        if file_path.exists():
            file_path.unlink()

        # Delete record
        db.delete(asset)
        db.commit()

        logger.info(f"✅ Asset deleted: {asset_id}")
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Failed to delete asset: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete asset: {str(e)}",
        )
