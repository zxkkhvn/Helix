"""Routing engine — evaluates on_completion rules after scoring.

Deliberately restrictive condition parser (no eval).
Supported condition patterns:
    score >= N    score > N    score == N    score < N    score <= N
    item.{item_id} > N    item.{item_id} >= N    etc.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from helix.scoring.base import ScoreResult

_OPERATORS = {
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    "<": lambda a, b: a < b,
    "==": lambda a, b: a == b,
}


@dataclass
class RoutingAction:
    """Output of the routing engine."""

    # One of: next_instrument | safety_pause | flag_elevated | none
    action: str
    next_instrument_id: Optional[str] = None
    # {child_item_id: value} — carry-forward values already translated to child IDs
    carry_forward_items: Optional[dict] = None
    safety_triggered: bool = False
    flags: list[str] = field(default_factory=list)
    # Planets to unlock (e.g. ASRS Part A >= 12 → unlock uranus)
    unlock_planets: list[str] = field(default_factory=list)


def _parse_condition(condition: str, total_score: float, responses: dict) -> bool:
    """Evaluate a single on_completion condition string.

    Returns False for any unrecognised pattern.
    """
    condition = condition.strip()
    for op_str, op_fn in _OPERATORS.items():
        # score-level: "score >= N"
        if condition.startswith(f"score {op_str} ") or condition.startswith(f"score{op_str}"):
            rhs_raw = condition.split(op_str, 1)[1].strip()
            try:
                return op_fn(total_score, float(rhs_raw))
            except ValueError:
                return False

        # item-level: "item.phq9_09 > N"
        if condition.startswith(f"item.") and f" {op_str} " in condition:
            parts = condition.split(f" {op_str} ", 1)
            item_id = parts[0].strip().removeprefix("item.")
            try:
                rhs = float(parts[1].strip())
            except ValueError:
                return False
            if item_id not in responses:
                return False
            return op_fn(responses[item_id], rhs)

    return False


def _build_carry_forward(definition: dict, parent_responses: dict) -> Optional[dict]:
    """Translate parent responses to child item IDs using carry_forward_items map.

    Returns {child_item_id: value} or None if no carry_forward_items defined.
    """
    cf_map = definition["routing"].get("carry_forward_items")
    if not cf_map:
        return None
    return {
        child_id: parent_responses[parent_id]
        for parent_id, child_id in cf_map.items()
        if parent_id in parent_responses
    }


def evaluate_routing(
    definition: dict,
    score_result: ScoreResult,
    all_responses: dict,
) -> RoutingAction:
    """Evaluate on_completion rules and return the routing action.

    Args:
        definition: Parsed instrument JSON definition (the instrument just scored).
        score_result: Output from the scorer.
        all_responses: Complete response set (client responses + carried responses merged).

    Returns:
        RoutingAction describing what should happen next.
    """
    on_completion = definition["routing"].get("on_completion") or []

    safety_triggered = False
    next_instrument_id = None
    carry_forward_items = None
    flags: list[str] = []
    unlock_planets: list[str] = []

    for rule in on_completion:
        condition = rule.get("condition", "")
        action = rule.get("action", "")

        if not _parse_condition(condition, score_result.total_score, all_responses):
            continue

        if action == "SAFETY_PROTOCOL":
            safety_triggered = True

        elif action == "trigger_expansion":
            next_instrument_id = rule.get("target")

        elif action == "unlock_planet":
            target = rule.get("target")
            if target:
                unlock_planets.append(target)

        elif action in ("flag_elevated", "flag_alexithymia_calibration"):
            flags.append(action)

    # Also treat any scorer-level safety flags as safety_triggered
    if score_result.safety_flags:
        safety_triggered = True

    if safety_triggered:
        determined_action = "safety_pause"
    elif next_instrument_id:
        determined_action = "next_instrument"
    elif flags:
        determined_action = "flag_elevated"
    else:
        determined_action = "none"

    return RoutingAction(
        action=determined_action,
        next_instrument_id=next_instrument_id,
        carry_forward_items=carry_forward_items,  # populated by caller from registry def
        safety_triggered=safety_triggered,
        flags=flags,
        unlock_planets=unlock_planets,
    )


def compute_available_instruments(session: Any, completed_scores: list) -> list[str]:
    """Compute which instruments are currently available.

    Args:
        session: Session ORM object.
        completed_scores: List of Score ORM objects for this session.

    Returns:
        List of instrument_ids available to submit next (in display order).

    Availability rules are still hardcoded, but now cover the implemented
    core-flow, Venus, Mercury, Earth, Mars, and Jupiter slices.
    """
    completed_by_id = {s.instrument_id: s for s in completed_scores}
    available = []

    # Enforce Core Flow Sequence
    if session.state == "CORE_FLOW_IN_PROGRESS":
        if not session.intake_data:
            return ["intake"]
        elif "pbat" not in completed_by_id:
            return ["pbat"]
        elif not session.anchors:
            return ["anchors"]
        elif "wsas" not in completed_by_id:
            return ["wsas"]
        elif "pcptsd5" not in completed_by_id:
            return ["pcptsd5"]
        # If all above are complete, the core flow is technically done. 
        # State transition will be handled by the route, but while the DB state 
        # still says CORE_FLOW_IN_PROGRESS during the same request, return empty.
        return []

    if session.state not in ("EXPLORING", "SAFETY_ACKNOWLEDGED"):
        return []

    # Earth instruments (always available in EXPLORING)
    earth_instruments = ["bfi_s", "ipip50", "scs_sf", "brs", "rses", "via_is_p"]
    for inst in earth_instruments:
        if inst not in completed_by_id:
            available.append(inst)

    # ACEs deferral logic
    aces_deferred = False
    if "pcptsd5" in completed_by_id and completed_by_id["pcptsd5"].total_score >= 3:
        if session.state != "SAFETY_ACKNOWLEDGED":
            aces_deferred = True
    if session.intake_data and session.intake_data.get("red_thread_risk_flag"):
        aces_deferred = True

    if not aces_deferred and "aces" not in completed_by_id:
        available.append("aces")

    # PHQ chain
    if "phq2" not in completed_by_id:
        available.append("phq2")
    elif completed_by_id["phq2"].total_score >= 3 and "phq9" not in completed_by_id:
        available.append("phq9")

    # GAD chain
    if "gad2" not in completed_by_id:
        available.append("gad2")
    elif completed_by_id["gad2"].total_score >= 3 and "gad7" not in completed_by_id:
        available.append("gad7")

    # PAQ chain
    if "paq_s" not in completed_by_id:
        available.append("paq_s")
    elif completed_by_id["paq_s"].total_score >= 30 and "paq" not in completed_by_id:
        available.append("paq")

    # Venus deep dives (always available)
    venus_deep_dives = ["ders16", "pss10", "dts", "erq"]
    for inst in venus_deep_dives:
        if inst not in completed_by_id:
            available.append(inst)

    # Mercury instruments (always available)
    mercury_instruments = ["isi", "wemwbs", "ffmq15", "maia2_brief", "meq", "psqi"]
    for inst in mercury_instruments:
        if inst not in completed_by_id:
            available.append(inst)

    # Mars — ASRS chain
    if "asrs_a" not in completed_by_id:
        available.append("asrs_a")
    elif completed_by_id["asrs_a"].total_score >= 12 and "asrs_full" not in completed_by_id:
        available.append("asrs_full")

    # Mars deep dives (always available)
    mars_deep_dives = ["bdefs_sf", "cfq25"]
    for inst in mars_deep_dives:
        if inst not in completed_by_id:
            available.append(inst)

    # Jupiter instruments (always available)
    jupiter_instruments = ["vlq", "aaq2", "compact", "mlq", "swls"]
    for inst in jupiter_instruments:
        if inst not in completed_by_id:
            available.append(inst)

    return available
