"""
Tests for LLMManager and settings configuration.

Uses unittest.mock to patch all dependencies — zero real API calls.
"""

from unittest.mock import Mock, patch

import pytest

from config.settings import get_settings
from core.exceptions import LLMProviderError
from llm.manager import LLMManager, get_default_manager
from llm.providers import LLMResponse

# ═════════════════════════════════════════════════════════════════
# Settings Tests
# ═════════════════════════════════════════════════════════════════


class TestSettings:
    """Test configuration settings loading and validation."""

    def test_settings_loads_with_anthropic_key(self):
        """Settings load successfully when anthropic key is set."""
        with patch.dict(
            "os.environ",
            {
                "ANTHROPIC_API_KEY": "sk-test-key",
                "DEFAULT_LLM_PROVIDER": "anthropic",
            },
        ):
            # Clear lru_cache to force reload
            get_settings.cache_clear()
            settings = get_settings()
            assert settings.anthropic_api_key == "sk-test-key"
            assert settings.default_llm_provider == "anthropic"

    def test_settings_requires_anthropic_key(self):
        """Settings raise ValueError if provider=anthropic but no key."""
        with patch.dict(
            "os.environ",
            {
                "ANTHROPIC_API_KEY": "",
                "DEFAULT_LLM_PROVIDER": "anthropic",
            },
            clear=True,
        ):
            get_settings.cache_clear()
            with pytest.raises(
                ValueError,
                match="ANTHROPIC_API_KEY is required",
            ):
                get_settings()

    def test_settings_requires_openai_key(self):
        """Settings raise ValueError if provider=openai but no key."""
        with patch.dict(
            "os.environ",
            {
                "OPENAI_API_KEY": "",
                "DEFAULT_LLM_PROVIDER": "openai",
            },
            clear=True,
        ):
            get_settings.cache_clear()
            with pytest.raises(
                ValueError,
                match="OPENAI_API_KEY is required",
            ):
                get_settings()

    def test_settings_requires_watsonx_key(self):
        """Settings raise ValueError if provider=watsonx but no key."""
        with patch.dict(
            "os.environ",
            {
                "WATSONX_API_KEY": "",
                "DEFAULT_LLM_PROVIDER": "watsonx",
            },
            clear=True,
        ):
            get_settings.cache_clear()
            with pytest.raises(
                ValueError,
                match="WATSONX_API_KEY and WATSONX_URL required",
            ):
                get_settings()

    def test_settings_accepts_ollama_without_keys(self):
        """Settings accept ollama provider without any API keys."""
        with patch.dict(
            "os.environ",
            {
                "DEFAULT_LLM_PROVIDER": "ollama",
            },
            clear=True,
        ):
            get_settings.cache_clear()
            settings = get_settings()
            assert settings.default_llm_provider == "ollama"

    def test_settings_caches_singleton(self):
        """get_settings() returns same instance on multiple calls."""
        get_settings.cache_clear()
        settings1 = get_settings()
        settings2 = get_settings()
        assert settings1 is settings2


# ═════════════════════════════════════════════════════════════════
# LLMManager Construction Tests
# ═════════════════════════════════════════════════════════════════


