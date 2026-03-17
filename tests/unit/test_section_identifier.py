"""Tests for tools.document.section_identifier module.

Tests cover pattern matching, LLM fallback, merging, and orchestration.
No real API calls — all LLM paths are mocked.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.models.document import ExtractedSection, ParsedDocument
from llm.manager import LLMManager
from tools.document.prompts import SECTION_IDENTIFICATION_SYSTEM
from tools.document.section_identifier import (
    SectionResponse,
    SectionsListResponse,
    identify_sections,
    identify_sections_by_llm,
    identify_sections_by_pattern,
)
from tools.document.pdf_parser import parse_pdf
from tools.document.docx_parser import parse_docx


# ==================== FIXTURES ====================


@pytest.fixture
def sample_simple_pdf() -> Path:
    """Path to sample_simple.pdf test fixture."""
    path = Path(__file__).parent.parent.parent / "data" / "sample_pdds" / "sample_simple.pdf"
    assert path.exists()
    return path


@pytest.fixture
def sample_process_docx() -> Path:
    """Path to sample_process.docx test fixture."""
    path = Path(__file__).parent.parent.parent / "data" / "sample_pdds" / "sample_process.docx"
    assert path.exists()
    return path


@pytest.fixture
def document_with_headings() -> ParsedDocument:
    """Create a ParsedDocument with DOCX-style headings."""
    full_text = """
=== Process Overview ===
This is the process overview section. It describes what the
process does and why it's important.

--- Process Steps ---
This is the process steps section. It lists all the steps
that are automated in this process.

--- Business Rules ---
This is the business rules section. It contains the decision
points and validations.
"""
    return ParsedDocument(
        source_path="/test/document.docx",
        file_type="docx",
        full_text=full_text,
        tables=[],
        page_count=1,
        metadata={},
        extraction_warnings=[],
    )


@pytest.fixture
def document_with_page_markers() -> ParsedDocument:
    """Create a ParsedDocument with PDF-style page markers."""
    full_text = """
--- Page 1 ---
=== Process Overview ===
Overview text here.

--- Page 2 ---
=== Process Steps ===
Steps text here.
"""
    return ParsedDocument(
        source_path="/test/document.pdf",
        file_type="pdf",
        full_text=full_text,
        tables=[],
        page_count=2,
        metadata={},
        extraction_warnings=[],
    )


@pytest.fixture
def document_without_headings() -> ParsedDocument:
    """Create a ParsedDocument without structural markers."""
    full_text = """
This is a plain document with no heading markers.
It has multiple paragraphs but no structural information
that would allow pattern matching to work.
Just plain text throughout.
"""
    return ParsedDocument(
        source_path="/test/document.docx",
        file_type="docx",
        full_text=full_text,
        tables=[],
        page_count=1,
        metadata={},
        extraction_warnings=[],
    )


# ==================== PATTERN MATCHING TESTS ====================


def test_pattern_matching_finds_headings(document_with_headings: ParsedDocument):
    """Test pattern matching identifies DOCX-style headings."""
    sections = identify_sections_by_pattern(document_with_headings)
    assert len(sections) >= 2
    assert any(s.title == "Process Overview" for s in sections)


def test_pattern_matching_identifies_section_types(document_with_headings: ParsedDocument):
    """Test pattern matching correctly identifies section types."""
    sections = identify_sections_by_pattern(document_with_headings)
    types_found = {s.section_type for s in sections}
    assert "process_overview" in types_found or "process_steps" in types_found


def test_pattern_matching_assigns_confidence(document_with_headings: ParsedDocument):
    """Test pattern matching assigns confidence scores."""
    sections = identify_sections_by_pattern(document_with_headings)
    assert all(0.0 <= s.confidence_score <= 1.0 for s in sections)
    # Pattern matches should have high confidence
    assert any(s.confidence_score > 0.8 for s in sections)


def test_pattern_matching_extracts_page_numbers(document_with_page_markers: ParsedDocument):
    """Test pattern matching extracts page numbers from PDF markers."""
    sections = identify_sections_by_pattern(document_with_page_markers)
    # At least one section should have a page number
    assert any(s.page_number is not None for s in sections)


def test_pattern_matching_handles_unstructured_headings():
    """Test pattern matching finds capitalized lines as headings."""
    full_text = """
PROCESS OVERVIEW
This is an overview section with body text.

