from enum import Enum
from typing import Optional
from pydantic import BaseModel, ConfigDict

class TaskType(str, Enum):
    INTER_INSTRUMENT_NARRATION = "inter_instrument_narration"
    INTER_INSTRUMENT = "inter_instrument"
    MISSION_CONTROL = "mission_control"
    PLANET_SUMMARY = "planet_summary"
    FULL_FORMULATION = "full_formulation"
    RED_THREAD = "red_thread"

class HelixAISchema(BaseModel):
    """Base class for all HELIX AI output schemas, enforcing strict key validation."""
    model_config = ConfigDict(extra="forbid")

class InterInstrumentNarration(HelixAISchema):
    convergent_narrative: str
    divergent_narrative: str
    composite_reflection: Optional[str] = None

class MissionControlSuggestion(HelixAISchema):
    safety_triggered: bool
    cognitive_reflection: Optional[str] = None
    behavioral_observation: Optional[str] = None
    integration_prompt: Optional[str] = None
    safety_protocol: Optional[str] = None

class PlanetSummary(HelixAISchema):
    core_tendencies: str
    environmental_interaction: str
    data_sufficiency_met: bool

class FullFormulation(HelixAISchema):
    safety_paragraph: Optional[str] = None
    theme_1_current_distress: str
    theme_2_maintaining_processes: str
    theme_3_relational_cognitive_patterns: str
    theme_4_values_and_friction: str
    theme_5_protective_resources: str
    so_what_layer: Optional[str] = None

class RedThreadIntegration(HelixAISchema):
    primary_red_thread: str
    evolution_summary: str
