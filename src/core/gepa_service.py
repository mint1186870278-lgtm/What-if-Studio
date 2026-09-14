"""Small, auditable GEPA-style prompt optimisation loop.

The service deliberately does not mutate model weights or call a second model.
It records prompt candidates and evaluates them against a fixed case set using
deterministic checks.  A production deployment can replace ``score_case`` with
an API evaluator while retaining the same candidate/evaluation/publish contract.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _store_path() -> Path:
    path = Path(os.getenv("GEPA_STORE_PATH", "./storage/gepa"))
    path.mkdir(parents=True, exist_ok=True)
    return path / "registry.json"


@dataclass
class PromptCandidate:
    id: str
    strategy: str
    version: int
    prompt_template: str
    model: str
    budget: int
    status: str = "draft"  # draft -> evaluated -> published/archived
    created_at: str = field(default_factory=_now)
    independent_evaluation: dict[str, Any] | None = None


@dataclass
class EvaluationRun:
    id: str
    candidate_id: str
    stage: str  # profile_baseline | experience | optimized
    model: str
    budget: int
    case_count: int
    metrics: dict[str, float]
    held_out: bool = False
    created_at: str = field(default_factory=_now)


class GEPAService:
    """File-backed registry suitable for local/dev and easy DB replacement."""

    def __init__(self, path: Path | None = None):
        self.path = path or _store_path()
        self._lock = threading.RLock()

    @property
    def model(self) -> str:
        return os.getenv("GEPA_MODEL", os.getenv("OPENAI_MODEL", "fixed-evaluator"))

    @property
    def budget(self) -> int:
        try:
            return max(1, int(os.getenv("GEPA_BUDGET", "3")))
        except ValueError:
            return 3

    def _read(self) -> dict[str, Any]:
        with self._lock:
            if not self.path.exists():
                return {"candidates": [], "evaluations": [], "executions": []}
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    raise ValueError("registry root must be an object")
                data.setdefault("candidates", [])
                data.setdefault("evaluations", [])
                data.setdefault("executions", [])
                return data
            except (OSError, ValueError, json.JSONDecodeError):
                return {"candidates": [], "evaluations": [], "executions": []}

    def _write(self, value: Mapping[str, Any]) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # A per-process lock plus replace keeps concurrent API requests
            # from truncating the registry.  The replace is atomic on the
            # filesystems supported by the local deployment.
            tmp = self.path.with_suffix(f".{os.getpid()}.tmp")
            tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.path)

    def config(self) -> dict[str, Any]:
        return {"model": self.model, "budget": self.budget, "store": str(self.path)}

    def create_candidate(self, strategy: str, prompt_template: str, *, model: str | None = None, budget: int | None = None) -> PromptCandidate:
        strategy = str(strategy or "").strip()
        prompt_template = str(prompt_template or "").strip()
        if not strategy or not prompt_template:
            raise ValueError("strategy and prompt_template are required")
        with self._lock:
            data = self._read()
            versions = [c.get("version", 0) for c in data["candidates"] if c.get("strategy") == strategy]
            candidate = PromptCandidate(
                id=str(uuid.uuid4()),
                strategy=strategy,
                version=max(versions, default=0) + 1,
                prompt_template=prompt_template,
                model=model or self.model,
                budget=budget or self.budget,
            )
            data["candidates"].append(asdict(candidate))
            self._write(data)
            return candidate

    def get_published_prompt(self, strategy: str) -> str | None:
        """Return the newest published prompt for a strategy.

        The graph calls this at node execution time, so publishing a candidate
        affects new runs without mutating code or already-checkpointed runs.
        """
        rows = [
            c for c in self._read().get("candidates", [])
            if c.get("strategy") == strategy and c.get("status") == "published"
        ]
        if not rows:
            return None
        rows.sort(key=lambda c: (int(c.get("version", 0)), c.get("created_at", "")), reverse=True)
        prompt = str(rows[0].get("prompt_template") or "").strip()
        return prompt or None

    def record_execution(
        self,
        strategy: str,
        case: Mapping[str, Any],
        outcome: Mapping[str, Any],
        *,
        candidate_id: str | None = None,
    ) -> dict[str, Any]:
        """Record an execution outcome used as GEPA mutation evidence.

        This is intentionally append-only and redacts oversized text.  It
        gives operators a durable source of real feedback/execution traces
        without treating generated text as a user preference.
        """
        with self._lock:
            data = self._read()
            row = {
                "id": str(uuid.uuid4()),
                "strategy": str(strategy),
                "candidate_id": candidate_id,
                "case": dict(case),
                "outcome": dict(outcome),
                "created_at": _now(),
            }
            data.setdefault("executions", []).append(row)
            # Keep the registry bounded for local deployments.
            data["executions"] = data["executions"][-2000:]
            self._write(data)
            return row

    def propose_candidate(
        self,
        strategy: str,
        cases: Iterable[Mapping[str, Any]],
        *,
        seed_prompt: str | None = None,
        model: str | None = None,
        budget: int | None = None,
    ) -> PromptCandidate:
        """Create a mutation candidate from observed failure signals.

        GEPA can later replace this deterministic mutator with an API model;
        the candidate/evaluation/publish contract stays identical.  The
        mutation only adds instructions supported by the supplied cases, so a
        missing provider still produces a reviewable proposal.
        """
        strategy = str(strategy or "").strip()
        if not strategy:
            raise ValueError("strategy is required")
        rows = [dict(c) for c in cases]
        if not rows:
            # When called without an explicit case set, derive reviewable
            # mutations from the bounded execution ledger.  Execution traces
            # are optimization evidence only; they never enter the SQL
            # personalization store as user preference evidence.
            rows = [
                {
                    **(item.get("case") or {}),
                    "outcome": item.get("outcome") or {},
                }
                for item in self._read().get("executions", [])[-100:]
            ]
        base = (seed_prompt or self.get_published_prompt(strategy) or "").strip()
        if not base:
            base = {
                "preference_extraction": "Extract only user-authored preferences; preserve one-off exceptions and scope.",
                "question_policy": "Ask only actionable questions at meaningful creative disagreements; avoid repeats.",
                "director_writing": "Follow the shared CreativeBrief priority order and confirmed decisions.",
            }.get(strategy, "Follow the shared CreativeBrief and cite user evidence.")

        hints: list[str] = []
        for case in rows:
            if case.get("hard_constraints"):
                hints.append("Treat hard_constraints as binding and keep exceptions request-scoped.")
            if case.get("expected_questions"):
                hints.append("Ask a question only when the expected ambiguity is actionable; include options and free text.")
            if case.get("experience_hints"):
                hints.append("Use experience_hints as conditional advice, never as a hard requirement.")
        additions = list(dict.fromkeys(hints))
        prompt = base
        if additions:
            prompt = f"{base}\n\nGEPA refinement rules:\n" + "\n".join(f"- {item}" for item in additions)

        # Optional API-backed mutation.  It is opt-in so local tests and
        # offline deployments stay deterministic; failures fall back to the
        # auditable rule-based proposal above.
        if os.getenv("GEPA_USE_API", "false").strip().lower() in {"1", "true", "yes", "on"}:
            try:
                from src.config import settings
                from openai import OpenAI

                api_key = (
                    settings.openai_api_key
                    or settings.deepseek_api_key
                    or settings.siliconflow_api_key
                    or settings.zhipu_api_key
                )
                base_url = settings.openai_base_url or settings.deepseek_base_url
                if api_key:
                    client = OpenAI(api_key=api_key, base_url=base_url or None)
                    response = client.chat.completions.create(
                        model=model or self.model,
                        messages=[
                            {"role": "system", "content": "Rewrite only the prompt. Return plain text, no markdown fence."},
                            {"role": "user", "content": f"Base prompt:\n{prompt}\n\nCases:\n{json.dumps(rows[:20], ensure_ascii=False)}"},
                        ],
                        temperature=0.2,
                        max_tokens=max(64, min(2000, int((budget or self.budget) * 256))),
                    )
                    generated = str(response.choices[0].message.content or "").strip()
                    if generated:
                        prompt = generated
            except Exception:
                # Keep proposal creation available when the evaluator API is
                # unavailable; independent evaluation still gates publishing.
                pass
        return self.create_candidate(strategy, prompt, model=model, budget=budget)

    def list_candidates(self) -> list[dict[str, Any]]:
        return self._read()["candidates"]

    @staticmethod
    def score_case(case: Mapping[str, Any], stage: str, prompt_template: str) -> dict[str, float]:
        """Score preference extraction/question decisions without model drift.

        Cases may provide ``expected_preferences`` and ``expected_questions``;
        matching is intentionally transparent and deterministic.
        """
        expected_p = {str(x).strip().lower() for x in case.get("expected_preferences", [])}
        expected_q = {str(x).strip().lower() for x in case.get("expected_questions", [])}
        text = str(case.get("user_text") or case.get("prompt") or "").lower()
        # Stage adds progressively richer context.  The marker is useful for
        # smoke tests and can be replaced by an API evaluator later.
        hints = set()
        if stage in {"experience", "optimized"}:
            hints.update(str(x).lower() for x in case.get("experience_hints", []))
        if stage == "optimized":
            hints.update(str(x).lower() for x in case.get("optimized_hints", []))
        found_p = {x for x in expected_p if x in text or x in hints or x in prompt_template.lower()}
        expected_questions = len(expected_q)
        prompt_lower = prompt_template.lower()
        question_hit = (
            expected_questions == 0
            or bool(expected_q & hints)
            or any(token in prompt_lower for token in expected_q)
        )
        constraints = [str(x).lower() for x in case.get("hard_constraints", [])]
        if not constraints:
            constraint_score = 1.0
        elif stage == "profile_baseline":
            constraint_score = 0.0
        else:
            # The optimized/experience stages only receive credit when the
            # prompt explicitly tells the evaluator how to preserve binding
            # constraints or exceptions.
            constraint_score = 1.0 if any(
                token in prompt_lower
                for token in ("constraint", "exception", "硬约束", "例外", "binding")
            ) else 0.5
        return {
            "preference_precision": len(found_p) / max(1, len(expected_p)),
            "question_decision_accuracy": 1.0 if question_hit else 0.0,
            "constraint_adherence": constraint_score,
        }

    def evaluate(
        self,
        candidate_id: str,
        cases: Iterable[Mapping[str, Any]],
        *,
        stage: str = "optimized",
        independent: bool = False,
        independent_cases: Iterable[Mapping[str, Any]] | None = None,
    ) -> EvaluationRun:
        with self._lock:
            data = self._read()
            candidate = next((c for c in data["candidates"] if c.get("id") == candidate_id), None)
            if candidate is None:
                raise KeyError(f"Unknown prompt candidate: {candidate_id}")
            held_out_cases = list(independent_cases) if independent and independent_cases is not None else None
            held_out = bool(held_out_cases)
            cases = held_out_cases if held_out_cases is not None else list(cases)
            rows = [self.score_case(c, stage, candidate.get("prompt_template", "")) for c in cases]
            metric_keys = rows[0] if rows else {"preference_precision": 0.0, "question_decision_accuracy": 0.0, "constraint_adherence": 0.0}
            metrics = {k: round(sum(r[k] for r in rows) / max(1, len(rows)), 4) for k in metric_keys}
            run = EvaluationRun(
                str(uuid.uuid4()),
                candidate_id,
                stage,
                candidate.get("model", self.model),
                int(candidate.get("budget", self.budget)),
                len(cases),
                metrics,
                held_out=held_out,
            )
            data["evaluations"].append(asdict(run))
            if independent:
                candidate["independent_evaluation"] = asdict(run)
                candidate["status"] = "evaluated"
            self._write(data)
            return run

    def compare_stages(self, candidate_id: str, cases: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
        cases = list(cases)
        runs = [self.evaluate(candidate_id, cases, stage=s) for s in ("profile_baseline", "experience", "optimized")]
        return {"candidate_id": candidate_id, "model": self.model, "budget": self.budget, "runs": [asdict(r) for r in runs]}

    def publish(self, candidate_id: str, *, min_score: float = 0.7) -> dict[str, Any]:
        with self._lock:
            data = self._read()
            candidate = next((c for c in data["candidates"] if c.get("id") == candidate_id), None)
            if candidate is None:
                raise KeyError(f"Unknown prompt candidate: {candidate_id}")
            evaluation = candidate.get("independent_evaluation") or {}
            metrics = evaluation.get("metrics") or {}
            score = sum(metrics.values()) / max(1, len(metrics))
            if not evaluation or not evaluation.get("held_out"):
                raise ValueError("independent held-out evaluation is required before publishing")
            if score < min_score or any(value < min_score for value in metrics.values()):
                raise ValueError("independent evaluation did not meet publish threshold")
            for row in data["candidates"]:
                if row.get("strategy") == candidate.get("strategy") and row.get("status") == "published":
                    row["status"] = "archived"
            candidate["status"] = "published"
            self._write(data)
            return candidate


gepa_service = GEPAService()
