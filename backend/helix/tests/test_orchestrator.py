"""Tests for NarrativeOrchestrator.

Uses in-memory SQLite + StaticPool. LLM is always mocked — no real API calls.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from helix.ai.context import ContextSerializer
from sqlalchemy import create_engine
from sqlalchemy.orm import Session as DBSession, sessionmaker
from sqlalchemy.pool import StaticPool

from helix.ai.orchestrator import NarrativeOrchestrator, _build_parameters_hash
from helix.ai.readiness import ReadinessEngine
from helix.ai.schemas import (
    FullFormulation,
    InterInstrumentNarration,
    MissionControlSuggestion,
    TaskType,
)
from helix.db.database import Base
from helix.models.models import AssessmentInstance, Narrative, Score, Session


# ---------------------------------------------------------------------------
# DB fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def engine_mem():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture()
def db_session(engine_mem):
    SessionLocal = sessionmaker(bind=engine_mem, autocommit=False, autoflush=True)
    session = SessionLocal()
    yield session
    session.rollback()
    session.close()


def _make_session_in_db(db: DBSession, *, scored: list[str] | None = None) -> Session:
    """Create a real Session + Score rows in the DB."""
    session = Session(
        id=str(uuid.uuid4()),
        state="EXPLORING",
        intake_data={"red_thread_question": "Why do I feel stuck?", "categories": []},
        anchors={"mood": 5, "energy": 5, "focus": 5},
        narratives_stale=False,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(session)
    db.flush()

    for inst_id in (scored or []):
        inst = AssessmentInstance(
            id=str(uuid.uuid4()),
            session_id=session.id,
            instrument_id=inst_id,
            instrument_version="1.0.0",
            responses={},
            status="COMPLETED",
        )
        db.add(inst)
        db.flush()
        score = Score(
            id=str(uuid.uuid4()),
            assessment_instance_id=inst.id,
            instrument_id=inst_id,
            total_score=5.0,
            band="moderate",
            score_metadata={"n_items_scored": 2},
        )
        db.add(score)

    db.flush()
    return session


def _context_hash_for_session(session: Session) -> str:
    payload = ContextSerializer.build_payload(session)
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


# ---------------------------------------------------------------------------
# _build_parameters_hash
# ---------------------------------------------------------------------------


def test_parameters_hash_stable():
    h1 = _build_parameters_hash(TaskType.PLANET_SUMMARY, planet_id="venus")
    h2 = _build_parameters_hash(TaskType.PLANET_SUMMARY, planet_id="venus")
    assert h1 == h2


def test_parameters_hash_differs_by_task():
    h1 = _build_parameters_hash(TaskType.PLANET_SUMMARY, planet_id="venus")
    h2 = _build_parameters_hash(TaskType.MISSION_CONTROL, planet_id="venus")
    assert h1 != h2


def test_parameters_hash_differs_by_planet():
    h1 = _build_parameters_hash(TaskType.PLANET_SUMMARY, planet_id="venus")
    h2 = _build_parameters_hash(TaskType.PLANET_SUMMARY, planet_id="mars")
    assert h1 != h2


# ---------------------------------------------------------------------------
# Not-ready path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_returns_not_ready_when_readiness_fails(db_session):
    session = _make_session_in_db(db_session, scored=[])
    orchestrator = NarrativeOrchestrator(db_session)

    result = await orchestrator.generate(
        session, TaskType.MISSION_CONTROL
    )

    assert result.ready is False
    assert result.cached is False
    assert result.narrative is None
    assert result.error is None


# ---------------------------------------------------------------------------
# Cache hit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_returns_cached_when_fresh(db_session):
    session = _make_session_in_db(db_session, scored=["phq2", "gad2"])
    orchestrator = NarrativeOrchestrator(db_session)

    cached_output = {"cognitive_reflection": "cached text", "behavioral_observation": "b", "integration_prompt": "c", "safety_triggered": False, "safety_protocol": None}
    params_hash = _build_parameters_hash(TaskType.MISSION_CONTROL)
    narrative_row = Narrative(
        id=str(uuid.uuid4()),
        session_id=session.id,
        task_type=TaskType.MISSION_CONTROL.value,
        parameters_hash=params_hash,
        context_hash=_context_hash_for_session(session),
        output_json=cached_output,
        model_used="gemini-1.5-flash",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(narrative_row)
    db_session.flush()

    result = await orchestrator.generate(session, TaskType.MISSION_CONTROL)

    assert result.ready is True
    assert result.cached is True
    assert result.narrative == cached_output
    assert result.model_used == "gemini-1.5-flash"


# ---------------------------------------------------------------------------
# Cache bypass when stale
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_bypasses_cache_when_stale(db_session):
    session = _make_session_in_db(db_session, scored=["phq2", "gad2"])
    session.narratives_stale = True

    fresh_output = MissionControlSuggestion(
        safety_triggered=False,
        cognitive_reflection="fresh",
        behavioral_observation="fresh b",
        integration_prompt="fresh c",
        safety_protocol=None,
    )

    params_hash = _build_parameters_hash(TaskType.MISSION_CONTROL)
    narrative_row = Narrative(
        id=str(uuid.uuid4()),
        session_id=session.id,
        task_type=TaskType.MISSION_CONTROL.value,
        parameters_hash=params_hash,
        output_json={"cognitive_reflection": "stale", "behavioral_observation": "stale", "integration_prompt": "stale", "safety_triggered": False, "safety_protocol": None},
        model_used="gemini-1.5-flash",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(narrative_row)
    db_session.flush()

    with patch("helix.ai.orchestrator._build_engine") as mock_build_engine:
        mock_engine = MagicMock()
        mock_engine.llm.model_name = "gemini-1.5-flash"
        mock_engine.build_context_payload.return_value = {"session_id": session.id}
        mock_engine.generate_mission_control = AsyncMock(return_value=fresh_output)
        mock_build_engine.return_value = mock_engine

        orchestrator = NarrativeOrchestrator(db_session)
        result = await orchestrator.generate(session, TaskType.MISSION_CONTROL)

    assert result.cached is False
    assert result.narrative["cognitive_reflection"] == "fresh"
    assert session.narratives_stale is False  # cleared after generation


# ---------------------------------------------------------------------------
# force_regenerate bypasses cache
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_force_regenerate_bypasses_cache(db_session):
    session = _make_session_in_db(db_session, scored=["phq2", "gad2"])
    orchestrator = NarrativeOrchestrator(db_session)

    fresh_output = MissionControlSuggestion(
        safety_triggered=False,
        cognitive_reflection="force fresh",
        behavioral_observation="b",
        integration_prompt="c",
        safety_protocol=None,
    )

    params_hash = _build_parameters_hash(TaskType.MISSION_CONTROL)
    narrative_row = Narrative(
        id=str(uuid.uuid4()),
        session_id=session.id,
        task_type=TaskType.MISSION_CONTROL.value,
        parameters_hash=params_hash,
        output_json={"cognitive_reflection": "old", "behavioral_observation": "old", "integration_prompt": "old", "safety_triggered": False, "safety_protocol": None},
        model_used="gemini-1.5-flash",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(narrative_row)
    db_session.flush()

    with patch("helix.ai.orchestrator._build_engine") as mock_build_engine:
        mock_engine = MagicMock()
        mock_engine.llm.model_name = "gemini-1.5-flash"
        mock_engine.build_context_payload.return_value = {"session_id": session.id}
        mock_engine.generate_mission_control = AsyncMock(return_value=fresh_output)
        mock_build_engine.return_value = mock_engine

        result = await orchestrator.generate(session, TaskType.MISSION_CONTROL, force_regenerate=True)

    assert result.cached is False
    assert result.narrative["cognitive_reflection"] == "force fresh"


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_persists_narrative(db_session):
    session = _make_session_in_db(db_session, scored=["phq2", "gad2"])
    orchestrator = NarrativeOrchestrator(db_session)

    fresh_output = MissionControlSuggestion(
        safety_triggered=False,
        cognitive_reflection="persisted text",
        behavioral_observation="b",
        integration_prompt="c",
        safety_protocol=None,
    )

    with patch("helix.ai.orchestrator._build_engine") as mock_build_engine:
        mock_engine = MagicMock()
        mock_engine.llm.model_name = "gemini-2.0-flash"
        mock_engine.build_context_payload.return_value = {"session_id": session.id}
        mock_engine.generate_mission_control = AsyncMock(return_value=fresh_output)
        mock_build_engine.return_value = mock_engine

        result = await orchestrator.generate(session, TaskType.MISSION_CONTROL)

    assert result.ready is True
    assert result.model_used == "gemini-2.0-flash"

    # Verify row was stored
    row = (
        db_session.query(Narrative)
        .filter(
            Narrative.session_id == session.id,
            Narrative.task_type == TaskType.MISSION_CONTROL.value,
        )
        .first()
    )
    assert row is not None
    assert row.output_json["cognitive_reflection"] == "persisted text"
    assert row.model_used == "gemini-2.0-flash"


@pytest.mark.asyncio
async def test_planet_summary_injects_planet_id_into_output_json(db_session):
    """planet_id must be persisted in output_json so the client can filter by planet."""
    from helix.ai.schemas import PlanetSummary

    session = _make_session_in_db(db_session, scored=["phq2", "gad2"])
    orchestrator = NarrativeOrchestrator(db_session)

    planet_output = PlanetSummary(
        core_tendencies="Elevated distress patterns.",
        environmental_interaction="These tendencies appear most pronounced under social pressure.",
        data_sufficiency_met=True,
    )

    with patch("helix.ai.orchestrator._build_engine") as mock_build_engine:
        mock_engine = MagicMock()
        mock_engine.llm.model_name = "test-model"
        mock_engine.build_context_payload.return_value = {"session_id": session.id, "base_scores": []}
        mock_engine.generate_planet_summary = AsyncMock(return_value=planet_output)
        mock_build_engine.return_value = mock_engine

        result = await orchestrator.generate(
            session, TaskType.PLANET_SUMMARY, planet_id="venus"
        )

    assert result.ready is True
    assert result.narrative["planet_id"] == "venus"

    row = (
        db_session.query(Narrative)
        .filter(
            Narrative.session_id == session.id,
            Narrative.task_type == TaskType.PLANET_SUMMARY.value,
        )
        .first()
    )
    assert row is not None
    assert row.output_json["planet_id"] == "venus"


# ---------------------------------------------------------------------------
# LLM error passthrough
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_surfaces_llm_error(db_session):
    session = _make_session_in_db(db_session, scored=["phq2", "gad2"])
    orchestrator = NarrativeOrchestrator(db_session)

    with patch("helix.ai.orchestrator._build_engine") as mock_build_engine:
        mock_engine = MagicMock()
        mock_engine.llm.model_name = "gemini-1.5-flash"
        mock_engine.build_context_payload.return_value = {"session_id": session.id}
        mock_engine.generate_mission_control = AsyncMock(side_effect=RuntimeError("LLM exploded"))
        mock_build_engine.return_value = mock_engine

        result = await orchestrator.generate(session, TaskType.MISSION_CONTROL)

    assert result.ready is True
    assert result.narrative is None
    assert result.error is not None
    assert "LLM exploded" in result.error


@pytest.mark.asyncio
async def test_generate_ignores_cached_row_when_context_hash_differs(db_session):
    session = _make_session_in_db(db_session, scored=["phq2", "gad2"])
    orchestrator = NarrativeOrchestrator(db_session)

    params_hash = _build_parameters_hash(TaskType.MISSION_CONTROL)
    db_session.add(
        Narrative(
            id=str(uuid.uuid4()),
            session_id=session.id,
            task_type=TaskType.MISSION_CONTROL.value,
            parameters_hash=params_hash,
            context_hash="outdated-context-hash",
            output_json={
                "cognitive_reflection": "stale",
                "behavioral_observation": "stale",
                "integration_prompt": "stale",
                "safety_triggered": False,
                "safety_protocol": None,
            },
            model_used="gemini-1.5-flash",
            created_at=datetime.now(timezone.utc),
        )
    )
    db_session.flush()

    fresh_output = MissionControlSuggestion(
        safety_triggered=False,
        cognitive_reflection="fresh via context hash",
        behavioral_observation="b",
        integration_prompt="c",
        safety_protocol=None,
    )

    with patch("helix.ai.orchestrator._build_engine") as mock_build_engine:
        mock_engine = MagicMock()
        mock_engine.llm.model_name = "gemini-1.5-flash"
        mock_engine.build_context_payload.return_value = {"session_id": session.id, "version": 2}
        mock_engine.generate_mission_control = AsyncMock(return_value=fresh_output)
        mock_build_engine.return_value = mock_engine

        result = await orchestrator.generate(session, TaskType.MISSION_CONTROL)

    assert result.cached is False
    assert result.narrative["cognitive_reflection"] == "fresh via context hash"


# ---------------------------------------------------------------------------
# list_narratives / get_narrative
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_narratives(db_session):
    session = _make_session_in_db(db_session, scored=[])
    orchestrator = NarrativeOrchestrator(db_session)

    row = Narrative(
        id=str(uuid.uuid4()),
        session_id=session.id,
        task_type="mission_control",
        parameters_hash="abc123",
        output_json={"x": 1},
        model_used="gemini-1.5-flash",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(row)
    db_session.flush()

    items = orchestrator.list_narratives(session.id)
    assert any(item["task_type"] == "mission_control" for item in items)


@pytest.mark.asyncio
async def test_get_narrative_wrong_session(db_session):
    session = _make_session_in_db(db_session, scored=[])
    other_session = _make_session_in_db(db_session, scored=[])
    orchestrator = NarrativeOrchestrator(db_session)

    row = Narrative(
        id=str(uuid.uuid4()),
        session_id=session.id,
        task_type="mission_control",
        parameters_hash="abc123",
        output_json={"x": 1},
        model_used=None,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(row)
    db_session.flush()

    # get_narrative returns the row; the API layer checks session_id ownership
    fetched = orchestrator.get_narrative(row.id)
    assert fetched is not None
    assert fetched.session_id == session.id
    assert fetched.session_id != other_session.id
