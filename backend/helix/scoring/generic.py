"""GenericScorer — handles any instrument with scoring.method sum or mean."""

from __future__ import annotations

from typing import Optional

from helix.scoring.base import BaseScorer, ScoreResult


class GenericScorer(BaseScorer):
    """Scores any instrument whose JSON definition uses sum or mean.

    The scorer is stateless once constructed. One instance per instrument
    definition; safe to reuse across requests.
    """

    def __init__(self, definition: dict) -> None:
        self._def = definition
        self._instrument_id: str = definition["instrument_id"]
        self._items: list[dict] = definition["items"]
        self._scoring: dict = definition["scoring"]
        self._method: str = self._scoring["method"]
        self._bands: Optional[list[dict]] = self._scoring.get("bands")
        # Ordered list of all item IDs (for longstring detection)
        self._item_order: list[str] = [item["item_id"] for item in self._items]
        # carry_forward_items: {parent_item_id: child_item_id}
        self._carry_map: dict[str, str] = (
            definition["routing"].get("carry_forward_items") or {}
        )
        self._subscales: Optional[dict[str, dict]] = self._scoring.get("subscales")

        # Pre-calculate min/max for reverse scoring
        # Supports both per-item "reverse_scored": true AND scoring-level
        # "reverse_items": ["item_id1", ...] list
        self._response_sets = definition.get("response_option_sets", {})
        reverse_items_list = set(self._scoring.get("reverse_items", []))
        self._item_reverse_info: dict[str, tuple[int | float, int | float]] = {}
        for item in self._items:
            is_reversed = item.get("reverse_scored", False) or item["item_id"] in reverse_items_list
            if is_reversed:
                opt_key = item.get("response_options_key")
                if opt_key and opt_key in self._response_sets:
                    options = self._response_sets[opt_key]
                    min_val = min(o["value"] for o in options)
                    max_val = max(o["value"] for o in options)
                    self._item_reverse_info[item["item_id"]] = (min_val, max_val)

        if self._method not in ("sum", "mean"):
            raise ValueError(
                f"{self._instrument_id}: GenericScorer only handles sum/mean, "
                f"got '{self._method}'. Use a custom scorer."
            )

    def score(
        self,
        responses: dict[str, int | float],
        timestamps: Optional[list[float]] = None,
        carried_responses: Optional[dict[str, int | float]] = None,
    ) -> ScoreResult:
        """Score a response set.

        Args:
            responses: {child_item_id: value} submitted by the user for this
                instrument. Should NOT include carried item IDs — they are
                provided separately via carried_responses.
            timestamps: Optional per-item Unix timestamps in item-presentation
                order (not necessarily item_id order). Used only for
                rapid-response detection.
            carried_responses: Optional {child_item_id: value} for items whose
                values came from a parent instrument (already translated to child
                item IDs by the caller). Merged into responses before scoring.
        """
        # 1. Merge carried responses into the working response set
        all_responses: dict[str, int | float] = dict(responses)
        if carried_responses:
            all_responses.update(carried_responses)

        # 2. Determine scoreable items
        scoreable = [
            item for item in self._items
            if not item.get("exclude_from_score", False)
        ]
        scoreable_ids = [item["item_id"] for item in scoreable]

        # 3. Collect values for scoreable items, applying reverse scoring
        values = []
        scored_responses = {}
        for iid in scoreable_ids:
            if iid in all_responses:
                val = all_responses[iid]
                if iid in self._item_reverse_info:
                    min_v, max_v = self._item_reverse_info[iid]
                    val = (min_v + max_v) - val
                values.append(val)
                scored_responses[iid] = val

        # 4. Compute total
        if not values:
            total: float = 0.0
        elif self._method == "sum":
            total = float(sum(values))
        else:  # mean
            total = sum(values) / len(values)

        # 5. Compute subscales
        subscale_scores = None
        if self._subscales and scored_responses:
            subscale_scores = {}
            for sub_id, sub_def in self._subscales.items():
                sub_method = sub_def.get("method", self._method)
                sub_items = [iid for iid in sub_def["items"] if iid in scored_responses]
                
                if not sub_items:
                    continue
                    
                sub_vals = [scored_responses[iid] for iid in sub_items]
                if sub_method == "sum":
                    subscale_scores[sub_id] = float(sum(sub_vals))
                else:  # mean
                    subscale_scores[sub_id] = sum(sub_vals) / len(sub_vals)

        # 6. Band assignment
        band = self._assign_band(total, self._bands)

        band_description = None
        subscale_band_descriptions = None
        band_desc_map = self._def.get("band_descriptions", {})

        if band and band in band_desc_map:
            band_description = band_desc_map[band]

        if subscale_scores and band_desc_map:
            subscale_band_descriptions = {}
            for sub_id, score in subscale_scores.items():
                if sub_id in self._subscales and sub_id in band_desc_map:
                    sub_def = self._subscales[sub_id]
                    # Only assign description if the subscale actually defines numeric bands
                    if sub_def.get("bands"):
                        sub_band = self._assign_band(score, sub_def["bands"])
                        if sub_band and sub_band in band_desc_map[sub_id]:
                            subscale_band_descriptions[sub_id] = band_desc_map[sub_id][sub_band]

        # 6. Safety flags
        safety_flags = self._evaluate_safety_flags(all_responses, self._items)

        # 7. Validity warnings
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

        return ScoreResult(
            instrument_id=self._instrument_id,
            total_score=total,
            band=band,
            band_description=band_description,
            subscale_scores=subscale_scores,
            subscale_band_descriptions=subscale_band_descriptions,
            safety_flags=safety_flags,
            validity_warnings=validity_warnings,
            metadata={
                "version": self._def.get("version"),
                "method": self._method,
                "n_items_scored": len(values),
                "n_items_expected": len(scoreable_ids),
            },
        )