class TestLLMManagerConstruction:
    """Test LLMManager initialization and provider building."""

    @patch("llm.manager.get_settings")
    @patch("llm.manager.AnthropicProvider")
    def test_builds_anthropic_provider(
        self,
        mock_anthropic,
        mock_settings,
    ):
        """LLMManager builds AnthropicProvider correctly."""
        mock_settings_obj = Mock()
        mock_settings_obj.default_llm_provider = "anthropic"
        mock_settings_obj.default_llm_model = "claude-opus-4-6"
        mock_settings_obj.anthropic_api_key = "sk-test"
        mock_settings.return_value = mock_settings_obj

        manager = LLMManager(
            provider_name="anthropic",
            model_name="claude-opus-4-6",
        )

        mock_anthropic.assert_called_once_with(
            api_key="sk-test",
            model="claude-opus-4-6",
        )
        assert manager._provider_name == "anthropic"
        assert manager._model_name == "claude-opus-4-6"

    @patch("llm.manager.get_settings")
    @patch("llm.manager.OpenAIProvider")
    def test_builds_openai_provider(
        self,
        mock_openai,
        mock_settings,
    ):
        """LLMManager builds OpenAIProvider correctly."""
        mock_settings_obj = Mock()
        mock_settings_obj.default_llm_provider = "openai"
        mock_settings_obj.default_llm_model = "gpt-4"
        mock_settings_obj.openai_api_key = "sk-test"
        mock_settings.return_value = mock_settings_obj

        manager = LLMManager(
            provider_name="openai",
            model_name="gpt-4",
        )

        mock_openai.assert_called_once_with(
            api_key="sk-test",
            model="gpt-4",
        )
        assert manager._provider_name == "openai"

    @patch("llm.manager.get_settings")
    @patch("llm.manager.OllamaProvider")
    def test_builds_ollama_provider(
        self,
        mock_ollama,
        mock_settings,
    ):
        """LLMManager builds OllamaProvider correctly."""
        mock_settings_obj = Mock()
        mock_settings_obj.default_llm_provider = "ollama"
        mock_settings_obj.default_llm_model = "llama3"
        mock_settings_obj.ollama_base_url = "http://localhost:11434"
        mock_settings.return_value = mock_settings_obj

        LLMManager(
            provider_name="ollama",
            model_name="llama3",
        )

        mock_ollama.assert_called_once_with(
            base_url="http://localhost:11434",
            model="llama3",
        )

    @patch("llm.manager.get_settings")
    def test_raises_on_unknown_provider(self, mock_settings):
        """LLMManager raises LLMProviderError for unknown provider."""
        mock_settings_obj = Mock()
        mock_settings_obj.default_llm_provider = "anthropic"
        mock_settings_obj.default_llm_model = "claude"
        mock_settings.return_value = mock_settings_obj

        with pytest.raises(LLMProviderError, match="Unknown LLM provider"):
            LLMManager(provider_name="unknown_provider")

    @patch("llm.manager.get_settings")
    @patch("llm.manager.AnthropicProvider")
    def test_reads_defaults_from_settings(
        self,
        mock_anthropic,
        mock_settings,
    ):
        """LLMManager reads defaults from settings when no args given."""
        mock_settings_obj = Mock()
        mock_settings_obj.default_llm_provider = "anthropic"
        mock_settings_obj.default_llm_model = "claude-opus-4-6"
        mock_settings_obj.anthropic_api_key = "sk-test"
        mock_settings.return_value = mock_settings_obj

        # No arguments to LLMManager
        manager = LLMManager()

        assert manager._provider_name == "anthropic"
        assert manager._model_name == "claude-opus-4-6"


# ═════════════════════════════════════════════════════════════════
# complete() Method Tests
# ═════════════════════════════════════════════════════════════════


