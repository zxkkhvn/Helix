"""Session management endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from helix.db.database import get_db
from helix.models.models import AssessmentInstance, Score, Session
from helix.routing.engine import compute_available_instruments

router = APIRouter(prefix="/sessions", tags=["sessions"])


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class CompletedInstrument(BaseModel):
    instrument_id: str
    assessment_instance_id: str
    total_score: float
    band: Optional[str]


class SessionStateResponse(BaseModel):
    session_id: str
    state: str
    completed: List[CompletedInstrument]
    available: List[str]
    safety_flags: Optional[list]


class CreateSessionResponse(BaseModel):
    session_id: str
    state: str
    available: List[str]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("", response_model=CreateSessionResponse, status_code=201)
def create_session(db: DBSession = Depends(get_db)):
    """Create a new assessment session. Starts in EXPLORING state."""
    session = Session(
        id=str(uuid.uuid4()),
        state="EXPLORING",
        safety_flags=None,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(session)
    db.flush()
    return CreateSessionResponse(
        session_id=session.id,
        state=session.state,
        available=["phq2", "gad2", "paq_s"],
    )


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

    completed = [
        CompletedInstrument(
            instrument_id=s.instrument_id,
            assessment_instance_id=s.assessment_instance_id,
            total_score=s.total_score,
            band=s.band,
        )
        for s in scores
    ]

    return SessionStateResponse(
        session_id=session.id,
        state=session.state,
        completed=completed,
        available=compute_available_instruments(scores),
        safety_flags=session.safety_flags,
    )


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
    session.updated_at = datetime.utcnow()
    db.flush()

    scores = (
        db.query(Score)
        .join(AssessmentInstance)
        .filter(AssessmentInstance.session_id == session_id)
        .all()
    )
    completed = [
        CompletedInstrument(
            instrument_id=s.instrument_id,
            assessment_instance_id=s.assessment_instance_id,
            total_score=s.total_score,
            band=s.band,
        )
        for s in scores
    ]

    return SessionStateResponse(
        session_id=session.id,
        state=session.state,
        completed=completed,
        available=compute_available_instruments(scores),
        safety_flags=None,
    )
