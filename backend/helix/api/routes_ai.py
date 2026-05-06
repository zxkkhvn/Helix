"""Production AI narrative endpoints.

These are non-debug endpoints that go through NarrativeOrchestrator
(readiness-gated, cached, persisted). Available in all modes.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, model_validator
from sqlalchemy.orm import Session as DBSession

from helix.ai.orchestrator import NarrativeOrchestrator
from helix.ai.schemas import TaskType
from helix.db.database import get_db
from helix.models.models import Session

router = APIRouter(prefix="/sessions", tags=["ai"])


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class NarrateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_type: TaskType
    planet_id: Optional[str] = None
    prev_instrument_id: Optional[str] = None
    next_instrument_id: Optional[str] = None
    force_regenerate: bool = False

    @model_validator(mode="after")
    def validate_task_requirements(self):
        if self.task_type == TaskType.PLANET_SUMMARY and not self.planet_id:
            raise ValueError("planet_id is required for PLANET_SUMMARY.")
        if self.task_type in (TaskType.INTER_INSTRUMENT, TaskType.INTER_INSTRUMENT_NARRATION):
            if not self.prev_instrument_id or not self.next_instrument_id:
                raise ValueError(
                    "prev_instrument_id and next_instrument_id are required for "
                    "INTER_INSTRUMENT_NARRATION."
                )
        return self


class NarrateResponse(BaseModel):
    ok: bool
    ready: bool
    cached: bool
    task_type: str
    readiness_reason: Optional[str] = None
    readiness_detail: Optional[dict[str, Any]] = None
    narrative: Optional[dict[str, Any]] = None
    model_used: Optional[str] = None
    generation_time_ms: Optional[int] = None
    error: Optional[str] = None


class NarrativeListItem(BaseModel):
    id: str
    task_type: str
    parameters_hash: str
    model_used: Optional[str]
    prompt_tokens: Optional[int]
    completion_tokens: Optional[int]
    created_at: Optional[str]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_session_or_404(db: DBSession, session_id: str) -> Session:
    session = db.get(Session, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/{session_id}/ai/readiness")
def ai_readiness_all(session_id: str, db: DBSession = Depends(get_db)):
    """Return readiness status for all AI task types. No LLM call."""
    session = _get_session_or_404(db, session_id)
    orchestrator = NarrativeOrchestrator(db)
    return {
        "ok": True,
        "session_id": session_id,
        "ai_readiness": orchestrator.check_all_readiness(session),
    }


@router.get("/{session_id}/ai/readiness/{task_type}")
def ai_readiness_single(
    session_id: str, task_type: str, db: DBSession = Depends(get_db)
):
    """Return readiness for a specific task type. No LLM call."""
    session = _get_session_or_404(db, session_id)

    try:
        parsed_task_type = TaskType(task_type)
    except ValueError:
        raise HTTPException(
            status_code=400, detail=f"Unknown task type: '{task_type}'"
        )

    orchestrator = NarrativeOrchestrator(db)
    result = orchestrator.readiness.check(session, parsed_task_type)
    return {
        "ok": True,
        "session_id": session_id,
        "task_type": task_type,
        "ready": result.ready,
        "reason": result.reason,
        "data_summary": result.data_summary,
    }


@router.post("/{session_id}/ai/narrate", response_model=NarrateResponse)
async def ai_narrate(
    session_id: str,
    body: NarrateRequest,
    db: DBSession = Depends(get_db),
):
    """Generate (or return cached) AI narrative for a task type.

    Always returns 200. If not ready, `ready=False` with `readiness_reason`.
    If generation fails, `ok=False` with `error`.
    """
    session = _get_session_or_404(db, session_id)
    orchestrator = NarrativeOrchestrator(db)

    result = await orchestrator.generate(
        session,
        body.task_type,
        force_regenerate=body.force_regenerate,
        planet_id=body.planet_id,
        prev_instrument_id=body.prev_instrument_id,
        next_instrument_id=body.next_instrument_id,
    )

    ok = result.ready and result.error is None
    return NarrateResponse(
        ok=ok,
        ready=result.ready,
        cached=result.cached,
        task_type=result.task_type.value,
        readiness_reason=result.readiness.reason if not result.ready else None,
        readiness_detail=result.readiness.data_summary if not result.ready else None,
        narrative=result.narrative,
        model_used=result.model_used,
        generation_time_ms=result.generation_time_ms,
        error=result.error,
    )


@router.get("/{session_id}/ai/narratives")
def list_narratives(session_id: str, db: DBSession = Depends(get_db)):
    """List all cached narratives for a session, newest first."""
    _get_session_or_404(db, session_id)
    orchestrator = NarrativeOrchestrator(db)
    narratives = orchestrator.list_narratives(session_id)
    return {
        "ok": True,
        "session_id": session_id,
        "narratives": narratives,
    }


@router.get("/{session_id}/ai/narratives/{narrative_id}")
def get_narrative(
    session_id: str, narrative_id: str, db: DBSession = Depends(get_db)
):
    """Retrieve a specific cached narrative."""
    _get_session_or_404(db, session_id)
    orchestrator = NarrativeOrchestrator(db)
    row = orchestrator.get_narrative(narrative_id)
    if row is None or row.session_id != session_id:
        raise HTTPException(status_code=404, detail="Narrative not found")
    return {
        "ok": True,
        "id": row.id,
        "session_id": row.session_id,
        "task_type": row.task_type,
        "parameters_hash": row.parameters_hash,
        "model_used": row.model_used,
        "prompt_tokens": row.prompt_tokens,
        "completion_tokens": row.completion_tokens,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "output_json": row.output_json,
    }
