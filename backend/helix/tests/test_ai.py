import asyncio
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from helix.ai import get_llm_client
from helix.ai.llm import OllamaAdapter, GeminiAdapter
from helix.config import settings

def test_llm_factory_routing():
    """Test that the factory routes correctly based on task types."""
    # Temporarily override settings for test
    original_routing = settings.task_routing
    settings.task_routing = {
        "test_task_gemini": "gemini",
        "test_task_ollama": "ollama",
        "default": "gemini"
    }
    settings.google_api_key = "dummy_key"

    try:
        # Test specific explicit routing
        client_gemini = get_llm_client("test_task_gemini")
        assert isinstance(client_gemini, GeminiAdapter)

        client_ollama = get_llm_client("test_task_ollama")
        assert isinstance(client_ollama, OllamaAdapter)

        # Test default fallback
        client_default = get_llm_client("unknown_task")
        assert isinstance(client_default, GeminiAdapter)

    finally:
        # Restore settings
        settings.task_routing = original_routing


def test_gemini_adapter_missing_key():
    """Test Gemini adapter raises error if no key is set."""
    original_key = settings.google_api_key
    settings.google_api_key = ""
    try:
        with pytest.raises(ValueError, match="GOOGLE_API_KEY is not set"):
            GeminiAdapter()
    finally:
        settings.google_api_key = original_key


def test_ollama_generate_mocked():
    """Test successful generation using Ollama adapter with mocked HTTP response."""
    adapter = OllamaAdapter(model_name="llama3")
    
    # Mock _post_with_retry
    mock_response = MagicMock()
    mock_response.json.return_value = {"response": "This is a local response"}
    mock_response.status_code = 200

    with patch("helix.ai.llm._post_with_retry", new=AsyncMock(return_value=mock_response)) as mock_post:
        result = asyncio.run(adapter.generate("Hello local"))
        assert result == "This is a local response"
        mock_post.assert_called_once()


def test_gemini_generate_mocked():
    """Test successful generation using Gemini adapter with mocked HTTP response."""
    original_key = settings.google_api_key
    settings.google_api_key = "test_key"
    try:
        adapter = GeminiAdapter(model_name="gemini-1.5-pro")
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": "This is a cloud response"}]
                    }
                }
            ]
        }

        with patch("helix.ai.llm._post_with_retry", new=AsyncMock(return_value=mock_response)) as mock_post:
            result = asyncio.run(adapter.generate("Hello cloud"))
            assert result == "This is a cloud response"
            mock_post.assert_called_once()
    finally:
        settings.google_api_key = original_key
