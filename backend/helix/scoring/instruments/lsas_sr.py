from __future__ import annotations
from typing import Dict, Any, Optional

from helix.scoring.base import BaseScorer, ScoreResult


class LSASSRScorer(BaseScorer):
    """
    Custom scorer for Liebowitz Social Anxiety Scale (LSAS-SR).
    Handles both the Short (12 situations) and Full (24 situations) forms.
    Computes fear, avoidance, and total scores. For the full form, also
    computes performance anxiety and social interaction subscales.
    """

    PERFORMANCE_SITUATIONS = {1, 2, 3, 4, 6, 8, 9, 13, 14, 16, 17, 20, 21}
    SOCIAL_SITUATIONS = {5, 7, 10, 11, 12, 15, 18, 19, 22, 23, 24}

    def __init__(self, definition: Dict[str, Any]) -> None:
        self._def = definition
        self.instrument_id = definition["instrument_id"]
        self.items = definition["items"]
        self.scoring = definition["scoring"]
        self._bands = self.scoring.get("bands", [])
        
        self.is_full = self.instrument_id == "lsas_sr_full"

    def score(
        self,
        responses: dict[str, int | float | str],
        timestamps: Optional[list[float]] = None,
        carried_responses: Optional[dict[str, int | float | str]] = None,
    ) -> ScoreResult:
        all_responses = dict(responses)
        if carried_responses:
            all_responses.update(carried_responses)

        fear_total = 0
        avoidance_total = 0
        
        perf_total = 0
        social_total = 0

        for item in self.items:
            item_id = item["item_id"]
            if item_id not in all_responses:
                continue

            try:
                val = int(all_responses[item_id])
            except (ValueError, TypeError):
                val = 0

            # Determine situation number
            # Item format: lsas_s_01_fear or lsas_f_24_avoid
            parts = item_id.split("_")
            try:
                sit_num = int(parts[2])
            except (IndexError, ValueError):
                continue
                
            is_fear = "fear" in item_id
            is_avoid = "avoid" in item_id

            if is_fear:
                fear_total += val
            elif is_avoid:
                avoidance_total += val

            if self.is_full:
                if sit_num in self.PERFORMANCE_SITUATIONS:
                    perf_total += val
                elif sit_num in self.SOCIAL_SITUATIONS:
                    social_total += val

        total_score = fear_total + avoidance_total

        assigned_band = None
        for band in self._bands:
            b_min = band.get("min", float("-inf"))
            b_max = band.get("max", float("inf"))
            if b_min <= total_score <= b_max:
                assigned_band = band["label"]
                break
                
        band_description = None
        band_desc_map = self._def.get("band_descriptions", {})
        if assigned_band and assigned_band in band_desc_map:
            band_description = band_desc_map[assigned_band]

        subscales = {
            "fear": fear_total,
            "avoidance": avoidance_total
        }
        
        if self.is_full:
            subscales["performance_anxiety"] = perf_total
            subscales["social_interaction"] = social_total

        return ScoreResult(
            instrument_id=self.instrument_id,
            total_score=total_score,
            subscale_scores=subscales,
            band=assigned_band,
            band_description=band_description,
            safety_flags=[],
            validity_warnings=[],
            metadata={},
        )

def create_scorer(definition: Dict[str, Any]) -> BaseScorer:
    return LSASSRScorer(definition)
