from src.core.gepa_service import GEPAService
import pytest


def test_gepa_compare_and_publish(tmp_path):
    service = GEPAService(tmp_path / "registry.json")
    candidate = service.create_candidate("preference_extraction", "extract preferences; preserve exceptions")
    cases = [
        {
            "user_text": "我喜欢温柔风格，但这次不要圆满结局",
            "expected_preferences": ["温柔"],
            "expected_questions": ["ending"],
            "experience_hints": ["ending"],
            "optimized_hints": ["ending"],
            "hard_constraints": ["不要圆满结局"],
        }
    ]
    result = service.compare_stages(candidate.id, cases)
    assert [r["stage"] for r in result["runs"]] == ["profile_baseline", "experience", "optimized"]
    independent = service.evaluate(candidate.id, cases, independent=True, independent_cases=cases)
    assert independent.metrics["preference_precision"] >= 0
    published = service.publish(candidate.id, min_score=0)
    assert published["status"] == "published"


def test_gepa_publish_requires_held_out_evaluation(tmp_path):
    service = GEPAService(tmp_path / "registry.json")
    candidate = service.create_candidate("question_policy", "ask only actionable questions")
    cases = [{"user_text": "无关内容", "expected_preferences": ["温柔"]}]
    evaluation = service.evaluate(
        candidate.id,
        cases,
        independent=True,
        independent_cases=cases,
    )
    assert evaluation.metrics["preference_precision"] == 0
    with pytest.raises(ValueError, match="independent evaluation"):
        service.publish(candidate.id)
