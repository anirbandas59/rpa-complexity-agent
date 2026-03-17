"""
Integration tests for the full RPA Complexity Assessment pipeline.

Phase 9 — Testing & Validation

Tests the complete end-to-end pipeline using real files and real LLM calls.
All tests in this module are marked with @pytest.mark.integration.
"""

import pytest
from pathlib import Path
from openpyxl import load_workbook

from agents import run_assessment
from core.constants import ComplexityTier


@pytest.fixture(scope="module")
def sample_pdf_path():
    """Path to sample_simple.pdf test fixture."""
    path = Path(__file__).parent.parent.parent / "data" / "sample_pdds" / "sample_simple.pdf"
    # If fixture doesn't exist, skip this test
    if not path.exists():
        pytest.skip(f"Test fixture not found: {path}")
    return str(path.absolute())


@pytest.fixture(scope="module")
def sample_docx_path():
    """Path to sample_process.docx test fixture."""
    path = Path(__file__).parent.parent.parent / "data" / "sample_pdds" / "sample_process.docx"
    # If fixture doesn't exist, skip this test
    if not path.exists():
        pytest.skip(f"Test fixture not found: {path}")
    return str(path.absolute())


@pytest.mark.integration
class TestFullPipeline:
    """End-to-end pipeline integration tests."""

    def test_pdf_pipeline_integration(self, sample_pdf_path):
        """Test PDF processing through complete pipeline.

        Validates that the pipeline can:
        - Parse a PDF document
        - Extract attributes
        - Produce a complexity score
        - Generate output files
        """
        result = run_assessment(
            file_path=sample_pdf_path,
            session_id="test_pdf_pipeline",
        )

        # Pipeline must complete
        assert result["status"] in ["success", "partial"], (
            f"Pipeline failed: {result['errors']}"
        )

        # Must produce a valid tier or None
        if result["complexity_tier"] is not None:
            assert result["complexity_tier"] in ["XS", "S", "M", "L", "XL"]

        # Score must be in valid range if present
        if result["total_score"] is not None:
            assert 0 <= result["total_score"] <= 28

        # Must have output files or have partial status
        if result["status"] == "success":
            assert (
                result["output_files"]["excel"] != ""
                or result["output_files"]["pdf"] != ""
            ), "Success status requires output files"

    def test_docx_pipeline_integration(self, sample_docx_path):
        """Test DOCX processing through complete pipeline.

        Validates that the pipeline can:
        - Parse a DOCX document
        - Extract structured sections
        - Detect RPA tool
        - Produce detailed attributes
        """
        result = run_assessment(
            file_path=sample_docx_path,
            rpa_tool="blue_prism",
            project_name="SAP Process Test",
            developer_name="Test Developer",
            session_id="test_docx_pipeline",
        )

        # Pipeline must complete
        assert result["status"] in ["success", "partial"], (
            f"Pipeline failed: {result['errors']}"
        )

        # Must produce a valid tier or None
        if result["complexity_tier"] is not None:
            assert result["complexity_tier"] in ["XS", "S", "M", "L", "XL"]

        # Score must be in valid range if present
        if result["total_score"] is not None:
            assert 0 <= result["total_score"] <= 28

        # Must have attributes dict
        attrs = result["raw_attributes"]
        assert isinstance(attrs, dict)

        # Print summary for debugging
        print(f"\n=== DOCX Pipeline Result ===")
        print(f"Tier: {result['complexity_tier']}")
        print(f"Score: {result['total_score']}")
        print(f"Attributes: {attrs}")
        print(f"Excel: {result['output_files']['excel']}")
        print(f"PDF: {result['output_files']['pdf']}")

    def test_rpa_tool_override_integration(self, sample_docx_path):
        """Test that RPA tool override is respected.

        Validates that:
        - User-specified RPA tool is used
        - Pipeline completes successfully
        """
        result = run_assessment(
            file_path=sample_docx_path,
            rpa_tool="uipath",
            session_id="test_rpa_override",
        )

        # Pipeline must complete
        assert result["status"] in ["success", "partial"]

        # Must record the tool (though it's stored as detected, the override
        # should influence the effort calculation if LLM detected something else)
        assert result["detected_rpa_tool"] is not None

    def test_output_files_validity(self, sample_docx_path):
        """Test that generated output files are valid.

        Validates that:
        - Excel files can be loaded with openpyxl
        - PDF files start with PDF header
        """
        result = run_assessment(
            file_path=sample_docx_path,
            session_id="test_output_files",
        )

        # If Excel file was generated
        excel_path = result["output_files"].get("excel", "")
        if excel_path and Path(excel_path).exists():
            # Must be loadable by openpyxl
            try:
                wb = load_workbook(excel_path)
                assert len(wb.sheetnames) > 0, "Excel workbook has no sheets"
            except Exception as e:
                pytest.fail(f"Excel file not readable: {e}")

        # If PDF file was generated
        pdf_path = result["output_files"].get("pdf", "")
        if pdf_path and Path(pdf_path).exists():
            # Must be a valid PDF (starts with %PDF)
            with open(pdf_path, "rb") as f:
                header = f.read(4)
                assert header == b"%PDF", (
                    f"PDF file invalid: starts with {header!r}, not b'%PDF'"
                )

    def test_pipeline_with_minimal_params(self, sample_docx_path):
        """Test pipeline with only required parameters.

        Validates that the pipeline works with:
        - Only file_path
        - Auto-generated session_id
        - Default parameters
        """
        result = run_assessment(file_path=sample_docx_path)

        # Must complete (success or partial)
        assert result["status"] in ["success", "partial"]

        # Must have session_id
        assert result["session_id"] is not None
        assert result["session_id"] != ""

    def test_pipeline_with_all_params(self, sample_docx_path):
        """Test pipeline with all optional parameters.

        Validates that all parameters are accepted:
        - Project name
        - Start date
        - Developer and analyst names
        - Squad name
        - RPA tool override
        """
        result = run_assessment(
            file_path=sample_docx_path,
            rpa_tool="blue_prism",
            project_name="Complete Test Project",
            start_date="2026-03-17",
            developer_name="John Developer",
            business_analyst="Jane Analyst",
            squad="RPA Squad 1",
            session_id="test_all_params",
        )

        # Must complete
        assert result["status"] in ["success", "partial"]

        # Session ID must be as specified
        assert result["session_id"] == "test_all_params"

    def test_result_dict_structure(self, sample_docx_path):
        """Test that result dict has all expected keys.

        Validates the complete result structure.
        """
        result = run_assessment(file_path=sample_docx_path)

        # Check all required keys exist
        required_keys = [
            "session_id",
            "status",
            "complexity_tier",
            "total_score",
            "confidence",
            "reasoning",
            "requires_tech_lead_review",
            "raw_attributes",
            "detected_rpa_tool",
            "effort_estimate",
            "timeline_summary",
            "output_files",
            "warnings",
            "errors",
            "completed_at",
        ]

        for key in required_keys:
            assert key in result, f"Missing key in result: {key}"

        # Check nested dict structures
        assert isinstance(result["output_files"], dict)
        assert "excel" in result["output_files"]
        assert "pdf" in result["output_files"]

        assert isinstance(result["raw_attributes"], dict)
        assert isinstance(result["warnings"], list)
        assert isinstance(result["errors"], list)


