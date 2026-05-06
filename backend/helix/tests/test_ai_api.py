"""API integration tests for Phase 3.5 AI endpoints.

Tests /sessions/{id}/ai/readiness, /ai/narrate, /ai/narratives,
and the updated submit response (ai_bridge, ai_readiness on GET session).

Uses the same TestClient + in-memory DB pattern as test_api.py.
LLM is always mocked via dependency override or patch.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session as DBSession, sessionmaker
from sqlalchemy.pool import StaticPool

from helix.db.database import Base, get_db
from helix.main import app
from helix.models.models import AssessmentInstance, Score, Session


# ---------------------------------------------------------------------------
# DB + client fixtures (mirror conftest.py pattern)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def test_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture(scope="module")
def test_session_factory(test_engine):
    return sessionmaker(bind=test_engine, autocommit=False, autoflush=True)


@pytest.fixture()
def db(test_session_factory) -> Generator[DBSession, None, None]:
    session = test_session_factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture()
def client(db) -> TestClient:
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _seed_session(db: DBSession, *, scored: list[str] | None = None) -> str:
    """Create a real Session (EXPLORING) with optional Score rows."""
    session_id = str(uuid.uuid4())
    session = Session(
        id=session_id,
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
            session_id=session_id,
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
    return session_id


# ---------------------------------------------------------------------------
# GET /sessions/{id}/ai/readiness
# ---------------------------------------------------------------------------


def test_ai_readiness_all_returns_200(client, db):
    session_id = _seed_session(db, scored=["phq2", "gad2"])
    resp = client.get(f"/sessions/{session_id}/ai/readiness")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "ai_readiness" in data
    readiness = data["ai_readiness"]
    assert "mission_control" in readiness
    assert "full_formulation" in readiness
    assert "planet_summary" in readiness
    assert "inter_instrument_narration" in readiness


def test_ai_readiness_all_404_unknown_session(client, db):
    resp = client.get("/sessions/nonexistent-id/ai/readiness")
    assert resp.status_code == 404


def test_ai_readiness_single_valid_task(client, db):
    session_id = _seed_session(db, scored=["phq2"])
    resp = client.get(f"/sessions/{session_id}/ai/readiness/mission_control")
    assert resp.status_code == 200
    data = resp.json()
    assert "ready" in data
    assert isinstance(data["ready"], bool)


def test_ai_readiness_single_invalid_task(client, db):
    session_id = _seed_session(db, scored=[])
    resp = client.get(f"/sessions/{session_id}/ai/readiness/fake_task_type")
    assert resp.status_code == 400


def test_ai_readiness_single_not_ready_reason(client, db):
    session_id = _seed_session(db, scored=[])
    resp = client.get(f"/sessions/{session_id}/ai/readiness/mission_control")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ready"] is False
    assert data["reason"] is not None


# ---------------------------------------------------------------------------
# POST /sessions/{id}/ai/narrate — not ready
# ---------------------------------------------------------------------------


def test_ai_narrate_not_ready_returns_200_with_ready_false(client, db):
    session_id = _seed_session(db, scored=[])
    resp = client.post(
        f"/sessions/{session_id}/ai/narrate",
        json={"task_type": "mission_control"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ready"] is False
    assert data["narrative"] is None
    assert data["readiness_reason"] is not None


def test_ai_narrate_planet_summary_missing_planet_id(client, db):
    session_id = _seed_session(db, scored=["phq2", "gad2"])
    resp = client.post(
        f"/sessions/{session_id}/ai/narrate",
        json={"task_type": "planet_summary"},
    )
    assert resp.status_code == 422  # Pydantic validation error


def test_ai_narrate_invalid_task_type(client, db):
    session_id = _seed_session(db, scored=[])
    resp = client.post(
        f"/sessions/{session_id}/ai/narrate",
        json={"task_type": "not_a_real_task"},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /sessions/{id}/ai/narrate — ready, mocked LLM
# ---------------------------------------------------------------------------


def test_ai_narrate_ready_mission_control(client, db):
    from helix.ai.schemas import MissionControlSuggestion

    session_id = _seed_session(db, scored=["phq2", "gad2"])

    mock_result = MissionControlSuggestion(
        safety_triggered=False,
        cognitive_reflection="You might explore when worry and energy dip together.",
        behavioral_observation="Notice what happens just before motivation drops.",
        integration_prompt="How do these patterns connect across your planets?",
        safety_protocol=None,
    )

    with patch("helix.ai.orchestrator._build_engine") as mock_build_engine:
        mock_engine = MagicMock()
        mock_engine.llm.model_name = "gemini-1.5-flash"
        mock_engine.build_context_payload.return_value = {"session_id": session_id}
        mock_engine.generate_mission_control = AsyncMock(return_value=mock_result)
        mock_build_engine.return_value = mock_engine

        resp = client.post(
            f"/sessions/{session_id}/ai/narrate",
            json={"task_type": "mission_control"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["ready"] is True
    assert data["cached"] is False
    assert data["narrative"]["cognitive_reflection"] is not None
    assert data["model_used"] == "gemini-1.5-flash"
    assert data["generation_time_ms"] is not None


def test_ai_narrate_returns_cached_on_second_call(client, db):
    from helix.ai.schemas import MissionControlSuggestion

    session_id = _seed_session(db, scored=["phq2", "gad2"])

    mock_result = MissionControlSuggestion(
        safety_triggered=False,
        cognitive_reflection="Cached reflection.",
        behavioral_observation="Cached observation.",
        integration_prompt="Cached prompt.",
        safety_protocol=None,
    )

    with patch("helix.ai.orchestrator._build_engine") as mock_build_engine:
        mock_engine = MagicMock()
        mock_engine.llm.model_name = "gemini-1.5-flash"
        mock_engine.build_context_payload.return_value = {"session_id": session_id}
        mock_engine.generate_mission_control = AsyncMock(return_value=mock_result)
        mock_build_engine.return_value = mock_engine

        # First call — generates
        resp1 = client.post(
            f"/sessions/{session_id}/ai/narrate",
            json={"task_type": "mission_control"},
        )
        assert resp1.json()["cached"] is False

        # Second call — should hit cache (no new score submitted)
        resp2 = client.post(
            f"/sessions/{session_id}/ai/narrate",
            json={"task_type": "mission_control"},
        )

    assert resp2.status_code == 200
    assert resp2.json()["cached"] is True


# ---------------------------------------------------------------------------
# GET /sessions/{id}/ai/narratives
# ---------------------------------------------------------------------------


def test_list_narratives_empty(client, db):
    session_id = _seed_session(db, scored=[])
    resp = client.get(f"/sessions/{session_id}/ai/narratives")
    assert resp.status_code == 200
    assert resp.json()["narratives"] == []


def test_list_narratives_after_generation(client, db):
    from helix.ai.schemas import MissionControlSuggestion

    session_id = _seed_session(db, scored=["phq2", "gad2"])
    mock_result = MissionControlSuggestion(
        safety_triggered=False,
        cognitive_reflection="x",
        behavioral_observation="y",
        integration_prompt="z",
        safety_protocol=None,
    )

    with patch("helix.ai.orchestrator._build_engine") as mock_build_engine:
        mock_engine = MagicMock()
        mock_engine.llm.model_name = "gemini-1.5-flash"
        mock_engine.build_context_payload.return_value = {"session_id": session_id}
        mock_engine.generate_mission_control = AsyncMock(return_value=mock_result)
        mock_build_engine.return_value = mock_engine

        client.post(f"/sessions/{session_id}/ai/narrate", json={"task_type": "mission_control"})

    resp = client.get(f"/sessions/{session_id}/ai/narratives")
    assert resp.status_code == 200
    narratives = resp.json()["narratives"]
    assert len(narratives) >= 1
    assert narratives[0]["task_type"] == "mission_control"


def test_get_narrative_404_wrong_session(client, db):
    session_id = _seed_session(db, scored=[])
    other_session_id = _seed_session(db, scored=[])
    resp = client.get(f"/sessions/{other_session_id}/ai/narratives/nonexistent-id")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /sessions/{id} — includes ai_readiness
# ---------------------------------------------------------------------------


def test_get_session_includes_ai_readiness(client, db):
    session_id = _seed_session(db, scored=["phq2"])
    resp = client.get(f"/sessions/{session_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert "ai_readiness" in data
    assert isinstance(data["ai_readiness"], dict)
    assert "mission_control" in data["ai_readiness"]


# ---------------------------------------------------------------------------
# POST submit — ai_bridge field present, submit never fails
# ---------------------------------------------------------------------------


def test_submit_response_has_ai_bridge_field(client, db):
    """ai_bridge field always present in submit response (may be null)."""
    session_id = _seed_session(db, scored=[])

    # Patch session state to EXPLORING so bridge can attempt
    sess = db.get(Session, session_id)
    sess.intake_data = {"red_thread_question": "test", "categories": []}
    sess.anchors = {"mood": 5, "energy": 5, "focus": 5}
    db.flush()

    resp = client.post(
        f"/sessions/{session_id}/assessments/phq2/submit",
        json={"responses": {"phq2_01": 1, "phq2_02": 1}},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert "ai_bridge" in data
    # ai_bridge may be None (bridge not ready if next_id not routed) — that's fine


def test_submit_succeeds_even_if_bridge_times_out(client, db):
    """Bridge failure must not propagate as a 500."""
    session_id = _seed_session(db, scored=[])

    sess = db.get(Session, session_id)
    sess.state = "EXPLORING"
    db.flush()

    with patch("helix.ai.orchestrator.NarrativeOrchestrator") as MockOrch:
        mock_orch_instance = MagicMock()
        mock_orch_instance.generate = AsyncMock(side_effect=Exception("bridge exploded"))
        MockOrch.return_value = mock_orch_instance

        resp = client.post(
            f"/sessions/{session_id}/assessments/phq2/submit",
            json={"responses": {"phq2_01": 1, "phq2_02": 1}},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert "assessment_instance_id" in data
    assert data["ai_bridge"] is None
