from __future__ import annotations

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Type, TypeVar, Union

import httpx
from pydantic import BaseModel, ValidationError

from helix.config import settings
from helix.ai.prompt_builder import Prompt
from helix.ai.schemas import TaskType

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_RETRY_STATUS_CODES = {429, 500, 502, 503, 504}
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 2.0  # seconds


async def _post_with_retry(
    url: str,
    *,
    params: dict | None = None,
    json_body: dict,
    timeout: float = 120.0,
) -> httpx.Response:
    """POST with exponential-backoff retry on 429/5xx and timeout."""
    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    params=params,
                    json=json_body,
                    timeout=timeout,
                )
            if response.status_code not in _RETRY_STATUS_CODES:
                response.raise_for_status()
                return response
            last_exc = httpx.HTTPStatusError(
                f"HTTP {response.status_code}",
                request=response.request,
                response=response,
            )
        except httpx.TimeoutException as exc:
            last_exc = exc
        if attempt < _MAX_RETRIES:
            await asyncio.sleep(_RETRY_BASE_DELAY * (2 ** attempt))
    raise last_exc  # type: ignore[misc]

class LLMClientAdapter(ABC):
    """Abstract base class for LLM generation clients.
    
    Strictly constrained to narrative generation only.
    No clinical scoring or routing authority should be implemented here.
    """

    async def execute(self, prompt: Prompt, response_schema: Type[T]) -> Union[T, dict[str, Any]]:
        """Primary execution method used by orchestration layers.
        
        Kept as a thin wrapper for backward compatibility with existing adapters
        that implement ``execute_prompt``.
        """
        return await self.execute_prompt(prompt, response_schema)

    @abstractmethod
    async def execute_prompt(self, prompt: Prompt, response_schema: Type[T]) -> Union[T, dict[str, Any]]:
        """Execute a prompt and validate the output against the response schema."""
        pass

    def _validate_response(self, raw_text: str, response_schema: Type[T]) -> Union[T, dict[str, Any]]:
        """Helper to parse and validate JSON against the Pydantic schema."""
        try:
            # Clean up markdown code blocks if the model wrapped the JSON
            clean_text = raw_text.strip()
            if clean_text.startswith("```json"):
                clean_text = clean_text[7:]
            if clean_text.startswith("```"):
                clean_text = clean_text[3:]
            if clean_text.endswith("```"):
                clean_text = clean_text[:-3]
            clean_text = clean_text.strip()

            data = json.loads(clean_text)
            return response_schema.model_validate(data)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from LLM: {raw_text}")
            return {"error": "json_parse_error", "message": str(e), "raw": raw_text}
        except ValidationError as e:
            logger.error(f"Schema validation failed for LLM output: {e.errors()}")
            return {"error": "schema_validation_error", "message": str(e), "raw": raw_text}


class OllamaAdapter(LLMClientAdapter):
    """Adapter for local Ollama instances."""
    
    def __init__(self, model_name: str = "llama3"):
        self.base_url = settings.ollama_base_url.rstrip("/")
        self.model_name = model_name

    async def generate(self, text: str) -> str:
        """Backward-compatible raw generation helper."""
        url = f"{self.base_url}/api/generate"
        payload = {"model": self.model_name, "prompt": text, "stream": False}
        response = await _post_with_retry(url, json_body=payload)
        data = response.json()
        return data.get("response", "")

    async def execute_prompt(self, prompt: Prompt, response_schema: Type[T]) -> Union[T, dict[str, Any]]:
        url = f"{self.base_url}/api/generate"
        
        # Combine system and user prompt for Ollama
        full_prompt = f"{prompt.system}\n\n{prompt.xml_payload}\n\nIMPORTANT: Return ONLY valid JSON matching this schema:\n{json.dumps(response_schema.model_json_schema())}"
        
        payload = {
            "model": self.model_name,
            "prompt": full_prompt,
            "stream": False,
            "format": "json"  # Ask Ollama for JSON format
        }
        response = await _post_with_retry(url, json_body=payload)
        data = response.json()
        raw_text = data.get("response", "")

        # Best-effort token usage (Ollama includes these in some versions)
        self._last_prompt_tokens = data.get("prompt_eval_count")
        self._last_completion_tokens = data.get("eval_count")

        return self._validate_response(raw_text, response_schema)


class GeminiAdapter(LLMClientAdapter):
    """Adapter for Google AI Studio / Gemini REST API."""
    
    def __init__(self, model_name: str = "gemini-1.5-pro"):
        self.api_key = settings.google_api_key
        self.model_name = model_name
        self._last_prompt_tokens: int | None = None
        self._last_completion_tokens: int | None = None
        
        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY is not set in configuration.")

    async def generate(self, text: str) -> str:
        """Backward-compatible raw generation helper."""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent"
        params = {"key": self.api_key}
        payload = {"contents": [{"parts": [{"text": text}]}]}
        response = await _post_with_retry(url, params=params, json_body=payload)
        data = response.json()
        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError):
            return ""

    async def execute_prompt(self, prompt: Prompt, response_schema: Type[T]) -> Union[T, dict[str, Any]]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent"
        params = {"key": self.api_key}
        
        # Inject schema into the prompt to avoid 400 errors from unsupported JSON Schema features in responseSchema
        full_prompt = f"{prompt.xml_payload}\n\nIMPORTANT: Return ONLY valid JSON matching this schema:\n{json.dumps(response_schema.model_json_schema())}"

        payload = {
            "systemInstruction": {
                "parts": [{"text": prompt.system}]
            },
            "contents": [{
                "parts": [{"text": full_prompt}]
            }],
            "generationConfig": {
                "responseMimeType": "application/json"
            }
        }
        
        response = await _post_with_retry(url, params=params, json_body=payload)
        data = response.json()

        # Best-effort token usage tracking
        usage = data.get("usageMetadata") or {}
        self._last_prompt_tokens = usage.get("promptTokenCount")
        self._last_completion_tokens = usage.get("candidatesTokenCount")

        try:
            raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
            return self._validate_response(raw_text, response_schema)
        except (KeyError, IndexError):
            return {"error": "gemini_api_error", "message": "Unexpected response structure", "raw": json.dumps(data)}


def get_llm_client(task_type: Union[TaskType, str]) -> LLMClientAdapter:
    """
    Factory function to retrieve the appropriate LLM client for a given task type.
    Routing is determined by the task_routing config.
    """
    task_key = task_type.value if isinstance(task_type, TaskType) else str(task_type)
    provider = settings.task_routing.get(task_key, settings.task_routing.get("default", "gemini"))
    
    if provider == "ollama":
        return OllamaAdapter()
    elif provider == "gemini":
        # Use Flash model to avoid Free Tier Quota Limit of 0 on Pro
        model_name = "gemini-2.5-flash"
            
        return GeminiAdapter(model_name=model_name)
    else:
        raise ValueError(f"Unknown LLM provider '{provider}' configured for task '{task_key}'")
