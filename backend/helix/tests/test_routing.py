"""Unit tests for the routing engine. No HTTP, no DB."""

import pytest

from helix.routing.engine import (
    RoutingAction,
    _parse_condition,
    compute_available_instruments,
    evaluate_routing,
)
from helix.scoring.base import ScoreResult
from helix.tests.conftest import make_min_responses, make_specific_responses


# ---------------------------------------------------------------------------
# Condition parser unit tests
# ---------------------------------------------------------------------------

class TestParseCondition:

    @pytest.mark.parametrize("condition,score,responses,expected", [
        ("score >= 3", 3.0, {}, True),
        ("score >= 3", 2.9, {}, False),
        ("score > 10", 10.0, {}, False),
        ("score > 10", 10.1, {}, True),
        ("score == 6", 6.0, {}, True),
        ("score == 6", 5.0, {}, False),
        ("score < 5", 4.9, {}, True),
        ("score < 5", 5.0, {}, False),
        ("item.phq9_09 > 0", 0.0, {"phq9_09": 1}, True),
        ("item.phq9_09 > 0", 0.0, {"phq9_09": 0}, False),
        ("item.phq9_09 > 0", 0.0, {}, False),  # item not in responses
        ("garbage condition", 5.0, {}, False),
    ])
    def test_parse_condition(self, condition, score, responses, expected):
        assert _parse_condition(condition, score, responses) == expected


# ---------------------------------------------------------------------------
# evaluate_routing — Venus instruments
# ---------------------------------------------------------------------------

class TestEvaluateRouting:

    def _make_score(self, total, safety_flags=None):
        return ScoreResult(
            instrument_id="test",
            total_score=total,
            band=None,
            subscale_scores=None,
            safety_flags=safety_flags or [],
            validity_warnings=[],
            metadata={},
        )

    def test_phq2_below_threshold_no_expansion(self, load_definition):
        defn = load_definition("phq2")
        score = self._make_score(2.0)
        result = evaluate_routing(defn, score, {"phq2_01": 1, "phq2_02": 1})
        assert result.action == "none"
        assert result.next_instrument_id is None
        assert result.safety_triggered is False

    def test_phq2_at_threshold_triggers_expansion(self, load_definition):
        defn = load_definition("phq2")
        score = self._make_score(3.0)
        result = evaluate_routing(defn, score, {"phq2_01": 2, "phq2_02": 1})
        assert result.action == "next_instrument"
        assert result.next_instrument_id == "phq9"
        assert result.safety_triggered is False

    def test_phq2_above_threshold_triggers_expansion(self, load_definition):
        defn = load_definition("phq2")
        score = self._make_score(6.0)
        result = evaluate_routing(defn, score, {"phq2_01": 3, "phq2_02": 3})
        assert result.action == "next_instrument"
        assert result.next_instrument_id == "phq9"

    def test_gad2_below_threshold_no_expansion(self, load_definition):
        defn = load_definition("gad2")
        score = self._make_score(2.0)
        result = evaluate_routing(defn, score, {})
        assert result.action == "none"
        assert result.next_instrument_id is None

    def test_gad2_at_threshold_triggers_expansion(self, load_definition):
        defn = load_definition("gad2")
        score = self._make_score(3.0)
        result = evaluate_routing(defn, score, {})
        assert result.action == "next_instrument"
        assert result.next_instrument_id == "gad7"

    def test_paq_s_below_threshold_no_expansion(self, load_definition):
        defn = load_definition("paq_s")
        score = self._make_score(29.0)
        result = evaluate_routing(defn, score, {})
        assert result.action == "none"

    def test_paq_s_at_threshold_triggers_expansion(self, load_definition):
        defn = load_definition("paq_s")
        score = self._make_score(30.0)
        result = evaluate_routing(defn, score, {})
        assert result.action == "next_instrument"
        assert result.next_instrument_id == "paq"

    def test_phq9_below_flag_elevated_threshold(self, load_definition):
        defn = load_definition("phq9")
        score = self._make_score(9.0)
        result = evaluate_routing(defn, score, {"phq9_09": 0})
        assert "flag_elevated" not in result.flags
        assert result.safety_triggered is False

    def test_phq9_at_flag_elevated_threshold(self, load_definition):
        defn = load_definition("phq9")
        score = self._make_score(10.0)
        result = evaluate_routing(defn, score, {"phq9_09": 0})
        assert "flag_elevated" in result.flags
        assert result.safety_triggered is False

    def test_phq9_item9_triggers_safety(self, load_definition):
        defn = load_definition("phq9")
        # Scorer already fires safety flag; routing engine also evaluates on_completion
        scorer_safety = [{"item_id": "phq9_09", "value": 1, "action": "SAFETY_PROTOCOL"}]
        score = self._make_score(5.0, safety_flags=scorer_safety)
        result = evaluate_routing(defn, score, {"phq9_09": 1})
        assert result.safety_triggered is True
        assert result.action == "safety_pause"

    def test_phq9_elevated_and_safety_both_fire(self, load_definition):
        """score >= 10 AND item 9 > 0: both flag_elevated and safety_triggered."""
        defn = load_definition("phq9")
        scorer_safety = [{"item_id": "phq9_09", "value": 2, "action": "SAFETY_PROTOCOL"}]
        score = self._make_score(15.0, safety_flags=scorer_safety)
        result = evaluate_routing(defn, score, {"phq9_09": 2})
        assert result.safety_triggered is True
        assert "flag_elevated" in result.flags
        # safety_pause takes precedence
        assert result.action == "safety_pause"

    def test_gad7_flag_elevated(self, load_definition):
        defn = load_definition("gad7")
        score = self._make_score(10.0)
        result = evaluate_routing(defn, score, {})
        assert "flag_elevated" in result.flags
        assert result.safety_triggered is False

    def test_ders16_flag_elevated(self, load_definition):
        defn = load_definition("ders16")
        score = self._make_score(48.0)
        result = evaluate_routing(defn, score, {})
        assert "flag_elevated" in result.flags

    def test_pss10_flag_elevated(self, load_definition):
        defn = load_definition("pss10")
        score = self._make_score(27.0)
        result = evaluate_routing(defn, score, {})
        assert "flag_elevated" in result.flags

    def test_dts_flag_elevated(self, load_definition):
        defn = load_definition("dts")
        score = self._make_score(30.0)
        result = evaluate_routing(defn, score, {})
        assert "flag_elevated" in result.flags

    def test_paq_flag_alexithymia_calibration(self, load_definition):
        defn = load_definition("paq")
        score = self._make_score(111.0)
        result = evaluate_routing(defn, score, {})
        assert "flag_alexithymia_calibration" in result.flags


