"""LLM provider abstraction layer.

This package provides a unified interface to multiple LLM providers:
- Anthropic Claude
- OpenAI GPT
- IBM Watsonx (stub)
- Local Ollama

IMPORTANT: SDKs are imported only within provider modules.
Agents and tools MUST use llm.manager to access providers.
"""

from llm.manager import LLMManager, get_default_manager
from llm.providers import BaseLLMProvider, LLMResponse

__all__ = [
    "LLMManager",
    "get_default_manager",
    "BaseLLMProvider",
    "LLMResponse",
]
