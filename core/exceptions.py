"""
Typed exception hierarchy for RPA Complexity Assessment Agent.

All exceptions accept a message and optional context dict,
and provide formatted string representations.
"""

from typing import Any


class RPAAgentError(Exception):
    """Base exception for all project errors."""

    def __init__(self, message: str, context: dict[str, Any] | None = None):
        """Initialize exception with message and optional context.

        Args:
            message: Human-readable error description
            context: Optional dict with additional context information
        """
        self.message = message
        self.context = context or {}
        super().__init__(message)

    def __str__(self) -> str:
        """Return formatted string representation."""
        class_name = self.__class__.__name__
        if self.context:
            context_str = ", ".join(f"{k}={v}" for k, v in self.context.items())
            return f"{class_name}: {self.message} ({context_str})"
        return f"{class_name}: {self.message}"


class DocumentProcessingError(RPAAgentError):
    """Raised when file parsing, OCR, or extraction fails."""

    pass


class ScoringValidationError(RPAAgentError):
    """Raised when scores are invalid or out of acceptable range."""

    pass


class LLMProviderError(RPAAgentError):
    """Raised when LLM API calls fail (auth, timeout, etc)."""

    pass


class AgentExecutionError(RPAAgentError):
    """Raised when LangGraph nodes or state transitions fail."""

    pass


class OutputGenerationError(RPAAgentError):
    """Raised when Excel or PDF generation fails."""

    pass
