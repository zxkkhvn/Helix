"""Tests for the composite index engine."""

import pytest

from helix.scoring.base import ScoreResult
from helix.scoring.composite import (
    compute_all_composites,
    compute_composite,
    find_score,
    load_composites,
    load_norms,
)

@pytest.fixture
def norms():
    return {
        "phq9": {"mean": 5.0, "sd": 5.0},
        "gad7": {"mean": 4.0, "sd": 4.0},
        "wemwbs": {"mean": 51.6, "sd": 8.7},
        "scs_sf": {"mean": 3.0, "sd": 0.6},
        "brs": {"mean": 3.5, "sd": 0.7},
        "rses": {"mean": 22.0, "sd": 5.0},
        "ecr_s_avoidance": {"mean": 3.0, "sd": 1.0},
        "asrs_full": {"mean": 25.0, "sd": 8.0},
        "bdefs_sf": {"mean": 20.0, "sd": 7.0},
        "isi": {"mean": 6.0, "sd": 4.0},
        "vlq": {"mean": 0.0, "sd": 1.0}, # Placeholder
    }

@pytest.fixture
def distress_def():
    return {
        "index_id": "distress_index",
        "version": "1.0",
        "components": ["phq9", "gad7", "lsas_sr", "wemwbs"],
        "required_core": ["phq9", "gad7"],
        "required_minimum": 2,
        "computation": "mean_z",
        "sign_inversions": ["wemwbs"],
    }

@pytest.fixture
def protective_def():
    return {
        "index_id": "protective_resources",
        "version": "1.0",
        "components": ["scs_sf", "brs", "wemwbs", "rses"],
        "required_core": [],
        "required_minimum": 2,
        "computation": "mean_z",
        "sign_inversions": [],
    }

@pytest.fixture
def executive_def():
    return {
        "index_id": "executive_load",
        "version": "1.0",
        "components": ["asrs_full", "bdefs_sf", "isi"],
        "required_core": ["asrs_full", "bdefs_sf"],
        "required_minimum": 2,
        "computation": "mean_z",
        "sign_inversions": ["isi"],
    }

def create_mock_score(instrument_id: str, total_score: float, subscales: dict = None) -> ScoreResult:
    return ScoreResult(
        instrument_id=instrument_id,
        total_score=total_score,
        band=None,
        subscale_scores=subscales,
        safety_flags=[],
        validity_warnings=[],
        metadata={},
    )

def test_distress_index_core_only(distress_def, norms):
    """Fires with just required core components."""
    scores = [
        create_mock_score("phq9", 10.0), # z = 1.0
        create_mock_score("gad7", 8.0),  # z = 1.0
    ]
    res = compute_composite(distress_def, scores, norms)
    assert res is not None
    assert res.score == 1.0
    assert res.is_partial is True
    assert res.label == "2 of 4 components"
    assert "phq9" in res.components_present
    assert "gad7" in res.components_present

def test_distress_index_with_wemwbs_inversion(distress_def, norms):
    """WEMWBS score is inverted."""
    scores = [
        create_mock_score("phq9", 10.0),   # z = 1.0
        create_mock_score("gad7", 8.0),    # z = 1.0
        create_mock_score("wemwbs", 42.9), # original z = -1.0, inverted z = 1.0
    ]
    res = compute_composite(distress_def, scores, norms)
    assert res is not None
    assert pytest.approx(res.score) == 1.0
    assert res.is_partial is True
    assert res.label == "3 of 4 components"
    assert "wemwbs" in res.components_present

def test_protective_resources_full(protective_def, norms):
    """Full composite computation."""
    scores = [
        create_mock_score("scs_sf", 3.6),  # z = 1.0
        create_mock_score("brs", 4.2),     # z = 1.0
        create_mock_score("wemwbs", 60.3), # z = 1.0
        create_mock_score("rses", 27.0),   # z = 1.0
    ]
    res = compute_composite(protective_def, scores, norms)
    assert res is not None
    assert pytest.approx(res.score) == 1.0
    assert res.is_partial is False
    assert res.label == "4 of 4 components"

def test_executive_load_insufficient(executive_def, norms):
    """Returns None when required core is missing."""
    scores = [
        create_mock_score("asrs_full", 25.0), # Misses bdefs_sf
        create_mock_score("isi", 6.0),
    ]
    res = compute_composite(executive_def, scores, norms)
    assert res is None

def test_subscale_component_resolution():
    """Can pull subscale from a base instrument."""
    scores = [
        create_mock_score("ecr_s", 20.0, {"avoidance": 4.0}), # z should be (4-3)/1 = 1.0
    ]
    # Use find_score directly
    val = find_score(scores, "ecr_s_avoidance")
    assert val == 4.0
