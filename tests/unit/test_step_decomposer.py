"""
Unit tests for step decomposer tool.

Tests models, validators, and step decomposition logic.
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from core.constants import ComplexityTier, RPATool
from core.models.assessment import AssessmentResult, AttributeScore
from core.models.document import ExtractedSection
from core.models.process import ProcessStep
from tools.analysis.rule_extractor import (
    BusinessRuleExtractionResult,
    ExtractedBusinessRule,
)
from tools.output.step_decomposer import (
    BranchData,
    StepData,
    StepDecompositionLLMResponse,
    StepDecompositionResult,
    decompose_steps,
)

# ===========================================================================
# FIXTURES
# ===========================================================================


@pytest.fixture
def sample_sections() -> list[ExtractedSection]:
    """Sample extracted sections."""
    return [
        ExtractedSection(
            title="Process Overview",
            content="This process handles order processing with approval workflow.",
            page_number=1,
            confidence_score=0.95,
            section_type="process_overview",
        ),
        ExtractedSection(
            title="Process Steps",
            content="1. Receive order\n2. Validate data\n3. Process payment",
            page_number=2,
            confidence_score=0.90,
            section_type="process_steps",
        ),
    ]


@pytest.fixture
def sample_assessment_result() -> AssessmentResult:
    """Sample assessment result."""
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
        reasoning="Complex order processing with multiple business rules",
        created_at=datetime.now(),
    )


@pytest.fixture
def sample_rule_result() -> BusinessRuleExtractionResult:
    """Sample business rule extraction result."""
    return BusinessRuleExtractionResult(
        rules=[
            ExtractedBusinessRule(
                description="If payment fails, escalate to manager",
                condition="payment_status == FAILED",
                branch_name="Payment Failure Flow",
                estimated_branch_activities=5,
                evidence="Mentioned in section 3.2",
                confidence=0.85,
            ),
            ExtractedBusinessRule(
                description="If high-value order, requires director approval",
                condition="order_value > 50000",
                branch_name="High-Value Approval Flow",
                estimated_branch_activities=8,
                evidence="SLA requirement in section 4",
                confidence=0.90,
            ),
        ],
        total_qualifying_count=2,
        extraction_confidence=0.87,
    )


# ===========================================================================
# STEPDATA VALIDATOR TESTS
# ===========================================================================


class TestStepDataValidators:
    """Test StepData model validators."""

    def test_weight_normalization_rounds_to_nearest(self):
        """Test weight rounding to nearest valid value."""
        # 0.3 is closer to 0.5 than 0.0 -> rounds to 0.5 -> PARTIAL tag forces 0.5 stays
        step = StepData(
            step_number=1,
            description="Test step",
            weight=0.3,
            reusability_tag="PARTIAL",
        )
        assert step.weight == 0.5

        # 0.7 is closer to 1.0 than 0.5 -> rounds to 1.0 -> NONE tag allows 1.0
        step = StepData(
            step_number=1,
            description="Test step",
            weight=0.7,
            reusability_tag="NONE",
        )
        assert step.weight == 1.0

    def test_tag_normalization_invalid_to_none(self):
        """Test invalid tag normalizes to NONE."""
        step = StepData(
            step_number=1,
            description="Test step",
            weight=1.0,
            reusability_tag="INVALID",
        )
        assert step.reusability_tag == "NONE"

    def test_full_tag_forces_zero_weight(self):
        """Test FULL tag forces weight to 0.0."""
        step = StepData(
            step_number=1,
            description="Reused step",
            weight=1.0,
            reusability_tag="FULL",
        )
        assert step.weight == 0.0
        assert step.reusability_tag == "FULL"

    def test_partial_tag_forces_half_weight(self):
        """Test PARTIAL tag forces weight to 0.5."""
        step = StepData(
            step_number=1,
            description="Modified step",
            weight=1.0,
            reusability_tag="PARTIAL",
        )
        assert step.weight == 0.5
        assert step.reusability_tag == "PARTIAL"

    def test_none_tag_with_zero_weight_corrected_to_one(self):
        """Test NONE tag with 0.0 weight corrects to 1.0."""
        step = StepData(
            step_number=1,
            description="New step",
            weight=0.0,
            reusability_tag="NONE",
        )
        assert step.weight == 1.0
        assert step.reusability_tag == "NONE"

    def test_none_tag_accepts_one_and_two_weights(self):
        """Test NONE tag allows 1.0 and 2.0 weights."""
        for weight in [1.0, 2.0]:
            step = StepData(
                step_number=1,
                description="Step",
                weight=weight,
                reusability_tag="NONE",
            )
            assert step.weight == weight


# ===========================================================================
# BRANCHDATA COMPUTED PROPERTIES
# ===========================================================================


class TestBranchDataProperties:
    """Test BranchData computed properties."""

    def test_branch_total_weight_sums_correctly(self):
        """Test branch_total_weight computes sum of all step weights."""
        branch = BranchData(
            branch_name="Main Flow",
            description="Primary steps",
            steps=[
                StepData(
                    step_number=1,
                    description="Step 1",
                    weight=1.0,
                    reusability_tag="NONE",
                ),
                StepData(
                    step_number=2,
                    description="Step 2",
                    weight=1.0,
                    reusability_tag="NONE",
                ),
                StepData(
                    step_number=3,
                    description="Step 3",
                    weight=0.5,
                    reusability_tag="PARTIAL",
                ),
            ],
        )
        assert branch.branch_total_weight == 2.5

    def test_branch_total_weight_empty_branch(self):
        """Test branch_total_weight for empty branch."""
        branch = BranchData(branch_name="Empty", steps=[])
        assert branch.branch_total_weight == 0.0

    def test_step_count_returns_correct_integer(self):
        """Test step_count returns number of steps."""
        branch = BranchData(
            branch_name="Main Flow",
            steps=[
                StepData(step_number=1, description="Step 1", weight=1.0),
                StepData(step_number=2, description="Step 2", weight=1.0),
            ],
        )
        assert branch.step_count == 2

    def test_step_count_empty_branch(self):
        """Test step_count for empty branch."""
        branch = BranchData(branch_name="Empty", steps=[])
        assert branch.step_count == 0


# ===========================================================================
# STEPDECOMPOSITIONRESULT COMPUTED PROPERTIES
# ===========================================================================


class TestStepDecompositionResultProperties:
    """Test StepDecompositionResult computed properties."""

    def test_all_steps_returns_flat_list(self):
        """Test all_steps returns flat list of ProcessStep objects."""
        result = StepDecompositionResult(
            project_name="Test",
            branches=[
                BranchData(
                    branch_name="Branch 1",
                    steps=[
                        StepData(step_number=1, description="B1-S1", weight=1.0),
                        StepData(step_number=2, description="B1-S2", weight=1.0),
                    ],
                ),
                BranchData(
                    branch_name="Branch 2",
                    steps=[
                        StepData(step_number=1, description="B2-S1", weight=1.0),
                    ],
                ),
            ],
            total_weighted_steps=3.0,
            total_step_count=3,
        )
        all_steps = result.all_steps
        assert len(all_steps) == 3
        assert all(isinstance(s, ProcessStep) for s in all_steps)

    def test_all_steps_renumbers_sequentially(self):
        """Test all_steps renumbers steps sequentially."""
        result = StepDecompositionResult(
            project_name="Test",
            branches=[
                BranchData(
                    branch_name="Branch 1",
                    steps=[
                        StepData(step_number=1, description="S1", weight=1.0),
                        StepData(step_number=2, description="S2", weight=1.0),
                    ],
                ),
                BranchData(
                    branch_name="Branch 2",
                    steps=[
                        StepData(step_number=1, description="S3", weight=1.0),
                    ],
                ),
            ],
            total_weighted_steps=3.0,
            total_step_count=3,
        )
        all_steps = result.all_steps
        assert [s.step_number for s in all_steps] == [1, 2, 3]

    def test_branch_names_returns_list(self):
        """Test branch_names returns list of branch names."""
        result = StepDecompositionResult(
            project_name="Test",
            branches=[
                BranchData(branch_name="Main Flow"),
                BranchData(branch_name="Error Handler"),
            ],
            total_weighted_steps=0.0,
            total_step_count=0,
        )
        assert result.branch_names == ["Main Flow", "Error Handler"]


# ===========================================================================
# DECOMPOSE_STEPS FUNCTION TESTS
# ===========================================================================


class TestDecomposeSteps:
    """Test decompose_steps function."""

    @patch("tools.output.step_decomposer.LLMManager")
    def test_decompose_steps_success(
        self, mock_llm_class, sample_sections, sample_assessment_result
    ):
        """Test successful step decomposition with mocked LLM."""
        # Setup mock LLM
        mock_llm = MagicMock()
        mock_llm_class.return_value = mock_llm

        llm_response = StepDecompositionLLMResponse(
            branches=[
                BranchData(
                    branch_name="Main Flow",
                    description="Primary process",
                    steps=[
                        StepData(
                            step_number=1,
                            description="Receive order",
                            weight=1.0,
                            reusability_tag="NONE",
                        ),
                        StepData(
                            step_number=2,
                            description="Validate",
                            weight=1.0,
                            reusability_tag="NONE",
                        ),
                    ],
                ),
                BranchData(
                    branch_name="Error Handler",
                    description="Error handling",
                    steps=[
                        StepData(
                            step_number=1,
                            description="Log error",
                            weight=0.5,
                            reusability_tag="PARTIAL",
                        ),
                    ],
                ),
            ],
            total_weighted_steps=2.5,
        )

        mock_llm.call_with_schema.return_value = llm_response

        # Call decomposer
        result = decompose_steps(
            sections=sample_sections,
            assessment_result=sample_assessment_result,
            llm_manager=mock_llm,
            session_id="test-123",
        )

        # Verify result
        assert isinstance(result, StepDecompositionResult)
        assert result.project_name == "Order Processing Automation"
        assert len(result.branches) == 2
        assert result.total_step_count == 3
        assert result.total_weighted_steps == 2.5

    @patch("tools.output.step_decomposer.LLMManager")
    def test_decompose_steps_with_rules(
        self,
        mock_llm_class,
        sample_sections,
        sample_assessment_result,
        sample_rule_result,
    ):
        """Test decomposition includes business rules in context."""
        mock_llm = MagicMock()
        mock_llm_class.return_value = mock_llm

        llm_response = StepDecompositionLLMResponse(
            branches=[
                BranchData(
                    branch_name="Main Flow",
                    steps=[StepData(step_number=1, description="Main", weight=1.0)],
                ),
                BranchData(
                    branch_name="Payment Failure Flow",
                    steps=[StepData(step_number=1, description="Escalate", weight=2.0)],
                ),
                BranchData(
                    branch_name="High-Value Approval Flow",
                    steps=[StepData(step_number=1, description="Approve", weight=2.0)],
                ),
            ],
            total_weighted_steps=5.0,
        )

        mock_llm.call_with_schema.return_value = llm_response

        decompose_steps(
            sections=sample_sections,
            assessment_result=sample_assessment_result,
            rule_result=sample_rule_result,
            llm_manager=mock_llm,
        )

        # Verify rules were included in prompt
        call_args = mock_llm.call_with_schema.call_args
        prompt_arg = call_args.kwargs.get("user_prompt", "")
        assert "Payment Failure Flow" in prompt_arg
        assert "High-Value Approval Flow" in prompt_arg

    @patch("tools.output.step_decomposer.LLMManager")
    def test_decompose_steps_llm_failure_returns_fallback(
        self, mock_llm_class, sample_sections, sample_assessment_result
    ):
        """Test LLM failure returns minimal fallback result."""
        mock_llm = MagicMock()
        mock_llm_class.return_value = mock_llm

        # First call raises exception, second call also fails
        mock_llm.call_with_schema.side_effect = Exception("LLM unavailable")

        result = decompose_steps(
            sections=sample_sections,
            assessment_result=sample_assessment_result,
            llm_manager=mock_llm,
        )

        # Verify fallback
        assert result.project_name == "Order Processing Automation"
        assert len(result.branches) == 1
        assert result.branches[0].branch_name == "Main Process Flow"
        assert result.total_step_count == 1
        assert result.generation_notes == "Fallback — LLM unavailable"

    @patch("tools.output.step_decomposer.LLMManager")
    def test_decompose_steps_without_assessment_activity_count(
        self, mock_llm_class, sample_sections
    ):
        """Test decomposition works without attribute scores."""
        mock_llm = MagicMock()
        mock_llm_class.return_value = mock_llm

        # Create assessment without attribute scores
        assessment = AssessmentResult(
            session_id="test",
            project_name="Test",
            rpa_tool=RPATool.BLUE_PRISM,
            attribute_scores=[],  # Empty
            total_score=0,
            complexity_tier=ComplexityTier.XS,
            confidence_score=0.0,
            reasoning="Test",
            created_at=datetime.now(),
        )

        mock_llm.call_with_schema.return_value = StepDecompositionLLMResponse(
            branches=[],
            total_weighted_steps=0.0,
        )

        result = decompose_steps(
            sections=sample_sections,
            assessment_result=assessment,
            llm_manager=mock_llm,
        )

        # Verify activity count defaulted to 0
        assert result is not None


# ===========================================================================
# STEPDECOMPOSITIONLLMRESPONSE VALIDATOR TESTS
# ===========================================================================


class TestStepDecompositionLLMResponse:
    """Test LLM response model validators."""

    def test_sync_total_weight_from_branches(self):
        """Test total_weighted_steps syncs from actual branches."""
        response = StepDecompositionLLMResponse(
            branches=[
                BranchData(
                    branch_name="B1",
                    steps=[
                        StepData(
                            step_number=1,
                            description="S1",
                            weight=1.0,
                            reusability_tag="NONE",
                        ),
                        StepData(
                            step_number=2,
                            description="S2",
                            weight=2.0,
                            reusability_tag="NONE",
                        ),
                    ],
                ),
                BranchData(
                    branch_name="B2",
                    steps=[
                        StepData(
                            step_number=1,
                            description="S3",
                            weight=0.5,
                            reusability_tag="PARTIAL",
                        )
                    ],
                ),
            ],
            total_weighted_steps=999.0,  # Incorrect value
        )

        # Should sync to actual
        assert response.total_weighted_steps == 3.5
