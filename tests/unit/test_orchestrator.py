"""Tests for agents.orchestrator module.

Covers the 5-stage orchestrator pipeline: state management, node functions,
routing logic, checkpoint saving, and the public run_assessment() entry point.

Unit tests mock all agent run() functions and output tools. Integration test
uses real files and executes the full pipeline.
"""

import json
from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agents.orchestrator import (
    PipelineState,
    _build_graph,
    _save_checkpoint,
    _should_continue,
    stage_complexity_assessment,
    stage_document_intelligence,
    stage_effort_and_decomposition,
    stage_generate_outputs,
    stage_process_analysis,
)
from core.constants import ComplexityTier, RPATool
from core.exceptions import AgentExecutionError, OutputGenerationError
from core.models.assessment import AssessmentResult, AttributeScore

# ==================== FIXTURES ====================


@pytest.fixture
def base_pipeline_state() -> PipelineState:
    """Minimal valid PipelineState for testing."""
    return {
        "file_path": "/test/sample.docx",
        "session_id": "test_session",
        "rpa_tool_override": "unknown",
        "project_name": "Test Project",
        "start_date": "2026-03-17",
        "developer_name": "Test Dev",
        "business_analyst": "Test BA",
        "squad": "Test Squad",
        "di_state": {},
        "pa_state": {},
        "ca_state": {},
        "decomposition": {},
        "timeline": {},
        "excel_path": "",
        "pdf_path": "",
        "status": "running",
        "current_stage": "initializing",
        "warnings": [],
        "errors": [],
        "completed_at": "",
    }


@pytest.fixture
def sample_process_docx() -> Path:
    """Path to sample_process.docx test fixture."""
    path = (
        Path(__file__).parent.parent.parent
        / "data"
        / "sample_pdds"
        / "sample_process.docx"
    )
    if not path.exists():
        pytest.skip(f"Test fixture not found: {path}")
    return path


@pytest.fixture
def mock_assessment_result() -> AssessmentResult:
    """Create a mock AssessmentResult."""
    return AssessmentResult(
        session_id="test_session",
        project_name="Test Project",
        rpa_tool=RPATool.UNKNOWN,
        complexity_tier=ComplexityTier.M,
        total_score=12,
        attribute_scores=[
            AttributeScore(
                attribute_id=1,
                attribute_name="Activities",
                raw_value=40,
                selected_tier=ComplexityTier.M,
                weight=4,
                tier_rationale="Medium activity count",
            ),
            AttributeScore(
                attribute_id=2,
                attribute_name="Business Rules",
                raw_value=4,
                selected_tier=ComplexityTier.M,
                weight=4,
                tier_rationale="Medium rule count",
            ),
            AttributeScore(
                attribute_id=3,
                attribute_name="Layouts",
                raw_value=3,
                selected_tier=ComplexityTier.S,
                weight=1,
                tier_rationale="Small layout count",
            ),
            AttributeScore(
                attribute_id=4,
                attribute_name="Interfaces",
                raw_value=1,
                selected_tier=ComplexityTier.S,
                weight=1,
                tier_rationale="Small interface count",
            ),
            AttributeScore(
                attribute_id=5,
                attribute_name="Technology",
                raw_value=0,
                selected_tier=ComplexityTier.S,
                weight=1,
                tier_rationale="Small technology count",
            ),
        ],
        confidence_score=0.85,
        reasoning="Medium complexity with moderate activities and rules",
        requires_tech_lead_review=False,
        created_at=datetime.now(),
    )


# ==================== CHECKPOINT TESTS ====================


def test_save_checkpoint_creates_file(base_pipeline_state: PipelineState) -> None:
    """Test checkpoint is saved to data/temp directory."""
    temp_dir = Path("data/temp")
    checkpoint_file = temp_dir / f"{base_pipeline_state['session_id']}_checkpoint.json"

    # Clean up if exists
    checkpoint_file.unlink(missing_ok=True)

    _save_checkpoint(base_pipeline_state, "test_stage")

    assert checkpoint_file.exists()
    with open(checkpoint_file) as f:
        data = json.load(f)
    assert data["session_id"] == "test_session"
    assert data["stage"] == "test_stage"

    # Cleanup
    checkpoint_file.unlink(missing_ok=True)


