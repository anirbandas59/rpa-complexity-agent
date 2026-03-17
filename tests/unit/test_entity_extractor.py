"""Tests for tools.document.entity_extractor module.

Tests cover entity extraction, deduplication, RPA tool validation,
and LLM integration with retry logic.
No real API calls in unit tests — all LLM paths are mocked.
Integration test marked separately and uses real DOCX fixture.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.constants import RPATool
from core.models.document import ExtractedSection
from llm.manager import LLMManager
from tools.document.docx_parser import parse_docx
from tools.document.entity_extractor import (
    ApplicationEntity,
    ConfidenceScores,
    EntityExtractionResponse,
    ProcessTrigger,
    TechnologyEntity,
    extract_entities,
    get_application_count,
    get_technology_count,
)
from tools.document.section_identifier import identify_sections

# ==================== FIXTURES ====================


@pytest.fixture
def sample_process_docx() -> Path:
    """Path to sample_process.docx test fixture."""
    path = Path(__file__).parent.parent.parent / "data" / "sample_pdds" / "sample_process.docx"
    assert path.exists()
    return path


@pytest.fixture
def mock_sections() -> list[ExtractedSection]:
    """Create sample extracted sections for testing."""
    return [
        ExtractedSection(
            title="Process Overview",
            content=(
                "This process uses SAP ECC and Microsoft Excel "
                "to automate purchase orders."
            ),
            section_type="process_overview",
            confidence_score=0.9,
            page_number=1,
        ),
        ExtractedSection(
            title="Applications",
            content=(
                "The bot interacts with SAP (MM module), Excel, "
                "and Outlook for email notifications."
            ),
            section_type="applications",
            confidence_score=0.85,
            page_number=2,
        ),
        ExtractedSection(
            title="Technology Stack",
            content=(
                "Uses API calls to a custom REST API and VBA macros in Excel."
            ),
            section_type="general",
            confidence_score=0.7,
            page_number=2,
        ),
    ]


# ==================== _prepare_sections_text TESTS ====================


def test_prepare_sections_text_formats_with_headers():
    """Test that sections are formatted with ## headers."""
    from tools.document.entity_extractor import _prepare_sections_text

    sections = [
        ExtractedSection(
            title="Overview",
            content="Overview text",
            section_type="process_overview",
            confidence_score=0.9,
            page_number=None,
        ),
        ExtractedSection(
            title="Steps",
            content="Step text",
            section_type="process_steps",
            confidence_score=0.85,
            page_number=None,
        ),
    ]

    result = _prepare_sections_text(sections)

    assert "## Overview (process_overview)" in result
    assert "## Steps (process_steps)" in result
    assert "Overview text" in result
    assert "Step text" in result


def test_prepare_sections_text_truncates_at_max_chars():
    """Test that text is truncated at max_chars."""
    from tools.document.entity_extractor import _prepare_sections_text

    sections = [
        ExtractedSection(
            title="Long Section",
            content="x" * 5000,
            section_type="general",
            confidence_score=0.5,
            page_number=None,
        ),
    ]

    result = _prepare_sections_text(sections, max_chars=100)

    assert len(result) <= 200  # 100 + truncation notice
    assert "[Document truncated for processing]" in result


def test_prepare_sections_text_empty_list_returns_empty_string():
    """Test that empty sections list returns empty string."""
    from tools.document.entity_extractor import _prepare_sections_text

    result = _prepare_sections_text([])
    assert result == ""


# ==================== _deduplicate_applications TESTS ====================


def test_deduplicate_applications_removes_sap_variants():
    """Test that SAP and SAP ECC are deduplicated."""
    from tools.document.entity_extractor import _deduplicate_applications

    apps = [
        ApplicationEntity(name="SAP", type="desktop"),
        ApplicationEntity(name="SAP ECC", type="desktop"),
        ApplicationEntity(name="Excel", type="desktop"),
    ]

    result = _deduplicate_applications(apps)

    assert len(result) == 2
    assert result[0].name == "SAP"
    assert result[1].name == "Excel"


def test_deduplicate_applications_removes_excel_variants():
    """Test that Excel variants are deduplicated."""
    from tools.document.entity_extractor import _deduplicate_applications

    apps = [
        ApplicationEntity(name="Excel", type="desktop"),
        ApplicationEntity(name="Microsoft Excel", type="desktop"),
        ApplicationEntity(name="MS Excel", type="desktop"),
    ]

    result = _deduplicate_applications(apps)

    assert len(result) == 1
    assert result[0].name == "Excel"


