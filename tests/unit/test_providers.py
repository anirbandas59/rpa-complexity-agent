"""Tests for LLM provider abstraction layer."""

import json
from unittest import mock
from unittest.mock import MagicMock, patch

import httpx
import pytest
from pydantic import BaseModel, Field

from core.exceptions import LLMProviderError
from llm.providers import BaseLLMProvider, LLMResponse
from llm.providers.anthropic_provider import AnthropicProvider
from llm.providers.ollama_provider import OllamaProvider
from llm.providers.openai_provider import OpenAIProvider
from llm.providers.watsonx_provider import WatsonxProvider


# ============================================================================
# Test Models
# ============================================================================


class SimpleResponse(BaseModel):
    """Simple test response model."""

    name: str = Field(..., description="The name")
    age: int = Field(..., description="The age")


class StubProvider(BaseLLMProvider):
    """Concrete stub implementation for testing BaseLLMProvider."""

    def get_provider_name(self) -> str:
        return "stub"

    def get_model_name(self) -> str:
        return "test-model"

    def complete(self, prompt: str, system: str = "", max_tokens: int = 1000) -> LLMResponse:
        return LLMResponse(
            content="test response",
            model="test-model",
            provider="stub",
            input_tokens=10,
            output_tokens=5,
            raw_response={},
        )

    def complete_structured(
        self, prompt: str, response_schema, system: str = "", max_tokens: int = 1000
    ):
        return response_schema(name="test", age=25)

    def health_check(self) -> bool:
        return True


# ============================================================================
# LLMResponse Tests
# ============================================================================


class TestLLMResponse:
    """Test LLMResponse model."""

    def test_instantiate_with_all_fields(self):
        """Test creating LLMResponse with all fields."""
        response = LLMResponse(
            content="test",
            model="gpt-4",
            provider="openai",
            input_tokens=100,
            output_tokens=50,
            raw_response={"usage": {}},
        )
        assert response.content == "test"
        assert response.model == "gpt-4"
        assert response.provider == "openai"

    def test_total_tokens_computed_property(self):
        """Test total_tokens is correctly computed."""
        response = LLMResponse(
            content="test",
            model="gpt-4",
            provider="openai",
            input_tokens=100,
            output_tokens=50,
            raw_response={},
        )
        assert response.total_tokens == 150


# ============================================================================
# BaseLLMProvider Tests
# ============================================================================


class TestBaseLLMProvider:
    """Test BaseLLMProvider abstract base class."""

    def test_cannot_instantiate_abstract_class(self):
        """Test that BaseLLMProvider cannot be instantiated directly."""
        with pytest.raises(TypeError):
            BaseLLMProvider()

    def test_stub_provider_instantiates(self):
        """Test that concrete implementations can be instantiated."""
        provider = StubProvider()
        assert provider.get_provider_name() == "stub"
        assert provider.get_model_name() == "test-model"

    def test_build_json_system_prompt_with_base(self):
        """Test building JSON system prompt with base prompt."""
        provider = StubProvider()
        result = provider.build_json_system_prompt("Base instructions", SimpleResponse)
        assert "Base instructions" in result
        assert "Respond with valid JSON only" in result
        assert "Do not include markdown code blocks" in result
        assert "name" in result
        assert "age" in result

    def test_build_json_system_prompt_without_base(self):
        """Test building JSON system prompt without base prompt."""
        provider = StubProvider()
        result = provider.build_json_system_prompt("", SimpleResponse)
        assert "Respond with valid JSON only" in result
        assert "name" in result
        assert "age" in result

    def test_parse_json_response_valid(self):
        """Test parsing valid JSON response."""
        provider = StubProvider()
        json_str = '{"name": "Alice", "age": 30}'
        result = provider.parse_json_response(json_str, SimpleResponse)
        assert result.name == "Alice"
        assert result.age == 30

    def test_parse_json_response_with_markdown_fences(self):
        """Test stripping markdown code fences before parsing."""
        provider = StubProvider()
        json_str = '```json\n{"name": "Bob", "age": 25}\n```'
        result = provider.parse_json_response(json_str, SimpleResponse)
        assert result.name == "Bob"
        assert result.age == 25

    def test_parse_json_response_invalid_json(self):
        """Test error handling for invalid JSON."""
        provider = StubProvider()
        with pytest.raises(LLMProviderError) as exc_info:
            provider.parse_json_response('{"invalid": json}', SimpleResponse)
        assert "LLM returned invalid JSON" in str(exc_info.value)

    def test_parse_json_response_schema_validation_error(self):
        """Test error handling for schema mismatch."""
        provider = StubProvider()
        json_str = '{"name": "Charlie"}'  # Missing required 'age' field
        with pytest.raises(LLMProviderError) as exc_info:
            provider.parse_json_response(json_str, SimpleResponse)
        assert "failed schema validation" in str(exc_info.value)


# ============================================================================
# AnthropicProvider Tests
# ============================================================================


