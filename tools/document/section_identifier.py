"""Section identifier for Process Design Documents.

Uses pattern matching (fast, zero cost) as primary strategy,
with LLM fallback (called only when pattern matching finds
fewer than 3 sections).

All prompts defined in tools/document/prompts.py.
All LLM access via llm.manager.LLMManager abstraction.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from pydantic import BaseModel, Field

from config.logging_config import get_logger
from core.exceptions import DocumentProcessingError, LLMProviderError
from core.models.document import ExtractedSection, ParsedDocument
from llm.manager import LLMManager
from tools.document.prompts import (
    SECTION_IDENTIFICATION_PROMPT,
    SECTION_IDENTIFICATION_RETRY_PROMPT,
    SECTION_IDENTIFICATION_SYSTEM,
)

logger = get_logger("section_identifier")

# Section type patterns for pattern matching
SECTION_PATTERNS: dict[str, list[str]] = {
    "process_overview": [
        "process overview",
        "overview",
        "introduction",
        "background",
        "process description",
        "about this process",
        "process summary",
        "scope",
    ],
    "process_steps": [
        "process steps",
        "steps",
        "workflow",
        "procedure",
        "process flow",
        "automation steps",
        "step by step",
        "process details",
        "activities",
    ],
    "business_rules": [
        "business rules",
        "rules",
        "decision",
        "conditions",
        "logic",
        "exceptions to process",
        "validations",
        "business logic",
        "decision points",
    ],
    "applications": [
        "applications",
        "systems",
        "target applications",
        "interfaces",
        "tools used",
        "technology",
        "platforms",
        "applications used",
        "target systems",
    ],
    "exceptions": [
        "exception",
        "error handling",
        "errors",
        "edge cases",
        "failure",
        "fallback",
        "escalation",
        "issues",
        "exception handling",
        "error scenarios",
    ],
    "inputs_outputs": [
        "input",
        "output",
        "layout",
        "template",
        "file",
        "document",
        "report",
        "data",
        "inputs and outputs",
        "digital layouts",
        "attachments",
    ],
}

# Valid section types for validation
VALID_SECTION_TYPES = set(SECTION_PATTERNS.keys()) | {"general"}


# ==================== PYDANTIC SCHEMAS ====================


class SectionResponse(BaseModel):
    """Response schema for individual section from LLM."""

    title: str
    section_type: str
    content: str
    confidence_score: float
    page_number: int | None = None


class SectionsListResponse(BaseModel):
    """Response schema for sections list from LLM."""

    sections: list[SectionResponse] = Field(default_factory=list)


# ==================== PATTERN MATCHING ====================


def identify_sections_by_pattern(document: ParsedDocument) -> list[ExtractedSection]:
    """
    Fast pattern-based section detection using structural markers.

    Looks for:
    - DOCX heading markers: "=== {text} ===", "--- {text} ---"
    - PDF page markers: "--- Page N ---"
    - Short, capitalized lines followed by content

    Args:
        document: ParsedDocument to analyze

    Returns:
        List of ExtractedSection objects found by pattern matching.
        Returns empty list if no structural markers found.
    """
    sections = []
    text = document.full_text
    lines = text.split("\n")

    # Track position for ordering sections
    current_position = 0

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Skip empty lines
        if not stripped:
            continue

        # Check for DOCX heading markers
        heading_text = None
        is_heading = False

        # Heading 1: === text ===
        if stripped.startswith("===") and stripped.endswith("==="):
            heading_text = stripped[3:-3].strip()
            is_heading = True
        # Heading 2: --- text ---
        elif stripped.startswith("---") and stripped.endswith("---") and not re.match(
            r"^--- Page \d+ ---$", stripped
        ):
            heading_text = stripped[3:-3].strip()
            is_heading = True
        # Heading 3: > text
        elif stripped.startswith(">"):
            heading_text = stripped[1:].strip()
            is_heading = True

        # Check for unstructured headings (short, capitalized lines)
        if not is_heading and len(stripped) < 60 and stripped.isupper() and len(stripped) > 3:
            # Check if followed by content (next non-empty line is not a heading)
            if i + 1 < len(lines):
                next_non_empty = None
                for j in range(i + 1, len(lines)):
                    if lines[j].strip():
                        next_non_empty = lines[j].strip()
                        break
                # If next line is not a heading marker, treat current as heading
                if (
                    next_non_empty
                    and not next_non_empty.startswith("===")
                    and not next_non_empty.startswith("---")
                    and not next_non_empty.startswith(">")
                ):
                    heading_text = stripped
                    is_heading = True

        if is_heading and heading_text:
            # Determine section type
            section_type = _get_section_type_from_pattern(heading_text)
            confidence = 0.85 if section_type != "general" else 0.5

            # Extract page number from context
            text_before = "\n".join(lines[:i])
            page_number = _extract_page_number(text_before)

            # Extract content until next heading
            content_lines = []
            for j in range(i + 1, len(lines)):
                next_line = lines[j].strip()
                # Stop at next heading
                if (
                    next_line.startswith("===")
                    or next_line.startswith("---")
                    or next_line.startswith(">")
                    or (len(next_line) < 60 and next_line.isupper() and len(next_line) > 3)
                ):
                    break
                content_lines.append(lines[j])

            content = "\n".join(content_lines).strip()

            section = ExtractedSection(
                title=heading_text,
                content=content,
                section_type=section_type,
                confidence_score=confidence,
                page_number=page_number,
            )
            sections.append(section)
            current_position = text.find(heading_text, current_position)

    logger.debug(f"Pattern matching found {len(sections)} sections")
    return sections


def _get_section_type_from_pattern(heading_text: str) -> str:
    """
    Determine section type by matching heading text against patterns.

    Args:
        heading_text: The heading text to classify

    Returns:
        Section type key or "general" if no match
    """
    heading_lower = heading_text.lower().strip()

    for section_type, patterns in SECTION_PATTERNS.items():
        for pattern in patterns:
            if pattern.lower() in heading_lower:
                return section_type

    return "general"


def _extract_page_number(text_before_section: str) -> int | None:
    """
    Extract page number from "--- Page N ---" markers in preceding text.

    Args:
        text_before_section: Text content before the section

    Returns:
        Page number as int, or None if not found
    """
    matches = re.findall(r"--- Page (\d+) ---", text_before_section)
    if matches:
        return int(matches[-1])  # Return the most recent page number
    return None


# ==================== LLM FALLBACK ====================


def identify_sections_by_llm(
    document: ParsedDocument, llm_manager: LLMManager
) -> list[ExtractedSection]:
    """
    LLM-based section detection (fallback when pattern matching insufficient).

    Args:
        document: ParsedDocument to analyze
        llm_manager: LLMManager instance for API access

    Returns:
        List of ExtractedSection objects from LLM analysis.
        Returns empty list if LLM call fails.
    """
    # Truncate to manage token limits
    max_chars = 8000
    text_for_llm = document.full_text[: max_chars]

    if len(document.full_text) > max_chars:
        logger.debug(
            f"Document truncated from {len(document.full_text)} to {max_chars} characters for LLM"
        )

    # Format prompt
    prompt = SECTION_IDENTIFICATION_PROMPT.format(document_text=text_for_llm)

    try:
        # Call LLM via manager
        response = llm_manager.complete_structured(
            prompt=prompt,
            response_schema=SectionsListResponse,
            system=SECTION_IDENTIFICATION_SYSTEM,
            max_tokens=2000,
            session_id="section_identifier",
        )

        # Convert response to ExtractedSection objects
        sections = []
        for section_resp in response.sections:
            # Validate and normalize section_type
            section_type = section_resp.section_type
            if section_type not in VALID_SECTION_TYPES:
                logger.debug(f"Invalid section_type '{section_type}' remapped to 'general'")
                section_type = "general"

            # Clamp confidence score
            confidence = max(0.0, min(1.0, section_resp.confidence_score))

            section = ExtractedSection(
                title=section_resp.title,
                content=section_resp.content,
                section_type=section_type,
                confidence_score=confidence,
                page_number=section_resp.page_number,
            )
            sections.append(section)

        logger.info(f"LLM identified {len(sections)} sections")
        return sections

    except LLMProviderError as e:
        logger.warning(f"LLM fallback failed: {e}")
        return []


# ==================== ORCHESTRATION ====================


def identify_sections(
    document: ParsedDocument, llm_manager: LLMManager | None = None
) -> list[ExtractedSection]:
    """
    Identify sections in a document using pattern matching + LLM fallback.

    Strategy:
    1. Try pattern matching (fast, zero cost)
    2. If < 3 sections found, fall back to LLM
    3. Merge results without duplicates
    4. Return catch-all section if nothing found

    Args:
        document: ParsedDocument to analyze
        llm_manager: Optional LLMManager. If None and LLM is needed,
                     creates default instance.

    Returns:
        Ordered list of ExtractedSection objects.
    """
    # STEP 1: Pattern matching
    pattern_sections = identify_sections_by_pattern(document)

    # STEP 2: Check if we need LLM fallback
    if len(pattern_sections) >= 3:
        logger.info(f"Pattern matching found {len(pattern_sections)} sections — skipping LLM")
        return pattern_sections

    # STEP 3: LLM fallback
    logger.info(
        f"Pattern matching found only {len(pattern_sections)} sections — "
        "falling back to LLM"
    )

    if llm_manager is None:
        llm_manager = LLMManager.create_default()

    llm_sections = identify_sections_by_llm(document, llm_manager)

    # STEP 4: Merge results (avoid duplicates by title)
    merged = list(pattern_sections)
    pattern_titles = {s.title.lower() for s in pattern_sections}

    for llm_section in llm_sections:
        if llm_section.title.lower() not in pattern_titles:
            merged.append(llm_section)
            pattern_titles.add(llm_section.title.lower())

    # STEP 5: Catch-all fallback
    if not merged:
        logger.warning(f"No sections identified in {document.source_path}")
        merged = [
            ExtractedSection(
                title="Full Document",
                content=document.full_text[:5000],
                section_type="general",
                confidence_score=0.1,
                page_number=None,
            )
        ]

    # STEP 6: Sort by appearance in document
    def get_section_position(section: ExtractedSection) -> int:
        """Get position of section title in document text."""
        pos = document.full_text.find(section.title)
        return pos if pos >= 0 else len(document.full_text)

    merged.sort(key=get_section_position)

    logger.info(f"Final section count: {len(merged)}")
    return merged
