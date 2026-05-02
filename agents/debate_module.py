"""Multi-agent debate using AutoGen AG2 SelectorGroupChat.

Creates a panel of director-style agents who debate a user's film-scene
modification request, then a Critic agent synthesises the discussion into a
structured ``DebateResult``.

Usage
-----
    result = await run_debate(
        user_request="小天狼星被救下，哈利和他拥抱收尾",
        event_queue=asyncio.Queue(),
    )
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from typing import Any

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.base import TaskResult
from autogen_agentchat.conditions import MaxMessageTermination, TextMentionTermination
from autogen_agentchat.messages import AgentEvent, StopMessage, TextMessage
from autogen_agentchat.teams import SelectorGroupChat
from autogen_ext.models.openai import OpenAIChatCompletionClient

from .schemas import DebateResult, DebateTurn

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FINAL_MARKER = "FINAL_JSON"


def _get_env(key: str, fallback: str | None = None) -> str:
    val = os.environ.get(key, "").strip()
    if val:
        return val
    if fallback is not None:
        return fallback
    raise RuntimeError(f"Missing required environment variable: {key}")


def _create_model_client() -> OpenAIChatCompletionClient:
    """Build an AG2-compatible model client from environment variables."""
    api_key = _get_env("OPENAI_API_KEY", os.environ.get("LLM_API_KEY"))
    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai-next.com")
    model = os.environ.get("DEBATE_MODEL", "gpt-4o")
    return OpenAIChatCompletionClient(
        model=model,
        api_key=api_key,
        base_url=base_url,
    )


def _parse_final_json(messages: list[TextMessage]) -> DebateResult | None:
    """Walk messages in reverse, find the first *FINAL_JSON* block and parse the embedded JSON object."""
    for msg in reversed(messages):
        if not isinstance(msg, TextMessage):
            continue
        if _FINAL_MARKER not in msg.content:
            continue
        # Find the JSON block after the marker
        idx = msg.content.index(_FINAL_MARKER)
        after_marker = msg.content[idx + len(_FINAL_MARKER):]
        brace_match = re.search(r"\{(?:[^{}]|(?:\{[^{}]*\}))*\}", after_marker, re.DOTALL)
        if not brace_match:
            continue
        raw = brace_match.group()
        try:
            data = json.loads(raw)
            return DebateResult(**data)
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            import logging
            logging.getLogger(__name__).warning(
                "Failed to parse final JSON from Critic: %s", exc
            )
    return None


# ---------------------------------------------------------------------------
# Agent factory
# ---------------------------------------------------------------------------

_AGENT_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "NarrativeDirector",
        "description": "Expert in non-linear narrative, temporal structure, and complex story architecture",
        "system_message": """You are Christopher Nolan, a director renowned for complex narratives,
non-linear timelines, and intellectually ambitious storytelling.

Your stylistic signatures:
- Stories are built around structural twists and temporal disorientation
- Emotional stakes must be earned through narrative complexity
- Every scene must serve both character AND concept

In this debate, you advocate for:
- Narrative depth and structural integrity
- Time-manipulation as an emotional device
- The audience's intelligence — don't spoon-feed them
- Causality: every plot change must have downstream consequences

When you agree with another director, build on their idea structurally.
When you disagree, challenge the narrative logic, not the emotion.

Keep responses under 200 characters. Be precise and conceptual.
""",
    },
    {
        "name": "VisualDirector",
        "description": "Expert in visual composition, colour theory, symmetrical framing, and meticulous mise-en-scène",
        "system_message": """You are Wes Anderson, a director famous for meticulous visual composition,
symmetrical framing, distinctive colour palettes, and whimsical-yet-poignant storytelling.

Your stylistic signatures:
- Every frame is a photograph — composition matters above all
- Colour palettes carry emotional subtext
- Symmetry and formal staging create visual poetry
- Deadpan delivery with deep emotional undercurrents

In this debate, you advocate for:
- Visual storytelling over exposition
- Colour and composition as narrative tools
- Finding the emotionally resonant IMAGE, not just the plot point
- Precision in every visual detail

