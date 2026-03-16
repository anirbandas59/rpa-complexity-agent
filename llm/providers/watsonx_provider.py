"""Watsonx provider stub implementation.

Watsonx is not yet functional in this environment. The ibm_watsonx_ai
library is available in the mamba environment but not in the project venv.
This stub raises NotImplementedError to indicate the provider is not configured.
"""

from typing import Type

from pydantic import BaseModel

from . import BaseLLMProvider, LLMResponse


class WatsonxProvider(BaseLLMProvider):
    """Stub LLM provider for IBM Watsonx (not yet configured)."""

    def __init__(self, api_key: str, url: str, project_id: str):
        """Initialize the Watsonx provider stub.

        Args:
            api_key: IBM API key.
            url: Watsonx API URL.
            project_id: IBM Cloud project ID.
        """
        self.api_key = api_key
        self.url = url
        self.project_id = project_id

    def get_provider_name(self) -> str:
        """Return provider name."""
        return "watsonx"

    def get_model_name(self) -> str:
        """Return default model name."""
        return "ibm/granite-13b-chat-v2"

    def complete(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int = 1000,
    ) -> LLMResponse:
        """Not implemented for Watsonx."""
        raise NotImplementedError(
            "WatsonxProvider is not yet configured. Install ibm-watsonx-ai "
            "and configure credentials. See docs/watsonx_setup.md."
        )

    def complete_structured(
        self,
        prompt: str,
        response_schema: Type[BaseModel],
        system: str = "",
        max_tokens: int = 1000,
    ) -> BaseModel:
        """Not implemented for Watsonx."""
        raise NotImplementedError(
            "WatsonxProvider is not yet configured. Install ibm-watsonx-ai "
            "and configure credentials. See docs/watsonx_setup.md."
        )

    def health_check(self) -> bool:
        """Not implemented for Watsonx."""
        raise NotImplementedError(
            "WatsonxProvider is not yet configured. Install ibm-watsonx-ai "
            "and configure credentials. See docs/watsonx_setup.md."
        )
