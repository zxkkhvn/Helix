import json
from typing import Any, Dict, List, Optional
from helix.models.models import Session, AssessmentInstance, Score
from helix.scoring.planet_state import compute_planet_states
from helix.scoring.composite import compute_all_composites
from helix.scoring.base import ScoreResult

THEME_THRESHOLD_PARTIAL = 2
THEME_THRESHOLD_RICH = 4

THEME_INSTRUMENT_MAPPING = {
    "current_distress": [
        "phq2", "phq9", "gad2", "gad7", "paq_s", "paq", "dts", "erq", 
        "ders16", "pss10", "wsas", "isi", "wemwbs"
    ],
    "maintaining_processes": [
        "ius12", "mss_ysq", "ptq10", "cpq", "des_b", "pswq", "oci_r", 
        "maia2_brief", "ffmq15", "psqi", "meq"
    ],
    "relational_cognitive_patterns": [
        "lsas_sr_short", "lsas_sr_full", "ecr_s", "ecr_rs", "dejong", 
        "ipip50", "scs_sf", "bfi_s"
    ],
    "values_and_friction": [
        "vlq", "aaq2", "compact", "mlq", "swls", "via_is_p"
    ],
    "protective_resources": [
        "brs", "rses", "aces", "wemwbs", "ffmq15", "scs_sf"
    ]
}

class ContextSerializer:
    """Serializes a SQLAlchemy Session into a PRE_SCORED_JSON_PAYLOAD for AI formulation."""

    @staticmethod
    def _compute_theme_states(scores: List[Score]) -> Dict[str, str]:
        theme_states = {}
        # Get unique instrument IDs present in the session scores
        present_instruments = {score.instrument_id for score in scores}

        for theme, mapped_instruments in THEME_INSTRUMENT_MAPPING.items():
            # Count how many mapped instruments are present in the completed scores
            count = sum(1 for inst in mapped_instruments if inst in present_instruments)
            
            if count >= THEME_THRESHOLD_RICH:
                theme_states[theme] = "RICH"
            elif count >= THEME_THRESHOLD_PARTIAL:
                theme_states[theme] = "PARTIAL"
            else:
                theme_states[theme] = "SPARSE"
                
        return theme_states

    @staticmethod
    def build_payload(session: Session) -> dict:
        """Constructs the JSON payload from the database session and its scores."""
        intake_data = session.intake_data or {}
        
        # Extract base scores as dictionaries
        scores = []
        for instance in session.assessment_instances:
            if instance.score:
                scores.append(instance.score)
                
        base_scores = [
            {
                "instrument_id": s.instrument_id,
                "total": s.total_score,
                "band": s.band,
                "subscale_scores": s.subscale_scores,
                "validity_warnings": s.validity_warnings
            }
            for s in scores
        ]
        
        # Determine safety markers
        safety_markers = {
            "self_harm": False,
            "acute_trauma": False,
            "severe_distress": False
        }
        
        has_any_safety_flag = False
        if session.safety_flags:
            has_any_safety_flag = True
            for flag in session.safety_flags:
                item_id = flag.get("item_id", "")
                if "phq9_09" in item_id:
                    safety_markers["self_harm"] = True
                elif "pcptsd5" in flag.get("instrument_id", ""):
                    safety_markers["acute_trauma"] = True
        
        # We need ScoreResult objects for compute_all_composites and planet states
        score_results = [
            ScoreResult(
                instrument_id=s.instrument_id,
                total_score=s.total_score,
                band=s.band,
                subscale_scores=s.subscale_scores,
                safety_flags=s.safety_flags,
                validity_warnings=s.validity_warnings,
                metadata=s.score_metadata
            )
            for s in scores
        ]

        composite_indices = compute_all_composites(score_results)
        theme_states = ContextSerializer._compute_theme_states(scores)
        planet_states = compute_planet_states(session, scores)

        # Retrieve PBAT profile if available
        pbat_profile = None
        for s in scores:
            if s.instrument_id == "pbat":
                pbat_profile = {
                    "subscale_scores": s.subscale_scores,
                    "metadata": s.score_metadata
                }
                break

        return {
            "session_id": str(session.id),
            "red_thread_question": intake_data.get("red_thread_question", ""),
            "red_thread_quality": intake_data.get("red_thread_quality", "empty"),
            "red_thread_categories": intake_data.get("red_thread_categories", []),
            "red_thread_risk_flag": intake_data.get("red_thread_risk_flag", False),
            "cultural_background": intake_data.get("cultural_background", {}),
            
            "session_anchors": session.anchors or {},
            "anchor_delta": intake_data.get("anchor_delta", {}),
            "anchor_flag": intake_data.get("anchor_flag"),
            
            "pbat_profile": pbat_profile,
            "base_scores": base_scores,
            "composite_indices": composite_indices,
            "theme_states": theme_states,
            "completion_state": planet_states,
            
            "safety_markers": safety_markers,
            "safety_protocol": "If you are experiencing immediate distress or thoughts of self-harm, please reach out to emergency services or a crisis helpline immediately." if has_any_safety_flag else None
        }