def test_deduplicate_applications_removes_outlook_variants():
    """Test that Outlook variants are deduplicated."""
    from tools.document.entity_extractor import _deduplicate_applications

    apps = [
        ApplicationEntity(name="Outlook", type="email"),
        ApplicationEntity(name="Microsoft Outlook", type="email"),
        ApplicationEntity(name="MS Outlook", type="email"),
    ]

    result = _deduplicate_applications(apps)

    assert len(result) == 1
    assert result[0].name == "Outlook"


def test_deduplicate_applications_keeps_distinct():
    """Test that distinct applications are kept."""
    from tools.document.entity_extractor import _deduplicate_applications

    apps = [
        ApplicationEntity(name="SAP", type="desktop"),
        ApplicationEntity(name="Excel", type="desktop"),
        ApplicationEntity(name="Salesforce", type="web"),
    ]

    result = _deduplicate_applications(apps)

    assert len(result) == 3


def test_deduplicate_applications_empty_list():
    """Test that empty list returns empty list."""
    from tools.document.entity_extractor import _deduplicate_applications

    result = _deduplicate_applications([])
    assert result == []


def test_deduplicate_applications_keeps_first_occurrence():
    """Test that first occurrence is kept when deduplicating."""
    from tools.document.entity_extractor import _deduplicate_applications

    apps = [
        ApplicationEntity(name="SAP", type="desktop", notes="original"),
        ApplicationEntity(name="SAP ECC", type="web", notes="duplicate"),
    ]

    result = _deduplicate_applications(apps)

    assert len(result) == 1
    assert result[0].name == "SAP"
    assert result[0].type == "desktop"
    assert result[0].notes == "original"


# ==================== _validate_rpa_tool TESTS ====================


def test_validate_rpa_tool_blue_prism():
    """Test mapping of Blue Prism string to enum."""
    from tools.document.entity_extractor import _validate_rpa_tool

    result = _validate_rpa_tool("Blue Prism")
    assert result == RPATool.BLUE_PRISM
    assert result.value == "BLUE_PRISM"


def test_validate_rpa_tool_uipath():
    """Test mapping of UiPath string to enum."""
    from tools.document.entity_extractor import _validate_rpa_tool

    result = _validate_rpa_tool("UiPath")
    assert result == RPATool.UIPATH


def test_validate_rpa_tool_power_automate():
    """Test mapping of Power Automate string to enum."""
    from tools.document.entity_extractor import _validate_rpa_tool

    result = _validate_rpa_tool("Power Automate")
    assert result == RPATool.POWER_AUTOMATE


def test_validate_rpa_tool_aa360():
    """Test mapping of AA360 string to enum."""
    from tools.document.entity_extractor import _validate_rpa_tool

    result = _validate_rpa_tool("AA360")
    assert result == RPATool.AA360


def test_validate_rpa_tool_none_returns_unknown():
    """Test that None returns UNKNOWN."""
    from tools.document.entity_extractor import _validate_rpa_tool

    result = _validate_rpa_tool(None)
    assert result == RPATool.UNKNOWN


def test_validate_rpa_tool_unknown_string_returns_unknown():
    """Test that unknown string returns UNKNOWN."""
    from tools.document.entity_extractor import _validate_rpa_tool

    result = _validate_rpa_tool("unknown tool xyz")
    assert result == RPATool.UNKNOWN


def test_validate_rpa_tool_never_raises():
    """Test that validation never raises exceptions."""
    from tools.document.entity_extractor import _validate_rpa_tool

    # These should all work without raising
    _validate_rpa_tool(None)
    _validate_rpa_tool("")
    _validate_rpa_tool("invalid")
    _validate_rpa_tool(123)  # type: ignore


# ==================== extract_entities TESTS ====================


def test_extract_entities_empty_sections():
    """Test that empty sections returns empty response."""
    result = extract_entities([])
    assert isinstance(result, EntityExtractionResponse)
    assert result.applications == []
    assert result.technologies == []
    assert result.rpa_tool is None


