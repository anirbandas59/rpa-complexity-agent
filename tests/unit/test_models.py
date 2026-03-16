"""
Tests for core data models.

Comprehensive tests covering all Pydantic models, validators,
and computed fields.
"""

from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from core.constants import AssessmentPhase, ComplexityTier, ReusabilityTag, RPATool, StepWeight
from core.models.assessment import (
    AssessmentInput,
    AssessmentResult,
    AttributeScore,
)
from core.models.document import ExtractedSection, ParsedDocument
from core.models.process import (
    BusinessRule,
    DigitalLayout,
    ProcessStep,
    TargetInterface,
)
from core.models.timeline import DeliveryFeature, DeliveryTimeline


class TestParsedDocument:
    """Tests for ParsedDocument model."""

    def test_parsed_document_instantiates(self):
        """Verify ParsedDocument can be instantiated."""
        doc = ParsedDocument(
            source_path="/path/to/doc.pdf",
            file_type="pdf",
            full_text="This is a test document with many words " * 20,
            page_count=5,
        )
        assert doc.source_path == "/path/to/doc.pdf"
        assert doc.file_type == "pdf"
        assert doc.page_count == 5

    def test_word_count_basic(self):
        """Verify word_count() returns correct count."""
        doc = ParsedDocument(
            source_path="/path/to/doc.pdf",
            file_type="pdf",
            full_text="one two three four five",
            page_count=1,
        )
        assert doc.word_count() == 5

    def test_word_count_complex(self):
        """Verify word_count() with complex spacing."""
        doc = ParsedDocument(
            source_path="/path/to/doc.pdf",
            file_type="pdf",
            full_text="one  two   three",  # Multiple spaces
            page_count=1,
        )
        # split() handles multiple spaces correctly
        assert doc.word_count() == 3

    def test_is_valid_false_insufficient_words(self):
        """Verify is_valid() returns False when < 100 words."""
        doc = ParsedDocument(
            source_path="/path/to/doc.pdf",
            file_type="pdf",
            full_text="one two three four five",
            page_count=5,
        )
        assert not doc.is_valid()

    def test_is_valid_false_zero_pages(self):
        """Verify is_valid() returns False when page_count = 0."""
        doc = ParsedDocument(
            source_path="/path/to/doc.pdf",
            file_type="pdf",
            full_text="word " * 50,  # More than 100 words
            page_count=0,
        )
        assert not doc.is_valid()

    def test_is_valid_true(self):
        """Verify is_valid() returns True when valid."""
        doc = ParsedDocument(
            source_path="/path/to/doc.pdf",
            file_type="pdf",
            full_text="word " * 101,  # 101 words > 100 when split
            page_count=5,
        )
        assert doc.is_valid()

    def test_is_valid_boundary_exactly_100_words(self):
        """Verify is_valid() with exactly 100 words is invalid (> 100)."""
        doc = ParsedDocument(
            source_path="/path/to/doc.pdf",
            file_type="pdf",
            full_text=" ".join(["word"] * 100),
            page_count=1,
        )
        assert not doc.is_valid()

    def test_is_valid_boundary_101_words(self):
        """Verify is_valid() with 101 words is valid."""
        doc = ParsedDocument(
            source_path="/path/to/doc.pdf",
            file_type="pdf",
            full_text=" ".join(["word"] * 101),
            page_count=1,
        )
        assert doc.is_valid()


