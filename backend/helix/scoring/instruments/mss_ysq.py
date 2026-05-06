from __future__ import annotations
from typing import Dict, Any, Optional

from helix.scoring.base import BaseScorer, ScoreResult


class MSSYSQScorer(BaseScorer):
    """
    Custom scorer for the Maladaptive Schema Scale - Young Schema Questionnaire (MSS-YSQ).
    Calculates 19 schema means, 5 unmet needs cluster means, and flags elevated schemas.
    """

    SCHEMAS = {
        "abandonment": range(1, 5),
        "emotional_deprivation": range(5, 9),
        "mistrust": range(9, 13),
        "social_isolation": range(13, 17),
        "defectiveness": range(17, 21),
        "vulnerability": range(21, 25),
        "dependence": range(25, 29),
        "low_self_efficacy": range(29, 33),
        "failure": range(33, 37),
        "enmeshment": range(37, 41),
        "subjugation": range(41, 45),
        "self_sacrifice": range(45, 49),
        "approval_seeking": range(49, 53),
        "emotional_inhibition": range(53, 57),
        "pessimism": range(57, 61),
        "unrelenting_standards": range(61, 65),
        "punitiveness_self": range(65, 69),
        "punitiveness_others": range(69, 73),
        "entitlement": range(73, 77)
    }

    CLUSTERS = {
        "disconnection_rejection": ["emotional_deprivation", "abandonment", "mistrust", "social_isolation", "defectiveness"],
        "impaired_autonomy": ["failure", "dependence", "low_self_efficacy", "vulnerability", "enmeshment"],
        "impaired_limits": ["entitlement"],
        "other_directedness": ["subjugation", "self_sacrifice", "approval_seeking"],
        "overvigilance_inhibition": ["pessimism", "emotional_inhibition", "unrelenting_standards", "punitiveness_self", "punitiveness_others"]
    }

    ELEVATED_THRESHOLD = 2.5

    def __init__(self, definition: Dict[str, Any]) -> None:
        self._def = definition
        self.instrument_id = definition["instrument_id"]
        self.items = definition["items"]
        self.scoring = definition["scoring"]
        self._bands = self.scoring.get("bands", [])

    def score(
        self,
        responses: dict[str, int | float | str],
        timestamps: Optional[list[float]] = None,
        carried_responses: Optional[dict[str, int | float | str]] = None,
    ) -> ScoreResult:
        all_responses = dict(responses)
        if carried_responses:
            all_responses.update(carried_responses)

        schema_scores = {}
        elevated_schemas = []

        # 1. Calculate Schema Means
        for schema_name, item_range in self.SCHEMAS.items():
            vals = []
            for i in item_range:
                item_id = f"mss_ysq_{i:02d}"
                if item_id in all_responses:
                    try:
                        vals.append(float(all_responses[item_id]))
                    except (ValueError, TypeError):
                        pass
            
            if vals:
                mean_val = sum(vals) / len(vals)
                schema_scores[schema_name] = mean_val
                if mean_val >= self.ELEVATED_THRESHOLD:
                    elevated_schemas.append(schema_name)

        # 2. Calculate Cluster Means
        cluster_scores = {}
        for cluster_name, schemas in self.CLUSTERS.items():
            c_vals = []
            for s in schemas:
                if s in schema_scores:
                    c_vals.append(schema_scores[s])
            
            if c_vals:
                cluster_scores[cluster_name] = sum(c_vals) / len(c_vals)

        # 3. Total Score
        all_schema_means = list(schema_scores.values())
        total_score = sum(all_schema_means) / len(all_schema_means) if all_schema_means else 0.0

        assigned_band = None
        for band in self._bands:
            b_min = band.get("min", float("-inf"))
            b_max = band.get("max", float("inf"))
            if b_min <= total_score <= b_max:
                assigned_band = band["label"]
                break

        return ScoreResult(
            instrument_id=self.instrument_id,
            total_score=total_score,
            subscale_scores=schema_scores,
            band=assigned_band,
            safety_flags=[],
            validity_warnings=[],
            metadata={
                "clusters": cluster_scores,
                "elevated_schemas": elevated_schemas
            },
        )

def create_scorer(definition: Dict[str, Any]) -> BaseScorer:
    return MSSYSQScorer(definition)
