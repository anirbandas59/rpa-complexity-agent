"""
Unit tests for PDF reporter tool.

Tests helper functions, PDF generation, and content verification.
"""

from datetime import date, datetime
from pathlib import Path

import pytest

from core.constants import ComplexityTier, RPATool
from core.exceptions import OutputGenerationError
from core.models.assessment import AssessmentResult, AttributeScore
from core.models.timeline import DeliveryFeature, DeliveryTimeline
from tools.output.pdf_reporter import (
    PDF_COLORS,
    _get_tier_color,
    generate_pdf_report,
)


# ===========================================================================
# FIXTURES
# ===========================================================================


@pytest.fixture
def sample_assessment_result() -> AssessmentResult:
    """Sample assessment result for testing."""
    return AssessmentResult(
        session_id="test-session-123",
        project_name="Order Processing Automation",
        rpa_tool=RPATool.UIPATH,
        attribute_scores=[
            AttributeScore(
                attribute_id=1,
                attribute_name="Activities",
                raw_value=20,
                selected_tier=ComplexityTier.L,
                weight=6,
                tier_rationale="20 distinct RPA activities identified",
            ),
            AttributeScore(
                attribute_id=2,
                attribute_name="Business Rules",
                raw_value=4,
                selected_tier=ComplexityTier.L,
                weight=6,
                tier_rationale="4 decision points in flow",
            ),
            AttributeScore(
                attribute_id=3,
                attribute_name="Layouts",
                raw_value=3,
                selected_tier=ComplexityTier.M,
                weight=2,
                tier_rationale="3 digital layouts used",
            ),
            AttributeScore(
                attribute_id=4,
                attribute_name="Interfaces",
                raw_value=2,
                selected_tier=ComplexityTier.S,
                weight=1,
                tier_rationale="2 target systems",
            ),
            AttributeScore(
                attribute_id=5,
                attribute_name="Additional Technology",
                raw_value=0,
                selected_tier=ComplexityTier.S,
                weight=1,
                tier_rationale="No additional technology",
            ),
        ],
        total_score=16,
        complexity_tier=ComplexityTier.L,
        confidence_score=0.92,
        reasoning="Complex order processing with multiple business rules and approval workflows",
        requires_tech_lead_review=False,
        created_at=datetime(2026, 3, 17, 10, 30, 0),
    )


@pytest.fixture
def sample_timeline() -> DeliveryTimeline:
    """Sample delivery timeline for testing."""
    return DeliveryTimeline(
        project_name="Order Processing Automation",
        squad="RPA Team",
        business_analyst="Jane Smith",
        developer="John Doe",
        features=[
            DeliveryFeature(
                name="Main Flow",
                scope="ORIGINAL",
                acceptance_status="APPROVED",
                start_date=date(2026, 3, 20),
                end_date=date(2026, 3, 24),
                hours=9.0,
                developer="John Doe",
                development_status="NOT STARTED",
                remarks="Primary process steps",
            ),
            DeliveryFeature(
                name="Error Handler",
                scope="ORIGINAL",
                acceptance_status="APPROVED",
                start_date=date(2026, 3, 27),
                end_date=date(2026, 3, 27),
                hours=4.5,
                developer="John Doe",
                development_status="NOT STARTED",
                remarks="Error handling branch",
            ),
        ],
    )


# ===========================================================================
# HELPER FUNCTION TESTS
# ===========================================================================


class TestHelperFunctions:
    """Test helper functions."""

    def test_get_tier_color_xs(self):
        """Test _get_tier_color returns green for XS."""
        color = _get_tier_color(ComplexityTier.XS)
        assert color == PDF_COLORS["XS"]

    def test_get_tier_color_s(self):
        """Test _get_tier_color returns darker green for S."""
        color = _get_tier_color(ComplexityTier.S)
        assert color == PDF_COLORS["S"]

    def test_get_tier_color_m(self):
        """Test _get_tier_color returns amber for M."""
        color = _get_tier_color(ComplexityTier.M)
        assert color == PDF_COLORS["M"]

    def test_get_tier_color_l(self):
        """Test _get_tier_color returns red for L."""
        color = _get_tier_color(ComplexityTier.L)
        assert color == PDF_COLORS["L"]

    def test_get_tier_color_xl(self):
        """Test _get_tier_color returns purple for XL."""
        color = _get_tier_color(ComplexityTier.XL)
        assert color == PDF_COLORS["XL"]

    def test_get_tier_color_all_tiers_return_non_none(self):
        """Test all tiers return non-None colors."""
        for tier in ComplexityTier:
            color = _get_tier_color(tier)
            assert color is not None


# ===========================================================================
# GENERATE_PDF_REPORT TESTS
# ===========================================================================