class TestAnthropicProvider:
    """Test AnthropicProvider implementation."""

    @patch("llm.providers.anthropic_provider.anthropic.Anthropic")
    def test_instantiate_without_api_call(self, mock_anthropic):
        """Test AnthropicProvider instantiation without making API calls."""
        provider = AnthropicProvider("test-key", "claude-sonnet")
        assert provider.model == "claude-sonnet"
        assert provider.get_provider_name() == "anthropic"
        assert provider.get_model_name() == "claude-sonnet"
        # Verify no API calls were made during instantiation
        mock_anthropic.return_value.messages.create.assert_not_called()

    @patch("llm.providers.anthropic_provider.anthropic.Anthropic")
    def test_complete_maps_response_fields(self, mock_anthropic):
        """Test complete() correctly maps Anthropic response to LLMResponse."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Hello")]
        mock_response.usage.input_tokens = 50
        mock_response.usage.output_tokens = 25
        mock_response.model_dump.return_value = {"usage": {"input_tokens": 50}}

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        provider = AnthropicProvider("test-key", "claude-sonnet")
        result = provider.complete("test prompt", "system", 500)

        assert result.content == "Hello"
        assert result.model == "claude-sonnet"
        assert result.provider == "anthropic"
        assert result.input_tokens == 50
        assert result.output_tokens == 25

    @patch("llm.providers.anthropic_provider.anthropic.Anthropic")
    def test_complete_handles_authentication_error(self, mock_anthropic):
        """Test complete() handles AuthenticationError."""
        # Create a real exception class to raise
        class MockAuthError(Exception):
            pass

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = MockAuthError("Invalid key")
        mock_anthropic.return_value = mock_client

        # Patch the exception class in the provider module
        with patch("llm.providers.anthropic_provider.anthropic.AuthenticationError", MockAuthError):
            provider = AnthropicProvider("bad-key", "claude-sonnet")
            with pytest.raises(LLMProviderError):
                provider.complete("test")

    @patch("llm.providers.anthropic_provider.anthropic.Anthropic")
    def test_complete_structured_calls_parse_json_response(self, mock_anthropic):
        """Test complete_structured() uses parse_json_response."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='{"name": "Alice", "age": 30}')]
        mock_response.usage.input_tokens = 50
        mock_response.usage.output_tokens = 30
        mock_response.model_dump.return_value = {}

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        provider = AnthropicProvider("test-key", "claude-sonnet")
        result = provider.complete_structured("test prompt", SimpleResponse)

        assert isinstance(result, SimpleResponse)
        assert result.name == "Alice"
        assert result.age == 30

    @patch("llm.providers.anthropic_provider.anthropic.Anthropic")
    def test_health_check_returns_true_on_success(self, mock_anthropic):
        """Test health_check() returns True when API is reachable."""
        mock_client = MagicMock()
        mock_client.messages.create.return_value = MagicMock()
        mock_anthropic.return_value = mock_client

        provider = AnthropicProvider("test-key", "claude-sonnet")
        assert provider.health_check() is True

    @patch("llm.providers.anthropic_provider.anthropic.Anthropic")
    def test_health_check_returns_false_on_error(self, mock_anthropic):
        """Test health_check() returns False on error."""
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("Connection error")
        mock_anthropic.return_value = mock_client

        provider = AnthropicProvider("test-key", "claude-sonnet")
        assert provider.health_check() is False


# ============================================================================
# OpenAIProvider Tests
# ============================================================================


class TestOpenAIProvider:
    """Test OpenAIProvider implementation."""

    @patch("llm.providers.openai_provider.openai.OpenAI")
    def test_instantiate_without_api_call(self, mock_openai):
        """Test OpenAIProvider instantiation without making API calls."""
        provider = OpenAIProvider("test-key", "gpt-4")
        assert provider.model == "gpt-4"
        assert provider.get_provider_name() == "openai"
        assert provider.get_model_name() == "gpt-4"

    @patch("llm.providers.openai_provider.openai.OpenAI")
    def test_complete_builds_messages_with_system(self, mock_openai):
        """Test complete() builds correct message list with system prompt."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Response"))]
        mock_response.usage.prompt_tokens = 50
        mock_response.usage.completion_tokens = 25
        mock_response.model_dump.return_value = {}

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client

        provider = OpenAIProvider("test-key", "gpt-4")
        provider.complete("test prompt", system="Be helpful", max_tokens=500)

        # Verify messages were built correctly
        call_args = mock_client.chat.completions.create.call_args
        messages = call_args.kwargs["messages"]
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"

    @patch("llm.providers.openai_provider.openai.OpenAI")
    def test_complete_builds_messages_without_system(self, mock_openai):
        """Test complete() builds correct message list without system prompt."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Response"))]
        mock_response.usage.prompt_tokens = 50
        mock_response.usage.completion_tokens = 25
        mock_response.model_dump.return_value = {}

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client

        provider = OpenAIProvider("test-key", "gpt-4")
        provider.complete("test prompt", max_tokens=500)

        # Verify messages were built correctly
        call_args = mock_client.chat.completions.create.call_args
        messages = call_args.kwargs["messages"]
        assert len(messages) == 1
        assert messages[0]["role"] == "user"

    @patch("llm.providers.openai_provider.openai.OpenAI")
    def test_complete_maps_response_fields(self, mock_openai):
        """Test complete() correctly maps OpenAI response to LLMResponse."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Response text"))]
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 50
        mock_response.model_dump.return_value = {}

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client

        provider = OpenAIProvider("test-key", "gpt-4")
        result = provider.complete("test")

        assert result.content == "Response text"
        assert result.input_tokens == 100
        assert result.output_tokens == 50

    @patch("llm.providers.openai_provider.openai.OpenAI")
    def test_health_check_returns_false_on_error(self, mock_openai):
        """Test health_check() returns False on error."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("Connection error")
        mock_openai.return_value = mock_client

        provider = OpenAIProvider("test-key", "gpt-4")
        assert provider.health_check() is False