class TestLLMManagerComplete:
    """Test LLMManager.complete() method."""

    @patch("llm.manager.get_settings")
    @patch("llm.manager.AnthropicProvider")
    def test_complete_returns_string(
        self,
        mock_provider_class,
        mock_settings,
    ):
        """complete() returns string content (not LLMResponse)."""
        mock_settings_obj = Mock()
        mock_settings_obj.default_llm_provider = "anthropic"
        mock_settings_obj.default_llm_model = "claude"
        mock_settings_obj.anthropic_api_key = "sk-test"
        mock_settings_obj.llm_max_retries = 3
        mock_settings_obj.llm_retry_base_delay = 1.0
        mock_settings.return_value = mock_settings_obj

        mock_response = LLMResponse(
            content="test response",
            model="claude",
            provider="anthropic",
            input_tokens=10,
            output_tokens=20,
            raw_response={},
        )

        mock_provider = Mock()
        mock_provider.complete.return_value = mock_response
        mock_provider_class.return_value = mock_provider

        manager = LLMManager()
        result = manager.complete("test prompt")

        assert isinstance(result, str)
        assert result == "test response"

    @patch("llm.manager.get_settings")
    @patch("llm.manager.AnthropicProvider")
    def test_complete_increments_call_count(
        self,
        mock_provider_class,
        mock_settings,
    ):
        """complete() increments _call_count after success."""
        mock_settings_obj = Mock()
        mock_settings_obj.default_llm_provider = "anthropic"
        mock_settings_obj.default_llm_model = "claude"
        mock_settings_obj.anthropic_api_key = "sk-test"
        mock_settings_obj.llm_max_retries = 3
        mock_settings_obj.llm_retry_base_delay = 1.0
        mock_settings.return_value = mock_settings_obj

        mock_response = LLMResponse(
            content="response",
            model="claude",
            provider="anthropic",
            input_tokens=10,
            output_tokens=20,
            raw_response={},
        )

        mock_provider = Mock()
        mock_provider.complete.return_value = mock_response
        mock_provider_class.return_value = mock_provider

        manager = LLMManager()
        assert manager._call_count == 0

        manager.complete("prompt 1")
        assert manager._call_count == 1

        manager.complete("prompt 2")
        assert manager._call_count == 2

    @patch("llm.manager.get_settings")
    @patch("llm.manager.AnthropicProvider")
    def test_complete_increments_total_tokens(
        self,
        mock_provider_class,
        mock_settings,
    ):
        """complete() increments _total_tokens after success."""
        mock_settings_obj = Mock()
        mock_settings_obj.default_llm_provider = "anthropic"
        mock_settings_obj.default_llm_model = "claude"
        mock_settings_obj.anthropic_api_key = "sk-test"
        mock_settings_obj.llm_max_retries = 3
        mock_settings_obj.llm_retry_base_delay = 1.0
        mock_settings.return_value = mock_settings_obj

        mock_response1 = LLMResponse(
            content="response1",
            model="claude",
            provider="anthropic",
            input_tokens=10,
            output_tokens=20,
            raw_response={},
        )
        mock_response2 = LLMResponse(
            content="response2",
            model="claude",
            provider="anthropic",
            input_tokens=15,
            output_tokens=25,
            raw_response={},
        )

        mock_provider = Mock()
        mock_provider.complete.side_effect = [mock_response1, mock_response2]
        mock_provider_class.return_value = mock_provider

        manager = LLMManager()
        assert manager._total_tokens == 0

        manager.complete("prompt 1")
        assert manager._total_tokens == 30  # 10 + 20

        manager.complete("prompt 2")
        assert manager._total_tokens == 70  # 30 + 15 + 25

    @patch("llm.manager.get_settings")
    @patch("llm.manager.AnthropicProvider")
    def test_complete_retries_on_rate_limit(
        self,
        mock_provider_class,
        mock_settings,
    ):
        """complete() retries on rate limit error."""
        mock_settings_obj = Mock()
        mock_settings_obj.default_llm_provider = "anthropic"
        mock_settings_obj.default_llm_model = "claude"
        mock_settings_obj.anthropic_api_key = "sk-test"
        mock_settings_obj.llm_max_retries = 3
        mock_settings_obj.llm_retry_base_delay = 0.01  # short delay for tests
        mock_settings.return_value = mock_settings_obj

        mock_success_response = LLMResponse(
            content="success",
            model="claude",
            provider="anthropic",
            input_tokens=10,
            output_tokens=20,
            raw_response={},
        )

        mock_provider = Mock()
        # Fail twice with rate limit, succeed third time
        mock_provider.complete.side_effect = [
            LLMProviderError("rate limit exceeded"),
            LLMProviderError("429 too many requests"),
            mock_success_response,
        ]
        mock_provider_class.return_value = mock_provider

        manager = LLMManager()

        with patch("time.sleep"):  # Skip actual sleep
            result = manager.complete("prompt")

        assert result == "success"
        assert mock_provider.complete.call_count == 3

    @patch("llm.manager.get_settings")
    @patch("llm.manager.AnthropicProvider")
    def test_complete_no_retry_on_non_rate_limit_error(
        self,
        mock_provider_class,
        mock_settings,
    ):
        """complete() does NOT retry on non-rate-limit errors."""
        mock_settings_obj = Mock()
        mock_settings_obj.default_llm_provider = "anthropic"
        mock_settings_obj.default_llm_model = "claude"
        mock_settings_obj.anthropic_api_key = "sk-test"
        mock_settings_obj.llm_max_retries = 3
        mock_settings_obj.llm_retry_base_delay = 1.0
        mock_settings.return_value = mock_settings_obj

        mock_provider = Mock()
        mock_provider.complete.side_effect = LLMProviderError("authentication failed")
        mock_provider_class.return_value = mock_provider

        manager = LLMManager()

        with pytest.raises(LLMProviderError, match="authentication failed"):
            manager.complete("prompt")

        # Should fail immediately, not retry
        assert mock_provider.complete.call_count == 1

    @patch("llm.manager.get_settings")
    @patch("llm.manager.AnthropicProvider")
    def test_complete_raises_after_max_retries(
        self,
        mock_provider_class,
        mock_settings,
    ):
        """complete() raises after exhausting all retries."""
        mock_settings_obj = Mock()
        mock_settings_obj.default_llm_provider = "anthropic"
        mock_settings_obj.default_llm_model = "claude"
        mock_settings_obj.anthropic_api_key = "sk-test"
        mock_settings_obj.llm_max_retries = 3
        mock_settings_obj.llm_retry_base_delay = 0.01
        mock_settings.return_value = mock_settings_obj

        mock_provider = Mock()
        mock_provider.complete.side_effect = LLMProviderError("rate limit exceeded")
        mock_provider_class.return_value = mock_provider

        manager = LLMManager()

        with patch("time.sleep"):
            with pytest.raises(LLMProviderError, match="rate limit exceeded"):
                manager.complete("prompt")

        # Should try max_retries times (3)
        assert mock_provider.complete.call_count == 3


