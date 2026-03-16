"""Ollama provider implementation using HTTP (no SDK)."""

from typing import Type

import httpx
from pydantic import BaseModel

from core.exceptions import LLMProviderError

from . import BaseLLMProvider, LLMResponse


class OllamaProvider(BaseLLMProvider):
    """LLM provider using local Ollama instance via HTTP."""

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3"):
        """Initialize the Ollama provider.

        Args:
            base_url: URL to Ollama instance (default: http://localhost:11434).
            model: Model name (default: llama3).
        """
        self.base_url = base_url
        self.model = model
        self.client = httpx.Client(timeout=60.0)

    def get_provider_name(self) -> str:
        """Return provider name."""
        return "ollama"

    def get_model_name(self) -> str:
        """Return configured model name."""
        return self.model

    def complete(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int = 1000,
    ) -> LLMResponse:
        """Send a completion request to Ollama.

        Args:
            prompt: User prompt.
            system: System prompt (optional).
            max_tokens: Max response tokens.

        Returns:
            LLMResponse with Ollama's response.

        Raises:
            LLMProviderError: On connection failure or API error.
        """
        try:
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})

            response = self.client.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": False,
                },
            )

            response_json = response.json()
            return LLMResponse(
                content=response_json["message"]["content"],
                model=self.model,
                provider=self.get_provider_name(),
                input_tokens=response_json.get("prompt_eval_count", 0),
                output_tokens=response_json.get("eval_count", 0),
                raw_response=response_json,
            )
        except httpx.ConnectError as e:
            raise LLMProviderError(
                f"Cannot connect to Ollama at {self.base_url}",
                context={"provider": "ollama"},
            ) from e
        except httpx.HTTPError as e:
            raise LLMProviderError(
                f"Ollama request failed — is Ollama running at {self.base_url}?",
                context={"provider": "ollama"},
            ) from e

    def complete_structured(
        self,
        prompt: str,
        response_schema: Type[BaseModel],
        system: str = "",
        max_tokens: int = 1000,
    ) -> BaseModel:
        """Get a structured JSON response from Ollama.

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
        """Check if Ollama is reachable.

        Returns:
            True if healthy, False otherwise.
        """
        try:
            response = self.client.get(f"{self.base_url}/api/tags")
            return response.status_code == 200
        except Exception:
            return False
