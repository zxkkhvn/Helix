from __future__ import annotations

import copy
import json
from typing import Any, Type, TypeVar

from pydantic import BaseModel

from helix.ai.context import ContextSerializer
from helix.ai.llm import LLMClientAdapter
from helix.ai.prompt_builder import Prompt, UnifiedPromptBuilder
from helix.ai.schemas import (
    FullFormulation,
    InterInstrumentNarration,
    MissionControlSuggestion,
    PlanetSummary,
    RedThreadIntegration,
    TaskType,
)
from helix.models.models import Session
from helix.scoring.planet_state import PLANET_INSTRUMENTS
from helix.scoring.registry import DEFINITIONS_DIR

T = TypeVar("T", bound=BaseModel)

SPARSE_REFUSAL_TEXT = (
    "Insufficient data available in the current profile to generate a comprehensive summary for this domain."
)


class FormulationEngine:
    """Orchestrates AI tasks by connecting serializer, prompt builder, and LLM."""

    def __init__(
        self,
        llm: LLMClientAdapter,
        builder: UnifiedPromptBuilder,
        context_serializer: ContextSerializer,
    ):
        self.llm = llm
        self.builder = builder
        self.context_serializer = context_serializer

    async def _execute(self, prompt: Prompt, response_schema: Type[T]) -> T | dict[str, Any]:
        """Execute using the new ``execute`` method with backward compatibility."""
        if hasattr(self.llm, "execute"):
            return await self.llm.execute(prompt, response_schema=response_schema)
        return await self.llm.execute_prompt(prompt, response_schema=response_schema)

    @staticmethod
    def _canonical_task_type(task_type: TaskType) -> TaskType:
        if task_type == TaskType.INTER_INSTRUMENT:
            return TaskType.INTER_INSTRUMENT_NARRATION
        return task_type

    @staticmethod
    def _extract_availability(payload: dict) -> tuple[list[str], list[str]]:
        """Derive available planets/instruments from completion_state."""
        completion_state = payload.get("completion_state") or []
        available_planets: list[str] = []
        available_instruments: list[str] = []

        for state in completion_state:
            planet_id = state.get("planet_id")
            status = state.get("status")
            if planet_id and status != "LOCKED" and planet_id not in available_planets:
                available_planets.append(planet_id)

            for instrument_id in state.get("available_instruments", []) or []:
                if instrument_id not in available_instruments:
                    available_instruments.append(instrument_id)

        return available_planets, available_instruments

    @staticmethod
    def _normalize_safety_context(payload: dict) -> dict:
        """Ensure safety markers/protocol are always present at root."""
        normalized = copy.deepcopy(payload)
        safety_markers = normalized.get("safety_markers") or {}
        normalized["safety_markers"] = {
            "self_harm": bool(safety_markers.get("self_harm", False)),
            "acute_trauma": bool(safety_markers.get("acute_trauma", False)),
            "severe_distress": bool(safety_markers.get("severe_distress", False)),
        }
        normalized.setdefault("safety_protocol", None)
        return normalized

    @staticmethod
    def _load_instrument_definition(instrument_id: str) -> dict[str, Any] | None:
        path = DEFINITIONS_DIR / f"{instrument_id}.json"
        if not path.exists():
            return None

        try:
            with path.open("r", encoding="utf-8") as file:
                return json.load(file)
        except (OSError, json.JSONDecodeError):
            return None

    def _instrument_metadata(self, instrument_id: str) -> dict[str, Any]:
        definition = self._load_instrument_definition(instrument_id)
        if definition is None:
            return {
                "instrument_id": instrument_id,
                "name": None,
                "planet": None,
                "brief_description": None,
            }

        brief_description = definition.get("time_window_text") or definition.get("abbreviation")
        return {
            "instrument_id": instrument_id,
            "name": definition.get("name"),
            "planet": definition.get("planet"),
            "brief_description": brief_description,
        }

    def _build_mission_control_payload(self, payload: dict) -> dict:
        mission_payload = copy.deepcopy(payload)

        mission_payload.setdefault("pbat_profile", None)
        if "completion_state" not in mission_payload:
            raise ValueError(
                "Mission Control requires backend-provided 'completion_state' to derive availability."
            )
        mission_payload.setdefault("completion_state", [])
        mission_payload.setdefault("theme_states", {})
        mission_payload.setdefault("safety_protocol", None)

        safety_markers = mission_payload.get("safety_markers") or {}
        mission_payload["safety_markers"] = {
            "self_harm": bool(safety_markers.get("self_harm", False)),
            "acute_trauma": bool(safety_markers.get("acute_trauma", False)),
            "severe_distress": bool(safety_markers.get("severe_distress", False)),
        }

        available_planets, available_instruments = self._extract_availability(mission_payload)
        mission_payload["available_planets"] = available_planets
        mission_payload["available_instruments"] = available_instruments

        return mission_payload

    def _build_planet_summary_payload(self, payload: dict, planet_id: str) -> dict:
        planet_instruments = PLANET_INSTRUMENTS.get(planet_id, {})
        allowed_instruments = set(
            planet_instruments.get("quick_scan", []) + planet_instruments.get("deep_dive", [])
        )

        filtered_scores = [
            score for score in payload.get("base_scores", []) if score.get("instrument_id") in allowed_instruments
        ]

        planet_state = next(
            (state for state in payload.get("completion_state", []) if state.get("planet_id") == planet_id),
            None,
        )

        planet_payload = copy.deepcopy(payload)
        planet_payload["base_scores"] = filtered_scores
        planet_payload["planet_focus"] = planet_state
        return planet_payload

    @staticmethod
    def _planet_has_sufficient_data(planet_payload: dict) -> bool:
        distinct_instruments = {
            score.get("instrument_id")
            for score in (planet_payload.get("base_scores") or [])
            if score.get("instrument_id")
        }
        return len(distinct_instruments) >= 2

    def _build_inter_instrument_payload(
        self,
        payload: dict,
        prev_instrument_id: str,
        next_instrument_id: str,
    ) -> dict:
        narration_payload = copy.deepcopy(payload)
        narration_payload["prev_instrument_id"] = prev_instrument_id
        narration_payload["next_instrument_id"] = next_instrument_id
        narration_payload["inter_instrument_focus"] = {
            "prev_instrument_id": prev_instrument_id,
            "next_instrument_id": next_instrument_id,
        }
        narration_payload["inter_instrument_metadata"] = {
            "previous": self._instrument_metadata(prev_instrument_id),
            "next": self._instrument_metadata(next_instrument_id),
        }
        return narration_payload

    def build_context_payload(self, session: Session) -> dict:
        """Build the normalized context contract used for AI tasks."""
        payload = self.context_serializer.build_payload(session)
        return self._normalize_safety_context(payload)

    def build_prompt_preview(
        self,
        session: Session,
        task_type: TaskType,
        *,
        planet_id: str | None = None,
        prev_instrument_id: str | None = None,
        next_instrument_id: str | None = None,
    ) -> dict[str, Any]:
        """Assemble task context + prompt without calling the LLM."""
        canonical_task_type = self._canonical_task_type(task_type)
        base_payload = self.build_context_payload(session)
        task_parameters: dict[str, Any] = {}

        if canonical_task_type == TaskType.FULL_FORMULATION:
            task_payload = base_payload
        elif canonical_task_type == TaskType.PLANET_SUMMARY:
            if not planet_id:
                raise ValueError("planet_id is required for PLANET_SUMMARY.")
            task_payload = self._build_planet_summary_payload(base_payload, planet_id=planet_id)
            task_parameters["planet_id"] = planet_id
            task_parameters["data_sufficiency_met"] = self._planet_has_sufficient_data(task_payload)
        elif canonical_task_type == TaskType.MISSION_CONTROL:
            task_payload = self._build_mission_control_payload(base_payload)
        elif canonical_task_type == TaskType.INTER_INSTRUMENT_NARRATION:
            if not prev_instrument_id or not next_instrument_id:
                raise ValueError(
                    "prev_instrument_id and next_instrument_id are required for INTER_INSTRUMENT_NARRATION."
                )
            task_payload = self._build_inter_instrument_payload(
                base_payload,
                prev_instrument_id=prev_instrument_id,
                next_instrument_id=next_instrument_id,
            )
            task_parameters["prev_instrument_id"] = prev_instrument_id
            task_parameters["next_instrument_id"] = next_instrument_id
        elif canonical_task_type == TaskType.RED_THREAD:
            task_payload = base_payload
        else:
            raise ValueError(f"Unsupported task type for formulation preview: {canonical_task_type}")

        self.builder.inject_context(task_payload)
        prompt = self.builder.build_xml_payload(canonical_task_type)

        return {
            "task_type": canonical_task_type,
            "context_payload": task_payload,
            "task_parameters": task_parameters,
            "system": prompt.system,
            "assembled_user_prompt": prompt.xml_payload,
        }

    async def generate_full_formulation(self, session: Session) -> FullFormulation:
        """Generate a five-theme full formulation narrative."""
        payload = self.build_context_payload(session)
        self.builder.inject_context(payload)
        prompt = self.builder.build_xml_payload(TaskType.FULL_FORMULATION)
        return await self._execute(prompt, response_schema=FullFormulation)

    async def generate_planet_summary(self, session: Session, planet_id: str) -> PlanetSummary:
        """Generate a summary of completed/available data in one planet."""
        payload = self.build_context_payload(session)
        planet_payload = self._build_planet_summary_payload(payload, planet_id=planet_id)

        # Deterministic sparse guard before LLM call.
        if not self._planet_has_sufficient_data(planet_payload):
            return PlanetSummary(
                core_tendencies=SPARSE_REFUSAL_TEXT,
                environmental_interaction=SPARSE_REFUSAL_TEXT,
                data_sufficiency_met=False,
            )

        self.builder.inject_context(planet_payload)
        prompt = self.builder.build_xml_payload(TaskType.PLANET_SUMMARY)
        return await self._execute(prompt, response_schema=PlanetSummary)

    async def generate_mission_control(self, session: Session) -> MissionControlSuggestion:
        """Generate exploratory Mission Control suggestions."""
        payload = self.build_context_payload(session)
        mission_payload = self._build_mission_control_payload(payload)

        self.builder.inject_context(mission_payload)
        prompt = self.builder.build_xml_payload(TaskType.MISSION_CONTROL)
        return await self._execute(prompt, response_schema=MissionControlSuggestion)

    async def generate_inter_instrument_narration(
        self,
        session: Session,
        prev_instrument_id: str,
        next_instrument_id: str,
    ) -> InterInstrumentNarration:
        """Generate bridge narration between two instruments."""
        payload = self.build_context_payload(session)
        narration_payload = self._build_inter_instrument_payload(
            payload,
            prev_instrument_id=prev_instrument_id,
            next_instrument_id=next_instrument_id,
        )

        self.builder.inject_context(narration_payload)
        prompt = self.builder.build_xml_payload(TaskType.INTER_INSTRUMENT_NARRATION)
        return await self._execute(prompt, response_schema=InterInstrumentNarration)

    async def generate_red_thread(self, session: Session) -> RedThreadIntegration:
        """Generate longitudinal red-thread synthesis against the guiding question."""
        payload = self.build_context_payload(session)

        red_thread_question = payload.get("red_thread_question", "")
        if not red_thread_question or red_thread_question.strip() in ("", "[dev]"):
            return RedThreadIntegration(
                primary_red_thread=(
                    "No guiding question has been provided for this session."
                ),
                evolution_summary=(
                    "Unable to generate evolution summary without a guiding question."
                ),
            )

        self.builder.inject_context(payload)
        prompt = self.builder.build_xml_payload(TaskType.RED_THREAD)
        return await self._execute(prompt, response_schema=RedThreadIntegration)