class TestExtractedSection:
    """Tests for ExtractedSection model."""

    def test_extracted_section_instantiates(self):
        """Verify ExtractedSection can be instantiated."""
        section = ExtractedSection(
            title="Process Overview",
            content="This is the content",
            confidence_score=0.95,
            section_type="process_overview",
        )
        assert section.title == "Process Overview"
        assert section.confidence_score == 0.95

    def test_confidence_score_rejects_too_high(self):
        """Verify confidence_score validator rejects > 1.0."""
        with pytest.raises(ValidationError) as exc_info:
            ExtractedSection(
                title="Test",
                content="Content",
                confidence_score=1.5,
                section_type="process_overview",
            )
        assert "confidence_score must be between 0.0 and 1.0" in str(exc_info.value)

    def test_confidence_score_rejects_negative(self):
        """Verify confidence_score validator rejects < 0.0."""
        with pytest.raises(ValidationError) as exc_info:
            ExtractedSection(
                title="Test",
                content="Content",
                confidence_score=-0.1,
                section_type="process_overview",
            )
        assert "confidence_score must be between 0.0 and 1.0" in str(exc_info.value)

    def test_confidence_score_accepts_zero(self):
        """Verify confidence_score accepts 0.0 (boundary)."""
        section = ExtractedSection(
            title="Test",
            content="Content",
            confidence_score=0.0,
            section_type="process_overview",
        )
        assert section.confidence_score == 0.0

    def test_confidence_score_accepts_one(self):
        """Verify confidence_score accepts 1.0 (boundary)."""
        section = ExtractedSection(
            title="Test",
            content="Content",
            confidence_score=1.0,
            section_type="process_overview",
        )
        assert section.confidence_score == 1.0


class TestProcessStep:
    """Tests for ProcessStep model."""

    def test_process_step_instantiates(self):
        """Verify ProcessStep can be instantiated."""
        step = ProcessStep(
            step_number=1,
            description="First step",
            weight=StepWeight.ONE,
            reusability_tag=ReusabilityTag.NONE,
            branch_name="main",
            reusability_comment="New automation",
        )
        assert step.step_number == 1

    def test_step_number_rejects_zero(self):
        """Verify step_number validator rejects 0."""
        with pytest.raises(ValidationError) as exc_info:
            ProcessStep(
                step_number=0,
                description="Test",
                weight=StepWeight.ONE,
                reusability_tag=ReusabilityTag.NONE,
                branch_name="main",
                reusability_comment="Test",
            )
        assert "step_number must be >= 1" in str(exc_info.value)

    def test_step_number_rejects_negative(self):
        """Verify step_number validator rejects negative values."""
        with pytest.raises(ValidationError):
            ProcessStep(
                step_number=-1,
                description="Test",
                weight=StepWeight.ONE,
                reusability_tag=ReusabilityTag.NONE,
                branch_name="main",
                reusability_comment="Test",
            )

    def test_step_number_accepts_one(self):
        """Verify step_number accepts 1 (boundary)."""
        step = ProcessStep(
            step_number=1,
            description="Test",
            weight=StepWeight.ONE,
            reusability_tag=ReusabilityTag.NONE,
            branch_name="main",
            reusability_comment="Test",
        )
        assert step.step_number == 1


class TestBusinessRule:
    """Tests for BusinessRule model."""

    def test_business_rule_flow_creating_with_low_count(self):
        """Verify flow-creating rules reject activity count <= 2."""
        with pytest.raises(ValidationError) as exc_info:
            BusinessRule(
                description="Check balance",
                creates_new_flow=True,
                branch_activity_count=2,
                branch_name="insufficient_funds",
            )
        assert "Flow-creating rules must have more than 2" in str(exc_info.value)

    def test_business_rule_flow_creating_with_high_count(self):
        """Verify flow-creating rules accept activity count > 2."""
        rule = BusinessRule(
            description="Check balance",
            creates_new_flow=True,
            branch_activity_count=5,
            branch_name="insufficient_funds",
        )
        assert rule.creates_new_flow is True
        assert rule.branch_activity_count == 5

    def test_business_rule_non_flow_with_low_count(self):
        """Verify non-flow rules accept any activity count."""
        rule = BusinessRule(
            description="Log action",
            creates_new_flow=False,
            branch_activity_count=1,
            branch_name="main",
        )
        assert rule.creates_new_flow is False


