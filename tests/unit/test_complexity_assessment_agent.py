"""
Tests for the Complexity Assessment Agent.

Comprehensive tests for the agent orchestration, node execution,
and end-to-end integration with Phase 4 (Process Analysis).
"""

from unittest.mock import patch

import pytest

from agents.complexity_assessment.agent import (
    classify_complexity,
    run,
    score_attributes,
)
from core.constants import ComplexityTier, RPATool
from core.models.assessment import AssessmentResult, AttributeScore

# ==================== FIXTURES ====================


@pytest.fixture
def process_analysis_state() -> dict:
    """Build a ProcessAnalysisState output from Phase 4."""
    return {
        "file_path": "/path/to/sample_process.docx",
        "session_id": "test_session_123",
        "parsed_document": None,
        "sections": [],
        "entities": None,
        "raw_attributes": {
            "activities": 50,
            "business_rules": 5,
            "layouts": 4,
            "interfaces": 1,
            "technology": 0,
        },
        "detected_rpa_tool": "uipath",
        "status": "success",
        "warnings": [],
        "errors": [],
    }


@pytest.fixture
def ground_truth_scores() -> list[AttributeScore]:
    """Build ground truth AttributeScore list."""
    return [
        AttributeScore(
            attribute_id=1,
            attribute_name="Activities",
            raw_value=50,
            selected_tier=ComplexityTier.XL,
            weight=8,
            tier_rationale="50 activities (41-60 activities) → Extra Large (XL) complexity tier",
        ),
        AttributeScore(
            attribute_id=2,
            attribute_name="Business Rules",
            raw_value=5,
            selected_tier=ComplexityTier.XL,
            weight=8,
            tier_rationale="5 business rules (5-6 business rules) → Extra Large (XL) complexity tier",
        ),
        AttributeScore(
            attribute_id=3,
            attribute_name="Layouts",
            raw_value=4,
            selected_tier=ComplexityTier.L,
            weight=3,
            tier_rationale="4 layouts (4-6 layouts) → Large (L) complexity tier",
        ),
        AttributeScore(
            attribute_id=4,
            attribute_name="Interfaces",
            raw_value=1,
            selected_tier=ComplexityTier.S,
            weight=1,
            tier_rationale="1 interfaces (1-2 interfaces) → Small (S) complexity tier",
        ),
        AttributeScore(
            attribute_id=5,
            attribute_name="Additional Technology",
            raw_value=0,
            selected_tier=ComplexityTier.S,
            weight=1,
            tier_rationale="0 additional technology (0 additional technology) → Small (S) complexity tier",
        ),
    ]


# ==================== TEST score_attributes NODE ====================


class TestScoreAttributesNode:
    """Tests for score_attributes node."""

    def test_returns_dict(self, process_analysis_state):
        """Should return a dict."""
        result = score_attributes(process_analysis_state)
        assert isinstance(result, dict)

    def test_produces_5_attribute_scores(self, process_analysis_state):
        """Should produce exactly 5 AttributeScore objects."""
        result = score_attributes(process_analysis_state)
        scores = result.get("attribute_scores", [])
        assert len(scores) == 5
        for score in scores:
            assert isinstance(score, AttributeScore)

    def test_ground_truth_weights(self, process_analysis_state):
        """Should produce correct weights for ground truth case."""
        result = score_attributes(process_analysis_state)
        scores = result.get("attribute_scores", [])
        weights = [s.weight for s in scores]
        assert weights == [8, 8, 3, 1, 1]

    def test_empty_raw_attributes_fails(self, process_analysis_state):
        """Should set status=failed if raw_attributes is empty."""
        process_analysis_state["raw_attributes"] = {}
        result = score_attributes(process_analysis_state)
        assert result.get("status") == "failed"
        assert len(result.get("errors", [])) > 0

    def test_missing_raw_attributes_fails(self, process_analysis_state):
        """Should set status=failed if raw_attributes is missing."""
        del process_analysis_state["raw_attributes"]
        result = score_attributes(process_analysis_state)
        assert result.get("status") == "failed"

    def test_skips_if_already_failed(self, process_analysis_state):
        """Should skip if status is already failed."""
        process_analysis_state["status"] = "failed"
        result = score_attributes(process_analysis_state)
        assert result == {}

    def test_handles_unknown_rpa_tool(self, process_analysis_state):
        """Should handle unknown RPA tool gracefully."""
        process_analysis_state["detected_rpa_tool"] = "unknown_tool"
        result = score_attributes(process_analysis_state)
        scores = result.get("attribute_scores")
        assert scores is not None
        assert len(scores) == 5

    def test_handles_missing_rpa_tool(self, process_analysis_state):
        """Should handle missing RPA tool gracefully."""
        del process_analysis_state["detected_rpa_tool"]
        result = score_attributes(process_analysis_state)
        scores = result.get("attribute_scores")
        assert scores is not None
        assert len(scores) == 5

    def test_attribute_ids_in_order(self, process_analysis_state):
        """Attribute IDs should be 1-5 in order."""
        result = score_attributes(process_analysis_state)
        scores = result.get("attribute_scores", [])
        attr_ids = [s.attribute_id for s in scores]
        assert attr_ids == [1, 2, 3, 4, 5]

    def test_all_scores_have_tiers(self, process_analysis_state):
        """All scores should have valid complexity tiers."""
        result = score_attributes(process_analysis_state)
        scores = result.get("attribute_scores", [])
        for score in scores:
            assert score.selected_tier in list(ComplexityTier)

    def test_all_scores_have_weights(self, process_analysis_state):
        """All scores should have non-negative weights."""
        result = score_attributes(process_analysis_state)
        scores = result.get("attribute_scores", [])
        for score in scores:
            assert score.weight >= 0


