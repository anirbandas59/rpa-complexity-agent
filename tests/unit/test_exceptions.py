"""
Tests for core exception hierarchy.

Verifies that all exceptions are properly defined, can be raised/caught,
and provide correct message and context information.
"""

import pytest

from core.exceptions import (
    AgentExecutionError,
    DocumentProcessingError,
    LLMProviderError,
    OutputGenerationError,
    RPAAgentError,
    ScoringValidationError,
)


class TestRPAAgentError:
    """Tests for base RPAAgentError exception."""

    def test_can_raise_base_exception(self):
        """Verify base exception can be raised."""
        with pytest.raises(RPAAgentError):
            raise RPAAgentError("Test error")

    def test_message_attribute(self):
        """Verify message is stored as attribute."""
        error = RPAAgentError("Test message")
        assert error.message == "Test message"

    def test_context_attribute_default(self):
        """Verify context defaults to empty dict."""
        error = RPAAgentError("Test error")
        assert error.context == {}

    def test_context_attribute_provided(self):
        """Verify context is stored when provided."""
        context = {"file": "test.pdf", "line": 42}
        error = RPAAgentError("Test error", context=context)
        assert error.context == context

    def test_str_without_context(self):
        """Verify str() without context."""
        error = RPAAgentError("Test message")
        assert str(error) == "RPAAgentError: Test message"

    def test_str_with_context(self):
        """Verify str() includes context when present."""
        error = RPAAgentError("Test message", context={"key": "value"})
        error_str = str(error)
        assert "RPAAgentError" in error_str
        assert "Test message" in error_str
        assert "key=value" in error_str or "key" in error_str and "value" in error_str


class TestDocumentProcessingError:
    """Tests for DocumentProcessingError."""

    def test_can_raise_specific_exception(self):
        """Verify DocumentProcessingError can be raised."""
        with pytest.raises(DocumentProcessingError):
            raise DocumentProcessingError("PDF parsing failed")

    def test_can_catch_as_base_exception(self):
        """Verify can be caught as RPAAgentError."""
        with pytest.raises(RPAAgentError):
            raise DocumentProcessingError("PDF parsing failed")

    def test_message_preserved(self):
        """Verify message is preserved."""
        msg = "Failed to extract text from PDF"
        error = DocumentProcessingError(msg)
        assert error.message == msg

    def test_context_preserved(self):
        """Verify context is preserved."""
        context = {"file": "document.pdf"}
        error = DocumentProcessingError("Error", context=context)
        assert error.context == context

    def test_str_representation(self):
        """Verify string representation."""
        error = DocumentProcessingError("PDF error")
        assert "DocumentProcessingError" in str(error)
        assert "PDF error" in str(error)


class TestScoringValidationError:
    """Tests for ScoringValidationError."""

    def test_can_raise_specific_exception(self):
        """Verify ScoringValidationError can be raised."""
        with pytest.raises(ScoringValidationError):
            raise ScoringValidationError("Invalid score")

    def test_can_catch_as_base_exception(self):
        """Verify can be caught as RPAAgentError."""
        with pytest.raises(RPAAgentError):
            raise ScoringValidationError("Invalid score")

    def test_message_preserved(self):
        """Verify message is preserved."""
        msg = "Score out of valid range"
        error = ScoringValidationError(msg)
        assert error.message == msg

    def test_context_preserved(self):
        """Verify context is preserved."""
        context = {"score": 99, "valid_max": 28}
        error = ScoringValidationError("Score too high", context=context)
        assert error.context == context

    def test_str_representation(self):
        """Verify string representation."""
        error = ScoringValidationError("Invalid weight")
        assert "ScoringValidationError" in str(error)
        assert "Invalid weight" in str(error)


