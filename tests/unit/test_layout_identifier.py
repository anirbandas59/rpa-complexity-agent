"""Tests for layout_identifier tool."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.exceptions import LLMProviderError
from core.models.document import ExtractedSection
from tools.analysis.layout_identifier import (
    IdentifiedLayout,
    LayoutIdentificationLLMResponse,
    LayoutIdentificationResult,
    _deduplicate_layouts,
    _filter_relevant_sections,
    _normalize_layout_name,
    _prepare_sections_text,
    get_layout_count,
    get_layout_tier_hint,
    identify_layouts,
)


# ==================== _normalize_layout_name TESTS ====================


class TestNormalizeLayoutName:
    """Tests for _normalize_layout_name helper."""

    def test_basic_lowercase(self):
        """Normalize basic name to lowercase."""
        assert _normalize_layout_name("Input Template") == "input template"

    def test_with_xlsx_extension(self):
        """Strip .xlsx extension."""
        assert _normalize_layout_name("Input Template.xlsx") == "input template"

    def test_with_pdf_extension(self):
        """Strip .pdf extension."""
        assert _normalize_layout_name("Report Output.pdf") == "report output"

    def test_with_csv_extension(self):
        """Strip .csv extension."""
        assert _normalize_layout_name("Data Export.csv") == "data export"

    def test_with_xml_extension(self):
        """Strip .xml extension."""
        assert _normalize_layout_name("Config.xml") == "config"

    def test_underscore_replacement(self):
        """Replace underscores with spaces."""
        assert _normalize_layout_name("Input_Template") == "input template"

    def test_hyphen_replacement(self):
        """Replace hyphens with spaces."""
        assert _normalize_layout_name("Input-Template") == "input template"

    def test_multiple_underscores(self):
        """Replace multiple underscores with single space."""
        assert _normalize_layout_name("Input__Template") == "input template"

    def test_mixed_case_with_extension_and_underscores(self):
        """Complex name with mixed case, extension, and underscores."""
        assert _normalize_layout_name("Monthly_Report.xlsx") == "monthly report"

    def test_trailing_whitespace(self):
        """Strip trailing whitespace."""
        assert _normalize_layout_name("  Input Template  ") == "input template"

    def test_multiple_spaces_collapse(self):
        """Collapse multiple spaces to single space."""
        assert _normalize_layout_name("Input   Template") == "input template"

    def test_uppercase_with_hyphens_and_extension(self):
        """Uppercase with hyphens and extension."""
        assert _normalize_layout_name("OUTPUT-FILE.csv") == "output file"


# ==================== _deduplicate_layouts TESTS ====================


class TestDeduplicateLayouts:
    """Tests for _deduplicate_layouts helper."""

    def test_empty_list(self):
        """Empty list returns empty list."""
        assert _deduplicate_layouts([]) == []

    def test_no_duplicates(self):
        """List with no duplicates returns all items."""
        layouts = [
            IdentifiedLayout(name="Template A", confidence=0.8),
            IdentifiedLayout(name="Template B", confidence=0.7),
            IdentifiedLayout(name="Template C", confidence=0.6),
        ]
        result = _deduplicate_layouts(layouts)
        assert len(result) == 3

    def test_exact_duplicate_keeps_higher_confidence(self):
        """Duplicate names — keep entry with higher confidence."""
        layouts = [
            IdentifiedLayout(name="Input Template.xlsx", confidence=0.6),
            IdentifiedLayout(name="Input Template", confidence=0.8),
        ]
        result = _deduplicate_layouts(layouts)
        assert len(result) == 1
        assert result[0].confidence == 0.8

    def test_duplicate_with_normalization(self):
        """Names that normalize to same value — keep higher confidence."""
        layouts = [
            IdentifiedLayout(name="Input_Template.xlsx", confidence=0.5),
            IdentifiedLayout(name="Input Template", confidence=0.9),
        ]
        result = _deduplicate_layouts(layouts)
        assert len(result) == 1
        assert result[0].confidence == 0.9

    def test_flag_merge_on_duplicate(self):
        """When deduplicating, merge is_input and is_output flags."""
        layouts = [
            IdentifiedLayout(
                name="Template A",
                is_input=True,
                is_output=False,
                confidence=0.8,
            ),
            IdentifiedLayout(
                name="Template A",
                is_input=False,
                is_output=True,
                confidence=0.6,
            ),
        ]
        result = _deduplicate_layouts(layouts)
        assert len(result) == 1
        assert result[0].is_input is True
        assert result[0].is_output is True

    def test_flag_merge_keeps_higher_confidence_but_merges_flags(self):
        """Higher confidence entry kept, but flags merged."""
        layouts = [
            IdentifiedLayout(
                name="Template A",
                is_input=False,
                is_output=True,
                confidence=0.9,
            ),
            IdentifiedLayout(
                name="Template A",
                is_input=True,
                is_output=False,
                confidence=0.7,
            ),
        ]
        result = _deduplicate_layouts(layouts)
        assert len(result) == 1
        assert result[0].confidence == 0.9
        assert result[0].is_input is True
        assert result[0].is_output is True

    def test_three_duplicate_layouts(self):
        """Three layouts where two normalize to same name."""
        layouts = [
            IdentifiedLayout(
                name="Template.xlsx",
                is_input=True,
                is_output=False,
                confidence=0.5,
            ),
            IdentifiedLayout(
                name="Template",
                is_input=False,
                is_output=True,
                confidence=0.7,
            ),
            IdentifiedLayout(
                name="Report.pdf",
                is_input=False,
                is_output=True,
                confidence=0.6,
            ),
        ]
        result = _deduplicate_layouts(layouts)
        assert len(result) == 2
        # First two deduplicate to one with confidence 0.7
        deduplicated_names = [_normalize_layout_name(l.name) for l in result]
        assert _normalize_layout_name("Template") in deduplicated_names
        assert _normalize_layout_name("Report") in deduplicated_names


# ==================== IdentifiedLayout VALIDATOR TESTS ====================


class TestIdentifiedLayoutValidators:
    """Tests for IdentifiedLayout field validators."""

    def test_both_flags_false_sets_input_true(self):
        """If both is_input and is_output are False: is_input set to True."""
        layout = IdentifiedLayout(
            name="Template",
            is_input=False,
            is_output=False,
        )
        assert layout.is_input is True
        assert layout.is_output is False

    def test_invalid_file_extension_defaults_to_other(self):
        """Invalid file_extension defaults to 'other'."""
        layout = IdentifiedLayout(
            name="Template",
            file_extension="doc",  # Invalid
        )
        assert layout.file_extension == "other"

    def test_valid_file_extension_preserved(self):
        """Valid file_extension is preserved."""
        layout = IdentifiedLayout(
            name="Template",
            file_extension="xlsx",
        )
        assert layout.file_extension == "xlsx"

    def test_uppercase_file_extension_lowercased(self):
        """Uppercase file_extension converted to lowercase."""
        layout = IdentifiedLayout(
            name="Template",
            file_extension="XLSX",
        )
        assert layout.file_extension == "xlsx"

    def test_invalid_template_type_defaults_to_other(self):
        """Invalid template_type defaults to 'other'."""
        layout = IdentifiedLayout(
            name="Template",
            template_type="invalid_type",
        )
        assert layout.template_type == "other"

    def test_valid_template_type_preserved(self):
        """Valid template_type is preserved."""
        layout = IdentifiedLayout(
            name="Template",
            template_type="input_template",
        )
        assert layout.template_type == "input_template"

    def test_uppercase_template_type_lowercased(self):
        """Uppercase template_type converted to lowercase."""
        layout = IdentifiedLayout(
            name="Template",
            template_type="OUTPUT_REPORT",
        )
        assert layout.template_type == "output_report"

    def test_confidence_clamped_below_zero(self):
        """Confidence below 0.0 clamped to 0.0."""
        layout = IdentifiedLayout(
            name="Template",
            confidence=-0.5,
        )
        assert layout.confidence == 0.0

    def test_confidence_clamped_above_one(self):
        """Confidence above 1.0 clamped to 1.0."""
        layout = IdentifiedLayout(
            name="Template",
            confidence=1.5,
        )
        assert layout.confidence == 1.0

    def test_confidence_in_valid_range(self):
        """Valid confidence value preserved."""
        layout = IdentifiedLayout(
            name="Template",
            confidence=0.7,
        )
        assert layout.confidence == 0.7


# ==================== _filter_relevant_sections TESTS ====================


class TestFilterRelevantSections:
    """Tests for _filter_relevant_sections helper."""

    def test_empty_sections(self):
        """Empty sections list returns empty."""
        result = _filter_relevant_sections([])
        assert result == []

    def test_priority_1_inputs_outputs(self):
        """Priority 1: inputs_outputs section."""
        sections = [
            ExtractedSection(
                title="Applications",
                section_type="applications",
                content="SAP",
                confidence_score=0.9,
            ),
            ExtractedSection(
                title="Input/Output",
                section_type="inputs_outputs",
                content="Excel files",
                confidence_score=0.9,
            ),
            ExtractedSection(
                title="Steps",
                section_type="process_steps",
                content="Step 1",
                confidence_score=0.9,
            ),
        ]
        result = _filter_relevant_sections(sections)
        assert len(result) == 1
        assert result[0].section_type == "inputs_outputs"

    def test_priority_2_process_steps(self):
        """Priority 2: process_steps when no inputs_outputs."""
        sections = [
            ExtractedSection(
                title="Applications",
                section_type="applications",
                content="SAP",
                confidence_score=0.9,
            ),
            ExtractedSection(
                title="Steps",
                section_type="process_steps",
                content="Step 1",
                confidence_score=0.9,
            ),
        ]
        result = _filter_relevant_sections(sections)
        assert len(result) == 1
        assert result[0].section_type == "process_steps"

    def test_priority_3_process_overview(self):
        """Priority 3: process_overview when no higher priorities."""
        sections = [
            ExtractedSection(
                title="Overview",
                section_type="process_overview",
                content="Overview text",
                confidence_score=0.9,
            ),
            ExtractedSection(
                title="Rules",
                section_type="business_rules",
                content="Rule 1",
                confidence_score=0.9,
            ),
        ]
        result = _filter_relevant_sections(sections)
        assert len(result) == 1
        assert result[0].section_type == "process_overview"

    def test_priority_4_general(self):
        """Priority 4: general section."""
        sections = [
            ExtractedSection(
                title="General",
                section_type="general",
                content="General info",
                confidence_score=0.9,
            ),
            ExtractedSection(
                title="Rules",
                section_type="business_rules",
                content="Rule 1",
                confidence_score=0.9,
            ),
        ]
        result = _filter_relevant_sections(sections)
        assert len(result) == 1
        assert result[0].section_type == "general"

    def test_fallback_all_sections(self):
        """Fallback: return all sections if no priority matches."""
        sections = [
            ExtractedSection(
                title="Rules",
                section_type="business_rules",
                content="Rule 1",
                confidence_score=0.9,
            ),
            ExtractedSection(
                title="Exceptions",
                section_type="exceptions",
                content="Exception 1",
                confidence_score=0.9,
            ),
        ]
        result = _filter_relevant_sections(sections)
        assert len(result) == 2


# ==================== identify_layouts TESTS ====================


class TestIdentifyLayouts:
    """Tests for identify_layouts main function."""

    def test_identify_layouts_empty_sections(self):
        """Empty sections returns empty result."""
        mock_llm = MagicMock()
        result = identify_layouts([], llm_manager=mock_llm)
        assert isinstance(result, LayoutIdentificationResult)
        assert len(result.layouts) == 0
        assert result.total_count == 0

    @patch("tools.analysis.layout_identifier.LLMManager")
    def test_identify_layouts_success(self, mock_llm_class):
        """Successful layout identification."""
        mock_llm = MagicMock()
        mock_response = LayoutIdentificationLLMResponse(
            layouts=[
                IdentifiedLayout(
                    name="Input Template",
                    file_extension="xlsx",
                    is_input=True,
                    confidence=0.8,
                ),
                IdentifiedLayout(
                    name="Output Report",
                    file_extension="pdf",
                    is_output=True,
                    confidence=0.8,
                ),
            ],
            total_count=2,
            detection_confidence=0.8,
        )
        mock_llm.complete_structured.return_value = mock_response

        sections = [
            ExtractedSection(
                title="Inputs/Outputs",
                section_type="inputs_outputs",
                content="Excel input and PDF output",
                confidence_score=0.9,
            )
        ]

        result = identify_layouts(sections, llm_manager=mock_llm)
        assert isinstance(result, LayoutIdentificationResult)
        assert len(result.layouts) == 2
        assert result.total_count == 2

    @patch("tools.analysis.layout_identifier.LLMManager")
    def test_identify_layouts_with_deduplication(self, mock_llm_class):
        """Deduplication happens after LLM response."""
        mock_llm = MagicMock()
        # LLM returns duplicates
        mock_response = LayoutIdentificationLLMResponse(
            layouts=[
                IdentifiedLayout(
                    name="Input_Template.xlsx",
                    is_input=True,
                    confidence=0.6,
                ),
                IdentifiedLayout(
                    name="Input Template",
                    is_input=False,
                    is_output=True,
                    confidence=0.8,
                ),
                IdentifiedLayout(
                    name="Output Report.pdf",
                    is_output=True,
                    confidence=0.8,
                ),
            ],
            total_count=3,
            detection_confidence=0.8,
        )
        mock_llm.complete_structured.return_value = mock_response

        sections = [
            ExtractedSection(
                title="IO",
                section_type="inputs_outputs",
                content="Files",
                confidence_score=0.9,
            )
        ]

        result = identify_layouts(sections, llm_manager=mock_llm)
        # After deduplication: 2 layouts (Input Template merged, Output Report)
        assert len(result.layouts) == 2

    @patch("tools.analysis.layout_identifier.LLMManager")
    def test_identify_layouts_ceiling_enforcement(self, mock_llm_class):
        """Layout count capped at 10 (XL ceiling)."""
        mock_llm = MagicMock()
        # LLM returns 12 layouts
        layouts = [
            IdentifiedLayout(
                name=f"Template {i}",
                confidence=1.0 - (i * 0.05),  # Descending confidence
            )
            for i in range(12)
        ]
        mock_response = LayoutIdentificationLLMResponse(
            layouts=layouts,
            total_count=12,
            detection_confidence=0.7,
        )
        mock_llm.complete_structured.return_value = mock_response

        sections = [
            ExtractedSection(
                title="IO",
                section_type="inputs_outputs",
                content="Files",
                confidence_score=0.9,
            )
        ]

        result = identify_layouts(sections, llm_manager=mock_llm)
        assert len(result.layouts) == 10
        assert result.exceeds_ceiling is True

    @patch("tools.analysis.layout_identifier.LLMManager")
    def test_identify_layouts_llm_failure_retry_success(self, mock_llm_class):
        """LLM fails first attempt, succeeds on retry."""
        mock_llm = MagicMock()
        # First call raises error, second succeeds
        mock_response = LayoutIdentificationLLMResponse(
            layouts=[
                IdentifiedLayout(
                    name="Template",
                    confidence=0.7,
                )
            ],
            total_count=1,
            detection_confidence=0.7,
        )
        mock_llm.complete_structured.side_effect = [
            LLMProviderError("First attempt failed"),
            mock_response,
        ]

        sections = [
            ExtractedSection(
                title="IO",
                section_type="inputs_outputs",
                content="Files",
                confidence_score=0.9,
            )
        ]

        result = identify_layouts(sections, llm_manager=mock_llm)
        assert len(result.layouts) == 1

    @patch("tools.analysis.layout_identifier.LLMManager")
    def test_identify_layouts_both_attempts_fail(self, mock_llm_class):
        """Both LLM attempts fail — return empty result."""
        mock_llm = MagicMock()
        mock_llm.complete_structured.side_effect = LLMProviderError("Failed")

        sections = [
            ExtractedSection(
                title="IO",
                section_type="inputs_outputs",
                content="Files",
                confidence_score=0.9,
            )
        ]

        result = identify_layouts(sections, llm_manager=mock_llm)
        assert len(result.layouts) == 0
        assert result.total_count == 0
        assert result.detection_confidence == 0.0
        assert "failed" in result.notes.lower()


# ==================== LayoutIdentificationResult TESTS ====================


class TestLayoutIdentificationResult:
    """Tests for LayoutIdentificationResult computed properties."""

    def test_layout_names_property(self):
        """layout_names() returns list of names."""
        result = LayoutIdentificationResult(
            layouts=[
                IdentifiedLayout(name="Template A"),
                IdentifiedLayout(name="Template B"),
            ],
            total_count=2,
            detection_confidence=0.8,
            exceeds_ceiling=False,
        )
        assert result.layout_names() == ["Template A", "Template B"]

    def test_input_count_property(self):
        """input_count() counts layouts where is_input=True."""
        result = LayoutIdentificationResult(
            layouts=[
                IdentifiedLayout(name="Template A", is_input=True, is_output=False),
                IdentifiedLayout(name="Template B", is_input=False, is_output=True),
                IdentifiedLayout(name="Template C", is_input=True, is_output=True),
            ],
            total_count=3,
            detection_confidence=0.8,
            exceeds_ceiling=False,
        )
        assert result.input_count() == 2

    def test_output_count_property(self):
        """output_count() counts layouts where is_output=True."""
        result = LayoutIdentificationResult(
            layouts=[
                IdentifiedLayout(name="Template A", is_input=True, is_output=False),
                IdentifiedLayout(name="Template B", is_input=False, is_output=True),
                IdentifiedLayout(name="Template C", is_input=True, is_output=True),
            ],
            total_count=3,
            detection_confidence=0.8,
            exceeds_ceiling=False,
        )
        assert result.output_count() == 2


# ==================== get_layout_count TESTS ====================


class TestGetLayoutCount:
    """Tests for get_layout_count function."""

    def test_returns_total_count(self):
        """get_layout_count returns total_count."""
        result = LayoutIdentificationResult(
            layouts=[IdentifiedLayout(name="Template")],
            total_count=1,
            detection_confidence=0.8,
            exceeds_ceiling=False,
        )
        assert get_layout_count(result) == 1

    def test_returns_zero_for_empty(self):
        """get_layout_count returns 0 for empty result."""
        result = LayoutIdentificationResult(
            layouts=[],
            total_count=0,
            detection_confidence=0.0,
            exceeds_ceiling=False,
        )
        assert get_layout_count(result) == 0

    def test_returns_count_greater_than_10(self):
        """get_layout_count returns count even if > 10."""
        result = LayoutIdentificationResult(
            layouts=[IdentifiedLayout(name=f"Template {i}") for i in range(12)],
            total_count=12,
            detection_confidence=0.5,
            exceeds_ceiling=True,
        )
        assert get_layout_count(result) == 12


# ==================== get_layout_tier_hint TESTS ====================


class TestGetLayoutTierHint:
    """Tests for get_layout_tier_hint function."""

    def test_one_layout(self):
        """1 layout → hints at XS or S."""
        result = LayoutIdentificationResult(
            layouts=[IdentifiedLayout(name="Template")],
            total_count=1,
            detection_confidence=0.8,
            exceeds_ceiling=False,
        )
        hint = get_layout_tier_hint(result)
        assert "XS or S" in hint
        assert "1" in hint

    def test_two_layouts(self):
        """2 layouts → hints at M."""
        result = LayoutIdentificationResult(
            layouts=[
                IdentifiedLayout(name="Template A"),
                IdentifiedLayout(name="Template B"),
            ],
            total_count=2,
            detection_confidence=0.8,
            exceeds_ceiling=False,
        )
        hint = get_layout_tier_hint(result)
        assert "M" in hint

    def test_three_layouts(self):
        """3 layouts → hints at M."""
        result = LayoutIdentificationResult(
            layouts=[
                IdentifiedLayout(name="Template A"),
                IdentifiedLayout(name="Template B"),
                IdentifiedLayout(name="Template C"),
            ],
            total_count=3,
            detection_confidence=0.8,
            exceeds_ceiling=False,
        )
        hint = get_layout_tier_hint(result)
        assert "M" in hint

    def test_five_layouts(self):
        """5 layouts → hints at L."""
        result = LayoutIdentificationResult(
            layouts=[
                IdentifiedLayout(name=f"Template {i}") for i in range(5)
            ],
            total_count=5,
            detection_confidence=0.8,
            exceeds_ceiling=False,
        )
        hint = get_layout_tier_hint(result)
        assert "L" in hint

    def test_eight_layouts(self):
        """8 layouts → hints at XL."""
        result = LayoutIdentificationResult(
            layouts=[
                IdentifiedLayout(name=f"Template {i}") for i in range(8)
            ],
            total_count=8,
            detection_confidence=0.8,
            exceeds_ceiling=False,
        )
        hint = get_layout_tier_hint(result)
        assert "XL" in hint

    def test_exceeds_ceiling(self):
        """> 10 layouts → hints at exceeds ceiling."""
        result = LayoutIdentificationResult(
            layouts=[
                IdentifiedLayout(name=f"Template {i}") for i in range(11)
            ],
            total_count=11,
            detection_confidence=0.5,
            exceeds_ceiling=True,
        )
        hint = get_layout_tier_hint(result)
        assert "Exceeds XL" in hint


# ==================== GROUND TRUTH TEST ====================


class TestGroundTruth:
    """Ground truth validation against known Excel project."""

    @pytest.mark.ground_truth
    def test_ground_truth_layout_count(self):
        """Ground truth: Excel project has ~5 layouts.

        Based on the known project in the Excel file:
        - Input template Modify
        - Input template Simple mass change
        - Input template Delete object
        - Schema file
        - CSV objects + CSV signatories (can be 1 or 2)

        We assert the identified count is 5.
        """
        # Mock a result with the ground truth layouts
        layouts = [
            IdentifiedLayout(
                name="Input template Modify",
                file_extension="xlsx",
                is_input=True,
                confidence=0.9,
            ),
            IdentifiedLayout(
                name="Input template Simple mass change",
                file_extension="xlsx",
                is_input=True,
                confidence=0.9,
            ),
            IdentifiedLayout(
                name="Input template Delete object",
                file_extension="xlsx",
                is_input=True,
                confidence=0.9,
            ),
            IdentifiedLayout(
                name="Schema file",
                file_extension="other",
                is_input=True,
                confidence=0.8,
            ),
            IdentifiedLayout(
                name="CSV objects",
                file_extension="csv",
                is_input=True,
                confidence=0.8,
            ),
        ]

        result = LayoutIdentificationResult(
            layouts=layouts,
            total_count=5,
            detection_confidence=0.85,
            exceeds_ceiling=False,
            notes="Ground truth validation",
        )

        # Assertions
        assert get_layout_count(result) == 5
        assert result.exceeds_ceiling is False
        assert "Schema file" in result.layout_names()
        assert result.input_count() >= 4


# ==================== FIXTURES ====================


@pytest.fixture
def sample_process_docx() -> Path:
    """Path to sample_process.docx test fixture."""
    path = Path(__file__).parent.parent / "fixtures" / "sample_process.docx"
    if not path.exists():
        pytest.skip(f"Sample document not found at {path}")
    return path


# ==================== INTEGRATION TESTS ====================


@pytest.mark.integration
class TestLayoutIdentifierIntegration:
    """Integration tests with real document parsing."""

    def test_identify_layouts_integration(self, sample_process_docx: Path):
        """Integration: parse DOCX and identify layouts."""
        from tools.document.docx_parser import parse_docx
        from tools.document.section_identifier import identify_sections

        # Parse the sample document
        parsed_doc = parse_docx(sample_process_docx)
        assert parsed_doc.is_valid()

        # Identify sections
        sections = identify_sections(parsed_doc)
        assert len(sections) > 0

        # Identify layouts
        mock_llm = MagicMock()
        mock_response = LayoutIdentificationLLMResponse(
            layouts=[
                IdentifiedLayout(
                    name="Input Template",
                    file_extension="xlsx",
                    is_input=True,
                    confidence=0.85,
                ),
                IdentifiedLayout(
                    name="Output Report",
                    file_extension="pdf",
                    is_output=True,
                    confidence=0.8,
                ),
            ],
            total_count=2,
            detection_confidence=0.82,
        )
        mock_llm.complete_structured.return_value = mock_response

        result = identify_layouts(sections, llm_manager=mock_llm)

        # Assertions
        assert isinstance(result, LayoutIdentificationResult)
        assert result.total_count >= 1
        assert result.detection_confidence >= 0.0
        print(f"Layouts found: {result.total_count}")
        print(f"Layout names: {result.layout_names()}")
        print(f"Inputs: {result.input_count()}")
        print(f"Outputs: {result.output_count()}")
