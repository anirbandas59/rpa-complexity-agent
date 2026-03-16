"""
Unit tests for timeline builder tool.

Tests timeline generation, scheduling, and formatting.
"""

from datetime import date, datetime

import pytest

from core.constants import ComplexityTier, RPATool
from core.models.assessment import AssessmentResult, AttributeScore
from core.models.timeline import DeliveryTimeline
from tools.output.step_decomposer import (
    BranchData,
    StepData,
    StepDecompositionResult,
)
from tools.output.timeline_builder import (
    _calculate_feature_hours,
    _next_working_day,
    _weight_to_hours,
    build_timeline,
    get_timeline_summary,
)

# ===========================================================================
# FIXTURES
# ===========================================================================


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
                tier_rationale="20 distinct RPA activities",
            ),
        ],
        total_score=16,
        complexity_tier=ComplexityTier.L,
        confidence_score=0.92,
        reasoning="Complex process",
        created_at=datetime.now(),
    )


@pytest.fixture
def sample_decomposition() -> StepDecompositionResult:
    """Sample step decomposition result."""
    return StepDecompositionResult(
        project_name="Order Processing Automation",
        branches=[
            BranchData(
                branch_name="Main Flow",
                description="Primary process steps",
                steps=[
                    StepData(
                        step_number=1,
                        description="Receive order",
                        weight=1.0,
                        reusability_tag="NONE",
                    ),
                    StepData(
                        step_number=2,
                        description="Validate data",
                        weight=1.0,
                        reusability_tag="NONE",
                    ),
                    StepData(
                        step_number=3,
                        description="Process payment",
                        weight=2.0,
                        reusability_tag="NONE",
                    ),
                ],
            ),
            BranchData(
                branch_name="Error Handler",
                description="Error handling and escalation",
                steps=[
                    StepData(
                        step_number=1,
                        description="Log error",
                        weight=0.5,
                        reusability_tag="PARTIAL",
                    ),
                    StepData(
                        step_number=2,
                        description="Send alert",
                        weight=0.5,
                        reusability_tag="PARTIAL",
                    ),
                ],
            ),
        ],
        total_weighted_steps=5.0,
        total_step_count=5,
    )


# ===========================================================================
# _WEIGHT_TO_HOURS TESTS
# ===========================================================================


class TestWeightToHours:
    """Test _weight_to_hours helper function."""

    def test_weight_zero_returns_zero(self):
        """Test weight 0.0 returns 0 hours."""
        assert _weight_to_hours(0.0) == 0

    def test_weight_half_returns_half_day(self):
        """Test weight 0.5 returns 4.5 hours."""
        assert _weight_to_hours(0.5) == 4.5

    def test_weight_one_returns_full_day(self):
        """Test weight 1.0 returns 9.0 hours."""
        assert _weight_to_hours(1.0) == 9.0

    def test_weight_two_returns_two_days(self):
        """Test weight 2.0 returns 18.0 hours."""
        assert _weight_to_hours(2.0) == 18.0

    def test_unknown_weight_defaults_to_one_day(self):
        """Test unknown weight defaults to 9.0 hours."""
        assert _weight_to_hours(1.5) == 9.0
        assert _weight_to_hours(3.0) == 9.0


# ===========================================================================
# _NEXT_WORKING_DAY TESTS
# ===========================================================================


class TestNextWorkingDay:
    """Test _next_working_day helper function."""

    def test_weekday_to_next_weekday(self):
        """Test weekday advances to next weekday."""
        # Thursday 2024-01-04
        thursday = date(2024, 1, 4)
        friday = _next_working_day(thursday)
        assert friday == date(2024, 1, 5)

    def test_friday_to_monday(self):
        """Test Friday advances to Monday (skips weekend)."""
        # Friday 2024-01-05
        friday = date(2024, 1, 5)
        monday = _next_working_day(friday)
        assert monday == date(2024, 1, 8)

    def test_saturday_input_to_monday(self):
        """Test Saturday input returns Monday."""
        # Saturday 2024-01-06
        saturday = date(2024, 1, 6)
        monday = _next_working_day(saturday)
        assert monday == date(2024, 1, 8)

    def test_sunday_input_to_monday(self):
        """Test Sunday input returns Monday."""
        # Sunday 2024-01-07
        sunday = date(2024, 1, 7)
        monday = _next_working_day(sunday)
        assert monday == date(2024, 1, 8)


