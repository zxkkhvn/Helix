import pytest
import uuid
from helix.models.models import Session, AssessmentInstance, Score
from helix.ai.context import ContextSerializer, THEME_INSTRUMENT_MAPPING, THEME_THRESHOLD_PARTIAL, THEME_THRESHOLD_RICH

def mock_score(instrument_id: str, total_score: float = 10.0, band: str = "mild") -> Score:
    return Score(
        instrument_id=instrument_id,
        total_score=total_score,
        band=band,
        subscale_scores={},
        safety_flags=[],
        validity_warnings=[],
        score_metadata={}
    )

def mock_assessment_instance(score: Score) -> AssessmentInstance:
    instance = AssessmentInstance(
        id=str(uuid.uuid4()),
        instrument_id=score.instrument_id,
        instrument_version="1.0",
        responses={},
        status="COMPLETED"
    )
    instance.score = score
    return instance

def mock_session(scores: list[Score], intake_data=None, safety_flags=None) -> Session:
    session = Session(
        id=uuid.uuid4(),
        state="EXPLORING",
        intake_data=intake_data or {},
        safety_flags=safety_flags,
        anchors={"mood": 50, "energy": 50, "focus": 50}
    )
    instances = []
    for s in scores:
        instances.append(mock_assessment_instance(s))
    session.assessment_instances = instances
    return session

def test_theme_states_transitions():
    """Test transitions between SPARSE, PARTIAL, and RICH."""
    
    distress_instruments = THEME_INSTRUMENT_MAPPING["current_distress"]
    
    # Test SPARSE (0 instruments)
    session_sparse = mock_session([])
    payload = ContextSerializer.build_payload(session_sparse)
    assert payload["theme_states"]["current_distress"] == "SPARSE"
    
    # Test SPARSE (1 instrument)
    session_sparse_1 = mock_session([mock_score(distress_instruments[0])])
    payload = ContextSerializer.build_payload(session_sparse_1)
    assert payload["theme_states"]["current_distress"] == "SPARSE"

    # Test PARTIAL (THEME_THRESHOLD_PARTIAL instruments)
    scores_partial = [mock_score(inst) for inst in distress_instruments[:THEME_THRESHOLD_PARTIAL]]
    session_partial = mock_session(scores_partial)
    payload = ContextSerializer.build_payload(session_partial)
    assert payload["theme_states"]["current_distress"] == "PARTIAL"

    # Test RICH (THEME_THRESHOLD_RICH instruments)
    scores_rich = [mock_score(inst) for inst in distress_instruments[:THEME_THRESHOLD_RICH]]
    session_rich = mock_session(scores_rich)
    payload = ContextSerializer.build_payload(session_rich)
    assert payload["theme_states"]["current_distress"] == "RICH"

def test_build_payload_structure():
    """Verify build_payload returns the exact JSON contract keys required."""
    
    intake_data = {
        "red_thread_question": "Why am I always tired?",
        "red_thread_quality": "good",
        "red_thread_categories": ["sleep", "energy"],
        "red_thread_risk_flag": False,
        "cultural_background": {"ethnicity": "Test"}
    }
    
    safety_flags = [{"instrument_id": "phq9", "item_id": "phq9_09", "reason": "Self harm"}]
    
    scores = [
        mock_score("phq9", 15.0, "moderately_severe"),
        mock_score("pbat", 0.0, None)
    ]
    # Inject pbat specific subscale logic for verification
    scores[1].subscale_scores = {"positive": 60, "negative": 40}
    
    session = mock_session(scores, intake_data=intake_data, safety_flags=safety_flags)
    
    payload = ContextSerializer.build_payload(session)
    
    assert "session_id" in payload
    assert payload["red_thread_question"] == "Why am I always tired?"
    assert payload["red_thread_quality"] == "good"
    assert payload["red_thread_categories"] == ["sleep", "energy"]
    assert payload["red_thread_risk_flag"] is False
    assert payload["cultural_background"] == {"ethnicity": "Test"}
    
    assert payload["session_anchors"] == {"mood": 50, "energy": 50, "focus": 50}
    
    assert payload["pbat_profile"]["subscale_scores"] == {"positive": 60, "negative": 40}
    
    assert len(payload["base_scores"]) == 2
    assert payload["base_scores"][0]["instrument_id"] == "phq9"
    assert payload["base_scores"][0]["total"] == 15.0
    
    assert "composite_indices" in payload
    assert "theme_states" in payload
    assert "completion_state" in payload
    
    # Safety markers verification
    assert payload["safety_markers"]["self_harm"] is True
    assert payload["safety_protocol"] is not None
    assert "immediate distress" in payload["safety_protocol"]