class TestDigitalLayout:
    """Tests for DigitalLayout model."""

    def test_digital_layout_both_input_and_output(self):
        """Verify layout can be both input and output."""
        layout = DigitalLayout(
            name="Master Data",
            file_extension="xlsx",
            is_input=True,
            is_output=True,
            template_type="input_template",
        )
        assert layout.is_input is True
        assert layout.is_output is True

    def test_digital_layout_input_only(self):
        """Verify layout can be input-only."""
        layout = DigitalLayout(
            name="Source Data",
            file_extension="csv",
            is_input=True,
            is_output=False,
            template_type="input_template",
        )
        assert layout.is_input is True
        assert layout.is_output is False

    def test_digital_layout_output_only(self):
        """Verify layout can be output-only."""
        layout = DigitalLayout(
            name="Report",
            file_extension="pdf",
            is_input=False,
            is_output=True,
            template_type="output_report",
        )
        assert layout.is_input is False
        assert layout.is_output is True

    def test_digital_layout_neither_input_nor_output(self):
        """Verify layout rejects both False."""
        with pytest.raises(ValidationError) as exc_info:
            DigitalLayout(
                name="Unused",
                file_extension="txt",
                is_input=False,
                is_output=False,
                template_type="schema_file",
            )
        assert "Layout must be either input, output, or both" in str(exc_info.value)


class TestAttributeScore:
    """Tests for AttributeScore model."""

    def test_attribute_score_instantiates(self):
        """Verify AttributeScore can be instantiated."""
        score = AttributeScore(
            attribute_id=1,
            attribute_name="Activities",
            raw_value=45,
            selected_tier=ComplexityTier.XL,
            weight=8,
            tier_rationale="45 activities fall in XL range",
        )
        assert score.attribute_id == 1
        assert score.weight == 8

    def test_attribute_id_rejects_zero(self):
        """Verify attribute_id validator rejects 0."""
        with pytest.raises(ValidationError) as exc_info:
            AttributeScore(
                attribute_id=0,
                attribute_name="Invalid",
                raw_value=1,
                selected_tier=ComplexityTier.XS,
                weight=0,
                tier_rationale="Test",
            )
        assert "attribute_id must be between 1 and 5" in str(exc_info.value)

    def test_attribute_id_rejects_six(self):
        """Verify attribute_id validator rejects 6."""
        with pytest.raises(ValidationError) as exc_info:
            AttributeScore(
                attribute_id=6,
                attribute_name="Invalid",
                raw_value=1,
                selected_tier=ComplexityTier.XS,
                weight=0,
                tier_rationale="Test",
            )
        assert "attribute_id must be between 1 and 5" in str(exc_info.value)

    def test_attribute_id_accepts_one_to_five(self):
        """Verify attribute_id accepts 1-5."""
        for attr_id in range(1, 6):
            score = AttributeScore(
                attribute_id=attr_id,
                attribute_name=f"Attr {attr_id}",
                raw_value=1,
                selected_tier=ComplexityTier.S,
                weight=2,
                tier_rationale="Test",
            )
            assert score.attribute_id == attr_id

    def test_weight_rejects_negative(self):
        """Verify weight validator rejects negative values."""
        with pytest.raises(ValidationError) as exc_info:
            AttributeScore(
                attribute_id=1,
                attribute_name="Activities",
                raw_value=1,
                selected_tier=ComplexityTier.XS,
                weight=-1,
                tier_rationale="Test",
            )
        assert "weight cannot be negative" in str(exc_info.value)

    def test_weight_accepts_zero(self):
        """Verify weight accepts 0."""
        score = AttributeScore(
            attribute_id=1,
            attribute_name="Activities",
            raw_value=1,
            selected_tier=ComplexityTier.XS,
            weight=0,
            tier_rationale="Test",
        )
        assert score.weight == 0


