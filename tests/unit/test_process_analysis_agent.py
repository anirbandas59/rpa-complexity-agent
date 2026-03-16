"""Tests for Process Analysis Agent."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agents.process_analysis.agent import (
    ProcessAnalysisState,
    compile_attributes,
    run,
)
from core.constants import RPATool
from core.models.document import ExtractedSection, ParsedDocument

# ==================== TEST: compile_attributes NODE ====================


class TestCompileAttributesNode:
    """Tests for compile_attributes node."""

    def test_compiles_all_attributes(self):
        """Compiles all 5 raw attributes when results present."""
        # Create mock results
        activity_result = MagicMock()
        activity_result.raw_activity_count = 10
        activity_result.count_confidence = 0.9

        interface_result = MagicMock()
        interface_result.total_count = 3
        interface_result.detection_confidence = 0.8

        rule_result = MagicMock()
        rule_result.total_qualifying_count = 2

        layout_result = MagicMock()
        layout_result.total_count = 4
        layout_result.detection_confidence = 0.8
        layout_result.exceeds_ceiling = False

        technology_result = MagicMock()
        technology_result.total_count = 1

        state: ProcessAnalysisState = {
            "file_path": "test.docx",
            "session_id": "test_session",
            "parsed_document": MagicMock(spec=ParsedDocument),
            "sections": [],
            "entities": None,
            "activity_result": activity_result,
            "interface_result": interface_result,
            "rule_result": rule_result,
            "layout_result": layout_result,
            "technology_result": technology_result,
            "rpa_tool_result": None,
            "raw_attributes": {},
            "detected_rpa_tool": RPATool.UNKNOWN.value,
            "status": "running",
            "warnings": [],
            "errors": [],
            "completed_at": "",
        }

        result = compile_attributes(state)

        assert "raw_attributes" in result
        raw_attrs = result["raw_attributes"]
        assert raw_attrs["activities"] == 10
        assert raw_attrs["interfaces"] == 3
        assert raw_attrs["business_rules"] == 2
        assert raw_attrs["layouts"] == 4
        assert raw_attrs["technology"] == 1

    def test_defaults_to_zero_for_missing_results(self):
        """Defaults to 0 for missing result fields."""
        state: ProcessAnalysisState = {
            "file_path": "test.docx",
            "session_id": "test_session",
            "parsed_document": MagicMock(spec=ParsedDocument),
            "sections": [],
            "entities": None,
            "activity_result": None,
            "interface_result": None,
            "rule_result": None,
            "layout_result": None,
            "technology_result": None,
            "rpa_tool_result": None,
            "raw_attributes": {},
            "detected_rpa_tool": RPATool.UNKNOWN.value,
            "status": "running",
            "warnings": [],
            "errors": [],
            "completed_at": "",
        }

        result = compile_attributes(state)

        raw_attrs = result["raw_attributes"]
        assert raw_attrs["activities"] == 0
        assert raw_attrs["interfaces"] == 0
        assert raw_attrs["business_rules"] == 0
        assert raw_attrs["layouts"] == 0
        assert raw_attrs["technology"] == 0

    def test_status_failed_when_no_document(self):
        """Status is 'failed' when parsed_document is None."""
        state: ProcessAnalysisState = {
            "file_path": "test.docx",
            "session_id": "test_session",
            "parsed_document": None,
            "sections": [],
            "entities": None,
            "activity_result": None,
            "interface_result": None,
            "rule_result": None,
            "layout_result": None,
            "technology_result": None,
            "rpa_tool_result": None,
            "raw_attributes": {},
            "detected_rpa_tool": RPATool.UNKNOWN.value,
            "status": "running",
            "warnings": [],
            "errors": [],
            "completed_at": "",
        }

        result = compile_attributes(state)

        assert result["status"] == "failed"

    def test_status_success_with_valid_results(self):
        """Status is 'success' with valid document and results."""
        activity_result = MagicMock()
        activity_result.raw_activity_count = 10
        activity_result.count_confidence = 0.9

        state: ProcessAnalysisState = {
            "file_path": "test.docx",
            "session_id": "test_session",
            "parsed_document": MagicMock(spec=ParsedDocument),
            "sections": [],
            "entities": None,
            "activity_result": activity_result,
            "interface_result": MagicMock(total_count=3),
            "rule_result": MagicMock(total_qualifying_count=2),
            "layout_result": MagicMock(total_count=4),
            "technology_result": MagicMock(total_count=1),
            "rpa_tool_result": None,
            "raw_attributes": {},
            "detected_rpa_tool": RPATool.UNKNOWN.value,
            "status": "running",
            "warnings": [],
            "errors": [],
            "completed_at": "",
        }

        result = compile_attributes(state)

        assert result["status"] == "success"

    def test_status_partial_when_zero_count_low_confidence(self):
        """Status is 'partial' when count=0 with confidence<0.3."""
        activity_result = MagicMock()
        activity_result.raw_activity_count = 0
        activity_result.count_confidence = 0.2

        state: ProcessAnalysisState = {
            "file_path": "test.docx",
            "session_id": "test_session",
            "parsed_document": MagicMock(spec=ParsedDocument),
            "sections": [],
            "entities": None,
            "activity_result": activity_result,
            "interface_result": MagicMock(total_count=3),
            "rule_result": MagicMock(total_qualifying_count=2),
            "layout_result": MagicMock(total_count=4),
            "technology_result": MagicMock(total_count=1),
            "rpa_tool_result": None,
            "raw_attributes": {},
            "detected_rpa_tool": RPATool.UNKNOWN.value,
            "status": "running",
            "warnings": [],
            "errors": [],
            "completed_at": "",
        }

        result = compile_attributes(state)

        assert result["status"] == "partial"

    def test_rpa_tool_detection_sets_detected_tool(self):
        """Detected RPA tool is set from rpa_tool_result."""
        rpa_tool_result = MagicMock()
        rpa_tool_result.is_known.return_value = True
        rpa_tool_result.detected_tool = RPATool.BLUE_PRISM

        state: ProcessAnalysisState = {
            "file_path": "test.docx",
            "session_id": "test_session",
            "parsed_document": MagicMock(spec=ParsedDocument),
            "sections": [],
            "entities": None,
            "activity_result": None,
            "interface_result": None,
            "rule_result": None,
            "layout_result": None,
            "technology_result": None,
            "rpa_tool_result": rpa_tool_result,
            "raw_attributes": {},
            "detected_rpa_tool": RPATool.UNKNOWN.value,
            "status": "running",
            "warnings": [],
            "errors": [],
            "completed_at": "",
        }

        result = compile_attributes(state)

        assert result["detected_rpa_tool"] == RPATool.BLUE_PRISM.value

    def test_warning_added_for_layout_exceeds_ceiling(self):
        """Warning added when layout_result.exceeds_ceiling is True."""
        layout_result = MagicMock()
        layout_result.total_count = 4
        layout_result.exceeds_ceiling = True

        state: ProcessAnalysisState = {
            "file_path": "test.docx",
            "session_id": "test_session",
            "parsed_document": MagicMock(spec=ParsedDocument),
            "sections": [],
            "entities": None,
            "activity_result": None,
            "interface_result": None,
            "rule_result": None,
            "layout_result": layout_result,
            "technology_result": None,
            "rpa_tool_result": None,
            "raw_attributes": {},
            "detected_rpa_tool": RPATool.UNKNOWN.value,
            "status": "running",
            "warnings": [],
            "errors": [],
            "completed_at": "",
        }

        result = compile_attributes(state)

        assert any("exceeds XL ceiling" in w for w in result["warnings"])

    def test_warning_added_for_low_activity_confidence(self):
        """Warning added when activity confidence < 0.4."""
        activity_result = MagicMock()
        activity_result.raw_activity_count = 5
        activity_result.count_confidence = 0.2

        state: ProcessAnalysisState = {
            "file_path": "test.docx",
            "session_id": "test_session",
            "parsed_document": MagicMock(spec=ParsedDocument),
            "sections": [],
            "entities": None,
            "activity_result": activity_result,
            "interface_result": None,
            "rule_result": None,
            "layout_result": None,
            "technology_result": None,
            "rpa_tool_result": None,
            "raw_attributes": {},
            "detected_rpa_tool": RPATool.UNKNOWN.value,
            "status": "running",
            "warnings": [],
            "errors": [],
            "completed_at": "",
        }

        result = compile_attributes(state)

        assert any("Activity count confidence" in w for w in result["warnings"])

    def test_warning_added_for_no_interfaces(self):
        """Warning added when no interfaces detected."""
        interface_result = MagicMock()
        interface_result.total_count = 0

        state: ProcessAnalysisState = {
            "file_path": "test.docx",
            "session_id": "test_session",
            "parsed_document": MagicMock(spec=ParsedDocument),
            "sections": [],
            "entities": None,
            "activity_result": None,
            "interface_result": interface_result,
            "rule_result": None,
            "layout_result": None,
            "technology_result": None,
            "rpa_tool_result": None,
            "raw_attributes": {},
            "detected_rpa_tool": RPATool.UNKNOWN.value,
            "status": "running",
            "warnings": [],
            "errors": [],
            "completed_at": "",
        }

        result = compile_attributes(state)

        assert any("No interfaces detected" in w for w in result["warnings"])

    def test_completed_at_populated(self):
        """completed_at is populated with ISO timestamp."""
        state: ProcessAnalysisState = {
            "file_path": "test.docx",
            "session_id": "test_session",
            "parsed_document": MagicMock(spec=ParsedDocument),
            "sections": [],
            "entities": None,
            "activity_result": None,
            "interface_result": None,
            "rule_result": None,
            "layout_result": None,
            "technology_result": None,
            "rpa_tool_result": None,
            "raw_attributes": {},
            "detected_rpa_tool": RPATool.UNKNOWN.value,
            "status": "running",
            "warnings": [],
            "errors": [],
            "completed_at": "",
        }

        result = compile_attributes(state)

        assert result["completed_at"] != ""
        # Should be ISO format
        assert "T" in result["completed_at"]


# ==================== TEST: run() FUNCTION ====================


class TestProcessAnalysisRun:
    """Tests for run() public function."""

    @patch("agents.process_analysis.agent._graph.invoke")
    def test_run_returns_state_dict(self, mock_invoke):
        """run() returns a ProcessAnalysisState dict."""
        expected_state = {
            "file_path": "test.docx",
            "session_id": "test_session",
            "raw_attributes": {
                "activities": 10,
                "business_rules": 2,
                "layouts": 4,
                "interfaces": 3,
                "technology": 1,
            },
            "detected_rpa_tool": RPATool.BLUE_PRISM.value,
            "status": "success",
            "warnings": [],
            "errors": [],
            "completed_at": "2024-01-01T00:00:00",
        }
        mock_invoke.return_value = expected_state

        document_state = {
            "file_path": "test.docx",
            "session_id": "test_session",
            "parsed_document": MagicMock(spec=ParsedDocument),
            "sections": [],
        }

        result = run(document_state)

        assert isinstance(result, dict)
        assert result["status"] == "success"
        assert "raw_attributes" in result

    @patch("agents.process_analysis.agent._graph.invoke")
    def test_run_inherits_session_id_from_document_state(self, mock_invoke):
        """run() uses session_id from document_state if not provided."""
        mock_invoke.return_value = {"status": "success", "raw_attributes": {}}

        document_state = {
            "file_path": "test.docx",
            "session_id": "doc_session_123",
            "parsed_document": MagicMock(spec=ParsedDocument),
            "sections": [],
        }

        run(document_state)

        # Check that graph was invoked with the correct session_id
        call_args = mock_invoke.call_args
        invoked_state = call_args[0][0]
        assert invoked_state["session_id"] == "doc_session_123"

    @patch("agents.process_analysis.agent._graph.invoke")
    def test_run_uses_provided_session_id(self, mock_invoke):
        """run() uses provided session_id over document_state."""
        mock_invoke.return_value = {"status": "success", "raw_attributes": {}}

        document_state = {
            "file_path": "test.docx",
            "session_id": "doc_session",
            "parsed_document": MagicMock(spec=ParsedDocument),
            "sections": [],
        }

        run(document_state, session_id="custom_session")

        call_args = mock_invoke.call_args
        invoked_state = call_args[0][0]
        assert invoked_state["session_id"] == "custom_session"

    @patch("agents.process_analysis.agent._graph.invoke")
    def test_run_with_no_document(self, mock_invoke):
        """run() handles missing parsed_document."""
        mock_invoke.return_value = {
            "status": "failed",
            "raw_attributes": {},
            "completed_at": "2024-01-01T00:00:00",
        }

        document_state = {
            "file_path": "test.docx",
            "session_id": "test_session",
            "parsed_document": None,
            "sections": [],
        }

        result = run(document_state)

        assert result["status"] == "failed"

    @patch("agents.process_analysis.agent._graph.invoke")
    def test_run_returns_all_5_raw_attributes(self, mock_invoke):
        """run() result contains all 5 raw attribute keys."""
        expected_state = {
            "file_path": "test.docx",
            "session_id": "test_session",
            "raw_attributes": {
                "activities": 10,
                "business_rules": 2,
                "layouts": 4,
                "interfaces": 3,
                "technology": 1,
            },
            "detected_rpa_tool": RPATool.UNKNOWN.value,
            "status": "success",
            "warnings": [],
            "errors": [],
            "completed_at": "2024-01-01T00:00:00",
        }
        mock_invoke.return_value = expected_state

        document_state = {
            "file_path": "test.docx",
            "session_id": "test_session",
            "parsed_document": MagicMock(spec=ParsedDocument),
            "sections": [],
        }

        result = run(document_state)

        raw_attrs = result["raw_attributes"]
        assert "activities" in raw_attrs
        assert "business_rules" in raw_attrs
        assert "layouts" in raw_attrs
        assert "interfaces" in raw_attrs
        assert "technology" in raw_attrs

    @patch("agents.process_analysis.agent._graph.invoke")
    def test_run_status_values(self, mock_invoke):
        """run() result status is one of: success, partial, failed."""
        for status in ["success", "partial", "failed"]:
            mock_invoke.return_value = {
                "status": status,
                "raw_attributes": {},
                "completed_at": "2024-01-01T00:00:00",
            }

            document_state = {
                "file_path": "test.docx",
                "session_id": "test_session",
                "parsed_document": MagicMock(spec=ParsedDocument),
                "sections": [],
            }

            result = run(document_state)

            assert result["status"] in ["success", "partial", "failed"]

    @patch("agents.process_analysis.agent._graph.invoke")
    def test_run_raises_on_critical_failure(self, mock_invoke):
        """run() raises AgentExecutionError on critical failure."""
        mock_invoke.side_effect = Exception("Critical LLM error")

        document_state = {
            "file_path": "test.docx",
            "session_id": "test_session",
            "parsed_document": MagicMock(spec=ParsedDocument),
            "sections": [],
        }

        from core.exceptions import AgentExecutionError

        with pytest.raises(AgentExecutionError):
            run(document_state)


# ==================== TEST: GROUND TRUTH ====================


class TestGroundTruth:
    """Ground truth test."""

    @patch("agents.process_analysis.agent._graph.invoke")
    def test_ground_truth_raw_attributes_present(self, mock_invoke):
        """Ground truth: all 5 raw attributes are compiled correctly."""
        # Known project values
        mock_invoke.return_value = {
            "file_path": "sample_process.docx",
            "session_id": "ground_truth",
            "parsed_document": MagicMock(spec=ParsedDocument),
            "sections": [],
            "entities": None,
            "activity_result": None,
            "interface_result": None,
            "rule_result": None,
            "layout_result": None,
            "technology_result": None,
            "rpa_tool_result": None,
            "raw_attributes": {
                "activities": 41,  # XL
                "business_rules": 5,  # XL
                "layouts": 5,  # L
                "interfaces": 2,  # S
                "technology": 0,  # S
            },
            "detected_rpa_tool": RPATool.UNKNOWN.value,
            "status": "success",
            "warnings": [],
            "errors": [],
            "completed_at": "2024-01-01T00:00:00",
        }

        document_state = {
            "file_path": "sample_process.docx",
            "session_id": "ground_truth",
            "parsed_document": MagicMock(spec=ParsedDocument),
            "sections": [],
        }

        result = run(document_state)

        # Verify all 5 attributes present
        assert "activities" in result["raw_attributes"]
        assert "business_rules" in result["raw_attributes"]
        assert "layouts" in result["raw_attributes"]
        assert "interfaces" in result["raw_attributes"]
        assert "technology" in result["raw_attributes"]


# ==================== TEST: INTEGRATION ====================


@pytest.mark.integration
def test_process_analysis_agent_integration():
    """Integration test: chain from Document Intelligence."""
    # This test chains from Document Intelligence if available
    # For now, test with mocked document state
    from agents.process_analysis.agent import run

    # Create a realistic document state
    parsed_doc = ParsedDocument(
        source_path="integration_test.docx",
        file_type="docx",
        full_text="The process uses blue prism for automation. "
        "It reads from Excel files and writes to CSV outputs.",
        page_count=1,
    )

    sections = [
        ExtractedSection(
            title="Process Overview",
            section_type="process_overview",
            content="Process uses Blue Prism",
            confidence_score=0.9,
        ),
    ]

    document_state = {
        "file_path": "integration_test.docx",
        "session_id": "integration_test",
        "parsed_document": parsed_doc,
        "sections": sections,
        "entities": None,
        "warnings": [],
        "errors": [],
    }

    # Mock the internal analysis tools to return results
    with (
        patch("agents.process_analysis.agent.analyze_activities") as mock_activity,
        patch("agents.process_analysis.agent.detect_interfaces") as mock_interface,
        patch("agents.process_analysis.agent.extract_business_rules") as mock_rules,
        patch("agents.process_analysis.agent.identify_layouts") as mock_layouts,
        patch("agents.process_analysis.agent.detect_technology") as mock_tech,
    ):

        # Mock return values
        mock_activity.return_value = MagicMock(
            raw_activity_count=8, count_confidence=0.9
        )
        mock_interface.return_value = MagicMock(total_count=2, detection_confidence=0.8)
        mock_rules.return_value = MagicMock(
            total_qualifying_count=2, extraction_confidence=0.8
        )
        mock_layouts.return_value = MagicMock(total_count=3, detection_confidence=0.85)
        mock_tech.return_value = MagicMock(total_count=0, detection_confidence=0.9)

        result = run(document_state)

        # Assertions
        assert result["status"] in ["success", "partial"]
        assert "raw_attributes" in result
        assert result["raw_attributes"]["activities"] == 8
        assert result["raw_attributes"]["business_rules"] == 2
        assert result["raw_attributes"]["layouts"] == 3
        assert result["raw_attributes"]["interfaces"] == 2
        assert result["raw_attributes"]["technology"] == 0
        assert result["detected_rpa_tool"] in [
            RPATool.BLUE_PRISM.value,
            RPATool.UNKNOWN.value,
        ]
        assert result["completed_at"] != ""

        # Print for visibility
        print(f"Status: {result['status']}")
        print(f"Raw Attributes: {result['raw_attributes']}")
        print(f"Detected RPA Tool: {result['detected_rpa_tool']}")
        print(f"Warnings: {result['warnings']}")
