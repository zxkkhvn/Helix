"""Tests for ReadinessEngine — deterministic only, no mocks needed."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, PropertyMock

import pytest

from helix.ai.readiness import ReadinessEngine
from helix.ai.schemas import TaskType
from helix.models.models import AssessmentInstance, Narrative, Score, Session


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session(
    *,
    state: str = "EXPLORING",
    intake_data: dict | None = None,
    safety_flags: list | None = None,
    scored_instruments: list[str] | None = None,
) -> Session:
    """Build a mock Session with assessment_instances populated from scored_instruments."""
    session = MagicMock(spec=Session)
    session.id = str(uuid.uuid4())
    session.state = state
    session.intake_data = intake_data if intake_data is not None else {"red_thread_question": "Why do I feel overwhelmed?", "categories": []}
    session.safety_flags = safety_flags
    session.narratives_stale = False
    session.anchors = None

    instances = []
    for inst_id in (scored_instruments or []):
        score = MagicMock(spec=Score)
        score.instrument_id = inst_id
        inst = MagicMock(spec=AssessmentInstance)
        inst.instrument_id = inst_id
        inst.score = score
        instances.append(inst)

    session.assessment_instances = instances
    return session


engine = ReadinessEngine()


# ---------------------------------------------------------------------------
# Safety override tests
# ---------------------------------------------------------------------------


def test_safety_pause_blocks_full_formulation():
    session = _make_session(state="SAFETY_PAUSED", scored_instruments=["phq2", "gad2", "phq9", "gad7"])
    result = engine.check(session, TaskType.FULL_FORMULATION)
    assert result.ready is False
    assert "safety pause" in (result.reason or "").lower()


def test_safety_pause_does_not_block_mission_control():
    """MISSION_CONTROL has its own safety-override prompt path — readiness engine allows it through."""
    session = _make_session(state="SAFETY_PAUSED", scored_instruments=["phq2", "gad2"])
    result = engine.check(session, TaskType.MISSION_CONTROL)
    # Not blocked by the safety-pause guard; the mission_control check itself may still fail
    # if no scored instruments, but it isn't filtered by the safety-pause guard.
    assert result.reason != "Session is in safety pause. Acknowledge safety resources before generating narratives."


def test_safety_pause_blocks_planet_summary():
    session = _make_session(state="SAFETY_PAUSED", scored_instruments=["phq2", "gad2"])
    result = engine.check(session, TaskType.PLANET_SUMMARY, planet_id="venus")
    assert result.ready is False
    assert "safety pause" in (result.reason or "").lower()


def test_safety_pause_blocks_red_thread():
    session = _make_session(state="SAFETY_PAUSED", scored_instruments=["phq2", "gad2", "gad7"])
    result = engine.check(session, TaskType.RED_THREAD)
    assert result.ready is False


def test_safety_pause_blocks_inter_instrument():
    session = _make_session(state="SAFETY_PAUSED", scored_instruments=["phq2"])
    result = engine.check(session, TaskType.INTER_INSTRUMENT_NARRATION, prev_instrument_id="phq2", next_instrument_id="gad2")
    assert result.ready is False


# ---------------------------------------------------------------------------
# INTER_INSTRUMENT_NARRATION
# ---------------------------------------------------------------------------


def test_inter_instrument_ready_when_prev_scored():
    session = _make_session(scored_instruments=["phq2"])
    result = engine.check(session, TaskType.INTER_INSTRUMENT_NARRATION, prev_instrument_id="phq2", next_instrument_id="gad2")
    assert result.ready is True
    assert result.reason is None


def test_inter_instrument_not_ready_when_prev_not_scored():
    session = _make_session(scored_instruments=["gad2"])
    result = engine.check(session, TaskType.INTER_INSTRUMENT_NARRATION, prev_instrument_id="phq2", next_instrument_id="gad2")
    assert result.ready is False
    assert "phq2" in (result.reason or "")


def test_inter_instrument_not_ready_missing_params():
    session = _make_session(scored_instruments=["phq2"])
    result = engine.check(session, TaskType.INTER_INSTRUMENT_NARRATION)
    assert result.ready is False
    assert "required" in (result.reason or "").lower()


def test_inter_instrument_not_ready_same_instrument():
    session = _make_session(scored_instruments=["phq2"])
    result = engine.check(session, TaskType.INTER_INSTRUMENT_NARRATION, prev_instrument_id="phq2", next_instrument_id="phq2")
    assert result.ready is False
    assert "different" in (result.reason or "").lower()


# ---------------------------------------------------------------------------
# PLANET_SUMMARY
# ---------------------------------------------------------------------------


def test_planet_summary_ready_with_2_instruments():
    session = _make_session(scored_instruments=["phq2", "gad2"])
    result = engine.check(session, TaskType.PLANET_SUMMARY, planet_id="venus")
    assert result.ready is True


def test_planet_summary_not_ready_with_1_instrument():
    session = _make_session(scored_instruments=["phq2"])
    result = engine.check(session, TaskType.PLANET_SUMMARY, planet_id="venus")
    assert result.ready is False
    assert "1 scored instrument" in (result.reason or "")


def test_planet_summary_not_ready_no_instruments():
    session = _make_session(scored_instruments=[])
    result = engine.check(session, TaskType.PLANET_SUMMARY, planet_id="venus")
    assert result.ready is False


def test_planet_summary_requires_planet_id():
    session = _make_session(scored_instruments=["phq2", "gad2"])
    result = engine.check(session, TaskType.PLANET_SUMMARY)
    assert result.ready is False
    assert "planet_id" in (result.reason or "")


def test_planet_summary_unknown_planet():
    session = _make_session(scored_instruments=["phq2", "gad2"])
    result = engine.check(session, TaskType.PLANET_SUMMARY, planet_id="pluto")
    assert result.ready is False
    assert "Unknown planet" in (result.reason or "")


def test_planet_summary_locked_conditional_planet_with_no_instruments():
    """Uranus is conditional — not ready when no Uranus instruments scored."""
    session = _make_session(scored_instruments=["phq2", "gad2"])
    result = engine.check(session, TaskType.PLANET_SUMMARY, planet_id="uranus")
    assert result.ready is False
    assert "locked" in (result.reason or "").lower()


def test_planet_summary_conditional_planet_with_instruments():
    """Uranus becomes eligible when 2+ instruments are scored."""
    session = _make_session(scored_instruments=["aq10", "catq"])
    result = engine.check(session, TaskType.PLANET_SUMMARY, planet_id="uranus")
    assert result.ready is True


# ---------------------------------------------------------------------------
# MISSION_CONTROL
# ---------------------------------------------------------------------------


def test_mission_control_ready_in_exploring_with_scores():
    session = _make_session(state="EXPLORING", scored_instruments=["phq2"])
    result = engine.check(session, TaskType.MISSION_CONTROL)
    assert result.ready is True


def test_mission_control_not_ready_core_flow():
    session = _make_session(state="CORE_FLOW_IN_PROGRESS", scored_instruments=["pbat"])
    result = engine.check(session, TaskType.MISSION_CONTROL)
    assert result.ready is False
    assert "core flow" in (result.reason or "").lower()


def test_mission_control_not_ready_no_scores():
    session = _make_session(state="EXPLORING", scored_instruments=[])
    result = engine.check(session, TaskType.MISSION_CONTROL)
    assert result.ready is False
    assert "No instruments" in (result.reason or "")


# ---------------------------------------------------------------------------
# FULL_FORMULATION
# ---------------------------------------------------------------------------


def test_full_formulation_not_ready_too_few_instruments():
    session = _make_session(scored_instruments=["phq2"])
    result = engine.check(session, TaskType.FULL_FORMULATION)
    assert result.ready is False
    assert "2 scored instruments" in (result.reason or "") or "least" in (result.reason or "")


def test_full_formulation_not_ready_all_themes_sparse():
    # Only 1 instrument per theme — all themes will be SPARSE
    session = _make_session(scored_instruments=["phq2", "ius12"])
    result = engine.check(session, TaskType.FULL_FORMULATION)
    assert result.ready is False
    assert "PARTIAL or RICH" in (result.reason or "") or "non-sparse" in (result.reason or "")


def test_full_formulation_ready_with_partial_themes():
    # phq2, phq9, gad2, gad7 → current_distress = RICH (4 instruments)
    # Also need 2nd partial theme — add ius12 + ptq10 → maintaining_processes PARTIAL
    session = _make_session(scored_instruments=["phq2", "phq9", "gad2", "gad7", "ius12", "ptq10"])
    result = engine.check(session, TaskType.FULL_FORMULATION)
    assert result.ready is True


# ---------------------------------------------------------------------------
# RED_THREAD
# ---------------------------------------------------------------------------


def test_red_thread_ready_with_question_and_3_instruments():
    session = _make_session(
        intake_data={"red_thread_question": "Why do I struggle with motivation?"},
        scored_instruments=["phq2", "gad2", "vlq"],
    )
    result = engine.check(session, TaskType.RED_THREAD)
    assert result.ready is True


def test_red_thread_not_ready_no_question():
    session = _make_session(
        intake_data={"red_thread_question": ""},
        scored_instruments=["phq2", "gad2", "vlq"],
    )
    result = engine.check(session, TaskType.RED_THREAD)
    assert result.ready is False
    assert "guiding question" in (result.reason or "").lower()


def test_red_thread_not_ready_dev_placeholder():
    session = _make_session(
        intake_data={"red_thread_question": "[dev]"},
        scored_instruments=["phq2", "gad2", "vlq"],
    )
    result = engine.check(session, TaskType.RED_THREAD)
    assert result.ready is False


def test_red_thread_not_ready_too_few_instruments():
    session = _make_session(
        intake_data={"red_thread_question": "Why do I struggle?"},
        scored_instruments=["phq2", "gad2"],
    )
    result = engine.check(session, TaskType.RED_THREAD)
    assert result.ready is False
    assert "3 scored instruments" in (result.reason or "") or "least" in (result.reason or "")


def test_red_thread_not_ready_no_intake():
    session = _make_session(intake_data={}, scored_instruments=["phq2", "gad2", "vlq"])
    result = engine.check(session, TaskType.RED_THREAD)
    assert result.ready is False


# ---------------------------------------------------------------------------
# check_all
# ---------------------------------------------------------------------------


def test_check_all_returns_all_task_types():
    session = _make_session(scored_instruments=[])
    summary = engine.check_all(session)

    assert "mission_control" in summary
    assert "full_formulation" in summary
    assert "red_thread" in summary
    assert "planet_summary" in summary
    assert "inter_instrument_narration" in summary

    # All planets present in planet_summary
    from helix.scoring.planet_state import PLANET_INSTRUMENTS
    for planet_id in PLANET_INSTRUMENTS:
        assert planet_id in summary["planet_summary"]


def test_check_all_ready_flags_correct_type():
    session = _make_session(scored_instruments=["phq2"])
    summary = engine.check_all(session)
    assert isinstance(summary["mission_control"]["ready"], bool)
    assert isinstance(summary["planet_summary"]["venus"]["ready"], bool)