# ==================== TEST classify_complexity NODE ====================


class TestClassifyComplexityNode:
    """Tests for classify_complexity node."""

    def test_returns_dict(self, process_analysis_state, ground_truth_scores):
        """Should return a dict."""
        state = {
            **process_analysis_state,
            "attribute_scores": ground_truth_scores,
        }
        with patch(
            "agents.complexity_assessment.agent.classify_and_explain"
        ) as mock_classify:
            mock_classify.return_value = AssessmentResult(
                session_id="test",
                project_name="test",
                rpa_tool=RPATool.UIPATH,
                attribute_scores=ground_truth_scores,
                total_score=21,
                complexity_tier=ComplexityTier.L,
                confidence_score=0.85,
                reasoning="Test reasoning",
                requires_tech_lead_review=False,
                created_at=__import__("datetime").datetime.utcnow(),
            )
            result = classify_complexity(state)
            assert isinstance(result, dict)

    def test_produces_assessment_result(
        self, process_analysis_state, ground_truth_scores
    ):
        """Should produce AssessmentResult."""
        state = {
            **process_analysis_state,
            "attribute_scores": ground_truth_scores,
        }
        with patch(
            "agents.complexity_assessment.agent.classify_and_explain"
        ) as mock_classify:
            mock_assess = AssessmentResult(
                session_id="test",
                project_name="test",
                rpa_tool=RPATool.UIPATH,
                attribute_scores=ground_truth_scores,
                total_score=21,
                complexity_tier=ComplexityTier.L,
                confidence_score=0.85,
                reasoning="Test",
                requires_tech_lead_review=False,
                created_at=__import__("datetime").datetime.utcnow(),
            )
            mock_classify.return_value = mock_assess
            result = classify_complexity(state)
            assert result.get("assessment_result") == mock_assess

    def test_sets_status_success(self, process_analysis_state, ground_truth_scores):
        """Should set status=success on success."""
        state = {
            **process_analysis_state,
            "attribute_scores": ground_truth_scores,
        }
        with patch(
            "agents.complexity_assessment.agent.classify_and_explain"
        ) as mock_classify:
            mock_assess = AssessmentResult(
                session_id="test",
                project_name="test",
                rpa_tool=RPATool.UIPATH,
                attribute_scores=ground_truth_scores,
                total_score=21,
                complexity_tier=ComplexityTier.L,
                confidence_score=0.85,
                reasoning="Test",
                requires_tech_lead_review=False,
                created_at=__import__("datetime").datetime.utcnow(),
            )
            mock_classify.return_value = mock_assess
            result = classify_complexity(state)
            assert result.get("status") == "success"

    def test_sets_completed_at(self, process_analysis_state, ground_truth_scores):
        """Should set completed_at timestamp."""
        state = {
            **process_analysis_state,
            "attribute_scores": ground_truth_scores,
        }
        with patch(
            "agents.complexity_assessment.agent.classify_and_explain"
        ) as mock_classify:
            mock_assess = AssessmentResult(
                session_id="test",
                project_name="test",
                rpa_tool=RPATool.UIPATH,
                attribute_scores=ground_truth_scores,
                total_score=21,
                complexity_tier=ComplexityTier.L,
                confidence_score=0.85,
                reasoning="Test",
                requires_tech_lead_review=False,
                created_at=__import__("datetime").datetime.utcnow(),
            )
            mock_classify.return_value = mock_assess
            result = classify_complexity(state)
            assert result.get("completed_at") != ""

    def test_skips_if_already_failed(self, process_analysis_state):
        """Should skip if status is already failed."""
        process_analysis_state["status"] = "failed"
        result = classify_complexity(process_analysis_state)
        assert result == {}

    def test_skips_if_no_attribute_scores(self, process_analysis_state):
        """Should skip if attribute_scores is empty."""
        process_analysis_state["attribute_scores"] = []
        result = classify_complexity(process_analysis_state)
        assert result == {}

    def test_extracts_project_name_from_filepath(
        self, process_analysis_state, ground_truth_scores
    ):
        """Should extract project name from file_path."""
        process_analysis_state["file_path"] = "/path/to/My_Process.docx"
        process_analysis_state["attribute_scores"] = ground_truth_scores
        with patch(
            "agents.complexity_assessment.agent.classify_and_explain"
        ) as mock_classify:
            mock_assess = AssessmentResult(
                session_id="test",
                project_name="test",
                rpa_tool=RPATool.UIPATH,
                attribute_scores=ground_truth_scores,
                total_score=21,
                complexity_tier=ComplexityTier.L,
                confidence_score=0.85,
                reasoning="Test",
                requires_tech_lead_review=False,
                created_at=__import__("datetime").datetime.utcnow(),
            )
            mock_classify.return_value = mock_assess
            classify_complexity(process_analysis_state)
            # Verify project_name was extracted
            call_kwargs = mock_classify.call_args.kwargs
            assert call_kwargs.get("project_name") == "My_Process"

    def test_parses_detected_rpa_tool(
        self, process_analysis_state, ground_truth_scores
    ):
        """Should parse detected_rpa_tool string."""
        process_analysis_state["detected_rpa_tool"] = "blue_prism"
        process_analysis_state["attribute_scores"] = ground_truth_scores
        with patch(
            "agents.complexity_assessment.agent.classify_and_explain"
        ) as mock_classify:
            mock_assess = AssessmentResult(
                session_id="test",
                project_name="test",
                rpa_tool=RPATool.BLUE_PRISM,
                attribute_scores=ground_truth_scores,
                total_score=21,
                complexity_tier=ComplexityTier.L,
                confidence_score=0.85,
                reasoning="Test",
                requires_tech_lead_review=False,
                created_at=__import__("datetime").datetime.utcnow(),
            )
            mock_classify.return_value = mock_assess
            classify_complexity(process_analysis_state)
            # Verify rpa_tool was parsed
            call_kwargs = mock_classify.call_args.kwargs
            assert call_kwargs.get("rpa_tool") == RPATool.BLUE_PRISM


