"""Debug endpoints for development and testing.

Gated behind DEBUG_MODE=true environment variable.
"""

from __future__ import annotations

import os
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, model_validator
from sqlalchemy.orm import Session as DBSession

from helix.ai.context import ContextSerializer
from helix.ai.formulation import FormulationEngine
from helix.ai.llm import LLMClientAdapter, get_llm_client
from helix.ai.prompt_builder import Prompt, UnifiedPromptBuilder
from helix.ai.schemas import TaskType
from helix.db.database import get_db
from helix.models.models import AssessmentInstance, Score, Session
from helix.routing.engine import compute_available_instruments
from helix.scoring import registry
from helix.scoring.composite import compute_all_composites

router = APIRouter(prefix="/debug", tags=["debug"])


def check_debug_mode():
    if os.environ.get("DEBUG_MODE") != "true":
        raise HTTPException(status_code=404, detail="Not Found")


class _NoopLLMAdapter(LLMClientAdapter):
    """Used for debug context/prompt preview paths that must not hit an LLM."""

    async def execute_prompt(self, prompt: Prompt, response_schema):
        raise RuntimeError("LLM execution is disabled for this debug path.")


def _get_session_or_404(db: DBSession, session_id: str) -> Session:
    session = db.get(Session, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


def _build_formulation_engine(task_type: TaskType, require_llm: bool = True) -> FormulationEngine:
    if require_llm:
        llm = get_llm_client(task_type)
    else:
        llm = _NoopLLMAdapter()
    return FormulationEngine(
        llm=llm,
        builder=UnifiedPromptBuilder(),
        context_serializer=ContextSerializer(),
    )


def _has_safety_markers(context_payload: dict[str, Any]) -> bool:
    safety_markers = context_payload.get("safety_markers") or {}
    return any(bool(v) for v in safety_markers.values())


def _to_jsonish(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, BaseModel):
        return value.model_dump()
    if isinstance(value, dict):
        return value
    return {"value": value}


class ScoreTestRequest(BaseModel):
    responses: dict


class PromptPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_type: TaskType
    planet_id: Optional[str] = None
    prev_instrument_id: Optional[str] = None
    next_instrument_id: Optional[str] = None

    @model_validator(mode="after")
    def validate_task_requirements(self):
        if self.task_type == TaskType.PLANET_SUMMARY and not self.planet_id:
            raise ValueError("planet_id is required for PLANET_SUMMARY.")
        if self.task_type in (TaskType.INTER_INSTRUMENT, TaskType.INTER_INSTRUMENT_NARRATION):
            if not self.prev_instrument_id or not self.next_instrument_id:
                raise ValueError(
                    "prev_instrument_id and next_instrument_id are required for INTER_INSTRUMENT_NARRATION."
                )
        return self


class PlanetSummaryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    planet_id: str


class InterInstrumentNarrationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prev_instrument_id: str
    next_instrument_id: str


class DebugPromptPreviewResponse(BaseModel):
    ok: bool
    task_type: TaskType
    session_id: str
    context_payload: dict[str, Any]
    task_parameters: dict[str, Any]
    system: str
    assembled_user_prompt: str


class DebugGenerationResponse(BaseModel):
    ok: bool
    task_type: TaskType
    session_id: str
    data_sufficiency_met: Optional[bool] = None
    safety_markers_present: bool
    context_payload: dict[str, Any]
    prompt: dict[str, Any]
    raw_response: Any = None
    validated_output: Optional[dict[str, Any]] = None
    validation_error: Optional[str] = None


@router.get("/sessions/{session_id}")
def debug_session_dump(session_id: str, db: DBSession = Depends(get_db), _=Depends(check_debug_mode)):
    """Full session dump."""
    session = _get_session_or_404(db, session_id)

    scores = (
        db.query(Score)
        .join(AssessmentInstance)
        .filter(AssessmentInstance.session_id == session_id)
        .all()
    )

    return {
        "session": {
            "id": session.id,
            "state": session.state,
            "intake_data": session.intake_data,
            "anchors": session.anchors,
            "safety_flags": session.safety_flags,
            "fatigue_nudge_shown": session.fatigue_nudge_shown,
            "fatigue_nudge_dismissed": session.fatigue_nudge_dismissed,
        },
        "scores": [
            {
                "instrument_id": s.instrument_id,
                "total_score": s.total_score,
                "band": s.band,
                "subscales": s.subscale_scores,
                "safety_flags": s.safety_flags,
                "score_metadata": s.score_metadata,
            }
            for s in scores
        ],
    }


@router.get("/sessions/{session_id}/composite/{index_id}")
def debug_composite(session_id: str, index_id: str, db: DBSession = Depends(get_db), _=Depends(check_debug_mode)):
    """Composite diagnostic for a specific index."""
    _get_session_or_404(db, session_id)
    scores = (
        db.query(Score)
        .join(AssessmentInstance)
        .filter(AssessmentInstance.session_id == session_id)
        .all()
    )
    composites = compute_all_composites(scores)
    for comp in composites:
        if comp["index_id"] == index_id:
            return comp
    return {"detail": "Composite not found or cannot be computed yet"}


@router.get("/sessions/{session_id}/routing")
def debug_routing(session_id: str, db: DBSession = Depends(get_db), _=Depends(check_debug_mode)):
    """Routing evaluation trace."""
    session = _get_session_or_404(db, session_id)
    scores = (
        db.query(Score)
        .join(AssessmentInstance)
        .filter(AssessmentInstance.session_id == session_id)
        .all()
    )
    available = compute_available_instruments(session, scores)

    return {
        "session_state": session.state,
        "available_instruments": available,
    }


@router.get("/sessions/{session_id}/ai/context")
def debug_ai_context(session_id: str, db: DBSession = Depends(get_db), _=Depends(check_debug_mode)):
    """Returns the serialized PRE_SCORED_JSON_PAYLOAD used by AI generation."""
    session = _get_session_or_404(db, session_id)
    engine = _build_formulation_engine(TaskType.FULL_FORMULATION, require_llm=False)
    payload = engine.build_context_payload(session)
    return {
        "ok": True,
        "session_id": session.id,
        "context_payload": payload,
    }


@router.post("/sessions/{session_id}/ai/prompt-preview", response_model=DebugPromptPreviewResponse)
def debug_ai_prompt_preview(
    session_id: str,
    body: PromptPreviewRequest,
    db: DBSession = Depends(get_db),
    _=Depends(check_debug_mode),
):
    """Assemble AI prompt blocks for a task without calling the LLM."""
    session = _get_session_or_404(db, session_id)
    engine = _build_formulation_engine(body.task_type, require_llm=False)
    preview = engine.build_prompt_preview(
        session=session,
        task_type=body.task_type,
        planet_id=body.planet_id,
        prev_instrument_id=body.prev_instrument_id,
        next_instrument_id=body.next_instrument_id,
    )
    return DebugPromptPreviewResponse(
        ok=True,
        task_type=preview["task_type"],
        session_id=session.id,
        context_payload=preview["context_payload"],
        task_parameters=preview["task_parameters"],
        system=preview["system"],
        assembled_user_prompt=preview["assembled_user_prompt"],
    )


def _build_debug_generation_response(
    *,
    task_type: TaskType,
    session_id: str,
    preview: dict[str, Any],
    result: Any,
    data_sufficiency_met: Optional[bool] = None,
) -> DebugGenerationResponse:
    result_payload = _to_jsonish(result)
    validation_error: Optional[str] = None
    validated_output: Optional[dict[str, Any]] = None
    ok = True

    if isinstance(result_payload, dict) and result_payload.get("error"):
        ok = False
        validation_error = result_payload.get("message") or result_payload.get("error")
    elif isinstance(result_payload, dict):
        validated_output = result_payload

    return DebugGenerationResponse(
        ok=ok,
        task_type=task_type,
        session_id=session_id,
        data_sufficiency_met=data_sufficiency_met,
        safety_markers_present=_has_safety_markers(preview["context_payload"]),
        context_payload=preview["context_payload"],
        prompt={
            "task_type": preview["task_type"],
            "task_parameters": preview["task_parameters"],
            "system": preview["system"],
            "assembled_user_prompt": preview["assembled_user_prompt"],
        },
        raw_response=result_payload,
        validated_output=validated_output,
        validation_error=validation_error,
    )


@router.post("/sessions/{session_id}/ai/full-formulation", response_model=DebugGenerationResponse)
async def debug_ai_full_formulation(
    session_id: str,
    db: DBSession = Depends(get_db),
    _=Depends(check_debug_mode),
):
    session = _get_session_or_404(db, session_id)
    engine = _build_formulation_engine(TaskType.FULL_FORMULATION, require_llm=True)
    preview = engine.build_prompt_preview(session, TaskType.FULL_FORMULATION)
    result = await engine.generate_full_formulation(session)
    return _build_debug_generation_response(
        task_type=TaskType.FULL_FORMULATION,
        session_id=session.id,
        preview=preview,
        result=result,
    )


@router.post("/sessions/{session_id}/ai/planet-summary", response_model=DebugGenerationResponse)
async def debug_ai_planet_summary(
    session_id: str,
    body: PlanetSummaryRequest,
    db: DBSession = Depends(get_db),
    _=Depends(check_debug_mode),
):
    session = _get_session_or_404(db, session_id)
    engine = _build_formulation_engine(TaskType.PLANET_SUMMARY, require_llm=True)
    preview = engine.build_prompt_preview(session, TaskType.PLANET_SUMMARY, planet_id=body.planet_id)
    result = await engine.generate_planet_summary(session, body.planet_id)
    data_sufficiency_met = None
    if isinstance(result, BaseModel) and hasattr(result, "data_sufficiency_met"):
        data_sufficiency_met = bool(getattr(result, "data_sufficiency_met"))
    return _build_debug_generation_response(
        task_type=TaskType.PLANET_SUMMARY,
        session_id=session.id,
        preview=preview,
        result=result,
        data_sufficiency_met=data_sufficiency_met,
    )


@router.post("/sessions/{session_id}/ai/mission-control", response_model=DebugGenerationResponse)
async def debug_ai_mission_control(
    session_id: str,
    db: DBSession = Depends(get_db),
    _=Depends(check_debug_mode),
):
    session = _get_session_or_404(db, session_id)
    engine = _build_formulation_engine(TaskType.MISSION_CONTROL, require_llm=True)
    preview = engine.build_prompt_preview(session, TaskType.MISSION_CONTROL)
    result = await engine.generate_mission_control(session)
    return _build_debug_generation_response(
        task_type=TaskType.MISSION_CONTROL,
        session_id=session.id,
        preview=preview,
        result=result,
    )


@router.post("/sessions/{session_id}/ai/inter-instrument-narration", response_model=DebugGenerationResponse)
async def debug_ai_inter_instrument_narration(
    session_id: str,
    body: InterInstrumentNarrationRequest,
    db: DBSession = Depends(get_db),
    _=Depends(check_debug_mode),
):
    session = _get_session_or_404(db, session_id)
    engine = _build_formulation_engine(TaskType.INTER_INSTRUMENT_NARRATION, require_llm=True)
    preview = engine.build_prompt_preview(
        session,
        TaskType.INTER_INSTRUMENT_NARRATION,
        prev_instrument_id=body.prev_instrument_id,
        next_instrument_id=body.next_instrument_id,
    )
    result = await engine.generate_inter_instrument_narration(
        session,
        prev_instrument_id=body.prev_instrument_id,
        next_instrument_id=body.next_instrument_id,
    )
    return _build_debug_generation_response(
        task_type=TaskType.INTER_INSTRUMENT_NARRATION,
        session_id=session.id,
        preview=preview,
        result=result,
    )


@router.get("/sessions/{session_id}/prompt")
def debug_prompt(session_id: str, db: DBSession = Depends(get_db), _=Depends(check_debug_mode)):
    """Backward-compatible prompt preview endpoint (defaults to full formulation)."""
    session = _get_session_or_404(db, session_id)
    engine = _build_formulation_engine(TaskType.FULL_FORMULATION, require_llm=False)
    preview = engine.build_prompt_preview(session, TaskType.FULL_FORMULATION)
    return {
        "ok": True,
        "task_type": preview["task_type"],
        "session_id": session.id,
        "system": preview["system"],
        "assembled_user_prompt": preview["assembled_user_prompt"],
    }


@router.post("/instruments/{instrument_id}/score-test")
def debug_score_test(instrument_id: str, body: ScoreTestRequest, _=Depends(check_debug_mode)):
    """Score a test vector without persisting."""
    try:
        scorer = registry.get_scorer(instrument_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown instrument: '{instrument_id}'")

    result = scorer.score(body.responses)
    return {
        "total_score": result.total_score,
        "band": result.band,
        "subscale_scores": result.subscale_scores,
        "safety_flags": result.safety_flags,
        "validity_warnings": result.validity_warnings,
        "score_metadata": result.score_metadata,
    }