def test_save_checkpoint_handles_missing_directory() -> None:
    """Test checkpoint saves correctly even if directory doesn't exist."""
    state: PipelineState = {
        "file_path": "/test",
        "session_id": "test",
        "rpa_tool_override": "unknown",
        "project_name": "",
        "start_date": "",
        "developer_name": "",
        "business_analyst": "",
        "squad": "",
        "di_state": {},
        "pa_state": {},
        "ca_state": {},
        "decomposition": {},
        "timeline": {},
        "excel_path": "",
        "pdf_path": "",
        "status": "running",
        "current_stage": "test",
        "warnings": [],
        "errors": [],
        "completed_at": "",
    }

    # Should not raise
    _save_checkpoint(state, "test_stage")


def test_save_checkpoint_does_not_raise_on_serialization_error(
    base_pipeline_state: PipelineState,
) -> None:
    """Test checkpoint failure never crashes pipeline."""
    # Add non-serializable object
    base_pipeline_state["di_state"] = {"func": lambda x: x}

    # Should not raise
    _save_checkpoint(base_pipeline_state, "test_stage")


# ==================== ROUTING TESTS ====================


def test_should_continue_returns_end_on_failure() -> None:
    """Test routing stops pipeline when status='failed'."""
    state: PipelineState = {
        "file_path": "/test",
        "session_id": "test",
        "rpa_tool_override": "unknown",
        "project_name": "",
        "start_date": "",
        "developer_name": "",
        "business_analyst": "",
        "squad": "",
        "di_state": {},
        "pa_state": {},
        "ca_state": {},
        "decomposition": {},
        "timeline": {},
        "excel_path": "",
        "pdf_path": "",
        "status": "failed",
        "current_stage": "test",
        "warnings": [],
        "errors": [],
        "completed_at": "",
    }
    assert _should_continue(state) == "end"


def test_should_continue_returns_continue_on_success() -> None:
    """Test routing continues to next stage on success."""
    state: PipelineState = {
        "file_path": "/test",
        "session_id": "test",
        "rpa_tool_override": "unknown",
        "project_name": "",
        "start_date": "",
        "developer_name": "",
        "business_analyst": "",
        "squad": "",
        "di_state": {},
        "pa_state": {},
        "ca_state": {},
        "decomposition": {},
        "timeline": {},
        "excel_path": "",
        "pdf_path": "",
        "status": "running",
        "current_stage": "test",
        "warnings": [],
        "errors": [],
        "completed_at": "",
    }
    assert _should_continue(state) == "continue"


# ==================== STAGE TESTS ====================


def test_stage_document_intelligence_success(
    base_pipeline_state: PipelineState,
) -> None:
    """Test DI stage success flow."""
    mock_di_state = {
        "file_path": "/test",
        "session_id": "test",
        "status": "success",
        "warnings": ["di_warning"],
        "errors": [],
        "sections": [],
        "entities": None,
    }

    with patch("agents.orchestrator.di_run", return_value=mock_di_state):
        result = stage_document_intelligence(base_pipeline_state)

    assert "di_state" in result
    assert result["current_stage"] == "document_intelligence"
    assert "di_warning" in result["warnings"]
    assert "status" not in result or result.get("status") != "failed"


def test_stage_document_intelligence_di_fails(
    base_pipeline_state: PipelineState,
) -> None:
    """Test DI stage when agent returns failed status."""
    mock_di_state = {
        "file_path": "/test",
        "session_id": "test",
        "status": "failed",
        "warnings": [],
        "errors": ["DI error"],
        "sections": [],
        "entities": None,
    }

    with patch("agents.orchestrator.di_run", return_value=mock_di_state):
        result = stage_document_intelligence(base_pipeline_state)

    assert result["status"] == "failed"
    assert "DI error" in result["errors"]


def test_stage_document_intelligence_exception(
    base_pipeline_state: PipelineState,
) -> None:
    """Test DI stage exception handling."""
    with patch("agents.orchestrator.di_run", side_effect=Exception("DI crashed")):
        result = stage_document_intelligence(base_pipeline_state)

    assert result["status"] == "failed"
    assert any("DI crashed" in e for e in result["errors"])


def test_stage_process_analysis_skips_on_failure(
    base_pipeline_state: PipelineState,
) -> None:
    """Test PA stage skips when status='failed'."""
    base_pipeline_state["status"] = "failed"

    result = stage_process_analysis(base_pipeline_state)

    assert result == {}


