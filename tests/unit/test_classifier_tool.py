"""
Tests for the classifier tool.

Comprehensive tests for generating complexity assessment results with
LLM-based reasoning narratives.
"""

from unittest.mock import MagicMock, patch

import pytest

from core.constants import ComplexityTier, RPATool
from core.exceptions import LLMProviderError
from core.models.assessment import AssessmentResult, AttributeScore
from tools.scoring.classifier_tool import (
    ReasoningResponse,
    _build_attribute_breakdown,
    _build_score_summary,
    _check_requires_tech_lead_review,
    classify_and_explain,
    generate_reasoning,
)


# ==================== FIXTURES ====================


@pytest.fixture
def ground_truth_scores() -> list[AttributeScore]:
    """Build the ground truth case from CLAUDE.md.

    Activities: XL (41-60) → weight 8
    Business Rules: XL (5-6) → weight 8
    Layouts: L (4-6) → weight 3
    Interfaces: S (1-2) → weight 1
    Technology: S (0) → weight 1
    Total: 21 → L tier
    """
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


# ==================== TEST _build_attribute_breakdown ====================


class TestBuildAttributeBreakdown:
    """Tests for _build_attribute_breakdown helper."""

    def test_returns_string(self, ground_truth_scores):
        """Should return a string."""
        result = _build_attribute_breakdown(ground_truth_scores)
        assert isinstance(result, str)

    def test_contains_all_attributes(self, ground_truth_scores):
        """Should contain all 5 attributes."""
        result = _build_attribute_breakdown(ground_truth_scores)
        assert "#1" in result
        assert "#2" in result
        assert "#3" in result
        assert "#4" in result
        assert "#5" in result

    def test_contains_attribute_names(self, ground_truth_scores):
        """Should reference attribute names."""
        result = _build_attribute_breakdown(ground_truth_scores)
        assert "Activities" in result
        assert "Business Rules" in result
        assert "Layouts" in result
        assert "Interfaces" in result
        assert "Additional Technology" in result

    def test_contains_tier_values(self, ground_truth_scores):
        """Should contain tier names."""
        result = _build_attribute_breakdown(ground_truth_scores)
        assert "XL" in result
        assert "L" in result
        assert "S" in result

    def test_contains_raw_values(self, ground_truth_scores):
        """Should reference raw values."""
        result = _build_attribute_breakdown(ground_truth_scores)
        assert "50" in result  # Activities
        assert "5" in result   # Business rules
        assert "4" in result   # Layouts
        assert "1" in result   # Interfaces
        assert "0" in result   # Technology

    def test_contains_weights(self, ground_truth_scores):
        """Should include weight values."""
        result = _build_attribute_breakdown(ground_truth_scores)
        assert "weight: 8" in result
        assert "weight: 3" in result
        assert "weight: 1" in result

    def test_multiline_format(self, ground_truth_scores):
        """Should return multi-line string."""
        result = _build_attribute_breakdown(ground_truth_scores)
        lines = result.split("\n")
        assert len(lines) == 5


# ==================== TEST _build_score_summary ====================


class TestBuildScoreSummary:
    """Tests for _build_score_summary helper."""

    def test_returns_string(self, ground_truth_scores):
        """Should return a string."""
        result = _build_score_summary(
            ground_truth_scores, ComplexityTier.L, 21, 0.85
        )
        assert isinstance(result, str)

    def test_contains_total_score(self, ground_truth_scores):
        """Should reference total score."""
        result = _build_score_summary(
            ground_truth_scores, ComplexityTier.L, 21, 0.85
        )
        assert "21" in result
        assert "/28" in result

    def test_contains_tier(self, ground_truth_scores):
        """Should reference complexity tier."""
        result = _build_score_summary(
            ground_truth_scores, ComplexityTier.L, 21, 0.85
        )
        assert "L" in result

    def test_contains_confidence(self, ground_truth_scores):
        """Should reference confidence as percentage."""
        result = _build_score_summary(
            ground_truth_scores, ComplexityTier.L, 21, 0.85
        )
        assert "85%" in result


# ==================== TEST _check_requires_tech_lead_review ====================