def test_extract_entities_successful_extraction(mock_sections):
    """Test successful entity extraction."""
    mock_manager = MagicMock(spec=LLMManager)
    mock_manager.complete_structured.return_value = EntityExtractionResponse(
        rpa_tool="SAP",
        applications=[
            ApplicationEntity(name="SAP", type="desktop"),
            ApplicationEntity(name="Excel", type="desktop"),
        ],
        technologies=[
            TechnologyEntity(name="REST API", category="api"),
        ],
        file_types=["xlsx", "pdf"],
        sap_tcodes=["SE16", "VA01"],
        process_triggers=[
            ProcessTrigger(type="scheduled", description="Daily 8 AM"),
        ],
        roles=["Finance Manager"],
        confidence=ConfidenceScores(applications=0.9, technologies=0.8, overall=0.85),
    )

    result = extract_entities(mock_sections, mock_manager)

    assert len(result.applications) == 2
    assert len(result.technologies) == 1
    assert len(result.file_types) == 2
    assert mock_manager.complete_structured.called


def test_extract_entities_first_attempt_fails_retries(mock_sections):
    """Test that extraction retries on first LLM failure."""
    from core.exceptions import LLMProviderError

    mock_manager = MagicMock(spec=LLMManager)

    # First call raises, second succeeds
    mock_manager.complete_structured.side_effect = [
        LLMProviderError(message="API Error", context={}),
        EntityExtractionResponse(
            applications=[ApplicationEntity(name="SAP", type="desktop")],
        ),
    ]

    result = extract_entities(mock_sections, mock_manager)

    assert len(result.applications) == 1
    assert mock_manager.complete_structured.call_count == 2


def test_extract_entities_both_attempts_fail_returns_empty(mock_sections):
    """Test that both LLM failures return empty response."""
    from core.exceptions import LLMProviderError

    mock_manager = MagicMock(spec=LLMManager)
    mock_manager.complete_structured.side_effect = LLMProviderError(
        message="API Error", context={}
    )

    result = extract_entities(mock_sections, mock_manager)

    assert isinstance(result, EntityExtractionResponse)
    assert result.applications == []
    assert result.technologies == []


def test_extract_entities_deduplicates_after_extraction(mock_sections):
    """Test that deduplication runs after LLM call."""
    mock_manager = MagicMock(spec=LLMManager)
    mock_manager.complete_structured.return_value = EntityExtractionResponse(
        applications=[
            ApplicationEntity(name="SAP", type="desktop"),
            ApplicationEntity(name="SAP ECC", type="desktop"),
            ApplicationEntity(name="Excel", type="desktop"),
        ],
    )

    result = extract_entities(mock_sections, mock_manager)

    # Should have 2 after dedup (SAP and SAP ECC merge)
    assert len(result.applications) == 2


def test_extract_entities_normalizes_file_types(mock_sections):
    """Test that file types are normalized."""
    mock_manager = MagicMock(spec=LLMManager)
    mock_manager.complete_structured.return_value = EntityExtractionResponse(
        file_types=[".XLSX", " PDF ", "csv"],
    )

    result = extract_entities(mock_sections, mock_manager)

    assert "xlsx" in result.file_types
    assert "pdf" in result.file_types
    assert "csv" in result.file_types
    # Ensure no dots or spaces
    for ft in result.file_types:
        assert not ft.startswith(".")
        assert ft == ft.strip()


def test_extract_entities_validates_rpa_tool(mock_sections):
    """Test that rpa_tool is validated and stored as string."""
    mock_manager = MagicMock(spec=LLMManager)
    mock_manager.complete_structured.return_value = EntityExtractionResponse(
        rpa_tool="Blue Prism",
    )

    result = extract_entities(mock_sections, mock_manager)

    assert result.rpa_tool == "BLUE_PRISM"  # Enum value stored as string


def test_extract_entities_creates_default_manager(mock_sections):
    """Test that default LLMManager is created if not provided."""
    with patch("tools.document.entity_extractor.LLMManager") as mock_class:
        mock_manager = MagicMock()
        mock_manager.complete_structured.return_value = EntityExtractionResponse()
        mock_class.create_default.return_value = mock_manager

        extract_entities(mock_sections, llm_manager=None)

        mock_class.create_default.assert_called_once()


# ==================== get_application_count TESTS ====================


def test_get_application_count_returns_correct_count():
    """Test that application count is correct."""
    response = EntityExtractionResponse(
        applications=[
            ApplicationEntity(name="SAP", type="desktop"),
            ApplicationEntity(name="Excel", type="desktop"),
            ApplicationEntity(name="Salesforce", type="web"),
        ]
    )

    count = get_application_count(response)
    assert count == 3


