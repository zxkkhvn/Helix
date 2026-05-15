"""Session management endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, constr
from sqlalchemy.orm import Session as DBSession

from helix.db.database import get_db
from helix.models.models import AssessmentInstance, Narrative, Score, Session
from helix.routing.engine import compute_available_instruments
from helix.scoring import registry
from helix.scoring.composite import compute_all_composites
from helix.scoring.planet_state import compute_planet_states
from helix.ai.readiness import ReadinessEngine
from helix.config import settings

_readiness_engine = ReadinessEngine()

router = APIRouter(prefix="/sessions", tags=["sessions"])


# ---------------------------------------------------------------------------
# Request and Response schemas
# ---------------------------------------------------------------------------

INTAKE_CATEGORIES = [
    {"id": "mood_anxiety", "label": "Mood and anxiety", "planet": "venus"},
    {"id": "sleep_energy", "label": "Sleep and energy", "planet": "mercury"},
    {"id": "relationships", "label": "Relationships and connection", "planet": "saturn"},
    {"id": "attention_focus", "label": "Attention and focus", "planet": "mars"},
    {"id": "identity_personality", "label": "Identity and personality", "planet": "earth"},
    {"id": "values_meaning", "label": "Values and meaning", "planet": "jupiter"},
    {"id": "childhood_history", "label": "Childhood and history", "planet": "earth"},
    {"id": "neurodivergence", "label": "Neurodivergence", "planet": "uranus"},
    {"id": "trauma_experiences", "label": "Trauma and past experiences", "planet": "neptune"},
    {"id": "general", "label": "General self-understanding", "planet": None},
]
VALID_CATEGORY_IDS = {c["id"] for c in INTAKE_CATEGORIES}

class IntakeRequest(BaseModel):
    red_thread_question: constr(min_length=1)
    categories: List[str]
    top3_ranked: Optional[List[Optional[str]]] = None

class AnchorsRequest(BaseModel):
    mood: int = Field(..., ge=0, le=10)
    energy: int = Field(..., ge=0, le=10)
    focus: int = Field(..., ge=0, le=10)

class CompletedInstrument(BaseModel):
    instrument_id: str
    assessment_instance_id: str
    total_score: float
    band: Optional[str]
    band_description: Optional[str] = None


def _build_completed_instruments(scores: List[Score]) -> List[CompletedInstrument]:
    completed = []
    for s in scores:
        band = s.band
        band_desc = None
        try:
            scorer = registry.get_scorer(s.instrument_id)
        except KeyError:
            scorer = None

        if scorer is not None:
            definition = scorer._def
            if definition.get("suppress_band_from_user"):
                band = None
            elif band:
                candidate = definition.get("band_descriptions", {}).get(band)
                if isinstance(candidate, str):
                    band_desc = candidate

        completed.append(
            CompletedInstrument(
                instrument_id=s.instrument_id,
                assessment_instance_id=s.assessment_instance_id,
                total_score=s.total_score,
                band=band,
                band_description=band_desc,
            )
        )
    return completed


class SessionStateResponse(BaseModel):
    session_id: str
    state: str
    completed: List[CompletedInstrument]
    available: List[str]
    safety_flags: Optional[list]
    intake: Optional[dict[str, Any]] = None
    anchors: Optional[dict[str, Any]] = None
    composites: List[dict] = Field(default_factory=list)
    planet_states: List[dict] = Field(default_factory=list)
    narratives: List[dict[str, Any]] = Field(default_factory=list)
    fatigue_nudge: bool = False
    ai_readiness: Optional[dict] = None


class CreateSessionResponse(BaseModel):
    session_id: str
    state: str
    available: List[str]


class InstrumentFormPayload(BaseModel):
    instrument_id: str
    instrument_name: str
    instrument_version: str
    time_window_text: Optional[str]
    items_to_render: list
    response_option_sets: dict
    parent_instance_id: Optional[str]
    session_state: str
    is_submittable: bool


def _compute_fatigue_nudge(
    session: Session,
    scores: List[Score],
    *,
    db: DBSession | None = None,
    mark_shown: bool = False,
) -> bool:
    total_items_scored = sum(
        s.score_metadata.get("n_items_scored", 0) if s.score_metadata else 0
        for s in scores
    )
    fatigue_nudge = total_items_scored >= 150 and not session.fatigue_nudge_dismissed
    if fatigue_nudge and mark_shown and not session.fatigue_nudge_shown:
        session.fatigue_nudge_shown = True
        if db is not None:
            db.flush()
    return fatigue_nudge


def _build_session_state_response(
    session: Session,
    scores: List[Score],
    *,
    db: DBSession | None = None,
    mark_fatigue_shown: bool = False,
) -> SessionStateResponse:
    narratives: List[dict[str, Any]] = []
    if db is not None:
        rows = (
            db.query(Narrative)
            .filter(Narrative.session_id == session.id)
            .order_by(Narrative.created_at.desc())
            .all()
        )
        narratives = [
            {
                "id": row.id,
                "task_type": row.task_type,
                "parameters_hash": row.parameters_hash,
                "model_used": row.model_used,
                "prompt_tokens": row.prompt_tokens,
                "completion_tokens": row.completion_tokens,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "output_json": row.output_json,
            }
            for row in rows
        ]

    return SessionStateResponse(
        session_id=session.id,
        state=session.state,
        completed=_build_completed_instruments(scores),
        available=compute_available_instruments(session, scores),
        safety_flags=session.safety_flags,
        intake=session.intake_data,
        anchors=session.anchors,
        composites=compute_all_composites(scores),
        planet_states=compute_planet_states(session, scores),
        narratives=narratives,
        fatigue_nudge=_compute_fatigue_nudge(
            session, scores, db=db, mark_shown=mark_fatigue_shown
        ),
        ai_readiness=_readiness_engine.check_all(session),
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("", response_model=CreateSessionResponse, status_code=201)
def create_session(db: DBSession = Depends(get_db)):
    """Create a new assessment session. Starts in EXPLORING state."""
    session = Session(
        id=str(uuid.uuid4()),
        state="CORE_FLOW_IN_PROGRESS",
        safety_flags=None,
        intake_data=None,
        anchors=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(session)
    db.flush()
    return CreateSessionResponse(
        session_id=session.id,
        state=session.state,
        available=["intake"],
    )


@router.post("/dev", response_model=CreateSessionResponse, status_code=201)
def create_dev_session(db: DBSession = Depends(get_db)):
    """Create a session already in EXPLORING state, skipping core flow.
    Only available when HELIX_DEV_MODE=1. Do not expose in production.
    """
    if not settings.debug_mode:
        raise HTTPException(status_code=403, detail="Dev mode not enabled (set DEBUG_MODE=true)")
    session = Session(
        id=str(uuid.uuid4()),
        state="EXPLORING",
        safety_flags=None,
        intake_data={"categories": [], "red_thread_question": "[dev]", "top3_ranked": None},
        anchors={"mood": 5, "energy": 5, "focus": 5},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(session)
    db.flush()
    scores = []
    return CreateSessionResponse(
        session_id=session.id,
        state=session.state,
        available=compute_available_instruments(session, scores),
    )


@router.post("/quick-start", response_model=SessionStateResponse, status_code=201)
def create_quick_start_session(db: DBSession = Depends(get_db)):
    """Create a session that has genuinely completed the core flow.
    Only available when HELIX_DEV_MODE=1.
    """
    if not settings.debug_mode:
        raise HTTPException(status_code=403, detail="Dev mode not enabled (set DEBUG_MODE=true)")
        
    session = Session(
        id=str(uuid.uuid4()),
        state="EXPLORING",
        safety_flags=None,
        intake_data={"categories": ["general"], "red_thread_question": "Testing session", "top3_ranked": None},
        anchors={"mood": 5, "energy": 5, "focus": 5},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(session)
    db.flush()
    
    # Create fake scores for PBAT, WSAS, PCPTSD5
    for inst_id, score_val, items_scored in [("pbat", 50, 18), ("wsas", 0, 5), ("pcptsd5", 0, 5)]:
        inst = AssessmentInstance(
            id=str(uuid.uuid4()),
            session_id=session.id,
            instrument_id=inst_id,
            instrument_version="1.0.0",
            responses={},
            status="COMPLETED",
        )
        db.add(inst)
        db.flush()
        score = Score(
            id=str(uuid.uuid4()),
            assessment_instance_id=inst.id,
            instrument_id=inst_id,
            total_score=score_val,
            score_metadata={"n_items_scored": items_scored}
        )
        db.add(score)
        
    db.flush()
    
    scores = (
        db.query(Score)
        .join(AssessmentInstance)
        .filter(AssessmentInstance.session_id == session.id)
        .all()
    )
    return _build_session_state_response(session, scores, db=db)



@router.get("/{session_id}", response_model=SessionStateResponse)
def get_session(session_id: str, db: DBSession = Depends(get_db)):
    """Return session state, completed instruments, and what's available next."""
    session = db.get(Session, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    scores = (
        db.query(Score)
        .join(AssessmentInstance)
        .filter(AssessmentInstance.session_id == session_id)
        .all()
    )

    return _build_session_state_response(
        session, scores, db=db, mark_fatigue_shown=True
    )



@router.post("/{session_id}/dismiss-fatigue", response_model=SessionStateResponse)
def dismiss_fatigue(session_id: str, db: DBSession = Depends(get_db)):
    """Dismiss the fatigue nudge for this session."""
    session = db.get(Session, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
        
    session.fatigue_nudge_dismissed = True
    session.updated_at = datetime.now(timezone.utc)
    db.flush()
    
    scores = (
        db.query(Score)
        .join(AssessmentInstance)
        .filter(AssessmentInstance.session_id == session_id)
        .all()
    )
    return _build_session_state_response(session, scores, db=db)

@router.post("/{session_id}/acknowledge-safety", response_model=SessionStateResponse)
def acknowledge_safety(session_id: str, db: DBSession = Depends(get_db)):
    """Acknowledge safety flags and resume EXPLORING state.

    Clears the session's unacknowledged safety flags and transitions
    SAFETY_PAUSED → EXPLORING.
    """
    session = db.get(Session, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.state != "SAFETY_PAUSED":
        raise HTTPException(
            status_code=409,
            detail="Session is not in SAFETY_PAUSED state",
        )

    session.state = "EXPLORING"
    session.safety_flags = None
    session.updated_at = datetime.now(timezone.utc)
    db.flush()

    scores = (
        db.query(Score)
        .join(AssessmentInstance)
        .filter(AssessmentInstance.session_id == session_id)
        .all()
    )
    return _build_session_state_response(session, scores, db=db)

@router.post("/{session_id}/intake", response_model=SessionStateResponse)
def submit_intake(session_id: str, body: IntakeRequest, db: DBSession = Depends(get_db)):
    """Submit the initial red-thread question and categories."""
    session = db.get(Session, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.state != "CORE_FLOW_IN_PROGRESS":
        raise HTTPException(status_code=409, detail="Intake can only be submitted during CORE_FLOW_IN_PROGRESS")
    if session.intake_data is not None:
        raise HTTPException(status_code=409, detail="Intake has already been submitted for this session")

    if len(body.categories) > 5:
        raise HTTPException(status_code=400, detail="Maximum 5 categories allowed")
    invalid_cats = set(body.categories) - VALID_CATEGORY_IDS
    if invalid_cats:
        raise HTTPException(status_code=400, detail=f"Invalid categories: {invalid_cats}")

    if body.top3_ranked:
        if len(body.top3_ranked) > 3:
            raise HTTPException(status_code=400, detail="Maximum 3 ranked categories allowed")
        # Ensure ranked categories (ignoring None) are a subset of selected categories
        ranked_cats = {c for c in body.top3_ranked if c is not None}
        if not ranked_cats.issubset(set(body.categories)):
            raise HTTPException(status_code=400, detail="Ranked categories must be a subset of selected categories")

    session.intake_data = {
        "red_thread_question": body.red_thread_question,
        "categories": body.categories,
        "top3_ranked": body.top3_ranked,
    }
    session.updated_at = datetime.now(timezone.utc)
    db.flush()

    # Re-evaluate routing. In CORE_FLOW_IN_PROGRESS, we just need to compute availability.
    scores = (
        db.query(Score)
        .join(AssessmentInstance)
        .filter(AssessmentInstance.session_id == session_id)
        .all()
    )
    return _build_session_state_response(session, scores, db=db)

@router.post("/{session_id}/anchors", response_model=SessionStateResponse)
def submit_anchors(session_id: str, body: AnchorsRequest, db: DBSession = Depends(get_db)):
    """Submit session anchors (mood, energy, focus)."""
    session = db.get(Session, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.state != "CORE_FLOW_IN_PROGRESS":
        raise HTTPException(
            status_code=409,
            detail="Anchors can only be submitted during CORE_FLOW_IN_PROGRESS",
        )
    if session.anchors is not None:
        raise HTTPException(status_code=409, detail="Anchors already submitted for this session")

    session.anchors = {
        "mood": body.mood,
        "energy": body.energy,
        "focus": body.focus,
    }
    session.updated_at = datetime.now(timezone.utc)

    # Check state transition? Wait, the state transition happens in routes_assessment.py
    # but what if anchors are the LAST thing submitted? (Normally WSAS and PC-PTSD-5 come after)
    # The rule: intake -> pbat -> anchors -> wsas -> pcptsd5.
    # So anchors are NEVER the last thing. Thus, we don't need to check core_flow_complete here.
    db.flush()

    scores = (
        db.query(Score)
        .join(AssessmentInstance)
        .filter(AssessmentInstance.session_id == session_id)
        .all()
    )
    return _build_session_state_response(session, scores, db=db)


@router.get("/{session_id}/instruments/{instrument_id}", response_model=InstrumentFormPayload)
def get_instrument_render_payload(session_id: str, instrument_id: str, db: DBSession = Depends(get_db)):
    """Return a session-aware render payload for an instrument."""
    session = db.get(Session, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        scorer = registry.get_scorer(instrument_id)
        definition = scorer._def
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown instrument: '{instrument_id}'")

    parent_instance_id = None
    items_to_render = definition.get("items", [])
    
    # Resolve carry-forward logic
    parent_instrument = definition.get("routing", {}).get("parent_instrument")
    carry_forward_items = definition.get("routing", {}).get("carry_forward_items", {})
    
    if parent_instrument and carry_forward_items:
        # Find the most recent parent AssessmentInstance
        parent_instance = (
            db.query(AssessmentInstance)
            .filter(AssessmentInstance.session_id == session_id)
            .filter(AssessmentInstance.instrument_id == parent_instrument)
            .order_by(AssessmentInstance.completed_at.desc())
            .first()
        )
        if parent_instance:
            parent_instance_id = parent_instance.id
            carried_child_ids = set(carry_forward_items.values())
            items_to_render = [
                item for item in items_to_render
                if item["item_id"] not in carried_child_ids
            ]

    is_submittable = session.state != "SAFETY_PAUSED"

    return InstrumentFormPayload(
        instrument_id=definition["instrument_id"],
        instrument_name=definition.get("name", instrument_id),
        instrument_version=definition.get("version", "1.0.0"),
        time_window_text=definition.get("time_window_text"),
        items_to_render=items_to_render,
        response_option_sets=definition.get("response_option_sets", {}),
        parent_instance_id=parent_instance_id,
        session_state=session.state,
        is_submittable=is_submittable,
    )