class TestCheckRequiresTechLeadReview:
    """Tests for _check_requires_tech_lead_review helper."""

    def test_returns_bool(self, ground_truth_scores):
        """Should return boolean."""
        result = _check_requires_tech_lead_review(
            ground_truth_scores, ComplexityTier.L, 21
        )
        assert isinstance(result, bool)

    def test_true_for_xl_tier(self, ground_truth_scores):
        """Should return True for XL tier."""
        result = _check_requires_tech_lead_review(
            ground_truth_scores, ComplexityTier.XL, 21
        )
        assert result is True

    def test_true_for_score_greater_than_25(self, ground_truth_scores):
        """Should return True when score > 25."""
        result = _check_requires_tech_lead_review(
            ground_truth_scores, ComplexityTier.L, 26
        )
        assert result is True

    def test_false_for_l_tier_score_21(self, ground_truth_scores):
        """Should return False for L tier with score 21."""
        result = _check_requires_tech_lead_review(
            ground_truth_scores, ComplexityTier.L, 21
        )
        assert result is False

    def test_true_for_ceiling_violation_marker(self):
        """Should return True if any rationale contains ⚠️."""
        scores = [
            AttributeScore(
                attribute_id=1,
                attribute_name="Activities",
                raw_value=70,
                selected_tier=ComplexityTier.XL,
                weight=8,
                tier_rationale="⚠️ Exceeds XL ceiling",
            ),
            AttributeScore(
                attribute_id=2,
                attribute_name="Business Rules",
                raw_value=5,
                selected_tier=ComplexityTier.XL,
                weight=8,
                tier_rationale="Normal rationale",
            ),
            AttributeScore(
                attribute_id=3,
                attribute_name="Layouts",
                raw_value=1,
                selected_tier=ComplexityTier.S,
                weight=1,
                tier_rationale="Normal",
            ),
            AttributeScore(
                attribute_id=4,
                attribute_name="Interfaces",
                raw_value=1,
                selected_tier=ComplexityTier.S,
                weight=1,
                tier_rationale="Normal",
            ),
            AttributeScore(
                attribute_id=5,
                attribute_name="Technology",
                raw_value=0,
                selected_tier=ComplexityTier.S,
                weight=1,
                tier_rationale="Normal",
            ),
        ]
        result = _check_requires_tech_lead_review(scores, ComplexityTier.XL, 20)
        assert result is True


# ==================== TEST generate_reasoning ====================


class TestGenerateReasoning:
    """Tests for generate_reasoning function."""

    def test_returns_reasoning_response(self, ground_truth_scores):
        """Should return ReasoningResponse instance."""
        with patch.object(
            __import__("llm.manager", fromlist=["LLMManager"]).LLMManager,
            "complete_structured",
        ) as mock_complete:
            mock_complete.return_value = ReasoningResponse(
                reasoning="Test reasoning",
                key_drivers=["Driver 1", "Driver 2"],
            )
            result = generate_reasoning(
                attribute_scores=ground_truth_scores,
                tier=ComplexityTier.L,
                total_score=21,
                confidence=0.85,
            )
            assert isinstance(result, ReasoningResponse)

    def test_reasoning_is_non_empty(self, ground_truth_scores):
        """Should always have non-empty reasoning."""
        with patch.object(
            __import__("llm.manager", fromlist=["LLMManager"]).LLMManager,
            "complete_structured",
        ) as mock_complete:
            # First, mock an empty reasoning response
            mock_complete.return_value = ReasoningResponse(reasoning="")
            result = generate_reasoning(
                attribute_scores=ground_truth_scores,
                tier=ComplexityTier.L,
                total_score=21,
                confidence=0.85,
            )
            # Validator should fill it with default
            assert result.reasoning != ""
            assert "Assessment complete" in result.reasoning

    def test_includes_all_attributes_in_breakdown(self, ground_truth_scores):
        """Should include all attributes in the prompt."""
        with patch.object(
            __import__("llm.manager", fromlist=["LLMManager"]).LLMManager,
            "complete_structured",
        ) as mock_complete:
            mock_complete.return_value = ReasoningResponse(
                reasoning="Test"
            )
            generate_reasoning(
                attribute_scores=ground_truth_scores,
                tier=ComplexityTier.L,
                total_score=21,
                confidence=0.85,
            )
            # Verify the prompt was called with breakdown
            call_args = mock_complete.call_args
            prompt = call_args.kwargs.get("prompt", "")
            assert "#1" in prompt
            assert "#5" in prompt

    def test_fallback_on_llm_failure(self, ground_truth_scores):
        """Should return fallback on LLM failure."""
        with patch.object(
            __import__("llm.manager", fromlist=["LLMManager"]).LLMManager,
            "complete_structured",
        ) as mock_complete:
            # First call fails, second call succeeds with fallback
            mock_complete.side_effect = [
                LLMProviderError("First attempt failed"),
                ReasoningResponse(reasoning="Fallback response"),
            ]
            result = generate_reasoning(
                attribute_scores=ground_truth_scores,
                tier=ComplexityTier.L,
                total_score=21,
                confidence=0.85,
            )
            assert isinstance(result, ReasoningResponse)
            assert "Fallback" in result.reasoning

    def test_hardcoded_fallback_on_double_failure(self, ground_truth_scores):
        """Should return hardcoded fallback if both LLM attempts fail."""
        with patch.object(
            __import__("llm.manager", fromlist=["LLMManager"]).LLMManager,
            "complete_structured",
        ) as mock_complete:
            # Both attempts fail
            mock_complete.side_effect = LLMProviderError("Failed")
            result = generate_reasoning(
                attribute_scores=ground_truth_scores,
                tier=ComplexityTier.L,
                total_score=21,
                confidence=0.85,
            )
            assert isinstance(result, ReasoningResponse)
            assert "L complexity" in result.reasoning
            assert "21/28" in result.reasoning

    def test_sets_session_id(self, ground_truth_scores):
        """Should log with session_id."""
        with patch.object(
            __import__("llm.manager", fromlist=["LLMManager"]).LLMManager,
            "complete_structured",
        ) as mock_complete:
            mock_complete.return_value = ReasoningResponse(reasoning="Test")
            generate_reasoning(
                attribute_scores=ground_truth_scores,
                tier=ComplexityTier.L,
                total_score=21,
                confidence=0.85,
                session_id="test_session",
            )
            # Verify session_id was passed to LLM
            call_kwargs = mock_complete.call_args.kwargs
            assert call_kwargs.get("session_id") == "test_session"


