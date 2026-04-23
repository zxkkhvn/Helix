import pytest
from helix.scoring.base import ScoreResult
from helix.tests.conftest import (
    make_max_responses,
    make_min_responses,
    make_specific_responses,
)


class TestVLQ:

    def test_all_equal(self, load_definition, score):
        """All domains: importance == consistency -> zero gap."""
        responses = {}
        for i in range(1, 11):
            responses[f"vlq_{i:02d}_imp"] = 5
            responses[f"vlq_{i:02d}_con"] = 5
        result = score("vlq", responses)
        assert result.total_score == 0.0  # mean_gap = 0
        assert result.metadata["mean_gap"] == 0.0
        assert result.metadata["composite_score"] == 25.0  # 5*5 = 25

    def test_max_gap(self, load_definition, score):
        """All domains: importance = 10, consistency = 1 -> gap = 9."""
        responses = {}
        for i in range(1, 11):
            responses[f"vlq_{i:02d}_imp"] = 10
            responses[f"vlq_{i:02d}_con"] = 1
        result = score("vlq", responses)
        assert result.total_score == 9.0  # all domains have imp >= 7
        assert result.metadata["mean_gap"] == 9.0
        assert result.metadata["domains_counted_for_gap"] == 10

    def test_gap_only_important_domains(self, load_definition, score):
        """Only domains with importance >= 7 count for mean_gap."""
        responses = {}
        # Domain 1: imp=10, con=2 -> gap=8 (counts)
        responses["vlq_01_imp"] = 10
        responses["vlq_01_con"] = 2
        # Domain 2: imp=3, con=1 -> gap=2 (does NOT count, imp < 7)
        responses["vlq_02_imp"] = 3
        responses["vlq_02_con"] = 1
        # Domains 3-10: imp=1, con=1 -> gap=0 (do not count)
        for i in range(3, 11):
            responses[f"vlq_{i:02d}_imp"] = 1
            responses[f"vlq_{i:02d}_con"] = 1
        result = score("vlq", responses)
        assert result.metadata["domains_counted_for_gap"] == 1
        assert result.total_score == 8.0  # only domain 1

    def test_no_important_domains(self, load_definition, score):
        """If no domain has importance >= 7, mean_gap = 0."""
        responses = {}
        for i in range(1, 11):
            responses[f"vlq_{i:02d}_imp"] = 5
            responses[f"vlq_{i:02d}_con"] = 1
        result = score("vlq", responses)
        assert result.total_score == 0.0  # no domains qualify
        assert result.metadata["domains_counted_for_gap"] == 0

    def test_domain_profiles(self, load_definition, score):
        """Verify domain profile structure in metadata."""
        responses = {}
        for i in range(1, 11):
            responses[f"vlq_{i:02d}_imp"] = 7
            responses[f"vlq_{i:02d}_con"] = 4
        result = score("vlq", responses)
        profiles = result.metadata["domain_profiles"]
        assert len(profiles) == 10
        assert profiles[0]["domain"] == "family"
        assert profiles[0]["importance"] == 7
        assert profiles[0]["consistency"] == 4
        assert profiles[0]["gap"] == 3


class TestAAQ2:

    def test_all_min(self, load_definition, score):
        defn = load_definition("aaq2")
        result = score("aaq2", make_min_responses(defn))
        assert result.total_score == 7.0
        assert result.band == "low_inflexibility"

    def test_all_max(self, load_definition, score):
        defn = load_definition("aaq2")
        result = score("aaq2", make_max_responses(defn))
        assert result.total_score == 49.0
        assert result.band == "high_inflexibility"

    def test_clinical_boundary(self, load_definition, score):
        defn = load_definition("aaq2")
        # 27 -> moderate
        responses = {f"aaq2_{i:02d}": 4 for i in range(1, 8)}
        responses["aaq2_07"] = 3  # 6*4 + 3 = 27
        result = score("aaq2", responses)
        assert result.total_score == 27.0
        assert result.band == "moderate"
        # 28 -> high
        responses["aaq2_07"] = 4  # 7*4 = 28
        result = score("aaq2", responses)
        assert result.total_score == 28.0
        assert result.band == "high_inflexibility"


