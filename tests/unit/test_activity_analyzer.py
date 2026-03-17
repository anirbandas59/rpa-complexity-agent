"""Tests for tools.analysis.activity_analyzer module.

Tests cover activity counting, section filtering, confidence validation,
and LLM integration with retry logic.
No real API calls in unit tests — all LLM paths are mocked.
Integration test marked separately and uses real DOCX fixture.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.exceptions import LLMProviderError
from core.models.document import ExtractedSection
from llm.manager import LLMManager
from tools.analysis.activity_analyzer import (
    ActivityAnalysisResult,
    analyze_activities,
    get_activity_tier_hint,
)
from tools.document.docx_parser import parse_docx
from tools.document.section_identifier import identify_sections


# ==================== FIXTURES ====================


@pytest.fixture
def sample_process_docx() -> Path:
    """Path to sample_process.docx test fixture."""
    path = Path(__file__).parent.parent / "fixtures" / "sample_process.docx"
    assert path.exists()
    return path


@pytest.fixture
def mock_sections() -> list[ExtractedSection]:
    """Create sample extracted sections for testing."""
    return [
        ExtractedSection(
            title="Process Overview",
            content=(
                "This process automates the daily invoice reconciliation. "
                "The bot downloads invoices from the vendor portal, extracts "
                "key fields, and matches them against the accounting system."
            ),
            section_type="process_overview",
            confidence_score=0.9,
            page_number=1,
        ),
        ExtractedSection(
            title="Process Steps",
            content=(
                "1. Log in to vendor portal\n"
                "2. Navigate to invoice section\n"
                "3. Download today's invoices\n"
                "4. Open Excel workbook\n"
                "5. Paste invoice numbers\n"
                "6. Launch SAP\n"
                "7. Search for invoices in FI/CO\n"
                "8. Compare amounts\n"
            ),
            section_type="process_steps",
            confidence_score=0.95,
            page_number=1,
        ),
        ExtractedSection(
            title="Business Rules",
            content=(
                "If amounts match, mark as reconciled. "
                "If amounts differ by < 5%, flag for review. "
                "If amounts differ by >= 5%, escalate to Finance Manager."
            ),
            section_type="business_rules",
            confidence_score=0.85,
            page_number=2,
        ),
    ]


@pytest.fixture
def mock_activity_result() -> ActivityAnalysisResult:
    """Create a mock activity analysis result."""
    return ActivityAnalysisResult(
        raw_activity_count=8,
        activity_list=[
            "Log in to vendor portal",
            "Navigate to invoice section",
            "Download invoices to file",
            "Open Excel workbook",
            "Paste invoice data",
            "Launch SAP",
            "Search for invoices",
            "Compare and reconcile",
        ],
        count_confidence=0.9,
        counting_rationale="Process steps clearly describe 8 distinct activities",
        ambiguous_items=[],
    )


# ==================== _filter_relevant_sections TESTS ====================


def test_filter_relevant_sections_returns_process_steps_when_present():
    """Test that process_steps sections are highest priority."""
    from tools.analysis.activity_analyzer import _filter_relevant_sections

    sections = [
        ExtractedSection(
            title="Overview",
            content="Overview",
            section_type="process_overview",
            confidence_score=0.9,
            page_number=None,
        ),
        ExtractedSection(
            title="Steps",
            content="Steps content",
            section_type="process_steps",
            confidence_score=0.85,
            page_number=None,
        ),
        ExtractedSection(
            title="Rules",
            content="Rules content",
            section_type="business_rules",
            confidence_score=0.8,
            page_number=None,
        ),
    ]

    result = _filter_relevant_sections(sections)

    assert len(result) == 1
    assert result[0].section_type == "process_steps"


def test_filter_relevant_sections_returns_process_overview_when_no_steps():
    """Test fallback to process_overview when no steps section."""
    from tools.analysis.activity_analyzer import _filter_relevant_sections

    sections = [
        ExtractedSection(
            title="Overview",
            content="Overview",
            section_type="process_overview",
            confidence_score=0.9,
            page_number=None,
        ),
        ExtractedSection(
            title="Rules",
            content="Rules content",
            section_type="business_rules",
            confidence_score=0.8,
            page_number=None,
        ),
    ]

    result = _filter_relevant_sections(sections)

    assert len(result) == 1
    assert result[0].section_type == "process_overview"


def test_filter_relevant_sections_returns_all_when_no_priority_sections():
    """Test fallback to all sections when no high-priority sections."""
    from tools.analysis.activity_analyzer import _filter_relevant_sections

    sections = [
        ExtractedSection(
            title="General Info",
            content="General content",
            section_type="general",
            confidence_score=0.7,
            page_number=None,
        ),
        ExtractedSection(
            title="Exceptions",
            content="Exceptions content",
            section_type="exceptions",
            confidence_score=0.6,
            page_number=None,
        ),
    ]

    result = _filter_relevant_sections(sections)

    # Should return all sections when no priority sections found
    assert len(result) == 2


def test_filter_relevant_sections_excludes_low_priority_when_steps_present():
    """Test that business_rules and applications are excluded when steps exist."""
    from tools.analysis.activity_analyzer import _filter_relevant_sections

    sections = [
        ExtractedSection(
            title="Steps",
            content="Steps content",
            section_type="process_steps",
            confidence_score=0.95,
            page_number=None,
        ),
        ExtractedSection(
            title="Rules",
            content="Rules content",
            section_type="business_rules",
            confidence_score=0.8,
            page_number=None,
        ),
        ExtractedSection(
            title="Applications",
            content="Apps content",
            section_type="applications",
            confidence_score=0.75,
            page_number=None,
        ),
    ]

    result = _filter_relevant_sections(sections)

    # Should return only process_steps
    assert len(result) == 1
    assert result[0].section_type == "process_steps"


def test_filter_relevant_sections_empty_list_returns_empty():
    """Test that empty input returns empty list."""
    from tools.analysis.activity_analyzer import _filter_relevant_sections

    result = _filter_relevant_sections([])

    assert result == []


# ==================== _prepare_sections_text TESTS ====================


def test_prepare_sections_text_formats_with_headers():
    """Test that sections are formatted with ## headers."""
    from tools.analysis.activity_analyzer import _prepare_sections_text

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
    from tools.analysis.activity_analyzer import _prepare_sections_text

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
    from tools.analysis.activity_analyzer import _prepare_sections_text

    result = _prepare_sections_text([])

    assert result == ""


