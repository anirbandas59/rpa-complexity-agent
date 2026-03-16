"""Anthropic provider implementation using the anthropic SDK."""

from typing import Type

import anthropic
from pydantic import BaseModel

from core.exceptions import LLMProviderError

from . import BaseLLMProvider, LLMResponse


class AnthropicProvider(BaseLLMProvider):
    """LLM provider using Anthropic's Claude models."""

    def __init__(self, api_key: str, model: str):
        """Initialize the Anthropic provider.

        Args:
            api_key: Anthropic API key.
            model: Model name (e.g. "claude-sonnet-4-5").
        """
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def get_provider_name(self) -> str:
        """Return provider name."""
        return "anthropic"

    def get_model_name(self) -> str:
        """Return configured model name."""
        return self.model

    def complete(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int = 1000,
    ) -> LLMResponse:
        """Send a completion request to Claude.

        Args:
            prompt: User prompt.
            system: System prompt (optional).
            max_tokens: Max response tokens.

        Returns:
            LLMResponse with Claude's response.

        Raises:
            LLMProviderError: On API failure.
        """
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system if system else None,
                messages=[{"role": "user", "content": prompt}],
            )

            return LLMResponse(
                content=response.content[0].text,
                model=self.model,
                provider=self.get_provider_name(),
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                raw_response=response.model_dump() if hasattr(response, 'model_dump') else {},
            )
        except anthropic.AuthenticationError as e:
            raise LLMProviderError(
                "Anthropic authentication failed — check ANTHROPIC_API_KEY",
                context={"provider": "anthropic"},
            ) from e
        except anthropic.APIError as e:
            raise LLMProviderError(
                str(e),
                context={"provider": "anthropic"},
            ) from e

    def complete_structured(
        self,
        prompt: str,
        response_schema: Type[BaseModel],
        system: str = "",
        max_tokens: int = 1000,
    ) -> BaseModel:
        """Get a structured JSON response from Claude.

        Args:
            prompt: User prompt.
            response_schema: Pydantic model for expected output.
            system: System prompt (optional).
            max_tokens: Max response tokens.

        Returns:
            Validated model instance.

        Raises:
            LLMProviderError: On API failure or validation error.
        """
        system_prompt = self.build_json_system_prompt(system, response_schema)
        response = self.complete(prompt, system_prompt, max_tokens)
        return self.parse_json_response(response.content, response_schema)

    def health_check(self) -> bool:
        """Check if Anthropic API is reachable.

        Returns:
            True if healthy, False otherwise.
        """
        try:
            self.client.messages.create(
                model=self.model,
                max_tokens=10,
                messages=[{"role": "user", "content": "ping"}],
            )
            return True
        except Exception:
            return False
