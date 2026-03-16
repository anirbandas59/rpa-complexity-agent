"""
LLMManager — Central orchestration layer for all LLM operations.

This module provides a single public interface for all LLM calls throughout
the project. It handles provider initialization, retry logic with exponential
backoff, and usage logging.

All agents and tools route LLM calls through this manager — nothing outside
llm/ ever imports a provider directly.
"""

import json
import logging
import os
import time
from functools import lru_cache
from typing import Any

from pydantic import BaseModel

from config.settings import get_settings
from core.exceptions import LLMProviderError
from llm.providers import BaseLLMProvider, LLMResponse
from llm.providers.anthropic_provider import AnthropicProvider
from llm.providers.ollama_provider import OllamaProvider
from llm.providers.openai_provider import OpenAIProvider
from llm.providers.watsonx_provider import WatsonxProvider


class LLMManager:
    """
    Central orchestration for all LLM operations.

    Handles provider initialization, retry logic with exponential backoff,
    and usage tracking. All agents and tools should use get_default_manager()
    to obtain a manager instance.
    """

    logger = logging.getLogger("rpa_agent.llm_manager")

    def __init__(
        self,
        provider_name: str | None = None,
        model_name: str | None = None,
    ):
        """
        Initialize LLMManager with specified or default provider.

        Args:
            provider_name: Provider to use (anthropic|openai|watsonx|ollama).
                If None, reads from settings.default_llm_provider.
            model_name: Model name for the provider.
                If None, reads from settings.default_llm_model.

        Raises:
            LLMProviderError: If provider_name is unknown.
            ValueError: If required API keys are missing (from settings validation).
        """
        settings = get_settings()

        # Use provided names or fall back to settings defaults
        self._provider_name = (
            provider_name.lower() if provider_name
            else settings.default_llm_provider.lower()
        )
        self._model_name = (
            model_name if model_name
            else settings.default_llm_model
        )

        # Initialize tracking
        self._call_count = 0
        self._total_tokens = 0

        # Build the provider
        self._provider = self._build_provider()

        self.logger.debug(
            f"LLMManager initialized | provider={self._provider_name} | "
            f"model={self._model_name}"
        )

    def _build_provider(self) -> BaseLLMProvider:
        """
        Build the correct provider instance based on provider name.

        Returns:
            BaseLLMProvider: Initialized provider instance.

        Raises:
            LLMProviderError: If provider_name is unknown.
        """
        settings = get_settings()
        provider_name = self._provider_name.lower()

        if provider_name == "anthropic":
            return AnthropicProvider(
                api_key=settings.anthropic_api_key,
                model=self._model_name,
            )

        elif provider_name == "openai":
            return OpenAIProvider(
                api_key=settings.openai_api_key,
                model=self._model_name,
            )

        elif provider_name == "watsonx":
            return WatsonxProvider(
                api_key=settings.watsonx_api_key,
                url=settings.watsonx_url,
                project_id=settings.watsonx_project_id,
            )

        elif provider_name == "ollama":
            return OllamaProvider(
                base_url=settings.ollama_base_url,
                model=self._model_name,
            )

        else:
            raise LLMProviderError(
                f"Unknown LLM provider: {self._provider_name}. Valid options: "
                "anthropic | openai | watsonx | ollama"
            )

    def _execute_with_retry(
        self,
        operation: callable,
        session_id: str = "",
    ) -> LLMResponse:
        """
        Execute LLM operation with exponential backoff retry logic.

        Retries only on rate limit errors (containing "rate" or "429").
        Other errors are raised immediately without retry.

        Args:
            operation: Callable that returns LLMResponse.
            session_id: Session ID for logging context.

        Returns:
            LLMResponse: Response from the provider.

        Raises:
            LLMProviderError: If all retries exhausted or non-rate-limit error.
        """
        settings = get_settings()
        max_retries = settings.llm_max_retries
        base_delay = settings.llm_retry_base_delay

        last_error = None

        for attempt in range(max_retries):
            try:
                result: LLMResponse = operation()

                # Success: log and update tracking
                self._call_count += 1
                self._total_tokens += result.total_tokens

                self.logger.debug(
                    f"LLM call #{self._call_count} | "
                    f"{result.provider} | {result.model} | "
                    f"{result.input_tokens}→{result.output_tokens} tokens | "
                    f"session={session_id}"
                )

                return result

            except LLMProviderError as e:
                error_msg = str(e).lower()
                is_rate_limit = "rate" in error_msg or "429" in error_msg

                if is_rate_limit and attempt < max_retries - 1:
                    # Rate limit: exponential backoff and retry
                    delay = base_delay * (2 ** attempt)
                    self.logger.warning(
                        f"Rate limited by {self._provider_name}, retrying in "
                        f"{delay}s (attempt {attempt + 1}/{max_retries})"
                    )
                    time.sleep(delay)
                    continue

                elif is_rate_limit:
                    # Rate limit on last attempt
                    last_error = e
                    break

                else:
                    # Non-rate-limit error: fail immediately
                    self.logger.error(f"LLM call failed: {e}")
                    raise

        # Exhausted retries on rate limit
        if last_error:
            raise last_error
        else:
            raise LLMProviderError(
                f"Failed to execute LLM operation after {max_retries} retries"
            )

    def complete(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int = 1000,
        session_id: str = "",
    ) -> str:
        """
        Execute a text completion request.

        Args:
            prompt: User prompt/query.
            system: System message (optional).
            max_tokens: Maximum tokens in response (default 1000).
            session_id: Session ID for logging (optional).

        Returns:
            str: Response text content only.

        Raises:
            LLMProviderError: If provider fails or all retries exhausted.
        """
        response = self._execute_with_retry(
            lambda: self._provider.complete(prompt, system, max_tokens),
            session_id,
        )
        return response.content

    def complete_structured(
        self,
        prompt: str,
        response_schema: type[BaseModel],
        system: str = "",
        max_tokens: int = 1000,
        session_id: str = "",
    ) -> BaseModel:
        """
        Execute a structured completion request that returns a Pydantic model.

        Structured calls do not use _execute_with_retry as they have
        their own internal validation/retry logic for JSON parsing.

        Args:
            prompt: User prompt/query.
            response_schema: Pydantic model class for response.
            system: System message (optional).
            max_tokens: Maximum tokens in response (default 1000).
            session_id: Session ID for logging (optional).

        Returns:
            BaseModel: Validated Pydantic model instance.

        Raises:
            LLMProviderError: If provider fails or JSON validation fails.
        """
        return self._provider.complete_structured(
            prompt,
            response_schema,
            system,
            max_tokens,
        )

    def get_provider_info(self) -> dict[str, str]:
        """
        Get information about the current provider and call statistics.

        Returns:
            dict: Keys: provider, model, call_count, total_tokens.
        """
        return {
            "provider": self._provider.get_provider_name(),
            "model": self._provider.get_model_name(),
            "call_count": str(self._call_count),
            "total_tokens": str(self._total_tokens),
        }

    def health_check(self) -> dict[str, bool | str]:
        """
        Check health of the configured provider.

        Returns:
            dict: Keys: provider, model, healthy (bool).
        """
        return {
            "provider": self._provider.get_provider_name(),
            "model": self._provider.get_model_name(),
            "healthy": self._provider.health_check(),
        }

    @classmethod
    def create_default(cls) -> "LLMManager":
        """
        Factory method to create manager with default settings.

        Returns:
            LLMManager: New instance using environment/settings defaults.
        """
        return cls()


# Module-level lazy singleton
_default_manager: LLMManager | None = None


def get_default_manager() -> LLMManager:
    """
    Get or create the default LLMManager singleton.

    The manager is only instantiated on first call (lazy initialization),
    not at module import time. This ensures environment variables and
    settings are fully loaded before the provider is built.

    Returns:
        LLMManager: Singleton instance.
    """
    global _default_manager
    if _default_manager is None:
        _default_manager = LLMManager.create_default()
    return _default_manager
