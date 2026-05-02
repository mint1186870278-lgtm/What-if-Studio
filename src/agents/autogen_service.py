"""AutoGen multi-director discussion orchestration."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, AsyncGenerator
from src.config import settings

logger = logging.getLogger(__name__)

try:
    from autogen_agentchat.agents import AssistantAgent
    from autogen_agentchat.base import TaskResult
    from autogen_agentchat.conditions import MaxMessageTermination
    from autogen_agentchat.teams import RoundRobinGroupChat
    from autogen_core.models import ModelFamily
    from autogen_ext.models.openai import OpenAIChatCompletionClient

    AUTOGEN_AVAILABLE = True
except Exception as exc:  # pragma: no cover
    AUTOGEN_AVAILABLE = False
    AUTOGEN_IMPORT_ERROR = exc


def _infer_model_info(model_name: str) -> dict[str, Any] | None:
    """Return model_info for non-OpenAI-compatible model names."""
    name = (model_name or "").lower()
    openai_prefixes = ("gpt-", "o1", "o3", "o4")
    if name.startswith(openai_prefixes):
        return None
    # Compatible defaults for OpenAI-like gateways (DeepSeek, etc.)
    family = ModelFamily.R1 if "deepseek" in name and "r1" in name else ModelFamily.UNKNOWN
    return {
        "vision": False,
        "function_calling": False,
        "json_output": True,
        "structured_output": True,
        "family": family,
    }


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
                return {str(item.get("agentId")): item for item in raw if isinstance(item, dict) and item.get("agentId")}
    return {}


def _agent_label(agent_map: dict[str, dict[str, Any]], agent_id: str, default_name: str) -> str:
    item = agent_map.get(agent_id, {})
    return str(item.get("name") or default_name)


def _py_name(agent_id: str) -> str:
    return agent_id.replace("-", "_")


def _autogen_ready() -> bool:
    return AUTOGEN_AVAILABLE and bool(settings.openai_api_key)


def _model_client() -> "OpenAIChatCompletionClient":
    model_name = settings.openai_model or "gpt-4o-mini"
    base_url = settings.openai_base_url or "https://api.openai.com/v1"
    kwargs: dict[str, Any] = {
        "model": model_name,
        "api_key": settings.openai_api_key,
        "base_url": base_url,
        "temperature": 0.7,
        "max_tokens": 200,
    }
    model_info = _infer_model_info(model_name)
    if model_info is not None:
        kwargs["model_info"] = model_info
    return OpenAIChatCompletionClient(
        **kwargs,
    )


def _build_team() -> tuple[Any, Any]:
    client = _model_client()
    agent_map = _load_agent_catalog()

    narrative_id = "agent-yates"
    visual_id = "agent-columbus"
    sound_id = "agent-jackson"
    material_id = "agent-collector"
    critic_id = "agent-rowling"

    id_by_py_name = {
        _py_name(narrative_id): narrative_id,
        _py_name(visual_id): visual_id,
        _py_name(sound_id): sound_id,
        _py_name(material_id): material_id,
        _py_name(critic_id): critic_id,
    }

    participants = [
        AssistantAgent(
            name=_py_name(narrative_id),
            description=f"{_agent_label(agent_map, narrative_id, 'Narrative Director')} decides whether to join and focuses on story logic.",
            model_client=client,
            system_message=(
                "你是NarrativeDirector。开头必须说JOIN:或SKIP:。"
                "如果SKIP，说一句理由就结束。如果JOIN，每轮只说一句话（不超过50字）。必须用中文。"
            ),
            model_client_stream=True,
        ),
        AssistantAgent(
            name=_py_name(visual_id),
            description=f"{_agent_label(agent_map, visual_id, 'Visual Director')} focuses on editing, shot rhythm, and visual structure.",
            model_client=client,
            system_message=(
                "你是VisualDirector。开头必须说JOIN:或SKIP:。"
                "如果SKIP，说一句理由就结束。如果JOIN，每轮只说一句话（不超过50字）。必须用中文。"
            ),
            model_client_stream=True,
        ),
        AssistantAgent(
            name=_py_name(sound_id),
            description=f"{_agent_label(agent_map, sound_id, 'Sound Director')} focuses on audio, score, and sound design.",
            model_client=client,
            system_message=(
                "你是SoundDirector。开头必须说JOIN:或SKIP:。"
                "如果SKIP，说一句理由就结束。如果JOIN，每轮只说一句话（不超过50字）。必须用中文。"
            ),
            model_client_stream=True,
        ),
        AssistantAgent(
            name=_py_name(material_id),
            description=f"{_agent_label(agent_map, material_id, 'Material Director')} focuses on materials and asset selection.",
            model_client=client,
            system_message=(
                "你是MaterialDirector。开头必须说JOIN:或SKIP:。"
                "如果SKIP，说一句理由就结束。如果JOIN，每轮只说一句话（不超过50字）。必须用中文。"
            ),
            model_client_stream=True,
        ),
        AssistantAgent(
            name=_py_name(critic_id),
            description=f"{_agent_label(agent_map, critic_id, 'Critic')} synthesizes the debate into a final markdown script.",
            model_client=client,
            system_message=(
                "你是Critic。听取大家的意见后，用中文汇总一份Markdown脚本，包含editing、audio、materials三部分。"
                "最后用FINAL_JSON输出JSON对象，keys: final_script, edit_instructions, audio_design, material_selection, new_shot_description。"
            ),
            model_client_stream=True,
        ),
    ]
    termination = MaxMessageTermination(max_messages=10)
    team = RoundRobinGroupChat(
        participants=participants,
        termination_condition=termination,
    )
    return client, team, id_by_py_name


def _message_to_event(message: Any, id_by_py_name: dict[str, str] | None = None) -> dict[str, Any]:
    content = getattr(message, "content", "")
    source = getattr(message, "source", None) or getattr(message, "name", None) or "system"
    if id_by_py_name and isinstance(source, str):
        source = id_by_py_name.get(source, source)
    if not isinstance(content, str):
        content = json.dumps(content, ensure_ascii=False)
    return {
        "type": "turn",
        "speaker": source,
        "role": source,
        "content": _clean_content(content),
        "stage": "debate",
        "ts": int(asyncio.get_running_loop().time() * 1000),
    }


def _clean_content(content: str) -> str:
    """Remove thinking tags and leading English, keep only Chinese."""
    import re
    # Remove <think>...</think> blocks
    cleaned = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)
    # Remove leading English text before Chinese starts (e.g. "I think we should...方案是")
    cleaned = re.sub(r"^[A-Za-z,\s;:!.'\"()]+(?=[一-鿿])", "", cleaned)
    return cleaned.strip()


def _chunk_to_event(message: Any, id_by_py_name: dict[str, str] | None = None) -> dict[str, Any]:
    source = getattr(message, "source", None) or getattr(message, "name", None) or "system"
    if id_by_py_name and isinstance(source, str):
        source = id_by_py_name.get(source, source)
    content = getattr(message, "content", "")
    if not isinstance(content, str):
        content = str(content or "")
    return {
        "type": "turn_chunk",
        "speaker": source,
        "role": source,
        "content": _clean_content(content),
        "stage": "debate",
        "ts": int(asyncio.get_running_loop().time() * 1000),
    }


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


async def run_autogen_discussion_stream(
    user_request: str,
    style: str = "auto",
    performance_notes: str | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """Stream the multi-director discussion as JSON-ready events."""

    if not _autogen_ready():
        if not AUTOGEN_AVAILABLE:
            reason = f"autogen package not available: {repr(globals().get('AUTOGEN_IMPORT_ERROR', 'unknown'))}"
        else:
            reason = "OPENAI_API_KEY missing in loaded settings"
        raise RuntimeError(f"AutoGen discussion is unavailable: {reason}")

    client, team, id_by_py_name = _build_team()
    task = (
        f"User request: {user_request}\n"
        f"Style: {style}\n"
        f"Performance notes: {performance_notes or ''}\n\n"
        "Phase 1: each director says JOIN: or SKIP:.\n"
        "Phase 2: joined directors debate briefly.\n"
        "Phase 3: Critic writes a Markdown script and ends with FINAL_JSON.\n"
        "所有回答必须用中文。回答尽量简短。"
    )

    final_text = ""
    try:
        async for message in team.run_stream(task=task):  # type: ignore[arg-type]
            message_type = str(getattr(message, "type", ""))
            if message_type == "ModelClientStreamingChunkEvent":
                chunk_event = _chunk_to_event(message, id_by_py_name=id_by_py_name)
                if chunk_event.get("speaker") != "user" and chunk_event.get("content"):
                    yield chunk_event
                continue
            if isinstance(message, TaskResult):
                # Prefer the final Critic response; avoid falling back to the initial user prompt.
                critic_candidates = [
                    str(getattr(msg, "content", ""))
                    for msg in message.messages
                    if id_by_py_name.get(str(getattr(msg, "source", "") or getattr(msg, "name", "")), "") == "agent-rowling"
                    and getattr(msg, "content", None)
                ]
                if critic_candidates:
                    final_text = critic_candidates[-1]
                else:
                    final_text = "\n".join(
                        str(getattr(msg, "content", ""))
                        for msg in message.messages
                        if getattr(msg, "content", None)
                    )
                yield {
                    "type": "task_result",
                    "stop_reason": message.stop_reason,
                }
                continue
            event = _message_to_event(message, id_by_py_name=id_by_py_name)
            if event.get("speaker") == "user":
                continue
            yield event
            if "FINAL_JSON" in event.get("content", ""):
                final_text = event["content"]
    finally:
        await client.close()

    if not final_text:
        final_text = ""
    final = _parse_final_json(final_text)
    yield {
        "type": "script",
        "script": final.get("final_script", final_text),
        "final": final,
    }


async def run_autogen_discussion(
    user_request: str,
    style: str = "auto",
    performance_notes: str | None = None,
    event_queue: asyncio.Queue | None = None,
) -> dict[str, Any]:
    """Collect the stream into a single result object for API callers."""

    turns: list[dict[str, Any]] = []
    script = ""
    final: dict[str, Any] = {}

    async for event in run_autogen_discussion_stream(user_request, style=style, performance_notes=performance_notes):
        if event_queue is not None:
            await event_queue.put(event)
        if event.get("type") == "turn":
            turns.append(event)
        elif event.get("type") == "script":
            script = str(event.get("script", ""))
            final = dict(event.get("final", {}))

    return {
        "prompt": user_request,
        "style_preference": style,
        "performance_notes": performance_notes,
        "turns": turns,
        "script_markdown": script,
        "final": final,
        "status": "success",
    }


async def dispatch_autogen_service(
    service_name: str,
    payload: dict[str, Any],
    event_queue: asyncio.Queue | None = None,
) -> dict[str, Any]:
    """Route service calls to discussion-related AutoGen capabilities."""

    prompt = payload.get("prompt") or payload.get("user_request") or payload.get("text") or ""
    style = payload.get("style_preference") or payload.get("style") or "auto"
    performance_notes = payload.get("performance_notes")

    if service_name in {
        "autogen.discussion",
        "autogen-discussion",
        "autogen.director",
        "agent-director",
        "director",
    }:
        return await run_autogen_discussion(
            user_request=prompt,
            style=style,
            performance_notes=performance_notes,
            event_queue=event_queue,
        )

    if service_name in {"autogen.sound", "autogen-sound", "agent-composer", "composer"}:
        return {
            "service": service_name,
            "status": "ok",
            "audio_design": f"建议音轨: {style}，围绕'{prompt[:48]}'构建克制、递进的情绪层次。",
        }

    if service_name in {"autogen.edit", "autogen-edit", "agent-editor", "editor"}:
        return {
            "service": service_name,
            "status": "ok",
            "edit_instructions": f"编辑方向: {style} 风格；保留关键情节，减少跳切。",
        }

    return {
        "service": service_name,
        "status": "mocked",
        "message": "Unknown service_name; no local autogen service matched.",
        "payload": payload,
    }


# Backward-compatible aliases
run_debate_stream = run_autogen_discussion_stream
run_debate = run_autogen_discussion
dispatch_agent = dispatch_autogen_service
