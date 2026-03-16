"""LLM provider abstraction layer.

This module defines the abstract base class and response model for LLM providers.
All concrete provider implementations inherit from BaseLLMProvider.

IMPORTANT: This is the ONLY place in the project where LLM SDKs can be imported.
Agents and tools MUST ONLY import from llm.manager, never directly from SDK modules.
"""

import json
from abc import ABC, abstractmethod
from typing import Any, Type

from pydantic import BaseModel, computed_field

from core.exceptions import LLMProviderError


class LLMResponse(BaseModel):
    """Response from an LLM provider.

    Attributes:
        content: The text response from the LLM.
        model: Model name that was used (e.g. "claude-sonnet-4-5").
        provider: Provider name (e.g. "anthropic", "openai").
        input_tokens: Number of tokens in the prompt.
        output_tokens: Number of tokens in the response.
        raw_response: Full raw API response as a dict.
    """

    content: str
    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    raw_response: dict[str, Any]

    @computed_field
    @property
    def total_tokens(self) -> int:
        """Total tokens consumed (input + output)."""
        return self.input_tokens + self.output_tokens


class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers.

    All LLM providers (Anthropic, OpenAI, Watsonx, Ollama) inherit from this
    and implement the abstract methods. This ensures a consistent interface
    across different LLM services.
    """

    @abstractmethod
    def get_provider_name(self) -> str:
        """Return the provider identifier.

        Returns:
            Provider name string (e.g. "anthropic", "openai", "watsonx", "ollama").
        """
        pass

    @abstractmethod
    def get_model_name(self) -> str:
        """Return the currently configured model identifier.

        Returns:
            Model name string (e.g. "claude-sonnet-4-5", "gpt-4o").
        """
        pass

    @abstractmethod
    def complete(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int = 1000,
    ) -> LLMResponse:
        """Send a completion request to the LLM.

        Args:
            prompt: The user prompt to send.
            system: Optional system prompt to guide the model.
            max_tokens: Maximum tokens in the response.

        Returns:
            LLMResponse with the model's reply and token usage.

        Raises:
            LLMProviderError: On any API failure or network error.
        """
        pass

    @abstractmethod
    def complete_structured(
        self,
        prompt: str,
        response_schema: Type[BaseModel],
        system: str = "",
        max_tokens: int = 1000,
    ) -> BaseModel:
        """Send a completion request expecting structured JSON output.

        Args:
            prompt: The user prompt to send.
            response_schema: Pydantic BaseModel class defining the expected output shape.
            system: Optional system prompt.
            max_tokens: Maximum tokens in the response.

        Returns:
            Validated instance of response_schema.

        Raises:
            LLMProviderError: If the response is invalid JSON or fails schema validation.
        """
        pass

    @abstractmethod
    def health_check(self) -> bool:
        """Check if the provider is reachable and authenticated.

        Returns:
            True if healthy, False if unreachable or invalid credentials.
            Never raises an exception.
        """
        pass

    def build_json_system_prompt(
        self,
        base_system: str,
        schema: Type[BaseModel],
    ) -> str:
        """Build a system prompt instructing the model to output valid JSON.

        Args:
            base_system: The initial system prompt (may be empty).
            schema: Pydantic model defining the expected JSON structure.

        Returns:
            Enhanced system prompt with JSON formatting instructions and field names.
        """
        field_names = ", ".join(schema.model_fields.keys())
        json_instructions = f"""
Respond with valid JSON only.
Do not include markdown code blocks (no ```json or ```).
Do not include any text outside the JSON object.
The JSON must contain these fields: {field_names}
"""
        if base_system:
            return base_system + "\n" + json_instructions
        return json_instructions

    def parse_json_response(
        self,
        response_text: str,
        schema: Type[BaseModel],
    ) -> BaseModel:
        """Parse and validate a JSON response against a schema.

        Strips markdown code fences (```json, ```) from the response.
        Parses JSON and validates against the provided Pydantic schema.

        Args:
            response_text: The raw text response from the LLM.
            schema: Pydantic model to validate against.

        Returns:
            Validated model instance.

        Raises:
            LLMProviderError: If JSON is invalid or fails schema validation.
        """
        # Strip markdown code fences
        cleaned = response_text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        # Parse JSON
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as e:
            raise LLMProviderError(
                "LLM returned invalid JSON",
                context={"raw_response": response_text[:500]},
            ) from e

        # Validate against schema
        try:
            return schema.model_validate(data)
        except Exception as e:
            raise LLMProviderError(
                "LLM response failed schema validation",
                context={"errors": str(e)},
            ) from e
