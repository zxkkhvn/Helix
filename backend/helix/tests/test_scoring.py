"""Test scoring correctness for all 6 Venus instruments.

Strategy:
- All-min / all-max scores and band assignment
- Band boundary thresholds
- PHQ-9 item 9 safety flag at every response value (0, 1, 2, 3)
- Carry-forward scoring (PHQ-2 → PHQ-9, GAD-2 → GAD-7, PAQ-S → PAQ)
- PAQ subscale computation
- Longstring and rapid-response validity warnings
- Registry lookup

Scorer is never mocked. Real computation path throughout.
"""

import pytest

from helix.scoring.base import ScoreResult, _evaluate_item_condition
from helix.scoring.generic import GenericScorer
from helix.scoring.instruments.paq import PAQScorer
from helix.tests.conftest import (
    make_max_responses,
    make_min_responses,
    make_specific_responses,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _item_ids(definition):
    return [item["item_id"] for item in definition["items"]]


def _make_responses_with_value(definition, value):
    """All items set to a constant value (ignores actual option range)."""
    return {item["item_id"]: value for item in definition["items"]}


# ---------------------------------------------------------------------------
# PHQ-2
# ---------------------------------------------------------------------------

class TestPHQ2:

    def test_all_min(self, load_definition, score):
        defn = load_definition("phq2")
        responses = make_min_responses(defn)
        result = score("phq2", responses)
        assert result.total_score == 0
        assert result.band == "minimal_or_none"
        assert result.safety_flags == []

    def test_all_max(self, load_definition, score):
        defn = load_definition("phq2")
        responses = make_max_responses(defn)
        result = score("phq2", responses)
        assert result.total_score == 6
        assert result.band == "elevated_symptoms"

    def test_threshold_boundary_below(self, load_definition, score):
        """Score 2 → minimal_or_none (expansion NOT triggered)."""
        defn = load_definition("phq2")
        responses = make_specific_responses(defn, {"phq2_01": 1, "phq2_02": 1})
        result = score("phq2", responses)
        assert result.total_score == 2
        assert result.band == "minimal_or_none"

    def test_threshold_boundary_at(self, load_definition, score):
        """Score 3 → elevated_symptoms (expansion trigger threshold)."""
        defn = load_definition("phq2")
        responses = make_specific_responses(defn, {"phq2_01": 2, "phq2_02": 1})
        result = score("phq2", responses)
        assert result.total_score == 3
        assert result.band == "elevated_symptoms"

    def test_metadata(self, load_definition, score):
        defn = load_definition("phq2")
        result = score("phq2", make_min_responses(defn))
        assert result.instrument_id == "phq2"
        assert result.metadata["method"] == "sum"
        assert result.metadata["n_items_scored"] == 2


# ---------------------------------------------------------------------------
# PHQ-9
# ---------------------------------------------------------------------------

class TestPHQ9:

    def test_all_min(self, load_definition, score):
        defn = load_definition("phq9")
        result = score("phq9", make_min_responses(defn))
        assert result.total_score == 0
        assert result.band == "minimal"

    def test_all_max(self, load_definition, score):
        defn = load_definition("phq9")
        result = score("phq9", make_max_responses(defn))
        assert result.total_score == 27
        assert result.band == "severe"

    @pytest.mark.parametrize("score_val,expected_band", [
        (4, "minimal"),
        (5, "mild"),
        (9, "mild"),
        (10, "moderate"),
        (14, "moderate"),
        (15, "moderately_severe"),
        (19, "moderately_severe"),
        (20, "severe"),
    ])
    def test_band_boundaries(self, load_definition, score, score_val, expected_band):
        """Distribute score_val across items 1-8 (item 9 = 0 to avoid safety flag)."""
        defn = load_definition("phq9")
        base = make_min_responses(defn)
        # items phq9_01..phq9_08 each have range 0-3; spread the target score
        # across them without touching phq9_09
        items_08 = [f"phq9_0{i}" for i in range(1, 9)]
        overrides = {}
        remaining = score_val
        for item_id in items_08:
            v = min(3, remaining)
            overrides[item_id] = v
            remaining -= v
            if remaining == 0:
                break
        overrides["phq9_09"] = 0
        responses = make_specific_responses(defn, overrides)
        result = score("phq9", responses)
        assert result.total_score == score_val, (
            f"Expected total={score_val}, got {result.total_score}"
        )
        assert result.band == expected_band

    @pytest.mark.parametrize("item9_value", [0, 1, 2, 3])
    def test_item9_safety_flag(self, load_definition, score, item9_value):
        """PHQ-9 item 9 at every value. value > 0 → SAFETY_PROTOCOL flag."""
        defn = load_definition("phq9")
        responses = make_specific_responses(defn, {"phq9_09": item9_value})
        result = score("phq9", responses)
        if item9_value == 0:
            assert result.safety_flags == [], (
                "item 9 = 0 must NOT produce a safety flag"
            )
        else:
            assert len(result.safety_flags) == 1
            flag = result.safety_flags[0]
            assert flag["item_id"] == "phq9_09"
            assert flag["value"] == item9_value
            assert flag["action"] == "SAFETY_PROTOCOL"

    def test_carry_forward_from_phq2(self, load_definition, score):
        """PHQ-2 items carried into PHQ-9 are included in the total.

        Scenario: PHQ-2 responses {phq2_01: 2, phq2_02: 3}
        Caller translates to child IDs: {phq9_01: 2, phq9_02: 3}
        User answers items 3-9 all as 0.
        Expected total: 2 + 3 + 0*7 = 5 → band: mild
        """
        defn = load_definition("phq9")
        # New responses from user (items 3-9 only)
        new_responses = {f"phq9_0{i}": 0 for i in range(3, 10)}
        # Carried responses already translated to child item IDs by caller
        carried = {"phq9_01": 2, "phq9_02": 3}
        result = score("phq9", new_responses, carried_responses=carried)
        assert result.total_score == 5
        assert result.band == "mild"
        assert result.metadata["n_items_scored"] == 9

    def test_no_safety_flag_carry_forward_item9_zero(self, load_definition, score):
        """Carry-forward items 1-2 only. Item 9 answered as 0. No safety flag."""
        defn = load_definition("phq9")
        new_responses = {f"phq9_0{i}": 0 for i in range(3, 10)}
        carried = {"phq9_01": 3, "phq9_02": 3}
        result = score("phq9", new_responses, carried_responses=carried)
        assert result.safety_flags == []
        assert result.total_score == 6


# ---------------------------------------------------------------------------
# GAD-2
# ---------------------------------------------------------------------------

class TestGAD2:

    def test_all_min(self, load_definition, score):
        defn = load_definition("gad2")
        result = score("gad2", make_min_responses(defn))
        assert result.total_score == 0
        assert result.band == "minimal_or_none"

    def test_all_max(self, load_definition, score):
        defn = load_definition("gad2")
        result = score("gad2", make_max_responses(defn))
        assert result.total_score == 6
        assert result.band == "elevated_symptoms"

    def test_threshold_below(self, load_definition, score):
        defn = load_definition("gad2")
        responses = make_specific_responses(defn, {"gad2_01": 1, "gad2_02": 1})
        result = score("gad2", responses)
        assert result.total_score == 2
        assert result.band == "minimal_or_none"

    def test_threshold_at(self, load_definition, score):
        defn = load_definition("gad2")
        responses = make_specific_responses(defn, {"gad2_01": 2, "gad2_02": 1})
        result = score("gad2", responses)
        assert result.total_score == 3
        assert result.band == "elevated_symptoms"


# ---------------------------------------------------------------------------
# GAD-7
# ---------------------------------------------------------------------------

class TestGAD7:

    def test_all_min(self, load_definition, score):
        defn = load_definition("gad7")
        result = score("gad7", make_min_responses(defn))
        assert result.total_score == 0
        assert result.band == "minimal"

    def test_all_max(self, load_definition, score):
        defn = load_definition("gad7")
        result = score("gad7", make_max_responses(defn))
        assert result.total_score == 21
        assert result.band == "severe"

    @pytest.mark.parametrize("score_val,expected_band", [
        (4, "minimal"),
        (5, "mild"),
        (9, "mild"),
        (10, "moderate"),
        (14, "moderate"),
        (15, "severe"),
        (21, "severe"),
    ])
    def test_band_boundaries(self, load_definition, score, score_val, expected_band):
        defn = load_definition("gad7")
        items = [f"gad7_0{i}" for i in range(1, 8)]
        overrides = {}
        remaining = score_val
        for item_id in items:
            v = min(3, remaining)
            overrides[item_id] = v
            remaining -= v
            if remaining == 0:
                break
        responses = make_specific_responses(defn, overrides)
        result = score("gad7", responses)
        assert result.total_score == score_val
        assert result.band == expected_band

    def test_carry_forward_from_gad2(self, load_definition, score):
        """GAD-2 items carried into GAD-7.

        Scenario: {gad7_01: 3, gad7_02: 3} carried; items 3-7 all 0.
        Expected total: 6 → band: mild
        """
        new_responses = {f"gad7_0{i}": 0 for i in range(3, 8)}
        carried = {"gad7_01": 3, "gad7_02": 3}
        result = score("gad7", new_responses, carried_responses=carried)
        assert result.total_score == 6
        assert result.band == "mild"
        assert result.metadata["n_items_scored"] == 7


# ---------------------------------------------------------------------------
# PAQ-S
# ---------------------------------------------------------------------------

class TestPAQS:

    def test_all_min(self, load_definition, score):
        defn = load_definition("paq_s")
        result = score("paq_s", make_min_responses(defn))
        assert result.total_score == 6   # 6 items × min value 1
        assert result.band == "low_alexithymia"

    def test_all_max(self, load_definition, score):
        defn = load_definition("paq_s")
        result = score("paq_s", make_max_responses(defn))
        assert result.total_score == 42  # 6 items × max value 7
        assert result.band == "high_alexithymia"

    @pytest.mark.parametrize("score_val,expected_band", [
        (6,  "low_alexithymia"),
        (18, "low_alexithymia"),
        (19, "moderate_alexithymia"),
        (29, "moderate_alexithymia"),
        (30, "high_alexithymia"),
        (42, "high_alexithymia"),
    ])
    def test_band_boundaries(self, load_definition, score, score_val, expected_band):
        defn = load_definition("paq_s")
        # Distribute score_val across 6 items (each can be 1–7)
        items = [item["item_id"] for item in defn["items"]]
        overrides = {}
        remaining = score_val
        for item_id in items:
            v = min(7, max(1, remaining - (len(items) - len(overrides) - 1)))
            v = min(v, remaining - (len(items) - len(overrides) - 1))
            v = max(1, min(7, v))
            overrides[item_id] = v
            remaining -= v
            if remaining == 0:
                break
        # Simpler: just set all to 1 and override first items
        # Use helper to produce target sum for simple cases
        base = {item_id: 1 for item_id in items}
        total_base = len(items)  # = 6
        extra = score_val - total_base
        for item_id in items:
            add = min(6, extra)  # can add up to 6 to bring 1→7
            base[item_id] = 1 + add
            extra -= add
            if extra <= 0:
                break
        result = score("paq_s", base)
        assert result.total_score == score_val, (
            f"Expected {score_val}, got {result.total_score} with {base}"
        )
        assert result.band == expected_band

    def test_no_safety_flags(self, load_definition, score):
        defn = load_definition("paq_s")
        result = score("paq_s", make_max_responses(defn))
        assert result.safety_flags == []


# ---------------------------------------------------------------------------
# PAQ (custom scorer)
# ---------------------------------------------------------------------------

class TestPAQ:

    def test_all_min(self, load_definition, score):
        """24 items × min value 1 = total 24. Subscales: N_DIF=4, P_DIF=4, N_DDF=4, P_DDF=4, G_EOT=8."""
        defn = load_definition("paq")
        result = score("paq", make_min_responses(defn))
        assert result.total_score == 24
        assert result.band == "low_alexithymia"
        ss = result.subscale_scores
        assert ss["N_DIF"] == 4   # 4 items × 1
        assert ss["P_DIF"] == 4
        assert ss["N_DDF"] == 4
        assert ss["P_DDF"] == 4
        assert ss["G_EOT"] == 8   # 8 items × 1

    def test_all_max(self, load_definition, score):
        """24 items × max value 7 = total 168. Subscales: ×4 items = 28, G_EOT ×8 = 56."""
        defn = load_definition("paq")
        result = score("paq", make_max_responses(defn))
        assert result.total_score == 168
        assert result.band == "high_alexithymia"
        ss = result.subscale_scores
        assert ss["N_DIF"] == 28
        assert ss["P_DIF"] == 28
        assert ss["N_DDF"] == 28
        assert ss["P_DDF"] == 28
        assert ss["G_EOT"] == 56

    def test_midpoint(self, load_definition, score):
        """All items at value 4: total=96, each 4-item subscale=16, G_EOT=32."""
        defn = load_definition("paq")
        responses = {item["item_id"]: 4 for item in defn["items"]}
        result = score("paq", responses)
        assert result.total_score == 96
        assert result.band == "moderate_alexithymia"
        ss = result.subscale_scores
        assert ss["N_DIF"] == 16
        assert ss["P_DIF"] == 16
        assert ss["N_DDF"] == 16
        assert ss["P_DDF"] == 16
        assert ss["G_EOT"] == 32

    @pytest.mark.parametrize("score_val,expected_band", [
        (24,  "low_alexithymia"),
        (60,  "low_alexithymia"),
        (61,  "moderate_alexithymia"),
        (110, "moderate_alexithymia"),
        (111, "high_alexithymia"),
        (168, "high_alexithymia"),
    ])
    def test_band_boundaries(self, load_definition, score, score_val, expected_band):
        """Band boundaries from Preece et al. 2018."""
        defn = load_definition("paq")
        # Set all items to 1, then add extra to first items to reach target
        items = [item["item_id"] for item in defn["items"]]
        base = {item_id: 1 for item_id in items}
        extra = score_val - 24  # 24 = min total
        for item_id in items:
            add = min(6, extra)
            base[item_id] = 1 + add
            extra -= add
            if extra <= 0:
                break
        result = score("paq", base)
        assert result.total_score == score_val
        assert result.band == expected_band

    def test_subscale_items_map_to_correct_groups(self, load_definition, score):
        """Set N_DIF items to max, all others to min. Verify only N_DIF subscale is elevated."""
        defn = load_definition("paq")
        base = make_min_responses(defn)
        n_dif_items = ["paq_01", "paq_02", "paq_03", "paq_04"]
        for item_id in n_dif_items:
            base[item_id] = 7
        result = score("paq", base)
        ss = result.subscale_scores
        assert ss["N_DIF"] == 28   # 4 × 7
        assert ss["P_DIF"] == 4    # 4 × 1
        assert ss["N_DDF"] == 4
        assert ss["P_DDF"] == 4
        assert ss["G_EOT"] == 8

    def test_carry_forward_from_paq_s(self, load_definition, score):
        """PAQ-S items carried into PAQ (non-sequential mapping).

        PAQ-S → PAQ mapping (from JSON def):
            paq_s_01 → paq_09
            paq_s_02 → paq_01
            paq_s_03 → paq_13
            paq_s_04 → paq_05
            paq_s_05 → paq_17
            paq_s_06 → paq_18

        Caller translates and passes carried_responses keyed by child item IDs.
        Scenario: all PAQ-S items answered as 7 (max), remaining PAQ items as 1.
        """
        defn = load_definition("paq")
        all_items = [item["item_id"] for item in defn["items"]]
        carried_ids = {"paq_09", "paq_01", "paq_13", "paq_05", "paq_17", "paq_18"}
        new_items = {iid: 1 for iid in all_items if iid not in carried_ids}
        carried = {iid: 7 for iid in carried_ids}
        result = score("paq", new_items, carried_responses=carried)
        # 6 carried items at 7, 18 new items at 1
        expected_total = 6 * 7 + 18 * 1  # 42 + 18 = 60
        assert result.total_score == expected_total
        assert result.band == "low_alexithymia"
        assert result.metadata["n_items_scored"] == 24

    def test_no_safety_flags(self, load_definition, score):
        defn = load_definition("paq")
        result = score("paq", make_max_responses(defn))
        assert result.safety_flags == []


# ---------------------------------------------------------------------------
# DERS-16
# ---------------------------------------------------------------------------

class TestDERS16:

    def test_all_min(self, load_definition, score):
        defn = load_definition("ders16")
        result = score("ders16", make_min_responses(defn))
        assert result.total_score == 16
        # Subscales
        ss = result.subscale_scores
        assert ss["clarity"] == 2
        assert ss["goals"] == 3
        assert ss["impulse"] == 3
        assert ss["strategies"] == 5
        assert ss["nonacceptance"] == 3

    def test_all_max(self, load_definition, score):
        defn = load_definition("ders16")
        result = score("ders16", make_max_responses(defn))
        assert result.total_score == 80
        ss = result.subscale_scores
        assert ss["clarity"] == 10
        assert ss["goals"] == 15
        assert ss["impulse"] == 15
        assert ss["strategies"] == 25
        assert ss["nonacceptance"] == 15

    def test_midpoint(self, load_definition, score):
        defn = load_definition("ders16")
        responses = {item["item_id"]: 3 for item in defn["items"]}
        result = score("ders16", responses)
        assert result.total_score == 48


# ---------------------------------------------------------------------------
# PSS-10
# ---------------------------------------------------------------------------

class TestPSS10:

    def test_all_min(self, load_definition, score):
        # min value is 0.
        # However, items 4, 5, 7, 8 are reverse scored.
        # (max+min)-0 = (4+0)-0 = 4.
        # So forward items (6 items) contribute 0, reverse items (4 items) contribute 4.
        # Total = 16.
        defn = load_definition("pss10")
        result = score("pss10", make_min_responses(defn))
        assert result.total_score == 16
        assert result.band == "moderate"

    def test_all_max(self, load_definition, score):
        # max value is 4.
        # Reverse items become (4+0)-4 = 0.
        # Forward items (6) contribute 4 * 6 = 24.
        # Total = 24.
        defn = load_definition("pss10")
        result = score("pss10", make_max_responses(defn))
        assert result.total_score == 24
        assert result.band == "moderate"

    def test_all_reverse_max_forward_min(self, load_definition, score):
        # Reverse items answered 4 (score 0), forward items answered 0 (score 0). Total = 0.
        defn = load_definition("pss10")
        responses = make_min_responses(defn)
        responses["pss10_04"] = 4
        responses["pss10_05"] = 4
        responses["pss10_07"] = 4
        responses["pss10_08"] = 4
        result = score("pss10", responses)
        assert result.total_score == 0
        assert result.band == "low"

    def test_band_boundaries(self, load_definition, score):
        defn = load_definition("pss10")
        responses = make_min_responses(defn)
        # To get pure points easily, we set reverse items to 4 (so they score 0).
        # Now we have 6 forward items (max 24 points).
        for iid in ["pss10_04", "pss10_05", "pss10_07", "pss10_08"]:
            responses[iid] = 4
            
        def _get_band(pts):
            resp = dict(responses)
            items = ["pss10_01", "pss10_02", "pss10_03", "pss10_06", "pss10_09", "pss10_10"]
            rem = pts
            for iid in items:
                v = min(4, rem)
                resp[iid] = v
                rem -= v
            return score("pss10", resp).band

        assert _get_band(13) == "low"
        assert _get_band(14) == "moderate"
        assert _get_band(26) == "moderate"
        
        # To get to 27, we need to use reverse items. Set one reverse item to 3 (scores 1). 
        # Plus 24 from forward items = 25. Still not enough.
        # Set all reverse items to 0 (scores 4*4=16). Plus 6 forward items at 0 = 16.
        resp = make_min_responses(defn) # reverse items score 4*4=16. forward = 0. total = 16.
        # Add 11 points to forward items to reach 27
        rem = 11
        items = ["pss10_01", "pss10_02", "pss10_03", "pss10_06", "pss10_09", "pss10_10"]
        for iid in items:
            v = min(4, rem)
            resp[iid] = v
            rem -= v
        assert score("pss10", resp).band == "high"


# ---------------------------------------------------------------------------
# DTS
# ---------------------------------------------------------------------------

class TestDTS:

    def test_all_min(self, load_definition, score):
        # min is 1. Item 6 is reverse scored: (5+1)-1 = 5.
        # Forward items (14) * 1 = 14. Total = 19.
        defn = load_definition("dts")
        result = score("dts", make_min_responses(defn))
        assert result.total_score == 19
        ss = result.subscale_scores
        assert ss["tolerance"] == 3     # 1,3,5 -> 1*3=3
        assert ss["absorption"] == 3    # 2,4,15 -> 1*3=3
        assert ss["appraisal"] == 10    # 7,9,10,11,12 -> 1*5=5 + item 6 (5) = 10
        assert ss["regulation"] == 3    # 8,13,14 -> 1*3=3

    def test_all_max(self, load_definition, score):
        # max is 5. Item 6: (5+1)-5 = 1.
        # Forward items (14) * 5 = 70. Total = 71.
        defn = load_definition("dts")
        result = score("dts", make_max_responses(defn))
        assert result.total_score == 71


# ---------------------------------------------------------------------------
# ERQ
# ---------------------------------------------------------------------------

class TestERQ:

    def test_all_min(self, load_definition, score):
        defn = load_definition("erq")
        result = score("erq", make_min_responses(defn))
        assert result.total_score == 10
        ss = result.subscale_scores
        assert ss["cognitive_reappraisal"] == 1.0
        assert ss["expressive_suppression"] == 1.0

    def test_all_max(self, load_definition, score):
        defn = load_definition("erq")
        result = score("erq", make_max_responses(defn))
        assert result.total_score == 70
        ss = result.subscale_scores
        assert ss["cognitive_reappraisal"] == 7.0
        assert ss["expressive_suppression"] == 7.0

    def test_mixed(self, load_definition, score):
        defn = load_definition("erq")
        responses = make_min_responses(defn) # all 1
        # Reappraisal items: 1, 3, 5, 7, 8, 10
        # Set them to 5. Mean should be 5.
        for iid in ["erq_01", "erq_03", "erq_05", "erq_07", "erq_08", "erq_10"]:
            responses[iid] = 5
        
        # Suppression items: 2, 4, 6, 9. Keep at 1.
        result = score("erq", responses)
        assert result.total_score == (6 * 5) + (4 * 1)
        ss = result.subscale_scores
        assert ss["cognitive_reappraisal"] == 5.0
        assert ss["expressive_suppression"] == 1.0


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class TestRegistry:

    def test_all_venus_instruments_registered(self):
        from helix.scoring import registry
        registered = registry.all_registered()
        for inst_id in ("phq2", "phq9", "gad2", "gad7", "paq_s", "paq"):
            assert inst_id in registered, f"'{inst_id}' not found in registry"

    def test_get_scorer_unknown_raises(self):
        from helix.scoring import registry
        with pytest.raises(KeyError, match="not_an_instrument"):
            registry.get_scorer("not_an_instrument")

    def test_generic_scorer_type_for_sum_instruments(self):
        from helix.scoring import registry
        from helix.scoring.generic import GenericScorer
        for inst_id in ("phq2", "phq9", "gad2", "gad7", "paq_s"):
            assert isinstance(registry.get_scorer(inst_id), GenericScorer)

    def test_paq_scorer_type(self):
        from helix.scoring import registry
        from helix.scoring.instruments.paq import PAQScorer
        assert isinstance(registry.get_scorer("paq"), PAQScorer)


# ---------------------------------------------------------------------------
# Validity checks
# ---------------------------------------------------------------------------

class TestValidityChecks:

    def test_longstring_detected_8_identical(self, load_definition, score):
        """8 identical consecutive responses → longstring warning."""
        defn = load_definition("phq9")
        responses = {item["item_id"]: 1 for item in defn["items"]}
        # PHQ-9 has 9 items — all at value 1 → longstring detected
        result = score("phq9", responses)
        assert any("longstring" in w for w in result.validity_warnings), (
            f"Expected longstring warning, got: {result.validity_warnings}"
        )

    def test_longstring_not_detected_7_then_different(self, load_definition, score):
        """7 identical then different → NOT a longstring."""
        defn = load_definition("phq9")
        responses = {item["item_id"]: 1 for item in defn["items"]}
        responses["phq9_09"] = 0  # break the run at item 9 (only 8 items → 7 + 1 different)
        # Actually PHQ-9 has 9 items; items 1-8 = value 1, item 9 = 0 → run of 8, not 7
        # Let's explicitly set only 7 identical then different
        items = [item["item_id"] for item in defn["items"]]
        for iid in items[:7]:
            responses[iid] = 2
        responses[items[7]] = 1  # different at position 8
        responses[items[8]] = 0  # position 9 (safety item)
        result = score("phq9", responses)
        assert not any("longstring" in w for w in result.validity_warnings), (
            f"Unexpected longstring warning: {result.validity_warnings}"
        )

    def test_rapid_response_detected(self, load_definition, score):
        """Median inter-item gap < 1.0s → rapid response warning."""
        defn = load_definition("phq2")
        responses = make_min_responses(defn)
        # Timestamps: 0.0, 0.4 → gap = 0.4s < 1.0s threshold
        timestamps = [0.0, 0.4]
        result = score("phq2", responses, timestamps=timestamps)
        assert any("rapid_response" in w for w in result.validity_warnings)

    def test_rapid_response_not_detected_slow(self, load_definition, score):
        """Median inter-item gap > 1.0s → no rapid response warning."""
        defn = load_definition("phq2")
        responses = make_min_responses(defn)
        timestamps = [0.0, 5.0]
        result = score("phq2", responses, timestamps=timestamps)
        assert not any("rapid_response" in w for w in result.validity_warnings)

    def test_no_timestamps_no_warning(self, load_definition, score):
        defn = load_definition("phq2")
        result = score("phq2", make_min_responses(defn), timestamps=None)
        assert not any("rapid_response" in w for w in result.validity_warnings)


# ---------------------------------------------------------------------------
# Condition parser (unit tests — not instrument-specific)
# ---------------------------------------------------------------------------

class TestConditionParser:

    @pytest.mark.parametrize("condition,value,expected", [
        ("value > 0", 0, False),
        ("value > 0", 1, True),
        ("value > 0", 3, True),
        ("value >= 3", 2, False),
        ("value >= 3", 3, True),
        ("value == 2", 1, False),
        ("value == 2", 2, True),
        ("value < 5", 4, True),
        ("value < 5", 5, False),
        ("value <= 3", 3, True),
        ("value <= 3", 4, False),
    ])
    def test_evaluate_item_condition(self, condition, value, expected):
        assert _evaluate_item_condition(condition, value) == expected

    def test_unknown_condition_returns_false(self):
        assert _evaluate_item_condition("something weird", 5) is False

    def test_empty_condition_returns_false(self):
        assert _evaluate_item_condition("", 5) is False
