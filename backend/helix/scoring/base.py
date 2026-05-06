"""BaseScorer abstract class and ScoreResult dataclass."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ScoreResult:
    """Output of any scorer."""

    instrument_id: str
    total_score: float
    band: Optional[str]
    band_description: Optional[str] = None
    subscale_scores: Optional[dict[str, float]] = None
    subscale_band_descriptions: Optional[dict[str, str]] = None
    safety_flags: list[dict] = field(default_factory=list)  # [{"item_id": str, "value": int, "action": str}]
    validity_warnings: list[str] = field(default_factory=list)  # longstring, rapid-response
    metadata: dict = field(default_factory=dict)  # version, method, n_items_scored


class BaseScorer(ABC):
    """Abstract base for all instrument scorers."""

    LONGSTRING_THRESHOLD = 8  # consecutive identical responses
    RAPID_RESPONSE_THRESHOLD_SECONDS = 1.0  # per-item median floor

    @abstractmethod
    def score(
        self,
        responses: dict[str, int | float],
        timestamps: Optional[list[float]] = None,
        carried_responses: Optional[dict[str, int | float]] = None,
    ) -> ScoreResult:
        """Score a complete response set.

        Args:
            responses: {item_id: value} for all items answered by the user.
            timestamps: Optional list of Unix timestamps (one per item, in item order)
                for rapid-response detection.
            carried_responses: Optional {item_id: value} for items already keyed to
                the child instrument (i.e. translated by the caller from the parent
                assessment). Will be merged into responses before scoring.
        """

    # ------------------------------------------------------------------
    # Validity helpers (used by GenericScorer and custom scorers alike)
    # ------------------------------------------------------------------

    def _detect_longstring(
        self,
        responses: dict[str, int | float],
        item_order: list[str],
    ) -> bool:
        """Return True if 8+ identical consecutive values appear in item order."""
        values = [responses[iid] for iid in item_order if iid in responses]
        if len(values) < self.LONGSTRING_THRESHOLD:
            return False
        run = 1
        for i in range(1, len(values)):
            if values[i] == values[i - 1]:
                run += 1
                if run >= self.LONGSTRING_THRESHOLD:
                    return True
            else:
                run = 1
        return False

    def _detect_rapid_response(
        self,
        timestamps: Optional[list[float]],
        threshold_seconds: Optional[float] = None,
    ) -> bool:
        """Return True if median inter-item time is below threshold.

        Only flags when at least 2 timestamps are present.
        """
        if not timestamps or len(timestamps) < 2:
            return False
        if threshold_seconds is None:
            threshold_seconds = self.RAPID_RESPONSE_THRESHOLD_SECONDS
        gaps = [timestamps[i] - timestamps[i - 1] for i in range(1, len(timestamps))]
        sorted_gaps = sorted(gaps)
        mid = len(sorted_gaps) // 2
        if len(sorted_gaps) % 2 == 1:
            median = sorted_gaps[mid]
        else:
            median = (sorted_gaps[mid - 1] + sorted_gaps[mid]) / 2.0
        return median < threshold_seconds

    def _assign_band(
        self,
        total_score: float,
        bands: Optional[list[dict]],
    ) -> Optional[str]:
        """Return the label of the first band whose [min, max] contains total_score."""
        if not bands:
            return None
        for band in bands:
            if band["min"] <= total_score <= band["max"]:
                return band["label"]
        return None

    def _evaluate_safety_flags(
        self,
        responses: dict[str, int | float],
        items: list[dict],
        total_score: Optional[float] = None,
    ) -> list[dict]:
        """Evaluate item-level safety triggers.

        Supported condition syntax (deliberately restrictive — no eval()):
            value > N
            value >= N
            value == N
            value < N
            value <= N

        The condition is evaluated against the item's response value.
        score-level conditions (score >= N) are NOT evaluated here — those
        belong in the routing engine.
        """
        flags = []
        for item in items:
            if not item.get("safety_flag"):
                continue
            trigger = item.get("safety_trigger")
            if not trigger:
                continue
            item_id = item["item_id"]
            if item_id not in responses:
                continue
            value = responses[item_id]
            condition = trigger.get("condition", "")
            if _evaluate_item_condition(condition, value):
                flags.append(
                    {
                        "item_id": item_id,
                        "value": value,
                        "action": trigger.get("action", "SAFETY_PROTOCOL"),
                    }
                )
        return flags


# ------------------------------------------------------------------
# Condition parser — deliberately restrictive, no eval()
# ------------------------------------------------------------------

_OPERATORS = {
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    "<": lambda a, b: a < b,
    "==": lambda a, b: a == b,
}


def _evaluate_item_condition(condition: str, value: float) -> bool:
    """Parse and evaluate a simple item-level condition string.

    Supports: "value > N", "value >= N", "value == N", etc.
    The left-hand side must be literally "value".
    Returns False for any unrecognised or malformed condition.
    """
    condition = condition.strip()
    for op_str, op_fn in _OPERATORS.items():
        if condition.startswith(f"value {op_str} "):
            rhs_str = condition[len(f"value {op_str} "):].strip()
            try:
                rhs = float(rhs_str)
            except ValueError:
                return False
            return op_fn(value, rhs)
        # Also accept "value{op}N" without spaces
        if condition.startswith(f"value{op_str}"):
            rhs_str = condition[len(f"value{op_str}"):].strip()
            try:
                rhs = float(rhs_str)
            except ValueError:
                return False
            return op_fn(value, rhs)
    return False
