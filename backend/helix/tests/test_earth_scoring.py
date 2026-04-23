"""Tests for Earth Planet instruments."""

import pytest

from helix.scoring.registry import get_scorer
from helix.tests.conftest import make_max_responses, make_min_responses


class TestEarthInstruments:

    def test_aces_suppress_band(self, load_definition, score):
        """ACEs should store the band internally but define suppress_band_from_user."""
        defn = load_definition("aces")
        assert defn.get("suppress_band_from_user") is True
        
        # Test max score (10)
        responses = make_max_responses(defn)
        result = score("aces", responses)
        assert result.total_score == 10
        assert result.band == "4+"  # Internal ScoreResult retains band

    def test_brs_scoring(self, load_definition, score):
        defn = load_definition("brs")
        # All min responses based on the response option sets
        # The user's "lowest resilience" answers would correspond to
        # 1 on forward items, and 1 on reverse items (which means strongly agree with negative)
        # We just test the generic scorer correctly computes the mean of the values provided.
        responses = {f"brs_0{i}": 1 for i in range(1, 7)}
        result = score("brs", responses)
        assert result.total_score == 1.0
        assert result.band == "low"
        
        responses_max = {f"brs_0{i}": 5 for i in range(1, 7)}
        result_max = score("brs", responses_max)
        assert result_max.total_score == 5.0
        assert result_max.band == "high"

    def test_rses_scoring(self, load_definition, score):
        defn = load_definition("rses")
        responses = make_min_responses(defn)
        result = score("rses", responses)
        assert result.total_score == 0
        assert result.band == "low"

        responses_max = make_max_responses(defn)
        result_max = score("rses", responses_max)
        assert result_max.total_score == 30
        assert result_max.band == "high"

    def test_scs_sf_scoring(self, load_definition, score):
        defn = load_definition("scs_sf")
        responses = make_min_responses(defn)
        result = score("scs_sf", responses)
        assert result.total_score == 1.0
        
        # Subscales
        ss = result.subscale_scores
        assert ss["self_kindness"] == 1.0
        assert ss["self_judgment"] == 1.0
        assert ss["common_humanity"] == 1.0
        assert ss["isolation"] == 1.0
        assert ss["mindfulness"] == 1.0
        assert ss["over_identification"] == 1.0

    def test_bfi_s_scoring(self, load_definition, score):
        defn = load_definition("bfi_s")
        responses = make_max_responses(defn)
        result = score("bfi_s", responses)
        assert result.total_score == 5.0
        ss = result.subscale_scores
        assert ss["extraversion"] == 5.0
        assert ss["agreeableness"] == 5.0
        assert ss["conscientiousness"] == 5.0
        assert ss["neuroticism"] == 5.0
        assert ss["openness"] == 5.0

    def test_via_is_p_scoring(self, load_definition, score):
        defn = load_definition("via_is_p")
        responses = make_min_responses(defn)
        result = score("via_is_p", responses)
        assert result.total_score == 1.0
        ss = result.subscale_scores
        assert ss["creativity"] == 1.0

    def test_ipip50_scoring(self, load_definition, score):
        defn = load_definition("ipip50")
        responses = make_max_responses(defn)
        result = score("ipip50", responses)
        assert result.total_score == 250
        ss = result.subscale_scores
        assert ss["extraversion"] == 50
        assert ss["agreeableness"] == 50
        assert ss["conscientiousness"] == 50
        assert ss["neuroticism"] == 50
        assert ss["openness"] == 50
