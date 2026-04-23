import pytest
from helix.scoring.base import ScoreResult
from helix.tests.conftest import (
    make_max_responses,
    make_min_responses,
    make_specific_responses,
)


class TestASRSPartA:

    def test_all_min(self, load_definition, score):
        defn = load_definition("asrs_a")
        result = score("asrs_a", make_min_responses(defn))
        assert result.total_score == 0.0
        assert result.band == "low"

    def test_all_max(self, load_definition, score):
        defn = load_definition("asrs_a")
        result = score("asrs_a", make_max_responses(defn))
        assert result.total_score == 24.0
        assert result.band == "elevated"

    def test_threshold_below(self, load_definition, score):
        defn = load_definition("asrs_a")
        # Sum of 11 -> low
        responses = {f"asrs_a_{i:02d}": 2 for i in range(1, 7)}
        responses["asrs_a_06"] = 1  # 2+2+2+2+2+1 = 11
        result = score("asrs_a", responses)
        assert result.total_score == 11.0
        assert result.band == "low"

    def test_threshold_at(self, load_definition, score):
        defn = load_definition("asrs_a")
        # Sum of 12 -> elevated
        responses = {f"asrs_a_{i:02d}": 2 for i in range(1, 7)}  # 6*2 = 12
        result = score("asrs_a", responses)
        assert result.total_score == 12.0
        assert result.band == "elevated"


class TestASRSFull:

    def test_all_min(self, load_definition, score):
        defn = load_definition("asrs_full")
        result = score("asrs_full", make_min_responses(defn))
        assert result.total_score == 0.0
        assert result.band == "low"

    def test_all_max(self, load_definition, score):
        defn = load_definition("asrs_full")
        result = score("asrs_full", make_max_responses(defn))
        assert result.total_score == 72.0
        assert result.band == "high"

    def test_carry_forward(self, load_definition, score):
        """Simulate carry-forward: 6 carried items + 12 new items = full 18."""
        defn = load_definition("asrs_full")
        carried = {f"asrs_full_{i:02d}": 3 for i in range(1, 7)}  # 6 * 3 = 18
        new_items = {f"asrs_full_{i:02d}": 2 for i in range(7, 19)}  # 12 * 2 = 24
        all_responses = {**carried, **new_items}
        result = score("asrs_full", all_responses)
        assert result.total_score == 42.0  # 18 + 24
        assert result.band == "moderate"

    def test_moderate_boundary(self, load_definition, score):
        defn = load_definition("asrs_full")
        responses = {f"asrs_full_{i:02d}": 2 for i in range(1, 19)}
        # 18 * 2 = 36 -> moderate
        # bump some to get to 44 (upper bound of moderate)
        for i in range(1, 5):
            responses[f"asrs_full_{i:02d}"] = 4  # 4*4 + 14*2 = 16+28 = 44
        result = score("asrs_full", responses)
        assert result.total_score == 44.0
        assert result.band == "moderate"


class TestBDEFSSF:

    def test_all_min(self, load_definition, score):
        defn = load_definition("bdefs_sf")
        result = score("bdefs_sf", make_min_responses(defn))
        assert result.total_score == 20.0  # 20 items * 1 = 20
        assert result.band == "normal"

    def test_all_max(self, load_definition, score):
        defn = load_definition("bdefs_sf")
        result = score("bdefs_sf", make_max_responses(defn))
        assert result.total_score == 80.0  # 20 items * 4 = 80
        assert result.band == "clinical"

    def test_subscale_scores(self, load_definition, score):
        defn = load_definition("bdefs_sf")
        # Set each subscale group to a distinct value
        responses = {}
        for i in range(1, 5):
            responses[f"bdefs_sf_{i:02d}"] = 1  # time: 4*1 = 4
        for i in range(5, 9):
            responses[f"bdefs_sf_{i:02d}"] = 2  # org: 4*2 = 8
        for i in range(9, 13):
            responses[f"bdefs_sf_{i:02d}"] = 3  # restraint: 4*3 = 12
        for i in range(13, 17):
            responses[f"bdefs_sf_{i:02d}"] = 4  # motivation: 4*4 = 16
        for i in range(17, 21):
            responses[f"bdefs_sf_{i:02d}"] = 2  # emotion: 4*2 = 8
        result = score("bdefs_sf", responses)
        assert result.total_score == 48.0
        assert result.band == "elevated"
        ss = result.subscale_scores
        assert ss["self_management_time"] == 4.0
        assert ss["self_organization"] == 8.0
        assert ss["self_restraint"] == 12.0
        assert ss["self_motivation"] == 16.0
        assert ss["self_regulation_emotion"] == 8.0


class TestCFQ25:

    def test_all_min(self, load_definition, score):
        defn = load_definition("cfq25")
        result = score("cfq25", make_min_responses(defn))
        assert result.total_score == 0.0
        assert result.band == "low"

    def test_all_max(self, load_definition, score):
        defn = load_definition("cfq25")
        result = score("cfq25", make_max_responses(defn))
        assert result.total_score == 100.0
        assert result.band == "high"

    def test_midpoint(self, load_definition, score):
        defn = load_definition("cfq25")
        responses = {f"cfq_{i:02d}": 2 for i in range(1, 26)}  # 25 * 2 = 50
        result = score("cfq25", responses)
        assert result.total_score == 50.0
        assert result.band == "elevated"