# ═════════════════════════════════════════════════════════════════
# Exponential Backoff Tests
# ═════════════════════════════════════════════════════════════════


class TestExponentialBackoff:
    """Test exponential backoff retry logic."""

    @patch("llm.manager.get_settings")
    @patch("llm.manager.AnthropicProvider")
    @patch("time.sleep")
    def test_exponential_backoff_delays(
        self,
        mock_sleep,
        mock_provider_class,
        mock_settings,
    ):
        """Exponential backoff delay doubles each attempt."""
        mock_settings_obj = Mock()
        mock_settings_obj.default_llm_provider = "anthropic"
        mock_settings_obj.default_llm_model = "claude"
        mock_settings_obj.anthropic_api_key = "sk-test"
        mock_settings_obj.llm_max_retries = 3
        mock_settings_obj.llm_retry_base_delay = 1.0
        mock_settings.return_value = mock_settings_obj

        mock_success = LLMResponse(
            content="success",
            model="claude",
            provider="anthropic",
            input_tokens=10,
            output_tokens=20,
            raw_response={},
        )

        mock_provider = Mock()
        mock_provider.complete.side_effect = [
            LLMProviderError("rate limit"),
            LLMProviderError("rate limit"),
            mock_success,
        ]
        mock_provider_class.return_value = mock_provider

        manager = LLMManager()
        manager.complete("prompt")

        # Check sleep was called with exponential backoff
        # Attempt 0: delay = 1.0 * 2^0 = 1.0
        # Attempt 1: delay = 1.0 * 2^1 = 2.0
        assert mock_sleep.call_count == 2
        assert mock_sleep.call_args_list[0][0][0] == 1.0
        assert mock_sleep.call_args_list[1][0][0] == 2.0


# ═════════════════════════════════════════════════════════════════
# get_provider_info() Tests
# ═════════════════════════════════════════════════════════════════


class TestGetProviderInfo:
    """Test get_provider_info() method."""

    @patch("llm.manager.get_settings")
    @patch("llm.manager.AnthropicProvider")
    def test_provider_info_structure(
        self,
        mock_provider_class,
        mock_settings,
    ):
        """get_provider_info() returns dict with expected keys."""
        mock_settings_obj = Mock()
        mock_settings_obj.default_llm_provider = "anthropic"
        mock_settings_obj.default_llm_model = "claude"
        mock_settings_obj.anthropic_api_key = "sk-test"
        mock_settings_obj.llm_max_retries = 3
        mock_settings_obj.llm_retry_base_delay = 1.0
        mock_settings.return_value = mock_settings_obj

        mock_provider = Mock()
        mock_provider.get_provider_name.return_value = "anthropic"
        mock_provider.get_model_name.return_value = "claude-opus-4-6"
        mock_provider_class.return_value = mock_provider

        manager = LLMManager()
        info = manager.get_provider_info()

        assert "provider" in info
        assert "model" in info
        assert "call_count" in info
        assert "total_tokens" in info
        assert info["provider"] == "anthropic"
        assert info["model"] == "claude-opus-4-6"
        assert info["call_count"] == "0"
        assert info["total_tokens"] == "0"

    @patch("llm.manager.get_settings")
    @patch("llm.manager.AnthropicProvider")
    def test_provider_info_call_count_increments(
        self,
        mock_provider_class,
        mock_settings,
    ):
        """call_count increments correctly in get_provider_info()."""
        mock_settings_obj = Mock()
        mock_settings_obj.default_llm_provider = "anthropic"
        mock_settings_obj.default_llm_model = "claude"
        mock_settings_obj.anthropic_api_key = "sk-test"
        mock_settings_obj.llm_max_retries = 3
        mock_settings_obj.llm_retry_base_delay = 1.0
        mock_settings.return_value = mock_settings_obj

        mock_response = LLMResponse(
            content="response",
            model="claude",
            provider="anthropic",
            input_tokens=10,
            output_tokens=20,
            raw_response={},
        )

        mock_provider = Mock()
        mock_provider.complete.return_value = mock_response
        mock_provider.get_provider_name.return_value = "anthropic"
        mock_provider.get_model_name.return_value = "claude"
        mock_provider_class.return_value = mock_provider

        manager = LLMManager()
        manager.complete("prompt 1")
        manager.complete("prompt 2")

        info = manager.get_provider_info()
        assert info["call_count"] == "2"
        assert info["total_tokens"] == "60"  # (10+20) * 2