class TestAssessmentInput:
    """Tests for AssessmentInput model."""

    def test_assessment_input_instantiates(self):
        """Verify AssessmentInput can be instantiated."""
        input_data = AssessmentInput(
            file_path="/path/to/pdd.pdf",
            rpa_tool=RPATool.BLUE_PRISM,
            project_name="Loan Processing",
            assessor_name="John Doe",
            start_date=date(2024, 1, 15),
        )
        assert input_data.file_path == "/path/to/pdd.pdf"

    def test_file_path_rejects_empty_string(self):
        """Verify file_path validator rejects empty string."""
        with pytest.raises(ValidationError) as exc_info:
            AssessmentInput(
                file_path="",
                rpa_tool=RPATool.UIPATH,
                project_name="Test",
                assessor_name="John",
                start_date=date(2024, 1, 1),
            )
        assert "file_path cannot be empty" in str(exc_info.value)

    def test_file_path_rejects_whitespace_only(self):
        """Verify file_path validator rejects whitespace-only string."""
        with pytest.raises(ValidationError) as exc_info:
            AssessmentInput(
                file_path="   ",
                rpa_tool=RPATool.POWER_AUTOMATE,
                project_name="Test",
                assessor_name="John",
                start_date=date(2024, 1, 1),
            )
        assert "file_path cannot be empty" in str(exc_info.value)


class TestAssessmentResult:
    """Tests for AssessmentResult model."""

    def test_assessment_result_instantiates(self):
        """Verify AssessmentResult can be instantiated."""
        result = AssessmentResult(
            session_id="uuid-123",
            project_name="Loan Processing",
            rpa_tool=RPATool.BLUE_PRISM,
            total_score=15,
            complexity_tier=ComplexityTier.M,
            confidence_score=0.85,
            reasoning="Medium complexity automation",
            created_at=datetime.now(timezone.utc),
        )
        assert result.project_name == "Loan Processing"

    def test_total_score_rejects_negative(self):
        """Verify total_score validator rejects negative values."""
        with pytest.raises(ValidationError) as exc_info:
            AssessmentResult(
                session_id="uuid-123",
                project_name="Test",
                rpa_tool=RPATool.UIPATH,
                total_score=-1,
                complexity_tier=ComplexityTier.XS,
                confidence_score=0.9,
                reasoning="Test",
                created_at=datetime.now(timezone.utc),
            )
        assert "total_score must be between 0 and 28" in str(exc_info.value)

    def test_total_score_rejects_too_high(self):
        """Verify total_score validator rejects > 28."""
        with pytest.raises(ValidationError) as exc_info:
            AssessmentResult(
                session_id="uuid-123",
                project_name="Test",
                rpa_tool=RPATool.POWER_AUTOMATE,
                total_score=29,
                complexity_tier=ComplexityTier.XL,
                confidence_score=0.9,
                reasoning="Test",
                created_at=datetime.now(timezone.utc),
            )
        assert "total_score must be between 0 and 28" in str(exc_info.value)

    def test_confidence_score_rejects_out_of_range(self):
        """Verify confidence_score validator rejects out of range."""
        with pytest.raises(ValidationError):
            AssessmentResult(
                session_id="uuid-123",
                project_name="Test",
                rpa_tool=RPATool.AA360,
                total_score=15,
                complexity_tier=ComplexityTier.M,
                confidence_score=1.5,
                reasoning="Test",
                created_at=datetime.now(timezone.utc),
            )

    def test_score_summary_with_scores(self):
        """Verify score_summary returns formatted table."""
        scores = [
            AttributeScore(
                attribute_id=1,
                attribute_name="Activities",
                raw_value=45,
                selected_tier=ComplexityTier.XL,
                weight=8,
                tier_rationale="Test",
            ),
            AttributeScore(
                attribute_id=2,
                attribute_name="Business Rules",
                raw_value=5,
                selected_tier=ComplexityTier.XL,
                weight=8,
                tier_rationale="Test",
            ),
        ]
        result = AssessmentResult(
            session_id="uuid-123",
            project_name="Test",
            rpa_tool=RPATool.BLUE_PRISM,
            attribute_scores=scores,
            total_score=16,
            complexity_tier=ComplexityTier.L,
            confidence_score=0.9,
            reasoning="Test",
            created_at=datetime.now(timezone.utc),
        )
        summary = result.score_summary
        assert "16" in summary
        assert "L" in summary
        assert "Activities" in summary

    def test_score_summary_empty_scores(self):
        """Verify score_summary returns message for empty scores."""
        result = AssessmentResult(
            session_id="uuid-123",
            project_name="Test",
            rpa_tool=RPATool.UIPATH,
            attribute_scores=[],
            total_score=0,
            complexity_tier=ComplexityTier.XS,
            confidence_score=0.5,
            reasoning="Test",
            created_at=datetime.now(timezone.utc),
        )
        assert result.score_summary == "No scores available."


