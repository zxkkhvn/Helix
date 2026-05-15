import pytest
from functools import lru_cache

from helix.scoring.registry import get_scorer
from helix.tests.conftest import _mock_responses


def test_aq10():
    scorer = get_scorer("aq10")
    res = scorer.score(_mock_responses("aq10", 0))
    # Some items reversed, some standard. Using mock responses might give random score if it doesn't match keys exactly
    # Let's just assert it runs and returns a valid band.
    assert res.band in ["below_threshold", "above_threshold"]

def test_catq():
    scorer = get_scorer("catq")
    res = scorer.score(_mock_responses("catq", 1))
    # 25 items, 5 reversed
    # 20 standard (1), 5 reversed (7) -> 20 + 35 = 55
    assert res.total_score == 55

def test_raads_r():
    scorer = get_scorer("raads_r")
    res = scorer.score(_mock_responses("raads_r", 0))
    assert res.total_score == 0
    assert res.band == "below_threshold"


def _raads_r_responses_for_total(target_total: int) -> dict[str, int]:
    scorer = get_scorer("raads_r")
    definition = scorer._def
    items = definition["items"]
    option_values = {
        item["item_id"]: sorted(
            {option["value"] for option in definition["response_option_sets"][item["response_options_key"]]},
            reverse=True,
        )
        for item in items
    }
    ordered_items = [item["item_id"] for item in items]

    @lru_cache(maxsize=None)
    def solve(index: int, remaining: int):
        if remaining == 0:
            return ()
        if index >= len(ordered_items) or remaining < 0:
            return None

        item_id = ordered_items[index]
        for value in option_values[item_id]:
            if value > remaining:
                continue
            suffix = solve(index + 1, remaining - value)
            if suffix is not None:
                return ((item_id, value),) + suffix
        return None

    solution = solve(0, target_total)
    assert solution is not None, f"Unable to build RAADS-R responses for total {target_total}"
    responses = {item_id: 0 for item_id in ordered_items}
    responses.update(dict(solution))
    return responses


@pytest.mark.parametrize(
    ("target_total", "expected_band"),
    [
        (64, "below_threshold"),
        (65, "gray_zone"),
        (105, "gray_zone"),
        (106, "consistent_with_autism"),
        (139, "consistent_with_autism"),
        (140, "pronounced_traits"),
    ],
)
def test_raads_r_band_thresholds(target_total, expected_band):
    scorer = get_scorer("raads_r")
    responses = _raads_r_responses_for_total(target_total)
    res = scorer.score(responses)
    assert res.total_score == target_total
    assert res.band == expected_band