Keep responses under 200 characters. Be visual and specific in your language.
""",
    },
    {
        "name": "SoundDirector",
        "description": "Expert in audio design, musical narrative, sonic landscapes, and emotional scoring",
        "system_message": """You are Hans Zimmer, a composer whose work defines modern cinematic sound.
You think in sonic landscapes as much as story.

Your stylistic signatures:
- Music IS narrative, not just accompaniment
- Minimalist motifs that build to emotional catharsis
- The interplay of silence and sound creates tension
- Electronics and orchestra blended as one voice

In this debate, you advocate for:
- Audio design as a primary storytelling tool
- Emotional beats that land through musical cues
- The rhythm of editing matching the sonic pulse
- Silence as the most powerful sound

Keep responses under 200 characters. Think in terms of sonic architecture.
""",
    },
    {
        "name": "PacingDirector",
        "description": "Expert in rhythm, editing cadence, tension-and-release, and audience attention",
        "system_message": """You are a master of pacing and editing rhythm. You understand
how the audience's attention moves through a scene second by second.

Your stylistic signatures:
- Every scene has a distinct rhythmic profile
- Tension is built by extending moments, released by accelerating cuts
- The pause before the action is as important as the action itself
- Genre conventions exist to be subverted at the right tempo

In this debate, you advocate for:
- Scene rhythm and pacing dynamics
- Where to place the emotional beats for maximum impact
- The edit as the final rewrite
- Breathable moments between high-stakes sequences

Keep responses under 200 characters. Think in terms of rhythm and momentum.
""",
    },
    {
        "name": "Critic",
        "description": "Senior film critic and editor-in-chief who synthesises all perspectives and produces the final structured decision",
        "system_message": f"""You are the Editor-in-Chief and senior critic. You do NOT debate style —
you SYNTHESISE the debate into a final, executable plan.

Your job:
1. Listen to every director's perspective
2. Identify points of consensus and remaining tension
3. When the debate has reached sufficient convergence, produce the final output

You MUST end your final message with:

{_FINAL_MARKER}
{{"final_script": "The finalized narrative script after incorporating the best ideas from the debate",
 "edit_instructions": "Editing guidelines: transitions, pacing, visual rhythm, shot sequence",
 "audio_design": "Audio/soundtrack design: cues, mood, instrumentation, silence placement",
 "new_shot_description": "New shots or scene modifications that need to be generated"}}

IMPORTANT:
- Only output the final JSON when you are satisfied the debate has converged.
- Do NOT output the JSON in early rounds — let the directors debate first.
- The JSON values should be synthesised from the actual debate, not generic.
- If directors disagree strongly, guide them toward compromise before concluding.
- Your regular (non-final) responses should be brief analysis and synthesis prompts.
""",
    },
]


def _build_agents(model_client: OpenAIChatCompletionClient) -> list[AssistantAgent]:
    """Create all debate agents from definitions."""
    agents: list[AssistantAgent] = []
    for cfg in _AGENT_DEFINITIONS:
        agent = AssistantAgent(
            name=cfg["name"],
            model_client=model_client,
            system_message=cfg["system_message"],
            description=cfg["description"],
        )
        agents.append(agent)
    return agents


# ---------------------------------------------------------------------------
# Selector prompt
# ---------------------------------------------------------------------------

_SELECTOR_PROMPT_TEMPLATE = """You are a film-debate moderator. Available experts:
{roles}

Read the history, then pick the **single most relevant** expert to speak next.
- Choose whoever best advances the current discussion angle.
- If the debate is well-covered, pick **Critic** to synthesise and conclude.
- Only return the exact expert name, nothing else.