class TestDeliveryFeature:
    """Tests for DeliveryFeature model."""

    def test_delivery_feature_instantiates(self):
        """Verify DeliveryFeature can be instantiated."""
        feature = DeliveryFeature(
            name="Build login form",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 5),
            hours=24.0,
            developer="John Doe",
        )
        assert feature.name == "Build login form"
        assert feature.hours == 24.0

    def test_sp_computed_property_hours_9(self):
        """Verify sp is computed correctly for 9 hours."""
        feature = DeliveryFeature(
            name="Task",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 2),
            hours=9.0,
            developer="Dev",
        )
        # 0.0666 * 9 = 0.5994 → rounded to 0.60
        assert feature.sp == round(0.0666 * 9, 2)
        assert feature.sp == 0.60

    def test_sp_computed_property_hours_24(self):
        """Verify sp is computed correctly for 24 hours."""
        feature = DeliveryFeature(
            name="Task",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 3),
            hours=24.0,
            developer="Dev",
        )
        # 0.0666 * 24 = 1.5984 → rounded to 1.60
        assert feature.sp == round(0.0666 * 24, 2)
        assert feature.sp == 1.60

    def test_hours_rejects_zero(self):
        """Verify hours validator rejects 0."""
        with pytest.raises(ValidationError) as exc_info:
            DeliveryFeature(
                name="Task",
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 2),
                hours=0,
                developer="Dev",
            )
        assert "hours must be greater than 0" in str(exc_info.value)

    def test_hours_rejects_negative(self):
        """Verify hours validator rejects negative values."""
        with pytest.raises(ValidationError) as exc_info:
            DeliveryFeature(
                name="Task",
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 2),
                hours=-5,
                developer="Dev",
            )
        assert "hours must be greater than 0" in str(exc_info.value)

    def test_end_date_rejects_before_start(self):
        """Verify end_date validator rejects date before start_date."""
        with pytest.raises(ValidationError) as exc_info:
            DeliveryFeature(
                name="Task",
                start_date=date(2024, 1, 10),
                end_date=date(2024, 1, 5),
                hours=10,
                developer="Dev",
            )
        assert "end_date cannot be before start_date" in str(exc_info.value)

    def test_end_date_accepts_equal_to_start(self):
        """Verify end_date accepts same date as start_date."""
        feature = DeliveryFeature(
            name="Task",
            start_date=date(2024, 1, 5),
            end_date=date(2024, 1, 5),
            hours=8,
            developer="Dev",
        )
        assert feature.end_date == feature.start_date

    def test_completion_pct_rejects_below_zero(self):
        """Verify completion_pct rejects < 0.0."""
        with pytest.raises(ValidationError):
            DeliveryFeature(
                name="Task",
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 2),
                hours=10,
                developer="Dev",
                completion_pct=-0.1,
            )

    def test_completion_pct_rejects_above_one(self):
        """Verify completion_pct rejects > 1.0."""
        with pytest.raises(ValidationError):
            DeliveryFeature(
                name="Task",
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 2),
                hours=10,
                developer="Dev",
                completion_pct=1.1,
            )


