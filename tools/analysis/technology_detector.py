"""Technology detector tool for Process Design Documents.

Identifies additional technologies that require development effort beyond
standard RPA capabilities. Enforces strict definition per Excel specification.

All prompts defined in tools/analysis/prompts.py.
All LLM access via llm.manager.LLMManager abstraction.
"""

from __future__ import annotations

import logging
import re

from pydantic import BaseModel, Field, field_validator

from config.logging_config import get_logger
from core.exceptions import LLMProviderError
from core.models.document import ExtractedSection
from llm.manager import LLMManager
from tools.analysis.prompts import (
    TECHNOLOGY_DETECTION_PROMPT,
    TECHNOLOGY_DETECTION_RETRY_PROMPT,
    TECHNOLOGY_DETECTION_SYSTEM,
)

logger = get_logger("technology_detector")

# XL ceiling for technologies
XL_TECHNOLOGY_CEILING = 5


# ==================== INTERNAL SCHEMAS ====================


class RPAToolNotes(BaseModel):
    """Notes on RPA platform-specific impacts."""

    blue_prism: str = Field(default="No special impact")
    uipath: str = Field(default="No special impact")
    power_automate: str = Field(default="No special impact")
    aa360: str = Field(default="No special impact")


class DetectedTechnology(BaseModel):
    """Represents an additional technology requiring development effort."""

    name: str = Field(..., description="Technology name")
    category: str = Field(
        default="other",
        description="Type: surface_automation|api|scripting|connector|ocr|ml|other",
    )
    description: str = Field(default="", description="How it is used")
    evidence: str = Field(default="", description="Evidence from the document")
    confidence: float = Field(
        default=0.5, description="Confidence 0.0-1.0 in this detection"
    )
    rpa_tool_notes: RPAToolNotes = Field(
        default_factory=RPAToolNotes, description="Platform-specific notes"
    )

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        """Validate category is one of allowed values.

        If invalid, defaults to "other" without raising.

        Args:
            v: Category value

        Returns:
            Valid category (or "other" default)
        """
        valid_categories = {
            "surface_automation",
            "api",
            "scripting",
            "connector",
            "ocr",
            "ml",
            "other",
        }
        if v.lower() in valid_categories:
            return v.lower()
        return "other"

    @field_validator("confidence")
    @classmethod
    def clamp_confidence(cls, v: float) -> float:
        """Clamp confidence to 0.0-1.0 range.

        Args:
            v: Confidence value

        Returns:
            Clamped confidence value
        """
        return max(0.0, min(1.0, v))


class ExcludedTechnology(BaseModel):
    """Represents a technology considered but excluded."""

    name: str = Field(..., description="Technology name")
    reason: str = Field(
        default="", description="Why it does not count as additional technology"
    )


class TechnologyDetectionLLMResponse(BaseModel):
    """Response schema for technology detection from LLM."""

    technologies: list[DetectedTechnology] = Field(
        default_factory=list, description="List of detected technologies"
    )
    excluded_items: list[ExcludedTechnology] = Field(
        default_factory=list, description="Technologies that were excluded"
    )
    total_count: int = Field(
        default=0, description="Total count of detected technologies"
    )
    detection_confidence: float = Field(
        default=0.5, description="Overall detection confidence"
    )
    notes: str = Field(default="", description="Additional observations")

    @field_validator("total_count")
    @classmethod
    def sync_count(cls, v: int, info) -> int:
        """Sync total_count with len(technologies).

        Args:
            v: Total count value
            info: Validation context

        Returns:
            Synced count
        """
        if hasattr(info, "data") and "technologies" in info.data:
            return len(info.data["technologies"])
        return v


class TechnologyDetectionResult(BaseModel):
    """Final result of technology detection."""

    technologies: list[DetectedTechnology] = Field(
        ..., description="List of detected additional technologies"
    )
    total_count: int = Field(..., description="Total number of technologies")
    detection_confidence: float = Field(
        ..., description="Overall detection confidence"
    )
    excluded_items: list[ExcludedTechnology] = Field(
        default_factory=list, description="Excluded items"
    )
    notes: str = Field(default="", description="Additional notes")
    has_surface_automation: bool = Field(
        ..., description="Whether Citrix/surface automation detected"
    )
    has_api_integration: bool = Field(
        ..., description="Whether API/web service integration detected"
    )

    def technology_names(self) -> list[str]:
        """Get list of technology names.

        Returns:
            List of technology names
        """
        return [t.name for t in self.technologies]

    def exceeds_xl_ceiling(self) -> bool:
        """Check if technology count exceeds XL ceiling (5).

        Returns:
            True if total_count > 5
        """
        return self.total_count > XL_TECHNOLOGY_CEILING

    def get_rpa_tool_note(self, tool_name: str) -> list[str]:
        """Get RPA tool notes for the specified tool.

        Returns only non-"No special impact" notes.

        Args:
            tool_name: "blue_prism"|"uipath"|"power_automate"|"aa360"

        Returns:
            List of notes for that tool
        """
        valid_tools = {"blue_prism", "uipath", "power_automate", "aa360"}
        if tool_name not in valid_tools:
            return []

        notes = []
        for tech in self.technologies:
            note = getattr(tech.rpa_tool_notes, tool_name, "No special impact")
            if note and note != "No special impact":
                notes.append(note)
        return notes