# ═════════════════════════════════════════════════════════════════
# health_check() Tests
# ═════════════════════════════════════════════════════════════════


class TestHealthCheck:
    """Test health_check() method."""

    @patch("llm.manager.get_settings")
    @patch("llm.manager.AnthropicProvider")
    def test_health_check_structure(
        self,
        mock_provider_class,
        mock_settings,
    ):
        """health_check() returns dict with expected keys."""
        mock_settings_obj = Mock()
        mock_settings_obj.default_llm_provider = "anthropic"
        mock_settings_obj.default_llm_model = "claude"
        mock_settings_obj.anthropic_api_key = "sk-test"
        mock_settings.return_value = mock_settings_obj

        mock_provider = Mock()
        mock_provider.get_provider_name.return_value = "anthropic"
        mock_provider.get_model_name.return_value = "claude"
        mock_provider.health_check.return_value = True
        mock_provider_class.return_value = mock_provider

        manager = LLMManager()
        health = manager.health_check()

        assert "provider" in health
        assert "model" in health
        assert "healthy" in health
        assert health["provider"] == "anthropic"
        assert health["model"] == "claude"
        assert health["healthy"] is True

    @patch("llm.manager.get_settings")
    @patch("llm.manager.AnthropicProvider")
    def test_health_check_healthy_false(
        self,
        mock_provider_class,
        mock_settings,
    ):
        """health_check() returns healthy=False when provider unhealthy."""
        mock_settings_obj = Mock()
        mock_settings_obj.default_llm_provider = "anthropic"
        mock_settings_obj.default_llm_model = "claude"
        mock_settings_obj.anthropic_api_key = "sk-test"
        mock_settings.return_value = mock_settings_obj

        mock_provider = Mock()
        mock_provider.get_provider_name.return_value = "anthropic"
        mock_provider.get_model_name.return_value = "claude"
        mock_provider.health_check.return_value = False
        mock_provider_class.return_value = mock_provider

        manager = LLMManager()
        health = manager.health_check()

        assert health["healthy"] is False


# ═════════════════════════════════════════════════════════════════
# get_default_manager() Singleton Tests
# ═════════════════════════════════════════════════════════════════


class TestGetDefaultManager:
    """Test get_default_manager() singleton function."""

    @patch("llm.manager.get_settings")
    @patch("llm.manager.AnthropicProvider")
    def test_returns_llm_manager_instance(
        self,
        mock_provider_class,
        mock_settings,
    ):
        """get_default_manager() returns LLMManager instance."""
        mock_settings_obj = Mock()
        mock_settings_obj.default_llm_provider = "anthropic"
        mock_settings_obj.default_llm_model = "claude"
        mock_settings_obj.anthropic_api_key = "sk-test"
        mock_settings.return_value = mock_settings_obj

        mock_provider_class.return_value = Mock()

        manager = get_default_manager()
        assert isinstance(manager, LLMManager)

    @patch("llm.manager.get_settings")
    @patch("llm.manager.AnthropicProvider")
    def test_returns_same_instance_on_multiple_calls(
        self,
        mock_provider_class,
        mock_settings,
    ):
        """get_default_manager() returns SAME instance on second call."""
        mock_settings_obj = Mock()
        mock_settings_obj.default_llm_provider = "anthropic"
        mock_settings_obj.default_llm_model = "claude"
        mock_settings_obj.anthropic_api_key = "sk-test"
        mock_settings.return_value = mock_settings_obj

        mock_provider_class.return_value = Mock()

        # Reset the global singleton
        import llm.manager as mgr_module

        mgr_module._default_manager = None

        manager1 = get_default_manager()
        manager2 = get_default_manager()

        assert manager1 is manager2

    @patch("llm.manager.get_settings")
    @patch("llm.manager.AnthropicProvider")
    def test_create_default_factory_method(
        self,
        mock_provider_class,
        mock_settings,
    ):
        """LLMManager.create_default() factory method works."""
        mock_settings_obj = Mock()
        mock_settings_obj.default_llm_provider = "anthropic"
        mock_settings_obj.default_llm_model = "claude"
        mock_settings_obj.anthropic_api_key = "sk-test"
        mock_settings.return_value = mock_settings_obj

        mock_provider_class.return_value = Mock()

        manager = LLMManager.create_default()
        assert isinstance(manager, LLMManager)
