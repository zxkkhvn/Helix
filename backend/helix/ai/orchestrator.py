"""NarrativeOrchestrator — single entry point for AI narrative generation.

Wraps ReadinessEngine + FormulationEngine + NarrativeStore (DB cache).
All production API endpoints call this instead of FormulationEngine directly.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session as DBSession

from helix.ai.context import ContextSerializer
from helix.ai.formulation import FormulationEngine
from helix.ai.llm import get_llm_client
from helix.ai.prompt_builder import UnifiedPromptBuilder
from helix.ai.readiness import ReadinessEngine, ReadinessResult
from helix.ai.schemas import (
    FullFormulation,
    InterInstrumentNarration,
    MissionControlSuggestion,
    PlanetSummary,
    RedThreadIntegration,
    TaskType,
)
from helix.models.models import Narrative, Session


@dataclass
class OrchestratorResult:
    ready: bool
    cached: bool
    task_type: TaskType
    readiness: ReadinessResult
    narrative: dict[str, Any] | None = None
    model_used: str | None = None
    generation_time_ms: int | None = None
    error: str | None = None


# Map task type → schema class for post-generation validation
_SCHEMA_MAP = {
    TaskType.INTER_INSTRUMENT_NARRATION: InterInstrumentNarration,
    TaskType.INTER_INSTRUMENT: InterInstrumentNarration,
    TaskType.PLANET_SUMMARY: PlanetSummary,
    TaskType.MISSION_CONTROL: MissionControlSuggestion,
    TaskType.FULL_FORMULATION: FullFormulation,
    TaskType.RED_THREAD: RedThreadIntegration,
}


def _build_parameters_hash(task_type: TaskType, **params: Any) -> str:
    """Stable sha256 hash of task type + sorted non-None parameters dict."""
    canonical = json.dumps(
        {"task_type": task_type.value, **{k: v for k, v in params.items() if v is not None}},
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()[:32]


def _build_engine(task_type: TaskType) -> FormulationEngine:
    llm = get_llm_client(task_type)
    return FormulationEngine(
        llm=llm,
        builder=UnifiedPromptBuilder(),
        context_serializer=ContextSerializer(),
    )


class NarrativeOrchestrator:
    """Single entry point for all AI narrative generation."""

    def __init__(self, db: DBSession):
        self.db = db
        self.readiness = ReadinessEngine()

    async def generate(
        self,
        session: Session,
        task_type: TaskType,
        *,
        force_regenerate: bool = False,
        planet_id: str | None = None,
        prev_instrument_id: str | None = None,
        next_instrument_id: str | None = None,
    ) -> OrchestratorResult:
        """
        Pipeline:
          1. Readiness check (deterministic — no LLM)
          2. Context-hash cache lookup (unless force_regenerate)
          3. Generate + validate + persist
        """
        readiness = self.readiness.check(
            session,
            task_type,
            planet_id=planet_id,
            prev_instrument_id=prev_instrument_id,
            next_instrument_id=next_instrument_id,
        )

        if not readiness.ready:
            return OrchestratorResult(
                ready=False,
                cached=False,
                task_type=task_type,
                readiness=readiness,
            )

        params_hash = _build_parameters_hash(
            task_type,
            planet_id=planet_id,
            prev_instrument_id=prev_instrument_id,
            next_instrument_id=next_instrument_id,
        )

        # Build context hash from the actual payload data to allow "smart reloads"
        engine = _build_engine(task_type)
        context_payload = engine.build_context_payload(session)
        
        # SCOPED CACHING: Prevent unrelated test completions from invalidating specific caches.
        if task_type == TaskType.PLANET_SUMMARY and planet_id:
            from helix.scoring.planets import PLANET_INSTRUMENT_MAP
            relevant_insts = PLANET_INSTRUMENT_MAP.get(planet_id, [])
            context_payload["base_scores"] = [
                s for s in context_payload.get("base_scores", [])
                if s["instrument_id"] in relevant_insts
            ]
        elif task_type in (TaskType.INTER_INSTRUMENT, TaskType.INTER_INSTRUMENT_NARRATION):
            relevant_insts = [prev_instrument_id, next_instrument_id]
            context_payload["base_scores"] = [
                s for s in context_payload.get("base_scores", [])
                if s["instrument_id"] in relevant_insts
            ]

        context_json = json.dumps(context_payload, sort_keys=True)
        current_context_hash = hashlib.sha256(context_json.encode()).hexdigest()

        if not force_regenerate:
            cached = self._find_context_cached(
                session.id, task_type, params_hash, current_context_hash
            )
            if cached is not None:
                return OrchestratorResult(
                    ready=True,
                    cached=True,
                    task_type=task_type,
                    readiness=readiness,
                    narrative=cached.output_json,
                    model_used=cached.model_used,
                )

        start_ms = int(time.monotonic() * 1000)

        try:
            result = await self._dispatch(
                engine,
                session,
                task_type,
                planet_id=planet_id,
                prev_instrument_id=prev_instrument_id,
                next_instrument_id=next_instrument_id,
            )
        except Exception as exc:
            return OrchestratorResult(
                ready=True,
                cached=False,
                task_type=task_type,
                readiness=readiness,
                error=str(exc),
            )

        generation_time_ms = int(time.monotonic() * 1000) - start_ms

        # Determine model used
        model_used = getattr(engine.llm, "model_name", None)

        # Handle dict-form error responses from the LLM adapter
        if isinstance(result, dict) and result.get("error"):
            return OrchestratorResult(
                ready=True,
                cached=False,
                task_type=task_type,
                readiness=readiness,
                error=result.get("message") or result.get("error"),
                model_used=model_used,
                generation_time_ms=generation_time_ms,
            )

        output_dict = result.model_dump() if hasattr(result, "model_dump") else dict(result)

        # Inject planet_id so the client can filter by planet when restoring from cache
        if task_type == TaskType.PLANET_SUMMARY and planet_id:
            output_dict["planet_id"] = planet_id

        # Extract token usage if available and ensure they are ints (handles mocks in tests safely)
        pt = getattr(engine.llm, "_last_prompt_tokens", None)
        ct = getattr(engine.llm, "_last_completion_tokens", None)
        prompt_tokens = pt if isinstance(pt, int) else None
        completion_tokens = ct if isinstance(ct, int) else None

        # Persist narrative with context_hash
        self._persist(
            session_id=session.id,
            task_type=task_type,
            parameters_hash=params_hash,
            context_hash=current_context_hash,
            output_json=output_dict,
            model_used=model_used,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

        # Clear staleness flag — we've just generated/verified a fresh narrative
        session.narratives_stale = False
        session.updated_at = datetime.now(timezone.utc)

        return OrchestratorResult(
            ready=True,
            cached=False,
            task_type=task_type,
            readiness=readiness,
            narrative=output_dict,
            model_used=model_used,
            generation_time_ms=generation_time_ms,
        )

    def check_all_readiness(self, session: Session) -> dict[str, Any]:
        """Return readiness summary for all task types (no LLM)."""
        return self.readiness.check_all(session)

    def list_narratives(self, session_id: str) -> list[dict[str, Any]]:
        """Return all cached narratives for a session, newest first."""
        rows = (
            self.db.query(Narrative)
            .filter(Narrative.session_id == session_id)
            .order_by(Narrative.created_at.desc())
            .all()
        )
        return [
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

    def get_narrative(self, narrative_id: str) -> Narrative | None:
        return self.db.get(Narrative, narrative_id)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _find_context_cached(
        self, session_id: str, task_type: TaskType, parameters_hash: str, context_hash: str
    ) -> Narrative | None:
        """Find a cached narrative that matches both task parameters and exact session context."""
        return (
            self.db.query(Narrative)
            .filter(
                Narrative.session_id == session_id,
                Narrative.task_type == task_type.value,
                Narrative.parameters_hash == parameters_hash,
                Narrative.context_hash == context_hash,
            )
            .order_by(Narrative.created_at.desc())
            .first()
        )

    async def _dispatch(
        self,
        engine: FormulationEngine,
        session: Session,
        task_type: TaskType,
        *,
        planet_id: str | None,
        prev_instrument_id: str | None,
        next_instrument_id: str | None,
    ) -> Any:
        """Dispatch to the correct FormulationEngine method."""
        if task_type in (TaskType.INTER_INSTRUMENT, TaskType.INTER_INSTRUMENT_NARRATION):
            return await engine.generate_inter_instrument_narration(
                session,
                prev_instrument_id=prev_instrument_id,
                next_instrument_id=next_instrument_id,
            )
        if task_type == TaskType.PLANET_SUMMARY:
            return await engine.generate_planet_summary(session, planet_id)
        if task_type == TaskType.MISSION_CONTROL:
            return await engine.generate_mission_control(session)
        if task_type == TaskType.FULL_FORMULATION:
            return await engine.generate_full_formulation(session)
        if task_type == TaskType.RED_THREAD:
            return await engine.generate_red_thread(session)

        raise ValueError(f"No dispatch handler for task type: {task_type}")

    def _persist(
        self,
        *,
        session_id: str,
        task_type: TaskType,
        parameters_hash: str,
        context_hash: str | None,
        output_json: dict[str, Any],
        model_used: str | None,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
    ) -> Narrative:
        row = Narrative(
            id=str(uuid.uuid4()),
            session_id=session_id,
            task_type=task_type.value,
            parameters_hash=parameters_hash,
            context_hash=context_hash,
            output_json=output_json,
            model_used=model_used,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(row)
        self.db.flush()
        return row
