"""Personalization primitives used by the discussion workflow.

This module intentionally keeps the learning boundary small and auditable:
only text supplied by a user (their request, a choice, an edit, or explicit
feedback) can become evidence.  Generated scripts and director messages are
never passed to :func:`extract_user_observations` by this service.

SQLAlchemy is the source of truth for structured profile/preferences and ACE
style experiences.  ``MemoryService``/Mem0 is reserved for semantic retrieval
of historical *cases* and is always filtered by ``user_id``.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any, Iterable, Mapping, Sequence

from sqlalchemy.orm import Session

from src.models import CreativeExperience, UserPreference, UserProfile


PROFILE_KEYS = {"ending_tendency", "emotional_style", "original_fidelity"}
USER_EVIDENCE_SOURCES = {
    "user_expression",
    "user_choice",
    "user_edit",
    "explicit_feedback",
    "feedback",
}
SCOPES = {"global", "project", "session", "request"}


def _utcnow() -> datetime:
    """Return a naive UTC timestamp for the app's SQL DateTime columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _norm(value: Any) -> str:
    """Normalize text for deterministic dedupe/comparison."""

    text = re.sub(r"\s+", " ", _text(value)).strip().lower()
    return text.strip(" .。！？!?,，;；:：\"'`[]()（）")


def _confidence(value: Any, default: float = 0.5) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    # Rows created by the old implementation used 0–100 integer percentages.
    if number > 1:
        number /= 100.0
    return max(0.0, min(1.0, number))


def _safe_user_id(user_id: str) -> str:
    value = _text(user_id)
    if not value or len(value) > 255:
        raise ValueError("user_id must be a non-empty string of at most 255 characters")
    # Prevent path/tenant confusion in callers that use IDs in URLs/files.
    if any(ord(ch) < 32 for ch in value):
        raise ValueError("user_id contains control characters")
    return value


def _evidence_source(source: str | None) -> str:
    value = _text(source) or "user_expression"
    if value not in USER_EVIDENCE_SOURCES:
        raise ValueError(
            "learning source must be one of user_expression, user_choice, "
            "user_edit, explicit_feedback"
        )
    return "explicit_feedback" if value == "feedback" else value


def _contains_any(text: str, words: Iterable[str]) -> bool:
    return any(word in text for word in words)