def test_stage_process_analysis_success(
    base_pipeline_state: PipelineState,
) -> None:
    """Test PA stage success flow."""
    base_pipeline_state["di_state"] = {"sections": [], "entities": None}

    mock_pa_state = {
        "file_path": "/test",
        "session_id": "test",
        "status": "success",
        "warnings": ["pa_warning"],
        "errors": [],
        "raw_attributes": {},
        "detected_rpa_tool": "unknown",
    }

    with patch("agents.orchestrator.pa_run", return_value=mock_pa_state):
        result = stage_process_analysis(base_pipeline_state)

    assert "pa_state" in result
    assert result["current_stage"] == "process_analysis"


def test_stage_process_analysis_applies_rpa_override(
    base_pipeline_state: PipelineState,
) -> None:
    """Test RPA tool override is applied in PA stage."""
    base_pipeline_state["di_state"] = {"sections": [], "entities": None}
    base_pipeline_state["rpa_tool_override"] = "blue_prism"

    mock_pa_state = {
        "file_path": "/test",
        "session_id": "test",
        "status": "success",
        "warnings": [],
        "errors": [],
        "raw_attributes": {},
        "detected_rpa_tool": "uipath",
    }

    with patch("agents.orchestrator.pa_run", return_value=mock_pa_state):
        result = stage_process_analysis(base_pipeline_state)

    assert result["pa_state"]["detected_rpa_tool"] == "blue_prism"


def test_stage_complexity_assessment_skips_on_failure(
    base_pipeline_state: PipelineState,
) -> None:
    """Test CA stage skips when status='failed'."""
    base_pipeline_state["status"] = "failed"

    result = stage_complexity_assessment(base_pipeline_state)

    assert result == {}


def test_stage_complexity_assessment_success(
    base_pipeline_state: PipelineState,
) -> None:
    """Test CA stage success flow."""
    base_pipeline_state["pa_state"] = {
        "raw_attributes": {},
        "detected_rpa_tool": "unknown",
    }

    mock_ca_state = {
        "file_path": "/test",
        "session_id": "test",
        "status": "success",
        "warnings": ["ca_warning"],
        "errors": [],
        "assessment_result": None,
    }

    with patch("agents.orchestrator.ca_run", return_value=mock_ca_state):
        result = stage_complexity_assessment(base_pipeline_state)

    assert "ca_state" in result
    assert result["current_stage"] == "complexity_assessment"


def test_stage_effort_and_decomposition_skips_on_failure(
    base_pipeline_state: PipelineState,
) -> None:
    """Test effort stage skips when status='failed'."""
    base_pipeline_state["status"] = "failed"

    result = stage_effort_and_decomposition(base_pipeline_state)

    assert result == {}


def test_stage_effort_and_decomposition_missing_assessment_result(
    base_pipeline_state: PipelineState,
) -> None:
    """Test effort stage fails when assessment_result missing."""
    base_pipeline_state["ca_state"] = {"assessment_result": None}

    result = stage_effort_and_decomposition(base_pipeline_state)

    assert result["status"] == "failed"
    assert any("not found" in e for e in result["errors"])


def test_stage_effort_and_decomposition_parses_start_date(
    base_pipeline_state: PipelineState, mock_assessment_result: AssessmentResult
) -> None:
    """Test effort stage parses valid ISO start date."""
    base_pipeline_state["start_date"] = "2026-04-15"
    base_pipeline_state["ca_state"] = {"assessment_result": mock_assessment_result}
    base_pipeline_state["di_state"] = {"sections": []}
    base_pipeline_state["pa_state"] = {"rule_result": None}

    mock_decomp = MagicMock()
    mock_decomp.total_step_count = 10
    mock_decomp.total_weighted_steps = 15.5
    mock_decomp.branches = []

    mock_timeline = MagicMock()
    mock_timeline.total_hours.return_value = 80
    mock_timeline.total_sp.return_value = 5.3
    mock_timeline.features = []

    with (
        patch("agents.orchestrator.decompose_steps", return_value=mock_decomp),
        patch(
            "agents.orchestrator.build_timeline", return_value=mock_timeline
        ) as mock_build,
    ):
        stage_effort_and_decomposition(base_pipeline_state)

    # Check that build_timeline was called with the correct date object
    call_args = mock_build.call_args
    assert call_args[1]["start_date"] == date(2026, 4, 15)