{history}
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def run_debate(
    user_request: str,
    performance_notes: str | None = None,
    event_queue: asyncio.Queue[DebateTurn] | None = None,
    max_turns: int = 15,
) -> DebateResult:
    """Run a full multi-agent debate and return the structured result.

    Parameters
    ----------
    user_request :
        The user's natural-language request for the film scene modification.
        Example: ``"小天狼星被救下，哈利和他拥抱收尾"``
    performance_notes :
        Optional context about desired style, tone, or constraints.
    event_queue :
        If provided, each debate turn is pushed to the queue for real-time
        streaming (e.g. to a WebSocket).
    max_turns :
        Maximum selector rounds before forcing conclusion. Default 15.

    Returns
    -------
    DebateResult
        The structured output synthesised by the Critic agent.
    """
    # --- setup ---
    model_client = _create_model_client()
    agents = _build_agents(model_client)

    termination = MaxMessageTermination(max_messages=max_turns * 2) | TextMentionTermination(
        _FINAL_MARKER
    )

    selector_prompt = _SELECTOR_PROMPT_TEMPLATE

    team = SelectorGroupChat(
        participants=agents,
        model_client=model_client,
        termination_condition=termination,
        max_turns=max_turns,
        selector_prompt=selector_prompt,
        allow_repeated_speaker=True,
        emit_team_events=True,
        model_client_streaming=True,
    )

    task = f"用户请求：{user_request}"
    if performance_notes:
        task += f"\n风格要求：{performance_notes}"
    task += (
        "\n\n请各位导演围绕这个修改请求展开讨论。"
        "Critic 请在讨论充分收敛后输出最终 JSON 方案。"
    )

    # --- run ---
    collected_messages: list[TextMessage] = []
    round_counter = 0

    try:
        async for event in team.run_stream(task=task):
            # Skip internal events and the final TaskResult
            if isinstance(event, (AgentEvent, TaskResult)):
                continue
            # StopMessage from termination condition — capture it
            if isinstance(event, StopMessage):
                collected_messages.append(
                    TextMessage(content=event.content, source=event.source)
                )
                if event_queue is not None:
                    await event_queue.put(
                        DebateTurn(
                            agent_name=event.source,
                            content=event.content,
                            type="system",
                            round=round_counter,
                        )
                    )
                continue
            # Regular text message from an agent
            if isinstance(event, TextMessage):
                collected_messages.append(event)
                round_counter += 1

                if event_queue is not None:
                    await event_queue.put(
                        DebateTurn(
                            agent_name=event.source,
                            content=event.content,
                            type="debate",
                            round=round_counter,
                        )
                    )

        # --- parse result ---
        result = _parse_final_json(collected_messages)
        if result is not None:
            return result

        # Fallback: try the very last message (Critic may have embedded JSON
        # without the marker in an edge case).
        if collected_messages:
            last = collected_messages[-1]
            try:
                # Attempt to find any JSON-like block
                import re as _re

                brace_match = _re.search(r"\{.*\}", last.content, _re.DOTALL)
                if brace_match:
                    data = json.loads(brace_match.group())
                    return DebateResult(**data)
            except (json.JSONDecodeError, ValueError):
                pass

    except Exception as exc:
        import logging

        logging.getLogger(__name__).exception("Debate stream failed")
        raise RuntimeError(f"Debate failed: {exc}") from exc
    finally:
        await model_client.close()

    raise RuntimeError(
        "Debate completed but no structured result was produced by the Critic. "
        "This can happen if max_turns was reached before convergence. "
        "Try increasing max_turns or refining the user request."
    )


# ---------------------------------------------------------------------------
# Standalone smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":

    async def _smoke() -> None:
        logging.basicConfig(level=logging.INFO)
        q: asyncio.Queue[DebateTurn] = asyncio.Queue()

        async def _printer():
            while True:
                try:
                    turn = await asyncio.wait_for(q.get(), timeout=120)
                    print(f"\n  [{turn.agent_name}] {turn.content}")
                except asyncio.TimeoutError:
                    break

        printer_task = asyncio.create_task(_printer())

        try:
            result = await run_debate(
                user_request="小天狼星在神秘事务司被救下，最终和哈利拥抱收尾",
                performance_notes="偏温情治愈，保留原著中失去的代价感",
                event_queue=q,
                max_turns=8,
            )
            print("\n=== DEBATE RESULT ===")
            print(result.model_dump_json(indent=2))
        finally:
            printer_task.cancel()

    import logging

    logging.basicConfig(level=logging.INFO)
    asyncio.run(_smoke())