def extract_user_observations(
    user_text: str,
    *,
    source: str = "user_expression",
    scope: str = "global",
    project_id: str | None = None,
    session_id: str | None = None,
    evidence_ref: str | None = None,
) -> list[dict[str, Any]]:
    """Extract explicit preference observations from *user* text.

    The extractor is deliberately conservative.  It recognizes statements
    containing first-person intent/choice markers and returns no observations
    for neutral or generated-looking prose.  Callers should invoke it only on
    user-authored input; the ``source`` guard prevents accidental model-output
    learning.

    Returned dictionaries are suitable for :meth:`PersonalizationService`.
    ``scope`` defaults to ``global`` for explicit durable statements, but a
    caller should pass ``request`` for a one-off exception.
    """

    source = _evidence_source(source)
    if scope not in SCOPES:
        raise ValueError(f"unsupported preference scope: {scope}")
    text = _text(user_text)
    if not text:
        return []

    # A safety marker for integrations: generated/model output must opt in to
    # no learning by using a non-user source (which raises above).
    explicit = (
        _contains_any(
            text.lower(),
            (
                "我想",
                "我希望",
                "我喜欢",
                "我偏好",
                "我不喜欢",
                "我不希望",
                "我不想要",
                "我不喜欢",
                "请保留",
                "请改成",
                "必须",
                "不要",
                "更倾向",
                "i want",
                "i prefer",
                "i like",
                "please keep",
                "please make",
                "must",
                "don't",
            ),
        )
        or source in {"user_choice", "user_edit", "explicit_feedback"}
    )
    if not explicit:
        return []

    lower = text.lower()
    observations: list[dict[str, Any]] = []

    def _scope_for_span(start: int | None = None, end: int | None = None) -> str:
        """Make a nearby one-off clause request-scoped.

        A sentence can contain both a durable statement and a one-off
        exception (for example, ``我喜欢温柔风格，但这次不要圆满结局``).
        Looking only at the clause containing the match preserves that
        distinction instead of downgrading the whole utterance to temporary.
        """
        if scope != "global" or start is None:
            return scope
        marker_start = int(start)
        marker_end = int(end if end is not None else start)
        separators = re.compile(r"[，,。；;\n]|\b(?:but|however)\b|但|但是|不过", re.IGNORECASE)
        boundaries = [0]
        boundaries.extend(match.start() for match in separators.finditer(text))
        boundaries.append(len(text))
        clause = text
        for left, right in zip(boundaries, boundaries[1:]):
            if left <= marker_start <= right or left <= marker_end <= right:
                clause = text[left:right]
                break
        return "request" if _contains_any(clause.lower(), ("这次", "本次", "这一次", "例外", "不要沿用", "不按以往")) else scope

    def add(
        key: str,
        value: str,
        condition: str | None = None,
        *,
        match_start: int | None = None,
        match_end: int | None = None,
        scope_override: str | None = None,
    ) -> None:
        value = _text(value)
        if not value:
            return
        observation_scope = scope_override or _scope_for_span(match_start, match_end)
        observations.append(
            {
                "key": key,
                "value": value,
                "scope": observation_scope,
                "project_id": project_id,
                "session_id": session_id,
                "applicability_condition": condition,
                "source": source,
                "evidence_source": source,
                "evidence_ref": evidence_ref,
                "evidence_text": text,
            }
        )

    # Ending tendency.  Keep the user's wording as evidence/value while
    # canonicalising common reversed Chinese forms such as ``结局开放式``.
    ending_patterns = (
        ("幸福结局", "幸福结局"),
        ("开放式结局", "开放式结局"),
        ("悲剧结局", "悲剧结局"),
        ("反转结局", "反转结局"),
        ("happy ending", "happy ending"),
        ("open ending", "open ending"),
        ("tragic ending", "tragic ending"),
        ("活下来", "活下来"),
        ("生还", "生还"),
        ("圆满", "圆满结局"),
        ("幸福", "幸福结局"),
        ("开放式", "开放式结局"),
        ("悲剧", "悲剧结局"),
        ("反转", "反转结局"),
    )
    ending_match = None
    for needle, canonical in ending_patterns:
        match = re.search(re.escape(needle), text, flags=re.IGNORECASE)
        if match and (ending_match is None or len(needle) > len(ending_match[0])):
            ending_match = (needle, canonical, match)
    if ending_match:
        needle, canonical, match = ending_match
        prefix = re.split(r"[，,。；;\n]|\b(?:but|however)\b|但|但是|不过", text[: match.start()], flags=re.IGNORECASE)[-1].lower()
        negated = bool(re.search(r"(?:不要|别|不想要|不必|不接受|拒绝|avoid|don't|do not|not)", prefix))
        exception_before = bool(
            re.search(r"(?:这次|本次|这一次)[^。！？.!?]{0,24}(?:不要沿用|不按以往|例外)", text[: match.start()], flags=re.IGNORECASE)
        )
        value = ("avoid:" if negated else "") + canonical
        add(
            "ending_tendency",
            value,
            "ending/结局",
            match_start=match.start(),
            match_end=match.end(),
            scope_override="request" if (negated or exception_before) and scope == "global" else None,
        )

    emotional_words = (
        "温柔",
        "治愈",
        "克制",
        "细腻",
        "轻松",
        "幽默",
        "压抑",
        "紧张",
        "浪漫",
        "热烈",
        "温暖",
        "dark",
        "tender",
        "healing",
        "romantic",
        "humorous",
    )
    for word in emotional_words:
        if word.lower() in lower and _contains_any(lower, ("风格", "氛围", "情绪", "tone", "style", "我喜欢", "我希望", "偏好")):
            match = re.search(re.escape(word), text, flags=re.IGNORECASE)
            add(
                "emotional_style",
                word,
                "tone/情感风格",
                match_start=match.start() if match else None,
                match_end=match.end() if match else None,
            )
            break

    fidelity_words = (
        ("忠实原作", "high"),
        ("尊重原著", "high"),
        ("贴合原作", "high"),
        ("大幅改编", "low"),
        ("不必忠实", "low"),
        ("自由发挥", "low"),
        ("faithful", "high"),
        ("liberal adaptation", "low"),
    )
    for word, label in fidelity_words:
        if word.lower() in lower:
            match = re.search(re.escape(word), text, flags=re.IGNORECASE)
            add(
                "original_fidelity",
                label,
                "fidelity/原作忠实度",
                match_start=match.start() if match else None,
                match_end=match.end() if match else None,
            )
            break

    # Preserve explicit generic preferences too.  This is useful for pacing,
    # dialogue, shot language, etc., while profile columns cover the core axes.
    generic_patterns = (
        r"(?:我喜欢|我偏好|我希望(?:能)?|请(?:尽量)?|please\s+(?:keep|make))\s*([^。！？.!?]{2,80})",
        r"(?:我不喜欢|我不希望|我不想要|不要|别|不想要|don't)\s*([^。！？.!?]{2,80})",
    )
    if source == "user_edit":
        generic_patterns += (
            r"(?:改成|改为|换成|调整为|保留|增加|添加|删掉|去掉)\s*([^。！？.!?]{2,80})",
        )
    elif source == "user_choice":
        generic_patterns += (
            r"(?:我选择|我选|选择|选)\s*([^。！？.!?]{2,80})",
        )
    for pattern_index, pattern in enumerate(generic_patterns):
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            value = _text(match.group(1))
            # Do not carry a later exception into the durable clause.
            value = re.split(r"[，,；;]|但|但是|不过|这次|本次", value, maxsplit=1)[0].strip()
            if pattern_index == 1 and value:
                value = "avoid:" + value
            if value and not _contains_any(value.lower(), ("沿用以往偏好", "不要沿用", "不按以往")) and not any(value == o.get("value") for o in observations):
                add("creative_preference", value, match_start=match.start(), match_end=match.end())
            if len(observations) >= 8:
                break
        if len(observations) >= 8:
            break

    # Deduplicate same key/value in one utterance.
    unique: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in observations:
        marker = (_norm(item["key"]), _norm(item["value"]))
        if marker not in seen:
            seen.add(marker)
            unique.append(item)
    return unique