# ==================== ActivityAnalysisResult Validator Tests ====================


def test_activity_analysis_result_rejects_negative_count():
    """Test that negative activity count is rejected."""
    with pytest.raises(ValueError):
        ActivityAnalysisResult(
            raw_activity_count=-1,
            activity_list=[],
            count_confidence=0.5,
            counting_rationale="Test",
        )


def test_activity_analysis_result_clamps_confidence():
    """Test that confidence is clamped to 0.0-1.0."""
    # Over 1.0
    result = ActivityAnalysisResult(
        raw_activity_count=5,
        activity_list=["Activity 1", "Activity 2", "Activity 3", "Activity 4", "Activity 5"],
        count_confidence=1.5,
        counting_rationale="Test",
    )
    assert result.count_confidence == 1.0

    # Below 0.0
    result = ActivityAnalysisResult(
        raw_activity_count=5,
        activity_list=["Activity 1", "Activity 2", "Activity 3", "Activity 4", "Activity 5"],
        count_confidence=-0.5,
        counting_rationale="Test",
    )
    assert result.count_confidence == 0.0


def test_activity_analysis_result_syncs_activity_list():
    """Test that activity_list is synced to count (truncate when too many)."""
    # More items than count — should truncate
    result = ActivityAnalysisResult(
        raw_activity_count=2,
        activity_list=["Activity 1", "Activity 2", "Activity 3", "Activity 4"],
        count_confidence=0.8,
        counting_rationale="Test",
    )

    # The list should have been truncated to match the count
    assert len(result.activity_list) <= 2