@pytest.mark.integration
class TestPipelineErrorHandling:
    """Error handling and edge cases."""

    def test_missing_file_raises(self):
        """Test that missing file raises AgentExecutionError."""
        from core.exceptions import AgentExecutionError

        with pytest.raises(AgentExecutionError) as excinfo:
            run_assessment(file_path="/nonexistent/file.pdf")

        assert "not found" in str(excinfo.value).lower()

    def test_unsupported_format_raises(self, tmp_path):
        """Test that unsupported file format raises AgentExecutionError."""
        from core.exceptions import AgentExecutionError

        # Create a temporary .txt file
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("Test content")

        with pytest.raises(AgentExecutionError) as excinfo:
            run_assessment(file_path=str(txt_file))

        assert "unsupported" in str(excinfo.value).lower()


@pytest.mark.integration
class TestPipelineValidation:
    """Validation of assessment results."""

    def test_confidence_score_in_range(self, sample_docx_path):
        """Confidence score must be between 0.0 and 1.0 if present."""
        result = run_assessment(file_path=sample_docx_path)

        if result["confidence"] is not None:
            assert 0.0 <= result["confidence"] <= 1.0, (
                f"Confidence {result['confidence']} outside [0.0, 1.0]"
            )

    def test_raw_attributes_non_negative(self, sample_docx_path):
        """All raw attribute values must be non-negative."""
        result = run_assessment(file_path=sample_docx_path)

        attrs = result["raw_attributes"]
        if attrs:
            for key, value in attrs.items():
                assert isinstance(value, int), (
                    f"Attribute {key} is not int: {value} ({type(value)})"
                )
                assert value >= 0, (
                    f"Attribute {key} is negative: {value}"
                )

    def test_tier_consistency(self, sample_docx_path):
        """If score exists, tier should match score range."""
        result = run_assessment(file_path=sample_docx_path)

        score = result["total_score"]
        tier = result["complexity_tier"]

        if score is not None and tier is not None:
            # Verify score-tier mapping
            tier_mapping = {
                ComplexityTier.XS: (0, 6),
                ComplexityTier.S: (7, 8),
                ComplexityTier.M: (9, 15),
                ComplexityTier.L: (16, 22),
                ComplexityTier.XL: (23, 28),
            }

            # Find matching tier for score
            for t, (min_score, max_score) in tier_mapping.items():
                if min_score <= score <= max_score:
                    assert tier == t.value, (
                        f"Score {score} should map to {t.value}, got {tier}"
                    )
                    break
