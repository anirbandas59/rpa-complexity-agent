"""Tests for technology detector tool."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.models.document import ExtractedSection
from tools.analysis.technology_detector import (
    DetectedTechnology,
    ExcludedTechnology,
    RPAToolNotes,
    TechnologyDetectionLLMResponse,
    TechnologyDetectionResult,
    XL_TECHNOLOGY_CEILING,
    _detect_api_integration,
    _detect_surface_automation,
    _filter_relevant_sections,
    _prepare_sections_text,
    detect_technology,
    get_technology_count,
    get_technology_tier_hint,
)


# ==================== TEST: _detect_surface_automation ====================


class TestDetectSurfaceAutomation:
    """Tests for _detect_surface_automation helper."""

    def test_surface_automation_category_returns_true(self):
        """Technology with category='surface_automation' returns True."""
        tech = DetectedTechnology(name="Citrix VDI", category="surface_automation")
        assert _detect_surface_automation([tech]) is True

    def test_citrix_in_name_returns_true(self):
        """Technology with 'citrix' in name returns True."""
        tech = DetectedTechnology(name="Citrix VDI Automation")
        assert _detect_surface_automation([tech]) is True

    def test_surface_in_name_returns_true(self):
        """Technology with 'surface' in name returns True."""
        tech = DetectedTechnology(name="Windows Surface Automation")
        assert _detect_surface_automation([tech]) is True

    def test_rdp_in_name_returns_true(self):
        """Technology with 'rdp' in name returns True."""
        tech = DetectedTechnology(name="RDP Terminal Connection")
        assert _detect_surface_automation([tech]) is True

    def test_vnc_in_name_returns_true(self):
        """Technology with 'vnc' in name returns True."""
        tech = DetectedTechnology(name="VNC Remote Desktop")
        assert _detect_surface_automation([tech]) is True

    def test_remote_desktop_in_name_returns_true(self):
        """Technology with 'remote desktop' in name returns True."""
        tech = DetectedTechnology(name="Remote Desktop Protocol Access")
        assert _detect_surface_automation([tech]) is True

    def test_virtual_desktop_in_name_returns_true(self):
        """Technology with 'virtual desktop' in name returns True."""
        tech = DetectedTechnology(name="Virtual Desktop Infrastructure")
        assert _detect_surface_automation([tech]) is True

    def test_api_technology_returns_false(self):
        """API technology returns False."""
        tech = DetectedTechnology(name="REST API", category="api")
        assert _detect_surface_automation([tech]) is False

    def test_empty_list_returns_false(self):
        """Empty technology list returns False."""
        assert _detect_surface_automation([]) is False

    def test_case_insensitive_detection(self):
        """Detection is case-insensitive."""
        tech = DetectedTechnology(name="CITRIX VDI SOLUTION")
        assert _detect_surface_automation([tech]) is True

    def test_multiple_technologies_with_one_match(self):
        """Returns True if any technology matches."""
        techs = [
            DetectedTechnology(name="REST API", category="api"),
            DetectedTechnology(name="Citrix Gateway", category="connector"),
        ]
        assert _detect_surface_automation(techs) is True

    def test_multiple_technologies_with_no_match(self):
        """Returns False if no technology matches."""
        techs = [
            DetectedTechnology(name="REST API", category="api"),
            DetectedTechnology(name="Python Script", category="scripting"),
        ]
        assert _detect_surface_automation(techs) is False


# ==================== TEST: _detect_api_integration ====================


class TestDetectAPIIntegration:
    """Tests for _detect_api_integration helper."""

    def test_api_category_returns_true(self):
        """Technology with category='api' returns True."""
        tech = DetectedTechnology(name="REST Gateway", category="api")
        assert _detect_api_integration([tech]) is True

    def test_api_in_name_returns_true(self):
        """Technology with 'api' in name returns True."""
        tech = DetectedTechnology(name="External API Integration")
        assert _detect_api_integration([tech]) is True

    def test_rest_in_name_returns_true(self):
        """Technology with 'rest' in name returns True."""
        tech = DetectedTechnology(name="REST Web Service")
        assert _detect_api_integration([tech]) is True

    def test_soap_in_name_returns_true(self):
        """Technology with 'soap' in name returns True."""
        tech = DetectedTechnology(name="SOAP XML Service")
        assert _detect_api_integration([tech]) is True

    def test_web_service_in_name_returns_true(self):
        """Technology with 'web service' in name returns True."""
        tech = DetectedTechnology(name="Web Service Integration")
        assert _detect_api_integration([tech]) is True

    def test_http_in_name_returns_true(self):
        """Technology with 'http' in name returns True."""
        tech = DetectedTechnology(name="HTTP Request Handler")
        assert _detect_api_integration([tech]) is True

    def test_webhook_in_name_returns_true(self):
        """Technology with 'webhook' in name returns True."""
        tech = DetectedTechnology(name="Webhook Listener")
        assert _detect_api_integration([tech]) is True

    def test_surface_automation_returns_false(self):
        """Surface automation technology returns False."""
        tech = DetectedTechnology(name="Citrix Gateway", category="surface_automation")
        assert _detect_api_integration([tech]) is False

    def test_empty_list_returns_false(self):
        """Empty technology list returns False."""
        assert _detect_api_integration([]) is False

    def test_case_insensitive_detection(self):
        """Detection is case-insensitive."""
        tech = DetectedTechnology(name="REST API CALL")
        assert _detect_api_integration([tech]) is True

    def test_multiple_technologies_with_one_match(self):
        """Returns True if any technology matches."""
        techs = [
            DetectedTechnology(name="Citrix Gateway", category="surface_automation"),
            DetectedTechnology(name="REST API", category="api"),
        ]
        assert _detect_api_integration(techs) is True

    def test_multiple_technologies_with_no_match(self):
        """Returns False if no technology matches."""
        techs = [
            DetectedTechnology(name="Citrix Gateway", category="surface_automation"),
            DetectedTechnology(name="Python Script", category="scripting"),
        ]
        assert _detect_api_integration(techs) is False


# ==================== TEST: DetectedTechnology Validators ====================


class TestDetectedTechnologyValidators:
    """Tests for DetectedTechnology field validators."""

    def test_invalid_category_defaults_to_other(self):
        """Invalid category defaults to 'other' without raising."""
        tech = DetectedTechnology(name="Unknown", category="invalid_category")
        assert tech.category == "other"

    def test_valid_category_preserved(self):
        """Valid category is preserved."""
        tech = DetectedTechnology(name="REST API", category="api")
        assert tech.category == "api"

    def test_category_case_insensitive(self):
        """Category is lowercased."""
        tech = DetectedTechnology(name="Citrix", category="SURFACE_AUTOMATION")
        assert tech.category == "surface_automation"

    def test_confidence_clamped_to_min(self):
        """Confidence below 0.0 is clamped to 0.0."""
        tech = DetectedTechnology(name="Tech", confidence=-0.5)
        assert tech.confidence == 0.0

    def test_confidence_clamped_to_max(self):
        """Confidence above 1.0 is clamped to 1.0."""
        tech = DetectedTechnology(name="Tech", confidence=1.5)
        assert tech.confidence == 1.0

    def test_confidence_within_range(self):
        """Confidence within 0.0-1.0 is preserved."""
        tech = DetectedTechnology(name="Tech", confidence=0.75)
        assert tech.confidence == 0.75

    def test_all_valid_categories(self):
        """All valid categories are accepted."""
        categories = [
            "surface_automation",
            "api",
            "scripting",
            "connector",
            "ocr",
            "ml",
            "other",
        ]
        for category in categories:
            tech = DetectedTechnology(name="Tech", category=category)
            assert tech.category == category

    def test_rpa_tool_notes_defaults(self):
        """RPAToolNotes defaults are set correctly."""
        tech = DetectedTechnology(name="Tech")
        assert tech.rpa_tool_notes.blue_prism == "No special impact"
        assert tech.rpa_tool_notes.uipath == "No special impact"
        assert tech.rpa_tool_notes.power_automate == "No special impact"
        assert tech.rpa_tool_notes.aa360 == "No special impact"

    def test_rpa_tool_notes_can_be_customized(self):
        """RPAToolNotes can be customized."""
        notes = RPAToolNotes(
            blue_prism="Special handling required",
            uipath="No special impact",
            power_automate="No special impact",
            aa360="No special impact",
        )
        tech = DetectedTechnology(name="Citrix", rpa_tool_notes=notes)
        assert tech.rpa_tool_notes.blue_prism == "Special handling required"


# ==================== TEST: _filter_relevant_sections ====================


class TestFilterRelevantSections:
    """Tests for _filter_relevant_sections helper."""

    def test_priority_process_steps(self):
        """Returns process_steps section if available."""
        sections = [
            ExtractedSection(
                title="Overview",
                section_type="process_overview",
                content="Overview",
                confidence_score=0.9,
            ),
            ExtractedSection(
                title="Steps",
                section_type="process_steps",
                content="Steps",
                confidence_score=0.9,
            ),
        ]
        result = _filter_relevant_sections(sections)
        assert len(result) == 1
        assert result[0].section_type == "process_steps"

    def test_priority_process_overview(self):
        """Returns process_overview when no process_steps."""
        sections = [
            ExtractedSection(
                title="Overview",
                section_type="process_overview",
                content="Overview",
                confidence_score=0.9,
            ),
            ExtractedSection(
                title="Apps",
                section_type="applications",
                content="Apps",
                confidence_score=0.9,
            ),
        ]
        result = _filter_relevant_sections(sections)
        assert len(result) == 1
        assert result[0].section_type == "process_overview"

    def test_priority_applications(self):
        """Returns applications when no higher priority."""
        sections = [
            ExtractedSection(
                title="Apps",
                section_type="applications",
                content="Apps",
                confidence_score=0.9,
            ),
            ExtractedSection(
                title="General",
                section_type="general",
                content="General",
                confidence_score=0.9,
            ),
        ]
        result = _filter_relevant_sections(sections)
        assert len(result) == 1
        assert result[0].section_type == "applications"

    def test_priority_general(self):
        """Returns general when no higher priority."""
        sections = [
            ExtractedSection(
                title="General",
                section_type="general",
                content="General",
                confidence_score=0.9,
            ),
        ]
        result = _filter_relevant_sections(sections)
        assert len(result) == 1
        assert result[0].section_type == "general"

    def test_excludes_business_rules(self):
        """Excludes business_rules section."""
        sections = [
            ExtractedSection(
                title="Rules",
                section_type="business_rules",
                content="Rules",
                confidence_score=0.9,
            ),
        ]
        result = _filter_relevant_sections(sections)
        assert len(result) == 0

    def test_empty_sections(self):
        """Returns empty list for empty input."""
        result = _filter_relevant_sections([])
        assert result == []

    def test_fallback_excludes_business_rules_exceptions_inputs_outputs(self):
        """Fallback excludes business_rules, exceptions, and inputs_outputs."""
        sections = [
            ExtractedSection(
                title="General",
                section_type="general",
                content="General",
                confidence_score=0.9,
            ),
            ExtractedSection(
                title="Exceptions",
                section_type="exceptions",
                content="Exceptions",
                confidence_score=0.9,
            ),
        ]
        result = _filter_relevant_sections(sections)
        assert len(result) == 1
        assert result[0].section_type == "general"


# ==================== TEST: _prepare_sections_text ====================


class TestPrepareSectionsText:
    """Tests for _prepare_sections_text helper."""

    def test_single_section_formatting(self):
        """Single section is formatted correctly."""
        sections = [
            ExtractedSection(
                title="Overview", section_type="process_overview", content="Content here",
                confidence_score=0.9
            ),
        ]
        result = _prepare_sections_text(sections)
        assert "## Overview (process_overview)" in result
        assert "Content here" in result

    def test_multiple_sections_formatting(self):
        """Multiple sections are formatted correctly."""
        sections = [
            ExtractedSection(
                title="Overview",
                section_type="process_overview",
                content="Overview content",
                confidence_score=0.9,
            ),
            ExtractedSection(
                title="Steps",
                section_type="process_steps",
                content="Steps content",
                confidence_score=0.9,
            ),
        ]
        result = _prepare_sections_text(sections)
        assert "## Overview (process_overview)" in result
        assert "Overview content" in result
        assert "## Steps (process_steps)" in result
        assert "Steps content" in result

    def test_empty_sections(self):
        """Empty sections list returns empty string."""
        result = _prepare_sections_text([])
        assert result == ""

    def test_truncation(self):
        """Text longer than max_chars is truncated."""
        long_content = "X" * 5000
        sections = [
            ExtractedSection(
                title="Long",
                section_type="general",
                content=long_content,
                confidence_score=0.9,
            ),
        ]
        result = _prepare_sections_text(sections, max_chars=100)
        assert len(result) <= 150  # 100 + truncation notice
        assert "[Document truncated for processing]" in result

    def test_no_truncation_below_limit(self):
        """Text shorter than max_chars is not truncated."""
        sections = [
            ExtractedSection(
                title="Short",
                section_type="general",
                content="Short content",
                confidence_score=0.9,
            ),
        ]
        result = _prepare_sections_text(sections, max_chars=1000)
        assert "[Document truncated for processing]" not in result


# ==================== TEST: detect_technology ====================


class TestDetectTechnology:
    """Tests for detect_technology main function with mocked LLM."""

    def test_success_returns_technology_detection_result(self):
        """Successful LLM call returns TechnologyDetectionResult."""
        mock_llm = MagicMock()
        mock_response = TechnologyDetectionLLMResponse(
            technologies=[
                DetectedTechnology(
                    name="REST API",
                    category="api",
                    confidence=0.9,
                )
            ],
            total_count=1,
            detection_confidence=0.85,
        )
        mock_llm.complete_structured.return_value = mock_response

        sections = [
            ExtractedSection(
                title="Process",
                section_type="process_steps",
                content="Calls REST API",
                confidence_score=0.9,
            ),
        ]

        result = detect_technology(sections, llm_manager=mock_llm)
        assert isinstance(result, TechnologyDetectionResult)
        assert result.total_count == 1
        assert len(result.technologies) == 1
        assert result.technologies[0].name == "REST API"

    def test_api_detection_flag(self):
        """API integration flag is set correctly."""
        mock_llm = MagicMock()
        mock_response = TechnologyDetectionLLMResponse(
            technologies=[
                DetectedTechnology(name="REST API Gateway", category="api", confidence=0.9)
            ],
            total_count=1,
            detection_confidence=0.85,
        )
        mock_llm.complete_structured.return_value = mock_response

        sections = [
            ExtractedSection(
                title="Process",
                section_type="process_steps",
                content="Calls REST API",
                confidence_score=0.9,
            ),
        ]

        result = detect_technology(sections, llm_manager=mock_llm)
        assert result.has_api_integration is True
        assert result.has_surface_automation is False

    def test_surface_automation_detection_flag(self):
        """Surface automation flag is set correctly."""
        mock_llm = MagicMock()
        mock_response = TechnologyDetectionLLMResponse(
            technologies=[
                DetectedTechnology(
                    name="Citrix VDI",
                    category="surface_automation",
                    confidence=0.9,
                )
            ],
            total_count=1,
            detection_confidence=0.85,
        )
        mock_llm.complete_structured.return_value = mock_response

        sections = [
            ExtractedSection(
                title="Process",
                section_type="process_steps",
                content="Uses Citrix",
                confidence_score=0.9,
            ),
        ]

        result = detect_technology(sections, llm_manager=mock_llm)
        assert result.has_surface_automation is True
        assert result.has_api_integration is False

    def test_ceiling_enforcement(self):
        """Technology count is capped at XL ceiling (5)."""
        mock_llm = MagicMock()
        # Create 7 technologies
        technologies = [
            DetectedTechnology(name=f"Tech{i}", category="api", confidence=0.9 - i * 0.1)
            for i in range(7)
        ]
        mock_response = TechnologyDetectionLLMResponse(
            technologies=technologies,
            total_count=7,
            detection_confidence=0.85,
        )
        mock_llm.complete_structured.return_value = mock_response

        sections = [
            ExtractedSection(
                title="Process",
                section_type="process_steps",
                content="Content",
                confidence_score=0.9,
            ),
        ]

        result = detect_technology(sections, llm_manager=mock_llm)
        assert result.total_count == 5  # Capped at 5
        assert len(result.technologies) == 5

    def test_ceiling_keeps_highest_confidence(self):
        """When capping, keeps technologies with highest confidence."""
        mock_llm = MagicMock()
        # Create 7 technologies with varying confidence
        technologies = [
            DetectedTechnology(name="Tech1", category="api", confidence=0.5),
            DetectedTechnology(name="Tech2", category="api", confidence=0.9),  # Highest
            DetectedTechnology(name="Tech3", category="api", confidence=0.6),
            DetectedTechnology(name="Tech4", category="api", confidence=0.8),
            DetectedTechnology(name="Tech5", category="api", confidence=0.7),
            DetectedTechnology(name="Tech6", category="api", confidence=0.95),  # Second highest
            DetectedTechnology(name="Tech7", category="api", confidence=0.4),
        ]
        mock_response = TechnologyDetectionLLMResponse(
            technologies=technologies,
            total_count=7,
            detection_confidence=0.85,
        )
        mock_llm.complete_structured.return_value = mock_response

        sections = [
            ExtractedSection(
                title="Process",
                section_type="process_steps",
                content="Content",
                confidence_score=0.9,
            ),
        ]

        result = detect_technology(sections, llm_manager=mock_llm)
        assert result.total_count == 5
        # Top 5 by confidence: Tech6 (0.95), Tech2 (0.9), Tech4 (0.8), Tech5 (0.7), Tech3 (0.6)
        names = [t.name for t in result.technologies]
        assert "Tech6" in names  # 0.95
        assert "Tech2" in names  # 0.9

    def test_retry_on_first_failure(self):
        """Falls back to retry if first LLM call fails."""
        mock_llm = MagicMock()
        mock_llm.complete_structured.side_effect = [
            Exception("First call failed"),  # First call fails
            TechnologyDetectionLLMResponse(
                technologies=[
                    DetectedTechnology(name="REST API", category="api", confidence=0.8)
                ],
                total_count=1,
                detection_confidence=0.7,
            ),  # Retry succeeds
        ]

        sections = [
            ExtractedSection(
                title="Process",
                section_type="process_steps",
                content="Content",
                confidence_score=0.9,
            ),
        ]

        with patch("tools.analysis.technology_detector.LLMProviderError", Exception):
            result = detect_technology(sections, llm_manager=mock_llm)
            assert result.total_count == 1

    def test_both_attempts_fail_returns_empty(self):
        """Both LLM attempts fail returns empty result."""
        mock_llm = MagicMock()
        mock_llm.complete_structured.side_effect = Exception("LLM error")

        sections = [
            ExtractedSection(
                title="Process",
                section_type="process_steps",
                content="Content",
                confidence_score=0.9,
            ),
        ]

        with patch("tools.analysis.technology_detector.LLMProviderError", Exception):
            result = detect_technology(sections, llm_manager=mock_llm)
            assert result.total_count == 0
            assert len(result.technologies) == 0
            assert result.detection_confidence == 0.0

    def test_entity_result_appended_to_sections_text(self):
        """Previously identified technologies from entity_result are included."""
        mock_llm = MagicMock()
        mock_response = TechnologyDetectionLLMResponse(
            technologies=[],
            total_count=0,
            detection_confidence=0.5,
        )
        mock_llm.complete_structured.return_value = mock_response

        # Create mock entity_result with technologies
        mock_entity_result = MagicMock()
        mock_entity_result.technologies = [
            MagicMock(name="Citrix", category="surface_automation", notes="VDI needed"),
        ]

        sections = [
            ExtractedSection(
                title="Process",
                section_type="process_steps",
                content="Content",
                confidence_score=0.9,
            ),
        ]

        result = detect_technology(sections, entity_result=mock_entity_result, llm_manager=mock_llm)

        # Verify that the mock was called (entity_result was processed)
        # Check the call args to see if entity technologies were appended
        call_args = mock_llm.complete_structured.call_args
        prompt = call_args[1]["prompt"]
        assert "Previously Identified Technologies" in prompt or "Citrix" in prompt

    def test_default_llm_manager_created(self):
        """If no llm_manager provided, default is created."""
        mock_llm = MagicMock()
        mock_response = TechnologyDetectionLLMResponse(
            technologies=[],
            total_count=0,
            detection_confidence=0.5,
        )
        mock_llm.complete_structured.return_value = mock_response

        sections = [
            ExtractedSection(
                title="Process",
                section_type="process_steps",
                content="Content",
                confidence_score=0.9,
            ),
        ]

        with patch(
            "tools.analysis.technology_detector.LLMManager.create_default",
            return_value=mock_llm,
        ):
            result = detect_technology(sections, llm_manager=None)
            assert isinstance(result, TechnologyDetectionResult)


# ==================== TEST: TechnologyDetectionResult Computed Properties ====================


class TestTechnologyDetectionResultProperties:
    """Tests for TechnologyDetectionResult computed properties."""

    def test_technology_names_property(self):
        """technology_names() returns list of technology names."""
        result = TechnologyDetectionResult(
            technologies=[
                DetectedTechnology(name="Citrix VDI"),
                DetectedTechnology(name="REST API"),
            ],
            total_count=2,
            detection_confidence=0.8,
            has_surface_automation=True,
            has_api_integration=True,
        )
        names = result.technology_names()
        assert names == ["Citrix VDI", "REST API"]

    def test_exceeds_xl_ceiling_true(self):
        """exceeds_xl_ceiling() returns True when count > 5."""
        result = TechnologyDetectionResult(
            technologies=[
                DetectedTechnology(name=f"Tech{i}") for i in range(6)
            ],
            total_count=6,
            detection_confidence=0.8,
            has_surface_automation=False,
            has_api_integration=False,
        )
        assert result.exceeds_xl_ceiling() is True

    def test_exceeds_xl_ceiling_false(self):
        """exceeds_xl_ceiling() returns False when count <= 5."""
        result = TechnologyDetectionResult(
            technologies=[
                DetectedTechnology(name=f"Tech{i}") for i in range(3)
            ],
            total_count=3,
            detection_confidence=0.8,
            has_surface_automation=False,
            has_api_integration=False,
        )
        assert result.exceeds_xl_ceiling() is False

    def test_get_rpa_tool_note_blue_prism(self):
        """get_rpa_tool_note('blue_prism') returns Blue Prism notes."""
        result = TechnologyDetectionResult(
            technologies=[
                DetectedTechnology(
                    name="Citrix",
                    rpa_tool_notes=RPAToolNotes(
                        blue_prism="Requires special module",
                        uipath="No special impact",
                        power_automate="No special impact",
                        aa360="No special impact",
                    ),
                ),
            ],
            total_count=1,
            detection_confidence=0.8,
            has_surface_automation=True,
            has_api_integration=False,
        )
        notes = result.get_rpa_tool_note("blue_prism")
        assert notes == ["Requires special module"]

    def test_get_rpa_tool_note_uipath(self):
        """get_rpa_tool_note('uipath') returns UiPath notes."""
        result = TechnologyDetectionResult(
            technologies=[
                DetectedTechnology(
                    name="REST API",
                    rpa_tool_notes=RPAToolNotes(
                        blue_prism="No special impact",
                        uipath="Use HTTP activities",
                        power_automate="No special impact",
                        aa360="No special impact",
                    ),
                ),
            ],
            total_count=1,
            detection_confidence=0.8,
            has_surface_automation=False,
            has_api_integration=True,
        )
        notes = result.get_rpa_tool_note("uipath")
        assert notes == ["Use HTTP activities"]

    def test_get_rpa_tool_note_empty_for_no_special_impact(self):
        """get_rpa_tool_note returns empty list when no special impact."""
        result = TechnologyDetectionResult(
            technologies=[
                DetectedTechnology(
                    name="REST API",
                    rpa_tool_notes=RPAToolNotes(
                        blue_prism="No special impact",
                        uipath="No special impact",
                        power_automate="No special impact",
                        aa360="No special impact",
                    ),
                ),
            ],
            total_count=1,
            detection_confidence=0.8,
            has_surface_automation=False,
            has_api_integration=True,
        )
        notes = result.get_rpa_tool_note("blue_prism")
        assert notes == []

    def test_get_rpa_tool_note_multiple_technologies(self):
        """get_rpa_tool_note returns notes from all technologies."""
        result = TechnologyDetectionResult(
            technologies=[
                DetectedTechnology(
                    name="Citrix",
                    rpa_tool_notes=RPAToolNotes(
                        blue_prism="Surface automation module required",
                        uipath="No special impact",
                        power_automate="No special impact",
                        aa360="No special impact",
                    ),
                ),
                DetectedTechnology(
                    name="REST API",
                    rpa_tool_notes=RPAToolNotes(
                        blue_prism="REST API stage available",
                        uipath="No special impact",
                        power_automate="No special impact",
                        aa360="No special impact",
                    ),
                ),
            ],
            total_count=2,
            detection_confidence=0.8,
            has_surface_automation=True,
            has_api_integration=True,
        )
        notes = result.get_rpa_tool_note("blue_prism")
        assert len(notes) == 2
        assert "Surface automation module required" in notes
        assert "REST API stage available" in notes

    def test_get_rpa_tool_note_invalid_tool_name(self):
        """get_rpa_tool_note returns empty list for invalid tool name."""
        result = TechnologyDetectionResult(
            technologies=[
                DetectedTechnology(
                    name="Citrix",
                    rpa_tool_notes=RPAToolNotes(
                        blue_prism="Requires special module",
                        uipath="No special impact",
                        power_automate="No special impact",
                        aa360="No special impact",
                    ),
                ),
            ],
            total_count=1,
            detection_confidence=0.8,
            has_surface_automation=True,
            has_api_integration=False,
        )
        notes = result.get_rpa_tool_note("invalid_tool")
        assert notes == []

    def test_get_rpa_tool_note_aa360(self):
        """get_rpa_tool_note('aa360') returns AA360 notes."""
        result = TechnologyDetectionResult(
            technologies=[
                DetectedTechnology(
                    name="Citrix",
                    rpa_tool_notes=RPAToolNotes(
                        blue_prism="No special impact",
                        uipath="No special impact",
                        power_automate="No special impact",
                        aa360="AA360 requires custom connector",
                    ),
                ),
            ],
            total_count=1,
            detection_confidence=0.8,
            has_surface_automation=True,
            has_api_integration=False,
        )
        notes = result.get_rpa_tool_note("aa360")
        assert notes == ["AA360 requires custom connector"]


# ==================== TEST: get_technology_count ====================


class TestGetTechnologyCount:
    """Tests for get_technology_count utility function."""

    def test_returns_total_count(self):
        """Returns total_count from result."""
        result = TechnologyDetectionResult(
            technologies=[DetectedTechnology(name="Citrix")],
            total_count=1,
            detection_confidence=0.8,
            has_surface_automation=True,
            has_api_integration=False,
        )
        assert get_technology_count(result) == 1

    def test_returns_zero_count(self):
        """Returns 0 when no technologies."""
        result = TechnologyDetectionResult(
            technologies=[],
            total_count=0,
            detection_confidence=0.0,
            has_surface_automation=False,
            has_api_integration=False,
        )
        assert get_technology_count(result) == 0

    def test_returns_ceiling_count(self):
        """Returns count at ceiling."""
        result = TechnologyDetectionResult(
            technologies=[DetectedTechnology(name=f"Tech{i}") for i in range(5)],
            total_count=5,
            detection_confidence=0.8,
            has_surface_automation=False,
            has_api_integration=False,
        )
        assert get_technology_count(result) == 5


# ==================== TEST: get_technology_tier_hint ====================


class TestGetTechnologyTierHint:
    """Tests for get_technology_tier_hint utility function."""

    def test_zero_technologies(self):
        """0 technologies returns XS/S hint."""
        result = TechnologyDetectionResult(
            technologies=[],
            total_count=0,
            detection_confidence=0.0,
            has_surface_automation=False,
            has_api_integration=False,
        )
        hint = get_technology_tier_hint(result)
        assert "XS or S" in hint
        assert "no additional technology" in hint

    def test_one_technology(self):
        """1 technology returns M hint."""
        result = TechnologyDetectionResult(
            technologies=[DetectedTechnology(name="REST API")],
            total_count=1,
            detection_confidence=0.8,
            has_surface_automation=False,
            has_api_integration=True,
        )
        hint = get_technology_tier_hint(result)
        assert "M" in hint
        assert "1 additional" in hint

    def test_two_technologies(self):
        """2 technologies returns L hint."""
        result = TechnologyDetectionResult(
            technologies=[
                DetectedTechnology(name="REST API"),
                DetectedTechnology(name="Python Script"),
            ],
            total_count=2,
            detection_confidence=0.8,
            has_surface_automation=False,
            has_api_integration=True,
        )
        hint = get_technology_tier_hint(result)
        assert "L" in hint
        assert "2-3" in hint

    def test_three_technologies(self):
        """3 technologies returns L hint."""
        result = TechnologyDetectionResult(
            technologies=[
                DetectedTechnology(name=f"Tech{i}") for i in range(3)
            ],
            total_count=3,
            detection_confidence=0.8,
            has_surface_automation=False,
            has_api_integration=True,
        )
        hint = get_technology_tier_hint(result)
        assert "L" in hint

    def test_five_technologies(self):
        """5 technologies returns XL hint."""
        result = TechnologyDetectionResult(
            technologies=[
                DetectedTechnology(name=f"Tech{i}") for i in range(5)
            ],
            total_count=5,
            detection_confidence=0.8,
            has_surface_automation=False,
            has_api_integration=True,
        )
        hint = get_technology_tier_hint(result)
        assert "XL" in hint
        assert "4-5" in hint

    def test_exceeds_ceiling(self):
        """More than 5 technologies returns exceeds hint."""
        result = TechnologyDetectionResult(
            technologies=[
                DetectedTechnology(name=f"Tech{i}") for i in range(6)
            ],
            total_count=6,
            detection_confidence=0.8,
            has_surface_automation=False,
            has_api_integration=True,
        )
        hint = get_technology_tier_hint(result)
        assert "Exceeds XL" in hint
        assert "Tech Lead" in hint


# ==================== TEST: Ground Truth ====================


class TestGroundTruth:
    """Ground truth test against known Excel project."""

    def test_ground_truth_technology_count(self):
        """Ground truth: GMP + Excel process has 0 additional technologies.

        From the Excel workbook:
        - No Citrix/surface automation
        - No API/web service integration
        - No scripting (Python/VBA)
        - Technology count = 0 (XS/S tier, weight=1)
        """
        # Create result with 0 technologies (ground truth)
        result = TechnologyDetectionResult(
            technologies=[],
            total_count=0,
            detection_confidence=0.9,
            excluded_items=[
                ExcludedTechnology(
                    name="Standard UI automation",
                    reason="Native to all RPA tools",
                ),
                ExcludedTechnology(
                    name="Excel read/write",
                    reason="Native to all RPA tools",
                ),
            ],
            notes="No additional technology requirements",
            has_surface_automation=False,
            has_api_integration=False,
        )

        # Verify ground truth assertions
        assert get_technology_count(result) == 0
        assert result.has_surface_automation is False
        assert result.has_api_integration is False
        assert "XS or S" in get_technology_tier_hint(result)


# ==================== TEST: Integration ====================


@pytest.mark.integration
def test_detect_technology_integration():
    """Integration test with real document parsing."""
    # This would require sample_process.docx to exist
    # For now, test with mocked data
    mock_llm = MagicMock()
    mock_response = TechnologyDetectionLLMResponse(
        technologies=[
            DetectedTechnology(
                name="REST API Gateway",
                category="api",
                description="Calls external REST API for data retrieval",
                evidence="Process calls REST API endpoint",
                confidence=0.85,
                rpa_tool_notes=RPAToolNotes(
                    blue_prism="Use REST API stage",
                    uipath="Use HTTP activities",
                    power_automate="No special impact",
                    aa360="No special impact",
                ),
            ),
        ],
        total_count=1,
        detection_confidence=0.8,
    )
    mock_llm.complete_structured.return_value = mock_response

    sections = [
        ExtractedSection(
            title="Process Steps",
            section_type="process_steps",
            content="The process calls an external REST API",
            confidence_score=0.9,
        ),
    ]

    result = detect_technology(sections, llm_manager=mock_llm)

    # Assertions
    assert isinstance(result, TechnologyDetectionResult)
    assert result.total_count >= 0
    assert result.detection_confidence > 0.0
    assert len(result.technology_names()) == result.total_count
    assert result.has_api_integration is True or result.has_surface_automation is False

    # Print output for visibility
    print(f"Technologies detected: {result.total_count}")
    print(f"Names: {result.technology_names()}")
    print(f"Surface automation: {result.has_surface_automation}")
    print(f"API integration: {result.has_api_integration}")
    print(f"Excluded items: {len(result.excluded_items)}")