# ==================== analyze_activities Tests (Mock LLMManager) ====================


def test_analyze_activities_returns_result_on_success(
    mock_sections: list[ExtractedSection],
    mock_activity_result: ActivityAnalysisResult,
):
    """Test successful activity analysis."""
    mock_llm = MagicMock(spec=LLMManager)
    mock_llm.complete_structured.return_value = mock_activity_result

    result = analyze_activities(mock_sections, llm_manager=mock_llm)

    assert isinstance(result, ActivityAnalysisResult)
    assert result.raw_activity_count == 8
    assert len(result.activity_list) == 8


def test_analyze_activities_with_successful_count_and_list():
    """Test that result with matching count and list works."""
    mock_sections = [
        ExtractedSection(
            title="Steps",
            content="Step descriptions",
            section_type="process_steps",
            confidence_score=0.9,
            page_number=None,
        ),
    ]

    mock_result = ActivityAnalysisResult(
        raw_activity_count=3,
        activity_list=["Activity A", "Activity B", "Activity C"],
        count_confidence=0.85,
        counting_rationale="Clear steps",
    )

    mock_llm = MagicMock(spec=LLMManager)
    mock_llm.complete_structured.return_value = mock_result

    result = analyze_activities(mock_sections, llm_manager=mock_llm)

    assert result.raw_activity_count == 3
    assert len(result.activity_list) == 3


def test_analyze_activities_retries_on_llm_failure():
    """Test that activity analysis retries once on LLM failure."""
    mock_sections = [
        ExtractedSection(
            title="Steps",
            content="Step descriptions",
            section_type="process_steps",
            confidence_score=0.9,
            page_number=None,
        ),
    ]

    mock_result = ActivityAnalysisResult(
        raw_activity_count=5,
        activity_list=["A1", "A2", "A3", "A4", "A5"],
        count_confidence=0.7,
        counting_rationale="Retry succeeded",
    )

    mock_llm = MagicMock(spec=LLMManager)
    # First call raises error, second call succeeds
    mock_llm.complete_structured.side_effect = [
        LLMProviderError("First attempt failed"),
        mock_result,
    ]

    result = analyze_activities(mock_sections, llm_manager=mock_llm)

    assert result.raw_activity_count == 5
    # Should have called complete_structured twice (once, then retry)
    assert mock_llm.complete_structured.call_count == 2


def test_analyze_activities_returns_default_on_both_failures():
    """Test that default result is returned when both attempts fail."""
    mock_sections = [
        ExtractedSection(
            title="Steps",
            content="Step descriptions",
            section_type="process_steps",
            confidence_score=0.9,
            page_number=None,
        ),
    ]

    mock_llm = MagicMock(spec=LLMManager)
    # Both calls raise error
    mock_llm.complete_structured.side_effect = [
        LLMProviderError("First attempt failed"),
        LLMProviderError("Retry failed"),
    ]

    result = analyze_activities(mock_sections, llm_manager=mock_llm)

    assert result.raw_activity_count == 0
    assert result.count_confidence == 0.0
    assert "manual review required" in result.counting_rationale


def test_analyze_activities_caps_count_at_60():
    """Test that activity count is capped at 60 (XL ceiling)."""
    mock_sections = [
        ExtractedSection(
            title="Steps",
            content="Many activities",
            section_type="process_steps",
            confidence_score=0.9,
            page_number=None,
        ),
    ]

    # Mock result with count > 60
    mock_result = ActivityAnalysisResult(
        raw_activity_count=75,
        activity_list=[f"Activity {i}" for i in range(75)],
        count_confidence=0.8,
        counting_rationale="Many activities found",
    )

    mock_llm = MagicMock(spec=LLMManager)
    mock_llm.complete_structured.return_value = mock_result

    result = analyze_activities(mock_sections, llm_manager=mock_llm)

    assert result.raw_activity_count == 60
    assert len(result.activity_list) == 60
    assert "Capped at 60" in result.counting_rationale
    assert "75" in result.counting_rationale