# ---------------------------------------------------------------------------
# compute_available_instruments
# ---------------------------------------------------------------------------

class TestComputeAvailableInstruments:

    def _make_score(self, instrument_id, total, assessment_instance_id="inst-1"):
        class FakeScore:
            pass
        s = FakeScore()
        s.instrument_id = instrument_id
        s.total_score = total
        s.assessment_instance_id = assessment_instance_id
        s.band = None
        return s

    def test_empty_session_all_quick_scans_available(self):
        available = compute_available_instruments([])
        assert "phq2" in available
        assert "gad2" in available
        assert "paq_s" in available

    def test_phq2_below_threshold_no_phq9(self):
        scores = [self._make_score("phq2", 2.0)]
        available = compute_available_instruments(scores)
        assert "phq2" not in available
        assert "phq9" not in available

    def test_phq2_at_threshold_phq9_available(self):
        scores = [self._make_score("phq2", 3.0)]
        available = compute_available_instruments(scores)
        assert "phq9" in available
        assert "phq2" not in available

    def test_phq9_complete_not_available(self):
        scores = [
            self._make_score("phq2", 3.0),
            self._make_score("phq9", 14.0, "inst-2"),
        ]
        available = compute_available_instruments(scores)
        assert "phq9" not in available
        assert "phq2" not in available

    def test_gad2_expansion(self):
        scores = [self._make_score("gad2", 4.0)]
        available = compute_available_instruments(scores)
        assert "gad7" in available
        assert "gad2" not in available

    def test_paq_s_expansion(self):
        scores = [self._make_score("paq_s", 30.0)]
        available = compute_available_instruments(scores)
        assert "paq" in available
        assert "paq_s" not in available

    def test_parallel_chains_independent(self):
        """PHQ chain completion doesn't affect GAD or PAQ availability."""
        scores = [self._make_score("phq2", 2.0)]
        available = compute_available_instruments(scores)
        assert "gad2" in available
        assert "paq_s" in available
