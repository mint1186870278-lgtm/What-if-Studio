"""LangGraph multi-director discussion orchestration.

Replaces AutoGen RoundRobinGroupChat with a LangGraph StateGraph that supports:
- Sequential director discussion with JOIN/SKIP gates
- Disagreement detection → automatic pause for user input
- Checkpoint persistence for pause/resume
- SSE-compatible streaming output (same event format as the AutoGen service)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import sqlite3
import threading
import uuid
from pathlib import Path
from typing import Any, AsyncGenerator, Literal

from pydantic import BaseModel, Field, ValidationError

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command, interrupt
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from src.config import settings

logger = logging.getLogger(__name__)


def _resolve_llm_config() -> dict[str, str]:
    """Return {'api_key': ..., 'base_url': ..., 'model': ...} from the first available provider.

    An explicitly configured OpenAI-compatible endpoint takes precedence.
    This allows gateways such as OpenAI Next to expose DeepSeek models while a
    separate native ``DEEPSEEK_API_KEY`` remains present in the environment.
    Native DeepSeek is kept as the fallback when no primary endpoint is set.
    """
    if settings.openai_api_key:
        return {
            "api_key": settings.openai_api_key,
            "base_url": settings.openai_base_url or "https://api.openai.com/v1",
            "model": settings.openai_model or "gpt-4o-mini",
        }
    if settings.deepseek_api_key:
        return {
            "api_key": settings.deepseek_api_key,
            "base_url": settings.deepseek_base_url,
            "model": os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
        }
    if settings.siliconflow_api_key:
        return {
            "api_key": settings.siliconflow_api_key,
            "base_url": settings.siliconflow_base_url,
            "model": os.getenv("SILICONFLOW_MODEL", "Qwen/Qwen2.5-7B-Instruct"),
        }
    if settings.zhipu_api_key:
        return {
            "api_key": settings.zhipu_api_key,
            "base_url": settings.zhipu_base_url,
            "model": os.getenv("ZHIPU_MODEL", "glm-4-flash"),
        }
    raise RuntimeError(
        "No LLM provider configured. Set one of: DEEPSEEK_API_KEY, OPENAI_API_KEY, "
        "SILICONFLOW_API_KEY, or ZHIPU_API_KEY in your .env file."
    )

# ---------------------------------------------------------------------------
# Module-level streaming queue (avoids putting non-serializable objects
# into LangGraph state, which would break msgpack checkpointing).
# ---------------------------------------------------------------------------

_stream_queue: asyncio.Queue | None = None
# A process can have several discussions open at the same time.  Keeping the
# queue keyed by the graph thread avoids one user's tokens being delivered to
# another user's SSE connection.  ``_stream_queue`` remains as a compatibility
# fallback for tests which call node functions directly.
_stream_queues: dict[str, asyncio.Queue] = {}

# ``MemorySaver`` was used by the first refactor and silently lost a paused
# graph whenever the worker restarted.  The sqlite saver is deliberately kept
# open for the life of the process so native LangGraph interrupts can be
# resumed by a later HTTP request (and survive a process restart).
_checkpoint_conn: sqlite3.Connection | None = None


class _AsyncSqliteSaver(BaseCheckpointSaver):
    """Small async facade over ``langgraph-checkpoint-sqlite``.

    The package's synchronous ``SqliteSaver`` is useful for imperative graph
    calls, but LangGraph's ``astream`` uses the async saver methods.  The
    official async saver owns an ``aiosqlite`` context manager, which is hard
    to keep alive across FastAPI/TestClient event loops.  This facade keeps one
    SQLite connection open and moves the short, transactional operations to a
    worker thread.  It therefore gives us durable checkpoints without making
    the graph runner block the event loop.
    """

    def __init__(self, saver: Any):
        super().__init__(serde=saver.serde)
        self._saver = saver
        self._lock = threading.RLock()

    def _sync_call(self, method: str, *args: Any, **kwargs: Any) -> Any:
        # SqliteSaver uses one process-wide connection.  Serialising the tiny
        # checkpoint transactions prevents concurrent sessions from colliding
        # on SQLite's implicit transaction state.
        with self._lock:
            return getattr(self._saver, method)(*args, **kwargs)

    @property
    def config_specs(self):
        return self._saver.config_specs

    async def aget_tuple(self, config):
        return await asyncio.to_thread(self._sync_call, "get_tuple", config)

    async def aget(self, config):
        return await asyncio.to_thread(self._sync_call, "get", config)

    async def aput(self, config, checkpoint, metadata, new_versions):
        return await asyncio.to_thread(self._sync_call, "put", config, checkpoint, metadata, new_versions)

    async def aput_writes(self, config, writes, task_id, task_path=""):
        return await asyncio.to_thread(self._sync_call, "put_writes", config, writes, task_id, task_path)

    async def alist(self, config, *, filter=None, before=None, limit=None):
        def _list_rows():
            with self._lock:
                return list(self._saver.list(config, filter=filter, before=before, limit=limit))

        rows = await asyncio.to_thread(_list_rows)
        for row in rows:
            yield row

    async def adelete_thread(self, thread_id):
        return await asyncio.to_thread(self._sync_call, "delete_thread", thread_id)

    async def adelete_for_runs(self, run_ids):
        return await asyncio.to_thread(self._sync_call, "delete_for_runs", run_ids)

    async def aprune(self, thread_ids, *, strategy="keep_latest"):
        return await asyncio.to_thread(self._sync_call, "prune", thread_ids, strategy=strategy)

    async def acopy_thread(self, source_thread_id, target_thread_id):
        return await asyncio.to_thread(self._sync_call, "copy_thread", source_thread_id, target_thread_id)

    def get_tuple(self, config):
        return self._sync_call("get_tuple", config)

    def get(self, config):
        return self._sync_call("get", config)

    def list(self, config, *, filter=None, before=None, limit=None):
        with self._lock:
            return list(self._saver.list(config, filter=filter, before=before, limit=limit))


def _set_stream_queue(q: asyncio.Queue | None, session_id: str | None = None) -> None:
    global _stream_queue
    _stream_queue = q
    if session_id:
        if q is None:
            _stream_queues.pop(session_id, None)
        else:
            _stream_queues[session_id] = q


def _queue_for_state(state: dict[str, Any]) -> asyncio.Queue | None:
    """Return the stream queue associated with a graph state/thread."""
    sid = str(state.get("session_id", ""))
    return _stream_queues.get(sid) or _stream_queue


def _checkpoint_path() -> str:
    """Resolve a durable checkpoint path without coupling to the app DB.

    ``LANGGRAPH_CHECKPOINT_PATH`` is useful for deployments/tests.  By
    default checkpoints live under the configured storage directory, next to
    other application state.  ``:memory:`` is intentionally supported for
    tests, although production should use a file or Postgres saver.
    """
    configured = os.getenv("LANGGRAPH_CHECKPOINT_PATH", "").strip()
    if configured:
        return configured
    root = Path(getattr(settings, "storage_path", "./storage"))
    root.mkdir(parents=True, exist_ok=True)
    return str(root / "langgraph_checkpoints.sqlite")


def _build_checkpointer() -> Any:
    """Create the process-wide durable saver.

    The optional dependency is declared in ``pyproject.toml``.  Falling back
    to ``MemorySaver`` keeps local imports/tests working when an older
    environment has not installed the extra yet, while making the loss of
    durability explicit in logs.
    """
    global _checkpoint_conn
    try:
        from langgraph.checkpoint.sqlite import SqliteSaver

        path = _checkpoint_path()
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        _checkpoint_conn = sqlite3.connect(path, check_same_thread=False)
        saver = SqliteSaver(_checkpoint_conn)
        saver.setup()
        # ``CompiledStateGraph.astream`` requires an async checkpointer.  The
        # sqlite package's synchronous saver deliberately raises from async
        # methods, so expose the same durable store through a small async
        # adapter.  Sync methods remain available for ``get_state`` and
        # diagnostics.
        logger.info("LangGraph SQLite checkpointer enabled: %s", path)
        return _AsyncSqliteSaver(saver)
    except Exception as exc:  # pragma: no cover - only old/minimal installs
        logger.warning("Durable LangGraph checkpointer unavailable: %s", exc)
        return MemorySaver()


def _init_state(
    user_request: str,
    style: str = "auto",
    session_id: str = "",
    memory_context: str = "",
    personalization_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "messages": [],
        "session_id": session_id,
        "user_request": user_request,
        "style": style,
        "phase": "briefing",
        "directors_joined": [],
        "director_decisions": {},
        "current_speaker": None,
        "script": "",
        "final_output": {},
        "disagreement_count": 0,
        "pending_user_question": None,
        "user_intervention": None,
        "turn_count": 0,
        "memory_context": memory_context,
        "personalization_context": personalization_context or {},
        "_user_just_intervened": False,
        "_checkin_done": False,
        # Structured requirement/interaction fields.  They are plain JSON so
        # all checkpointers (including SQLite) can serialize them.
        "requirements": {
            "goal": user_request,
            "hard_constraints": [],
            "explicit_preferences": [],
            "exceptions": [],
            "open_questions": [],
        },
        "creative_brief": {
            "current_goal": user_request,
            "hard_constraints": [],
            "applicable_preferences": [],
            "confirmed_decisions": [],
            "version": 1,
        },
        "question_candidate": None,
        "interaction_policy_decision": None,
        "pending_answer": None,
        "question_history": [],
        "answered_questions": {},
    }


# ---------------------------------------------------------------------------
# Real-time user intervention helpers (WebSocket-driven)
# ---------------------------------------------------------------------------

async def _check_user_intervention(session_id: str) -> str | None:
    """Check if user has requested intervention via WebSocket.

    Returns the user's text if an intervention flag is set, or None.
    Clears the flag so it is only consumed once.
    """
    if not session_id:
        return None
    try:
        from src.api.ws import intervention_flags, intervention_texts
        flag = intervention_flags.get(session_id)
        if flag and flag.is_set():
            text = intervention_texts.pop(session_id, None)
            intervention_flags.pop(session_id, None)
            return text
    except Exception:
        pass
    return None


async def _warm_memory_async(user_id: str, user_request: str) -> None:
    """Fetch memory context in background to warm cache for next session."""
    try:
        from src.core.memory_service import memory_service
        await memory_service.build_context_for_new_session(user_id, user_request)
        logger.debug("Background memory warm completed for %s", user_id)
    except Exception:
        pass


async def _check_pause(session_id: str) -> None:
    """Wait if the discussion has been paused via WebSocket.

    Blocks until a resume_now or intervene action is received.
    """
    if not session_id:
        return
    try:
        from src.api.ws import pause_events
        evt = pause_events.get(session_id)
        if evt is not None:
            logger.info("Discussion paused for session %s, waiting...", session_id)
            await evt.wait()
            pause_events.pop(session_id, None)
            logger.info("Discussion resumed for session %s", session_id)
    except Exception:
        pass


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
        "你是Critic（总评导演）。听取大家的意见后，用中文汇总一份简洁的Markdown脚本（总字数不超过500字）。"
        "包含editing（2-3句）、audio（1-2句）、materials（1-2句）三部分。"
        "最后用FINAL_JSON输出JSON对象，keys: final_script（核心剧本，不超过300字）, edit_instructions, audio_design, material_selection, new_shot_description。"
        "务必简洁，不要长篇大论。"
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


def _published_prompt(strategy: str, fallback: str) -> str:
    """Read a published GEPA prompt without making the graph depend on it.

    Prompt publication is an operational concern.  If the registry is absent
    or malformed the checked-in prompt remains the safe fallback, and an
    already-running checkpoint continues using its own state.
    """
    try:
        from src.core.gepa_service import gepa_service

        return gepa_service.get_published_prompt(strategy) or fallback
    except Exception:
        return fallback


# ---------------------------------------------------------------------------
# LLM helper
# ---------------------------------------------------------------------------

def _get_llm(temp: float = 0.7, max_tokens: int = 500) -> ChatOpenAI:
    cfg = _resolve_llm_config()
    return ChatOpenAI(
        model=cfg["model"],
        api_key=cfg["api_key"],
        base_url=cfg["base_url"],
        temperature=temp,
        max_tokens=max_tokens,
        streaming=True,
    )


# ---------------------------------------------------------------------------
# Node implementations
# ---------------------------------------------------------------------------


def _creative_brief_prompt(state: dict[str, Any]) -> str:
    """Render the shared CreativeBrief for every director/critic prompt.

    The ordering is intentional: explicit requirements are shown before
    remembered preferences.  A one-off exception therefore cannot be
    accidentally overridden by a global profile value.
    """
    brief = state.get("creative_brief") or {}
    req = state.get("requirements") or {}
    goal = brief.get("current_goal") or req.get("goal") or state.get("user_request", "")
    hard = brief.get("hard_constraints") or req.get("hard_constraints") or []
    explicit = req.get("explicit_preferences") or []
    prefs = brief.get("applicable_preferences") or []
    decisions = brief.get("confirmed_decisions") or []
    lines = [
        "共享 CreativeBrief（按优先级：当前明确要求 > 项目决定 > 条件偏好 > 全局偏好）：",
        f"- 当前目标：{goal}",
        f"- 硬约束：{'; '.join(map(str, hard)) if hard else '无'}",
        f"- 当前明确偏好：{'; '.join(map(str, explicit)) if explicit else '无'}",
        f"- 适用偏好：{'; '.join(map(str, prefs)) if prefs else '无'}",
        f"- 已确认决定：{'; '.join(map(str, decisions)) if decisions else '无'}",
    ]
    exceptions = req.get("exceptions") or []
    if exceptions:
        lines.append(f"- 本次例外（优先于长期偏好）：{'; '.join(map(str, exceptions))}")
    return "\n".join(lines)


def _split_requirement_items(text: str) -> list[str]:
    """Split a short Chinese request into stable, human-readable clauses."""
    chunks = re.split(r"[，,。；;\n]|并且|同时|另外|然后", text or "")
    return [c.strip(" \t：:") for c in chunks if c.strip(" \t：:")]


def _parse_requirements_text(user_request: str, style: str = "auto") -> dict[str, Any]:
    """Extract an auditable requirement skeleton without inventing preferences.

    This deliberately starts with deterministic extraction.  An API model can
    enrich the result later, but this baseline is safe when a provider is
    unavailable and, importantly, keeps explicit one-session exceptions out of
    the long-term profile.
    """
    text = str(user_request or "").strip()
    clauses = _split_requirement_items(text)
    hard: list[str] = []
    exceptions: list[str] = []
    explicit: list[str] = []
    for clause in clauses:
        low = clause.lower()
        if any(k in clause for k in ("必须", "一定要", "务必", "不能", "不要", "禁止", "仅")):
            hard.append(clause)
        if any(k in clause for k in ("这次", "本次", "这一次", "例外", "不要沿用", "不按以往")):
            exceptions.append(clause)
        # Style is an explicit signal only when the user wrote it; ``auto`` is
        # a UI default and must not become a learned preference.
        if any(k in clause for k in ("风格", "氛围", "节奏", "忠实", "改编", "结局")):
            explicit.append(clause)
    if style and style != "auto":
        explicit.append(f"界面选择的风格：{style}")
    return {
        "goal": text,
        "hard_constraints": list(dict.fromkeys(hard)),
        "explicit_preferences": list(dict.fromkeys(explicit)),
        "exceptions": list(dict.fromkeys(exceptions)),
        "open_questions": [],
    }


def _requirements_node_event(state: dict[str, Any]) -> dict[str, Any]:
    req = state.get("requirements") or {}
    return {
        "type": "requirements_parsed",
        "requirements": req,
        "creative_brief": state.get("creative_brief") or {},
    }


def _question_id(candidate: dict[str, Any]) -> str:
    raw = "|".join(
        [
            str(candidate.get("kind", "")),
            str(candidate.get("question", "")),
            ",".join(str(x) for x in candidate.get("options", [])),
        ]
    )
    # ``hash()`` is randomized per Python process.  A stable digest makes the
    # answered-question ledger durable across restarts/workers.
    return "q_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def _normalise_answer(answer: Any) -> str:
    if isinstance(answer, dict):
        for key in ("free_text", "text", "answer", "value", "selected_option", "choice"):
            value = answer.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
        if answer.get("continue") is True:
            return "继续"
    if answer is None:
        return "继续"
    return str(answer).strip() or "继续"


def _make_question_candidate(state: dict[str, Any]) -> dict[str, Any] | None:
    """Rule-constrained interaction policy.

    Questions are limited to actionable ambiguity and are deduplicated by a
    stable id.  The LLM may later score candidates, but cannot bypass these
    hard constraints.
    """
    req = state.get("requirements") or {}
    messages = state.get("messages") or []
    rounds = int(state.get("round_count", 0) or 0)
    if state.get("pending_answer") is not None:
        return None
    # A user explicitly supplied a hard constraint/exception: do not ask a
    # generic preference question immediately afterwards.
    if req.get("exceptions") and rounds <= 2:
        return None
    # Ask once at a meaningful milestone, or when the directors visibly
    # disagree.  Existing ``_checkin_done`` prevents repetitive check-ins.
    disagreement = sum(
        1
        for m in messages[-6:]
        if any(k in str(m.get("content", "")) for k in ("不同意", "反对", "但是", "然而", "不建议"))
    )
    # The policy asks at most once per thread unless a genuinely new
    # disagreement appears.  ``_checkin_done`` is only set after an answer.
    should_ask = (rounds >= 2 and not state.get("_checkin_done")) or disagreement >= 3
    if not should_ask:
        return None
    recent = [str(m.get("content", ""))[:100] for m in messages[-4:] if m.get("content")]
    candidate: dict[str, Any] = {
        "kind": "direction_confirmation" if disagreement < 3 else "creative_disagreement",
        "question": (
            "导演组已形成几个方向，想确认你的取舍："
            if disagreement < 3
            else "导演组在创作方向上存在分歧，想确认你的取舍："
        ),
        "options": ["保持当前方向", "更忠实原作", "更大胆改写"],
        "allow_free_text": True,
        "allow_decide": True,
        "context": recent,
        "stage": "decision",
    }
    candidate["id"] = _question_id(candidate)
    answered = state.get("answered_questions") or {}
    if candidate["id"] in answered:
        return None
    return candidate


class InteractionPolicyDecision(BaseModel):
    """Bounded, inspectable output for the optional policy model call."""

    action: Literal["continue", "suggest", "ask"] = "continue"
    reason: str = Field(default="", max_length=500)
    question: str = Field(default="", max_length=300)
    options: list[str] = Field(default_factory=list, max_length=5)


async def _llm_interaction_decision(state: dict[str, Any]) -> InteractionPolicyDecision | None:
    """Ask an API model to score a rule-generated interaction candidate.

    This is opt-in because a policy model must never be able to bypass the
    hard repetition/scope rules.  Invalid or unavailable responses simply
    return ``None`` and the deterministic policy remains authoritative.
    """
    if os.getenv("INTERACTION_POLICY_USE_API", "false").strip().lower() not in {"1", "true", "yes", "on"}:
        return None
    candidate = _make_question_candidate(state)
    if candidate is None:
        return InteractionPolicyDecision(action="continue", reason="no rule-approved candidate")
    try:
        llm = _get_llm(temp=0.1, max_tokens=260)
        prompt = _published_prompt(
            "question_policy",
            "根据 CreativeBrief 和最近讨论判断继续、给建议或暂停提问，只返回 JSON。",
        )
        response = await llm.ainvoke(
            [
                SystemMessage(content=prompt),
                HumanMessage(
                    content=json.dumps(
                        {
                            "brief": state.get("creative_brief") or {},
                            "requirements": state.get("requirements") or {},
                            "candidate": candidate,
                        },
                        ensure_ascii=False,
                    )
                ),
            ]
        )
        raw = str(getattr(response, "content", "") or "").strip()
        match = re.search(r"\{[\s\S]*\}", raw)
        if not match:
            return None
        return InteractionPolicyDecision.model_validate_json(match.group(0))
    except (ValidationError, Exception) as exc:
        logger.debug("Interaction policy model unavailable: %s", exc)
        return None


async def _requirement_parse_node(state: dict[str, Any]) -> dict[str, Any]:
    """Parse the request and establish the first shared CreativeBrief."""
    req = _parse_requirements_text(state.get("user_request", ""), state.get("style", "auto"))
    # Preserve upstream SQL context as structured, conditional preferences;
    # current-request overrides remain explicit and are rendered separately.
    pctx = state.get("personalization_context") or {}
    applicable: list[str] = []
    prefs = pctx.get("preferences") or {}
    for key, item in prefs.items():
        value = item.get("value") if isinstance(item, dict) else item
        if value:
            applicable.append(f"{key}={value}")
    for item in pctx.get("experiences") or []:
        if isinstance(item, dict) and item.get("advice"):
            applicable.append(f"经验[{item.get('condition','')}]：{item.get('advice')}")
    # Legacy callers may only provide a pre-rendered memory string.
    if not applicable and not pctx:
        memory = str(state.get("memory_context") or "").strip()
        if memory:
            applicable.append(memory[:1000])
    current = pctx.get("current_overrides") or {}
    if current:
        req["explicit_preferences"] = list(req.get("explicit_preferences") or []) + [
            f"{key}={item.get('value') if isinstance(item, dict) else item}" for key, item in current.items()
        ]
    state["requirements"] = req
    state["creative_brief"] = {
        "current_goal": req.get("goal", ""),
        "hard_constraints": req.get("hard_constraints", []),
        "applicable_preferences": applicable,
        "confirmed_decisions": [],
        "version": int((state.get("creative_brief") or {}).get("version", 0)) + 1,
    }
    state["phase"] = "briefing"
    queue = _queue_for_state(state)
    if queue is not None:
        await queue.put(_requirements_node_event(state))
    return state


async def _question_decision_node(state: dict[str, Any]) -> dict[str, Any]:
    """Select a useful question and pause with native LangGraph interrupt."""
    candidate = _make_question_candidate(state)
    if candidate is None:
        state["question_candidate"] = None
        return state

    policy = await _llm_interaction_decision(state)
    if policy is not None:
        state["interaction_policy_decision"] = policy.model_dump()
        if policy.action == "continue":
            state["question_candidate"] = None
            return state
        if policy.action in {"ask", "suggest"}:
            # The model may sharpen wording, but must retain at least two
            # choices and the client contract's free-text/decide affordances.
            if policy.question:
                candidate["question"] = policy.question
            if len(policy.options) >= 2:
                candidate["options"] = policy.options[:5]
            candidate["kind"] = "creative_suggestion" if policy.action == "suggest" else candidate.get("kind", "direction_confirmation")
            candidate["id"] = _question_id(candidate)
            if candidate["id"] in (state.get("answered_questions") or {}):
                state["question_candidate"] = None
                return state
            if policy.action == "suggest":
                queue = _queue_for_state(state)
                if queue is not None:
                    await queue.put({
                        "type": "interaction_suggestion",
                        "message": policy.question or candidate["question"],
                        "options": candidate["options"],
                        "stage": candidate.get("stage", "decision"),
                    })
                state["question_candidate"] = None
                state["phase"] = "discussion"
                return state

    # ``interrupt`` raises on the first pass and returns the supplied value on
    # ``Command(resume=...)``.  Keep all payload values JSON-compatible for
    # durable checkpointers and clients.
    state["question_candidate"] = candidate
    state["pending_user_question"] = candidate
    answer = interrupt(candidate)
    state["pending_answer"] = answer
    state["phase"] = "answering"
    return state


async def _answer_node(state: dict[str, Any]) -> dict[str, Any]:
    """Apply a resumed answer and update the shared brief before more debate."""
    candidate = state.get("pending_user_question") or state.get("question_candidate") or {}
    answer_raw = state.get("pending_answer")
    answer = _normalise_answer(answer_raw)
    qid = str(candidate.get("id") or _question_id(candidate))
    history = list(state.get("question_history") or [])
    history.append({"id": qid, "question": candidate.get("question", ""), "answer": answer})
    state["question_history"] = history
    answered = dict(state.get("answered_questions") or {})
    answered[qid] = answer
    state["answered_questions"] = answered

    # Every non-neutral answer is a user decision, including the explicit
    # ``保持当前方向`` and ``你决定`` options.  Previously those two choices
    # were silently omitted from the conversation/brief, so the next
    # directors could not reliably tell that the user had made (or delegated)
    # a decision.  A plain ``继续`` remains a no-op acknowledgement.
    if answer.lower() not in ("继续", "continue", "go on"):
        ts = int(asyncio.get_running_loop().time() * 1000)
        state["messages"] = list(state.get("messages") or []) + [{
            "speaker": "user",
            "role": "user",
            "content": f"[用户对提问的回答] {answer}",
            "stage": "user_input",
            "ts": ts,
        }]
        brief = dict(state.get("creative_brief") or {})
        decisions = list(brief.get("confirmed_decisions") or [])
        decisions.append(
            "用户授权导演自行决定" if answer.lower() in ("你决定", "you decide") else answer
        )
        brief["confirmed_decisions"] = decisions[-12:]
        brief["version"] = int(brief.get("version", 0) or 0) + 1
        state["creative_brief"] = brief

    state["_checkin_done"] = True
    state["question_candidate"] = None
    state["pending_user_question"] = None
    state["pending_answer"] = None
    state["disagreement_count"] = 0
    state["phase"] = "discussion"
    queue = _queue_for_state(state)
    if queue is not None:
        await queue.put({
            "type": "answer_applied",
            "question_id": qid,
            "answer": answer,
            "creative_brief": state.get("creative_brief") or {},
        })
    return state

async def _briefing_node(state: dict[str, Any]) -> dict[str, Any]:
    """Entry node — no LLM call, just set up the task."""
    state["phase"] = "briefing"
    state["turn_count"] = 0
    return state


def _build_director_node(role: str, agent_id: str) -> callable:
    """Factory for director nodes — streams tokens to _event_queue for real-time SSE."""

    async def _node(state: dict[str, Any]) -> dict[str, Any]:
        agent_map = _load_agent_catalog()
        name = _agent_label(agent_map, agent_id, role)
        base_prompt = DIRECTOR_PROMPTS.get(role, DIRECTOR_PROMPTS["narrative"])
        tuned_prompt = _published_prompt("director_writing", "")
        system_prompt = f"{base_prompt}\n\nGEPA 已发布补充策略：\n{tuned_prompt}" if tuned_prompt else base_prompt
        queue = _queue_for_state(state)  # queues stay outside checkpoint state
        sid = str(state.get("session_id", ""))

        # The participation gate is evaluated once.  A director that chose
        # SKIP must not be called again in later rounds, which both honours
        # the protocol and saves API budget.
        decisions = state.get("director_decisions") or {}
        if decisions.get(agent_id) == "skip":
            return state

        # 1. Check for pause (block until resumed)
        await _check_pause(sid)

        # 2. Check for real-time user intervention
        intervention_text = await _check_user_intervention(sid)
        if intervention_text:
            state["user_intervention"] = intervention_text
            state["_user_just_intervened"] = True
            if queue is not None:
                await queue.put({
                    "type": "user_intervention",
                    "speaker": "user",
                    "role": "user",
                    "content": intervention_text,
                    "stage": "debate",
                    "ts": int(asyncio.get_running_loop().time() * 1000),
                })

        llm = _get_llm()

        # Build conversation context
        context_parts = []
        # User intervention takes TOP priority — MUST address it first
        user_intv = state.get("user_intervention")
        if user_intv:
            context_parts.append(
                f"【重要】用户刚刚直接向你提出了意见，你必须首先回应这个意见：\n"
                f"「{user_intv}」\n"
                f"请先针对这个意见给出你的看法，然后再继续你的本职工作。"
            )
            state["user_intervention"] = None
        context_parts.append(f"用户需求：{state['user_request']}")
        context_parts.append(f"风格：{state['style']}")
        context_parts.append(_creative_brief_prompt(state))
        if state.get("memory_context"):
            context_parts.append(f"用户历史偏好：{state['memory_context']}")

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
                # Stream token immediately
                if queue is not None:
                    await queue.put({
                        "type": "turn_chunk",
                        "speaker": agent_id,
                        "role": role,
                        "content": content,
                        "stage": "debate",
                        "ts": int(asyncio.get_running_loop().time() * 1000),
                    })

        cleaned = _clean_content(full_response)
        speaker = agent_id
        ts = int(asyncio.get_running_loop().time() * 1000)

        turn_event = {
            "type": "turn",
            "speaker": speaker,
            "role": role,
            "content": cleaned,
            "stage": "debate",
            "ts": ts,
        }

        # Append to messages
        state["messages"] = state.get("messages", []) + [{
            "speaker": speaker,
            "role": role,
            "content": cleaned,
            "stage": "debate",
            "ts": ts,
        }]

        # Track JOIN/SKIP
        # ``_clean_content`` removes leading English labels for display, so
        # inspect the raw provider response for the JOIN/SKIP gate first.
        raw_head = full_response.lstrip().upper()
        upper_cleaned = cleaned.upper()
        decisions = dict(state.get("director_decisions") or {})
        if raw_head.startswith("SKIP") or upper_cleaned.startswith("SKIP"):
            decisions[agent_id] = "skip"
        else:
            decisions[agent_id] = "join"
        state["director_decisions"] = decisions
        first_join = decisions[agent_id] == "join" and agent_id not in state.get("directors_joined", [])
        if first_join:
            state["directors_joined"] = state.get("directors_joined", []) + [agent_id]
            state.setdefault("_events", []).append(turn_event)
        if queue is not None:
            if first_join:
                await queue.put({
                    "type": "director_joined",
                    "speaker": speaker,
                    "role": role,
                    "stage": "briefing",
                    "ts": ts,
                })
            await queue.put(turn_event)

        state["turn_count"] = state.get("turn_count", 0) + 1
        state["phase"] = "discussion"
        return state

    return _node


_MAX_ROUNDS = 3  # each director speaks this many times before critic

async def _round_check_node(state: dict[str, Any]) -> dict[str, Any]:
    """Check discussion progress and choose the next graph phase.

    Interaction decisions intentionally live in the following dedicated node;
    keeping this node side-effect free makes it safe to replay after a native
    interrupt.
    """
    # If user just intervened, skip disagreement detection so we don't
    # immediately ask the user for MORE input.
    if state.get("_user_just_intervened"):
        state["_user_just_intervened"] = False
        state["disagreement_count"] = 0

    msgs = state.get("messages", [])
    state["round_count"] = state.get("round_count", 0) + 1

    # Determine next step
    if state.get("round_count", 0) >= _MAX_ROUNDS:
        state["phase"] = "finalize"
    else:
        state["phase"] = "discussion"
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
    base_prompt = DIRECTOR_PROMPTS["critic"]
    tuned_prompt = _published_prompt("director_writing", "")
    system_prompt = f"{base_prompt}\n\nGEPA 已发布补充策略：\n{tuned_prompt}" if tuned_prompt else base_prompt
    queue = _queue_for_state(state)  # queues stay outside checkpoint state
    sid = str(state.get("session_id", ""))

    # 1. Check for pause (block until resumed)
    await _check_pause(sid)

    # 2. Check for real-time user intervention
    intervention_text = await _check_user_intervention(sid)
    if intervention_text:
        state["user_intervention"] = intervention_text
        state["_user_just_intervened"] = True
        if queue is not None:
            await queue.put({
                "type": "user_intervention",
                "speaker": "user",
                "role": "user",
                "content": intervention_text,
                "stage": "finalize",
                "ts": int(asyncio.get_running_loop().time() * 1000),
            })

    # Keep Critic on the same factory as the director nodes.  Besides making
    # provider selection consistent, this lets tests and deployments inject a
    # deterministic/API-compatible model without patching a second code path.
    llm = _get_llm(temp=0.5, max_tokens=800)

    prev_msgs = state.get("messages", [])
    discussion_text = "\n".join(
        f"[{m.get('speaker', '')}]: {m.get('content', '')}" for m in prev_msgs
    )

    # User intervention takes top priority
    user_intv = state.get("user_intervention")
    user_intv_block = ""
    if user_intv:
        user_intv_block = (
            f"【重要】用户刚刚直接提出了意见，你必须优先考虑：\n"
            f"「{user_intv}」\n\n"
        )
        state["user_intervention"] = None

    context = (
        f"{user_intv_block}"
        f"用户需求：{state['user_request']}\n"
        f"风格：{state['style']}\n"
        f"{_creative_brief_prompt(state)}\n"
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
            # Stream critic tokens
            if queue is not None:
                await queue.put({
                    "type": "turn_chunk",
                    "speaker": agent_id,
                    "role": "critic",
                    "content": content,
                    "stage": "finalize",
                    "ts": int(asyncio.get_running_loop().time() * 1000),
                })

    cleaned = _clean_content(full_response)
    final = _parse_final_json(full_response)

    state["script"] = str(final.get("final_script") or cleaned).strip()
    state["final_output"] = final
    state["phase"] = "finalize"

    ts = int(asyncio.get_running_loop().time() * 1000)

    script_event = {
        "type": "script",
        "script": state["script"],
        "final": final,
    }

    if queue is not None:
        await queue.put(script_event)

    state.setdefault("_events", []).append(script_event)
    state["messages"] = state.get("messages", []) + [{
        "speaker": agent_id,
        "role": "critic",
        "content": cleaned,
        "stage": "finalize",
        "ts": ts,
    }]

    # Keep a bounded GEPA execution trace for later prompt mutations.  This
    # is optimization evidence only; generated script text is never submitted
    # to the personalization extractor or SQL profile store.
    try:
        from src.core.gepa_service import gepa_service

        gepa_service.record_execution(
            "director_writing",
            {
                "user_request": str(state.get("user_request", ""))[:500],
                "creative_brief": state.get("creative_brief") or {},
            },
            {
                "script": state.get("script", "")[:2000],
                "final_output": state.get("final_output") or {},
            },
        )
    except Exception as exc:
        logger.debug("Unable to record GEPA execution trace: %s", exc)

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

    # Add nodes.  Requirement parsing and interaction policy are explicit
    # graph nodes so their outputs are checkpointed and observable.
    workflow.add_node("briefing", _briefing_node)
    workflow.add_node("requirement_parse", _requirement_parse_node)
    workflow.add_node("narrative_director", _build_director_node("narrative", DIRECTOR_IDS["narrative"]))
    workflow.add_node("visual_director", _build_director_node("visual", DIRECTOR_IDS["visual"]))
    workflow.add_node("sound_director", _build_director_node("sound", DIRECTOR_IDS["sound"]))
    workflow.add_node("material_director", _build_director_node("material", DIRECTOR_IDS["material"]))
    workflow.add_node("round_check", _round_check_node)
    workflow.add_node("question_decision", _question_decision_node)
    workflow.add_node("answer", _answer_node)
    workflow.add_node("user_input", _user_input_node)
    workflow.add_node("critic", _critic_node)

    # Set entry
    workflow.set_entry_point("briefing")

    # briefing → parse requirements → first round
    workflow.add_edge("briefing", "requirement_parse")
    workflow.add_edge("requirement_parse", "narrative_director")
    workflow.add_edge("narrative_director", "visual_director")
    workflow.add_edge("visual_director", "sound_director")
    workflow.add_edge("sound_director", "material_director")
    workflow.add_edge("material_director", "round_check")

    # round_check routing.  Every non-final round passes through the
    # interaction policy.  If no useful question is selected that node is a
    # no-op; if it selects one, ``interrupt`` pauses the graph.
    def _route_after_check(s: dict) -> str:
        if s.get("phase") == "finalize":
            return "critic"
        return "question_decision"

    workflow.add_conditional_edges("round_check", _route_after_check, {
        "question_decision": "question_decision",
        "critic": "critic",
    })

    def _route_after_question(s: dict) -> str:
        if s.get("phase") == "answering" or s.get("pending_answer") is not None:
            return "answer"
        if s.get("phase") == "finalize":
            return "critic"
        return "narrative_director"

    workflow.add_conditional_edges("question_decision", _route_after_question, {
        "answer": "answer",
        "critic": "critic",
        "narrative_director": "narrative_director",
    })
    workflow.add_edge("answer", "narrative_director")
    workflow.add_edge("critic", END)

    _graph_checkpointer = _build_checkpointer()
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
    # Providers sometimes wrap the structured tail in a Markdown fence or
    # append a short explanation.  Decode the first JSON object rather than
    # discarding an otherwise valid script.
    candidate = re.sub(r"^```(?:json)?\s*|\s*```$", "", candidate, flags=re.IGNORECASE).strip()
    try:
        parsed = json.loads(candidate)
        return parsed if isinstance(parsed, dict) else {"final_script": _clean_content(text)}
    except Exception:
        match = re.search(r"\{[\s\S]*\}", candidate)
        if match:
            try:
                parsed = json.loads(match.group(0))
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass
        logger.warning("Failed to parse Critic FINAL_JSON payload")
        return {
            "final_script": _clean_content(text),
            "edit_instructions": "",
            "audio_design": "",
            "material_selection": "",
            "new_shot_description": "",
        }


def _extract_interrupt_items(
    event: dict[str, Any] | None,
) -> list[tuple[str | None, dict[str, Any]]]:
    """Extract ``(interrupt_id, payload)`` pairs from a graph event.

    LangGraph's SQLite checkpointer serialises ``__interrupt__`` into the
    channel values.  Consequently that key can be present on *every* event
    after an interrupt has been resumed, even though the graph is no longer
    paused.  The ID is retained here so callers can distinguish a replayed
    interrupt from a newly-created one.
    """
    if not isinstance(event, dict):
        return []
    raw = event.get("__interrupt__")
    if not raw:
        return []
    if not isinstance(raw, (list, tuple)):
        raw = [raw]
    result: list[tuple[str | None, dict[str, Any]]] = []
    for item in raw:
        # Depending on serializer/version an Interrupt may come back as the
        # concrete object, a mapping (``{"id", "value"}``), or a bare
        # payload.  Accept all three representations for API/test adapters.
        if isinstance(item, dict) and "value" in item:
            interrupt_id = item.get("id")
            value = item.get("value")
        else:
            interrupt_id = getattr(item, "id", None)
            value = getattr(item, "value", item)
        if isinstance(value, dict):
            result.append((str(interrupt_id) if interrupt_id else None, dict(value)))
        elif value is not None:
            result.append(
                (
                    str(interrupt_id) if interrupt_id else None,
                    {"question": str(value), "options": [], "allow_free_text": True},
                )
            )
    return result


def _extract_interrupt(event: dict[str, Any]) -> dict[str, Any] | None:
    """Return the first JSON interrupt payload from a graph values event.

    Kept as a small compatibility helper for callers/tests that only need the
    payload.  Streaming paths use :func:`_extract_interrupt_items` plus the
    checkpoint snapshot to avoid stale ``__interrupt__`` values.
    """
    items = _extract_interrupt_items(event)
    return items[0][1] if items else None


def _snapshot_interrupt_items(
    graph: Any,
    config: dict[str, Any],
) -> list[tuple[str | None, dict[str, Any]]]:
    """Read active interrupts from the durable graph snapshot.

    ``StateSnapshot.interrupts`` is the authoritative pause indicator.  It is
    intentionally separate from ``snapshot.values['__interrupt__']``, which
    may be stale with the synchronous SQLite saver adapter.
    """
    try:
        snapshot = graph.get_state(config)
    except Exception:
        logger.debug("Unable to read LangGraph checkpoint state", exc_info=True)
        return []
    active = getattr(snapshot, "interrupts", ()) or ()
    result: list[tuple[str | None, dict[str, Any]]] = []
    for item in active:
        if isinstance(item, dict) and "value" in item:
            interrupt_id = item.get("id")
            value = item.get("value")
        else:
            interrupt_id = getattr(item, "id", None)
            value = getattr(item, "value", item)
        if isinstance(value, dict):
            payload = dict(value)
        elif value is not None:
            payload = {"question": str(value), "options": [], "allow_free_text": True}
        else:
            continue
        result.append((str(interrupt_id) if interrupt_id else None, payload))
    return result


def _question_event(payload: dict[str, Any], session_id: str) -> dict[str, Any]:
    """Normalize an interrupt into the ordered SSE event contract."""
    question = dict(payload)
    question.setdefault("id", _question_id(question))
    question.setdefault("allow_free_text", True)
    question.setdefault("allow_decide", True)
    return {
        "type": "awaiting_input",
        "question": question,
        "question_id": question["id"],
        "session_id": session_id,
        "stage": question.get("stage", "decision"),
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
    personalization_context: dict[str, Any] | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """Stream a LangGraph discussion as SSE-compatible JSON events.

    Uses an asyncio.Queue so director LLM tokens are yielded in real-time
    (the same way the old AutoGen service did).  A background task runs the
    LangGraph; the foreground drains the queue.

    Events (same format as legacy AutoGen):
      {"type": "turn_chunk", "speaker": ..., "role": ..., "content": ..., "stage": "debate", "ts": ...}
      {"type": "turn",        "speaker": ..., "role": ..., "content": ..., "stage": "debate", "ts": ...}
      {"type": "script",      "script": ..., "final": {...}}
      {"type": "task_result", "stop_reason": "critic_finished"}
    """

    _resolve_llm_config()  # raises if no provider configured

    sid = session_id or str(uuid.uuid4())
    graph = build_discussion_graph()

    # SQL personalization is the authoritative source for profile,
    # scoped preferences and ACE experiences.  API callers build this context
    # synchronously from their request DB session and pass it here.  Keep the
    # rendering deliberately explicit so a one-off request override is shown
    # before lower-priority global values.
    # Keep the structured SQL preference count when a personalization context
    # was supplied by the API; semantic-case retrieval only contributes its
    # own count below.
    if not personalization_context:
        prefs_count = 0
    similar_count = 0
    if personalization_context:
        pctx = personalization_context
        parts: list[str] = ["## 结构化用户画像（SQL 权威）"]
        profile = pctx.get("profile") or {}
        for key, label in (("ending_tendency", "结局倾向"), ("emotional_style", "情感风格"), ("original_fidelity", "原作忠实度")):
            if profile.get(key):
                parts.append(f"- {label}：{profile[key]}")
        prefs = pctx.get("preferences") or {}
        current = pctx.get("current_overrides") or {}
        if current:
            parts.append("## 本次明确要求（最高优先级）")
            for key, value in current.items():
                val = value.get("value") if isinstance(value, dict) else value
                parts.append(f"- {key}：{val}")
        if prefs:
            parts.append("## 适用偏好（项目/会话/条件/全局，按优先级解析）")
            for key, value in prefs.items():
                val = value.get("value") if isinstance(value, dict) else value
                scope = value.get("scope") if isinstance(value, dict) else ""
                condition = value.get("condition") if isinstance(value, dict) else ""
                suffix = f"（{scope}{'；'+condition if condition else ''}）" if scope or condition else ""
                parts.append(f"- {key}：{val}{suffix}")
        experiences = pctx.get("experiences") or []
        if experiences:
            parts.append("## ACE 创作经验（条件建议，不是硬约束）")
            for item in experiences:
                if not isinstance(item, dict):
                    continue
                parts.append(f"- 适用：{item.get('condition','')}；建议：{item.get('advice','')}；证据：{item.get('evidence','')}")
        structured = "\n".join(parts)
        memory_context = "\n".join(x for x in (structured, memory_context) if x)
        prefs_count = len(prefs) + len(current)

    # Inject semantic historical-case context if available -- with a short timeout so Chroma
    # model downloads don't block the discussion from starting.
    if user_id:
        try:
            from src.core.memory_service import memory_service
            if personalization_context:
                # SQL already supplied preferences; Mem0 is reserved for
                # semantic historical cases and is therefore queried
                # independently rather than through the legacy JSON builder.
                cases = await asyncio.wait_for(
                    memory_service.search_historical_cases(user_id, user_request, k=2),
                    timeout=3.0,
                )
                if cases:
                    case_lines = ["## 历史相关创作案例（Mem0）"]
                    for case in cases:
                        if isinstance(case, dict):
                            content = case.get("memory") or case.get("script") or case.get("content") or case
                            case_lines.append(f"- {str(content)[:400]}")
                    memory_context = "\n".join(x for x in (memory_context, "\n".join(case_lines)) if x)
                    similar_count = len(cases)
            elif not memory_context:
                mem_info = await asyncio.wait_for(
                    memory_service.build_context_for_new_session(user_id, user_request),
                    timeout=3.0,
                )
                memory_context = mem_info.get("context", "") if isinstance(mem_info, dict) else str(mem_info)
                prefs_count = mem_info.get("preferences_count", 0) if isinstance(mem_info, dict) else 0
                similar_count = mem_info.get("similar_scripts", 0) if isinstance(mem_info, dict) else 0
        except (asyncio.TimeoutError, Exception) as exc:
            logger.debug("Memory context fetch skipped (%s), proceeding without it", exc)
            # Retry in background for next session
            if user_id:
                asyncio.create_task(_warm_memory_async(user_id, user_request))

    # Notify frontend when historical preferences are loaded
    if memory_context:
        yield {
            "type": "memory_loaded",
            "preferences_count": prefs_count,
            "similar_scripts": similar_count,
        }

    initial_state = _init_state(
        user_request=user_request,
        style=style,
        session_id=sid,
        memory_context=memory_context,
        personalization_context=personalization_context,
    )
    if performance_notes:
        initial_state["user_request"] = f"{user_request}\n\nPerformance notes: {performance_notes}"

    # Queue for real-time token streaming from within graph nodes.  It is
    # keyed by thread so concurrent sessions cannot cross-talk.
    queue: asyncio.Queue = asyncio.Queue()
    _set_stream_queue(queue, sid)
    config = {"configurable": {"thread_id": sid}}
    sentinel = object()
    graph_error: Exception | None = None
    paused = False

    async def _run_graph() -> None:
        nonlocal graph_error, paused
        try:
            async for event in graph.astream(initial_state, config, stream_mode="values"):
                # Do not infer pause state from ``event['__interrupt__']``.
                # With the SQLite saver adapter that channel can remain in
                # subsequent values events after a resume.  We consume the
                # complete graph run first, then inspect the authoritative
                # StateSnapshot.interrupts below.
                _ = event
            active_interrupts = _snapshot_interrupt_items(graph, config)
            if active_interrupts:
                paused = True
                _, interruption = active_interrupts[0]
                await queue.put(_question_event(interruption, sid))
        except Exception as exc:
            logger.error("LangGraph discussion failed: %s", exc)
            graph_error = exc
        finally:
            await queue.put(sentinel)

    graph_task = asyncio.create_task(_run_graph())
    try:
        while True:
            item = await queue.get()
            if item is sentinel:
                break
            yield item
    finally:
        if not graph_task.done():
            graph_task.cancel()
        _set_stream_queue(None, sid)

    if graph_error:
        yield {"type": "error", "message": str(graph_error)}
    elif paused:
        yield {"type": "paused", "session_id": sid, "stop_reason": "awaiting_user"}
    else:
        yield {"type": "task_result", "stop_reason": "critic_finished"}


async def resume_langgraph_discussion_stream(
    session_id: str,
    user_input: str,
) -> AsyncGenerator[dict[str, Any], None]:
    """Manually resume a paused discussion with user input."""
    graph = build_discussion_graph()
    config = {"configurable": {"thread_id": session_id}}

    state = graph.get_state(config)
    # ``CompiledStateGraph.get_state`` returns an empty StateSnapshot for an
    # unknown thread (rather than ``None``).  Treat both forms as a missing
    # checkpoint; otherwise ``Command(resume=...)`` would silently start a
    # no-op run and report a misleading ``task_result``.
    if state is None or not getattr(state, "values", None):
        yield {"type": "error", "message": f"No checkpoint found for session {session_id}"}
        return

    # A resume answer is meaningful only while an interaction is pending.
    # Rejecting a second/late answer also prevents replaying a completed graph
    # or accidentally applying input to a thread that was paused by another
    # mechanism.  ``StateSnapshot.interrupts`` is authoritative; do not use
    # the potentially stale ``values['__interrupt__']`` channel.
    if not (getattr(state, "interrupts", ()) or ()):
        yield {
            "type": "error",
            "message": f"No pending user input for session {session_id}",
        }
        return

    queue: asyncio.Queue = asyncio.Queue()
    _set_stream_queue(queue, session_id)

    sentinel = object()
    graph_error: Exception | None = None
    paused = False

    async def _run():
        nonlocal graph_error, paused
        try:
            # Native resume is essential: passing a copied state as input
            # re-runs nodes and loses the interrupt's task identity.
            async for event in graph.astream(Command(resume=user_input), config, stream_mode="values"):
                # ``__interrupt__`` in a values event may be a stale channel
                # value left by the synchronous SQLite saver.  Only an
                # active interrupt in the final checkpoint means this resume
                # request paused again.
                _ = event
            active_interrupts = _snapshot_interrupt_items(graph, config)
            if active_interrupts:
                paused = True
                _, interruption = active_interrupts[0]
                await queue.put(_question_event(interruption, session_id))
        except Exception as exc:
            graph_error = exc
        finally:
            await queue.put(sentinel)

    graph_task = asyncio.create_task(_run())

    try:
        while True:
            item = await queue.get()
            if item is sentinel:
                break
            yield item
    finally:
        if not graph_task.done():
            graph_task.cancel()
        _set_stream_queue(None, session_id)

    if graph_error:
        yield {"type": "error", "message": str(graph_error)}
    elif paused:
        yield {"type": "paused", "session_id": session_id, "stop_reason": "awaiting_user"}
    else:
        yield {"type": "task_result", "stop_reason": "critic_finished"}


async def get_discussion_state(session_id: str) -> dict[str, Any] | None:
    """Get current discussion state from checkpoint."""
    graph = build_discussion_graph()
    config = {"configurable": {"thread_id": session_id}}
    state = graph.get_state(config)
    if state is None or not getattr(state, "values", None):
        return None
    # ``__interrupt__`` is an internal LangGraph channel and can remain in
    # SQLite-backed values after a resume.  Expose an explicit, authoritative
    # pause bit instead of leaking that stale implementation detail to API
    # consumers.
    values = {
        key: value for key, value in dict(state.values).items() if key != "__interrupt__"
    }
    values["paused"] = bool(getattr(state, "interrupts", ()) or ())
    if values["paused"]:
        active = _snapshot_interrupt_items(graph, config)
        if active:
            values["active_question"] = active[0][1]
    else:
        values.pop("active_question", None)
    return values