# ==================== TEST classify_and_explain ====================


class TestClassifyAndExplain:
    """Tests for classify_and_explain function."""

    def test_returns_assessment_result(self, ground_truth_scores):
        """Should return AssessmentResult instance."""
        with patch(
            "tools.scoring.classifier_tool.generate_reasoning"
        ) as mock_reason:
            mock_reason.return_value = ReasoningResponse(reasoning="Test")
            result = classify_and_explain(
                attribute_scores=ground_truth_scores,
                project_name="Test Project",
            )
            assert isinstance(result, AssessmentResult)

    def test_ground_truth_case(self, ground_truth_scores):
        """Verify ground truth case from CLAUDE.md.

        Activities: XL (41-60) → weight 8
        Business Rules: XL (5-6) → weight 8
        Layouts: L (4-6) → weight 3
        Interfaces: S (1-2) → weight 1
        Technology: S (0) → weight 1
        Total: 21 → L tier
        """
        with patch(
            "tools.scoring.classifier_tool.generate_reasoning"
        ) as mock_reason:
            mock_reason.return_value = ReasoningResponse(reasoning="Test")
            result = classify_and_explain(
                attribute_scores=ground_truth_scores,
                project_name="Ground Truth Case",
            )
            assert result.complexity_tier == ComplexityTier.L
            assert result.total_score == 21
            assert result.requires_tech_lead_review is False
            assert isinstance(result, AssessmentResult)

    def test_result_has_all_fields(self, ground_truth_scores):
        """Should populate all required AssessmentResult fields."""
        with patch(
            "tools.scoring.classifier_tool.generate_reasoning"
        ) as mock_reason:
            mock_reason.return_value = ReasoningResponse(reasoning="Test")
            result = classify_and_explain(
                attribute_scores=ground_truth_scores,
                project_name="Test Project",
                rpa_tool=RPATool.UIPATH,
            )
            assert result.session_id != ""
            assert result.project_name == "Test Project"
            assert result.rpa_tool == RPATool.UIPATH
            assert result.attribute_scores == ground_truth_scores
            assert result.total_score == 21
            assert result.complexity_tier == ComplexityTier.L
            assert 0.0 <= result.confidence_score <= 1.0
            assert result.reasoning != ""
            assert result.requires_tech_lead_review is False
            assert result.created_at is not None

    def test_xl_tier_requires_tech_lead(self):
        """XL tier should set requires_tech_lead_review to True."""
        xl_scores = [
            AttributeScore(
                attribute_id=1,
                attribute_name="Activities",
                raw_value=50,
                selected_tier=ComplexityTier.XL,
                weight=8,
                tier_rationale="XL",
            ),
            AttributeScore(
                attribute_id=2,
                attribute_name="Business Rules",
                raw_value=5,
                selected_tier=ComplexityTier.XL,
                weight=8,
                tier_rationale="XL",
            ),
            AttributeScore(
                attribute_id=3,
                attribute_name="Layouts",
                raw_value=5,
                selected_tier=ComplexityTier.XL,
                weight=4,
                tier_rationale="XL",
            ),
            AttributeScore(
                attribute_id=4,
                attribute_name="Interfaces",
                raw_value=7,
                selected_tier=ComplexityTier.XL,
                weight=4,
                tier_rationale="XL",
            ),
            AttributeScore(
                attribute_id=5,
                attribute_name="Technology",
                raw_value=4,
                selected_tier=ComplexityTier.XL,
                weight=4,
                tier_rationale="XL",
            ),
        ]
        with patch(
            "tools.scoring.classifier_tool.generate_reasoning"
        ) as mock_reason:
            mock_reason.return_value = ReasoningResponse(reasoning="XL test")
            result = classify_and_explain(
                attribute_scores=xl_scores,
                project_name="XL Test",
            )
            assert result.complexity_tier == ComplexityTier.XL
            assert result.requires_tech_lead_review is True

    def test_inherits_session_id(self, ground_truth_scores):
        """Should use provided session_id."""
        with patch(
            "tools.scoring.classifier_tool.generate_reasoning"
        ) as mock_reason:
            mock_reason.return_value = ReasoningResponse(reasoning="Test")
            result = classify_and_explain(
                attribute_scores=ground_truth_scores,
                session_id="custom_session_123",
            )
            assert result.session_id == "custom_session_123"

    def test_generates_new_session_if_not_provided(self, ground_truth_scores):
        """Should generate session_id if not provided."""
        with patch(
            "tools.scoring.classifier_tool.generate_reasoning"
        ) as mock_reason:
            mock_reason.return_value = ReasoningResponse(reasoning="Test")
            result = classify_and_explain(
                attribute_scores=ground_truth_scores,
                session_id="",
            )
            assert result.session_id != ""
            assert len(result.session_id) == 8  # UUID first 8 chars

    def test_confidence_in_valid_range(self, ground_truth_scores):
        """Confidence should always be between 0.0 and 1.0."""
        with patch(
            "tools.scoring.classifier_tool.generate_reasoning"
        ) as mock_reason:
            mock_reason.return_value = ReasoningResponse(reasoning="Test")
            result = classify_and_explain(
                attribute_scores=ground_truth_scores,
            )
            assert 0.0 <= result.confidence_score <= 1.0

    def test_reasoning_appends_tech_note(self):
        """Should append tech_lead_note if present."""
        # Create scores that total > 25 to trigger tech lead review
        xl_scores = [
            AttributeScore(
                attribute_id=1,
                attribute_name="Activities",
                raw_value=50,
                selected_tier=ComplexityTier.XL,
                weight=8,
                tier_rationale="XL",
            ),
            AttributeScore(
                attribute_id=2,
                attribute_name="Business Rules",
                raw_value=5,
                selected_tier=ComplexityTier.XL,
                weight=8,
                tier_rationale="XL",
            ),
            AttributeScore(
                attribute_id=3,
                attribute_name="Layouts",
                raw_value=5,
                selected_tier=ComplexityTier.XL,
                weight=4,
                tier_rationale="XL",
            ),
            AttributeScore(
                attribute_id=4,
                attribute_name="Interfaces",
                raw_value=1,
                selected_tier=ComplexityTier.S,
                weight=1,
                tier_rationale="S",
            ),
            AttributeScore(
                attribute_id=5,
                attribute_name="Technology",
                raw_value=0,
                selected_tier=ComplexityTier.S,
                weight=1,
                tier_rationale="S",
            ),
        ]
        with patch(
            "tools.scoring.classifier_tool.generate_reasoning"
        ) as mock_reason:
            mock_reason.return_value = ReasoningResponse(
                reasoning="Main reasoning",
                tech_lead_note="Special attention required",
            )
            result = classify_and_explain(
                attribute_scores=xl_scores,
            )
            assert "Main reasoning" in result.reasoning
            assert "Tech Lead Note:" in result.reasoning
            assert "Special attention required" in result.reasoning
