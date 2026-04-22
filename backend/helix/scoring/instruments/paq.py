"""PAQ custom scorer — Perth Alexithymia Questionnaire.

5 subscales with valence-specific grouping:
    N_DIF  Negative Difficulty Identifying Feelings  (items 01-04, negative valence)
    P_DIF  Positive DIF                              (items 05-08, positive valence)
    N_DDF  Negative Difficulty Describing Feelings   (items 09-12, negative valence)
    P_DDF  Positive DDF                              (items 13-16, positive valence)
    G_EOT  General Externally-Oriented Thinking      (items 17-24, general valence)

Total score = sum of all 24 items (= sum of all subscales).
All items are positively keyed — no reverse scoring.
Carry-forward from PAQ-S maps non-sequentially (see LEARNINGS.md + JSON def).
"""

from __future__ import annotations

from typing import Optional

from helix.scoring.base import BaseScorer, ScoreResult


class PAQScorer(BaseScorer):
    """Custom scorer for the Perth Alexithymia Questionnaire."""

    def __init__(self, definition: dict) -> None:
        self._def = definition
        self._instrument_id: str = definition["instrument_id"]
        self._items: list[dict] = definition["items"]
        self._scoring: dict = definition["scoring"]
        self._bands: Optional[list[dict]] = self._scoring.get("bands")
        self._subscale_defs: dict[str, dict] = self._scoring.get("subscales") or {}
        self._item_order: list[str] = [item["item_id"] for item in self._items]

    def score(
        self,
        responses: dict[str, int | float],
        timestamps: Optional[list[float]] = None,
        carried_responses: Optional[dict[str, int | float]] = None,
    ) -> ScoreResult:
        # 1. Merge carried responses
        all_responses: dict[str, int | float] = dict(responses)
        if carried_responses:
            all_responses.update(carried_responses)

        # 2. Compute subscale scores
        subscale_scores: dict[str, float] = {}
        for scale_name, scale_def in self._subscale_defs.items():
            scale_method: str = scale_def.get("method", "sum")
            scale_item_ids: list[str] = scale_def["items"]
            scale_values = [
                all_responses[iid]
                for iid in scale_item_ids
                if iid in all_responses
            ]
            if not scale_values:
                subscale_scores[scale_name] = 0.0
            elif scale_method == "sum":
                subscale_scores[scale_name] = float(sum(scale_values))
            else:  # mean
                subscale_scores[scale_name] = sum(scale_values) / len(scale_values)

        # 3. Total = sum of all subscale sums (equivalent to summing all items)
        total = float(sum(subscale_scores.values()))

        # 4. Band
        band = self._assign_band(total, self._bands)

        # 5. Safety flags (PAQ has none, but evaluated for completeness)
        safety_flags = self._evaluate_safety_flags(all_responses, self._items)

        # 6. Validity warnings
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

        # Count how many items were actually scored
        all_item_ids = [item["item_id"] for item in self._items]
        n_scored = sum(1 for iid in all_item_ids if iid in all_responses)

        return ScoreResult(
            instrument_id=self._instrument_id,
            total_score=total,
            band=band,
            subscale_scores=subscale_scores,
            safety_flags=safety_flags,
            validity_warnings=validity_warnings,
            metadata={
                "version": self._def.get("version"),
                "method": "custom",
                "n_items_scored": n_scored,
                "n_items_expected": len(all_item_ids),
            },
        )


def create_scorer(definition: dict) -> PAQScorer:
    """Factory function called by the registry."""
    return PAQScorer(definition)