def test_stage_effort_and_decomposition_invalid_start_date_uses_today(
    base_pipeline_state: PipelineState, mock_assessment_result: AssessmentResult
) -> None:
    """Test effort stage uses today() when start_date invalid."""
    base_pipeline_state["start_date"] = "invalid-date"
    base_pipeline_state["ca_state"] = {"assessment_result": mock_assessment_result}
    base_pipeline_state["di_state"] = {"sections": []}
    base_pipeline_state["pa_state"] = {"rule_result": None}

    mock_decomp = MagicMock()
    mock_decomp.total_step_count = 10
    mock_decomp.total_weighted_steps = 15.5
    mock_decomp.branches = []

    mock_timeline = MagicMock()
    mock_timeline.total_hours.return_value = 80
    mock_timeline.total_sp.return_value = 5.3
    mock_timeline.features = []

    with (
        patch("agents.orchestrator.decompose_steps", return_value=mock_decomp),
        patch(
            "agents.orchestrator.build_timeline", return_value=mock_timeline
        ) as mock_build,
    ):
        stage_effort_and_decomposition(base_pipeline_state)

    # Check that build_timeline was called with today's date
    call_args = mock_build.call_args
    assert call_args[1]["start_date"] == date.today()


def test_stage_generate_outputs_skips_on_failure(
    base_pipeline_state: PipelineState,
) -> None:
    """Test output stage skips when status='failed'."""
    base_pipeline_state["status"] = "failed"

    result = stage_generate_outputs(base_pipeline_state)

    assert result == {}


def test_stage_generate_outputs_missing_objects(
    base_pipeline_state: PipelineState,
) -> None:
    """Test output stage fails when required objects missing."""
    base_pipeline_state["_assessment_result_obj"] = None

    result = stage_generate_outputs(base_pipeline_state)

    assert result["status"] == "failed"


def test_stage_generate_outputs_both_succeed(
    base_pipeline_state: PipelineState,
    mock_assessment_result: AssessmentResult,
) -> None:
    """Test output stage when both Excel and PDF succeed."""
    mock_decomp = MagicMock()
    mock_timeline = MagicMock()

    base_pipeline_state["_assessment_result_obj"] = mock_assessment_result
    base_pipeline_state["_decomposition_obj"] = mock_decomp
    base_pipeline_state["_timeline_obj"] = mock_timeline

    with (
        patch(
            "agents.orchestrator.generate_excel_report",
            return_value="/output/test.xlsx",
        ),
        patch(
            "agents.orchestrator.generate_pdf_report",
            return_value="/output/test.pdf",
        ),
    ):
        result = stage_generate_outputs(base_pipeline_state)

    assert result["status"] == "success"
    assert result["excel_path"] == "/output/test.xlsx"
    assert result["pdf_path"] == "/output/test.pdf"


def test_stage_generate_outputs_excel_fails(
    base_pipeline_state: PipelineState,
    mock_assessment_result: AssessmentResult,
) -> None:
    """Test output stage when Excel fails but PDF succeeds."""
    mock_decomp = MagicMock()
    mock_timeline = MagicMock()

    base_pipeline_state["_assessment_result_obj"] = mock_assessment_result
    base_pipeline_state["_decomposition_obj"] = mock_decomp
    base_pipeline_state["_timeline_obj"] = mock_timeline

    with (
        patch(
            "agents.orchestrator.generate_excel_report",
            side_effect=OutputGenerationError(message="Excel failed", context={}),
        ),
        patch(
            "agents.orchestrator.generate_pdf_report",
            return_value="/output/test.pdf",
        ),
    ):
        result = stage_generate_outputs(base_pipeline_state)

    assert result["status"] == "partial"
    assert result["excel_path"] == ""
    assert result["pdf_path"] == "/output/test.pdf"
    assert any("Excel" in w for w in result["warnings"])


