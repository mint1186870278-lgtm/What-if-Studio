"""AutoGen multi-director discussion orchestration."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, AsyncGenerator

logger = logging.getLogger(__name__)

try:
    from autogen_agentchat.agents import AssistantAgent
    from autogen_agentchat.base import TaskResult
    from autogen_agentchat.conditions import MaxMessageTermination, TextMentionTermination
    from autogen_agentchat.teams import SelectorGroupChat
    from autogen_ext.models.openai import OpenAIChatCompletionClient

    AUTOGEN_AVAILABLE = True
except Exception as exc:  # pragma: no cover
    AUTOGEN_AVAILABLE = False
    AUTOGEN_IMPORT_ERROR = exc

from src.core.discussion_engine import discussion_engine


def _autogen_ready() -> bool:
    return AUTOGEN_AVAILABLE and bool(os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY"))


def _model_client() -> "OpenAIChatCompletionClient":
    return OpenAIChatCompletionClient(
        model=os.getenv("AUTOGEN_MODEL", os.getenv("DEBATE_MODEL", "gpt-4o-mini")),
        api_key=os.getenv("OPENAI_API_KEY", os.getenv("LLM_API_KEY")),
        base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        temperature=0.7,
    )


def _build_team() -> tuple[Any, Any]:
    client = _model_client()
    participants = [
        AssistantAgent(
            name="NarrativeDirector",
            description="Decides whether to join and focuses on story logic.",
            model_client=client,
            system_message=(
                "You are the NarrativeDirector. First decide whether this topic interests you. "
                "If not, briefly decline. If yes, join the debate and focus on story logic, causality, "
                "and emotional payoff. Keep replies concise."
            ),
            model_client_stream=False,
        ),
        AssistantAgent(
            name="VisualDirector",
            description="Focuses on editing, shot rhythm, and visual structure.",
            model_client=client,
            system_message=(
                "You are the VisualDirector. First decide whether to join. If you join, debate the edit, "
                "shot rhythm, composition, and scene continuity. When the discussion turns to division of labor, "
                "own the editing part. Keep replies concise."
            ),
            model_client_stream=False,
        ),
        AssistantAgent(
            name="SoundDirector",
            description="Focuses on audio, score, and sound design.",
            model_client=client,
            system_message=(
                "You are the SoundDirector. First decide whether to join. If you join, debate audio design, "
                "score, silence, and emotional pacing. When the discussion turns to division of labor, "
                "own the audio part. Keep replies concise."
            ),
            model_client_stream=False,
        ),
        AssistantAgent(
            name="MaterialDirector",
            description="Focuses on materials and asset selection.",
            model_client=client,
            system_message=(
                "You are the MaterialDirector. First decide whether to join. If you join, debate what materials "
                "or assets are needed and which project assets should be selected. When the discussion turns to "
                "division of labor, own the material selection part. Keep replies concise."
            ),
            model_client_stream=False,
        ),
        AssistantAgent(
            name="Critic",
            description="Synthesizes the debate into a final markdown script.",
            model_client=client,
            system_message=(
                "You are the Critic. Synthesize the debate into one large Markdown script with three sections: "
                "editing, audio, and materials. End your final response with FINAL_JSON and a single JSON object "
                "with keys final_script, edit_instructions, audio_design, material_selection, new_shot_description."
            ),
            model_client_stream=False,
        ),
    ]
    selector_prompt = (
        "You are moderating a film discussion. Available participants:\n"
        "{roles}\n\n"
        "Conversation history:\n{history}\n\n"
        "Choose exactly one next speaker by name. Prefer the specialist best suited to the current phase. "
        "When the debate has converged, choose Critic."
    )
    termination = TextMentionTermination("FINAL_JSON") | MaxMessageTermination(max_messages=24)
    team = SelectorGroupChat(
        participants=participants,
        model_client=client,
        selector_prompt=selector_prompt,
        termination_condition=termination,
        allow_repeated_speaker=True,
    )
    return client, team


def _message_to_event(message: Any) -> dict[str, Any]:
    content = getattr(message, "content", "")
    source = getattr(message, "source", None) or getattr(message, "name", None) or "system"
    if not isinstance(content, str):
        content = json.dumps(content, ensure_ascii=False)
    return {
        "type": "turn",
        "speaker": source,
        "role": source,
        "content": content,
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
        turns, script = discussion_engine.generate_timeline(user_request, style)
        if performance_notes:
            script += f"\n\n## 性能备注\n{performance_notes}\n"
        for turn in turns:
            yield {
                "type": "turn",
                "speaker": turn.speaker,
                "role": turn.role,
                "content": turn.content,
                "stage": turn.stage,
                "ts": turn.ts,
            }
        yield {
            "type": "script",
            "script": script,
            "final": {
                "final_script": script,
                "edit_instructions": "",
                "audio_design": "",
                "material_selection": "",
                "new_shot_description": "",
            },
        }
        return

    client, team = _build_team()
    task = (
        f"User request: {user_request}\n"
        f"Style: {style}\n"
        f"Performance notes: {performance_notes or ''}\n\n"
        "Phase 1: each director decides whether they are interested and should join.\n"
        "Phase 2: joined directors debate the edit plan, sound plan, and materials.\n"
        "Phase 3: divide work into editing, audio, and material selection.\n"
        "Phase 4: Critic synthesizes everything into a single large Markdown script and ends with FINAL_JSON."
    )

    final_text = ""
    try:
        async for message in team.run_stream(task=task):  # type: ignore[arg-type]
            if isinstance(message, TaskResult):
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
            event = _message_to_event(message)
            yield event
            if "FINAL_JSON" in event.get("content", ""):
                final_text = event["content"]
    finally:
        await client.close()

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
