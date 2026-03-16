"""Tests for RPA tool detector."""

from __future__ import annotations

from unittest.mock import MagicMock

from core.constants import RPATool
from core.models.document import ParsedDocument
from tools.analysis.rpa_tool_detector import (
    RPAToolDetectionResult,
    _scan_text_for_tool,
    detect_rpa_tool,
    get_rpa_tool,
)

# ==================== TEST: _scan_text_for_tool ====================


class TestScanTextForTool:
    """Tests for _scan_text_for_tool helper."""

    def test_finds_blue_prism_pattern(self):
        """Finds 'blue prism' pattern in text."""
        text = "the process uses blue prism for automation"
        count, evidence = _scan_text_for_tool(text, "BLUE_PRISM")
        assert count >= 1
        assert len(evidence) > 0

    def test_finds_multiple_mentions(self):
        """Counts multiple mentions of same pattern."""
        text = "blue prism is used. then blue prism was deployed."
        count, evidence = _scan_text_for_tool(text, "BLUE_PRISM")
        assert count >= 2

    def test_case_insensitive_matching(self):
        """Matching is case-insensitive."""
        text = "BLUE PRISM is used here"
        count, evidence = _scan_text_for_tool(text.lower(), "BLUE_PRISM")
        assert count >= 1

    def test_returns_evidence_with_context(self):
        """Evidence includes context window around match."""
        text = "the application uses blue prism orchestrator for automation"
        count, evidence = _scan_text_for_tool(text, "BLUE_PRISM")
        assert len(evidence) > 0
        assert any("blue" in e.lower() for e in evidence)

    def test_limits_to_3_evidence_snippets(self):
        """Limits evidence to max 3 snippets."""
        text = "blue prism " * 10
        count, evidence = _scan_text_for_tool(text, "BLUE_PRISM")
        assert len(evidence) <= 3

    def test_no_match_returns_zero(self):
        """No match returns (0, [])."""
        text = "this document contains no rpa tool mentions"
        count, evidence = _scan_text_for_tool(text, "BLUE_PRISM")
        assert count == 0
        assert evidence == []


# ==================== TEST: RPAToolDetectionResult ====================


class TestRPAToolDetectionResult:
    """Tests for RPAToolDetectionResult schema."""

    def test_confidence_clamped_to_max(self):
        """Confidence > 1.0 is clamped to 1.0."""
        result = RPAToolDetectionResult(
            detected_tool=RPATool.BLUE_PRISM, confidence=1.5, mention_count=5
        )
        assert result.confidence == 1.0

    def test_is_known_true_for_known_tool(self):
        """is_known() returns True for known tools."""
        result = RPAToolDetectionResult(
            detected_tool=RPATool.BLUE_PRISM, confidence=0.9, mention_count=5
        )
        assert result.is_known() is True

    def test_is_known_false_for_unknown_tool(self):
        """is_known() returns False for UNKNOWN tool."""
        result = RPAToolDetectionResult(
            detected_tool=RPATool.UNKNOWN, confidence=0.0, mention_count=0
        )
        assert result.is_known() is False


# ==================== TEST: detect_rpa_tool ====================


class TestDetectRPATool:
    """Tests for detect_rpa_tool main function."""

    def test_detects_blue_prism(self):
        """Detects Blue Prism in document."""
        doc = ParsedDocument(
            source_path="test.docx",
            file_type="docx",
            full_text="blue prism is used. blue prism processes. blue prism automation.",
            page_count=1,
        )
        result = detect_rpa_tool(doc)
        assert result.detected_tool == RPATool.BLUE_PRISM
        assert result.confidence > 0.5
        assert result.mention_count >= 3

    def test_detects_uipath(self):
        """Detects UiPath in document."""
        doc = ParsedDocument(
            source_path="test.docx",
            file_type="docx",
            full_text="uipath orchestrator is deployed here",
            page_count=1,
        )
        result = detect_rpa_tool(doc)
        assert result.detected_tool == RPATool.UIPATH
        assert result.is_known() is True

    def test_detects_power_automate(self):
        """Detects Power Automate in document."""
        doc = ParsedDocument(
            source_path="test.docx",
            file_type="docx",
            full_text="power automate desktop is the automation platform",
            page_count=1,
        )
        result = detect_rpa_tool(doc)
        assert result.detected_tool == RPATool.POWER_AUTOMATE

    def test_detects_aa360(self):
        """Detects AA360 in document."""
        doc = ParsedDocument(
            source_path="test.docx",
            file_type="docx",
            full_text="automation anywhere a360 iqbot solution",
            page_count=1,
        )
        result = detect_rpa_tool(doc)
        assert result.detected_tool == RPATool.AA360

    def test_no_tool_found_returns_unknown(self):
        """Document with no RPA tool returns UNKNOWN."""
        doc = ParsedDocument(
            source_path="test.docx",
            file_type="docx",
            full_text="this is a general document",
            page_count=1,
        )
        result = detect_rpa_tool(doc)
        assert result.detected_tool == RPATool.UNKNOWN
        assert result.is_known() is False

    def test_entity_result_boosts_tool(self):
        """Entity result boosts tool count."""
        doc = ParsedDocument(
            source_path="test.docx",
            file_type="docx",
            full_text="process automation",
            page_count=1,
        )
        entity_result = MagicMock()
        entity_result.rpa_tool = "uipath"

        result = detect_rpa_tool(doc, entity_result=entity_result)
        assert result.detected_tool == RPATool.UIPATH


# ==================== TEST: get_rpa_tool ====================


class TestGetRPATool:
    """Tests for get_rpa_tool utility function."""

    def test_returns_detected_tool(self):
        """Returns detected_tool from result."""
        result = RPAToolDetectionResult(
            detected_tool=RPATool.BLUE_PRISM, confidence=0.9, mention_count=5
        )
        tool = get_rpa_tool(result)
        assert tool == RPATool.BLUE_PRISM
