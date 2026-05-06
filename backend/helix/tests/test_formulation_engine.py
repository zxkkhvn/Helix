import pytest
from unittest.mock import AsyncMock, MagicMock

from helix.ai.context import ContextSerializer
from helix.ai.formulation import FormulationEngine
from helix.ai.llm import LLMClientAdapter
from helix.ai.prompt_builder import Prompt, UnifiedPromptBuilder
from helix.ai.schemas import (
    FullFormulation,
    InterInstrumentNarration,
    MissionControlSuggestion,
    PlanetSummary,
    TaskType,
)
from helix.models.models import Session


def _build_engine(
    payload: dict,
    llm_response,
):
    mock_llm = MagicMock(spec=LLMClientAdapter)
    mock_llm.execute = AsyncMock(return_value=llm_response)

    mock_builder = MagicMock(spec=UnifiedPromptBuilder)
    fake_prompt = Prompt(system="system", xml_payload="<xml/>")
    mock_builder.build_xml_payload.return_value = fake_prompt

    mock_serializer = MagicMock(spec=ContextSerializer)
    mock_serializer.build_payload.return_value = payload

    engine = FormulationEngine(mock_llm, mock_builder, mock_serializer)
    return engine, mock_llm, mock_builder, mock_serializer, fake_prompt


@pytest.mark.asyncio
async def test_generate_full_formulation_rich():
    mock_session = MagicMock(spec=Session)
    payload = {
        "session_id": "session-1",
        "safety_markers": {"self_harm": False},
        "theme_states": {"current_distress": "RICH"},
        "base_scores": [],
    }
    llm_response = FullFormulation(
        safety_paragraph=None,
        theme_1_current_distress="Rich distress details",
        theme_2_maintaining_processes="Some processes",
        theme_3_relational_cognitive_patterns="Relationships",
        theme_4_values_and_friction="Values",
        theme_5_protective_resources="Protections",
        so_what_layer="Insights",
    )
    engine, mock_llm, mock_builder, mock_serializer, fake_prompt = _build_engine(payload, llm_response)

    result = await engine.generate_full_formulation(mock_session)
    injected_payload = mock_builder.inject_context.call_args.args[0]

    assert result == llm_response
    assert "theme_states" in injected_payload
    assert injected_payload["theme_states"]["current_distress"] == "RICH"
    mock_serializer.build_payload.assert_called_once_with(mock_session)
    mock_builder.build_xml_payload.assert_called_once_with(TaskType.FULL_FORMULATION)
    mock_llm.execute.assert_called_once_with(fake_prompt, response_schema=FullFormulation)


@pytest.mark.asyncio
async def test_generate_planet_summary_sparse():
    mock_session = MagicMock(spec=Session)
    payload = {
        "session_id": "session-1",
        "base_scores": [
            {"instrument_id": "phq2", "total": 2},
            {"instrument_id": "vlq", "total": 12},
        ],
        "completion_state": [{"planet_id": "venus", "status": "AVAILABLE"}],
    }
    llm_response = PlanetSummary(
        core_tendencies="placeholder",
        environmental_interaction="placeholder",
        data_sufficiency_met=True,
    )
    engine, mock_llm, mock_builder, mock_serializer, fake_prompt = _build_engine(payload, llm_response)

    result = await engine.generate_planet_summary(mock_session, "venus")
    assert result.data_sufficiency_met is False
    assert "Insufficient data available" in result.core_tendencies
    assert result.environmental_interaction == result.core_tendencies
    mock_serializer.build_payload.assert_called_once_with(mock_session)
    mock_builder.inject_context.assert_not_called()
    mock_builder.build_xml_payload.assert_not_called()
    mock_llm.execute.assert_not_called()


def test_build_prompt_preview_does_not_call_llm():
    mock_session = MagicMock(spec=Session)
    payload = {
        "session_id": "session-preview",
        "completion_state": [],
        "theme_states": {"current_distress": "SPARSE"},
        "safety_markers": {"self_harm": False, "acute_trauma": False, "severe_distress": False},
    }
    llm_response = MissionControlSuggestion(
        safety_triggered=False,
        cognitive_reflection="x",
        behavioral_observation="y",
        integration_prompt="z",
        safety_protocol=None,
    )
    engine, mock_llm, mock_builder, mock_serializer, _ = _build_engine(payload, llm_response)

    preview = engine.build_prompt_preview(mock_session, TaskType.MISSION_CONTROL)

    assert preview["task_type"] == TaskType.MISSION_CONTROL
    assert "context_payload" in preview
    mock_llm.execute.assert_not_called()
    mock_serializer.build_payload.assert_called_once_with(mock_session)


