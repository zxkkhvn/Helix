"""PBAT custom scorer — Process-Based Assessment Tool.

Formative scale (18 items, VAS 0-100).
Produces an item-level profile rather than a single validated total score.
Negative valence items are reversed (100 - value) so that higher is always better.
"""

from __future__ import annotations

from typing import Optional

from helix.scoring.base import BaseScorer, ScoreResult


class PBATScorer(BaseScorer):
    """Custom scorer for the Process-Based Assessment Tool."""

    def __init__(self, definition: dict) -> None:
        self._def = definition
        self._instrument_id: str = definition["instrument_id"]
        self._items: list[dict] = definition["items"]
        self._item_order: list[str] = [item["item_id"] for item in self._items]
        self._negative_items = {
            item["item_id"] for item in self._items if item.get("valence") == "negative"
        }

    def score(
        self,
        responses: dict[str, int | float],
        timestamps: Optional[list[float]] = None,
        carried_responses: Optional[dict[str, int | float]] = None,
    ) -> ScoreResult:
        all_responses: dict[str, int | float] = dict(responses)
        if carried_responses:
            all_responses.update(carried_responses)

        scored_profile: dict[str, float] = {}
        areas_to_strengthen: list[str] = []

        for item_id in self._item_order:
            if item_id in all_responses:
                val = float(all_responses[item_id])
                if item_id in self._negative_items:
                    val = 100.0 - val
                scored_profile[item_id] = val

                if val < 30.0:
                    areas_to_strengthen.append(item_id)

        # The positive-process aggregate (mean of all items after reversing negatives)
        total_score = 0.0
        if scored_profile:
            total_score = sum(scored_profile.values()) / len(scored_profile)

        # Validity warnings
        validity_warnings: list[str] = []
        if self._detect_longstring(all_responses, self._item_order):
            validity_warnings.append(
                f"longstring: {self.LONGSTRING_THRESHOLD}+ identical "
                f"consecutive responses detected"
            )
        if self._detect_rapid_response(timestamps):
            validity_warnings.append(
                f"rapid_response: median inter-item time below "
                f"{self.RAPID_RESPONSE_THRESHOLD_SECONDS}s threshold"
            )

        n_scored = len(scored_profile)
        
        return ScoreResult(
            instrument_id=self._instrument_id,
            total_score=total_score,
            band=None,
            subscale_scores=scored_profile,  # Item-level profile
            safety_flags=[],
            validity_warnings=validity_warnings,
            metadata={
                "version": self._def.get("version"),
                "method": "custom",
                "n_items_scored": n_scored,
                "n_items_expected": len(self._item_order),
                "areas_to_strengthen": areas_to_strengthen,
            },
        )


def create_scorer(definition: dict) -> PBATScorer:
    """Factory function called by the registry."""
    return PBATScorer(definition)
