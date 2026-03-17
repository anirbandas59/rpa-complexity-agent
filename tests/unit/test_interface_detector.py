"""Tests for tools.analysis.interface_detector module.

Tests cover interface detection, deduplication, entity merging,
and LLM integration.
No real API calls in unit tests — all LLM paths are mocked.
Integration test marked separately and uses real DOCX fixture.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.exceptions import LLMProviderError
from core.models.document import ExtractedSection
from llm.manager import LLMManager
from tools.analysis.interface_detector import (
    ApplicationEntity,
    DetectedInterface,
    InterfaceDetectionLLMResponse,
    InterfaceDetectionResult,
    detect_interfaces,
    get_interface_count,
)
from tools.analysis.interface_detector import _normalize_app_name
from tools.document.docx_parser import parse_docx
from tools.document.entity_extractor import extract_entities
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
            title="Applications",
            content=(
                "The bot interacts with SAP ECC, Microsoft Excel, "
                "and Outlook for email notifications. It also reads from "
                "a shared network drive."
            ),
            section_type="applications",
            confidence_score=0.9,
            page_number=1,
        ),
        ExtractedSection(
            title="Process Overview",
            content="Daily invoice reconciliation process.",
            section_type="process_overview",
            confidence_score=0.85,
            page_number=1,
        ),
    ]


@pytest.fixture
def mock_entity_result():
    """Create a mock entity extraction result."""
    from tools.document.entity_extractor import EntityExtractionResponse, ConfidenceScores

    return EntityExtractionResponse(
        applications=[
            ApplicationEntity(name="SAP", type="desktop", notes="ERP system"),
            ApplicationEntity(name="Excel", type="desktop", notes="Spreadsheets"),
        ],
        confidence=ConfidenceScores(applications=0.85, overall=0.8),
    )


@pytest.fixture
def mock_llm_response() -> InterfaceDetectionLLMResponse:
    """Create a mock LLM response."""
    return InterfaceDetectionLLMResponse(
        applications=[
            DetectedInterface(
                name="SAP ECC",
                type="desktop",
                automation_method="ui_automation",
                evidence="Bot logs into SAP ECC",
                confidence=0.9,
            ),
            DetectedInterface(
                name="Outlook",
                type="email",
                automation_method="ui_automation",
                evidence="Sends emails via Outlook",
                confidence=0.8,
            ),
        ],
        total_count=2,
        detection_confidence=0.85,
        notes="Found 2 applications",
    )


# ==================== _normalize_app_name TESTS ====================


def test_normalize_app_name_sap_ecc_to_sap():
    """Test SAP ECC normalizes to SAP."""
    from tools.analysis.interface_detector import _normalize_app_name

    result = _normalize_app_name("SAP ECC")
    assert result == "sap"


def test_normalize_app_name_microsoft_excel_to_excel():
    """Test Microsoft Excel normalizes to excel."""
    from tools.analysis.interface_detector import _normalize_app_name

    result = _normalize_app_name("Microsoft Excel")
    assert result == "excel"


def test_normalize_app_name_ms_outlook_to_outlook():
    """Test MS Outlook normalizes to outlook."""
    from tools.analysis.interface_detector import _normalize_app_name

    result = _normalize_app_name("MS Outlook")
    assert result == "outlook"


def test_normalize_app_name_no_alias():
    """Test name without alias just gets lowercased."""
    from tools.analysis.interface_detector import _normalize_app_name

    result = _normalize_app_name("CustomerPortal")
    assert result == "customerportal"


def test_normalize_app_name_case_insensitive():
    """Test normalization is case insensitive."""
    from tools.analysis.interface_detector import _normalize_app_name

    result1 = _normalize_app_name("Excel")
    result2 = _normalize_app_name("EXCEL")
    result3 = _normalize_app_name("Excel")
    assert result1 == result2 == result3


# ==================== _deduplicate_interfaces TESTS ====================


def test_deduplicate_interfaces_removes_sap_variants():
    """Test that SAP and SAP ECC are deduplicated."""
    from tools.analysis.interface_detector import _deduplicate_interfaces

    interfaces = [

        DetectedInterface(name="SAP", type="desktop", confidence=0.8),
        DetectedInterface(name="SAP ECC", type="desktop", confidence=0.9),
        DetectedInterface(name="Excel", type="desktop", confidence=0.85),
    ]

    result = _deduplicate_interfaces(interfaces)

    assert len(result) == 2
    # Should keep SAP ECC since it has higher confidence
    sap_entry = next((i for i in result if _normalize_app_name(i.name) == "sap"), None)
    assert sap_entry is not None
    assert sap_entry.confidence == 0.9


def test_deduplicate_interfaces_keeps_higher_confidence():
    """Test that higher confidence entry is kept when deduplicating."""
    from tools.analysis.interface_detector import _deduplicate_interfaces

    interfaces = [
        DetectedInterface(name="Excel", type="desktop", confidence=0.6),
        DetectedInterface(name="Microsoft Excel", type="desktop", confidence=0.9),
    ]

    result = _deduplicate_interfaces(interfaces)

    assert len(result) == 1
    assert result[0].confidence == 0.9


def test_deduplicate_interfaces_empty_list():
    """Test empty list returns empty list."""
    from tools.analysis.interface_detector import _deduplicate_interfaces

    result = _deduplicate_interfaces([])
    assert result == []


# ==================== _merge_with_entity_results TESTS ====================


def test_merge_with_entity_results_combines_sources():
    """Test merging LLM and entity results."""
    from tools.analysis.interface_detector import _merge_with_entity_results

    llm_interfaces = [
        DetectedInterface(name="Outlook", type="email", confidence=0.8),
    ]
    entity_apps = [
        ApplicationEntity(name="SAP", type="desktop", notes="ERP"),
        ApplicationEntity(name="Excel", type="desktop", notes="Spreadsheets"),
    ]

    result = _merge_with_entity_results(llm_interfaces, entity_apps)

    assert len(result) == 3
    names = [i.name for i in result]
    assert "Outlook" in names
    assert "SAP" in names
    assert "Excel" in names


def test_merge_with_entity_results_deduplicates_across_sources():
    """Test deduplication when both sources have same app."""
    from tools.analysis.interface_detector import _merge_with_entity_results

    llm_interfaces = [
        DetectedInterface(name="SAP ECC", type="desktop", confidence=0.9),
    ]
    entity_apps = [
        ApplicationEntity(name="SAP", type="desktop", notes="ERP"),
    ]

    result = _merge_with_entity_results(llm_interfaces, entity_apps)

    # Should deduplicate to 1 (SAP/SAP ECC are same)
    assert len(result) == 1
    # Should keep LLM result since it has higher confidence
    assert result[0].confidence == 0.9


def test_merge_with_entity_results_entity_apps_only():
    """Test merging when only entity apps provided."""
    from tools.analysis.interface_detector import _merge_with_entity_results

    entity_apps = [
        ApplicationEntity(name="SAP", type="desktop", notes="ERP"),
        ApplicationEntity(name="Excel", type="desktop", notes="Spreadsheets"),
    ]

    result = _merge_with_entity_results([], entity_apps)

    assert len(result) == 2
    names = [i.name for i in result]
    assert "SAP" in names
    assert "Excel" in names


def test_merge_with_entity_results_llm_only():
    """Test merging when only LLM interfaces provided."""
    from tools.analysis.interface_detector import _merge_with_entity_results

    llm_interfaces = [
        DetectedInterface(name="Outlook", type="email", confidence=0.8),
        DetectedInterface(name="SharePoint", type="web", confidence=0.7),
    ]

    result = _merge_with_entity_results(llm_interfaces, [])

    assert len(result) == 2


# ==================== _filter_relevant_sections TESTS ====================


def test_filter_relevant_sections_prioritizes_applications():
    """Test that applications section has highest priority."""
    from tools.analysis.interface_detector import _filter_relevant_sections

    sections = [
        ExtractedSection(
            title="Process Overview",
            content="Overview",
            section_type="process_overview",
            confidence_score=0.9,
            page_number=None,
        ),
        ExtractedSection(
            title="Applications",
            content="Apps content",
            section_type="applications",
            confidence_score=0.85,
            page_number=None,
        ),
    ]

    result = _filter_relevant_sections(sections)

    assert len(result) == 1
    assert result[0].section_type == "applications"


def test_filter_relevant_sections_fallback_to_process_overview():
    """Test fallback to process_overview when no applications."""
    from tools.analysis.interface_detector import _filter_relevant_sections

    sections = [
        ExtractedSection(
            title="Process Overview",
            content="Overview",
            section_type="process_overview",
            confidence_score=0.9,
            page_number=None,
        ),
        ExtractedSection(
            title="Steps",
            content="Steps",
            section_type="process_steps",
            confidence_score=0.85,
            page_number=None,
        ),
    ]

    result = _filter_relevant_sections(sections)

    assert len(result) == 1
    assert result[0].section_type == "process_overview"


# ==================== DetectedInterface Validator Tests ====================


def test_detected_interface_invalid_type_defaults_to_desktop():
    """Test that invalid type defaults to desktop."""
    interface = DetectedInterface(
        name="Test",
        type="invalid_type",
        confidence=0.8,
    )

    assert interface.type == "desktop"


def test_detected_interface_invalid_automation_method_defaults():
    """Test that invalid automation_method defaults to ui_automation."""
    interface = DetectedInterface(
        name="Test",
        automation_method="invalid_method",
        confidence=0.8,
    )

    assert interface.automation_method == "ui_automation"


def test_detected_interface_confidence_clamped_to_1():
    """Test confidence clamped to 1.0."""
    interface = DetectedInterface(
        name="Test",
        confidence=1.5,
    )

    assert interface.confidence == 1.0


def test_detected_interface_confidence_clamped_to_0():
    """Test confidence clamped to 0.0."""
    interface = DetectedInterface(
        name="Test",
        confidence=-0.5,
    )

    assert interface.confidence == 0.0


# ==================== detect_interfaces Tests (Mock LLMManager) ====================


def test_detect_interfaces_returns_result_on_success(
    mock_sections: list[ExtractedSection],
    mock_entity_result,
    mock_llm_response: InterfaceDetectionLLMResponse,
):
    """Test successful interface detection with merged results."""
    mock_llm = MagicMock(spec=LLMManager)
    mock_llm.complete_structured.return_value = mock_llm_response

    result = detect_interfaces(
        mock_sections, entity_result=mock_entity_result, llm_manager=mock_llm
    )

    assert isinstance(result, InterfaceDetectionResult)
    assert result.source == "merged"
    assert result.total_count >= 2


def test_detect_interfaces_source_merged():
    """Test source is 'merged' when both LLM and entity provide data."""
    from tools.document.entity_extractor import EntityExtractionResponse, ConfidenceScores

    sections = [
        ExtractedSection(
            title="Apps",
            content="Using SAP and Excel",
            section_type="applications",
            confidence_score=0.9,
            page_number=None,
        ),
    ]

    entity_result = EntityExtractionResponse(
        applications=[ApplicationEntity(name="SAP", type="desktop")],
        confidence=ConfidenceScores(applications=0.8, overall=0.8),
    )

    llm_response = InterfaceDetectionLLMResponse(
        applications=[
            DetectedInterface(name="Excel", type="desktop", confidence=0.8),
        ],
        total_count=1,
        detection_confidence=0.8,
    )

    mock_llm = MagicMock(spec=LLMManager)
    mock_llm.complete_structured.return_value = llm_response

    result = detect_interfaces(
        sections, entity_result=entity_result, llm_manager=mock_llm
    )

    assert result.source == "merged"


def test_detect_interfaces_source_llm_only():
    """Test source is 'llm_only' when no entity_result provided."""
    sections = [
        ExtractedSection(
            title="Apps",
            content="Using SAP",
            section_type="applications",
            confidence_score=0.9,
            page_number=None,
        ),
    ]

    llm_response = InterfaceDetectionLLMResponse(
        applications=[
            DetectedInterface(name="SAP", type="desktop", confidence=0.9),
        ],
        total_count=1,
        detection_confidence=0.9,
    )

    mock_llm = MagicMock(spec=LLMManager)
    mock_llm.complete_structured.return_value = llm_response

    result = detect_interfaces(sections, entity_result=None, llm_manager=mock_llm)

    assert result.source == "llm_only"
    assert result.total_count == 1


def test_detect_interfaces_source_entity_extractor_only():
    """Test source is 'entity_extractor_only' when LLM returns empty."""
    from tools.document.entity_extractor import EntityExtractionResponse, ConfidenceScores

    sections = [
        ExtractedSection(
            title="Apps",
            content="",
            section_type="applications",
            confidence_score=0.9,
            page_number=None,
        ),
    ]

    entity_result = EntityExtractionResponse(
        applications=[
            ApplicationEntity(name="SAP", type="desktop"),
            ApplicationEntity(name="Excel", type="desktop"),
        ],
        confidence=ConfidenceScores(applications=0.85, overall=0.8),
    )

    llm_response = InterfaceDetectionLLMResponse(
        applications=[],
        total_count=0,
        detection_confidence=0.1,
    )

    mock_llm = MagicMock(spec=LLMManager)
    mock_llm.complete_structured.return_value = llm_response

    result = detect_interfaces(
        sections, entity_result=entity_result, llm_manager=mock_llm
    )

    assert result.source == "entity_extractor_only"
    assert result.total_count == 2


def test_detect_interfaces_source_empty():
    """Test source is 'empty' when both sources return nothing."""
    sections = [
        ExtractedSection(
            title="Apps",
            content="",
            section_type="applications",
            confidence_score=0.9,
            page_number=None,
        ),
    ]

    llm_response = InterfaceDetectionLLMResponse(
        applications=[],
        total_count=0,
        detection_confidence=0.1,
    )

    mock_llm = MagicMock(spec=LLMManager)
    mock_llm.complete_structured.return_value = llm_response

    result = detect_interfaces(
        sections, entity_result=None, llm_manager=mock_llm
    )

    assert result.source == "empty"
    assert result.total_count == 0


def test_detect_interfaces_retries_on_llm_failure():
    """Test that LLM failure triggers retry."""
    sections = [
        ExtractedSection(
            title="Apps",
            content="Using SAP",
            section_type="applications",
            confidence_score=0.9,
            page_number=None,
        ),
    ]

    llm_response = InterfaceDetectionLLMResponse(
        applications=[
            DetectedInterface(name="SAP", type="desktop", confidence=0.8),
        ],
        total_count=1,
        detection_confidence=0.8,
    )

    mock_llm = MagicMock(spec=LLMManager)
    # First call raises error, second succeeds
    mock_llm.complete_structured.side_effect = [
        LLMProviderError("First attempt failed"),
        llm_response,
    ]

    result = detect_interfaces(sections, entity_result=None, llm_manager=mock_llm)

    assert result.total_count == 1
    assert mock_llm.complete_structured.call_count == 2


def test_detect_interfaces_returns_default_on_both_failures():
    """Test default result when both LLM attempts fail."""
    sections = [
        ExtractedSection(
            title="Apps",
            content="Using SAP",
            section_type="applications",
            confidence_score=0.9,
            page_number=None,
        ),
    ]

    mock_llm = MagicMock(spec=LLMManager)
    # Both attempts fail
    mock_llm.complete_structured.side_effect = [
        LLMProviderError("First attempt failed"),
        LLMProviderError("Retry failed"),
    ]

    result = detect_interfaces(sections, entity_result=None, llm_manager=mock_llm)

    assert result.source == "empty"
    assert result.total_count == 0


# ==================== InterfaceDetectionResult Property Tests ====================


def test_interface_names_returns_name_list():
    """Test interface_names property returns list of names."""
    interfaces = [
        DetectedInterface(name="SAP", type="desktop"),
        DetectedInterface(name="Excel", type="desktop"),
        DetectedInterface(name="Outlook", type="email"),
    ]

    result = InterfaceDetectionResult(
        interfaces=interfaces,
        total_count=3,
        detection_confidence=0.85,
        source="test",
    )

    names = result.interface_names()

    assert names == ["SAP", "Excel", "Outlook"]


# ==================== get_interface_count Tests ====================


def test_get_interface_count_returns_total_count():
    """Test get_interface_count returns total_count from result."""
    result = InterfaceDetectionResult(
        interfaces=[
            DetectedInterface(name="SAP", type="desktop"),
            DetectedInterface(name="Excel", type="desktop"),
        ],
        total_count=2,
        detection_confidence=0.85,
        source="test",
    )

    count = get_interface_count(result)

    assert count == 2


# ==================== INTEGRATION TESTS ====================


@pytest.mark.integration
def test_detect_interfaces_integration(sample_process_docx: Path):
    """Integration test with real DOCX parsing."""
    # Parse the document
    parsed_doc = parse_docx(sample_process_docx)
    assert parsed_doc.is_valid()

    # Identify sections
    sections = identify_sections(parsed_doc)
    assert len(sections) > 0

    # Extract entities
    entity_result = extract_entities(sections)

    # Detect interfaces (will use real LLM)
    result = detect_interfaces(
        sections, entity_result=entity_result, session_id="test_integration"
    )

    # Verify result structure
    assert isinstance(result, InterfaceDetectionResult)
    assert result.total_count >= 0
    assert result.source in ["merged", "llm_only", "entity_extractor_only", "empty"]
    assert 0.0 <= result.detection_confidence <= 1.0
    assert isinstance(result.interface_names(), list)

    # Log results for inspection
    print(f"\nInterfaces found: {result.interface_names()}")
    print(f"Total count: {result.total_count}")
    print(f"Source: {result.source}")
    print(f"Confidence: {result.detection_confidence:.2f}")
    if result.notes:
        print(f"Notes: {result.notes}")
