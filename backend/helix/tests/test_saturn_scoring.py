import pytest
from helix.scoring.registry import get_scorer
from helix.tests.conftest import _mock_responses

def test_lsas_sr_short():
    scorer = get_scorer("lsas_sr_short")
    res = scorer.score(_mock_responses("lsas_sr_short", 0))
    assert res.total_score == 0
    assert res.band == "none"

    res = scorer.score(_mock_responses("lsas_sr_short", 3))
    assert res.total_score == 72
    assert res.band == "severe"

def test_lsas_sr_full():
    scorer = get_scorer("lsas_sr_full")
    res = scorer.score(_mock_responses("lsas_sr_full", 0))
    assert res.total_score == 0
    assert res.band == "none"

    res = scorer.score(_mock_responses("lsas_sr_full", 3))
    assert res.total_score == 144
    assert res.band == "very_severe"

def test_ecr_rs():
    scorer = get_scorer("ecr_rs")
    res = scorer.score(_mock_responses("ecr_rs", 1))
    # Reverse items 1-4: 8 - 1 = 7. Items 5-9: 1
    # Avoidance = mean(7,7,7,7,1,1) = 30/6 = 5.0
    # Anxiety = mean(1,1,1) = 1.0
    # Mean of 6 items = 5.0, 3 items = 1.0
    assert res.total_score == pytest.approx((5.0*6 + 1.0*3)/9)
    assert res.subscale_scores["mother_avoidance"] == 5.0
    assert res.subscale_scores["mother_anxiety"] == 1.0

def test_dejong():
    scorer = get_scorer("dejong")
    # All 1 -> DeJong positive: Yes=0, more or less=1, No=1
    res = scorer.score({"dejong_01": 1, "dejong_02": 1, "dejong_03": 1, "dejong_04": 1, "dejong_05": 1, "dejong_06": 1})
    assert res.total_score == 6
    assert res.band == "severe"
