"""Video job management API routes with SSE progress streaming"""

import asyncio
import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse, FileResponse
from sqlalchemy.orm import Session as DBSession
from pathlib import Path

from src.db import get_db, SessionLocal
from src.models import Session, VideoJob, Asset
from src.schemas import VideoJobCreate, VideoJobResponse
from src.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


async def process_video_job_background(
    job_id: str,
    session_id: str,
    asset_ids: list[str],
    image_url: str | None = None,
):
    """Background task to process video job through pipeline stages.

    Creates its own DB session to avoid sharing with the SSE generator.
    """
    db = SessionLocal()
    try:
        job = db.query(VideoJob).filter(VideoJob.id == job_id).first()
        if not job:
            logger.error("Job %s not found", job_id)
            return

        session = db.query(Session).filter(Session.id == session_id).first()
        if not session:
            logger.error("Session %s not found", session_id)
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

        # Create output path and generate video
        output_dir = settings.storage_projects_path / str(session.project_id) / "outputs"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(output_dir / f"{job_id}.mp4")

        try:
            from src.core.video_pipeline import generate_video_from_script
            # The prompt is the full director discussion script (what directors produced),
            # combined with any uploaded image for I2V reference.
            import re
            full_script = (session.script or "").strip()
            # Clean up: remove markdown headers and FINAL_JSON data
            script_clean = re.sub(r"^#+\s*", "", full_script, flags=re.MULTILINE)
            script_clean = re.sub(r"\s*FINAL_JSON\s*[\s\S]*", "", script_clean, flags=re.DOTALL)
            script_clean = script_clean.strip()
            # Use the full cleaned script as the prompt (truncated to a reasonable length)
            video_prompt = script_clean[:800] if script_clean else "生成一段视频"

            actual_path = await generate_video_from_script(
                session.script or "", output_path,
                prompt_override=video_prompt,
                image_url=image_url,
            )
            job.output_path = actual_path
            logger.info("✅ Video generated: %s", actual_path)
        except Exception as render_err:
            logger.error("Video generation failed: %s", render_err)
            # Still set output_path so the download endpoint can serve the file
            # (generate_video_from_script writes a placeholder on failure)
            if not job.output_path:
                job.output_path = output_path

        await asyncio.sleep(1)

        # Stage 6: Deliver
        job.phase = "deliver"
        job.status = "done"
        db.commit()

        logger.info("✅ Video job completed: %s", job_id)

    except Exception as e:
        logger.error("❌ Video job failed: %s", e)
        try:
            job.status = "failed"
            job.error = str(e)
            db.commit()
        except Exception:
            pass
    finally:
        db.close()


async def generate_video_progress_stream(
    job_id: str,
    session_id: str,
    asset_ids: list[str],
    db: DBSession,
    image_url: str | None = None,
) -> AsyncGenerator[str, None]:
    """Generate SSE stream for video job progress"""
    try:
        # Verify job exists before starting background task
        initial_job = db.query(VideoJob).filter(VideoJob.id == job_id).first()
        if not initial_job:
            yield f"data: {json.dumps({'error': 'Job not found'})}\n\n"
            return

        # Start background processing task with its own DB session
        task = asyncio.create_task(
            process_video_job_background(job_id, session_id, asset_ids, image_url)
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
            # Expire all cached objects to see background task's committed changes
            db.expire_all()
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

        # Check if the background task itself raised an unhandled exception
        try:
            exc = task.exception()
            if exc:
                logger.error("Background task crashed: %s", exc)
                event = {
                    "type": "error",
                    "status": "failed",
                    "error": str(exc),
                    "message": f"视频生成任务异常：{exc}",
                }
                yield f"data: {json.dumps(event)}\n\n"
                return
        except (asyncio.CancelledError, RuntimeError):
            pass

        # Get final job state
        db.expire_all()
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
                    "message": job.error or "视频生成失败",
                }
            yield f"data: {json.dumps(event)}\n\n"

        logger.info("✅ Video progress stream completed for job %s", job_id)

    except Exception as e:
        logger.error("❌ Video progress stream error: %s", e)
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
    image_url: str | None = None,
):
    """Stream video job progress as Server-Sent Events

    Query param ``image_url`` — optional reference image for I2V generation.
    """
    job = db.query(VideoJob).filter(VideoJob.id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )

    return StreamingResponse(
        generate_video_progress_stream(job_id, job.session_id, [], db, image_url=image_url),
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
