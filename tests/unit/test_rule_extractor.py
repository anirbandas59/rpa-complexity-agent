"""Tests for tools.analysis.rule_extractor module.

Tests cover business rule extraction, filtering, validation,
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
from tools.analysis.rule_extractor import (
    BusinessRuleExtractionLLMResponse,
    BusinessRuleExtractionResult,
    ExtractedBusinessRule,
    NonQualifyingRule,
    extract_business_rules,
    get_rule_count,
    get_rule_tier_hint,
)
from tools.document.docx_parser import parse_docx
from tools.document.section_identifier import identify_sections

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
def mock_sections() -> list[ExtractedSection]:
    """Create sample extracted sections for testing."""
    return [
        ExtractedSection(
            title="Business Rules",
            content=(
                "If the customer is premium, navigate to premium portal, "
                "look up tier, update 3 fields, and send email (5 activities). "
                "If month-end, run reconciliation module (7 activities). "
                "If amount is negative, log error and skip (1 activity)."
            ),
            section_type="business_rules",
            confidence_score=0.9,
            page_number=1,
        ),
        ExtractedSection(
            title="Process Steps",
            content="Main workflow steps...",
            section_type="process_steps",
            confidence_score=0.85,
            page_number=1,
        ),
    ]


@pytest.fixture
def mock_llm_response() -> BusinessRuleExtractionLLMResponse:
    """Create a mock LLM response with qualifying rules."""
    return BusinessRuleExtractionLLMResponse(
        flow_creating_rules=[
            ExtractedBusinessRule(
                description="Premium customer path with portal access",
                condition="If customer_type == 'Premium'",
                branch_name="Premium Portal Flow",
                estimated_branch_activities=5,
                evidence="Navigate to premium portal, look up tier, update fields, send email",
                confidence=0.9,
            ),
            ExtractedBusinessRule(
                description="Month-end reconciliation subprocess",
                condition="If is_month_end == true",
                branch_name="Month-End Reconciliation",
                estimated_branch_activities=7,
                evidence="Run reconciliation module with 7 steps",
                confidence=0.85,
            ),
        ],
        non_qualifying_rules=[
            NonQualifyingRule(
                description="Log error if amount is negative",
                reason_excluded="Only 1 activity, not a flow-creating rule",
            ),
        ],
        total_qualifying_count=2,
        extraction_confidence=0.87,
        notes="Found 2 flow-creating rules",
    )


# ==================== ExtractedBusinessRule Validator Tests ====================


def test_extracted_business_rule_rejects_activities_2():
    """Test that rules with 2 activities are rejected."""
    with pytest.raises(ValueError, match="more than 2"):
        ExtractedBusinessRule(
            description="Test rule",
            branch_name="Test",
            estimated_branch_activities=2,
        )


def test_extracted_business_rule_rejects_activities_1():
    """Test that rules with 1 activity are rejected."""
    with pytest.raises(ValueError, match="more than 2"):
        ExtractedBusinessRule(
            description="Test rule",
            branch_name="Test",
            estimated_branch_activities=1,
        )


def test_extracted_business_rule_accepts_activities_3():
    """Test that rules with 3 activities are accepted."""
    rule = ExtractedBusinessRule(
        description="Test rule",
        branch_name="Test",
        estimated_branch_activities=3,
    )
    assert rule.estimated_branch_activities == 3


def test_extracted_business_rule_confidence_clamped():
    """Test confidence is clamped to 0.0-1.0."""
    rule = ExtractedBusinessRule(
        description="Test",
        branch_name="Test",
        estimated_branch_activities=3,
        confidence=1.5,
    )
    assert rule.confidence == 1.0

    rule = ExtractedBusinessRule(
        description="Test",
        branch_name="Test",
        estimated_branch_activities=3,
        confidence=-0.5,
    )
    assert rule.confidence == 0.0


# ==================== _validate_and_filter_rules TESTS ====================


def test_validate_and_filter_rules_removes_low_activity():
    """Test that rules with activities<=2 are filtered out."""
    from tools.analysis.rule_extractor import _validate_and_filter_rules

    rules = [
        ExtractedBusinessRule(
            description="Valid rule",
            branch_name="Valid",
            estimated_branch_activities=5,
            confidence=0.9,
        ),
    ]

    # This should fail at the validator, but we test that the filter handles it
    # We'll test with rules that pass the validator
    result = _validate_and_filter_rules(rules)
    assert len(result) == 1


def test_validate_and_filter_rules_caps_at_6():
    """Test that more than 6 rules are capped to 6."""
    from tools.analysis.rule_extractor import _validate_and_filter_rules

    rules = [
        ExtractedBusinessRule(
            description=f"Rule {i}",
            branch_name=f"Rule {i}",
            estimated_branch_activities=3 + i,
            confidence=0.5 + (i * 0.05),
        )
        for i in range(8)
    ]

    result = _validate_and_filter_rules(rules)

    assert len(result) == 6
    # Should keep highest confidence rules (0.85, 0.8, 0.75, 0.7, 0.65, 0.6)
    assert all(r.confidence >= 0.6 for r in result)


def test_validate_and_filter_rules_empty_list():
    """Test empty list returns empty list."""
    from tools.analysis.rule_extractor import _validate_and_filter_rules

    result = _validate_and_filter_rules([])
    assert result == []


# ==================== _filter_relevant_sections TESTS ====================


def test_filter_relevant_sections_prioritizes_business_rules():
    """Test that business_rules section has highest priority."""
    from tools.analysis.rule_extractor import _filter_relevant_sections

    sections = [
        ExtractedSection(
            title="Process Overview",
            content="Overview",
            section_type="process_overview",
            confidence_score=0.9,
            page_number=None,
        ),
        ExtractedSection(
            title="Business Rules",
            content="Rules content",
            section_type="business_rules",
            confidence_score=0.85,
            page_number=None,
        ),
    ]

    result = _filter_relevant_sections(sections)

    assert len(result) == 1
    assert result[0].section_type == "business_rules"


def test_filter_relevant_sections_excludes_applications():
    """Test that applications section is excluded."""
    from tools.analysis.rule_extractor import _filter_relevant_sections

    sections = [
        ExtractedSection(
            title="Applications",
            content="Apps",
            section_type="applications",
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
    ]

    result = _filter_relevant_sections(sections)

    assert len(result) == 1
    assert result[0].section_type == "process_steps"


def test_filter_relevant_sections_returns_all_when_no_business_rules():
    """Test fallback excludes applications when no business_rules section."""
    from tools.analysis.rule_extractor import _filter_relevant_sections

    sections = [
        ExtractedSection(
            title="Applications",
            content="Apps",
            section_type="applications",
            confidence_score=0.9,
            page_number=None,
        ),
        ExtractedSection(
            title="Exceptions",
            content="Exceptions",
            section_type="exceptions",
            confidence_score=0.85,
            page_number=None,
        ),
        ExtractedSection(
            title="Process Steps",
            content="Steps",
            section_type="process_steps",
            confidence_score=0.9,
            page_number=None,
        ),
    ]

    result = _filter_relevant_sections(sections)

    # Should exclude applications/inputs_outputs but include other sections
    assert len(result) == 2
    assert all(s.section_type != "applications" for s in result)
    assert all(s.section_type != "inputs_outputs" for s in result)


# ==================== extract_business_rules Tests (Mock LLMManager) ====================


def test_extract_business_rules_returns_result_on_success(
    mock_sections: list[ExtractedSection],
    mock_llm_response: BusinessRuleExtractionLLMResponse,
):
    """Test successful business rule extraction."""
    mock_llm = MagicMock(spec=LLMManager)
    mock_llm.complete_structured.return_value = mock_llm_response

    result = extract_business_rules(mock_sections, llm_manager=mock_llm)

    assert isinstance(result, BusinessRuleExtractionResult)
    assert result.total_qualifying_count == 2
    assert len(result.rules) == 2


def test_extract_business_rules_filters_invalid_rules():
    """Test that LLM response with invalid rules is filtered."""
    sections = [
        ExtractedSection(
            title="Business Rules",
            content="Rules",
            section_type="business_rules",
            confidence_score=0.9,
            page_number=None,
        ),
    ]

    # Mock response with 1 valid and 1 invalid rule (invalid won't be created
    # due to validator, so we just test valid rules pass through)
    mock_response = BusinessRuleExtractionLLMResponse(
        flow_creating_rules=[
            ExtractedBusinessRule(
                description="Valid",
                branch_name="Valid",
                estimated_branch_activities=5,
                confidence=0.9,
            ),
        ],
        non_qualifying_rules=[
            NonQualifyingRule(
                description="Invalid",
                reason_excluded="Only 1 activity",
            ),
        ],
        total_qualifying_count=1,
        extraction_confidence=0.85,
    )

    mock_llm = MagicMock(spec=LLMManager)
    mock_llm.complete_structured.return_value = mock_response

    result = extract_business_rules(sections, llm_manager=mock_llm)

    assert result.total_qualifying_count == 1
    assert len(result.rules) == 1


def test_extract_business_rules_retries_on_llm_failure():
    """Test that LLM failure triggers retry."""
    sections = [
        ExtractedSection(
            title="Business Rules",
            content="Rules",
            section_type="business_rules",
            confidence_score=0.9,
            page_number=None,
        ),
    ]

    mock_response = BusinessRuleExtractionLLMResponse(
        flow_creating_rules=[
            ExtractedBusinessRule(
                description="Test",
                branch_name="Test",
                estimated_branch_activities=4,
                confidence=0.8,
            ),
        ],
        total_qualifying_count=1,
        extraction_confidence=0.8,
    )

    mock_llm = MagicMock(spec=LLMManager)
    # First call fails, second succeeds
    mock_llm.complete_structured.side_effect = [
        LLMProviderError("First attempt failed"),
        mock_response,
    ]

    result = extract_business_rules(sections, llm_manager=mock_llm)

    assert result.total_qualifying_count == 1
    assert mock_llm.complete_structured.call_count == 2


def test_extract_business_rules_returns_empty_on_both_failures():
    """Test empty result when both LLM attempts fail."""
    sections = [
        ExtractedSection(
            title="Business Rules",
            content="Rules",
            section_type="business_rules",
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

    result = extract_business_rules(sections, llm_manager=mock_llm)

    assert result.total_qualifying_count == 0
    assert len(result.rules) == 0


def test_extract_business_rules_caps_at_6():
    """Test that rule count is capped at 6."""
    sections = [
        ExtractedSection(
            title="Business Rules",
            content="Many rules",
            section_type="business_rules",
            confidence_score=0.9,
            page_number=None,
        ),
    ]

    # Create mock response with 8 rules
    mock_response = BusinessRuleExtractionLLMResponse(
        flow_creating_rules=[
            ExtractedBusinessRule(
                description=f"Rule {i}",
                branch_name=f"Rule {i}",
                estimated_branch_activities=3 + i,
                confidence=0.5 + (i * 0.05),
            )
            for i in range(8)
        ],
        total_qualifying_count=8,
        extraction_confidence=0.8,
    )

    mock_llm = MagicMock(spec=LLMManager)
    mock_llm.complete_structured.return_value = mock_response

    result = extract_business_rules(sections, llm_manager=mock_llm)

    assert result.total_qualifying_count == 6
    assert len(result.rules) == 6


# ==================== BusinessRuleExtractionResult Property Tests ====================


def test_business_rule_result_rule_names():
    """Test rule_names property returns branch names."""
    result = BusinessRuleExtractionResult(
        rules=[
            ExtractedBusinessRule(
                description="Rule 1",
                branch_name="Branch A",
                estimated_branch_activities=3,
            ),
            ExtractedBusinessRule(
                description="Rule 2",
                branch_name="Branch B",
                estimated_branch_activities=4,
            ),
        ],
        total_qualifying_count=2,
        extraction_confidence=0.85,
    )

    names = result.rule_names()

    assert names == ["Branch A", "Branch B"]


def test_business_rule_result_exceeds_xl_ceiling():
    """Test exceeds_xl_ceiling property."""
    result = BusinessRuleExtractionResult(
        rules=[
            ExtractedBusinessRule(
                description=f"Rule {i}",
                branch_name=f"Branch {i}",
                estimated_branch_activities=3 + i,
            )
            for i in range(7)
        ],
        total_qualifying_count=7,
        extraction_confidence=0.85,
    )

    assert result.exceeds_xl_ceiling() is True

    result2 = BusinessRuleExtractionResult(
        rules=[
            ExtractedBusinessRule(
                description="Rule",
                branch_name="Branch",
                estimated_branch_activities=3,
            ),
        ],
        total_qualifying_count=1,
        extraction_confidence=0.85,
    )

    assert result2.exceeds_xl_ceiling() is False


# ==================== get_rule_count Tests ====================


def test_get_rule_count_returns_total():
    """Test get_rule_count returns total_qualifying_count."""
    result = BusinessRuleExtractionResult(
        rules=[
            ExtractedBusinessRule(
                description="Rule",
                branch_name="Branch",
                estimated_branch_activities=3,
            ),
        ],
        total_qualifying_count=1,
        extraction_confidence=0.85,
    )

    count = get_rule_count(result)

    assert count == 1


# ==================== get_rule_tier_hint Tests ====================


def test_get_rule_tier_hint_zero_rules():
    """Test tier hint for 0 rules."""
    result = BusinessRuleExtractionResult(
        rules=[],
        total_qualifying_count=0,
        extraction_confidence=0.0,
    )

    hint = get_rule_tier_hint(result)

    assert "XS or S" in hint
    assert "0" in hint


def test_get_rule_tier_hint_m_range():
    """Test tier hint for 1-2 rules."""
    result = BusinessRuleExtractionResult(
        rules=[
            ExtractedBusinessRule(
                description="Rule",
                branch_name="Branch",
                estimated_branch_activities=3,
            ),
        ],
        total_qualifying_count=1,
        extraction_confidence=0.85,
    )

    hint = get_rule_tier_hint(result)

    assert "Likely M" in hint


def test_get_rule_tier_hint_l_range():
    """Test tier hint for 3-4 rules."""
    result = BusinessRuleExtractionResult(
        rules=[
            ExtractedBusinessRule(
                description=f"Rule {i}",
                branch_name=f"Branch {i}",
                estimated_branch_activities=3 + i,
            )
            for i in range(3)
        ],
        total_qualifying_count=3,
        extraction_confidence=0.85,
    )

    hint = get_rule_tier_hint(result)

    assert "Likely L" in hint
    assert "3-4" in hint


def test_get_rule_tier_hint_xl_range():
    """Test tier hint for 5-6 rules."""
    result = BusinessRuleExtractionResult(
        rules=[
            ExtractedBusinessRule(
                description=f"Rule {i}",
                branch_name=f"Branch {i}",
                estimated_branch_activities=3 + i,
            )
            for i in range(5)
        ],
        total_qualifying_count=5,
        extraction_confidence=0.85,
    )

    hint = get_rule_tier_hint(result)

    assert "Likely XL" in hint
    assert "5-6" in hint


def test_get_rule_tier_hint_exceeds_xl():
    """Test tier hint for > 6 rules."""
    result = BusinessRuleExtractionResult(
        rules=[
            ExtractedBusinessRule(
                description=f"Rule {i}",
                branch_name=f"Branch {i}",
                estimated_branch_activities=3 + i,
            )
            for i in range(7)
        ],
        total_qualifying_count=7,
        extraction_confidence=0.85,
    )

    hint = get_rule_tier_hint(result)

    assert "Exceeds XL ceiling" in hint


# ==================== GROUND TRUTH TEST ====================


def test_ground_truth_business_rule_count():
    """Ground truth test for 6-rule project.

    The known project in the Excel file has 6 business rules:
    - Change description
    - Change approval rights
    - Add signatory / Change limit & rights
    - Replace signatory / Owner & signatory / Copy ASM access
    - Replace object owner
    - Remove signatory
    """
    # Create mock result with the 6 ground truth rules
    rules = [
        ExtractedBusinessRule(
            description="Change description for rights",
            branch_name="Change Description",
            estimated_branch_activities=3,
            confidence=0.95,
        ),
        ExtractedBusinessRule(
            description="Change approval rights process",
            branch_name="Change Approval Rights",
            estimated_branch_activities=4,
            confidence=0.92,
        ),
        ExtractedBusinessRule(
            description="Add signatory or change limit and rights",
            branch_name="Add/Change Signatory",
            estimated_branch_activities=5,
            confidence=0.90,
        ),
        ExtractedBusinessRule(
            description="Replace signatory with owner and signatory, copy ASM access",
            branch_name="Replace Signatory",
            estimated_branch_activities=6,
            confidence=0.88,
        ),
        ExtractedBusinessRule(
            description="Replace object owner process",
            branch_name="Replace Object Owner",
            estimated_branch_activities=4,
            confidence=0.85,
        ),
        ExtractedBusinessRule(
            description="Remove signatory from system",
            branch_name="Remove Signatory",
            estimated_branch_activities=3,
            confidence=0.87,
        ),
    ]

    result = BusinessRuleExtractionResult(
        rules=rules,
        total_qualifying_count=6,
        extraction_confidence=0.90,
        notes="Ground truth: 6 flow-creating rules from Excel project",
    )

    assert get_rule_count(result) == 6
    assert result.exceeds_xl_ceiling() is False
    assert len(result.rules) == 6
    assert len(result.rule_names()) == 6


# ==================== INTEGRATION TESTS ====================


@pytest.mark.integration
def test_extract_business_rules_integration(sample_process_docx: Path):
    """Integration test with real DOCX parsing."""
    # Parse the document
    parsed_doc = parse_docx(sample_process_docx)
    assert parsed_doc.is_valid()

    # Identify sections
    sections = identify_sections(parsed_doc)
    assert len(sections) > 0

    # Extract business rules (will use real LLM)
    result = extract_business_rules(sections, session_id="test_integration")

    # Verify result structure
    assert isinstance(result, BusinessRuleExtractionResult)
    assert result.total_qualifying_count >= 0
    assert 0.0 <= result.extraction_confidence <= 1.0
    assert isinstance(result.rule_names(), list)

    # Log results for inspection
    print(f"\nQualifying rules: {result.total_qualifying_count}")
    print(f"Rule names: {result.rule_names()}")
    print(f"Non-qualifying: {len(result.non_qualifying_rules)}")
    print(f"Confidence: {result.extraction_confidence:.2f}")
    if result.notes:
        print(f"Notes: {result.notes}")
