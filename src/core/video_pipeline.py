"""Video processing pipeline with HappyHorse Video Edit (DashScope/Bailian).

Flow:
1. Submit a video + text prompt + optional reference images to HappyHorse.
2. Poll for task completion.
3. Download the edited video.

Falls back to ffmpeg text overlay when ``DASHSCOPE_API_KEY`` is not set.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# HappyHorse / DashScope client
# ---------------------------------------------------------------------------

_HAPPYHORSE_MODEL = "happyhorse-1.0-video-edit"
_DEFAULT_POLL_INTERVAL = 15.0
_MAX_POLL_ATTEMPTS = 60  # up to ~15 min


def _dashscope_key() -> str | None:
    key = settings.happyhorse_api_key or settings.openai_api_key
    return key if key else None


def _submit_url() -> str:
    base = settings.happyhorse_base_url or "https://dashscope.aliyuncs.com"
    return f"{base.rstrip('/')}/api/v1/services/aigc/video-generation/video-synthesis"


def _task_url(task_id: str) -> str:
    base = settings.happyhorse_base_url or "https://dashscope.aliyuncs.com"
    return f"{base.rstrip('/')}/api/v1/tasks/{task_id}"


async def _submit_happyhorse(
    prompt: str,
    video_url: str,
    reference_image_urls: list[str] | None = None,
) -> str:
    """Submit a HappyHorse video-edit job and return the task_id."""
    headers = {
        "Authorization": f"Bearer {_dashscope_key()}",
        "Content-Type": "application/json",
        "X-DashScope-Async": "enable",
    }
    media: list[dict[str, str]] = [{"type": "video", "url": video_url}]
    if reference_image_urls:
        for img_url in reference_image_urls[:5]:
            media.append({"type": "reference_image", "url": img_url})

    payload = {
        "model": _HAPPYHORSE_MODEL,
        "input": {
            "prompt": prompt,
            "media": media,
        },
        "parameters": {
            "resolution": "720P",
            "audio_setting": "origin",
        },
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            _submit_url(), headers=headers, json=payload, timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()

    task_id = data.get("output", {}).get("task_id")
    if not task_id:
        raise RuntimeError(f"HappyHorse submit returned no task_id: {data}")
    return str(task_id)


async def _poll_happyhorse(task_id: str) -> str:
    """Poll DashScope until the task completes and return the video URL."""
    headers = {
        "Authorization": f"Bearer {_dashscope_key()}",
    }

    for attempt in range(1, _MAX_POLL_ATTEMPTS + 1):
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    _task_url(task_id), headers=headers, timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()

            output = data.get("output") or {}
            status = str(output.get("task_status") or "").upper()
            logger.info("   poll[%d] status=%s", attempt, status)

            if status == "SUCCEEDED":
                video_url = output.get("video_url") or ""
                if video_url:
                    return video_url
                raise RuntimeError(f"HappyHorse done but no video_url: {data}")

            if status in ("FAILED", "CANCELED"):
                raise RuntimeError(
                    output.get("message")
                    or output.get("code")
                    or f"HappyHorse task {task_id} {status}"
                )

        except asyncio.CancelledError:
            logger.warning("   poll[%d] cancelled, retrying", attempt)
            await asyncio.sleep(_DEFAULT_POLL_INTERVAL)
            continue
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                await asyncio.sleep(_DEFAULT_POLL_INTERVAL)
                continue
            raise

        await asyncio.sleep(_DEFAULT_POLL_INTERVAL)

    raise TimeoutError(f"HappyHorse task {task_id} did not complete within timeout")


# ---------------------------------------------------------------------------
# ffmpeg fallback
# ---------------------------------------------------------------------------


def _generate_ffmpeg_video(prompt: str, script: str, output_path: str) -> str:
    """Render a playable MP4 with the script text using ffmpeg."""
    import subprocess as _sp
    import textwrap as _tw
    import tempfile

    display = prompt or (script[:300] if script else "意难平剧组")
    wrapped = _tw.fill(display, width=42)

    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
    try:
        tmp.write(wrapped)
        tmp.close()

        out = Path(output_path)
        duration = 20

        _sp.run(
            [
                "ffmpeg", "-y",
                "-f", "lavfi",
                "-i", f"color=c=#0d1117:s=1280x720:d={duration}:r=24",
                "-vf", (
                    f"drawtext=textfile={tmp.name}:"
                    f"fontsize=28:fontcolor=#c9d1d9:"
                    f"x=(w-tw)/2:y=(h-th)/2:"
                    f"fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:"
                    f"line_spacing=12,"
                    f"drawtext=text='意难平剧组':fontsize=14:fontcolor=#58a6ff:"
                    f"x=20:y=h-36"
                ),
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-preset", "fast", "-crf", "23",
                str(out),
            ],
            check=True, capture_output=True, timeout=60,
        )
        logger.info("✅ ffmpeg video saved to %s", output_path)
        return str(output_path)
    except Exception:
        raise
    finally:
        p = Path(tmp.name)
        if p.exists():
            p.unlink()


# ---------------------------------------------------------------------------
# Public rendering helper
# ---------------------------------------------------------------------------


async def generate_video_from_script(
    script: str,
    output_path: str,
    prompt_override: str | None = None,
    video_url: str | None = None,
    reference_image_urls: list[str] | None = None,
) -> str:
    """Generate / edit a video clip.

    1. If ``video_url`` is set and a DashScope API key is available,
       call HappyHorse Video Edit to transform the source clip.
    2. Otherwise render an ffmpeg text-overlay video.
    """
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    prompt = prompt_override or ""
    if not prompt:
        for line in script.splitlines():
            stripped = line.strip().strip("#").strip()
            if stripped:
                prompt = stripped[:500]
                break
    if not prompt:
        prompt = "意难平剧组场景"

    api_key = _dashscope_key()
    if api_key and video_url:
        logger.info("🎬 Submitting HappyHorse Video Edit job...")
        logger.info("   source video: %s", video_url[:80])
        try:
            task_id = await _submit_happyhorse(
                prompt, video_url, reference_image_urls=reference_image_urls,
            )
            logger.info("HappyHorse task submitted: %s", task_id[:12])
            result_url = await _poll_happyhorse(task_id)
            logger.info("HappyHorse completed, downloading from: %s", result_url[:60])

            async with httpx.AsyncClient() as client:
                resp = await client.get(result_url, timeout=300, follow_redirects=True)
                resp.raise_for_status()
                output.write_bytes(resp.content)

            logger.info("✅ Video saved to %s (%d bytes)", output_path, output.stat().st_size)
            return str(output_path)
        except asyncio.CancelledError:
            logger.warning("HappyHorse task was cancelled (client disconnected?)")
            raise
        except Exception as exc:
            logger.warning("HappyHorse failed (%s); falling back to ffmpeg", exc)
    else:
        if not api_key:
            logger.info("HAPPYHORSE_API_KEY not set — using ffmpeg fallback")
        if not video_url:
            logger.info("No source video — using ffmpeg text-overlay fallback")

    try:
        return _generate_ffmpeg_video(prompt, script, output_path)
    except Exception as ffmpeg_err:
        logger.warning("ffmpeg fallback also failed (%s); writing text placeholder", ffmpeg_err)
        output.write_bytes(f"Placeholder video for prompt: {prompt}\n".encode("utf-8"))
        return str(output_path)


async def call_seedance(
    api_url: str, script: str, assets: list[str], output_format: str = "mp4",
) -> str:
    """Legacy entry point — delegates to ``generate_video_from_script``."""
    output_path = settings.storage_temp_path / f"seedance_output.{output_format}"
    return await generate_video_from_script(script, str(output_path))


# ---------------------------------------------------------------------------
# Pipeline manager
# ---------------------------------------------------------------------------


class VideoPipelineManager:
    """Manager for video processing pipeline."""

    def __init__(self, seedance_api_url: str = ""):
        logger.info("🎬 VideoPipelineManager initialized (HappyHorse ready)")

    async def process_job(
        self, job_id: str, script: str, assets: list[str], video_url: str | None = None,
    ) -> str:
        logger.info("🎞️  Processing job: %s", job_id)
        output_path = settings.storage_temp_path / f"job_{job_id}.mp4"
        return await generate_video_from_script(
            script, str(output_path), video_url=video_url,
        )


video_pipeline = VideoPipelineManager()