class TestLLMProviderError:
    """Tests for LLMProviderError."""

    def test_can_raise_specific_exception(self):
        """Verify LLMProviderError can be raised."""
        with pytest.raises(LLMProviderError):
            raise LLMProviderError("API timeout")

    def test_can_catch_as_base_exception(self):
        """Verify can be caught as RPAAgentError."""
        with pytest.raises(RPAAgentError):
            raise LLMProviderError("API timeout")

    def test_message_preserved(self):
        """Verify message is preserved."""
        msg = "Authentication failed"
        error = LLMProviderError(msg)
        assert error.message == msg

    def test_context_preserved(self):
        """Verify context is preserved."""
        context = {"provider": "openai", "status_code": 401}
        error = LLMProviderError("Auth error", context=context)
        assert error.context == context

    def test_str_representation(self):
        """Verify string representation."""
        error = LLMProviderError("Connection failed")
        assert "LLMProviderError" in str(error)
        assert "Connection failed" in str(error)


class TestAgentExecutionError:
    """Tests for AgentExecutionError."""

    def test_can_raise_specific_exception(self):
        """Verify AgentExecutionError can be raised."""
        with pytest.raises(AgentExecutionError):
            raise AgentExecutionError("Node failed")

    def test_can_catch_as_base_exception(self):
        """Verify can be caught as RPAAgentError."""
        with pytest.raises(RPAAgentError):
            raise AgentExecutionError("Node failed")

    def test_message_preserved(self):
        """Verify message is preserved."""
        msg = "State transition failed"
        error = AgentExecutionError(msg)
        assert error.message == msg

    def test_context_preserved(self):
        """Verify context is preserved."""
        context = {"node": "classify", "state": "incomplete"}
        error = AgentExecutionError("Execution failed", context=context)
        assert error.context == context

    def test_str_representation(self):
        """Verify string representation."""
        error = AgentExecutionError("Graph traversal failed")
        assert "AgentExecutionError" in str(error)
        assert "Graph traversal failed" in str(error)


class TestOutputGenerationError:
    """Tests for OutputGenerationError."""

    def test_can_raise_specific_exception(self):
        """Verify OutputGenerationError can be raised."""
        with pytest.raises(OutputGenerationError):
            raise OutputGenerationError("Excel generation failed")

    def test_can_catch_as_base_exception(self):
        """Verify can be caught as RPAAgentError."""
        with pytest.raises(RPAAgentError):
            raise OutputGenerationError("Excel generation failed")

    def test_message_preserved(self):
        """Verify message is preserved."""
        msg = "PDF generation failed"
        error = OutputGenerationError(msg)
        assert error.message == msg

    def test_context_preserved(self):
        """Verify context is preserved."""
        context = {"format": "xlsx", "reason": "corrupted_worksheet"}
        error = OutputGenerationError("Generation error", context=context)
        assert error.context == context

    def test_str_representation(self):
        """Verify string representation."""
        error = OutputGenerationError("PDF render error")
        assert "OutputGenerationError" in str(error)
        assert "PDF render error" in str(error)


class TestExceptionHierarchy:
    """Tests for overall exception hierarchy."""

    def test_all_specific_exceptions_inherit_from_base(self):
        """Verify all specific exceptions inherit from RPAAgentError."""
        exceptions = [
            DocumentProcessingError("test"),
            ScoringValidationError("test"),
            LLMProviderError("test"),
            AgentExecutionError("test"),
            OutputGenerationError("test"),
        ]

        for exc in exceptions:
            assert isinstance(exc, RPAAgentError)

    def test_can_catch_all_with_base_exception(self):
        """Verify all specific exceptions can be caught with base exception."""
        exceptions = [
            DocumentProcessingError("test"),
            ScoringValidationError("test"),
            LLMProviderError("test"),
            AgentExecutionError("test"),
            OutputGenerationError("test"),
        ]

        for exc in exceptions:
            with pytest.raises(RPAAgentError):
                raise exc

    def test_multiple_context_items_in_str(self):
        """Verify multiple context items are included in str()."""
        context = {"a": 1, "b": 2, "c": 3}
        error = RPAAgentError("Multi context", context=context)
        error_str = str(error)

        assert "RPAAgentError" in error_str
        assert "Multi context" in error_str
        # All context items should be present
        for key, val in context.items():
            assert f"{key}={val}" in error_str or (key in error_str and str(val) in error_str)
