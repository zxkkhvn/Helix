import pytest
from helix.scoring.base import ScoreResult
from helix.tests.conftest import (
    make_max_responses,
    make_min_responses,
    make_specific_responses,
)

class TestMAIA2Brief:

    def test_all_min(self, load_definition, score):
        defn = load_definition("maia2_brief")
        result = score("maia2_brief", make_min_responses(defn))
        # Min response for Likert 0-5 is 0
        # For MAIA-2 Brief, it uses mean per subscale
        # So total score is 0.
        assert result.total_score == 0.0
        ss = result.subscale_scores
        for key in ss:
            assert ss[key] == 0.0

    def test_all_max(self, load_definition, score):
        defn = load_definition("maia2_brief")
        result = score("maia2_brief", make_max_responses(defn))
        assert result.total_score == 5.0
        ss = result.subscale_scores
        for key in ss:
            assert ss[key] == 5.0


class TestMEQ:

    def test_all_min(self, load_definition, score):
        defn = load_definition("meq")
        result = score("meq", make_min_responses(defn))
        # Sum of min values for each item (17*1 + 2*0 = 17)
        assert result.total_score == 17.0
        assert result.band == "definite_evening"
        assert result.metadata["light_therapy_start_time"] == "Consult clinician"

    def test_all_max(self, load_definition, score):
        defn = load_definition("meq")
        result = score("meq", make_max_responses(defn))
        # Max is 86
        assert result.total_score == 86.0
        assert result.band == "definite_morning"

    def test_light_therapy_time(self, load_definition, score):
        defn = load_definition("meq")
        base = make_min_responses(defn) # score is 16
        # Let's hit a specific score, e.g. 50
        # Add 34 points
        # item 1 is 1 to 5. diff is 4.
        # We can just manually set the items
        for item in defn["items"]:
            base[item["item_id"]] = 2 # 19 * 2 = 38
        base["meq_01"] = 3
        base["meq_02"] = 3
        # 17 * 2 = 34 + 6 = 40
        # let's just make it simple
        base = {f"meq_{i:02d}": 2 for i in range(1, 20)} # 38
        base["meq_01"] = 4 # +2 = 40
        base["meq_02"] = 4 # +2 = 42
        base["meq_03"] = 4 # +2 = 44
        base["meq_04"] = 4 # +2 = 46
        base["meq_05"] = 4 # +2 = 48
        base["meq_06"] = 4 # +2 = 50
        result = score("meq", base)
        assert result.total_score == 50.0
        assert result.band == "intermediate"
        assert result.metadata["light_therapy_start_time"] == "6:30 AM"


class TestPSQI:

    def test_good_sleep(self, load_definition, score):
        defn = load_definition("psqi")
        responses = {
            "psqi_01": "10:00 PM", # bed time
            "psqi_02": 10,         # latency (<=15 = 0)
            "psqi_03": "7:00 AM",  # wake time (9 hours in bed)
            "psqi_04": 8.5,        # hours slept (>7 = 0)
            # 5a-5j are 0 (no trouble)
            "psqi_05a": 0, "psqi_05b": 0, "psqi_05c": 0, "psqi_05d": 0,
            "psqi_05e": 0, "psqi_05f": 0, "psqi_05g": 0, "psqi_05h": 0,
            "psqi_05i": 0, "psqi_05j": 0,
            "psqi_06": 0,          # quality = very good (0)
            "psqi_07": 0,          # meds = 0
            "psqi_08": 0,          # dysfunction = 0
            "psqi_09": 0,
        }
        result = score("psqi", responses)
        assert result.total_score == 0.0
        assert result.band == "good_sleep_quality"

    def test_poor_sleep(self, load_definition, score):
        defn = load_definition("psqi")
        responses = {
            "psqi_01": "02:00",    # bed time 2am
            "psqi_02": 90,         # latency (>60 = 3)
            "psqi_03": "06:00",    # wake time 6am (4 hours in bed)
            "psqi_04": 2.0,        # hours slept (2/4 = 50% eff -> 3)
            # 5a-5j max problems
            "psqi_05a": 3, "psqi_05b": 3, "psqi_05c": 3, "psqi_05d": 3,
            "psqi_05e": 3, "psqi_05f": 3, "psqi_05g": 3, "psqi_05h": 3,
            "psqi_05i": 3, "psqi_05j": 3,
            "psqi_06": 3,          # quality = very bad (3)
            "psqi_07": 3,          # meds = 3
            "psqi_08": 3,          # dysfunction = 3
            "psqi_09": 3,
        }
        result = score("psqi", responses)
        assert result.total_score == 21.0
        assert result.band == "poor_sleep_quality"

    def test_efficiency_edge_cases(self, load_definition, score):
        defn = load_definition("psqi")
        responses = {
            "psqi_01": "wrong time format",
            "psqi_02": 0,
            "psqi_03": "also wrong",
            "psqi_04": 4.0, # 4.0 / fallback 8.0 = 50% (<65% = 3)
            "psqi_05a": 0, "psqi_05b": 0, "psqi_05c": 0, "psqi_05d": 0,
            "psqi_05e": 0, "psqi_05f": 0, "psqi_05g": 0, "psqi_05h": 0,
            "psqi_05i": 0, "psqi_05j": 0,
            "psqi_06": 0,
            "psqi_07": 0,
            "psqi_08": 0,
            "psqi_09": 0,
        }
        result = score("psqi", responses)
        assert result.subscale_scores["habitual_sleep_efficiency"] == 3.0
