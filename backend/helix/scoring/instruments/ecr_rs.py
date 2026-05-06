from __future__ import annotations
from typing import Dict, Any, Optional

from helix.scoring.base import BaseScorer, ScoreResult


class ECRRSScorer(BaseScorer):
    """
    Custom scorer for Experiences in Close Relationships - Relationship Structures (ECR-RS).
    Handles 4 relationship targets (mother, father, partner, friend).
    Computes avoidance (items 1-6) and anxiety (items 7-9) subscales per target.
    Items 1-4 are reverse scored.
    """

    TARGETS = ["mother", "father", "partner", "friend"]

    def __init__(self, definition: Dict[str, Any]) -> None:
        self._def = definition
        self.instrument_id = definition["instrument_id"]
        self.scoring = definition["scoring"]

    def score(
        self,
        responses: dict[str, int | float | str],
        timestamps: Optional[list[float]] = None,
        carried_responses: Optional[dict[str, int | float | str]] = None,
    ) -> ScoreResult:
        all_responses = dict(responses)
        if carried_responses:
            all_responses.update(carried_responses)

        subscales = {}
        all_valid_vals = []

        for target in self.TARGETS:
            avoidance_vals = []
            anxiety_vals = []

            for i in range(1, 10):
                item_id = f"ecr_rs_{target}_{i:02d}"
                if item_id not in all_responses:
                    continue

                try:
                    val = float(all_responses[item_id])
                except (ValueError, TypeError):
                    continue

                if i <= 4:
                    # Reverse score 1-4
                    val = 8.0 - val

                if i <= 6:
                    avoidance_vals.append(val)
                else:
                    anxiety_vals.append(val)

                all_valid_vals.append(val)

            if avoidance_vals:
                subscales[f"{target}_avoidance"] = sum(avoidance_vals) / len(avoidance_vals)
            if anxiety_vals:
                subscales[f"{target}_anxiety"] = sum(anxiety_vals) / len(anxiety_vals)

        total_score = sum(all_valid_vals) / len(all_valid_vals) if all_valid_vals else 0.0

        # No aggregate bands/descriptions for the attachment profile model.
        # total_score is returned as a mean placeholder for backend compatibility.
        subscale_band_descriptions = {}
        subscale_defs = self.scoring.get("subscales", {})
        band_desc_map = self._def.get("band_descriptions", {})

        for sub_id, score in subscales.items():
            if sub_id in subscale_defs:
                sub_bands = subscale_defs[sub_id].get("bands", [])
                for band in sub_bands:
                    if band["min"] <= score <= band["max"]:
                        label = band["label"]
                        desc = band_desc_map.get(sub_id, {}).get(label)
                        if desc:
                            subscale_band_descriptions[sub_id] = desc
                        break

        return ScoreResult(
            instrument_id=self.instrument_id,
            total_score=total_score,
            subscale_scores=subscales,
            subscale_band_descriptions=subscale_band_descriptions,
            band=None,
            band_description=None,
            safety_flags=[],
            validity_warnings=[],
            metadata={},
        )

def create_scorer(definition: Dict[str, Any]) -> BaseScorer:
    return ECRRSScorer(definition)
