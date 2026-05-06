import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import helix.models.models  # noqa: F401
from helix.api.routes_debug import router as debug_router
from helix.db.database import Base, get_db
from helix.models.models import Session
from helix.ai.schemas import (
    FullFormulation,
    InterInstrumentNarration,
    MissionControlSuggestion,
    PlanetSummary,
    TaskType,
)


@pytest.fixture(scope="function")
def debug_client(monkeypatch, _bootstrap_registry):
    monkeypatch.setenv("DEBUG_MODE", "true")

    app = FastAPI()
    app.include_router(debug_router)

    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(test_engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=True) as client:
        yield client, TestingSession
    app.dependency_overrides.clear()
    Base.metadata.drop_all(test_engine)


def _insert_session(session_factory) -> str:
    session_id = str(uuid.uuid4())
    db = session_factory()
    try:
        row = Session(
            id=session_id,
            state="EXPLORING",
            intake_data={"red_thread_question": "What keeps this pattern going?"},
            anchors={"mood": 5, "energy": 5, "focus": 5},
            safety_flags=None,
        )
        db.add(row)
        db.commit()
        return session_id
    finally:
        db.close()


def test_debug_context_endpoint_returns_required_contract_keys(debug_client):
    client, session_factory = debug_client
    session_id = _insert_session(session_factory)

    response = client.get(f"/debug/sessions/{session_id}/ai/context")
    assert response.status_code == 200
    body = response.json()
    payload = body["context_payload"]

    assert body["ok"] is True
    assert body["session_id"] == session_id
    assert "theme_states" in payload
    assert "safety_markers" in payload
    assert "completion_state" in payload
    assert "pbat_profile" in payload
    assert "base_scores" in payload
    assert "composite_indices" in payload


def test_prompt_preview_requires_task_specific_parameters(debug_client):
    client, session_factory = debug_client
    session_id = _insert_session(session_factory)

    missing_planet = client.post(
        f"/debug/sessions/{session_id}/ai/prompt-preview",
        json={"task_type": "planet_summary"},
    )
    assert missing_planet.status_code == 422

    missing_next = client.post(
        f"/debug/sessions/{session_id}/ai/prompt-preview",
        json={"task_type": "inter_instrument_narration", "prev_instrument_id": "phq2"},
    )
    assert missing_next.status_code == 422

    valid_full = client.post(
        f"/debug/sessions/{session_id}/ai/prompt-preview",
        json={"task_type": "full_formulation"},
    )
    assert valid_full.status_code == 200


def test_prompt_preview_does_not_require_llm(monkeypatch, debug_client):
    client, session_factory = debug_client
    session_id = _insert_session(session_factory)
    seen = {}

    fake_engine = MagicMock()
    fake_engine.build_prompt_preview.return_value = {
        "task_type": TaskType.FULL_FORMULATION,
        "context_payload": {"theme_states": {}},
        "task_parameters": {},
        "system": "system-rules",
        "assembled_user_prompt": "<xml/>",
    }

    def fake_build_engine(task_type, require_llm=True):
        seen["task_type"] = task_type
        seen["require_llm"] = require_llm
        return fake_engine

    monkeypatch.setattr("helix.api.routes_debug._build_formulation_engine", fake_build_engine)

    response = client.post(
        f"/debug/sessions/{session_id}/ai/prompt-preview",
        json={"task_type": "full_formulation"},
    )

    assert response.status_code == 200
    assert seen["require_llm"] is False
    fake_engine.build_prompt_preview.assert_called_once()


@pytest.mark.parametrize(
    "path,body,task_type,method_name,model_instance",
    [
        (
            "full-formulation",
            None,
            TaskType.FULL_FORMULATION,
            "generate_full_formulation",
            FullFormulation(
                safety_paragraph=None,
                theme_1_current_distress="a",
                theme_2_maintaining_processes="b",
                theme_3_relational_cognitive_patterns="c",
                theme_4_values_and_friction="d",
                theme_5_protective_resources="e",
                so_what_layer="f",
            ),
        ),
        (
            "planet-summary",
            {"planet_id": "venus"},
            TaskType.PLANET_SUMMARY,
            "generate_planet_summary",
            PlanetSummary(
                core_tendencies="Insufficient data available in the current profile to generate a comprehensive summary for this domain.",
                environmental_interaction="Insufficient data available in the current profile to generate a comprehensive summary for this domain.",
                data_sufficiency_met=False,
            ),
        ),
        (
            "mission-control",
            None,
            TaskType.MISSION_CONTROL,
            "generate_mission_control",
            MissionControlSuggestion(
                safety_triggered=False,
                cognitive_reflection="x",
                behavioral_observation="y",
                integration_prompt="z",
                safety_protocol=None,
            ),
        ),
        (
            "inter-instrument-narration",
            {"prev_instrument_id": "phq2", "next_instrument_id": "gad2"},
            TaskType.INTER_INSTRUMENT_NARRATION,
            "generate_inter_instrument_narration",
            InterInstrumentNarration(
                convergent_narrative="x",
                divergent_narrative="y",
                composite_reflection="z",
            ),
        ),
    ],
)
def test_generation_endpoints_delegate_to_expected_engine_method(
    monkeypatch, debug_client, path, body, task_type, method_name, model_instance
):
    client, session_factory = debug_client
    session_id = _insert_session(session_factory)

    fake_engine = MagicMock()
    fake_engine.build_prompt_preview.return_value = {
        "task_type": task_type,
        "context_payload": {"safety_markers": {"self_harm": False, "acute_trauma": False, "severe_distress": False}},
        "task_parameters": body or {},
        "system": "system-rules",
        "assembled_user_prompt": "<xml/>",
    }
    fake_engine.generate_full_formulation = AsyncMock(return_value=model_instance)
    fake_engine.generate_planet_summary = AsyncMock(return_value=model_instance)
    fake_engine.generate_mission_control = AsyncMock(return_value=model_instance)
    fake_engine.generate_inter_instrument_narration = AsyncMock(return_value=model_instance)

    def fake_build_engine(_task_type, require_llm=True):
        assert require_llm is True
        return fake_engine

    monkeypatch.setattr("helix.api.routes_debug._build_formulation_engine", fake_build_engine)

    if body is None:
        response = client.post(f"/debug/sessions/{session_id}/ai/{path}")
    else:
        response = client.post(f"/debug/sessions/{session_id}/ai/{path}", json=body)

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["task_type"] == task_type.value
    assert payload["session_id"] == session_id
    assert payload["safety_markers_present"] is False
    assert "context_payload" in payload
    assert "prompt" in payload
    assert "raw_response" in payload
    assert "validated_output" in payload
    assert payload["validation_error"] is None
    if task_type == TaskType.PLANET_SUMMARY:
        assert payload["data_sufficiency_met"] is False

    getattr(fake_engine, method_name).assert_called_once()


def test_inter_instrument_generation_requires_prev_next(debug_client):
    client, session_factory = debug_client
    session_id = _insert_session(session_factory)

    response = client.post(
        f"/debug/sessions/{session_id}/ai/inter-instrument-narration",
        json={"prev_instrument_id": "phq2"},
    )
    assert response.status_code == 422