class TestDeliveryTimeline:
    """Tests for DeliveryTimeline model."""

    def test_delivery_timeline_instantiates(self):
        """Verify DeliveryTimeline can be instantiated."""
        timeline = DeliveryTimeline(
            project_name="Loan Processing",
            squad="Squad A",
            business_analyst="Jane",
            developer="John",
        )
        assert timeline.project_name == "Loan Processing"

    def test_total_hours_empty(self):
        """Verify total_hours returns 0 for empty features."""
        timeline = DeliveryTimeline(
            project_name="Test",
            squad="Squad",
            business_analyst="BA",
            developer="Dev",
            features=[],
        )
        assert timeline.total_hours == 0

    def test_total_hours_with_features(self):
        """Verify total_hours sums correctly."""
        features = [
            DeliveryFeature(
                name="Task 1",
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 2),
                hours=10.0,
                developer="Dev",
            ),
            DeliveryFeature(
                name="Task 2",
                start_date=date(2024, 1, 3),
                end_date=date(2024, 1, 4),
                hours=15.0,
                developer="Dev",
            ),
        ]
        timeline = DeliveryTimeline(
            project_name="Test",
            squad="Squad",
            business_analyst="BA",
            developer="Dev",
            features=features,
        )
        assert timeline.total_hours == 25.0

    def test_total_sp_sums_correctly(self):
        """Verify total_sp sums story points correctly."""
        features = [
            DeliveryFeature(
                name="Task 1",
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 2),
                hours=9.0,
                developer="Dev",
            ),
            DeliveryFeature(
                name="Task 2",
                start_date=date(2024, 1, 3),
                end_date=date(2024, 1, 4),
                hours=24.0,
                developer="Dev",
            ),
        ]
        timeline = DeliveryTimeline(
            project_name="Test",
            squad="Squad",
            business_analyst="BA",
            developer="Dev",
            features=features,
        )
        # total_sp = 0.60 + 1.60 = 2.20
        assert timeline.total_sp == round(0.60 + 1.60, 2)

    def test_start_date_earliest(self):
        """Verify start_date returns earliest date."""
        features = [
            DeliveryFeature(
                name="Task 1",
                start_date=date(2024, 1, 5),
                end_date=date(2024, 1, 6),
                hours=10,
                developer="Dev",
            ),
            DeliveryFeature(
                name="Task 2",
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 2),
                hours=10,
                developer="Dev",
            ),
        ]
        timeline = DeliveryTimeline(
            project_name="Test",
            squad="Squad",
            business_analyst="BA",
            developer="Dev",
            features=features,
        )
        assert timeline.start_date == date(2024, 1, 1)

    def test_end_date_latest(self):
        """Verify end_date returns latest date."""
        features = [
            DeliveryFeature(
                name="Task 1",
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 3),
                hours=10,
                developer="Dev",
            ),
            DeliveryFeature(
                name="Task 2",
                start_date=date(2024, 1, 2),
                end_date=date(2024, 1, 10),
                hours=10,
                developer="Dev",
            ),
        ]
        timeline = DeliveryTimeline(
            project_name="Test",
            squad="Squad",
            business_analyst="BA",
            developer="Dev",
            features=features,
        )
        assert timeline.end_date == date(2024, 1, 10)

    def test_start_date_none_empty_features(self):
        """Verify start_date returns None for empty features."""
        timeline = DeliveryTimeline(
            project_name="Test",
            squad="Squad",
            business_analyst="BA",
            developer="Dev",
            features=[],
        )
        assert timeline.start_date is None

    def test_end_date_none_empty_features(self):
        """Verify end_date returns None for empty features."""
        timeline = DeliveryTimeline(
            project_name="Test",
            squad="Squad",
            business_analyst="BA",
            developer="Dev",
            features=[],
        )
        assert timeline.end_date is None

    def test_completed_count(self):
        """Verify completed_count counts COMPLETED features."""
        features = [
            DeliveryFeature(
                name="Task 1",
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 2),
                hours=10,
                developer="Dev",
                development_status="COMPLETED",
            ),
            DeliveryFeature(
                name="Task 2",
                start_date=date(2024, 1, 3),
                end_date=date(2024, 1, 4),
                hours=10,
                developer="Dev",
                development_status="IN PROGRESS",
            ),
            DeliveryFeature(
                name="Task 3",
                start_date=date(2024, 1, 5),
                end_date=date(2024, 1, 6),
                hours=10,
                developer="Dev",
                development_status="COMPLETED",
            ),
        ]
        timeline = DeliveryTimeline(
            project_name="Test",
            squad="Squad",
            business_analyst="BA",
            developer="Dev",
            features=features,
        )
        assert timeline.completed_count() == 2

    def test_in_progress_count(self):
        """Verify in_progress_count counts IN PROGRESS features."""
        features = [
            DeliveryFeature(
                name="Task 1",
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 2),
                hours=10,
                developer="Dev",
                development_status="COMPLETED",
            ),
            DeliveryFeature(
                name="Task 2",
                start_date=date(2024, 1, 3),
                end_date=date(2024, 1, 4),
                hours=10,
                developer="Dev",
                development_status="IN PROGRESS",
            ),
            DeliveryFeature(
                name="Task 3",
                start_date=date(2024, 1, 5),
                end_date=date(2024, 1, 6),
                hours=10,
                developer="Dev",
                development_status="IN PROGRESS",
            ),
        ]
        timeline = DeliveryTimeline(
            project_name="Test",
            squad="Squad",
            business_analyst="BA",
            developer="Dev",
            features=features,
        )
        assert timeline.in_progress_count() == 2