class PersonalizationService:
    """Transactional profile, preference and experience operations."""

    def ensure_profile(self, db: Session, user_id: str) -> UserProfile:
        user_id = _safe_user_id(user_id)
        profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).one_or_none()
        if profile is None:
            profile = UserProfile(user_id=user_id, profile_data={}, version=1, evidence_count=0)
            db.add(profile)
            db.flush()
        return profile

    def get_profile(self, db: Session, user_id: str) -> UserProfile | None:
        return db.query(UserProfile).filter(UserProfile.user_id == _safe_user_id(user_id)).one_or_none()

    def apply_observations(
        self,
        db: Session,
        user_id: str,
        observations: Sequence[Mapping[str, Any]],
        *,
        default_scope: str = "global",
        commit: bool = True,
    ) -> list[UserPreference]:
        """Persist user-originated observations and update the profile.

        Global values are upserted as new versions (old rows stay auditable and
        are marked superseded).  Request/project/session observations remain
        bounded and never mutate long-term profile columns.
        """

        user_id = _safe_user_id(user_id)
        profile = self.ensure_profile(db, user_id)
        saved: list[UserPreference] = []
        try:
            for raw in observations:
                item = dict(raw)
                source = _evidence_source(item.get("source") or item.get("evidence_source"))
                scope = _text(item.get("scope")) or default_scope
                if scope not in SCOPES:
                    raise ValueError(f"unsupported preference scope: {scope}")
                if scope == "project" and not item.get("project_id"):
                    raise ValueError("project-scoped preferences require project_id")
                if scope == "session" and not item.get("session_id"):
                    raise ValueError("session-scoped preferences require session_id")
                if scope == "request" and not item.get("project_id") and not item.get("session_id"):
                    # A request-scoped observation without a context can never
                    # be resolved after the request finishes.  Current-run
                    # parsing remains in-memory and does not call apply.
                    raise ValueError("request-scoped preferences require project_id or session_id")
                key = _text(item.get("key") or item.get("preference_key"))
                value = _text(item.get("value") or item.get("preference_value"))
                if not key or not value:
                    continue
                # Only these sources may enter durable storage.
                if source not in USER_EVIDENCE_SOURCES:
                    continue
                current = (
                    db.query(UserPreference)
                    .filter(
                        UserPreference.user_id == user_id,
                        UserPreference.preference_key == key,
                        UserPreference.scope == scope,
                        UserPreference.status == "active",
                        UserPreference.project_id == item.get("project_id"),
                        UserPreference.session_id == item.get("session_id"),
                    )
                    .order_by(UserPreference.version.desc(), UserPreference.created_at.desc())
                    .first()
                )
                if current is not None and _norm(current.preference_value) == _norm(value):
                    # Repeated evidence strengthens confidence without creating
                    # duplicate rows.
                    current.confidence = min(1.0, _confidence(current.confidence) + 0.05)
                    current.updated_at = _utcnow()
                    saved.append(current)
                    continue
                next_version = (current.version + 1) if current is not None else 1
                if current is not None:
                    current.status = "superseded"
                    current.updated_at = _utcnow()
                row = UserPreference(
                    user_id=user_id,
                    preference_key=key,
                    preference_value=value,
                    scope=scope,
                    project_id=item.get("project_id"),
                    session_id=item.get("session_id"),
                    applicability_condition=item.get("applicability_condition"),
                    evidence_source=source,
                    evidence_ref=item.get("evidence_ref"),
                    confidence=_confidence(item.get("confidence"), 0.8),
                    source=source,
                    version=next_version,
                    status="active",
                    is_long_term=scope == "global",
                )
                db.add(row)
                db.flush()
                saved.append(row)

                # Profile columns are changed only by global user evidence.
                if scope == "global" and key in PROFILE_KEYS:
                    setattr(profile, key, value)
                    profile.version = (profile.version or 0) + 1
                    profile.evidence_count = (profile.evidence_count or 0) + 1
                    profile.last_evidence_source = source
                    profile.last_evidence_ref = item.get("evidence_ref")
                elif scope == "global":
                    data = dict(profile.profile_data or {})
                    data[key] = value
                    profile.profile_data = data
                    profile.version = (profile.version or 0) + 1
                    profile.evidence_count = (profile.evidence_count or 0) + 1
                    profile.last_evidence_source = source
                    profile.last_evidence_ref = item.get("evidence_ref")
            if commit:
                db.commit()
            return saved
        except Exception:
            db.rollback()
            raise

    def record_user_text(
        self,
        db: Session,
        user_id: str,
        text: str,
        *,
        source: str = "user_expression",
        scope: str = "global",
        project_id: str | None = None,
        session_id: str | None = None,
        evidence_ref: str | None = None,
        commit: bool = True,
    ) -> list[UserPreference]:
        observations = extract_user_observations(
            text,
            source=source,
            scope=scope,
            project_id=project_id,
            session_id=session_id,
            evidence_ref=evidence_ref,
        )
        return self.apply_observations(db, user_id, observations, commit=commit)

    def list_preferences(
        self,
        db: Session,
        user_id: str,
        *,
        include_inactive: bool = False,
        scope: str | None = None,
        project_id: str | None = None,
        session_id: str | None = None,
    ) -> list[UserPreference]:
        query = db.query(UserPreference).filter(UserPreference.user_id == _safe_user_id(user_id))
        if not include_inactive:
            query = query.filter(UserPreference.status == "active")
        if scope:
            query = query.filter(UserPreference.scope == scope)
        if project_id is not None:
            query = query.filter(UserPreference.project_id == project_id)
        if session_id is not None:
            query = query.filter(UserPreference.session_id == session_id)
        return query.order_by(UserPreference.preference_key, UserPreference.version.desc()).all()

    def resolve_preferences(
        self,
        db: Session,
        user_id: str,
        *,
        current_request: str = "",
        project_id: str | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Resolve values with explicit priority and preserve one-off exceptions.

        Priority: current explicit request > project/session/request evidence >
        conditional global > global.  Current request observations are
        returned in ``current_overrides`` but are *not* persisted.
        """

        rows = self.list_preferences(db, user_id, include_inactive=False)
        current_obs = extract_user_observations(current_request, source="user_expression", scope="request")
        current_by_key = {o["key"]: o for o in current_obs}
        resolved: dict[str, dict[str, Any]] = {}

        def rank(row: UserPreference) -> tuple[int, float, int]:
            same_session = bool(session_id and row.session_id == session_id)
            same_project = bool(project_id and row.project_id == project_id)
            if same_session:
                scope_rank = 300
            elif same_project:
                scope_rank = 250
            elif row.scope == "request":
                scope_rank = 220
            elif row.applicability_condition:
                scope_rank = 150
            elif row.scope == "global":
                scope_rank = 100
            else:
                scope_rank = 0
            return scope_rank, _confidence(row.confidence), int(row.version or 0)

        for row in rows:
            # Scope isolation is strict: a session preference must never
            # become active merely because its project happens to match, and
            # project/request rows are only visible in their referenced
            # context.  This prevents cross-session leakage while retaining
            # global values as the low-priority fallback.
            if row.scope == "project":
                if not project_id or row.project_id != project_id:
                    continue
            elif row.scope == "session":
                if not session_id or row.session_id != session_id:
                    continue
            elif row.scope == "request":
                if not ((project_id and row.project_id == project_id) or (session_id and row.session_id == session_id)):
                    continue
            old = resolved.get(row.preference_key)
            if old is None or rank(row) > old["_rank"]:
                resolved[row.preference_key] = {"value": row.preference_value, "source": row.source, "scope": row.scope, "condition": row.applicability_condition, "_rank": rank(row)}

        # Explicit text always wins for this run, including a deliberate
        # exception such as “这次不要圆满结局”.
        for key, obs in current_by_key.items():
            resolved[key] = {"value": obs["value"], "source": "current_request", "scope": "request", "condition": obs.get("applicability_condition"), "_rank": (1000, 1.0, 0)}

        clean = {k: {kk: vv for kk, vv in value.items() if kk != "_rank"} for k, value in resolved.items()}
        return {
            "user_id": user_id,
            "preferences": clean,
            "current_overrides": current_by_key,
            "profile": self.profile_dict(db, user_id),
        }

    def profile_dict(self, db: Session, user_id: str) -> dict[str, Any]:
        profile = self.get_profile(db, user_id)
        if profile is None:
            return {"user_id": _safe_user_id(user_id), "ending_tendency": None, "emotional_style": None, "original_fidelity": None, "profile_data": {}, "version": 0}
        return {
            "user_id": profile.user_id,
            "ending_tendency": profile.ending_tendency,
            "emotional_style": profile.emotional_style,
            "original_fidelity": profile.original_fidelity,
            "profile_data": dict(profile.profile_data or {}),
            "version": profile.version,
            "evidence_count": profile.evidence_count,
        }

    def record_experience(
        self,
        db: Session,
        user_id: str,
        *,
        applicable_condition: str,
        advice: str,
        user_evidence: str,
        evidence_source: str = "explicit_feedback",
        evidence_ref: str | None = None,
        project_id: str | None = None,
        session_id: str | None = None,
        confidence: float = 0.8,
        commit: bool = True,
    ) -> CreativeExperience:
        """Add or revise a deduplicated ACE-style experience entry."""

        user_id = _safe_user_id(user_id)
        source = _evidence_source(evidence_source)
        condition, advice_norm = _norm(applicable_condition), _norm(advice)
        if not condition or not advice_norm or not _text(user_evidence):
            raise ValueError("condition, advice and user_evidence are required")
        candidates = (
            db.query(CreativeExperience)
            .filter(
                CreativeExperience.user_id == user_id,
                CreativeExperience.status == "active",
                # An experience is a scoped lesson.  Do not revise a global
                # lesson with a project/session observation that merely has
                # the same wording, and do not let one project's evidence
                # move another project's entry.
                CreativeExperience.project_id == project_id,
                CreativeExperience.session_id == session_id,
            )
            .all()
        )
        existing = None
        for candidate in candidates:
            c_sim = SequenceMatcher(None, condition, _norm(candidate.applicable_condition)).ratio()
            a_sim = SequenceMatcher(None, advice_norm, _norm(candidate.advice)).ratio()
            if c_sim >= 0.90 and a_sim >= 0.90:
                existing = candidate
                break
        if existing is not None:
            # Revision retains the same logical entry and increments version.
            existing.applicable_condition = _text(applicable_condition)
            existing.advice = _text(advice)
            existing.user_evidence = _text(user_evidence)
            existing.evidence_source = source
            existing.evidence_ref = evidence_ref
            existing.project_id = project_id
            existing.session_id = session_id
            existing.confidence = max(_confidence(existing.confidence), _confidence(confidence))
            existing.version = (existing.version or 0) + 1
            existing.updated_at = _utcnow()
            result = existing
        else:
            result = CreativeExperience(
                user_id=user_id,
                applicable_condition=_text(applicable_condition),
                advice=_text(advice),
                user_evidence=_text(user_evidence),
                evidence_source=source,
                evidence_ref=evidence_ref,
                project_id=project_id,
                session_id=session_id,
                confidence=_confidence(confidence),
                version=1,
                status="active",
                usage_count=0,
            )
            db.add(result)
        if commit:
            db.commit()
            db.refresh(result)
        else:
            db.flush()
        return result

    def list_experiences(self, db: Session, user_id: str, *, include_inactive: bool = False) -> list[CreativeExperience]:
        query = db.query(CreativeExperience).filter(CreativeExperience.user_id == _safe_user_id(user_id))
        if not include_inactive:
            query = query.filter(CreativeExperience.status == "active")
        return query.order_by(CreativeExperience.updated_at.desc()).all()

    def invalidate_experience(self, db: Session, user_id: str, experience_id: str, *, commit: bool = True) -> CreativeExperience | None:
        row = (
            db.query(CreativeExperience)
            .filter(CreativeExperience.id == experience_id, CreativeExperience.user_id == _safe_user_id(user_id))
            .one_or_none()
        )
        if row is None:
            return None
        row.status = "invalid"
        row.version = (row.version or 0) + 1
        row.updated_at = _utcnow()
        if commit:
            db.commit()
            db.refresh(row)
        return row

    def build_context(self, db: Session, user_id: str, *, current_request: str = "", project_id: str | None = None, session_id: str | None = None, max_experiences: int = 8) -> dict[str, Any]:
        resolved = self.resolve_preferences(db, user_id, current_request=current_request, project_id=project_id, session_id=session_id)
        # Experience entries follow the same tenant/context isolation as
        # preferences.  A project- or session-specific lesson is only useful
        # in that context; global entries remain available everywhere.
        all_experiences = self.list_experiences(db, user_id)
        experiences = [
            e for e in all_experiences
            if (e.session_id is None or e.session_id == session_id)
            and (e.project_id is None or e.project_id == project_id)
        ][:max_experiences]
        return {
            "user_id": _safe_user_id(user_id),
            "profile": resolved["profile"],
            "preferences": resolved["preferences"],
            "current_overrides": resolved["current_overrides"],
            "experiences": [
                {"condition": e.applicable_condition, "advice": e.advice, "evidence": e.user_evidence, "confidence": _confidence(e.confidence), "version": e.version}
                for e in experiences
            ],
        }

    async def build_context_async(self, db: Session, user_id: str, **kwargs: Any) -> dict[str, Any]:
        """Async-friendly alias for API/graph integrations."""

        return self.build_context(db, user_id, **kwargs)


personalization_service = PersonalizationService()


# Stable aliases for integrations/tests that use shorter names.
extract_preferences_from_user_text = extract_user_observations
Personalization = PersonalizationService