def test_get_application_count_empty_response():
    """Test that empty response returns 0."""
    response = EntityExtractionResponse()
    count = get_application_count(response)
    assert count == 0


# ==================== get_technology_count TESTS ====================


def test_get_technology_count_returns_correct_count():
    """Test that technology count is correct."""
    response = EntityExtractionResponse(
        technologies=[
            TechnologyEntity(name="REST API", category="api"),
            TechnologyEntity(name="VBA Macros", category="scripting"),
        ]
    )

    count = get_technology_count(response)
    assert count == 2


def test_get_technology_count_empty_response():
    """Test that empty response returns 0."""
    response = EntityExtractionResponse()
    count = get_technology_count(response)
    assert count == 0


# ==================== SCHEMA TESTS ====================


def test_application_entity_schema():
    """Test ApplicationEntity schema."""
    app = ApplicationEntity(name="SAP", type="desktop", notes="ECC instance")
    assert app.name == "SAP"
    assert app.type == "desktop"
    assert app.notes == "ECC instance"


def test_technology_entity_schema():
    """Test TechnologyEntity schema."""
    tech = TechnologyEntity(name="REST API", category="api", notes="Custom integration")
    assert tech.name == "REST API"
    assert tech.category == "api"
    assert tech.notes == "Custom integration"


def test_process_trigger_schema():
    """Test ProcessTrigger schema."""
    trigger = ProcessTrigger(type="scheduled", description="Daily 8 AM")
    assert trigger.type == "scheduled"
    assert trigger.description == "Daily 8 AM"


def test_confidence_scores_schema():
    """Test ConfidenceScores schema."""
    confidence = ConfidenceScores(applications=0.9, technologies=0.8, overall=0.85)
    assert confidence.applications == 0.9
    assert confidence.technologies == 0.8
    assert confidence.overall == 0.85


def test_entity_extraction_response_schema():
    """Test EntityExtractionResponse schema."""
    response = EntityExtractionResponse(
        rpa_tool="BLUE_PRISM",
        applications=[ApplicationEntity(name="SAP", type="desktop")],
        technologies=[TechnologyEntity(name="API", category="api")],
        file_types=["xlsx", "pdf"],
        sap_tcodes=["SE16"],
        process_triggers=[ProcessTrigger(type="scheduled", description="Daily")],
        roles=["Finance Manager"],
        confidence=ConfidenceScores(applications=0.9, technologies=0.8, overall=0.85),
    )

    assert response.rpa_tool == "BLUE_PRISM"
    assert len(response.applications) == 1
    assert len(response.technologies) == 1
    assert response.file_types == ["xlsx", "pdf"]


# ==================== INTEGRATION TESTS ====================


@pytest.mark.integration
def test_integration_entity_extraction_from_real_docx(sample_process_docx: Path):
    """Test entity extraction from real DOCX document.

    This test makes a real LLM API call and is marked as integration.
    Run separately with: uv run pytest tests/unit/test_entity_extractor.py
                             -v -m "integration" -s
    """
    # Parse the DOCX document
    parsed_doc = parse_docx(str(sample_process_docx))

    # Identify sections
    sections = identify_sections(parsed_doc)

    # Extract entities
    result = extract_entities(sections)

    # Assertions
    assert isinstance(result, EntityExtractionResponse)

    # sample_process.docx mentions SAP, Excel, Outlook
    # Should find at least one application
    assert len(result.applications) >= 1, "Should find at least one application"

    # Confidence should be above 0
    assert result.confidence.overall > 0.0, "Should have confidence score"

    # Print extracted entities for inspection
    print(f"\n=== Extracted Entities from {sample_process_docx.name} ===")
    print(f"RPA Tool: {result.rpa_tool}")
    print(f"Applications ({len(result.applications)}):")
    for app in result.applications:
        print(f"  - {app.name} ({app.type}): {app.notes}")
    print(f"Technologies ({len(result.technologies)}):")
    for tech in result.technologies:
        print(f"  - {tech.name} ({tech.category}): {tech.notes}")
    print(f"File Types: {result.file_types}")
    print(f"SAP Tcodes: {result.sap_tcodes}")
    print("Process Triggers:")
    for trigger in result.process_triggers:
        print(f"  - {trigger.type}: {trigger.description}")
    print(f"Roles: {result.roles}")
    print(f"Confidence: {result.confidence.overall}")
