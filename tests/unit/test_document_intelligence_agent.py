"""Tests for agents.document_intelligence.agent module.

Tests cover state definition, node functions, routing logic,
graph compilation, and end-to-end agent execution.
Unit tests mock all tools. Integration test uses real files and LLM.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from agents.document_intelligence.agent import (
    DocumentIntelligenceState,
    extract_document_entities,
    identify_document_sections,
    ingest_document,
    run,
    should_continue,
    validate_output,
)
from core.exceptions import AgentExecutionError
from core.models.document import ExtractedSection, ParsedDocument
from tools.document.entity_extractor import (
    ApplicationEntity,
    ConfidenceScores,
    EntityExtractionResponse,
)

# ==================== FIXTURES ====================


@pytest.fixture
def sample_process_docx() -> Path:
    """Path to sample_process.docx test fixture."""
    path = (
        Path(__file__).parent.parent.parent
        / "data"
        / "sample_pdds"
        / "sample_process.docx"
    )
    assert path.exists()
    return path


@pytest.fixture
def mock_parsed_document() -> ParsedDocument:
    """Create a mock ParsedDocument for testing."""
    return ParsedDocument(
        source_path="/test/document.docx",
        file_type="docx",
        full_text="This is a test document with enough content. " * 50,  # >300 words
        tables=[],
        page_count=1,
        metadata={"paragraph_count": "5"},
        extraction_warnings=[],
    )


@pytest.fixture
def base_state() -> DocumentIntelligenceState:
    """Create a base state for testing nodes."""
    return {
        "file_path": "/test/document.docx",
        "session_id": "test-session",
        "parsed_document": None,
        "sections": [],
        "entities": None,
        "status": "running",
        "warnings": [],
        "errors": [],
        "completed_at": "",
    }


@pytest.fixture
def mock_sections() -> list[ExtractedSection]:
    """Create mock sections for testing."""
    return [
        ExtractedSection(
            title="Overview",
            content="Process overview content",
            section_type="process_overview",
            confidence_score=0.9,
            page_number=1,
        ),
        ExtractedSection(
            title="Steps",
            content="Process steps content",
            section_type="process_steps",
            confidence_score=0.85,
            page_number=1,
        ),
    ]


@pytest.fixture
def mock_entities() -> EntityExtractionResponse:
    """Create mock entities for testing."""
    return EntityExtractionResponse(
        rpa_tool="BLUE_PRISM",
        applications=[
            ApplicationEntity(name="SAP", type="desktop"),
            ApplicationEntity(name="Excel", type="desktop"),
        ],
        technologies=[],
        file_types=["xlsx"],
        sap_tcodes=[],
        process_triggers=[],
        roles=[],
        confidence=ConfidenceScores(applications=0.9, technologies=0.8, overall=0.85),
    )


# ==================== STATE AND ROUTING TESTS ====================


def test_should_continue_returns_end_when_failed():
    """Test routing returns 'end' when status='failed'."""
    state: DocumentIntelligenceState = {
        "file_path": "/test/doc.pdf",
        "session_id": "test",
        "parsed_document": None,
        "sections": [],
        "entities": None,
        "status": "failed",
        "warnings": [],
        "errors": [],
        "completed_at": "",
    }

    result = should_continue(state)
    assert result == "end"


def test_should_continue_returns_continue_when_running():
    """Test routing returns 'continue' when status='running'."""
    state: DocumentIntelligenceState = {
        "file_path": "/test/doc.pdf",
        "session_id": "test",
        "parsed_document": None,
        "sections": [],
        "entities": None,
        "status": "running",
        "warnings": [],
        "errors": [],
        "completed_at": "",
    }

    result = should_continue(state)
    assert result == "continue"


def test_should_continue_returns_continue_by_default():
    """Test routing returns 'continue' for any non-failed status."""
    state: DocumentIntelligenceState = {
        "file_path": "/test/doc.pdf",
        "session_id": "test",
        "parsed_document": None,
        "sections": [],
        "entities": None,
        "status": "success",
        "warnings": [],
        "errors": [],
        "completed_at": "",
    }

    result = should_continue(state)
    assert result == "continue"


# ==================== INGEST_DOCUMENT TESTS ====================


def test_ingest_document_unsupported_extension(base_state: DocumentIntelligenceState):
    """Test that unsupported extensions set status='failed'."""
    state = base_state.copy()
    state["file_path"] = "/test/document.xlsx"

    result = ingest_document(state)

    assert result["status"] == "failed"
    assert len(result["errors"]) > 0
    assert "Unsupported file type" in result["errors"][0]
    assert result["parsed_document"] is None


def test_ingest_document_parse_error(base_state: DocumentIntelligenceState):
    """Test that parse errors set status='failed'."""
    state = base_state.copy()
    state["file_path"] = "/nonexistent/document.pdf"

    result = ingest_document(state)

    assert result["status"] == "failed"
    assert len(result["errors"]) > 0
    assert result["parsed_document"] is None


def test_ingest_document_successful_docx(
    base_state: DocumentIntelligenceState, mock_parsed_document: ParsedDocument
):
    """Test successful DOCX parsing."""
    with patch("agents.document_intelligence.agent.parse_docx") as mock_parse:
        mock_parse.return_value = mock_parsed_document
        state = base_state.copy()
        state["file_path"] = "/test/document.docx"

        result = ingest_document(state)

        assert result["parsed_document"] is not None
        assert result["parsed_document"].file_type == "docx"
        mock_parse.assert_called_once_with("/test/document.docx")


def test_ingest_document_successful_pdf(
    base_state: DocumentIntelligenceState, mock_parsed_document: ParsedDocument
):
    """Test successful PDF parsing."""
    with patch("agents.document_intelligence.agent.parse_pdf") as mock_parse:
        mock_parse.return_value = mock_parsed_document
        state = base_state.copy()
        state["file_path"] = "/test/document.pdf"

        result = ingest_document(state)

        assert result["parsed_document"] is not None
        assert result["parsed_document"].file_type == "docx"
        mock_parse.assert_called_once_with("/test/document.pdf")


def test_ingest_document_accumulates_warnings(
    base_state: DocumentIntelligenceState,
):
    """Test that extraction warnings are accumulated."""
    doc_with_warnings = ParsedDocument(
        source_path="/test/doc.docx",
        file_type="docx",
        full_text="test content" * 50,
        tables=[],
        page_count=1,
        metadata={},
        extraction_warnings=["Warning 1", "Warning 2"],
    )

    with patch("agents.document_intelligence.agent.parse_docx") as mock_parse:
        mock_parse.return_value = doc_with_warnings
        state = base_state.copy()
        state["file_path"] = "/test/document.docx"
        state["warnings"] = ["Existing warning"]

        result = ingest_document(state)

        assert "Existing warning" in result["warnings"]
        assert "Warning 1" in result["warnings"]
        assert "Warning 2" in result["warnings"]


# ==================== IDENTIFY_DOCUMENT_SECTIONS TESTS ====================


def test_identify_sections_skips_when_failed(
    base_state: DocumentIntelligenceState,
):
    """Test that node skips if document failed to parse."""
    state = base_state.copy()
    state["status"] = "failed"

    result = identify_document_sections(state)

    assert result == {}


def test_identify_sections_skips_when_no_document(
    base_state: DocumentIntelligenceState,
):
    """Test that node skips if parsed_document is None."""
    state = base_state.copy()
    state["parsed_document"] = None

    result = identify_document_sections(state)

    assert result == {}


def test_identify_sections_successful(
    base_state: DocumentIntelligenceState,
    mock_parsed_document: ParsedDocument,
    mock_sections: list[ExtractedSection],
):
    """Test successful section identification."""
    with patch("agents.document_intelligence.agent.identify_sections") as mock_identify:
        mock_identify.return_value = mock_sections
        state = base_state.copy()
        state["parsed_document"] = mock_parsed_document

        result = identify_document_sections(state)

        assert result["sections"] == mock_sections
        mock_identify.assert_called_once()


def test_identify_sections_handles_exception(
    base_state: DocumentIntelligenceState,
    mock_parsed_document: ParsedDocument,
):
    """Test that section identification failure adds warning (recoverable)."""
    with patch("agents.document_intelligence.agent.identify_sections") as mock_identify:
        mock_identify.side_effect = Exception("Section ID failed")
        state = base_state.copy()
        state["parsed_document"] = mock_parsed_document

        result = identify_document_sections(state)

        assert result["sections"] == []
        assert len(result["warnings"]) > 0
        assert "Section identification failed" in result["warnings"][0]
        assert "status" not in result  # Status not set (recoverable)


# ==================== EXTRACT_DOCUMENT_ENTITIES TESTS ====================


def test_extract_entities_skips_when_failed(
    base_state: DocumentIntelligenceState,
):
    """Test that node skips if document failed to parse."""
    state = base_state.copy()
    state["status"] = "failed"

    result = extract_document_entities(state)

    assert result == {}


def test_extract_entities_creates_catchall_section(
    base_state: DocumentIntelligenceState,
    mock_parsed_document: ParsedDocument,
    mock_entities: EntityExtractionResponse,
):
    """Test that catch-all section is created when no sections."""
    with patch("agents.document_intelligence.agent.extract_entities") as mock_extract:
        mock_extract.return_value = mock_entities
        state = base_state.copy()
        state["parsed_document"] = mock_parsed_document
        state["sections"] = []

        result = extract_document_entities(state)

        assert result["entities"] is not None
        # Verify that extract_entities was called with a catch-all section
        call_args = mock_extract.call_args
        sections_arg = call_args[0][0]  # First positional arg
        assert len(sections_arg) == 1
        assert sections_arg[0].title == "Full Document"


def test_extract_entities_successful(
    base_state: DocumentIntelligenceState,
    mock_parsed_document: ParsedDocument,
    mock_sections: list[ExtractedSection],
    mock_entities: EntityExtractionResponse,
):
    """Test successful entity extraction."""
    with patch("agents.document_intelligence.agent.extract_entities") as mock_extract:
        mock_extract.return_value = mock_entities
        state = base_state.copy()
        state["parsed_document"] = mock_parsed_document
        state["sections"] = mock_sections

        result = extract_document_entities(state)

        assert result["entities"] is not None
        assert result["entities"] == mock_entities
        mock_extract.assert_called_once()


def test_extract_entities_handles_exception(
    base_state: DocumentIntelligenceState,
    mock_parsed_document: ParsedDocument,
    mock_sections: list[ExtractedSection],
):
    """Test that entity extraction failure adds warning (recoverable)."""
    with patch("agents.document_intelligence.agent.extract_entities") as mock_extract:
        mock_extract.side_effect = Exception("Entity extraction failed")
        state = base_state.copy()
        state["parsed_document"] = mock_parsed_document
        state["sections"] = mock_sections

        result = extract_document_entities(state)

        assert isinstance(result["entities"], EntityExtractionResponse)
        assert len(result["warnings"]) > 0
        assert "Entity extraction failed" in result["warnings"][0]


# ==================== VALIDATE_OUTPUT TESTS ====================


def test_validate_output_status_failed_propagates(
    base_state: DocumentIntelligenceState,
):
    """Test that status='failed' propagates through validation."""
    state = base_state.copy()
    state["status"] = "failed"

    result = validate_output(state)

    assert result["status"] == "failed"
    assert result["completed_at"] != ""


def test_validate_output_no_parsed_document_fails(
    base_state: DocumentIntelligenceState,
):
    """Test that missing parsed_document triggers failure."""
    state = base_state.copy()
    state["parsed_document"] = None

    result = validate_output(state)

    assert result["status"] == "failed"


def test_validate_output_low_word_count_needs_review(
    base_state: DocumentIntelligenceState,
):
    """Test that low word count triggers needs_review."""
    low_word_doc = ParsedDocument(
        source_path="/test/doc.docx",
        file_type="docx",
        full_text="short",  # Very few words
        tables=[],
        page_count=1,
        metadata={},
        extraction_warnings=[],
    )
    state = base_state.copy()
    state["parsed_document"] = low_word_doc
    state["sections"] = [
        ExtractedSection(
            title="Test",
            content="test",
            section_type="general",
            confidence_score=0.5,
            page_number=None,
        )
    ]
    state["entities"] = EntityExtractionResponse(
        applications=[ApplicationEntity(name="Test")]
    )

    result = validate_output(state)

    assert result["status"] == "needs_review"
    assert any("very few words" in w for w in result["warnings"])


def test_validate_output_few_sections_needs_review(
    base_state: DocumentIntelligenceState, mock_parsed_document: ParsedDocument
):
    """Test that few sections trigger needs_review."""
    state = base_state.copy()
    state["parsed_document"] = mock_parsed_document
    state["sections"] = [
        ExtractedSection(
            title="Test",
            content="test",
            section_type="general",
            confidence_score=0.5,
            page_number=None,
        )
    ]  # Only 1 section
    state["entities"] = EntityExtractionResponse(
        applications=[ApplicationEntity(name="Test")]
    )

    result = validate_output(state)

    assert result["status"] == "needs_review"
    assert any("Only" in w and "sections identified" in w for w in result["warnings"])


def test_validate_output_no_applications_needs_review(
    base_state: DocumentIntelligenceState, mock_parsed_document: ParsedDocument
):
    """Test that no applications trigger needs_review."""
    state = base_state.copy()
    state["parsed_document"] = mock_parsed_document
    state["sections"] = [
        ExtractedSection(
            title="Test",
            content="test",
            section_type="general",
            confidence_score=0.5,
            page_number=None,
        )
    ] * 3  # Multiple sections
    state["entities"] = EntityExtractionResponse(applications=[])  # No applications

    result = validate_output(state)

    assert result["status"] == "needs_review"
    assert any("No target applications" in w for w in result["warnings"])


def test_validate_output_success(
    base_state: DocumentIntelligenceState,
    mock_parsed_document: ParsedDocument,
    mock_sections: list[ExtractedSection],
    mock_entities: EntityExtractionResponse,
):
    """Test that all checks passing results in success."""
    state = base_state.copy()
    state["parsed_document"] = mock_parsed_document
    state["sections"] = mock_sections
    state["entities"] = mock_entities

    result = validate_output(state)

    assert result["status"] == "success"
    assert result["completed_at"] != ""


# ==================== RUN() FUNCTION TESTS ====================


def test_run_generates_session_id_when_none():
    """Test that run() generates session_id when not provided."""
    with patch("agents.document_intelligence.agent._graph") as mock_graph:
        # Capture the session_id that was passed to the graph
        def capture_state(state):
            state["status"] = "failed"
            return state

        mock_graph.invoke.side_effect = capture_state

        result = run("/test/doc.pdf")

        # Session ID should be generated and used
        assert result["session_id"] != ""
        assert len(result["session_id"]) == 8

        # Verify that invoke was called with the generated session_id
        called_state = mock_graph.invoke.call_args[0][0]
        assert called_state["session_id"] == result["session_id"]


def test_run_uses_provided_session_id():
    """Test that run() uses provided session_id."""
    with patch("agents.document_intelligence.agent._graph") as mock_graph:
        final_state = {
            "file_path": "/test/doc.pdf",
            "session_id": "custom-id",
            "parsed_document": None,
            "sections": [],
            "entities": None,
            "status": "failed",
            "warnings": [],
            "errors": [],
            "completed_at": "",
        }
        mock_graph.invoke.return_value = final_state

        result = run("/test/doc.pdf", session_id="custom-id")

        assert result["session_id"] == "custom-id"


def test_run_raises_on_graph_error():
    """Test that run() raises AgentExecutionError on graph failure."""
    with patch("agents.document_intelligence.agent._graph") as mock_graph:
        mock_graph.invoke.side_effect = Exception("Graph execution failed")

        with pytest.raises(AgentExecutionError) as exc_info:
            run("/test/doc.pdf")

        assert "Document Intelligence Agent failed" in str(exc_info.value.message)


def test_run_returns_state_dict(
    mock_parsed_document: ParsedDocument,
    mock_sections: list[ExtractedSection],
    mock_entities: EntityExtractionResponse,
):
    """Test that run() returns complete state dict."""
    with patch("agents.document_intelligence.agent.parse_docx") as mock_parse:
        with patch(
            "agents.document_intelligence.agent.identify_sections"
        ) as mock_sections_fn:
            with patch(
                "agents.document_intelligence.agent.extract_entities"
            ) as mock_entities_fn:
                mock_parse.return_value = mock_parsed_document
                mock_sections_fn.return_value = mock_sections
                mock_entities_fn.return_value = mock_entities

                result = run("/test/document.docx", session_id="test-session")

                # Verify result is a dict with all expected keys
                assert isinstance(result, dict)
                assert "file_path" in result
                assert "session_id" in result
                assert result["session_id"] == "test-session"
                assert "parsed_document" in result
                assert "sections" in result
                assert "entities" in result
                assert "status" in result
                assert "warnings" in result
                assert "errors" in result
                assert "completed_at" in result


# ==================== INTEGRATION TESTS ====================


@pytest.mark.integration
def test_document_intelligence_agent_integration(sample_process_docx: Path):
    """Test end-to-end agent execution with real document and LLM.

    This test makes a real LLM API call and is marked as integration.
    Run separately with: uv run pytest tests/unit/test_document_intelligence_agent.py
                             -v -m "integration" -s
    """
    result = run(str(sample_process_docx))

    # Verify result structure
    assert isinstance(result, dict)
    assert result["status"] in ["success", "needs_review", "failed"]
    assert result["parsed_document"] is not None
    assert len(result["sections"]) >= 1
    assert result["entities"] is not None
    assert result["completed_at"] != ""

    print("\n=== Document Intelligence Agent Integration Test ===")
    print(f"Session ID: {result['session_id']}")
    print(f"Status: {result['status']}")
    print(
        f"Parsed Document: {result['parsed_document'].file_type} "
        f"({result['parsed_document'].page_count} pages, "
        f"{result['parsed_document'].word_count()} words)"
    )
    print(f"Sections Found: {len(result['sections'])}")
    for section in result["sections"][:3]:
        print(f"  - {section.title} ({section.section_type})")
    if result["entities"]:
        print(f"Applications: {len(result['entities'].applications)}")
        for app in result["entities"].applications[:3]:
            print(f"  - {app.name}")
    print(f"Warnings: {len(result['warnings'])}")
    print(f"Errors: {len(result['errors'])}")
    print(f"Completed At: {result['completed_at']}")