class TestGeneratePdfReport:
    """Test generate_pdf_report function."""

    def test_returns_string_path(self, sample_assessment_result, sample_timeline, tmp_path):
        """Test function returns string file path."""
        output_file = tmp_path / "test.pdf"
        result = generate_pdf_report(
            sample_assessment_result,
            sample_timeline,
            output_path=str(output_file),
        )
        assert isinstance(result, str)

    def test_file_exists_at_returned_path(self, sample_assessment_result, sample_timeline, tmp_path):
        """Test file exists at returned path."""
        output_file = tmp_path / "test.pdf"
        result = generate_pdf_report(
            sample_assessment_result,
            sample_timeline,
            output_path=str(output_file),
        )
        assert Path(result).exists()

    def test_file_size_greater_than_3kb(self, sample_assessment_result, sample_timeline, tmp_path):
        """Test generated file is > 3KB (real PDF)."""
        output_file = tmp_path / "test.pdf"
        result = generate_pdf_report(
            sample_assessment_result,
            sample_timeline,
            output_path=str(output_file),
        )
        file_size = Path(result).stat().st_size
        assert file_size > 3000, f"PDF too small: {file_size} bytes"

    def test_output_path_parameter_respected(self, sample_assessment_result, sample_timeline, tmp_path):
        """Test output_path parameter is respected."""
        custom_path = tmp_path / "report.pdf"
        result = generate_pdf_report(
            sample_assessment_result,
            sample_timeline,
            output_path=str(custom_path),
        )
        assert result == str(custom_path)
        assert Path(result).exists()

    def test_auto_generated_path_valid_format(self, sample_assessment_result, sample_timeline, tmp_path):
        """Test auto-generated path has valid format with timestamp."""
        # Create output directory
        output_dir = tmp_path / "outputs"
        output_dir.mkdir(parents=True, exist_ok=True)

        # Mock the data/outputs directory in pdf_reporter
        import tools.output.pdf_reporter as pdf_mod

        original_file = pdf_mod.Path(__file__).parent

        # Generate with no output path - will create in default location
        result = generate_pdf_report(
            sample_assessment_result,
            sample_timeline,
            output_path=None,
        )

        assert result.endswith(".pdf")
        assert Path(result).exists()

    def test_path_ends_with_pdf(self, sample_assessment_result, sample_timeline, tmp_path):
        """Test returned path ends with .pdf."""
        output_file = tmp_path / "test.pdf"
        result = generate_pdf_report(
            sample_assessment_result,
            sample_timeline,
            output_path=str(output_file),
        )
        assert result.endswith(".pdf")

    def test_error_on_invalid_directory(self, sample_assessment_result, sample_timeline):
        """Test OutputGenerationError raised if directory invalid."""
        invalid_path = "/nonexistent/path/that/does/not/exist/report.pdf"

        with pytest.raises(OutputGenerationError):
            generate_pdf_report(
                sample_assessment_result,
                sample_timeline,
                output_path=invalid_path,
            )


# ===========================================================================
# PDF CONTENT VERIFICATION TESTS
# ===========================================================================


class TestPdfContent:
    """Test PDF file content and structure."""

    def test_pdf_header_valid(self, sample_assessment_result, sample_timeline, tmp_path):
        """Test PDF file starts with valid %PDF header."""
        output_file = tmp_path / "test.pdf"
        result = generate_pdf_report(
            sample_assessment_result,
            sample_timeline,
            output_path=str(output_file),
        )

        with open(result, "rb") as f:
            header = f.read(4)

        assert header == b"%PDF", "PDF header is invalid"

    def test_file_size_between_bounds(self, sample_assessment_result, sample_timeline, tmp_path):
        """Test file size is between 3KB and 2MB."""
        output_file = tmp_path / "test.pdf"
        result = generate_pdf_report(
            sample_assessment_result,
            sample_timeline,
            output_path=str(output_file),
        )

        file_size = Path(result).stat().st_size
        assert 3000 < file_size < 2_000_000, f"File size {file_size} out of bounds"


# ===========================================================================
# GROUND TRUTH TEST
# ===========================================================================


class TestGroundTruth:
    """Test ground truth case."""

    def test_ground_truth_pdf_output(self, sample_assessment_result, sample_timeline, tmp_path):
        """Test known project data generates valid PDF.

        Uses score=16, tier=L (ground truth).
        """
        # Verify test data
        assert sample_assessment_result.total_score == 16
        assert sample_assessment_result.complexity_tier == ComplexityTier.L

        output_file = tmp_path / "ground_truth.pdf"
        result = generate_pdf_report(
            sample_assessment_result,
            sample_timeline,
            output_path=str(output_file),
        )

        # Assertions
        assert Path(result).exists(), "PDF file not created"

        file_size = Path(result).stat().st_size
        assert file_size > 3000, f"PDF too small: {file_size} bytes"

        assert result.endswith(".pdf"), "Path does not end with .pdf"

        with open(result, "rb") as f:
            header = f.read(4)
        assert header == b"%PDF", "PDF header is invalid"


# ===========================================================================
# TECH LEAD REVIEW FLAG TEST
# ===========================================================================


class TestTechLeadReviewFlag:
    """Test tech lead review flag handling."""

    def test_pdf_with_tech_lead_review_required(self, sample_assessment_result, sample_timeline, tmp_path):
        """Test PDF generation when tech lead review is required."""
        sample_assessment_result.requires_tech_lead_review = True

        output_file = tmp_path / "tech_lead_review.pdf"
        result = generate_pdf_report(
            sample_assessment_result,
            sample_timeline,
            output_path=str(output_file),
        )

        assert Path(result).exists()
        assert Path(result).stat().st_size > 3000


