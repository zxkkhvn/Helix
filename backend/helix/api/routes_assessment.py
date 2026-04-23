"""Assessment submission endpoint.

POST /sessions/{session_id}/assessments/{instrument_id}/submit

Carry-forward is computed server-side from the parent AssessmentInstance —
the client is never trusted to supply carried values.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from helix.db.database import get_db
from helix.models.models import AssessmentInstance, Score, Session
from helix.routing.engine import RoutingAction, _build_carry_forward, evaluate_routing
from helix.scoring import registry

router = APIRouter(prefix="/sessions", tags=["assessments"])

# Crisis resource payload returned when a session is SAFETY_PAUSED
CRISIS_RESOURCES = {
    "message": (
        "Your responses indicate you may be going through a very difficult time. "
        "Please reach out for support."
    ),
    "resources": [
        {"name": "Samaritans (UK)", "phone": "116 123", "url": "https://www.samaritans.org"},
        {"name": "Crisis Text Line", "text": "Text HOME to 85258"},
        {"name": "International Association for Suicide Prevention",
         "url": "https://www.iasp.info/resources/Crisis_Centres/"},
    ],
}


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------

class SubmitRequest(BaseModel):
    responses: Dict[str, float]
    parent_instance_id: Optional[str] = None
    timestamps: Optional[List[float]] = None  # optional, for rapid-response detection


class ScoreOut(BaseModel):
    instrument_id: str
    total_score: float
    band: Optional[str]
    subscale_scores: Optional[dict]
    safety_flags: list
    validity_warnings: list


class RoutingOut(BaseModel):
    action: str
    next_instrument_id: Optional[str]
    carry_forward_items: Optional[dict]
    safety_triggered: bool
    flags: List[str]


class SubmitResponse(BaseModel):
    assessment_instance_id: str
    score: ScoreOut
    routing: RoutingOut
    session_state: str


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post(
    "/{session_id}/assessments/{instrument_id}/submit",
    response_model=SubmitResponse,
)
def submit_assessment(
    session_id: str,
    instrument_id: str,
    body: SubmitRequest,
    db: DBSession = Depends(get_db),
):
    # 1. Validate session
    session = db.get(Session, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.state == "SAFETY_PAUSED":
        raise HTTPException(
            status_code=409,
            detail="Session is paused due to a safety concern. "
                   "Acknowledge safety resources before continuing.",
            headers={"X-Crisis-Resources": json.dumps(CRISIS_RESOURCES)},
        )

    # 2. Get scorer + definition
    try:
        scorer = registry.get_scorer(instrument_id)
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown instrument: '{instrument_id}'",
        )

    definition = scorer._def  # all scorers store their definition as _def

    # 3. Compute carry-forward server-side from parent AssessmentInstance
    carried_responses: Optional[dict] = None
    if body.parent_instance_id:
        parent = db.get(AssessmentInstance, body.parent_instance_id)
        if parent is None or parent.session_id != session_id:
            raise HTTPException(
                status_code=400,
                detail="parent_instance_id not found in this session",
            )
        carried_responses = _build_carry_forward(definition, parent.responses)

    # 4. Score — pass new responses + server-computed carry-forward
    score_result = scorer.score(
        responses=body.responses,
        timestamps=body.timestamps,
        carried_responses=carried_responses,
    )

    # 5. Build complete response set for storage (new + carried)
    all_responses = dict(body.responses)
    if carried_responses:
        all_responses.update(carried_responses)

    # 6. Evaluate routing
    routing = evaluate_routing(definition, score_result, all_responses)

    # If expansion triggered, build carry-forward items for the response
    # (so the client knows what to prefill / what has already been answered)
    if routing.next_instrument_id:
        child_def = None
        try:
            child_scorer = registry.get_scorer(routing.next_instrument_id)
            child_def = child_scorer._def
        except KeyError:
            pass
        if child_def:
            routing.carry_forward_items = _build_carry_forward(child_def, all_responses)

    # 7. Persist AssessmentInstance
    instance_id = str(uuid.uuid4())
    instance = AssessmentInstance(
        id=instance_id,
        session_id=session_id,
        instrument_id=instrument_id,
        instrument_version=definition.get("version", "unknown"),
        parent_instance_id=body.parent_instance_id,
        responses=all_responses,
        status="COMPLETED",
        created_at=datetime.utcnow(),
        completed_at=datetime.utcnow(),
    )
    db.add(instance)
    db.flush()

    # 8. Persist Score
    score_row = Score(
        id=str(uuid.uuid4()),
        assessment_instance_id=instance_id,
        instrument_id=instrument_id,
        total_score=score_result.total_score,
        band=score_result.band,
        subscale_scores=score_result.subscale_scores,
        safety_flags=score_result.safety_flags,
        validity_warnings=score_result.validity_warnings,
        score_metadata=score_result.metadata,
        created_at=datetime.utcnow(),
    )
    db.add(score_row)
    db.flush()

    # 9. Handle safety protocol
    if routing.safety_triggered:
        safety_event = {
            "instrument_id": instrument_id,
            "item_id": score_result.safety_flags[0]["item_id"] if score_result.safety_flags else None,
            "reason": "safety_item_triggered",
            "timestamp": datetime.utcnow().isoformat(),
        }
        existing_flags = session.safety_flags or []
        session.safety_flags = existing_flags + [safety_event]
        session.state = "SAFETY_PAUSED"
        session.updated_at = datetime.utcnow()

    # 10. Check if core flow is complete (transition to EXPLORING if not SAFETY_PAUSED)
    if session.state == "CORE_FLOW_IN_PROGRESS":
        all_scores = db.query(Score).join(AssessmentInstance).filter(AssessmentInstance.session_id == session_id).all()
        completed_ids = {s.instrument_id for s in all_scores}
        core_flow_complete = (
            session.intake_data is not None and
            session.anchors is not None and
            "pbat" in completed_ids and
            "wsas" in completed_ids and
            "pcptsd5" in completed_ids
        )
        if core_flow_complete:
            session.state = "EXPLORING"
            session.updated_at = datetime.utcnow()

    return SubmitResponse(
        assessment_instance_id=instance_id,
        score=ScoreOut(
            instrument_id=score_result.instrument_id,
            total_score=score_result.total_score,
            band=None if definition.get("suppress_band_from_user") else score_result.band,
            subscale_scores=score_result.subscale_scores,
            safety_flags=score_result.safety_flags,
            validity_warnings=score_result.validity_warnings,
        ),
        routing=RoutingOut(
            action=routing.action,
            next_instrument_id=routing.next_instrument_id,
            carry_forward_items=routing.carry_forward_items,
            safety_triggered=routing.safety_triggered,
            flags=routing.flags,
        ),
        session_state=session.state,
    )