# ==================== TEST run FUNCTION ====================


class TestRunFunction:
    """Tests for run() public function."""

    def test_returns_state_dict(self, process_analysis_state):
        """Should return ComplexityAssessmentState dict."""
        with (
            patch("agents.complexity_assessment.agent.score_attributes") as mock_score,
            patch(
                "agents.complexity_assessment.agent.classify_complexity"
            ) as mock_classify,
        ):
            mock_score.return_value = {
                "attribute_scores": [
                    AttributeScore(
                        attribute_id=i,
                        attribute_name=f"Attr {i}",
                        raw_value=10,
                        selected_tier=ComplexityTier.M,
                        weight=4,
                        tier_rationale="Test",
                    )
                    for i in range(1, 6)
                ]
            }
            mock_assess = AssessmentResult(
                session_id="test",
                project_name="test",
                rpa_tool=RPATool.UIPATH,
                attribute_scores=[
                    AttributeScore(
                        attribute_id=i,
                        attribute_name=f"Attr {i}",
                        raw_value=10,
                        selected_tier=ComplexityTier.M,
                        weight=4,
                        tier_rationale="Test",
                    )
                    for i in range(1, 6)
                ],
                total_score=20,
                complexity_tier=ComplexityTier.M,
                confidence_score=0.75,
                reasoning="Test",
                requires_tech_lead_review=False,
                created_at=__import__("datetime").datetime.utcnow(),
            )
            mock_classify.return_value = {
                "assessment_result": mock_assess,
                "status": "success",
                "completed_at": "2026-03-17T00:00:00",
            }

            result = run(process_analysis_state)
            assert isinstance(result, dict)

    def test_inherits_session_id(self, process_analysis_state):
        """Should inherit session_id from input."""
        with patch("agents.complexity_assessment.agent._graph.invoke") as mock_invoke:
            mock_invoke.return_value = {
                **process_analysis_state,
                "assessment_result": None,
                "attribute_scores": [],
                "status": "success",
            }
            run(process_analysis_state)
            # The state passed to graph should have inherited session_id
            call_state = mock_invoke.call_args[0][0]
            assert call_state["session_id"] == "test_session_123"

    def test_uses_provided_session_id(self, process_analysis_state):
        """Should use provided session_id."""
        with patch("agents.complexity_assessment.agent._graph.invoke") as mock_invoke:
            mock_invoke.return_value = {
                **process_analysis_state,
                "assessment_result": None,
                "attribute_scores": [],
                "status": "success",
            }
            run(process_analysis_state, session_id="custom_session")
            call_state = mock_invoke.call_args[0][0]
            assert call_state["session_id"] == "custom_session"

    def test_inherits_file_path(self, process_analysis_state):
        """Should inherit file_path from input."""
        with patch("agents.complexity_assessment.agent._graph.invoke") as mock_invoke:
            mock_invoke.return_value = {
                **process_analysis_state,
                "assessment_result": None,
                "attribute_scores": [],
                "status": "success",
            }
            run(process_analysis_state)
            call_state = mock_invoke.call_args[0][0]
            assert call_state["file_path"] == "/path/to/sample_process.docx"

    def test_inherits_raw_attributes(self, process_analysis_state):
        """Should inherit raw_attributes from input."""
        with patch("agents.complexity_assessment.agent._graph.invoke") as mock_invoke:
            mock_invoke.return_value = {
                **process_analysis_state,
                "assessment_result": None,
                "attribute_scores": [],
                "status": "success",
            }
            run(process_analysis_state)
            call_state = mock_invoke.call_args[0][0]
            assert call_state["raw_attributes"]["activities"] == 50

    def test_inherits_warnings_and_errors(self, process_analysis_state):
        """Should inherit warnings and errors from input."""
        process_analysis_state["warnings"] = ["Warning 1"]
        process_analysis_state["errors"] = ["Error 1"]
        with patch("agents.complexity_assessment.agent._graph.invoke") as mock_invoke:
            mock_invoke.return_value = {
                **process_analysis_state,
                "assessment_result": None,
                "attribute_scores": [],
                "status": "success",
            }
            run(process_analysis_state)
            call_state = mock_invoke.call_args[0][0]
            assert "Warning 1" in call_state["warnings"]
            assert "Error 1" in call_state["errors"]