@pytest.mark.asyncio
async def test_generate_mission_control_without_safety_flags():
    mock_session = MagicMock(spec=Session)
    payload = {
        "session_id": "session-1",
        "pbat_profile": {"subscale_scores": {"flexibility": 60}},
        "completion_state": [
            {
                "planet_id": "venus",
                "status": "DEEP_DIVE_AVAILABLE",
                "available_instruments": ["phq2", "gad2"],
            }
        ],
        "theme_states": {"current_distress": "PARTIAL"},
        "safety_markers": {"self_harm": False, "acute_trauma": False, "severe_distress": False},
        "safety_protocol": None,
    }
    llm_response = MissionControlSuggestion(
        safety_triggered=False,
        cognitive_reflection="You might explore when low energy and worry overlap.",
        behavioral_observation="Notice what tends to happen before motivation dips.",
        integration_prompt="Reflect on which planet patterns feel most linked this week.",
        safety_protocol=None,
    )
    engine, mock_llm, mock_builder, mock_serializer, fake_prompt = _build_engine(payload, llm_response)

    result = await engine.generate_mission_control(mock_session)
    injected_payload = mock_builder.inject_context.call_args.args[0]

    assert result.safety_triggered is False
    assert result.cognitive_reflection is not None
    assert result.behavioral_observation is not None
    assert result.integration_prompt is not None
    assert "pbat_profile" in injected_payload
    assert "completion_state" in injected_payload
    assert "theme_states" in injected_payload
    assert "safety_markers" in injected_payload
    assert injected_payload["available_planets"] == ["venus"]
    assert injected_payload["available_instruments"] == ["phq2", "gad2"]
    mock_builder.build_xml_payload.assert_called_once_with(TaskType.MISSION_CONTROL)
    mock_llm.execute.assert_called_once_with(fake_prompt, response_schema=MissionControlSuggestion)
    mock_serializer.build_payload.assert_called_once_with(mock_session)


@pytest.mark.asyncio
async def test_generate_mission_control_with_safety_override():
    mock_session = MagicMock(spec=Session)
    payload = {
        "session_id": "session-2",
        "completion_state": [],
        "theme_states": {},
        "safety_markers": {"self_harm": True, "acute_trauma": False, "severe_distress": False},
        "safety_protocol": "Please reach out to emergency services or a crisis helpline immediately.",
    }
    llm_response = MissionControlSuggestion(
        safety_triggered=True,
        cognitive_reflection=None,
        behavioral_observation=None,
        integration_prompt=None,
        safety_protocol="Please reach out to emergency services or a crisis helpline immediately.",
    )
    engine, mock_llm, mock_builder, mock_serializer, fake_prompt = _build_engine(payload, llm_response)

    result = await engine.generate_mission_control(mock_session)
    injected_payload = mock_builder.inject_context.call_args.args[0]

    assert result.safety_triggered is True
    assert result.safety_protocol == payload["safety_protocol"]
    assert result.cognitive_reflection is None
    assert result.behavioral_observation is None
    assert result.integration_prompt is None
    assert injected_payload["safety_markers"]["self_harm"] is True
    mock_builder.build_xml_payload.assert_called_once_with(TaskType.MISSION_CONTROL)
    mock_llm.execute.assert_called_once_with(fake_prompt, response_schema=MissionControlSuggestion)
    mock_serializer.build_payload.assert_called_once_with(mock_session)


@pytest.mark.asyncio
async def test_generate_mission_control_requires_completion_state():
    mock_session = MagicMock(spec=Session)
    payload = {
        "session_id": "session-missing-completion",
        "theme_states": {"current_distress": "SPARSE"},
        "safety_markers": {"self_harm": False, "acute_trauma": False, "severe_distress": False},
    }
    llm_response = MissionControlSuggestion(
        safety_triggered=False,
        cognitive_reflection="x",
        behavioral_observation="y",
        integration_prompt="z",
        safety_protocol=None,
    )
    engine, mock_llm, mock_builder, mock_serializer, _ = _build_engine(payload, llm_response)

    with pytest.raises(ValueError, match="completion_state"):
        await engine.generate_mission_control(mock_session)

    mock_llm.execute.assert_not_called()
    mock_builder.build_xml_payload.assert_not_called()
    mock_serializer.build_payload.assert_called_once_with(mock_session)


@pytest.mark.asyncio
async def test_generate_inter_instrument_narration_payload_and_response():
    mock_session = MagicMock(spec=Session)
    payload = {
        "session_id": "session-3",
        "base_scores": [{"instrument_id": "phq2", "total": 3}],
        "theme_states": {"current_distress": "SPARSE"},
        "completion_state": [],
        "safety_markers": {"self_harm": False, "acute_trauma": False, "severe_distress": False},
    }
    llm_response = InterInstrumentNarration(
        convergent_narrative="Both measures suggest heightened distress reactivity.",
        divergent_narrative="One measure suggests low mood while another suggests relative steadiness.",
        composite_reflection="Composite indicators broadly reflect this mixed pattern.",
    )
    engine, mock_llm, mock_builder, mock_serializer, fake_prompt = _build_engine(payload, llm_response)

    result = await engine.generate_inter_instrument_narration(mock_session, "phq2", "gad2")
    injected_payload = mock_builder.inject_context.call_args.args[0]

    assert injected_payload["prev_instrument_id"] == "phq2"
    assert injected_payload["next_instrument_id"] == "gad2"
    assert injected_payload["inter_instrument_focus"] == {
        "prev_instrument_id": "phq2",
        "next_instrument_id": "gad2",
    }
    assert "inter_instrument_metadata" in injected_payload
    assert injected_payload["inter_instrument_metadata"]["previous"]["name"] == "Patient Health Questionnaire-2"
    assert injected_payload["inter_instrument_metadata"]["next"]["name"] == "Generalized Anxiety Disorder-2"
    assert result.convergent_narrative
    assert result.divergent_narrative
    assert result.composite_reflection
    mock_builder.build_xml_payload.assert_called_once_with(TaskType.INTER_INSTRUMENT_NARRATION)
    mock_llm.execute.assert_called_once_with(fake_prompt, response_schema=InterInstrumentNarration)
    mock_serializer.build_payload.assert_called_once_with(mock_session)


