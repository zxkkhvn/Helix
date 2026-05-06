import json
import pytest
from pydantic import ValidationError

from helix.ai.schemas import (
    TaskType,
    InterInstrumentNarration,
    MissionControlSuggestion,
    PlanetSummary,
    FullFormulation,
    RedThreadIntegration
)
from helix.ai.prompt_builder import UnifiedPromptBuilder, Prompt
from helix.ai.prompts import STANDARD_HELIX_SYSTEM_RULES, TASK_TEMPLATES

def test_mission_control_schema_valid():
    """Test valid schema parses correctly."""
    data = {
        "safety_triggered": False,
        "cognitive_reflection": "Reflect on this.",
        "behavioral_observation": "Notice when this happens.",
        "integration_prompt": "How does this connect?",
        "safety_protocol": None
    }
    obj = MissionControlSuggestion.model_validate(data)
    assert obj.safety_triggered is False
    assert obj.cognitive_reflection == "Reflect on this."

def test_mission_control_schema_extra_forbid():
    """Test that extra keys raise validation error."""
    data = {
        "safety_triggered": False,
        "cognitive_reflection": "Reflect on this.",
        "extra_key": "Should fail"
    }
    with pytest.raises(ValidationError):
        MissionControlSuggestion.model_validate(data)

def test_mission_control_safety_override():
    """Test behavior when safety is triggered."""
    data = {
        "safety_triggered": True,
        "cognitive_reflection": None,
        "behavioral_observation": None,
        "integration_prompt": None,
        "safety_protocol": "Please contact emergency services."
    }
    obj = MissionControlSuggestion.model_validate(data)
    assert obj.safety_triggered is True
    assert obj.safety_protocol == "Please contact emergency services."
    assert obj.cognitive_reflection is None

def test_planet_summary_sparse_data():
    """Test sparse data fallback."""
    data = {
        "core_tendencies": "Insufficient data available in the current profile to generate a comprehensive summary for this domain.",
        "environmental_interaction": "Insufficient data available in the current profile to generate a comprehensive summary for this domain.",
        "data_sufficiency_met": False
    }
    obj = PlanetSummary.model_validate(data)
    assert obj.data_sufficiency_met is False
    assert "Insufficient data" in obj.core_tendencies

def test_prompt_builder():
    """Test that the prompt builder correctly injects context and assembles XML."""
    builder = UnifiedPromptBuilder()
    context = {"test_key": "test_value"}
    builder.inject_context(context)
    
    prompt = builder.build_xml_payload(TaskType.FULL_FORMULATION)
    
    # Assert system rules are loaded
    assert "You are an automated narrative synthesizer" in prompt.system
    
    # Assert XML payload structure
    assert "<system_constraints>" in prompt.xml_payload
    assert "<backend_data>" in prompt.xml_payload
    assert "<task_instructions>" in prompt.xml_payload
    
    # Assert context is injected
    assert '"test_key": "test_value"' in prompt.xml_payload

def test_hedging_rules_in_system_prompt():
    """Test that forbidden and permitted words are documented in the system prompt."""
    rules = STANDARD_HELIX_SYSTEM_RULES.lower()
    
    # Check prohibitions
    assert "diagnose" in rules
    assert "disorder" in rules
    
    # Check permitted hedging
    assert "suggests" in rules
    assert "appears" in rules
    assert "tends to" in rules


def test_system_prompt_read_only_and_no_inference_constraints():
    rules = STANDARD_HELIX_SYSTEM_RULES.lower()
    assert "precomputed by helix" in rules
    assert "treated as read-only" in rules
    assert "never recompute" in rules
    assert "never infer missing scores" in rules
    assert "if context is absent, remain limited to what is provided" in rules


def test_mission_control_prompt_backend_routing_constraint():
    mission_prompt = TASK_TEMPLATES[TaskType.MISSION_CONTROL].lower()
    assert "available planets and instruments are determined by the backend" in mission_prompt
    assert "must never invent, unlock, expand, reorder, or override" in mission_prompt


def test_full_formulation_prompt_safety_sparse_precedence():
    full_prompt = TASK_TEMPLATES[TaskType.FULL_FORMULATION].lower()
    assert "safety + sparse consistency" in full_prompt
    assert "sparse themes must still return the exact refusal string" in full_prompt


def test_inter_instrument_prompt_bridge_semantics():
    bridge_prompt = TASK_TEMPLATES[TaskType.INTER_INSTRUMENT_NARRATION].lower()
    assert "prev_instrument_id" in bridge_prompt
    assert "next_instrument_id" in bridge_prompt
    assert "red-thread question" in bridge_prompt
    assert "2-3 sentence bridge" in bridge_prompt


@pytest.mark.parametrize(
    "task_type",
    [
        TaskType.INTER_INSTRUMENT,
        TaskType.MISSION_CONTROL,
        TaskType.PLANET_SUMMARY,
        TaskType.FULL_FORMULATION,
        TaskType.RED_THREAD,
    ],
)
def test_templates_include_context_limit(task_type):
    text = TASK_TEMPLATES[task_type].lower()
    assert "do not infer missing context from unstated assumptions" in text
    assert "if context is absent, remain limited to what is provided" in text
