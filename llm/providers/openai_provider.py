"""OpenAI provider implementation using the openai SDK."""

from typing import Type

import openai
from pydantic import BaseModel

from core.exceptions import LLMProviderError

from . import BaseLLMProvider, LLMResponse


class OpenAIProvider(BaseLLMProvider):
    """LLM provider using OpenAI's GPT models."""

    def __init__(self, api_key: str, model: str):
        """Initialize the OpenAI provider.

        Args:
            api_key: OpenAI API key.
            model: Model name (e.g. "gpt-4o").
        """
        self.client = openai.OpenAI(api_key=api_key)
        self.model = model

    def get_provider_name(self) -> str:
        """Return provider name."""
        return "openai"

    def get_model_name(self) -> str:
        """Return configured model name."""
        return self.model

    def complete(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int = 1000,
    ) -> LLMResponse:
        """Send a completion request to OpenAI.

        Args:
            prompt: User prompt.
            system: System prompt (optional).
            max_tokens: Max response tokens.

        Returns:
            LLMResponse with OpenAI's response.

        Raises:
            LLMProviderError: On API failure.
        """
        try:
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})

            response = self.client.chat.completions.create(
                model=self.model,
                max_tokens=max_tokens,
                messages=messages,
            )

            return LLMResponse(
                content=response.choices[0].message.content,
                model=self.model,
                provider=self.get_provider_name(),
                input_tokens=response.usage.prompt_tokens,
                output_tokens=response.usage.completion_tokens,
                raw_response=(
                    response.model_dump() if hasattr(response, "model_dump") else {}
                ),
            )
        except openai.AuthenticationError as e:
            raise LLMProviderError(
                "OpenAI authentication failed — check OPENAI_API_KEY",
                context={"provider": "openai"},
            ) from e
        except openai.APIError as e:
            raise LLMProviderError(
                str(e),
                context={"provider": "openai"},
            ) from e

    def complete_structured(
        self,
        prompt: str,
        response_schema: Type[BaseModel],
        system: str = "",
        max_tokens: int = 1000,
    ) -> BaseModel:
        """Get a structured JSON response from OpenAI.

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
        """Check if OpenAI API is reachable.

        Returns:
            True if healthy, False otherwise.
        """
        try:
            self.client.chat.completions.create(
                model=self.model,
                max_tokens=10,
                messages=[{"role": "user", "content": "ping"}],
            )
            return True
        except Exception:
            return False
