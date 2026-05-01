"""Video job management API routes with SSE progress streaming"""

import asyncio
import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse, FileResponse
from sqlalchemy.orm import Session as DBSession
from pathlib import Path

from src.db import get_db
from src.models import Session, VideoJob, Asset
from src.schemas import VideoJobCreate, VideoJobResponse
from src.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


async def process_video_job_background(
    job_id: str,
    session_id: str,
    asset_ids: list[str],
    db: DBSession,
):
    """Background task to process video job through pipeline stages"""
    try:
        job = db.query(VideoJob).filter(VideoJob.id == job_id).first()
        if not job:
            logger.error(f"Job {job_id} not found")
            return

        session = db.query(Session).filter(Session.id == session_id).first()
        if not session:
            logger.error(f"Session {session_id} not found")
            return

        # Stage 1: Collect
        job.phase = "collect"
        job.status = "running"
        db.commit()
        await asyncio.sleep(1)

        # Stage 2: Analyze
        job.phase = "analyze"
        db.commit()
        await asyncio.sleep(1)

        # Stage 3: Discuss
        job.phase = "discuss"
        job.script = session.script  # Get script from session
        db.commit()
        await asyncio.sleep(1)

        # Stage 4: Edit
        job.phase = "edit"
        db.commit()
        await asyncio.sleep(1)

        # Stage 5: Render
        job.phase = "render"
        db.commit()
        await asyncio.sleep(2)

        # Stage 6: Deliver
        job.phase = "deliver"

        # Create output path
        output_dir = settings.storage_projects_path / str(session.project_id) / "outputs"
        output_dir.mkdir(parents=True, exist_ok=True)

        # For now, just store the placeholder path
        # In real implementation, would call Seedance API here
        output_path = str(output_dir / f"{job_id}.mp4")
        job.output_path = output_path

        job.status = "done"
        db.commit()

        logger.info(f"✅ Video job completed: {job_id}")

    except Exception as e:
        logger.error(f"❌ Video job failed: {e}")
        job.status = "failed"
        job.error = str(e)
        db.commit()


async def generate_video_progress_stream(
    job_id: str,
    session_id: str,
    asset_ids: list[str],
    db: DBSession,
) -> AsyncGenerator[str, None]:
    """Generate SSE stream for video job progress"""
    try:
        job = db.query(VideoJob).filter(VideoJob.id == job_id).first()
        if not job:
            yield f"data: {json.dumps({'error': 'Job not found'})}\n\n"
            return

        # Start background processing task
        task = asyncio.create_task(
            process_video_job_background(job_id, session_id, asset_ids, db)
        )

        # Stream progress events
        stages = [
            ("collect", "正在收集素材...", 10),
            ("analyze", "正在分析视频...", 20),
            ("discuss", "正在应用讨论建议...", 30),
            ("edit", "正在生成编辑脚本...", 50),
            ("render", "正在调用生成模型...", 75),
            ("deliver", "正在保存视频...", 100),
        ]

        completed_stages = set()

        while not task.done():
            job = db.query(VideoJob).filter(VideoJob.id == job_id).first()

            if job and job.phase not in completed_stages:
                # Find matching stage
                for phase, message, progress in stages:
                    if phase == job.phase:
                        completed_stages.add(phase)
                        event = {
                            "type": "progress",
                            "phase": phase,
                            "status": job.status,
                            "progress": progress,
                            "message": message,
                        }
                        yield f"data: {json.dumps(event)}\n\n"
                        break

            await asyncio.sleep(0.5)

        # Get final job state
        job = db.query(VideoJob).filter(VideoJob.id == job_id).first()
        if job:
            if job.status == "done":
                event = {
                    "type": "complete",
                    "status": "done",
                    "output_path": job.output_path,
                    "message": "视频生成完毕",
                }
            else:
                event = {
                    "type": "error",
                    "status": "failed",
                    "error": job.error,
                    "message": "视频生成失败",
                }
            yield f"data: {json.dumps(event)}\n\n"

        logger.info(f"✅ Video progress stream completed for job {job_id}")

    except Exception as e:
        logger.error(f"❌ Video progress stream error: {e}")
        yield f"data: {json.dumps({'error': str(e)})}\n\n"


@router.post("/video-jobs", response_model=VideoJobResponse, status_code=status.HTTP_201_CREATED)
async def create_video_job(
    job_create: VideoJobCreate,
    db: DBSession = Depends(get_db),
):
    """Create a new video job"""
    # Verify session exists
    session = db.query(Session).filter(Session.id == job_create.session_id).first()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {job_create.session_id} not found",
        )

    try:
        job = VideoJob(
            session_id=job_create.session_id,
            phase="collect",
            status="pending",
            script="",
            output_path=None,
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        logger.info(f"✅ Video job created: {job.id}")
        return job

    except Exception as e:
        db.rollback()
        logger.error(f"❌ Failed to create video job: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create video job: {str(e)}",
        )


@router.get("/video-jobs/{job_id}", response_model=VideoJobResponse)
async def get_video_job(
    job_id: str,
    db: DBSession = Depends(get_db),
):
    """Get video job by ID"""
    job = db.query(VideoJob).filter(VideoJob.id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )
    return job


@router.get("/video-jobs/{job_id}/events")
async def stream_video_progress(
    job_id: str,
    db: DBSession = Depends(get_db),
):
    """Stream video job progress as Server-Sent Events"""
    job = db.query(VideoJob).filter(VideoJob.id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )

    return StreamingResponse(
        generate_video_progress_stream(job_id, job.session_id, [], db),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/video-jobs/{job_id}/output")
async def download_video_output(
    job_id: str,
    db: DBSession = Depends(get_db),
):
    """Download completed video"""
    job = db.query(VideoJob).filter(VideoJob.id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )

    if not job.output_path or job.status != "done":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Video not ready for download",
        )

    file_path = Path(job.output_path)
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Output file not found",
        )

    return FileResponse(
        path=file_path,
        filename=f"{job_id}.mp4",
        media_type="video/mp4",
    )
