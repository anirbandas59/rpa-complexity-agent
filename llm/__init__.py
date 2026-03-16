"""LLM provider abstraction layer.

This package provides a unified interface to multiple LLM providers:
- Anthropic Claude
- OpenAI GPT
- IBM Watsonx (stub)
- Local Ollama

IMPORTANT: SDKs are imported only within provider modules.
Agents and tools MUST use llm.manager to access providers.
"""
