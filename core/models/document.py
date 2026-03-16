"""
Data models for document parsing and extraction.

Defines models for parsed documents and extracted sections from PDDs.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ParsedDocument(BaseModel):
    """Represents a parsed Process Design Document (PDD)."""

    model_config = ConfigDict(frozen=False)

    source_path: str = Field(..., description="Absolute path to the original file")
    file_type: str = Field(..., description='File type: "pdf" or "docx"')
    full_text: str = Field(..., description="Complete extracted text content")
    tables: list[list[dict[str, Any]]] = Field(
        default_factory=list,
        description="List of tables, each table is a list of row dicts",
    )
    page_count: int = Field(..., description="Total number of pages")
    metadata: dict[str, str] = Field(
        default_factory=dict,
        description="File metadata (author, created, modified, etc.)",
    )
    extraction_warnings: list[str] = Field(
        default_factory=list, description="Non-fatal issues during extraction"
    )

    def word_count(self) -> int:
        """Return the word count of the document.

        Returns:
            Number of words in full_text
        """
        return len(self.full_text.split())

    def is_valid(self) -> bool:
        """Check if document is valid for processing.

        A document is valid if it has more than 100 words
        and at least one page.

        Returns:
            True if document meets minimum validity criteria
        """
        return self.word_count() > 100 and self.page_count > 0


class ExtractedSection(BaseModel):
    """Represents a section extracted from a document."""

    model_config = ConfigDict(frozen=False)

    title: str = Field(..., description="Section heading text")
    content: str = Field(..., description="Full text content of the section")
    page_number: int | None = Field(
        default=None, description="Page where section starts (None if unknown)"
    )
    confidence_score: float = Field(
        ..., description="Confidence 0.0-1.0 of extraction accuracy"
    )
    section_type: str = Field(
        ...,
        description='Type of section: "process_overview", "process_steps", '
        '"business_rules", "applications", "exceptions", "inputs_outputs", "general"',
    )

    @field_validator("confidence_score")
    @classmethod
    def validate_confidence_score(cls, v: float) -> float:
        """Validate confidence_score is between 0.0 and 1.0 inclusive.

        Args:
            v: Confidence score value

        Returns:
            The validated confidence score

        Raises:
            ValueError: If score is outside [0.0, 1.0]
        """
        if not (0.0 <= v <= 1.0):
            raise ValueError("confidence_score must be between 0.0 and 1.0")
        return v