# ============================================================================
# WatsonxProvider Tests
# ============================================================================


class TestWatsonxProvider:
    """Test WatsonxProvider stub implementation."""

    def test_complete_raises_not_implemented(self):
        """Test complete() raises NotImplementedError."""
        provider = WatsonxProvider("key", "url", "project")
        with pytest.raises(NotImplementedError):
            provider.complete("test")

    def test_complete_structured_raises_not_implemented(self):
        """Test complete_structured() raises NotImplementedError."""
        provider = WatsonxProvider("key", "url", "project")
        with pytest.raises(NotImplementedError):
            provider.complete_structured("test", SimpleResponse)

    def test_health_check_raises_not_implemented(self):
        """Test health_check() raises NotImplementedError."""
        provider = WatsonxProvider("key", "url", "project")
        with pytest.raises(NotImplementedError):
            provider.health_check()


# ============================================================================
# OllamaProvider Tests
# ============================================================================


class TestOllamaProvider:
    """Test OllamaProvider implementation."""

    def test_instantiate_with_defaults(self):
        """Test OllamaProvider instantiation with default parameters."""
        provider = OllamaProvider()
        assert provider.base_url == "http://localhost:11434"
        assert provider.model == "llama3"
        assert provider.get_provider_name() == "ollama"
        assert provider.get_model_name() == "llama3"

    def test_instantiate_with_custom_params(self):
        """Test OllamaProvider instantiation with custom parameters."""
        provider = OllamaProvider("http://example.com:11434", "llama2")
        assert provider.base_url == "http://example.com:11434"
        assert provider.model == "llama2"

    @patch("llm.providers.ollama_provider.httpx.Client")
    def test_complete_builds_correct_post_body_with_system(self, mock_httpx):
        """Test complete() builds correct request body with system prompt."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "message": {"content": "Response"},
            "prompt_eval_count": 50,
            "eval_count": 25,
        }

        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_httpx.return_value = mock_client

        provider = OllamaProvider()
        provider.complete("test prompt", system="Be helpful")

        # Verify POST request was made with correct body
        call_args = mock_client.post.call_args
        body = call_args.kwargs["json"]
        assert body["model"] == "llama3"
        assert body["stream"] is False
        assert len(body["messages"]) == 2
        assert body["messages"][0]["role"] == "system"
        assert body["messages"][1]["role"] == "user"

    @patch("llm.providers.ollama_provider.httpx.Client")
    def test_complete_raises_on_connect_error(self, mock_httpx):
        """Test complete() raises LLMProviderError on ConnectError."""
        mock_client = MagicMock()
        mock_client.post.side_effect = httpx.ConnectError("Connection refused")
        mock_httpx.return_value = mock_client

        provider = OllamaProvider()
        with pytest.raises(LLMProviderError) as exc_info:
            provider.complete("test")
        assert "Cannot connect to Ollama" in str(exc_info.value)

    @patch("llm.providers.ollama_provider.httpx.Client")
    def test_health_check_returns_true_on_success(self, mock_httpx):
        """Test health_check() returns True on successful connection."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_httpx.return_value = mock_client

        provider = OllamaProvider()
        assert provider.health_check() is True

    @patch("llm.providers.ollama_provider.httpx.Client")
    def test_health_check_returns_false_on_error(self, mock_httpx):
        """Test health_check() returns False on connection error."""
        mock_client = MagicMock()
        mock_client.get.side_effect = Exception("Connection error")
        mock_httpx.return_value = mock_client

        provider = OllamaProvider()
        assert provider.health_check() is False

    @patch("llm.providers.ollama_provider.httpx.Client")
    def test_health_check_never_raises(self, mock_httpx):
        """Test health_check() never raises exceptions."""
        mock_client = MagicMock()
        mock_client.get.side_effect = RuntimeError("Unexpected error")
        mock_httpx.return_value = mock_client

        provider = OllamaProvider()
        # Should not raise, should return False
        result = provider.health_check()
        assert result is False
