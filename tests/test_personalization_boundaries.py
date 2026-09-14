from __future__ import annotations

import asyncio

from src.core.memory_service import MemoryService
from src.core.personalization_service import (
    extract_user_observations,
    personalization_service,
)
from src.db import SessionLocal
from src.models import CreativeExperience, UserPreference, UserProfile


def test_request_exception_does_not_replace_long_term_profile() -> None:
    user_id = "boundary-user-request-exception"
    project_id = "boundary-project-exception"
    db = SessionLocal()
    try:
        db.query(UserPreference).filter(UserPreference.user_id == user_id).delete()
        db.query(UserProfile).filter(UserProfile.user_id == user_id).delete()
        db.commit()

        observations = extract_user_observations("我喜欢温柔风格，但这次不要圆满结局")
        ending = next(item for item in observations if item["key"] == "ending_tendency")
        style = next(item for item in observations if item["key"] == "emotional_style")
        assert ending["scope"] == "request"
        assert ending["value"] == "avoid:圆满结局"
        assert style["scope"] == "global"

        # Persist the durable style and the bounded exception separately.
        personalization_service.apply_observations(db, user_id, [style])
        request_observations = extract_user_observations(
            "这次不要圆满结局",
            scope="request",
            project_id=project_id,
        )
        personalization_service.apply_observations(db, user_id, request_observations)

        context = personalization_service.build_context(
            db,
            user_id,
            current_request="这次不要圆满结局",
            project_id=project_id,
        )
        assert context["profile"]["emotional_style"] == "温柔"
        assert context["preferences"]["ending_tendency"]["value"] == "avoid:圆满结局"
        assert context["profile"]["ending_tendency"] is None
    finally:
        db.query(CreativeExperience).filter(CreativeExperience.user_id == user_id).delete()
        db.query(UserPreference).filter(UserPreference.user_id == user_id).delete()
        db.query(UserProfile).filter(UserProfile.user_id == user_id).delete()
        db.commit()
        db.close()


def test_experience_deduplication_is_scoped_to_project() -> None:
    user_id = "boundary-user-experience"
    db = SessionLocal()
    try:
        db.query(CreativeExperience).filter(CreativeExperience.user_id == user_id).delete()
        db.commit()

        first = personalization_service.record_experience(
            db,
            user_id,
            applicable_condition="告别场景",
            advice="用动作表达告别",
            user_evidence="用户修改为拥抱",
            project_id="project-a",
        )
        second = personalization_service.record_experience(
            db,
            user_id,
            applicable_condition="告别场景",
            advice="用动作表达告别",
            user_evidence="另一个项目的修改",
            project_id="project-b",
        )
        revised = personalization_service.record_experience(
            db,
            user_id,
            applicable_condition="告别场景",
            advice="用动作表达告别",
            user_evidence="用户再次选择拥抱",
            project_id="project-a",
        )

        assert first.id != second.id
        assert revised.id == first.id
        assert revised.version == 2
        assert [item["evidence"] for item in personalization_service.build_context(db, user_id, project_id="project-a")["experiences"]] == ["用户再次选择拥抱"]
        assert [item["evidence"] for item in personalization_service.build_context(db, user_id, project_id="project-b")["experiences"]] == ["另一个项目的修改"]
    finally:
        db.query(CreativeExperience).filter(CreativeExperience.user_id == user_id).delete()
        db.commit()
        db.close()


def test_mem0_results_without_attributable_user_are_discarded(monkeypatch) -> None:
    service = MemoryService()

    class FakeMem0:
        def search(self, *args, **kwargs):
            return [
                {"memory": "other tenant", "metadata": {"user_id": "other"}},
                {"memory": "unscoped result", "metadata": {}},
            ]

    async def fake_ensure():
        return FakeMem0()

    monkeypatch.setattr(service, "_ensure_mem0", fake_ensure)
    result = asyncio.run(service.search_historical_cases("tenant-a", "告别"))
    assert result == []


def test_user_edits_and_choices_are_valid_learning_evidence() -> None:
    edited = extract_user_observations("把告别改成拥抱", source="user_edit", scope="session", session_id="s-edit")
    chosen = extract_user_observations("我选择用动作表达告别", source="user_choice", scope="session", session_id="s-choice")
    assert any(item["value"] == "拥抱" for item in edited)
    assert any(item["value"] == "用动作表达告别" for item in chosen)
