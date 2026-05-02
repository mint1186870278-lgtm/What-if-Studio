"""LangGraph production workflow: video editing, audio design, material scouting,
and final aggregation that decides T2V vs I2V generation path.

Each node is a stub function that can be replaced with real implementations.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Literal

from langgraph.graph import END, StateGraph

from .schemas import DebateResult, ProductionState, VideoResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Node implementations (stubs – replace with real logic)
# ---------------------------------------------------------------------------


def video_editor_node(state: ProductionState) -> dict[str, Any]:
    """Generate editing instructions from the final script."""
    logger.info("[video_editor] Generating editing plan...")
    script = state.final_script or ""
    edit_instructions = state.edit_instructions or ""

    # Stub: in production, this would call an LLM or editing rules engine
    t2v_prompts: list[str] = []
    if script:
        # Extract key visual moments from script for T2V generation
        t2v_prompts.append(f"Scene based on: {script[:200]}")

    return {
        "t2v_prompts": t2v_prompts,
        # edit_instructions already set from debate result
    }


def audio_designer_node(state: ProductionState) -> dict[str, Any]:
    """Generate audio cues and sound design specifications."""
    logger.info("[audio_designer] Composing audio landscape...")
    audio = state.audio_design or ""

    # Stub: would call an LLM or audio rules engine
    _ = audio  # placeholder

    return {
        # audio_design already set from debate result
    }


def material_scout_node(state: ProductionState) -> dict[str, Any]:
    """Scout for reference materials and source footage URLs."""
    logger.info("[material_scout] Scouting reference materials...")

    # Stub: would search a database or scrape the web
    material_urls = state.material_urls or []

    # Determine if we have image frames (I2V candidates)
    i2v_frames = state.i2v_frames or []

    return {
        "material_urls": material_urls,
        "i2v_frames": i2v_frames,
    }


def final_aggregator_node(state: ProductionState) -> dict[str, Any]:
    """Decide T2V vs I2V for each scene and record the plan.

    - If ``i2v_frames`` exist for a scene → use I2V (image-conditioned).
    - Otherwise → use T2V (text-only).
    """
    logger.info("[final_aggregator] Aggregating production plan...")

    t2v_prompts = state.t2v_prompts or []
    i2v_frames = state.i2v_frames or []
    video_results: list[VideoResult] = []

    # Plan T2V tasks for text-only scenes
    for prompt in t2v_prompts:
        video_results.append(
            VideoResult(
                task_type="t2v",
                prompt=prompt,
                status="pending",
            )
        )

    # Plan I2V tasks for scenes with reference frames
    for frame_url in i2v_frames:
        video_results.append(
            VideoResult(
                task_type="i2v",
                prompt=f"Animate from reference frame: {frame_url}",
                status="pending",
            )
        )

    # If nothing was planned, create a default T2V job from the script
    if not video_results and state.final_script:
        video_results.append(
            VideoResult(
                task_type="t2v",
                prompt=state.final_script[:300],
                status="pending",
            )
        )

    return {
        "video_results": video_results,
    }


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------


def build_workflow() -> StateGraph:
    """Build the LangGraph production workflow.

    Returns
    -------
    StateGraph
        The compiled workflow, ready to ``ainvoke()``.
    """
    builder = StateGraph(ProductionState)

    # Add nodes
    builder.add_node("video_editor", video_editor_node)
    builder.add_node("audio_designer", audio_designer_node)
    builder.add_node("material_scout", material_scout_node)
    builder.add_node("final_aggregator", final_aggregator_node)

    # Define edges
    builder.set_entry_point("video_editor")
    builder.add_edge("video_editor", "audio_designer")
    builder.add_edge("audio_designer", "material_scout")
    builder.add_edge("material_scout", "final_aggregator")
    builder.add_edge("final_aggregator", END)

    return builder.compile()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_compiled_workflow = build_workflow()


async def run_workflow(
    debate_result: DebateResult,
    material_urls: list[str] | None = None,
    event_queue: asyncio.Queue | None = None,
) -> ProductionState:
    """Execute the production workflow after a debate concludes.

    Parameters
    ----------
    debate_result :
        Structured output from the debate phase.
    material_urls :
        Optional pre-existing material URLs to inject into the workflow.
    event_queue :
        If provided, ``production_update`` events are pushed for streaming.

    Returns
    -------
    ProductionState
        Final production state including video task plans.
    """
    initial_state = ProductionState(
        final_script=debate_result.final_script,
        edit_instructions=debate_result.edit_instructions,
        audio_design=debate_result.audio_design,
        new_shot_description=debate_result.new_shot_description,
        material_urls=material_urls or [],
    )

    if event_queue is not None:
        await event_queue.put(
            _make_event("system", "进入后期制作管线。", metadata={"phase": "workflow"})
        )

    try:
        result: ProductionState = await _compiled_workflow.ainvoke(initial_state)

        if event_queue is not None:
            await event_queue.put(
                _make_event(
                    "production_update",
                    f"制作计划完成：{len(result.video_results)} 个视频任务待生成。",
                    metadata={
                        "phase": "workflow_done",
                        "t2v_count": sum(
                            1 for v in result.video_results if v.task_type == "t2v"
                        ),
                        "i2v_count": sum(
                            1 for v in result.video_results if v.task_type == "i2v"
                        ),
                    },
                )
            )

        return result

    except Exception as exc:
        logger.exception("Workflow failed")
        raise RuntimeError(f"Production workflow failed: {exc}") from exc


def _make_event(
    type_: str,
    content: str,
    metadata: dict[str, Any] | None = None,
) -> Any:
    """Create an event object compatible with the pipeline's event queue."""
    from .schemas import DebateTurn

    return DebateTurn(
        agent_name="system",
        content=content,
        type=type_,  # type: ignore[arg-type]
        metadata=metadata or {},
    )
