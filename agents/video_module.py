"""Video generation module — Wan2.2 models via SiliconFlow API.

Supports both T2V (text-to-video) and I2V (image-to-video) generation using
the SiliconFlow-compatible API endpoint.  All tasks are submitted asynchronously
and polled until completion.

Usage
-----
    url = await generate_video_t2v("A magical battle scene...")
    url = await generate_video_i2v("Continue this scene...", first_frame_url="https://...")
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Literal

import httpx

from .schemas import VideoResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_BASE_URL = "https://api.siliconflow.cn/v1"
_DEFAULT_TIMEOUT_S = 120  # per-request timeout
_DEFAULT_POLL_INTERVAL_S = 3.0
_MAX_POLL_ATTEMPTS = 120  # 120 × 3s = 6 minutes max
_T2V_MODEL = "Wan-AI/Wan2.2-T2V-A14B"
_I2V_MODEL = "Wan-AI/Wan2.2-I2V-A14B"


# ---------------------------------------------------------------------------
# Internal client
# ---------------------------------------------------------------------------


def _get_api_key() -> str:
    key = os.environ.get("SILICONFLOW_API_KEY", "").strip()
    if not key:
        key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "Missing SILICONFLOW_API_KEY (or fallback OPENAI_API_KEY) env var"
        )
    return key


def _get_base_url() -> str:
    return os.environ.get("SILICONFLOW_BASE_URL", _DEFAULT_BASE_URL).rstrip("/") + "/v1"


async def _submit_video_task(
    client: httpx.AsyncClient,
    model: str,
    prompt: str,
    first_frame_url: str | None = None,
    **extra: Any,
) -> str:
    """Submit an async video generation task and return the *request_id*."""
    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        **extra,
    }

    # I2V: pass the first-frame image
    if first_frame_url:
        # Some SiliconFlow endpoints accept the image in extra_body;
        # we pass it directly in the payload body.
        payload["first_frame_image"] = first_frame_url

    headers = {
        "Authorization": f"Bearer {_get_api_key()}",
        "Content-Type": "application/json",
    }

    response = await client.post(
        f"{_get_base_url()}/video/submit",
        headers=headers,
        json=payload,
        timeout=_DEFAULT_TIMEOUT_S,
    )
    response.raise_for_status()
    data = response.json()

    task_id = data.get("request_id") or data.get("task_id") or data.get("id")
    if not task_id:
        raise RuntimeError(
            f"SiliconFlow submit returned no task_id: {data}"
        )
    return str(task_id)


async def _poll_task(
    client: httpx.AsyncClient,
    request_id: str,
) -> dict[str, Any]:
    """Poll SiliconFlow task status until completion or failure."""
    headers = {
        "Authorization": f"Bearer {_get_api_key()}",
        "Content-Type": "application/json",
    }
    url = f"{_get_base_url()}/video/status"

    for attempt in range(1, _MAX_POLL_ATTEMPTS + 1):
        try:
            response = await client.get(
                url,
                headers=headers,
                params={"request_id": request_id},
                timeout=_DEFAULT_TIMEOUT_S,
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "Poll attempt %d/%d failed: %s",
                attempt,
                _MAX_POLL_ATTEMPTS,
                exc,
            )
            if attempt >= _MAX_POLL_ATTEMPTS:
                raise
            await asyncio.sleep(_DEFAULT_POLL_INTERVAL_S * 2)
            continue

        status: str = (data.get("status") or "running").lower()

        if status in ("succeeded", "completed", "done"):
            # Extract video URL — SiliconFlow returns it under various keys
            video_url = (
                data.get("video_url")
                or data.get("output")
                or data.get("result", {}).get("video_url")
                or ""
            )
            return {"status": "completed", "video_url": video_url, "raw": data}

        if status in ("failed", "error"):
            error_msg = (
                data.get("error")
                or data.get("message")
                or data.get("reason")
                or "Unknown error"
            )
            return {"status": "failed", "error": error_msg, "raw": data}

        # Still running — wait and retry
        await asyncio.sleep(_DEFAULT_POLL_INTERVAL_S)

    raise TimeoutError(
        f"Video task {request_id} did not complete within "
        f"{_MAX_POLL_ATTEMPTS * _DEFAULT_POLL_INTERVAL_S:.0f}s"
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def generate_video_t2v(
    prompt: str,
    event_queue: asyncio.Queue | None = None,
    size: str = "1280x720",
    duration: int = 5,
    **extra: Any,
) -> VideoResult:
    """Generate a video from a text prompt using Wan2.2-T2V (SiliconFlow).

    Parameters
    ----------
    prompt :
        Text description of the scene to generate.
    event_queue :
        Optional queue for progress events.
    size :
        Output video resolution (default ``1280x720``).
    duration :
        Target duration in seconds (default 5).

    Returns
    -------
    VideoResult
        Completed result with the video download URL.
    """
    result = VideoResult(task_type="t2v", prompt=prompt, status="pending")

    if event_queue is not None:
        await event_queue.put(_progress_event("video_progress", "T2V 任务已提交...", prompt))

    try:
        async with httpx.AsyncClient() as client:
            request_id = await _submit_video_task(
                client,
                model=_T2V_MODEL,
                prompt=prompt,
                size=size,
                duration=duration,
                **extra,
            )
            result.status = "running"

            if event_queue is not None:
                await event_queue.put(
                    _progress_event("video_progress", f"任务 {request_id[:8]}… 生成中", prompt)
                )

            poll_result = await _poll_task(client, request_id)

        result.status = "completed"
        result.video_url = poll_result.get("video_url", "")

        if event_queue is not None:
            await event_queue.put(
                _progress_event(
                    "video_progress",
                    f"视频生成完成: {result.video_url[:60] if result.video_url else 'empty'}",
                    prompt,
                )
            )

    except Exception as exc:
        result.status = "failed"
        result.error = str(exc)
        logger.exception("T2V generation failed for prompt: %.60s", prompt)

        if event_queue is not None:
            await event_queue.put(
                _progress_event("video_progress", f"T2V 失败: {exc}", prompt)
            )

    return result


async def generate_video_i2v(
    prompt: str,
    first_frame_url: str,
    event_queue: asyncio.Queue | None = None,
    size: str = "1280x720",
    duration: int = 5,
    **extra: Any,
) -> VideoResult:
    """Generate a video from a text prompt **conditioned on a first frame**
    using Wan2.2-I2V (SiliconFlow).

    Parameters
    ----------
    prompt :
        Text description of the scene continuation.
    first_frame_url :
        Publicly accessible URL of the image to use as the first frame
        (the conditioning image for I2V).
    event_queue :
        Optional queue for progress events.
    size :
        Output video resolution.
    duration :
        Target duration in seconds.

    Returns
    -------
    VideoResult
        Completed result with the video download URL.
    """
    result = VideoResult(task_type="i2v", prompt=prompt, status="pending")

    if event_queue is not None:
        await event_queue.put(
            _progress_event("video_progress", "I2V 任务已提交（首帧条件）...", prompt)
        )

    try:
        async with httpx.AsyncClient() as client:
            request_id = await _submit_video_task(
                client,
                model=_I2V_MODEL,
                prompt=prompt,
                first_frame_url=first_frame_url,
                size=size,
                duration=duration,
                **extra,
            )
            result.status = "running"

            if event_queue is not None:
                await event_queue.put(
                    _progress_event(
                        "video_progress",
                        f"I2V 任务 {request_id[:8]}… 生成中",
                        prompt,
                    )
                )

            poll_result = await _poll_task(client, request_id)

        result.status = "completed"
        result.video_url = poll_result.get("video_url", "")

        if event_queue is not None:
            await event_queue.put(
                _progress_event(
                    "video_progress",
                    f"I2V 视频生成完成",
                    prompt,
                )
            )

    except Exception as exc:
        result.status = "failed"
        result.error = str(exc)
        logger.exception("I2V generation failed for prompt: %.60s", prompt)

        if event_queue is not None:
            await event_queue.put(
                _progress_event("video_progress", f"I2V 失败: {exc}", prompt)
            )

    return result


async def generate_videos_batch(
    video_results: list[VideoResult],
    event_queue: asyncio.Queue | None = None,
    concurrency: int = 2,
) -> list[VideoResult]:
    """Execute multiple video generation tasks concurrently.

    Parameters
    ----------
    video_results :
        List of ``VideoResult`` objects with ``task_type`` and ``prompt`` set.
        I2V tasks must also have a prompt containing the frame URL.
    event_queue :
        Optional queue for progress events.
    concurrency :
        Maximum concurrent API calls (default 2 — SiliconFlow rate limits).

    Returns
    -------
    list[VideoResult]
        Completed results (status and video_url populated).
    """
    sem = asyncio.Semaphore(concurrency)

    async def _run_one(r: VideoResult) -> VideoResult:
        async with sem:
            if r.task_type == "i2v":
                # Extract frame URL from prompt — stored by final_aggregator
                frame_url = ""
                # The prompt format may contain the URL; otherwise material_urls
                return await generate_video_i2v(
                    prompt=r.prompt,
                    first_frame_url=frame_url,
                    event_queue=event_queue,
                )
            return await generate_video_t2v(
                prompt=r.prompt,
                event_queue=event_queue,
            )

    tasks = [_run_one(r) for r in video_results]
    return await asyncio.gather(*tasks)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _progress_event(type_: str, content: str, prompt: str) -> Any:
    from .schemas import DebateTurn

    return DebateTurn(
        agent_name="system",
        content=content,
        type=type_,
        metadata={"prompt": prompt[:80]},
    )