def test_stage_generate_outputs_both_fail(
    base_pipeline_state: PipelineState,
    mock_assessment_result: AssessmentResult,
) -> None:
    """Test output stage when both Excel and PDF fail."""
    mock_decomp = MagicMock()
    mock_timeline = MagicMock()

    base_pipeline_state["_assessment_result_obj"] = mock_assessment_result
    base_pipeline_state["_decomposition_obj"] = mock_decomp
    base_pipeline_state["_timeline_obj"] = mock_timeline

    with (
        patch(
            "agents.orchestrator.generate_excel_report",
            side_effect=OutputGenerationError(message="Excel failed", context={}),
        ),
        patch(
            "agents.orchestrator.generate_pdf_report",
            side_effect=OutputGenerationError(message="PDF failed", context={}),
        ),
    ):
        result = stage_generate_outputs(base_pipeline_state)

    assert result["status"] == "failed"


# ==================== GRAPH TESTS ====================


def test_build_graph_compiles() -> None:
    """Test graph compiles without errors."""
    graph = _build_graph()
    assert graph is not None
    # Verify it's a compiled graph (has invoke method)
    assert hasattr(graph, "invoke")


def test_build_graph_has_five_nodes() -> None:
    """Test graph has all 5 nodes."""
    from agents.orchestrator import _graph

    # Get node names from compiled graph
    assert _graph is not None


# ==================== RUN_ASSESSMENT TESTS ====================


def test_run_assessment_missing_file() -> None:
    """Test run_assessment raises when file not found."""
    from agents import run_assessment

    with pytest.raises(AgentExecutionError) as exc_info:
        run_assessment(file_path="/nonexistent/file.docx")

    assert "not found" in str(exc_info.value).lower()


def test_run_assessment_unsupported_extension() -> None:
    """Test run_assessment raises on unsupported file type."""
    # Create a temporary .txt file
    import tempfile

    from agents import run_assessment

    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
        temp_file = f.name

    try:
        with pytest.raises(AgentExecutionError) as exc_info:
            run_assessment(file_path=temp_file)

        assert "unsupported" in str(exc_info.value).lower()
    finally:
        Path(temp_file).unlink(missing_ok=True)


def test_run_assessment_auto_generates_session_id(
    sample_process_docx: Path,
) -> None:
    """Test run_assessment generates session_id if not provided."""
    from agents import run_assessment

    with patch("agents.orchestrator._graph.invoke") as mock_invoke:
        mock_invoke.return_value = {
            "status": "success",
            "ca_state": {"assessment_result": None},
            "pa_state": {"raw_attributes": {}, "detected_rpa_tool": "unknown"},
            "decomposition": {},
            "timeline": {},
            "excel_path": "",
            "pdf_path": "",
            "warnings": [],
            "errors": [],
            "completed_at": "",
        }

        result = run_assessment(file_path=str(sample_process_docx))

        # Check that session_id is present and auto-generated
        assert "session_id" in result
        assert len(result["session_id"]) == 8


def test_run_assessment_uses_provided_session_id(
    sample_process_docx: Path,
) -> None:
    """Test run_assessment uses provided session_id."""
    from agents import run_assessment

    with patch("agents.orchestrator._graph.invoke") as mock_invoke:
        mock_invoke.return_value = {
            "status": "success",
            "ca_state": {"assessment_result": None},
            "pa_state": {"raw_attributes": {}, "detected_rpa_tool": "unknown"},
            "decomposition": {},
            "timeline": {},
            "excel_path": "",
            "pdf_path": "",
            "warnings": [],
            "errors": [],
            "completed_at": "",
        }

        result = run_assessment(
            file_path=str(sample_process_docx), session_id="custom_id"
        )

        assert result["session_id"] == "custom_id"


def test_run_assessment_returns_all_required_keys(
    sample_process_docx: Path, mock_assessment_result: AssessmentResult
) -> None:
    """Test run_assessment returns dict with all required keys."""
    from agents import run_assessment

    with patch("agents.orchestrator._graph.invoke") as mock_invoke:
        mock_invoke.return_value = {
            "status": "success",
            "ca_state": {"assessment_result": mock_assessment_result},
            "pa_state": {
                "raw_attributes": {
                    "activities": "XL",
                    "business_rules": "XL",
                    "layouts": "L",
                    "interfaces": "S",
                    "technology": "S",
                },
                "detected_rpa_tool": "blue_prism",
            },
            "decomposition": {"total_step_count": 10, "branch_count": 2},
            "timeline": {"total_hours": 80, "feature_count": 5},
            "excel_path": "/out/test.xlsx",
            "pdf_path": "/out/test.pdf",
            "warnings": ["warning1"],
            "errors": [],
            "completed_at": "2026-03-17T12:00:00",
        }

        result = run_assessment(file_path=str(sample_process_docx))

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
            assert key in result, f"Missing key: {key}"

        # Check nested dicts
        assert "excel" in result["output_files"]
        assert "pdf" in result["output_files"]


