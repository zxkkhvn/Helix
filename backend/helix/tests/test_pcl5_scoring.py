import pytest
from helix.scoring.registry import get_scorer
from helix.tests.conftest import _mock_responses

def test_pcl5():
    scorer = get_scorer("pcl5")
    res = scorer.score(_mock_responses("pcl5", 0))
    assert res.total_score == 0
    assert res.band == "subthreshold"
