"""Planet state calculator — determines planet opacity and depth tiers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class PlanetState:
    planet_id: str
    display_name: str
    status: str
    completion_pct: float
    quick_scan_done: bool
    deep_dive_instruments_total: int
    deep_dive_instruments_done: int
    available_instruments: list[str]
    completed_instruments: list[str]


PLANET_INSTRUMENTS = {
    "mercury": {
        "display_name": "Mercury — Sleep, Function & Body",
        "quick_scan": ["isi"],
        "deep_dive": ["wemwbs", "maia2_brief", "meq", "psqi", "ffmq15"],
    },
    "venus": {
        "display_name": "Venus — Mood, Emotion & Awareness",
        "quick_scan": ["phq2", "gad2", "paq_s"],
        "deep_dive": ["phq9", "gad7", "paq", "ders16", "pss10", "dts", "erq"],
    },
    "earth": {
        "display_name": "Earth — Core Self",
        "quick_scan": ["bfi_s", "via_is_p"],
        "deep_dive": ["ipip50", "scs_sf", "brs", "rses", "aces"],
    },
    "mars": {
        "display_name": "Mars — Attention & Drive",
        "quick_scan": ["asrs_a"],
        "deep_dive": ["asrs_full", "bdefs_sf", "cfq25"],
    },
    "jupiter": {
        "display_name": "Jupiter — Values, Motivation & Meaning",
        "quick_scan": ["vlq"],
        "deep_dive": ["aaq2", "compact", "mlq", "swls"],
    },
    "saturn": {
        "display_name": "Saturn — Social & Relational",
        "quick_scan": ["lsas_sr_short"],
        "deep_dive": ["lsas_sr_full", "ecr_s", "ecr_rs", "dejong"],
    },
    "neptune": {
        "display_name": "Neptune — Deep Patterns",
        "quick_scan": ["ius12"],
        "deep_dive": ["mss_ysq", "ptq10", "cpq", "des_b", "pswq", "oci_r"],
    },
    "uranus": {
        "display_name": "Uranus — Neurodivergence",
        "quick_scan": ["aq10"],
        "deep_dive": ["catq", "raads_r"],
        "conditional": True,
    },
}

def compute_planet_states(session: Any, completed_scores: list) -> list[dict]:
    """Compute current exploration state for all planets."""
    completed_ids = {s.instrument_id for s in completed_scores}
    
    # We need compute_available_instruments here to check what's actually available.
    # To avoid circular imports, import inside the function.
    from helix.routing.engine import compute_available_instruments
    
    available_ids = set(compute_available_instruments(session, completed_scores))
    
    states = []
    for planet_id, config in PLANET_INSTRUMENTS.items():
        quick_scan_ids = config.get("quick_scan", [])
        deep_dive_ids = config.get("deep_dive", [])
        
        all_instruments = quick_scan_ids + deep_dive_ids
        planet_completed = [inst for inst in all_instruments if inst in completed_ids]
        planet_available = [inst for inst in all_instruments if inst in available_ids]
        
        quick_scan_done = all(inst in completed_ids for inst in quick_scan_ids)
        deep_dive_done = [inst for inst in deep_dive_ids if inst in completed_ids]
        
        status = "AVAILABLE"
        
        if config.get("conditional", False):
            # If conditional, it's LOCKED unless at least one instrument is available or completed
            if not planet_available and not planet_completed:
                status = "LOCKED"
                
        if status != "LOCKED":
            if len(planet_completed) == len(all_instruments) and len(all_instruments) > 0:
                status = "DEEP_DIVE_COMPLETE"
            elif quick_scan_done:
                # If there are available deep dive instruments, it's DEEP_DIVE_AVAILABLE
                # Otherwise, if we're just waiting for routing to unlock something (or all are done),
                # it's SCANNED. But if deep dive is available it's also SCANNED basically.
                # The user says: "DEEP_DIVE_AVAILABLE: same as SCANNED (user can go deeper)".
                # Let's say DEEP_DIVE_AVAILABLE if any deep dive instrument is in available_ids, 
                # otherwise SCANNED.
                if any(inst in available_ids for inst in deep_dive_ids):
                    status = "DEEP_DIVE_AVAILABLE"
                else:
                    status = "SCANNED"

        completion_pct = 0.0
        if len(all_instruments) > 0:
            completion_pct = len(planet_completed) / len(all_instruments)
            
        state = PlanetState(
            planet_id=planet_id,
            display_name=config["display_name"],
            status=status,
            completion_pct=completion_pct,
            quick_scan_done=quick_scan_done,
            deep_dive_instruments_total=len(deep_dive_ids),
            deep_dive_instruments_done=len(deep_dive_done),
            available_instruments=planet_available,
            completed_instruments=planet_completed,
        )
        # Convert to dict for JSON serialization
        states.append({
            "planet_id": state.planet_id,
            "display_name": state.display_name,
            "status": state.status,
            "completion_pct": state.completion_pct,
            "quick_scan_done": state.quick_scan_done,
            "deep_dive_instruments_total": state.deep_dive_instruments_total,
            "deep_dive_instruments_done": state.deep_dive_instruments_done,
            "available_instruments": state.available_instruments,
            "completed_instruments": state.completed_instruments,
        })
        
    return states