@pytest.mark.asyncio
async def test_generate_red_thread_with_valid_question():
    from helix.ai.schemas import RedThreadIntegration

    mock_session = MagicMock(spec=Session)
    payload = {
        "session_id": "session-rt-1",
        "red_thread_question": "Why do I always feel like I'm failing?",
        "red_thread_quality": "present",
        "base_scores": [
            {"instrument_id": "phq2", "total": 3},
            {"instrument_id": "gad2", "total": 4},
            {"instrument_id": "vlq", "total": 2.5},
        ],
        "theme_states": {"current_distress": "PARTIAL"},
        "safety_markers": {"self_harm": False, "acute_trauma": False, "severe_distress": False},
        "completion_state": [],
    }
    llm_response = RedThreadIntegration(
        primary_red_thread="A recurring pattern of self-critical appraisal appears across emotional and values domains.",
        evolution_summary="This pattern seems relatively stable across the measured period, though values engagement shows some variability.",
    )
    engine, mock_llm, mock_builder, mock_serializer, fake_prompt = _build_engine(payload, llm_response)

    result = await engine.generate_red_thread(mock_session)

    assert result.primary_red_thread
    assert result.evolution_summary
    mock_serializer.build_payload.assert_called_once_with(mock_session)
    mock_builder.build_xml_payload.assert_called_once_with(TaskType.RED_THREAD)
    mock_llm.execute.assert_called_once_with(fake_prompt, response_schema=RedThreadIntegration)


@pytest.mark.asyncio
async def test_generate_red_thread_no_question_returns_deterministic_refusal():
    from helix.ai.schemas import RedThreadIntegration

    mock_session = MagicMock(spec=Session)
    payload = {
        "session_id": "session-rt-empty",
        "red_thread_question": "",
        "base_scores": [],
        "safety_markers": {"self_harm": False},
        "completion_state": [],
    }
    # LLM response would be ignored — no LLM call should happen
    llm_response = RedThreadIntegration(
        primary_red_thread="should not appear",
        evolution_summary="should not appear",
    )
    engine, mock_llm, mock_builder, mock_serializer, _ = _build_engine(payload, llm_response)

    result = await engine.generate_red_thread(mock_session)

    assert "No guiding question" in result.primary_red_thread
    assert "Unable to generate" in result.evolution_summary
    mock_llm.execute.assert_not_called()
    mock_builder.build_xml_payload.assert_not_called()


@pytest.mark.asyncio
async def test_generate_red_thread_dev_placeholder_returns_refusal():
    from helix.ai.schemas import RedThreadIntegration

    mock_session = MagicMock(spec=Session)
    payload = {
        "session_id": "session-rt-dev",
        "red_thread_question": "[dev]",
        "base_scores": [],
        "safety_markers": {"self_harm": False},
        "completion_state": [],
    }
    llm_response = RedThreadIntegration(primary_red_thread="x", evolution_summary="y")
    engine, mock_llm, mock_builder, mock_serializer, _ = _build_engine(payload, llm_response)

    result = await engine.generate_red_thread(mock_session)

    assert "No guiding question" in result.primary_red_thread
    mock_llm.execute.assert_not_called()


def test_build_prompt_preview_red_thread():
    """RED_THREAD case must not raise ValueError in build_prompt_preview."""
    mock_session = MagicMock(spec=Session)
    payload = {
        "session_id": "session-preview-rt",
        "red_thread_question": "Why do I feel stuck?",
        "completion_state": [],
        "theme_states": {},
        "safety_markers": {"self_harm": False, "acute_trauma": False, "severe_distress": False},
    }
    from helix.ai.schemas import RedThreadIntegration
    llm_response = RedThreadIntegration(primary_red_thread="x", evolution_summary="y")
    engine, mock_llm, mock_builder, mock_serializer, _ = _build_engine(payload, llm_response)

    preview = engine.build_prompt_preview(mock_session, TaskType.RED_THREAD)

    assert preview["task_type"] == TaskType.RED_THREAD
    assert "context_payload" in preview
    mock_llm.execute.assert_not_called()