def test_analyze_activities_handles_empty_sections():
    """Test that empty sections are handled gracefully."""
    mock_llm = MagicMock(spec=LLMManager)
    mock_result = ActivityAnalysisResult(
        raw_activity_count=0,
        activity_list=[],
        count_confidence=0.1,
        counting_rationale="No sections provided",
    )
    mock_llm.complete_structured.return_value = mock_result

    result = analyze_activities([], llm_manager=mock_llm)

    # Should still call LLM even with empty sections
    assert isinstance(result, ActivityAnalysisResult)


# ==================== get_activity_tier_hint Tests ====================


def test_get_activity_tier_hint_xs_s_range():
    """Test tier hint for XS/S range (0-10 activities)."""
    result = ActivityAnalysisResult(
        raw_activity_count=5,
        activity_list=["A1", "A2", "A3", "A4", "A5"],
        count_confidence=0.9,
        counting_rationale="Test",
    )

    hint = get_activity_tier_hint(result)

    assert "XS or S" in hint
    assert "< 10" in hint


def test_get_activity_tier_hint_m_range():
    """Test tier hint for M range (11-20 activities)."""
    result = ActivityAnalysisResult(
        raw_activity_count=15,
        activity_list=[f"A{i}" for i in range(15)],
        count_confidence=0.85,
        counting_rationale="Test",
    )

    hint = get_activity_tier_hint(result)

    assert "Likely M" in hint
    assert "11-20" in hint


def test_get_activity_tier_hint_l_range():
    """Test tier hint for L range (21-40 activities)."""
    result = ActivityAnalysisResult(
        raw_activity_count=30,
        activity_list=[f"A{i}" for i in range(30)],
        count_confidence=0.8,
        counting_rationale="Test",
    )

    hint = get_activity_tier_hint(result)

    assert "Likely L" in hint
    assert "21-40" in hint


def test_get_activity_tier_hint_xl_range():
    """Test tier hint for XL range (41-60 activities)."""
    result = ActivityAnalysisResult(
        raw_activity_count=50,
        activity_list=[f"A{i}" for i in range(50)],
        count_confidence=0.7,
        counting_rationale="Test",
    )

    hint = get_activity_tier_hint(result)

    assert "Likely XL" in hint
    assert "41-60" in hint


def test_get_activity_tier_hint_exceeds_xl():
    """Test tier hint for counts exceeding XL ceiling."""
    result = ActivityAnalysisResult(
        raw_activity_count=65,
        activity_list=[f"A{i}" for i in range(65)],
        count_confidence=0.6,
        counting_rationale="Test",
    )

    hint = get_activity_tier_hint(result)

    assert "Exceeds XL ceiling" in hint
    assert "Tech Lead review" in hint


# ==================== INTEGRATION TESTS ====================


@pytest.mark.integration
def test_analyze_activities_integration(sample_process_docx: Path):
    """Integration test with real DOCX parsing."""
    # Parse the document
    parsed_doc = parse_docx(sample_process_docx)
    assert parsed_doc.is_valid()

    # Identify sections
    sections = identify_sections(parsed_doc)
    assert len(sections) > 0

    # Analyze activities (will use real LLM)
    result = analyze_activities(sections, session_id="test_integration")

    # Verify result structure
    assert isinstance(result, ActivityAnalysisResult)
    assert result.raw_activity_count >= 0
    assert len(result.activity_list) >= 0
    assert 0.0 <= result.count_confidence <= 1.0
    assert result.counting_rationale != ""

    # Log results for inspection
    print(f"\nActivities found: {result.raw_activity_count}")
    print(f"Confidence: {result.count_confidence:.2f}")
    print(f"Rationale: {result.counting_rationale}")
    if result.activity_list:
        print("Activity list:")
        for i, activity in enumerate(result.activity_list, 1):
            print(f"  {i}. {activity}")
    if result.ambiguous_items:
        print("Ambiguous items:")
        for item in result.ambiguous_items:
            print(f"  - {item}")