class TestGroundTruthAssessmentResult:
    """Ground truth test from CLAUDE.md domain knowledge."""

    def test_ground_truth_assessment_result(self):
        """Test the exact ground truth scenario from the project.

        This matches the assessment scenario documented in CLAUDE.md:
        - Activities: XL (41-60) → weight 8
        - Business Rules: XL (5-6) → weight 8
        - Layouts: L (4-6) → weight 3
        - Interfaces: S (1-2) → weight 1
        - Technology: S (0) → weight 1
        - Total score: 21 → Classification: L
        """
        scores = [
            AttributeScore(
                attribute_id=1,
                attribute_name="Activities",
                raw_value=45,
                selected_tier=ComplexityTier.XL,
                weight=8,
                tier_rationale="45 activities in XL range (41-60)",
            ),
            AttributeScore(
                attribute_id=2,
                attribute_name="Business Rules",
                raw_value=5,
                selected_tier=ComplexityTier.XL,
                weight=8,
                tier_rationale="5 rules in XL range (5-6)",
            ),
            AttributeScore(
                attribute_id=3,
                attribute_name="Layouts",
                raw_value=5,
                selected_tier=ComplexityTier.L,
                weight=3,
                tier_rationale="5 screens in L range (4-6)",
            ),
            AttributeScore(
                attribute_id=4,
                attribute_name="Interfaces",
                raw_value=1,
                selected_tier=ComplexityTier.S,
                weight=1,
                tier_rationale="1 interface in S range (1-2)",
            ),
            AttributeScore(
                attribute_id=5,
                attribute_name="Add. Technology",
                raw_value=0,
                selected_tier=ComplexityTier.S,
                weight=1,
                tier_rationale="0 integrations in S range (1)",
            ),
        ]

        result = AssessmentResult(
            session_id="ground-truth-test-001",
            project_name="Ground Truth Test Automation",
            rpa_tool=RPATool.BLUE_PRISM,
            attribute_scores=scores,
            total_score=21,
            complexity_tier=ComplexityTier.L,
            confidence_score=0.95,
            reasoning="Automation with high activity count and rules, moderate UI complexity",
            requires_tech_lead_review=False,
            created_at=datetime.now(timezone.utc),
        )

        # All assertions from acceptance criteria
        assert result.total_score == 21
        assert result.complexity_tier == ComplexityTier.L
        assert result.requires_tech_lead_review is False
        assert "21" in result.score_summary
        assert "L" in result.score_summary
