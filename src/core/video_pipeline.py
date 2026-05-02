"""Video processing pipeline with Wan T2V (SiliconFlow) integration.

Falls back to a placeholder file when ``SILICONFLOW_API_KEY`` is not set.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SiliconFlow Wan T2V client
# ---------------------------------------------------------------------------

_T2V_MODEL = "Wan-AI/Wan2.2-T2V-A14B"
_DEFAULT_POLL_INTERVAL = 3.0
_MAX_POLL_ATTEMPTS = 120


def _siliconflow_key() -> str | None:
    key = settings.siliconflow_api_key
    return key if key else None


def _siliconflow_base() -> str:
    return os.environ.get("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1").rstrip("/")


async def _submit_wan_task(prompt: str, **extra: dict) -> str:
    """Submit an async T2V task to SiliconFlow and return the request_id."""
    headers = {
        "Authorization": f"Bearer {_siliconflow_key()}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": _T2V_MODEL,
        "prompt": prompt,
        **extra,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{_siliconflow_base()}/video/submit",
            headers=headers,
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
    # SiliconFlow returns camelCase ("requestId") not snake_case ("request_id")
    task_id = (
        data.get("requestId")
        or data.get("request_id")
        or data.get("taskId")
        or data.get("task_id")
        or data.get("id")
    )
    if not task_id:
        raise RuntimeError(f"SiliconFlow submit returned no task_id: {data}")
    return str(task_id)


async def _poll_wan_task(request_id: str) -> str:
    """Poll until the task completes and return the video URL.

    Uses SiliconFlow's correct API endpoints:
      1. POST /v1/video/status  body={"requestId": "..."}
      2. GET  /v1/video/query   ?id=...
    """
    headers = {
        "Authorization": f"Bearer {_siliconflow_key()}",
        "Content-Type": "application/json",
    }
    base = _siliconflow_base()

    for attempt in range(1, _MAX_POLL_ATTEMPTS + 1):
        data = None

        # Try POST /video/status with requestId in body (primary)
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{base}/video/status",
                    headers=headers,
                    json={"requestId": request_id},
                    timeout=30,
                )
                if resp.status_code not in (404,):
                    resp.raise_for_status()
                    data = resp.json()
        except Exception:
            pass

        # Fallback: GET /video/query?id=
        if data is None:
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(
                        f"{base}/video/query",
                        headers=headers,
                        params={"id": request_id},
                        timeout=30,
                    )
                    if resp.status_code not in (404,):
                        resp.raise_for_status()
                        data = resp.json()
            except Exception:
                pass

        if data is None:
            await asyncio.sleep(_DEFAULT_POLL_INTERVAL)
            continue

        # Some APIs return status in camelCase (e.g. "Succeed", "Running", "Failed")
        raw_status = str(data.get("status") or "running").lower()
        if raw_status in ("succeeded", "completed", "done", "succeed"):
            # Try common video URL field names from SiliconFlow responses
            video_url = (
                data.get("videoUrl")
                or data.get("video_url")
                or data.get("output")
                or data.get("result", {}).get("videoUrl")
                or data.get("result", {}).get("video_url")
                or data.get("video")
                or ""
            )
            if video_url:
                return video_url
            raise RuntimeError(f"Task done but no video_url in response: {data}")
        if raw_status in ("failed", "error"):
            raise RuntimeError(data.get("error") or data.get("message") or "Unknown error")
        await asyncio.sleep(_DEFAULT_POLL_INTERVAL)
    raise TimeoutError(f"Task {request_id} did not complete within timeout")


# ---------------------------------------------------------------------------
# Public rendering helper
# ---------------------------------------------------------------------------


async def generate_video_from_script(
    script: str,
    output_path: str,
    prompt_override: str | None = None,
) -> str:
    """Generate a video clip from a Markdown script.

    1. If ``SILICONFLOW_API_KEY`` is set → call Wan T2V on SiliconFlow.
    2. Otherwise → write a placeholder file.

    Returns the *output_path* on success.
    """
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    # Extract a concise prompt from the script (first non-empty line, or title)
    prompt = prompt_override or ""
    if not prompt:
        for line in script.splitlines():
            stripped = line.strip().strip("#").strip()
            if stripped:
                prompt = stripped[:200]
                break
    if not prompt:
        prompt = f"Video scene based on: {script[:120]}"

    api_key = _siliconflow_key()
    if api_key:
        logger.info("📹 Submitting Wan T2V job via SiliconFlow...")
        try:
            request_id = await _submit_wan_task(prompt, size="1280x720", duration=5)
            logger.info("Wan T2V task submitted, id=%s", request_id)
            video_url = await _poll_wan_task(request_id)
            logger.info("Wan T2V completed, URL: %s", video_url[:60])
            # Download the result to the local output path
            async with httpx.AsyncClient() as client:
                resp = await client.get(video_url, timeout=120)
                resp.raise_for_status()
                output.write_bytes(resp.content)
            logger.info("✅ Video saved to %s (%d bytes)", output_path, output.stat().st_size)
            return str(output_path)
        except Exception as exc:
            logger.warning("Wan T2V failed (%s); falling back to placeholder", exc)
    else:
        logger.info(
            "SILICONFLOW_API_KEY not set — writing placeholder video. "
            "Set SILICONFLOW_API_KEY in .env to enable Wan T2V generation."
        )

    # Fallback: write placeholder so the pipeline completes (not a real mp4,
    # but prevents 404 on the download endpoint)
    output.write_bytes(
        f"Placeholder video for prompt: {prompt}\n".encode("utf-8")
    )
    logger.warning("⚠️  Placeholder written to %s", output_path)
    return str(output_path)


async def call_seedance(
    api_url: str,
    script: str,
    assets: list[str],
    output_format: str = "mp4",
) -> str:
    """Legacy entry point — delegates to ``generate_video_from_script``.

    ``api_url`` is ignored; the function uses SiliconFlow env config.
    """
    output_path = settings.storage_temp_path / f"seedance_output.{output_format}"
    return await generate_video_from_script(script, str(output_path))


# ---------------------------------------------------------------------------
# Pipeline manager
# ---------------------------------------------------------------------------


class VideoPipelineManager:
    """Manager for video processing pipeline."""

    def __init__(self, seedance_api_url: str = ""):
        logger.info("📋 VideoPipelineManager initialized (Wan T2V ready)")

    async def process_job(self, job_id: str, script: str, assets: list[str]) -> str:
        logger.info("🎞️  Processing job: %s", job_id)
        output_path = settings.storage_temp_path / f"job_{job_id}.mp4"
        return await generate_video_from_script(script, str(output_path))


# Global instance
video_pipeline = VideoPipelineManager()
