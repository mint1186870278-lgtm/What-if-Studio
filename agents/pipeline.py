"""Unified pipeline entry point.

Orchestrates:  **Debate** → **Workflow** → **Video generation**

Usage (WebSocket integration)
-----------------------------
.. code-block:: python

    import asyncio
    from agents import run_pipeline

    async def handler(websocket):
        await run_pipeline(
            user_request="小天狼星被救下，最终和哈利拥抱",
            materials={
                "performance_notes": "偏温情治愈，保留代价感",
                "material_urls": ["https://..."],
                "i2v_frames": ["https://..."],
            },
            send_event=websocket.send_json,
        )
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Coroutine

from .debate_module import run_debate
from .schemas import DebateResult, DebateTurn, PipelineResult, ProductionState, VideoResult
from .video_module import generate_videos_batch
from .workflow_module import run_workflow

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def run_pipeline(
    user_request: str,
    materials: dict[str, Any] | None = None,
    send_event: Callable[[dict[str, Any]], Coroutine[Any, Any, None]] | None = None,
    max_debate_turns: int = 5,
) -> PipelineResult:
    """Execute the full pipeline: debate → production workflow → video generation.

    Parameters
    ----------
    user_request :
        The user's natural-language scene modification request.
        Example: ``"小天狼星被救下，哈利和他拥抱收尾"``
    materials :
        Optional dict with keys:

        - ``performance_notes`` (str) – tone / style guidance for the debate
        - ``material_urls`` (list[str]) – reference URLs for the workflow
        - ``i2v_frames`` (list[str]) – image URLs for I2V conditioning
        - ``i2v_enabled`` (bool) – whether to use I2V (default ``False``)
    send_event :
        Async callable that receives a JSON-serialisable dict for each event.
        Designed to be hooked to ``websocket.send_json`` or an ``asyncio.Queue``.
        Each event has the shape::

            {"agent_name": "...", "content": "...", "type": "debate|task_assignment|...",
             "round": 0, "metadata": {}}
    max_debate_turns :
        Maximum debate selector rounds (default 15).

    Returns
    -------
    PipelineResult
        Aggregated result of all three pipeline stages.
    """
    materials = materials or {}
    performance_notes: str | None = materials.get("performance_notes")
    material_urls: list[str] = materials.get("material_urls", [])
    i2v_frames: list[str] = materials.get("i2v_frames", [])
    i2v_enabled: bool = materials.get("i2v_enabled", False)

    # Internal event queue — bridges debate/workflow/video modules to the
    # caller's ``send_event`` callback.
    internal_queue: asyncio.Queue[DebateTurn] = asyncio.Queue()
    bridge_task: asyncio.Task[None] | None = None

    async def _bridge() -> None:
        """Forward internal queue events to the caller's callback."""
        if send_event is None:
            return
        while True:
            try:
                turn = await asyncio.wait_for(internal_queue.get(), timeout=600)
                await send_event(turn.model_dump())
            except asyncio.TimeoutError:
                logger.warning("Event bridge timed out — stopping")
                break
            except Exception:
                logger.exception("Event bridge error")
                break

    async def _emit(type_: str, content: str, **meta: Any) -> None:
        await internal_queue.put(
            DebateTurn(
                agent_name="system",
                content=content,
                type=type_,  # type: ignore[arg-type]
                metadata=meta,
            )
        )

    # ───────────────────────────── Stage 1: Debate ──────────────────────────
    pipeline_start = time.monotonic()
    bridge_task = asyncio.create_task(_bridge())

    debate_result: DebateResult
    try:
        await _emit("system", "导演组集合，多轮辩论开始。", phase="debate")
        debate_result = await run_debate(
            user_request=user_request,
            performance_notes=performance_notes,
            event_queue=internal_queue,
            max_turns=max_debate_turns,
        )
        await _emit(
            "task_assignment",
            "辩论结束，Critic 已输出最终方案。",
            phase="debate_done",
            debate_summary=debate_result.model_dump(),
        )
    except Exception as exc:
        logger.exception("Debate stage failed")
        await _emit("system", f"辩论阶段失败: {exc}", phase="debate_failed", error=str(exc))
        if bridge_task:
            bridge_task.cancel()
        return PipelineResult(
            debate=DebateResult(
                final_script="",
                edit_instructions="",
                audio_design="",
                new_shot_description="",
            ),
            production=ProductionState(),
            status="failed",
            error=f"Debate failed: {exc}",
        )

    # ──────────────────────── Stage 2: Workflow ─────────────────────────
    production_state: ProductionState
    try:
        await _emit("system", "进入后期制作管线。", phase="workflow")
        production_state = await run_workflow(
            debate_result=debate_result,
            material_urls=material_urls,
            event_queue=internal_queue,
        )
        await _emit(
            "task_assignment",
            f"制作计划完成：{len(production_state.video_results)} 个视频任务待生成。",
            phase="workflow_done",
        )
    except Exception as exc:
        logger.exception("Workflow stage failed")
        await _emit("system", f"制作管线失败: {exc}", phase="workflow_failed", error=str(exc))
        if bridge_task:
            bridge_task.cancel()
        return PipelineResult(
            debate=debate_result,
            production=ProductionState(error=str(exc)),
            status="partial",
            error=f"Workflow failed: {exc}",
        )

    # ──────────────────── Stage 3: Video Generation ─────────────────────
    video_results: list[VideoResult] = []
    try:
        # Inject I2V frames if provided
        video_tasks = production_state.video_results
        if i2v_enabled and i2v_frames:
            # Add I2V tasks for the provided frames
            for frame_url in i2v_frames:
                video_tasks.append(
                    VideoResult(
                        task_type="i2v",
                        prompt=f"Animate scene from reference frame",
                        status="pending",
                    )
                )

        if video_tasks:
            await _emit(
                "system",
                f"开始 {len(video_tasks)} 个视频生成任务（并发 2）。",
                phase="video_gen",
            )
            video_results = await generate_videos_batch(
                video_results=video_tasks,
                event_queue=internal_queue,
                concurrency=2,
            )

            success_count = sum(1 for v in video_results if v.status == "completed")
            await _emit(
                "system",
                f"视频生成完成：{success_count}/{len(video_results)} 成功。",
                phase="video_gen_done",
                results=[v.model_dump() for v in video_results],
            )
        else:
            await _emit("system", "无视频任务需要生成。", phase="video_gen_skipped")

    except Exception as exc:
        logger.exception("Video generation stage failed")
        await _emit("system", f"视频生成失败: {exc}", phase="video_failed", error=str(exc))

    # ──────────────────────────── Finalise ─────────────────────────────
    duration_s = time.monotonic() - pipeline_start
    overall_status: str = "success"
    errors: list[str] = []

    if video_results:
        failed = [v for v in video_results if v.status == "failed"]
        if len(failed) == len(video_results):
            overall_status = "failed"
            errors.extend(f.error or "unknown error" for f in failed)
        elif failed:
            overall_status = "partial"
            errors.extend(f.error or "unknown error" for f in failed)

    if production_state.error:
        overall_status = "partial"
        errors.append(production_state.error)

    if bridge_task:
        bridge_task.cancel()

    await _emit(
        "system",
        f"管线结束，耗时 {duration_s:.0f}s，状态: {overall_status}",
        phase="pipeline_done",
        duration_s=round(duration_s, 1),
    )

    result = PipelineResult(
        debate=debate_result,
        production=production_state,
        videos=video_results,
        status=overall_status,  # type: ignore[arg-type]
        error="; ".join(errors) if errors else None,
    )
    return result