BUSINESS RULES
This is the rules section.
"""
    doc = ParsedDocument(
        source_path="/test/doc.txt",
        file_type="txt",
        full_text=full_text,
        tables=[],
        page_count=1,
        metadata={},
        extraction_warnings=[],
    )
    sections = identify_sections_by_pattern(doc)
    # Should find at least one section from capitalized headings
    assert len(sections) >= 1


def test_pattern_matching_returns_empty_for_no_headings(document_without_headings: ParsedDocument):
    """Test pattern matching returns empty list for unstructured documents."""
    sections = identify_sections_by_pattern(document_without_headings)
    assert sections == []


def test_pattern_matching_returns_extracted_section_objects(
    document_with_headings: ParsedDocument,
):
    """Test pattern matching returns ExtractedSection instances."""
    sections = identify_sections_by_pattern(document_with_headings)
    assert all(isinstance(s, ExtractedSection) for s in sections)


# ==================== LLM FALLBACK TESTS ====================


def test_llm_fallback_returns_sections():
    """Test LLM fallback returns ExtractedSection list."""
    doc = ParsedDocument(
        source_path="/test/doc.docx",
        file_type="docx",
        full_text="Some document text",
        tables=[],
        page_count=1,
        metadata={},
        extraction_warnings=[],
    )

    # Mock LLMManager
    mock_manager = MagicMock(spec=LLMManager)
    mock_manager.complete_structured.return_value = SectionsListResponse(
        sections=[
            SectionResponse(
                title="Overview",
                section_type="process_overview",
                content="Overview content",
                confidence_score=0.9,
                page_number=None,
            )
        ]
    )

    sections = identify_sections_by_llm(doc, mock_manager)

    assert len(sections) == 1
    assert sections[0].title == "Overview"
    assert sections[0].section_type == "process_overview"


def test_llm_fallback_validates_section_types():
    """Test LLM fallback remaps invalid section types to 'general'."""
    doc = ParsedDocument(
        source_path="/test/doc.docx",
        file_type="docx",
        full_text="Some document text",
        tables=[],
        page_count=1,
        metadata={},
        extraction_warnings=[],
    )

    mock_manager = MagicMock(spec=LLMManager)
    mock_manager.complete_structured.return_value = SectionsListResponse(
        sections=[
            SectionResponse(
                title="Unknown",
                section_type="invalid_type",
                content="Content",
                confidence_score=0.8,
                page_number=None,
            )
        ]
    )

    sections = identify_sections_by_llm(doc, mock_manager)

    assert sections[0].section_type == "general"


def test_llm_fallback_clamps_confidence_score():
    """Test LLM fallback clamps confidence_score to 0.0-1.0."""
    doc = ParsedDocument(
        source_path="/test/doc.docx",
        file_type="docx",
        full_text="Some document text",
        tables=[],
        page_count=1,
        metadata={},
        extraction_warnings=[],
    )

    mock_manager = MagicMock(spec=LLMManager)
    mock_manager.complete_structured.return_value = SectionsListResponse(
        sections=[
            SectionResponse(
                title="Test",
                section_type="general",
                content="Content",
                confidence_score=1.5,  # Out of range
                page_number=None,
            )
        ]
    )

    sections = identify_sections_by_llm(doc, mock_manager)

    assert sections[0].confidence_score == 1.0


def test_llm_fallback_handles_error_gracefully():
    """Test LLM fallback returns empty list on error."""
    from core.exceptions import LLMProviderError

    doc = ParsedDocument(
        source_path="/test/doc.docx",
        file_type="docx",
        full_text="Some document text",
        tables=[],
        page_count=1,
        metadata={},
        extraction_warnings=[],
    )

    mock_manager = MagicMock(spec=LLMManager)
    mock_manager.complete_structured.side_effect = LLMProviderError(
        message="API Error", context={}
    )

    sections = identify_sections_by_llm(doc, mock_manager)

    assert sections == []


# ==================== ORCHESTRATION TESTS ====================


def test_orchestration_skips_llm_when_pattern_finds_enough(
    document_with_headings: ParsedDocument,
):
    """Test orchestration skips LLM when pattern finds >= 3 sections."""
    mock_manager = MagicMock(spec=LLMManager)

    sections = identify_sections(document_with_headings, mock_manager)

    # If pattern found enough sections, LLM should not be called
    if len(sections) >= 3:
        mock_manager.complete_structured.assert_not_called()


def test_orchestration_calls_llm_when_pattern_insufficient(
    document_without_headings: ParsedDocument,
):
    """Test orchestration calls LLM when pattern finds < 3 sections."""
    mock_manager = MagicMock(spec=LLMManager)
    mock_manager.complete_structured.return_value = SectionsListResponse(
        sections=[
            SectionResponse(
                title="Overview",
                section_type="process_overview",
                content="Content",
                confidence_score=0.8,
                page_number=None,
            )
        ]
    )

    sections = identify_sections(document_without_headings, mock_manager)

    # Pattern matching returns 0 sections, so LLM should be called
    mock_manager.complete_structured.assert_called_once()


def test_orchestration_creates_default_llm_manager():
    """Test orchestration creates LLMManager if not provided."""
    doc = ParsedDocument(
        source_path="/test/doc.docx",
        file_type="docx",
        full_text="Document without patterns",
        tables=[],
        page_count=1,
        metadata={},
        extraction_warnings=[],
    )

    with patch("tools.document.section_identifier.LLMManager") as mock_llm_class:
        mock_manager = MagicMock()
        mock_manager.complete_structured.return_value = SectionsListResponse(sections=[])
        mock_llm_class.create_default.return_value = mock_manager

        sections = identify_sections(doc, llm_manager=None)

        # Should create default manager when none provided and needed
        mock_llm_class.create_default.assert_called_once()


def test_orchestration_merges_without_duplicates(document_with_headings: ParsedDocument):
    """Test orchestration merges pattern and LLM sections without duplicates."""
    mock_manager = MagicMock(spec=LLMManager)
    # LLM returns a section with same title as pattern match
    mock_manager.complete_structured.return_value = SectionsListResponse(
        sections=[
            SectionResponse(
                title="Process Overview",  # Same as pattern match
                section_type="process_overview",
                content="LLM content",
                confidence_score=0.7,
                page_number=None,
            )
        ]
    )

    sections = identify_sections(document_with_headings, mock_manager)

    # Should not have duplicates
    titles = [s.title for s in sections]
    assert len(titles) == len(set(titles))


def test_orchestration_fallback_to_full_document(document_without_headings: ParsedDocument):
    """Test orchestration returns catch-all section when nothing found."""
    mock_manager = MagicMock(spec=LLMManager)
    mock_manager.complete_structured.return_value = SectionsListResponse(sections=[])

    sections = identify_sections(document_without_headings, mock_manager)

    # Should return at least one catch-all section
    assert len(sections) == 1
    assert sections[0].title == "Full Document"
    assert sections[0].section_type == "general"
    assert sections[0].confidence_score == 0.1


def test_orchestration_sorts_sections_by_appearance(document_with_headings: ParsedDocument):
    """Test orchestration sorts sections by appearance in document."""
    sections = identify_sections(document_with_headings)

    if len(sections) > 1:
        # Sections should be in order of appearance
        positions = []
        for section in sections:
            pos = document_with_headings.full_text.find(section.title)
            if pos >= 0:
                positions.append(pos)

        # Positions should be in ascending order
        assert positions == sorted(positions)


# ==================== INTEGRATION TESTS ====================


def test_integration_with_docx_fixture(sample_process_docx: Path):
    """Test section identification with real DOCX document."""
    doc = parse_docx(str(sample_process_docx))
    sections = identify_sections(doc)

    # sample_process.docx has multiple sections
    assert len(sections) >= 3

    # At least one section should not be "general"
    assert any(s.section_type != "general" for s in sections)

    # All should be ExtractedSection
    assert all(isinstance(s, ExtractedSection) for s in sections)


def test_integration_with_pdf_fixture(sample_simple_pdf: Path):
    """Test section identification with real PDF document."""
    doc = parse_pdf(str(sample_simple_pdf))
    sections = identify_sections(doc)

    # sample_simple.pdf has content, should find at least 1 section
    assert len(sections) >= 1

    # All should be ExtractedSection
    assert all(isinstance(s, ExtractedSection) for s in sections)


# ==================== SCHEMA TESTS ====================


def test_section_response_schema():
    """Test SectionResponse pydantic schema."""
    section = SectionResponse(
        title="Test",
        section_type="process_overview",
        content="Content",
        confidence_score=0.9,
        page_number=1,
    )
    assert section.title == "Test"
    assert section.confidence_score == 0.9


def test_sections_list_response_schema():
    """Test SectionsListResponse pydantic schema."""
    response = SectionsListResponse(
        sections=[
            SectionResponse(
                title="Test",
                section_type="process_overview",
                content="Content",
                confidence_score=0.9,
                page_number=None,
            )
        ]
    )
    assert len(response.sections) == 1
    assert response.sections[0].title == "Test"


def test_sections_list_response_schema_empty():
    """Test SectionsListResponse with empty sections."""
    response = SectionsListResponse(sections=[])
    assert response.sections == []
