"""LangGraph multi-director discussion orchestration.

Replaces AutoGen RoundRobinGroupChat with a LangGraph StateGraph that supports:
- Sequential director discussion with JOIN/SKIP gates
- Disagreement detection → automatic pause for user input
- Checkpoint persistence for pause/resume
- SSE-compatible streaming output (same event format as the AutoGen service)
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from pathlib import Path
from typing import Any, AsyncGenerator

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from src.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

class DiscussionState(dict):
    """Mutable state bag for the discussion graph."""
    pass


def _init_state(
    user_request: str,
    style: str = "auto",
    session_id: str = "",
    memory_context: str = "",
) -> dict[str, Any]:
    return {
        "messages": [],
        "session_id": session_id,
        "user_request": user_request,
        "style": style,
        "phase": "briefing",
        "directors_joined": [],
        "current_speaker": None,
        "script": "",
        "final_output": {},
        "disagreement_count": 0,
        "pending_user_question": None,
        "user_intervention": None,
        "turn_count": 0,
        "memory_context": memory_context,
    }


# ---------------------------------------------------------------------------
# Agent catalog loader
# ---------------------------------------------------------------------------

def _load_agent_catalog() -> dict[str, dict[str, Any]]:
    repo_root = Path(__file__).resolve().parents[2]
    candidates = [
        repo_root / "web" / "public" / "mock" / "agents.json",
        repo_root / "web" / "dist" / "mock" / "agents.json",
    ]
    for path in candidates:
        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, list):
                return {
                    str(item.get("agentId")): item
                    for item in raw
                    if isinstance(item, dict) and item.get("agentId")
                }
    return {}


def _agent_label(agent_map: dict[str, dict[str, Any]], agent_id: str, default_name: str) -> str:
    item = agent_map.get(agent_id, {})
    return str(item.get("name") or default_name)


# ---------------------------------------------------------------------------
# Director system prompts (Chinese, same personas as legacy AutoGen)
# ---------------------------------------------------------------------------

DIRECTOR_PROMPTS = {
    "narrative": (
        "你是NarrativeDirector（叙事导演）。你的职责是评判故事逻辑、角色动机和情节结构。"
        "开头必须说JOIN:或SKIP:。如果SKIP，说一句理由就结束。"
        "如果JOIN，每轮只说一句话（不超过100字）。必须用中文。"
        "聚焦：故事是否合理、情节推进是否有张力、角色行为是否有动机。"
    ),
    "visual": (
        "你是VisualDirector（视觉导演）。你的职责是镜头剪辑、画面节奏和视觉结构。"
        "开头必须说JOIN:或SKIP:。如果SKIP，说一句理由就结束。"
        "如果JOIN，每轮只说一句话（不超过100字）。必须用中文。"
        "聚焦：镜头语言、剪辑节奏、画面构图、色调氛围。"
    ),
    "sound": (
        "你是SoundDirector（声音导演）。你的职责是配乐、音效和声音设计。"
        "开头必须说JOIN:或SKIP:。如果SKIP，说一句理由就结束。"
        "如果JOIN，每轮只说一句话（不超过100字）。必须用中文。"
        "聚焦：配乐风格、音效层次、情绪铺陈、声音叙事。"
    ),
    "material": (
        "你是MaterialDirector（素材导演）。你的职责是素材选择和资产管理。"
        "开头必须说JOIN:或SKIP:。如果SKIP，说一句理由就结束。"
        "如果JOIN，每轮只说一句话（不超过100字）。必须用中文。"
        "聚焦：素材质量、风格统一、资产复用、技术可行性。"
    ),
    "critic": (
        "你是Critic（总评导演）。听取大家的意见后，用中文汇总一份Markdown脚本。"
        "包含editing、audio、materials三部分。"
        "最后用FINAL_JSON输出JSON对象，keys: final_script, edit_instructions, audio_design, material_selection, new_shot_description。"
        "所有回答必须用中文。回答尽量有深度，充分讨论后再给出结论。"
    ),
}

# Agent ID mapping
DIRECTOR_IDS = {
    "narrative": "agent-yates",
    "visual": "agent-columbus",
    "sound": "agent-jackson",
    "material": "agent-collector",
    "critic": "agent-rowling",
}


# ---------------------------------------------------------------------------
# LLM helper
# ---------------------------------------------------------------------------

def _get_llm(temp: float = 0.7, max_tokens: int = 500) -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.openai_model or "gpt-4o-mini",
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url or "https://api.openai.com/v1",
        temperature=temp,
        max_tokens=max_tokens,
        streaming=True,
    )


# ---------------------------------------------------------------------------
# Node implementations
# ---------------------------------------------------------------------------

async def _briefing_node(state: dict[str, Any]) -> dict[str, Any]:
    """Entry node — no LLM call, just set up the task."""
    state["phase"] = "briefing"
    state["turn_count"] = 0
    return state


def _build_director_node(role: str, agent_id: str) -> callable:
    """Factory for director nodes."""

    async def _node(state: dict[str, Any]) -> dict[str, Any]:
        agent_map = _load_agent_catalog()
        name = _agent_label(agent_map, agent_id, role)
        system_prompt = DIRECTOR_PROMPTS.get(role, DIRECTOR_PROMPTS["narrative"])

        llm = _get_llm()

        # Build conversation context
        context_parts = [f"用户需求：{state['user_request']}", f"风格：{state['style']}"]
        if state.get("memory_context"):
            context_parts.append(f"用户历史偏好：{state['memory_context']}")
        if state.get("user_intervention"):
            context_parts.append(f"用户介入意见：{state['user_intervention']}")
            state["user_intervention"] = None

        # Include previous turns
        prev_msgs = state.get("messages", [])
        if prev_msgs:
            context_parts.append("此前讨论：")
            for m in prev_msgs[-6:]:
                context_parts.append(f"[{m.get('speaker', '')}]: {m.get('content', '')}")

        context = "\n".join(context_parts)

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=context),
        ]

        full_response = ""
        async for chunk in llm.astream(messages):
            content = str(chunk.content) if hasattr(chunk, "content") and chunk.content else ""
            if content:
                full_response += content

        cleaned = _clean_content(full_response)
        speaker = agent_id
        ts = int(asyncio.get_running_loop().time() * 1000)

        # Append to messages
        state["messages"] = state.get("messages", []) + [{
            "speaker": speaker,
            "role": role,
            "content": cleaned,
            "stage": "debate",
            "ts": ts,
        }]

        # Track JOIN/SKIP
        if cleaned.upper().startswith("JOIN") and agent_id not in state.get("directors_joined", []):
            state["directors_joined"] = state.get("directors_joined", []) + [agent_id]
            # Also append to streaming events list
            state.setdefault("_events", []).append({
                "type": "turn",
                "speaker": speaker,
                "role": role,
                "content": cleaned,
                "stage": "debate",
                "ts": ts,
            })

        state["turn_count"] = state.get("turn_count", 0) + 1
        state["phase"] = "discussion"
        return state

    return _node


async def _disagreement_check_node(state: dict[str, Any]) -> dict[str, Any]:
    """Check for disagreement between directors. Set pending_user_question if threshold exceeded."""
    msgs = state.get("messages", [])
    if len(msgs) < 3:
        return state

    recent = msgs[-4:]
    disagreement_signals = 0
    for m in recent:
        content = str(m.get("content", ""))
        # Simple keyword-based disagreement detection
        if any(kw in content for kw in ["不同意", "反对", "但是", "然而", "我认为应该", "不建议"]):
            disagreement_signals += 1

    state["disagreement_count"] = state.get("disagreement_count", 0) + disagreement_signals

    if state["disagreement_count"] >= 2 and state.get("turn_count", 0) < 15:
        state["pending_user_question"] = (
            "导演们对创作方向存在不同意见。"
            f"当前讨论焦点：{recent[-1].get('content', '')[:150]}\n"
            "请问你倾向于哪种方向？请给出你的意见，或输入'继续'让导演们自行决定。"
        )
        state["phase"] = "awaiting_user"

    return state


async def _user_input_node(state: dict[str, Any]) -> dict[str, Any]:
    """Process user intervention."""
    intervention = state.get("user_intervention", "")
    if intervention and intervention.strip().lower() not in ("继续", "continue", "go on"):
        # Inject user input into conversation
        state["messages"] = state.get("messages", []) + [{
            "speaker": "user",
            "role": "user",
            "content": f"[用户意见] {intervention}",
            "stage": "user_input",
            "ts": int(asyncio.get_running_loop().time() * 1000),
        }]

    state["disagreement_count"] = 0
    state["pending_user_question"] = None
    state["phase"] = "discussion"
    return state


async def _critic_node(state: dict[str, Any]) -> dict[str, Any]:
    """Critic synthesizes all opinions into a final Markdown script."""
    agent_map = _load_agent_catalog()
    agent_id = DIRECTOR_IDS["critic"]
    name = _agent_label(agent_map, agent_id, "Critic")
    system_prompt = DIRECTOR_PROMPTS["critic"]

    llm = ChatOpenAI(
        model=settings.openai_model or "gpt-4o-mini",
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url or "https://api.openai.com/v1",
        temperature=0.5,
        max_tokens=2048,
        streaming=True,
    )

    prev_msgs = state.get("messages", [])
    discussion_text = "\n".join(
        f"[{m.get('speaker', '')}]: {m.get('content', '')}" for m in prev_msgs
    )

    context = (
        f"用户需求：{state['user_request']}\n"
        f"风格：{state['style']}\n"
        f"讨论记录：\n{discussion_text}\n\n"
        "请汇总为Markdown脚本，并以FINAL_JSON结尾。"
    )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=context),
    ]

    full_response = ""
    async for chunk in llm.astream(messages):
        content = str(chunk.content) if hasattr(chunk, "content") and chunk.content else ""
        if content:
            full_response += content

    cleaned = _clean_content(full_response)
    final = _parse_final_json(full_response)

    state["script"] = final.get("final_script", cleaned)
    state["final_output"] = final
    state["phase"] = "finalize"

    ts = int(asyncio.get_running_loop().time() * 1000)
    state.setdefault("_events", []).append({
        "type": "script",
        "script": state["script"],
        "final": final,
    })
    state["messages"] = state.get("messages", []) + [{
        "speaker": agent_id,
        "role": "critic",
        "content": cleaned,
        "stage": "finalize",
        "ts": ts,
    }]

    return state


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

_graph_instance: Any = None
_graph_checkpointer: Any = None


def build_discussion_graph() -> Any:
    """Build and compile the LangGraph discussion graph."""
    global _graph_instance, _graph_checkpointer

    if _graph_instance is not None:
        return _graph_instance

    workflow = StateGraph(dict)

    # Add nodes
    workflow.add_node("briefing", _briefing_node)
    workflow.add_node("narrative_director", _build_director_node("narrative", DIRECTOR_IDS["narrative"]))
    workflow.add_node("visual_director", _build_director_node("visual", DIRECTOR_IDS["visual"]))
    workflow.add_node("sound_director", _build_director_node("sound", DIRECTOR_IDS["sound"]))
    workflow.add_node("material_director", _build_director_node("material", DIRECTOR_IDS["material"]))
    workflow.add_node("disagreement_check", _disagreement_check_node)
    workflow.add_node("user_input", _user_input_node)
    workflow.add_node("critic", _critic_node)

    # Set entry
    workflow.set_entry_point("briefing")

    # Sequential discussion flow
    workflow.add_edge("briefing", "narrative_director")
    workflow.add_edge("narrative_director", "visual_director")
    workflow.add_edge("visual_director", "sound_director")
    workflow.add_edge("sound_director", "material_director")
    workflow.add_edge("material_director", "disagreement_check")

    # Conditional: ask user or finalize
    def _route_after_check(s: dict) -> str:
        if s.get("pending_user_question") and s.get("phase") == "awaiting_user":
            return "user_input"
        return "critic"

    workflow.add_conditional_edges("disagreement_check", _route_after_check, {
        "user_input": "user_input",
        "critic": "critic",
    })

    # After user input, loop back to the first director
    workflow.add_edge("user_input", "narrative_director")

    # Critic is terminal
    workflow.add_edge("critic", END)

    _graph_checkpointer = MemorySaver()
    _graph_instance = workflow.compile(checkpointer=_graph_checkpointer)
    logger.info("LangGraph discussion graph compiled")
    return _graph_instance


# ---------------------------------------------------------------------------
# Content cleaning (ported from legacy autogen_service)
# ---------------------------------------------------------------------------

def _clean_content(content: str) -> str:
    """Remove thinking tags, leading English, FINAL_JSON, markdown headers."""
    cleaned = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)
    cleaned = re.sub(r"^[A-Za-z,\s;:!.'\"()]+(?=[一-鿿])", "", cleaned)
    cleaned = re.sub(r"\s*FINAL_JSON\s*[\s\S]*", "", cleaned, flags=re.DOTALL)
    cleaned = re.sub(r"^#{1,6}\s+", "", cleaned, flags=re.MULTILINE)
    lines = [line.strip().lstrip("*-") for line in cleaned.split("\n")]
    cleaned = "\n".join(line for line in lines if line.strip())
    return cleaned.strip()


def _parse_final_json(text: str) -> dict[str, Any]:
    marker = "FINAL_JSON"
    if marker not in text:
        return {
            "final_script": text,
            "edit_instructions": "",
            "audio_design": "",
            "material_selection": "",
            "new_shot_description": "",
        }
    candidate = text.split(marker, 1)[-1].strip()
    try:
        return json.loads(candidate)
    except Exception:
        logger.warning("Failed to parse Critic FINAL_JSON payload")
        return {
            "final_script": text,
            "edit_instructions": "",
            "audio_design": "",
            "material_selection": "",
            "new_shot_description": "",
        }


# ---------------------------------------------------------------------------
# Streaming (SSE-compatible)
# ---------------------------------------------------------------------------

async def run_langgraph_discussion_stream(
    user_request: str,
    style: str = "auto",
    session_id: str | None = None,
    user_id: str | None = None,
    performance_notes: str | None = None,
    memory_context: str = "",
) -> AsyncGenerator[dict[str, Any], None]:
    """Stream a LangGraph discussion as SSE-compatible JSON events.

    Yields events in the SAME format as the legacy AutoGen service:
      {"type": "turn", "speaker": "...", "role": "...", "content": "...", "stage": "debate", "ts": ...}
      {"type": "script", "script": "...", "final": {...}}
      {"type": "task_result", "stop_reason": "..."}
    """

    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY missing — cannot run LangGraph discussion")

    sid = session_id or str(uuid.uuid4())
    graph = build_discussion_graph()

    # Inject memory context if available
    if user_id and not memory_context:
        try:
            from src.core.memory_service import memory_service
            memory_context = await memory_service.build_context_for_new_session(user_id, user_request)
        except Exception as exc:
            logger.debug("Memory context fetch skipped: %s", exc)

    initial_state = _init_state(
        user_request=user_request,
        style=style,
        session_id=sid,
        memory_context=memory_context,
    )
    if performance_notes:
        initial_state["user_request"] = f"{user_request}\n\nPerformance notes: {performance_notes}"

    config = {"configurable": {"thread_id": sid}}

    try:
        # Stream graph execution
        async for event in graph.astream(initial_state, config, stream_mode="values"):
            if not isinstance(event, dict):
                continue

            # Emit any turn events accumulated in _events
            for ev in event.get("_events", []):
                if ev.get("type") == "turn":
                    yield ev
                elif ev.get("type") == "script":
                    yield ev

            # If graph paused for user input
            if event.get("pending_user_question") and event.get("phase") == "awaiting_user":
                yield {
                    "type": "awaiting_input",
                    "question": event["pending_user_question"],
                    "session_id": sid,
                }
                # Try to get user input via WebSocket
                try:
                    from src.api.ws import wait_for_user_input
                    user_input = await wait_for_user_input(sid, event["pending_user_question"], timeout=120.0)
                    event["user_intervention"] = user_input
                    # Resume graph with user input
                    async for resume_event in graph.astream(
                        None, config, stream_mode="values",
                    ):
                        if isinstance(resume_event, dict):
                            for ev in resume_event.get("_events", []):
                                if ev.get("type") == "turn":
                                    yield ev
                                elif ev.get("type") == "script":
                                    yield ev
                            if resume_event.get("script"):
                                for ev in resume_event.get("_events", []):
                                    yield ev
                except Exception as exc:
                    logger.warning("User input wait failed: %s", exc)
                    event["pending_user_question"] = None
                    event["phase"] = "discussion"
                    # Continue without user input
                    async for resume_event in graph.astream(None, config, stream_mode="values"):
                        if isinstance(resume_event, dict):
                            for ev in resume_event.get("_events", []):
                                yield ev

            # If final output available
            if event.get("script") and event.get("phase") == "finalize":
                yield {
                    "type": "script",
                    "script": event["script"],
                    "final": event.get("final_output", {}),
                }
                yield {
                    "type": "task_result",
                    "stop_reason": "critic_finished",
                }

    except Exception as exc:
        logger.error("LangGraph discussion failed: %s", exc)
        yield {"type": "error", "message": str(exc)}


async def resume_langgraph_discussion_stream(
    session_id: str,
    user_input: str,
) -> AsyncGenerator[dict[str, Any], None]:
    """Manually resume a paused discussion with user input."""
    graph = build_discussion_graph()
    config = {"configurable": {"thread_id": session_id}}

    state = graph.get_state(config)
    if state is None:
        yield {"type": "error", "message": f"No checkpoint found for session {session_id}"}
        return

    current = dict(state.values)
    current["user_intervention"] = user_input
    current["pending_user_question"] = None

    try:
        async for event in graph.astream(current, config, stream_mode="values"):
            if isinstance(event, dict):
                for ev in event.get("_events", []):
                    yield ev
                if event.get("script"):
                    yield {
                        "type": "script",
                        "script": event["script"],
                        "final": event.get("final_output", {}),
                    }
                    yield {"type": "task_result", "stop_reason": "critic_finished"}
    except Exception as exc:
        logger.error("LangGraph resume failed: %s", exc)
        yield {"type": "error", "message": str(exc)}


async def get_discussion_state(session_id: str) -> dict[str, Any] | None:
    """Get current discussion state from checkpoint."""
    graph = build_discussion_graph()
    config = {"configurable": {"thread_id": session_id}}
    state = graph.get_state(config)
    if state is None:
        return None
    return dict(state.values)
