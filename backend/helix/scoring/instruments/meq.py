from __future__ import annotations
from typing import Dict, Any, Optional

from helix.scoring.base import BaseScorer, ScoreResult

class MEQScorer(BaseScorer):
    """
    Custom scorer for the Morningness-Eveningness Questionnaire (MEQ).
    Calculates the total score, assigns chronotype bands, and calculates 
    the recommended start time for light therapy based on the score.
    """

    def __init__(self, definition: Dict[str, Any]) -> None:
        self._def = definition
        self.instrument_id = definition["instrument_id"]
        self.items = definition["items"]
        self.scoring = definition["scoring"]
        self._item_order = [item["item_id"] for item in self.items]
        self._bands = self.scoring.get("bands")

    def _get_light_therapy_time(self, score: int) -> str:
        if 23 <= score <= 26: return "8:15 AM"
        if 27 <= score <= 30: return "8:00 AM"
        if 31 <= score <= 34: return "7:45 AM"
        if 35 <= score <= 38: return "7:30 AM"
        if 39 <= score <= 41: return "7:15 AM"
        if 42 <= score <= 45: return "7:00 AM"
        if 46 <= score <= 49: return "6:45 AM"
        if 50 <= score <= 53: return "6:30 AM"
        if 54 <= score <= 57: return "6:15 AM"
        if 58 <= score <= 61: return "6:00 AM"
        if 62 <= score <= 65: return "5:45 AM"
        if 66 <= score <= 68: return "5:30 AM"
        if 69 <= score <= 72: return "5:15 AM"
        if 73 <= score <= 76: return "5:00 AM"
        return "Consult clinician" # For scores < 23 or > 76

    def score(
        self,
        responses: dict[str, int | float],
        timestamps: Optional[list[float]] = None,
        carried_responses: Optional[dict[str, int | float]] = None,
    ) -> ScoreResult:
        all_responses = dict(responses)
        if carried_responses:
            all_responses.update(carried_responses)

        total_score = 0
        for item in self.items:
            if item.get("exclude_from_score", False):
                continue
                
            item_id = item["item_id"]
            if item_id in all_responses:
                total_score += int(all_responses[item_id])

        band = self._assign_band(float(total_score), self._bands)
        
        band_description = None
        band_desc_map = self._def.get("band_descriptions", {})
        if band and band in band_desc_map:
            band_description = band_desc_map[band]

        light_therapy_time = self._get_light_therapy_time(int(total_score))

        validity_warnings = []
        if self._detect_longstring(all_responses, self._item_order):
            validity_warnings.append("longstring: 8+ identical consecutive responses detected")
        if self._detect_rapid_response(timestamps):
            validity_warnings.append("rapid_response: median inter-item time below 1.0s threshold")

        return ScoreResult(
            instrument_id=self.instrument_id,
            total_score=float(total_score),
            band=band,
            band_description=band_description,
            subscale_scores=None,
            safety_flags=[],
            validity_warnings=validity_warnings,
            metadata={
                "light_therapy_start_time": light_therapy_time
            }
        )

def create_scorer(definition: Dict[str, Any]) -> MEQScorer:
    return MEQScorer(definition)