class TestCompACT:

    def test_all_min_raw(self, load_definition, score):
        """All items at 0. Reverse items become 6, forward items stay 0."""
        defn = load_definition("compact")
        result = score("compact", make_min_responses(defn))
        # Forward items (1,5,7,10,14,17,20,21,23) = 9 items * 0 = 0
        # Reverse items (2,3,4,6,8,9,11,12,13,15,16,18,19,22) = 14 items * 6 = 84
        assert result.total_score == 84.0

    def test_all_max_raw(self, load_definition, score):
        """All items at 6. Reverse items become 0, forward items stay 6."""
        defn = load_definition("compact")
        result = score("compact", make_max_responses(defn))
        # Forward items = 9 * 6 = 54
        # Reverse items = 14 * 0 = 0
        assert result.total_score == 54.0

    def test_all_sixes_post_reversal(self, load_definition, score):
        """Set forward items to 6, reverse items to 0 -> all score 6 after reversal."""
        defn = load_definition("compact")
        forward = ["compact_01", "compact_05", "compact_07", "compact_10",
                    "compact_14", "compact_17", "compact_20", "compact_21", "compact_23"]
        reverse = ["compact_02", "compact_03", "compact_04", "compact_06",
                    "compact_08", "compact_09", "compact_11", "compact_12",
                    "compact_13", "compact_15", "compact_16", "compact_18",
                    "compact_19", "compact_22"]
        responses = {}
        for item_id in forward:
            responses[item_id] = 6
        for item_id in reverse:
            responses[item_id] = 0
        result = score("compact", responses)
        assert result.total_score == 138.0  # 23 * 6
        assert result.band == "high_flexibility"

    def test_subscale_valued_action(self, load_definition, score):
        """Verify valued action subscale (no reverse items in this subscale)."""
        defn = load_definition("compact")
        responses = {f"compact_{i:02d}": 3 for i in range(1, 24)}
        result = score("compact", responses)
        # VA items: 1,5,7,10,14,17,21,23 — all forward, all 3 -> sum = 24
        assert result.subscale_scores["valued_action"] == 24.0


class TestMLQ:

    def test_all_min(self, load_definition, score):
        defn = load_definition("mlq")
        result = score("mlq", make_min_responses(defn))
        # Item 9 is reverse: min=1 -> reversed = 7
        # Other 9 items: 9 * 1 = 9
        # Total = 9 + 7 = 16
        assert result.total_score == 16.0

    def test_all_max(self, load_definition, score):
        defn = load_definition("mlq")
        result = score("mlq", make_max_responses(defn))
        # Item 9 is reverse: max=7 -> reversed = 1
        # Other 9 items: 9 * 7 = 63
        # Total = 63 + 1 = 64
        assert result.total_score == 64.0

    def test_reverse_item9(self, load_definition, score):
        defn = load_definition("mlq")
        responses = {f"mlq_{i:02d}": 4 for i in range(1, 11)}
        responses["mlq_09"] = 2  # reversed: 8-2 = 6
        result = score("mlq", responses)
        # 9 items * 4 = 36 + reversed item 9 = 6 -> total = 42
        assert result.total_score == 42.0

    def test_subscale_independence(self, load_definition, score):
        defn = load_definition("mlq")
        responses = {}
        # Presence items (1,4,5,6,9): set to 7
        for item_id in ["mlq_01", "mlq_04", "mlq_05", "mlq_06"]:
            responses[item_id] = 7
        responses["mlq_09"] = 1  # reversed to 7
        # Search items (2,3,7,8,10): set to 1
        for item_id in ["mlq_02", "mlq_03", "mlq_07", "mlq_08", "mlq_10"]:
            responses[item_id] = 1
        result = score("mlq", responses)
        assert result.subscale_scores["presence"] == 35.0  # 5 * 7
        assert result.subscale_scores["search"] == 5.0  # 5 * 1
        assert result.band is None  # no total bands


class TestSWLS:

    def test_all_min(self, load_definition, score):
        defn = load_definition("swls")
        result = score("swls", make_min_responses(defn))
        assert result.total_score == 5.0
        assert result.band == "extremely_dissatisfied"

    def test_all_max(self, load_definition, score):
        defn = load_definition("swls")
        result = score("swls", make_max_responses(defn))
        assert result.total_score == 35.0
        assert result.band == "extremely_satisfied"

    def test_neutral(self, load_definition, score):
        defn = load_definition("swls")
        responses = {f"swls_{i:02d}": 4 for i in range(1, 6)}  # 5 * 4 = 20
        result = score("swls", responses)
        assert result.total_score == 20.0
        assert result.band == "neutral"

    def test_band_boundaries(self, load_definition, score):
        defn = load_definition("swls")
        # 19 -> slightly_dissatisfied
        responses = {f"swls_{i:02d}": 4 for i in range(1, 6)}
        responses["swls_05"] = 3  # 4*4 + 3 = 19
        result = score("swls", responses)
        assert result.total_score == 19.0
        assert result.band == "slightly_dissatisfied"
        # 21 -> slightly_satisfied
        responses["swls_05"] = 5  # 4*4 + 5 = 21
        result = score("swls", responses)
        assert result.total_score == 21.0
        assert result.band == "slightly_satisfied"
