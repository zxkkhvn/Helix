import pytest
from helix.scoring.registry import get_scorer
from helix.tests.conftest import _mock_responses

def test_mss_ysq():
    scorer = get_scorer("mss_ysq")
    res = scorer.score(_mock_responses("mss_ysq", 1))
    assert res.total_score == 1.0

def test_ius12():
    scorer = get_scorer("ius12")
    res = scorer.score(_mock_responses("ius12", 1))
    assert res.total_score == 12
    assert res.band == "low"

def test_ptq10():
    scorer = get_scorer("ptq10")
    res = scorer.score(_mock_responses("ptq10", 0))
    assert res.total_score == 0

def test_cpq():
    scorer = get_scorer("cpq")
    res = scorer.score(_mock_responses("cpq", 1))
    assert res.total_score == 18

def test_des_b():
    scorer = get_scorer("des_b")
    res = scorer.score(_mock_responses("des_b", 0))
    assert res.total_score == 0

def test_pswq():
    scorer = get_scorer("pswq")
    res = scorer.score(_mock_responses("pswq", 1))
    # 5 items reversed: 6-1=5 (25 total), 11 items standard: 1 (11 total) = 36
    assert res.total_score == 36

def test_oci_r():
    scorer = get_scorer("oci_r")
    res = scorer.score(_mock_responses("oci_r", 0))
    assert res.total_score == 0