# ==================== HELPER FUNCTIONS ====================


def _filter_relevant_sections(sections: list[ExtractedSection]) -> list[ExtractedSection]:
    """Filter sections most relevant for technology detection.

    Priority order:
    1. section_type == "process_steps"
    2. section_type == "process_overview"
    3. section_type == "applications"
    4. section_type == "general"

    Exclude: "business_rules", "exceptions", "inputs_outputs"
    If no priority sections: return all sections except excluded types.

    Args:
        sections: List of ExtractedSection objects

    Returns:
        Filtered list of relevant sections
    """
    if not sections:
        return []

    # Priority 1: process_steps
    priority_1 = [s for s in sections if s.section_type == "process_steps"]
    if priority_1:
        return priority_1

    # Priority 2: process_overview
    priority_2 = [s for s in sections if s.section_type == "process_overview"]
    if priority_2:
        return priority_2

    # Priority 3: applications
    priority_3 = [s for s in sections if s.section_type == "applications"]
    if priority_3:
        return priority_3

    # Priority 4: general
    priority_4 = [s for s in sections if s.section_type == "general"]
    if priority_4:
        return priority_4

    # Fallback: return all sections except excluded types
    return [
        s for s in sections
        if s.section_type not in {"business_rules", "exceptions", "inputs_outputs"}
    ]


def _prepare_sections_text(
    sections: list[ExtractedSection], max_chars: int = 4000
) -> str:
    """Format sections for LLM prompt.

    For each section:
      Format as:
      "## {section.title} ({section.section_type})\\n{section.content}\\n"

    Join all formatted sections.
    If total length > max_chars: truncate and append notice.

    Args:
        sections: List of ExtractedSection objects
        max_chars: Maximum characters to include

    Returns:
        Formatted sections text
    """
    if not sections:
        return ""

    formatted_parts = []

    for section in sections:
        formatted = f"## {section.title} ({section.section_type})\n{section.content}\n"
        formatted_parts.append(formatted)

    full_text = "".join(formatted_parts)

    if len(full_text) > max_chars:
        full_text = full_text[:max_chars]
        full_text += "\n[Document truncated for processing]"

    return full_text


def _detect_surface_automation(technologies: list[DetectedTechnology]) -> bool:
    """Detect presence of surface automation/Citrix technologies.

    Returns True if any technology has category == "surface_automation"
    OR if any technology name contains (case-insensitive):
    "citrix", "surface", "vnc", "rdp", "remote desktop", "virtual desktop".

    Args:
        technologies: List of DetectedTechnology objects

    Returns:
        True if surface automation detected
    """
    if not technologies:
        return False

    keywords = ["citrix", "surface", "vnc", "rdp", "remote desktop", "virtual desktop"]

    for tech in technologies:
        if tech.category == "surface_automation":
            return True
        tech_name_lower = tech.name.lower()
        for keyword in keywords:
            if keyword in tech_name_lower:
                return True

    return False


def _detect_api_integration(technologies: list[DetectedTechnology]) -> bool:
    """Detect presence of API/web service integration technologies.

    Returns True if any technology has category == "api"
    OR if any technology name contains (case-insensitive):
    "api", "rest", "soap", "web service", "http", "webhook".

    Args:
        technologies: List of DetectedTechnology objects

    Returns:
        True if API integration detected
    """
    if not technologies:
        return False

    keywords = ["api", "rest", "soap", "web service", "http", "webhook"]

    for tech in technologies:
        if tech.category == "api":
            return True
        tech_name_lower = tech.name.lower()
        for keyword in keywords:
            if keyword in tech_name_lower:
                return True

    return False


# ==================== PUBLIC API ====================