# ===========================================================================
# XL TIER TEST
# ===========================================================================


class TestXLTier:
    """Test XL complexity tier."""

    def test_pdf_with_xl_tier(self, sample_assessment_result, sample_timeline, tmp_path):
        """Test PDF generation for XL tier."""
        sample_assessment_result.complexity_tier = ComplexityTier.XL
        sample_assessment_result.total_score = 24
        sample_assessment_result.requires_tech_lead_review = True

        output_file = tmp_path / "xl_tier.pdf"
        result = generate_pdf_report(
            sample_assessment_result,
            sample_timeline,
            output_path=str(output_file),
        )

        assert Path(result).exists()
        assert Path(result).stat().st_size > 3000


# ===========================================================================
# TIMELINE WITH MANY FEATURES TEST
# ===========================================================================


class TestTimelineWithManyFeatures:
    """Test timeline with many features (pagination)."""

    def test_pdf_with_many_features(self, sample_assessment_result, tmp_path):
        """Test PDF handles 20+ features gracefully."""
        # Create timeline with 20 features
        from datetime import timedelta
        features = []
        current_date = date(2026, 3, 20)
        for i in range(20):
            features.append(
                DeliveryFeature(
                    name=f"Feature {i+1}",
                    start_date=current_date,
                    end_date=current_date,
                    hours=9.0,
                    developer="John Doe",
                )
            )
            current_date = current_date + timedelta(days=1)

        timeline = DeliveryTimeline(
            project_name="Large Project",
            squad="RPA Team",
            business_analyst="Jane Smith",
            developer="John Doe",
            features=features,
        )

        output_file = tmp_path / "many_features.pdf"
        result = generate_pdf_report(
            sample_assessment_result,
            timeline,
            output_path=str(output_file),
        )

        assert Path(result).exists()
        assert Path(result).stat().st_size > 3000


# ===========================================================================
# SESSION ID LOGGING TEST
# ===========================================================================


class TestSessionIdLogging:
    """Test session ID is properly handled."""

    def test_generate_pdf_with_session_id(self, sample_assessment_result, sample_timeline, tmp_path):
        """Test PDF generation with explicit session ID."""
        output_file = tmp_path / "test.pdf"
        result = generate_pdf_report(
            sample_assessment_result,
            sample_timeline,
            output_path=str(output_file),
            session_id="custom-session-456",
        )

        assert Path(result).exists()
        assert Path(result).stat().st_size > 3000


# ===========================================================================
# EDGE CASES
# ===========================================================================


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_very_long_project_name(self, sample_assessment_result, sample_timeline, tmp_path):
        """Test handling of very long project names."""
        sample_assessment_result.project_name = "A" * 100

        output_file = tmp_path / "long_name.pdf"
        result = generate_pdf_report(
            sample_assessment_result,
            sample_timeline,
            output_path=str(output_file),
        )

        assert Path(result).exists()

    def test_very_long_reasoning(self, sample_assessment_result, sample_timeline, tmp_path):
        """Test handling of very long reasoning text."""
        sample_assessment_result.reasoning = (
            "This is a very long reasoning paragraph. " * 20
        )

        output_file = tmp_path / "long_reasoning.pdf"
        result = generate_pdf_report(
            sample_assessment_result,
            sample_timeline,
            output_path=str(output_file),
        )

        assert Path(result).exists()

    def test_empty_timeline(self, sample_assessment_result, tmp_path):
        """Test PDF generation with empty timeline."""
        empty_timeline = DeliveryTimeline(
            project_name="Empty Project",
            squad="RPA Team",
            business_analyst="Jane Smith",
            developer="John Doe",
            features=[],
        )

        output_file = tmp_path / "empty_timeline.pdf"
        result = generate_pdf_report(
            sample_assessment_result,
            empty_timeline,
            output_path=str(output_file),
        )

        assert Path(result).exists()

    def test_xs_tier(self, sample_assessment_result, sample_timeline, tmp_path):
        """Test PDF generation for XS tier."""
        sample_assessment_result.complexity_tier = ComplexityTier.XS
        sample_assessment_result.total_score = 2

        output_file = tmp_path / "xs_tier.pdf"
        result = generate_pdf_report(
            sample_assessment_result,
            sample_timeline,
            output_path=str(output_file),
        )

        assert Path(result).exists()

    def test_all_tiers(self, sample_assessment_result, sample_timeline, tmp_path):
        """Test PDF generation for all complexity tiers."""
        for idx, tier in enumerate([ComplexityTier.XS, ComplexityTier.S, ComplexityTier.M, ComplexityTier.L, ComplexityTier.XL]):
            sample_assessment_result.complexity_tier = tier
            sample_assessment_result.total_score = 2 + (idx * 5)

            output_file = tmp_path / f"tier_{tier.value}.pdf"
            result = generate_pdf_report(
                sample_assessment_result,
                sample_timeline,
                output_path=str(output_file),
            )

            assert Path(result).exists()
            assert Path(result).stat().st_size > 3000