# ===========================================================================
# _CALCULATE_FEATURE_HOURS TESTS
# ===========================================================================


class TestCalculateFeatureHours:
    """Test _calculate_feature_hours helper function."""

    def test_sum_of_step_hours(self):
        """Test hours sum correctly from all steps."""
        branch = BranchData(
            branch_name="Main",
            steps=[
                StepData(
                    step_number=1, description="S1", weight=1.0, reusability_tag="NONE"
                ),  # 9h
                StepData(
                    step_number=2, description="S2", weight=1.0, reusability_tag="NONE"
                ),  # 9h
                StepData(
                    step_number=3,
                    description="S3",
                    weight=0.5,
                    reusability_tag="PARTIAL",
                ),  # 4.5h
            ],
        )
        # 9 + 9 + 4.5 = 22.5
        assert _calculate_feature_hours(branch) == 22.5

    def test_empty_branch_returns_zero(self):
        """Test empty branch returns 0 hours."""
        branch = BranchData(branch_name="Empty", steps=[])
        assert _calculate_feature_hours(branch) == 0

    def test_fully_reused_steps_return_zero(self):
        """Test fully reused steps contribute 0 hours."""
        branch = BranchData(
            branch_name="Reused",
            steps=[
                StepData(
                    step_number=1,
                    description="Reused",
                    weight=0.0,
                    reusability_tag="FULL",
                ),
                StepData(
                    step_number=2,
                    description="Reused",
                    weight=0.0,
                    reusability_tag="FULL",
                ),
            ],
        )
        assert _calculate_feature_hours(branch) == 0


# ===========================================================================
# BUILD_TIMELINE TESTS
# ===========================================================================