def detect_technology(
    sections: list[ExtractedSection],
    entity_result=None,
    llm_manager: LLMManager | None = None,
    session_id: str = "",
) -> TechnologyDetectionResult:
    """Detect additional technologies in a process.

    Analyzes PDD sections to identify technologies requiring development
    effort beyond standard RPA capabilities.

    Args:
        sections: List of ExtractedSection objects
        entity_result: EntityExtractionResponse from entity_extractor (optional)
        llm_manager: Optional LLMManager. If None, creates default.
        session_id: Optional session ID for logging

    Returns:
        TechnologyDetectionResult with detected technologies
    """
    # STEP 1: Filter sections
    relevant = _filter_relevant_sections(sections)
    logger.debug(f"Analysing technologies from {len(relevant)} sections")

    # STEP 2: Prepare text
    sections_text = _prepare_sections_text(relevant, max_chars=4000)

    # STEP 3: Incorporate entity_result if provided
    if entity_result and hasattr(entity_result, "technologies") and entity_result.technologies:
        entity_tech_text = "\n\n## Previously Identified Technologies\n"
        for tech in entity_result.technologies:
            entity_tech_text += f"{tech.name} ({tech.category}): {tech.notes}\n"
        sections_text += entity_tech_text

    # STEP 4: Get LLM manager
    if llm_manager is None:
        llm_manager = LLMManager.create_default()

    # STEP 5: LLM detection — first attempt
    result: TechnologyDetectionLLMResponse | None = None
    try:
        prompt = TECHNOLOGY_DETECTION_PROMPT.format(sections_text=sections_text)
        response = llm_manager.complete_structured(
            prompt=prompt,
            response_schema=TechnologyDetectionLLMResponse,
            system=TECHNOLOGY_DETECTION_SYSTEM,
            max_tokens=1500,
            session_id=session_id or "technology_detector",
        )
        result = response if isinstance(response, TechnologyDetectionLLMResponse) else None
    except LLMProviderError as e:
        logger.warning(f"Technology detection failed on first attempt, retrying: {e}")
        pass

    # STEP 6: Retry on failure
    if result is None:
        try:
            truncated = sections_text[:1500]
            retry_prompt = TECHNOLOGY_DETECTION_RETRY_PROMPT.format(
                sections_text_truncated=truncated
            )
            response = llm_manager.complete_structured(
                prompt=retry_prompt,
                response_schema=TechnologyDetectionLLMResponse,
                system=TECHNOLOGY_DETECTION_SYSTEM,
                max_tokens=800,
                session_id=(session_id or "technology_detector") + "_retry",
            )
            result = response if isinstance(response, TechnologyDetectionLLMResponse) else None
        except LLMProviderError as e:
            logger.error(f"Technology detection failed after retry: {e}")
            # Return empty result on both failures
            return TechnologyDetectionResult(
                technologies=[],
                total_count=0,
                detection_confidence=0.0,
                excluded_items=[],
                notes="Detection failed — manual review required",
                has_surface_automation=False,
                has_api_integration=False,
            )

        if result is None:
            return TechnologyDetectionResult(
                technologies=[],
                total_count=0,
                detection_confidence=0.0,
                excluded_items=[],
                notes="Detection failed — manual review required",
                has_surface_automation=False,
                has_api_integration=False,
            )

    # STEP 8: Post-process
    technologies = result.technologies

    # a) Cap at XL ceiling of 5
    if len(technologies) > XL_TECHNOLOGY_CEILING:
        logger.warning(
            f"Technology count ({len(technologies)}) exceeds XL ceiling "
            f"({XL_TECHNOLOGY_CEILING}) — keeping {XL_TECHNOLOGY_CEILING} "
            f"with highest confidence"
        )
        # Sort by confidence descending, keep top 5
        technologies_sorted = sorted(technologies, key=lambda t: t.confidence, reverse=True)
        technologies = technologies_sorted[:XL_TECHNOLOGY_CEILING]

    # b) Detect flags
    has_surface = _detect_surface_automation(technologies)
    has_api = _detect_api_integration(technologies)

    # STEP 9: Log
    logger.info(
        f"[{session_id or 'technology_detector'}] Technologies detected: "
        f"{len(technologies)}, surface_automation={has_surface}, "
        f"api={has_api}, confidence={result.detection_confidence:.2f}"
    )

    for tech in technologies:
        logger.debug(f"  - {tech.name} ({tech.category})")

    # STEP 10: Return result
    return TechnologyDetectionResult(
        technologies=technologies,
        total_count=len(technologies),
        detection_confidence=result.detection_confidence,
        excluded_items=result.excluded_items,
        notes=result.notes,
        has_surface_automation=has_surface,
        has_api_integration=has_api,
    )


def get_technology_count(result: TechnologyDetectionResult) -> int:
    """Get count of additional technologies from detection result.

    Args:
        result: TechnologyDetectionResult from detect_technology()

    Returns:
        Number of additional technologies (for scoring attribute #5)
    """
    return result.total_count


def get_technology_tier_hint(result: TechnologyDetectionResult) -> str:
    """Get human-readable tier hint from technology count.

    Returns a string hint about which tier the count suggests.
    Does NOT call the scoring engine.
    For logging and debugging only.

    Args:
        result: TechnologyDetectionResult from detect_technology()

    Returns:
        Human-readable tier hint string
    """
    count = result.total_count

    if count == 0:
        return "Likely XS or S (no additional technology)"
    elif count == 1:
        return "Likely M (1 additional technology)"
    elif count <= 3:
        return "Likely L (2-3 additional technologies)"
    elif count <= XL_TECHNOLOGY_CEILING:
        return "Likely XL (4-5 additional technologies)"
    else:
        return "Exceeds XL ceiling — Tech Lead review needed"