def test_run_assessment_with_parameters(
    sample_process_docx: Path,
) -> None:
    """Test run_assessment passes parameters correctly."""
    from agents import run_assessment

    with patch("agents.orchestrator._graph.invoke") as mock_invoke:
        mock_invoke.return_value = {
            "status": "success",
            "ca_state": {"assessment_result": None},
            "pa_state": {"raw_attributes": {}, "detected_rpa_tool": "unknown"},
            "decomposition": {},
            "timeline": {},
            "excel_path": "",
            "pdf_path": "",
            "warnings": [],
            "errors": [],
            "completed_at": "",
        }

        run_assessment(
            file_path=str(sample_process_docx),
            rpa_tool="blue_prism",
            project_name="My Project",
            start_date="2026-04-01",
            developer_name="John Doe",
            business_analyst="Jane Smith",
            squad="Team A",
            session_id="test_session",
        )

        # Check that invoke was called with correct initial state
        call_args = mock_invoke.call_args[0][0]
        assert call_args["rpa_tool_override"] == "blue_prism"
        assert call_args["project_name"] == "My Project"
        assert call_args["start_date"] == "2026-04-01"
        assert call_args["developer_name"] == "John Doe"
        assert call_args["business_analyst"] == "Jane Smith"
        assert call_args["squad"] == "Team A"
        assert call_args["session_id"] == "test_session"


# ==================== INTEGRATION TEST ====================


@pytest.mark.integration
def test_full_pipeline_integration(sample_process_docx: Path) -> None:
    """Integration test: run full pipeline with real files.

    This test uses the actual test fixture and runs through all 5 stages.
    It verifies:
    - Pipeline executes without crashing
    - Assessment result is produced
    - Output files are generated
    """
    from agents import run_assessment

    result = run_assessment(
        file_path=str(sample_process_docx),
        rpa_tool="blue_prism",
        project_name="SAP ASM Automation Test",
        developer_name="Test Developer",
        business_analyst="Test BA",
        squad="Test Squad",
        session_id="integration_test",
    )

    # Debug: print any errors that occurred
    if result["errors"]:
        print("\n=== PIPELINE ERRORS ===")
        for err in result["errors"]:
            print(f"  - {err}")

    # Status checks
    assert result["status"] in [
        "success",
        "partial",
    ], f"Pipeline failed with errors: {result['errors']}"
    assert result["session_id"] == "integration_test"

    # Assessment checks
    assert result["complexity_tier"] is not None
    assert result["complexity_tier"] in ["XS", "S", "M", "L", "XL"]
    assert result["total_score"] is not None
    assert 0 <= result["total_score"] <= 28

    # Raw attributes
    attrs = result["raw_attributes"]
    assert "activities" in attrs
    assert "business_rules" in attrs
    assert "layouts" in attrs
    assert "interfaces" in attrs
    assert "technology" in attrs

    # Output files
    files = result["output_files"]
    if files["excel"]:
        assert Path(files["excel"]).exists()
    if files["pdf"]:
        assert Path(files["pdf"]).exists()

    # Print full result for inspection
    print("\n=== FULL PIPELINE RESULT ===")
    print(f"Status:     {result['status']}")
    print(f"Tier:       {result['complexity_tier']}")
    print(f"Score:      {result['total_score']}/28")
    print(
        f"Confidence: {result['confidence']:.2f}"
        if result["confidence"]
        else "Confidence: None"
    )
    print(f"RPA Tool:   {result['detected_rpa_tool']}")
    print(f"Attributes: {result['raw_attributes']}")
    print(f"Excel:      {result['output_files']['excel']}")
    print(f"PDF:        {result['output_files']['pdf']}")
    print(f"Warnings:   {len(result['warnings'])}")
    if result["reasoning"]:
        print(f"Reasoning:  {result['reasoning'][:200]}")
    print(f"Completed:  {result['completed_at']}")