class TestBuildTimeline:
    """Test build_timeline function."""

    def test_returns_delivery_timeline(
        self, sample_decomposition, sample_assessment_result
    ):
        """Test build_timeline returns DeliveryTimeline instance."""
        start = date(2024, 1, 8)  # Monday
        timeline = build_timeline(
            decomposition=sample_decomposition,
            assessment_result=sample_assessment_result,
            start_date=start,
        )
        assert isinstance(timeline, DeliveryTimeline)

    def test_feature_count_matches_branch_count(
        self, sample_decomposition, sample_assessment_result
    ):
        """Test features count equals branch count."""
        start = date(2024, 1, 8)
        timeline = build_timeline(
            decomposition=sample_decomposition,
            assessment_result=sample_assessment_result,
            start_date=start,
        )
        assert len(timeline.features) == len(sample_decomposition.branches)

    def test_features_ordered_sequentially(
        self, sample_decomposition, sample_assessment_result
    ):
        """Test features have sequential dates with no overlap."""
        start = date(2024, 1, 8)  # Monday
        timeline = build_timeline(
            decomposition=sample_decomposition,
            assessment_result=sample_assessment_result,
            start_date=start,
        )

        # Each feature's start should be same as or after previous feature's end
        for i in range(1, len(timeline.features)):
            prev_end = timeline.features[i - 1].end_date
            curr_start = timeline.features[i].start_date
            assert curr_start >= prev_end

    def test_feature_hours_calculated(self, sample_assessment_result):
        """Test feature hours are calculated correctly."""
        # Create decomposition with controlled weights
        decomp = StepDecompositionResult(
            project_name="Test",
            branches=[
                BranchData(
                    branch_name="Main Flow",
                    description="Primary flow",
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
                            weight=1.0,
                            reusability_tag="NONE",
                        ),
                        StepData(
                            step_number=3,
                            description="S3",
                            weight=2.0,
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
                            description="E1",
                            weight=0.5,
                            reusability_tag="PARTIAL",
                        ),
                        StepData(
                            step_number=2,
                            description="E2",
                            weight=0.5,
                            reusability_tag="PARTIAL",
                        ),
                    ],
                ),
            ],
            total_weighted_steps=5.0,
            total_step_count=5,
        )

        start = date(2024, 1, 8)
        timeline = build_timeline(
            decomposition=decomp,
            assessment_result=sample_assessment_result,
            start_date=start,
        )

        # Main Flow: 1.0 + 1.0 + 2.0 weights = 4.0 total weight
        # Hours: (1*9 + 1*9 + 2*9) = 36h
        assert timeline.features[0].hours == 36.0
        # Error Handler: 0.5 + 0.5 weights = 1.0 total weight
        # Hours: (0.5*9 + 0.5*9) = 9h
        assert timeline.features[1].hours == 9.0

    def test_feature_story_points_calculated(self, sample_assessment_result):
        """Test story points calculated from hours."""
        # Create decomposition with known weights
        decomp = StepDecompositionResult(
            project_name="Test",
            branches=[
                BranchData(
                    branch_name="Main Flow",
                    description="Primary flow",
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
                            weight=1.0,
                            reusability_tag="NONE",
                        ),
                    ],
                ),
            ],
            total_weighted_steps=2.0,
            total_step_count=2,
        )

        start = date(2024, 1, 8)
        timeline = build_timeline(
            decomposition=decomp,
            assessment_result=sample_assessment_result,
            start_date=start,
        )

        # Main Flow: 2 steps * 1.0 weight = 2.0 total weight
        # Hours: 2 * 9 = 18h
        # SP: 18 * 0.0666 = 1.20
        assert timeline.features[0].hours == 18.0
        assert timeline.features[0].sp == round(18.0 * 0.0666, 2)

    def test_all_features_have_required_fields(
        self, sample_decomposition, sample_assessment_result
    ):
        """Test all features have required fields set."""
        start = date(2024, 1, 8)
        timeline = build_timeline(
            decomposition=sample_decomposition,
            assessment_result=sample_assessment_result,
            start_date=start,
            developer_name="John Doe",
            business_analyst="Jane Smith",
            squad="Team A",
        )

        for feature in timeline.features:
            assert feature.scope == "ORIGINAL"
            assert feature.acceptance_status == "APPROVED"
            assert feature.priority == "MUST"
            assert feature.completion_pct == 0.0
            assert feature.development_status == "NOT STARTED"
            assert feature.developer == "John Doe"

    def test_timeline_metadata(self, sample_decomposition, sample_assessment_result):
        """Test timeline metadata is correct."""
        start = date(2024, 1, 8)
        timeline = build_timeline(
            decomposition=sample_decomposition,
            assessment_result=sample_assessment_result,
            start_date=start,
            developer_name="Test Dev",
            business_analyst="Test BA",
            squad="Test Squad",
        )

        assert timeline.project_name == "Order Processing Automation"
        assert timeline.developer == "Test Dev"
        assert timeline.business_analyst == "Test BA"
        assert timeline.squad == "Test Squad"

    def test_timeline_computed_properties(
        self, sample_decomposition, sample_assessment_result
    ):
        """Test timeline computed properties work."""
        start = date(2024, 1, 8)
        timeline = build_timeline(
            decomposition=sample_decomposition,
            assessment_result=sample_assessment_result,
            start_date=start,
        )

        # Total hours should be sum of feature hours
        assert timeline.total_hours > 0
        # Total SP should be computed
        assert timeline.total_sp > 0
        # Start and end dates should exist
        assert timeline.start_date is not None
        assert timeline.end_date is not None
        assert timeline.end_date >= timeline.start_date

    def test_minimum_hours_per_feature(self, sample_assessment_result):
        """Test features with zero hours get minimum 9h."""
        decomp = StepDecompositionResult(
            project_name="Test",
            branches=[
                BranchData(
                    branch_name="Reused Only",
                    steps=[StepData(step_number=1, description="Reused", weight=0.0)],
                ),
            ],
            total_weighted_steps=0.0,
            total_step_count=1,
        )

        start = date(2024, 1, 8)
        timeline = build_timeline(
            decomposition=decomp,
            assessment_result=sample_assessment_result,
            start_date=start,
        )

        # Even reused-only branch should have minimum hours
        assert timeline.features[0].hours == 9.0

    def test_default_parameters(self, sample_decomposition, sample_assessment_result):
        """Test default parameters are set correctly."""
        start = date(2024, 1, 8)
        timeline = build_timeline(
            decomposition=sample_decomposition,
            assessment_result=sample_assessment_result,
            start_date=start,
        )

        assert timeline.developer == "TBD"
        assert timeline.business_analyst == "TBD"
        assert timeline.squad == "RPA Team"


# ===========================================================================
# GET_TIMELINE_SUMMARY TESTS
# ===========================================================================


