"""API integration tests — full Venus flow over HTTP.

Uses FastAPI TestClient with an in-memory SQLite database.
The scorer registry is bootstrapped by the app's lifespan handler.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import helix.models.models  # noqa: F401 — ensures Base.metadata is populated
from helix.db.database import Base, get_db
from helix.main import app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function")
def client(_bootstrap_registry):
    """TestClient backed by a fresh in-memory SQLite database.

    Bypasses the app lifespan to avoid create_tables() running against the
    real engine. Tables are created manually here against the test engine.
    Registry is bootstrapped by the session-scoped _bootstrap_registry fixture.
    """
    # Import models so SQLAlchemy metadata knows all table definitions
    import helix.models.models  # noqa: F401

    from helix.db.database import Base, get_db
    from helix.main import app

    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # all connections share the same in-memory DB
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
    # Use raise_server_exceptions=True so test failures are clear
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()
    Base.metadata.drop_all(test_engine)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_session(client) -> str:
    r = client.post("/sessions")
    assert r.status_code == 201
    return r.json()["session_id"]


def _phq2_min_responses():
    return {"phq2_01": 0, "phq2_02": 0}


def _phq2_expansion_responses():
    return {"phq2_01": 2, "phq2_02": 2}  # total = 4 >= 3


def _phq9_responses(item9_value=0):
    return {f"phq9_0{i}": 0 for i in range(3, 10)} | {"phq9_09": item9_value}


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# Session lifecycle
# ---------------------------------------------------------------------------

class TestSessionLifecycle:

    def test_create_session(self, client):
        r = client.post("/sessions")
        assert r.status_code == 201
        body = r.json()
        assert "session_id" in body
        assert body["state"] == "EXPLORING"
        assert set(body["available"]) == {"phq2", "gad2", "paq_s"}

    def test_get_session_empty(self, client):
        sid = _create_session(client)
        r = client.get(f"/sessions/{sid}")
        assert r.status_code == 200
        body = r.json()
        assert body["state"] == "EXPLORING"
        assert body["completed"] == []
        assert set(body["available"]) == {"phq2", "gad2", "paq_s"}

    def test_get_session_not_found(self, client):
        r = client.get("/sessions/00000000-0000-0000-0000-000000000000")
        assert r.status_code == 404

    def test_multiple_independent_sessions(self, client):
        sid1 = _create_session(client)
        sid2 = _create_session(client)
        assert sid1 != sid2


# ---------------------------------------------------------------------------
# Assessment submission
# ---------------------------------------------------------------------------

class TestSubmitAssessment:

    def test_submit_phq2_no_expansion(self, client):
        """PHQ-2 score=0 → no expansion, session stays EXPLORING."""
        sid = _create_session(client)
        r = client.post(
            f"/sessions/{sid}/assessments/phq2/submit",
            json={"responses": _phq2_min_responses()},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["score"]["total_score"] == 0.0
        assert body["score"]["band"] == "minimal_or_none"
        assert body["routing"]["action"] == "none"
        assert body["routing"]["next_instrument_id"] is None
        assert body["session_state"] == "EXPLORING"

    def test_submit_phq2_triggers_expansion(self, client):
        """PHQ-2 score >= 3 → expansion to PHQ-9 with carry-forward."""
        sid = _create_session(client)
        r = client.post(
            f"/sessions/{sid}/assessments/phq2/submit",
            json={"responses": _phq2_expansion_responses()},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["score"]["total_score"] == 4.0
        assert body["routing"]["action"] == "next_instrument"
        assert body["routing"]["next_instrument_id"] == "phq9"
        # carry_forward_items should map phq9_01 and phq9_02
        cf = body["routing"]["carry_forward_items"]
        assert cf is not None
        assert "phq9_01" in cf
        assert "phq9_02" in cf
        assert cf["phq9_01"] == 2
        assert cf["phq9_02"] == 2

    def test_session_shows_phq2_completed(self, client):
        sid = _create_session(client)
        client.post(
            f"/sessions/{sid}/assessments/phq2/submit",
            json={"responses": _phq2_min_responses()},
        )
        r = client.get(f"/sessions/{sid}")
        body = r.json()
        completed_ids = [c["instrument_id"] for c in body["completed"]]
        assert "phq2" in completed_ids
        # Score present in completed
        phq2_entry = next(c for c in body["completed"] if c["instrument_id"] == "phq2")
        assert phq2_entry["total_score"] == 0.0
        assert phq2_entry["band"] == "minimal_or_none"

    def test_phq9_carry_forward_server_side(self, client):
        """Submit PHQ-2 → get instance_id → submit PHQ-9 with parent_instance_id.
        Server computes carry-forward; total includes items 1 & 2."""
        sid = _create_session(client)

        # Submit PHQ-2
        r1 = client.post(
            f"/sessions/{sid}/assessments/phq2/submit",
            json={"responses": {"phq2_01": 2, "phq2_02": 3}},
        )
        parent_id = r1.json()["assessment_instance_id"]

        # Submit PHQ-9: only items 3-9 (item 9 = 0 to avoid safety)
        new_responses = {f"phq9_0{i}": 0 for i in range(3, 10)}
        r2 = client.post(
            f"/sessions/{sid}/assessments/phq9/submit",
            json={
                "responses": new_responses,
                "parent_instance_id": parent_id,
            },
        )
        assert r2.status_code == 200
        body = r2.json()
        # 2 + 3 + 0*7 = 5
        assert body["score"]["total_score"] == 5.0
        assert body["score"]["band"] == "mild"

    def test_phq9_carry_forward_wrong_session_rejected(self, client):
        """parent_instance_id from a different session is rejected."""
        sid1 = _create_session(client)
        sid2 = _create_session(client)
        r1 = client.post(
            f"/sessions/{sid1}/assessments/phq2/submit",
            json={"responses": {"phq2_01": 3, "phq2_02": 3}},
        )
        parent_id = r1.json()["assessment_instance_id"]
        r2 = client.post(
            f"/sessions/{sid2}/assessments/phq9/submit",
            json={"responses": _phq9_responses(), "parent_instance_id": parent_id},
        )
        assert r2.status_code == 400

    def test_unknown_instrument_returns_404(self, client):
        sid = _create_session(client)
        r = client.post(
            f"/sessions/{sid}/assessments/not_real/submit",
            json={"responses": {}},
        )
        assert r.status_code == 404

    def test_submit_gad2_triggers_gad7_expansion(self, client):
        sid = _create_session(client)
        r = client.post(
            f"/sessions/{sid}/assessments/gad2/submit",
            json={"responses": {"gad2_01": 2, "gad2_02": 2}},
        )
        body = r.json()
        assert body["routing"]["next_instrument_id"] == "gad7"

    def test_submit_paq_s_triggers_paq_expansion(self, client):
        sid = _create_session(client)
        # PAQ-S min is 6, need score >= 30. Set all items to 5 (total=30).
        responses = {f"paq_s_0{i}": 5 for i in range(1, 7)}
        r = client.post(
            f"/sessions/{sid}/assessments/paq_s/submit",
            json={"responses": responses},
        )
        body = r.json()
        assert body["routing"]["next_instrument_id"] == "paq"

    def test_submit_ders16_subscales(self, client):
        sid = _create_session(client)
        # All items = 1 -> Total = 16. Subscales populated.
        responses = {f"ders16_{i:02d}": 1 for i in range(1, 17)}
        r = client.post(
            f"/sessions/{sid}/assessments/ders16/submit",
            json={"responses": responses},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["score"]["total_score"] == 16.0
        ss = body["score"]["subscale_scores"]
        assert ss is not None
        assert "clarity" in ss

    def test_submit_pss10_reverse_scoring(self, client):
        sid = _create_session(client)
        # Reverse items (4, 5, 7, 8) answered 4 -> score 0.
        # Forward items answered 0 -> score 0.
        responses = {f"pss10_{i:02d}": 0 for i in range(1, 11)}
        for i in [4, 5, 7, 8]:
            responses[f"pss10_{i:02d}"] = 4
        r = client.post(
            f"/sessions/{sid}/assessments/pss10/submit",
            json={"responses": responses},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["score"]["total_score"] == 0.0


# ---------------------------------------------------------------------------
# Safety protocol
# ---------------------------------------------------------------------------

class TestSafetyProtocol:

    def test_phq9_item9_triggers_safety_pause(self, client):
        """PHQ-9 item 9 = 1 → session goes to SAFETY_PAUSED."""
        sid = _create_session(client)
        responses = {f"phq9_0{i}": 0 for i in range(1, 10)}
        responses["phq9_09"] = 1
        r = client.post(
            f"/sessions/{sid}/assessments/phq9/submit",
            json={"responses": responses},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["routing"]["safety_triggered"] is True
        assert body["session_state"] == "SAFETY_PAUSED"

    def test_session_paused_blocks_further_submission(self, client):
        """SAFETY_PAUSED session rejects new submissions with 409."""
        sid = _create_session(client)
        responses = {f"phq9_0{i}": 0 for i in range(1, 10)}
        responses["phq9_09"] = 2
        client.post(
            f"/sessions/{sid}/assessments/phq9/submit",
            json={"responses": responses},
        )
        # Try submitting another instrument
        r = client.post(
            f"/sessions/{sid}/assessments/gad2/submit",
            json={"responses": {"gad2_01": 0, "gad2_02": 0}},
        )
        assert r.status_code == 409

    def test_safety_flags_on_session(self, client):
        """GET /sessions/{id} returns safety_flags when paused."""
        sid = _create_session(client)
        responses = {f"phq9_0{i}": 0 for i in range(1, 10)}
        responses["phq9_09"] = 3
        client.post(
            f"/sessions/{sid}/assessments/phq9/submit",
            json={"responses": responses},
        )
        r = client.get(f"/sessions/{sid}")
        body = r.json()
        assert body["state"] == "SAFETY_PAUSED"
        assert body["safety_flags"] is not None
        assert len(body["safety_flags"]) >= 1
        flag = body["safety_flags"][0]
        assert flag["instrument_id"] == "phq9"
        assert "timestamp" in flag

    def test_acknowledge_safety_resumes_session(self, client):
        """Acknowledge safety → session returns to EXPLORING."""
        sid = _create_session(client)
        responses = {f"phq9_0{i}": 0 for i in range(1, 10)}
        responses["phq9_09"] = 1
        client.post(
            f"/sessions/{sid}/assessments/phq9/submit",
            json={"responses": responses},
        )
        r = client.post(f"/sessions/{sid}/acknowledge-safety")
        assert r.status_code == 200
        assert r.json()["state"] == "EXPLORING"
        assert r.json()["safety_flags"] is None

    def test_can_submit_after_acknowledge(self, client):
        """Submission works again after safety acknowledgment."""
        sid = _create_session(client)
        responses = {f"phq9_0{i}": 0 for i in range(1, 10)}
        responses["phq9_09"] = 1
        client.post(
            f"/sessions/{sid}/assessments/phq9/submit",
            json={"responses": responses},
        )
        client.post(f"/sessions/{sid}/acknowledge-safety")
        r = client.post(
            f"/sessions/{sid}/assessments/gad2/submit",
            json={"responses": {"gad2_01": 0, "gad2_02": 0}},
        )
        assert r.status_code == 200

    def test_acknowledge_safety_on_exploring_session_returns_409(self, client):
        sid = _create_session(client)
        r = client.post(f"/sessions/{sid}/acknowledge-safety")
        assert r.status_code == 409

    @pytest.mark.parametrize("item9_value", [1, 2, 3])
    def test_all_nonzero_item9_values_trigger_safety(self, client, item9_value):
        sid = _create_session(client)
        responses = {f"phq9_0{i}": 0 for i in range(1, 10)}
        responses["phq9_09"] = item9_value
        r = client.post(
            f"/sessions/{sid}/assessments/phq9/submit",
            json={"responses": responses},
        )
        assert r.json()["session_state"] == "SAFETY_PAUSED"

    def test_item9_zero_does_not_trigger_safety(self, client):
        sid = _create_session(client)
        responses = {f"phq9_0{i}": 0 for i in range(1, 10)}
        r = client.post(
            f"/sessions/{sid}/assessments/phq9/submit",
            json={"responses": responses},
        )
        assert r.json()["session_state"] == "EXPLORING"


# ---------------------------------------------------------------------------
# Available instruments update after submission
# ---------------------------------------------------------------------------

class TestAvailableInstruments:

    def test_phq2_complete_no_expansion_not_in_available(self, client):
        sid = _create_session(client)
        client.post(
            f"/sessions/{sid}/assessments/phq2/submit",
            json={"responses": _phq2_min_responses()},
        )
        r = client.get(f"/sessions/{sid}")
        available = r.json()["available"]
        assert "phq2" not in available
        assert "phq9" not in available
        assert "gad2" in available  # other chains unaffected

    def test_phq2_expansion_makes_phq9_available(self, client):
        sid = _create_session(client)
        client.post(
            f"/sessions/{sid}/assessments/phq2/submit",
            json={"responses": _phq2_expansion_responses()},
        )
        r = client.get(f"/sessions/{sid}")
        assert "phq9" in r.json()["available"]

    def test_all_chains_can_complete_independently(self, client):
        """All three Venus quick scans below threshold → all chains close, nothing available."""
        sid = _create_session(client)
        for instrument, responses in [
            ("phq2", {"phq2_01": 0, "phq2_02": 0}),
            ("gad2", {"gad2_01": 0, "gad2_02": 0}),
            ("paq_s", {f"paq_s_0{i}": 1 for i in range(1, 7)}),  # total=6, below 30
        ]:
            client.post(
                f"/sessions/{sid}/assessments/{instrument}/submit",
                json={"responses": responses},
            )
        r = client.get(f"/sessions/{sid}")
        assert r.json()["available"] == []
        assert len(r.json()["completed"]) == 3