# ==================== INTEGRATION TESTS ====================


@pytest.mark.integration
class TestComplexityAssessmentIntegration:
    """Integration tests for the full complexity assessment pipeline."""

    def test_full_chain_from_process_analysis_to_assessment(
        self, process_analysis_state
    ):
        """Test the full chain: PA → CA → AssessmentResult.

        This is a simplified integration test that does not require the
        full Document Intelligence and Process Analysis agents.
        """

        # Run the agent with mocked LLM
        with patch(
            "tools.scoring.classifier_tool.LLMManager.complete_structured"
        ) as mock_llm:
            from tools.scoring.classifier_tool import ReasoningResponse

            mock_llm.return_value = ReasoningResponse(
                reasoning="This process has moderate complexity with 5 distinct "
                "activities and several decision points.",
                key_drivers=[
                    "Multiple business rules",
                    "Multi-layout UI interaction",
                ],
                simplification_opportunities=["Consolidate similar business rules"],
                tech_lead_note="",
            )

            result = run(process_analysis_state)

            # Verify structure
            assert result is not None
            assert isinstance(result, dict)
            assert result.get("status") == "success" or "attribute_scores" in result

            # Verify assessment result if present
            assessment = result.get("assessment_result")
            if assessment:
                assert isinstance(assessment, AssessmentResult)
                assert assessment.complexity_tier in list(ComplexityTier)
                assert 0 <= assessment.total_score <= 28
                assert 0.0 <= assessment.confidence_score <= 1.0
                assert assessment.reasoning != ""
                assert isinstance(assessment.requires_tech_lead_review, bool)

                # Print summary for manual inspection
                print("\n" + "=" * 50)
                print("Integration Test Score Summary")
                print("=" * 50)
                print(assessment.score_summary)
                print("\nReasoning:")
                print(assessment.reasoning[:200] + "...")
                print("\nKey Details:")
                print(f"  Tier: {assessment.complexity_tier.value}")
                print(f"  Score: {assessment.total_score}/28")
                print(f"  Confidence: {assessment.confidence_score:.0%}")
                print(f"  Tech Lead Review: {assessment.requires_tech_lead_review}")
