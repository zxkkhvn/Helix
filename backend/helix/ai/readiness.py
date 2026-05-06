"""Deterministic readiness engine.

Decides whether an AI narrative task should fire for a given session.
No LLM involvement — pure Python logic against pre-computed session state.
All AI generation must pass through this before the LLM is called.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from helix.ai.context import THEME_INSTRUMENT_MAPPING, THEME_THRESHOLD_PARTIAL, THEME_THRESHOLD_RICH
from helix.ai.schemas import TaskType
from helix.models.models import Session
from helix.scoring.planet_state import PLANET_INSTRUMENTS


@dataclass
class ReadinessResult:
    ready: bool
    reason: str | None
    task_type: TaskType
    data_summary: dict = field(default_factory=dict)


class ReadinessEngine:
    """Deterministic gate that decides whether an AI task should fire."""

    # Minimum scored instruments required for FULL_FORMULATION
    FULL_FORMULATION_MIN_INSTRUMENTS = 2
    # Minimum scored instruments for RED_THREAD
    RED_THREAD_MIN_INSTRUMENTS = 3
    # Minimum non-SPARSE themes for FULL_FORMULATION (PARTIAL or RICH)
    FULL_FORMULATION_MIN_NON_SPARSE_THEMES = 2

    def check(
        self,
        session: Session,
        task_type: TaskType,
        *,
        planet_id: str | None = None,
        prev_instrument_id: str | None = None,
        next_instrument_id: str | None = None,
    ) -> ReadinessResult:
        """Evaluate readiness for a specific AI task."""

        # Safety pause blocks all tasks except MISSION_CONTROL.
        # MISSION_CONTROL has a built-in safety-override prompt path.
        if session.state == "SAFETY_PAUSED" and task_type != TaskType.MISSION_CONTROL:
            return ReadinessResult(
                ready=False,
                reason="Session is in safety pause. Acknowledge safety resources before generating narratives.",
                task_type=task_type,
                data_summary={"session_state": session.state},
            )

        scored_instruments = self._scored_instrument_ids(session)

        if task_type in (TaskType.INTER_INSTRUMENT, TaskType.INTER_INSTRUMENT_NARRATION):
            return self._check_inter_instrument(
                session, scored_instruments, prev_instrument_id, next_instrument_id
            )

        if task_type == TaskType.PLANET_SUMMARY:
            return self._check_planet_summary(session, scored_instruments, planet_id)

        if task_type == TaskType.MISSION_CONTROL:
            return self._check_mission_control(session, scored_instruments)

        if task_type == TaskType.FULL_FORMULATION:
            return self._check_full_formulation(session, scored_instruments)

        if task_type == TaskType.RED_THREAD:
            return self._check_red_thread(session, scored_instruments)

        return ReadinessResult(
            ready=False,
            reason=f"Unknown task type: {task_type}",
            task_type=task_type,
        )

    # ------------------------------------------------------------------
    # Per-task readiness checks
    # ------------------------------------------------------------------

    def _check_inter_instrument(
        self,
        session: Session,
        scored: set[str],
        prev_id: str | None,
        next_id: str | None,
    ) -> ReadinessResult:
        if not prev_id or not next_id:
            return ReadinessResult(
                ready=False,
                reason="prev_instrument_id and next_instrument_id are required.",
                task_type=TaskType.INTER_INSTRUMENT_NARRATION,
            )

        if prev_id == next_id:
            return ReadinessResult(
                ready=False,
                reason="prev_instrument_id and next_instrument_id must be different.",
                task_type=TaskType.INTER_INSTRUMENT_NARRATION,
            )

        if prev_id not in scored:
            return ReadinessResult(
                ready=False,
                reason=f"Previous instrument '{prev_id}' has no score in this session.",
                task_type=TaskType.INTER_INSTRUMENT_NARRATION,
                data_summary={"prev_instrument_id": prev_id, "scored_instruments": list(scored)},
            )

        return ReadinessResult(
            ready=True,
            reason=None,
            task_type=TaskType.INTER_INSTRUMENT_NARRATION,
            data_summary={
                "prev_instrument_id": prev_id,
                "next_instrument_id": next_id,
                "prev_scored": True,
            },
        )

    def _check_planet_summary(
        self,
        session: Session,
        scored: set[str],
        planet_id: str | None,
    ) -> ReadinessResult:
        if not planet_id:
            return ReadinessResult(
                ready=False,
                reason="planet_id is required for PLANET_SUMMARY.",
                task_type=TaskType.PLANET_SUMMARY,
            )

        planet_config = PLANET_INSTRUMENTS.get(planet_id)
        if planet_config is None:
            return ReadinessResult(
                ready=False,
                reason=f"Unknown planet: '{planet_id}'.",
                task_type=TaskType.PLANET_SUMMARY,
            )

        all_planet_instruments = (
            planet_config.get("quick_scan", []) + planet_config.get("deep_dive", [])
        )
        scored_on_planet = [inst for inst in all_planet_instruments if inst in scored]
        distinct_count = len(scored_on_planet)

        # Conditional (Uranus) — check if it's accessible at all
        if planet_config.get("conditional") and distinct_count == 0:
            return ReadinessResult(
                ready=False,
                reason=f"Planet '{planet_id}' is locked (conditional planet, no instruments scored).",
                task_type=TaskType.PLANET_SUMMARY,
                data_summary={"planet_id": planet_id, "scored_on_planet": scored_on_planet},
            )

        if distinct_count < 2:
            return ReadinessResult(
                ready=False,
                reason=(
                    f"Planet '{planet_id}' has only {distinct_count} scored instrument(s). "
                    "At least 2 are required for a summary."
                ),
                task_type=TaskType.PLANET_SUMMARY,
                data_summary={"planet_id": planet_id, "scored_on_planet": scored_on_planet},
            )

        return ReadinessResult(
            ready=True,
            reason=None,
            task_type=TaskType.PLANET_SUMMARY,
            data_summary={"planet_id": planet_id, "scored_on_planet": scored_on_planet},
        )

    def _check_mission_control(
        self, session: Session, scored: set[str]
    ) -> ReadinessResult:
        if session.state == "CORE_FLOW_IN_PROGRESS":
            return ReadinessResult(
                ready=False,
                reason="Mission Control is not available during the core flow.",
                task_type=TaskType.MISSION_CONTROL,
                data_summary={"session_state": session.state},
            )

        if not scored:
            return ReadinessResult(
                ready=False,
                reason="No instruments have been scored yet.",
                task_type=TaskType.MISSION_CONTROL,
                data_summary={"scored_instruments_count": 0},
            )

        return ReadinessResult(
            ready=True,
            reason=None,
            task_type=TaskType.MISSION_CONTROL,
            data_summary={"scored_instruments_count": len(scored)},
        )

    def _check_full_formulation(
        self, session: Session, scored: set[str]
    ) -> ReadinessResult:
        if len(scored) < self.FULL_FORMULATION_MIN_INSTRUMENTS:
            return ReadinessResult(
                ready=False,
                reason=(
                    f"Full formulation requires at least "
                    f"{self.FULL_FORMULATION_MIN_INSTRUMENTS} scored instruments. "
                    f"Only {len(scored)} present."
                ),
                task_type=TaskType.FULL_FORMULATION,
                data_summary={"scored_instruments_count": len(scored)},
            )

        theme_states = self._compute_theme_states(scored)
        non_sparse = sum(1 for v in theme_states.values() if v != "SPARSE")

        if non_sparse < self.FULL_FORMULATION_MIN_NON_SPARSE_THEMES:
            return ReadinessResult(
                ready=False,
                reason=(
                    f"Full formulation requires at least "
                    f"{self.FULL_FORMULATION_MIN_NON_SPARSE_THEMES} themes with data "
                    f"(PARTIAL or RICH). Currently {non_sparse} non-sparse theme(s)."
                ),
                task_type=TaskType.FULL_FORMULATION,
                data_summary={"theme_states": theme_states, "non_sparse_count": non_sparse},
            )

        return ReadinessResult(
            ready=True,
            reason=None,
            task_type=TaskType.FULL_FORMULATION,
            data_summary={"theme_states": theme_states, "non_sparse_count": non_sparse},
        )

    def _check_red_thread(
        self, session: Session, scored: set[str]
    ) -> ReadinessResult:
        intake = session.intake_data or {}
        red_thread_question = intake.get("red_thread_question", "")

        if not red_thread_question or red_thread_question.strip() in ("", "[dev]"):
            return ReadinessResult(
                ready=False,
                reason="No guiding question has been provided for this session.",
                task_type=TaskType.RED_THREAD,
                data_summary={"red_thread_question": red_thread_question},
            )

        if len(scored) < self.RED_THREAD_MIN_INSTRUMENTS:
            return ReadinessResult(
                ready=False,
                reason=(
                    f"Red Thread integration requires at least "
                    f"{self.RED_THREAD_MIN_INSTRUMENTS} scored instruments. "
                    f"Only {len(scored)} present."
                ),
                task_type=TaskType.RED_THREAD,
                data_summary={
                    "red_thread_question": red_thread_question,
                    "scored_instruments_count": len(scored),
                },
            )

        return ReadinessResult(
            ready=True,
            reason=None,
            task_type=TaskType.RED_THREAD,
            data_summary={
                "red_thread_question": red_thread_question,
                "scored_instruments_count": len(scored),
            },
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _scored_instrument_ids(session: Session) -> set[str]:
        """Collect the set of instrument IDs that have a Score in this session."""
        scored = set()
        for instance in (session.assessment_instances or []):
            if instance.score is not None:
                scored.add(instance.instrument_id)
        return scored

    @staticmethod
    def _compute_theme_states(scored: set[str]) -> dict[str, str]:
        """Mirror of ContextSerializer._compute_theme_states but operates on a set."""
        states: dict[str, str] = {}
        for theme, instruments in THEME_INSTRUMENT_MAPPING.items():
            count = sum(1 for inst in instruments if inst in scored)
            if count >= THEME_THRESHOLD_RICH:
                states[theme] = "RICH"
            elif count >= THEME_THRESHOLD_PARTIAL:
                states[theme] = "PARTIAL"
            else:
                states[theme] = "SPARSE"
        return states

    def check_all(
        self, session: Session
    ) -> dict[str, Any]:
        """Run readiness checks for all task types and return a summary dict."""
        scored = self._scored_instrument_ids(session)
        results: dict[str, Any] = {}

        simple_tasks = [
            TaskType.MISSION_CONTROL,
            TaskType.FULL_FORMULATION,
            TaskType.RED_THREAD,
        ]
        for task_type in simple_tasks:
            r = self.check(session, task_type)
            results[task_type.value] = {
                "ready": r.ready,
                "reason": r.reason,
                "data_summary": r.data_summary,
            }

        # For PLANET_SUMMARY, report per planet
        planet_summaries: dict[str, Any] = {}
        for planet_id in PLANET_INSTRUMENTS:
            r = self.check(session, TaskType.PLANET_SUMMARY, planet_id=planet_id)
            planet_summaries[planet_id] = {
                "ready": r.ready,
                "reason": r.reason,
                "data_summary": r.data_summary,
            }
        results["planet_summary"] = planet_summaries

        # INTER_INSTRUMENT is param-dependent, report availability heuristic
        results["inter_instrument_narration"] = {
            "ready": len(scored) >= 1,
            "reason": None if scored else "No scored instruments yet.",
            "data_summary": {"scored_instruments_count": len(scored)},
        }

        return results
