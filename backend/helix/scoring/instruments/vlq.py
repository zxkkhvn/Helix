from __future__ import annotations
from typing import Dict, Any, Optional

from helix.scoring.base import BaseScorer, ScoreResult

# 10 VLQ domains in order
_DOMAINS = [
    "family", "marriage_intimate", "parenting", "friends_social",
    "work", "education", "recreation", "spirituality",
    "citizenship", "physical_self_care",
]


class VLQScorer(BaseScorer):
    """Custom scorer for the Valued Living Questionnaire (VLQ).

    Computes:
      - Per-domain importance, consistency, and gap scores
      - Composite score = mean of (importance * consistency) across all domains
      - Mean gap = mean of (importance - consistency) for domains where importance >= 7
      - total_score = mean_gap (used by valued_living_gap composite)
    """

    def __init__(self, definition: Dict[str, Any]) -> None:
        self._def = definition
        self.instrument_id = definition["instrument_id"]
        self.items = definition["items"]
        self.scoring = definition["scoring"]
        self._item_order = [item["item_id"] for item in self.items]
        self._bands = self.scoring.get("bands")

    def score(
        self,
        responses: dict[str, int | float],
        timestamps: Optional[list[float]] = None,
        carried_responses: Optional[dict[str, int | float]] = None,
    ) -> ScoreResult:
        all_responses = dict(responses)
        if carried_responses:
            all_responses.update(carried_responses)

        domain_profiles = []
        composites = []
        gaps_for_important = []

        for i, domain_name in enumerate(_DOMAINS, start=1):
            imp_key = f"vlq_{i:02d}_imp"
            con_key = f"vlq_{i:02d}_con"

            imp = int(all_responses.get(imp_key, 1))
            con = int(all_responses.get(con_key, 1))
            gap = imp - con

            domain_profiles.append({
                "domain": domain_name,
                "importance": imp,
                "consistency": con,
                "gap": gap,
            })

            composites.append(imp * con)

            if imp >= 7:
                gaps_for_important.append(gap)

        composite_score = sum(composites) / len(composites) if composites else 0.0
        mean_gap = (
            sum(gaps_for_important) / len(gaps_for_important)
            if gaps_for_important
            else 0.0
        )

        validity_warnings = []
        if self._detect_longstring(all_responses, self._item_order):
            validity_warnings.append(
                "longstring: 8+ identical consecutive responses detected"
            )
        if self._detect_rapid_response(timestamps):
            validity_warnings.append(
                "rapid_response: median inter-item time below 1.0s threshold"
            )

        return ScoreResult(
            instrument_id=self.instrument_id,
            total_score=round(mean_gap, 2),
            band=None,
            subscale_scores=None,
            safety_flags=[],
            validity_warnings=validity_warnings,
            metadata={
                "composite_score": round(composite_score, 2),
                "mean_gap": round(mean_gap, 2),
                "domains_counted_for_gap": len(gaps_for_important),
                "domain_profiles": domain_profiles,
            },
        )


def create_scorer(definition: Dict[str, Any]) -> VLQScorer:
    return VLQScorer(definition)