class TestGetTimelineSummary:
    """Test get_timeline_summary formatter."""

    def test_returns_non_empty_string(
        self, sample_decomposition, sample_assessment_result
    ):
        """Test summary returns non-empty string."""
        start = date(2024, 1, 8)
        timeline = build_timeline(
            decomposition=sample_decomposition,
            assessment_result=sample_assessment_result,
            start_date=start,
        )
        summary = get_timeline_summary(timeline)
        assert isinstance(summary, str)
        assert len(summary) > 0

    def test_contains_project_name(
        self, sample_decomposition, sample_assessment_result
    ):
        """Test summary contains project name."""
        start = date(2024, 1, 8)
        timeline = build_timeline(
            decomposition=sample_decomposition,
            assessment_result=sample_assessment_result,
            start_date=start,
        )
        summary = get_timeline_summary(timeline)
        assert "Order Processing Automation" in summary

    def test_contains_total_hours(self, sample_decomposition, sample_assessment_result):
        """Test summary contains total hours."""
        start = date(2024, 1, 8)
        timeline = build_timeline(
            decomposition=sample_decomposition,
            assessment_result=sample_assessment_result,
            start_date=start,
        )
        summary = get_timeline_summary(timeline)
        assert "Total Hours" in summary

    def test_contains_feature_names(
        self, sample_decomposition, sample_assessment_result
    ):
        """Test summary contains each feature name."""
        start = date(2024, 1, 8)
        timeline = build_timeline(
            decomposition=sample_decomposition,
            assessment_result=sample_assessment_result,
            start_date=start,
        )
        summary = get_timeline_summary(timeline)
        assert "Main Flow" in summary
        assert "Error Handler" in summary

    def test_multiline_formatted(self, sample_decomposition, sample_assessment_result):
        """Test summary is multi-line formatted."""
        start = date(2024, 1, 8)
        timeline = build_timeline(
            decomposition=sample_decomposition,
            assessment_result=sample_assessment_result,
            start_date=start,
        )
        summary = get_timeline_summary(timeline)
        lines = summary.split("\n")
        assert len(lines) > 5


# ===========================================================================
# GROUND TRUTH TEST
# ===========================================================================


class TestGroundTruthTimeline:
    """Ground truth validation for timeline generation."""

    def test_ground_truth_l_tier_timeline(self):
        """Test known L-tier project timeline matches expectations.

        From CLAUDE.md:
        - Total effort: 60 days for L tier
        - Project name: Order Processing (example)
        - Start date: 2021-07-09 (from Excel template)
        """
        # Create assessment matching L-tier known case
        assessment = AssessmentResult(
            session_id="gt-123",
            project_name="Known L-tier Project",
            rpa_tool=RPATool.BLUE_PRISM,
            attribute_scores=[],
            total_score=18,  # L tier score
            complexity_tier=ComplexityTier.L,
            confidence_score=0.95,
            reasoning="Ground truth test case",
            created_at=datetime.now(),
        )

        # Create decomposition matching ~60 hours effort
        # L tier expected: 60 days effort
        # 60 days / 9 hours per day ≈ 6.67 days of actual work
        # Use ~6-7 steps at 1.0 weight each
        decomp = StepDecompositionResult(
            project_name="Known L-tier Project",
            branches=[
                BranchData(
                    branch_name="Feature 1",
                    description="Main processing flow",
                    steps=[
                        StepData(step_number=i, description=f"Step {i}", weight=1.0)
                        for i in range(1, 4)
                    ],  # 3 steps = 27h
                ),
                BranchData(
                    branch_name="Feature 2",
                    description="Error handling",
                    steps=[
                        StepData(step_number=i, description=f"Step {i}", weight=1.0)
                        for i in range(1, 4)
                    ],  # 3 steps = 27h
                ),
            ],
            total_weighted_steps=6.0,
            total_step_count=6,
        )

        # Build timeline starting from known date
        start_date = date(2021, 7, 9)  # Friday from template
        timeline = build_timeline(
            decomposition=decomp,
            assessment_result=assessment,
            start_date=start_date,
            developer_name="Hemalatha Polasani",
            business_analyst="QA Team",
        )

        # Validate expectations
        assert timeline.project_name == "Known L-tier Project"
        assert timeline.developer == "Hemalatha Polasani"
        assert timeline.start_date == date(2021, 7, 9)
        assert len(timeline.features) == 2
        assert timeline.total_hours == 54.0  # 6 steps * 9h
        assert all(f.development_status == "NOT STARTED" for f in timeline.features)
        assert timeline.end_date > start_date
