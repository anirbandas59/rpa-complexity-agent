"""Interface detector tool for Process Design Documents.

Detects and counts distinct target applications/interfaces that the RPA bot
must interact with. Combines results from entity_extractor (already processed)
with fresh LLM analysis, then deduplicates.

All prompts defined in tools/analysis/prompts.py.
All LLM access via llm.manager.LLMManager abstraction.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator

from config.logging_config import get_logger
from core.exceptions import LLMProviderError
from core.models.document import ExtractedSection
from llm.manager import LLMManager
from tools.analysis.prompts import (
    INTERFACE_DETECTION_PROMPT,
    INTERFACE_DETECTION_RETRY_PROMPT,
    INTERFACE_DETECTION_SYSTEM,
)
from tools.document.entity_extractor import ApplicationEntity

logger = get_logger("interface_detector")

# Application name aliases for normalization
APPLICATION_ALIASES: dict[str, str] = {
    "sap ecc": "sap",
    "sap ec2": "sap",
    "sap bw": "sap",
    "sap hr": "sap",
    "ms excel": "excel",
    "microsoft excel": "excel",
    "msexcel": "excel",
    "ms outlook": "outlook",
    "microsoft outlook": "outlook",
    "msoutlook": "outlook",
    "ms word": "word",
    "microsoft word": "word",
    "msword": "word",
    "ms teams": "teams",
    "microsoft teams": "teams",
    "msteams": "teams",
}


# ==================== INTERNAL SCHEMAS ====================


class DetectedInterface(BaseModel):
    """Represents a target application/interface detected in the process."""

    name: str = Field(..., description="Application or interface name")
    type: str = Field(
        default="desktop",
        description="Type: web|desktop|api|database|file_system|email",
    )
    automation_method: str = Field(
        default="ui_automation",
        description="Method: ui_automation|api_call|file_read_write|email_trigger",
    )
    evidence: str = Field(default="", description="Evidence from the document")
    confidence: float = Field(
        default=0.5, description="Confidence 0.0-1.0 in this detection"
    )

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

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        """Validate type is one of allowed values.

        If invalid, defaults to "desktop" without raising.

        Args:
            v: Type value

        Returns:
            Valid type (or "desktop" default)
        """
        valid_types = {"web", "desktop", "api", "database", "file_system", "email"}
        if v.lower() in valid_types:
            return v.lower()
        return "desktop"

    @field_validator("automation_method")
    @classmethod
    def validate_automation_method(cls, v: str) -> str:
        """Validate automation_method is one of allowed values.

        If invalid, defaults to "ui_automation" without raising.

        Args:
            v: Automation method value

        Returns:
            Valid automation method (or "ui_automation" default)
        """
        valid_methods = {
            "ui_automation",
            "api_call",
            "file_read_write",
            "email_trigger",
        }
        if v.lower() in valid_methods:
            return v.lower()
        return "ui_automation"


class InterfaceDetectionLLMResponse(BaseModel):
    """Response schema for interface detection from LLM."""

    applications: list[DetectedInterface] = Field(
        default_factory=list, description="List of detected interfaces"
    )
    total_count: int = Field(default=0, description="Total count of applications")
    detection_confidence: float = Field(
        default=0.5, description="Overall detection confidence"
    )
    notes: str = Field(default="", description="Additional notes")

    @field_validator("total_count")
    @classmethod
    def sync_count(cls, v: int, info) -> int:
        """Sync total_count with len(applications).

        If mismatch, set total_count = len(applications).

        Args:
            v: Total count value
            info: Validation context

        Returns:
            Synced count
        """
        if hasattr(info, "data") and "applications" in info.data:
            return len(info.data["applications"])
        return v


class InterfaceDetectionResult(BaseModel):
    """Final result of interface detection."""

    interfaces: list[DetectedInterface] = Field(
        ..., description="List of detected interfaces"
    )
    total_count: int = Field(..., description="Total number of interfaces")
    detection_confidence: float = Field(..., description="Overall detection confidence")
    notes: str = Field(default="", description="Additional notes")
    source: str = Field(
        ...,
        description="Source: entity_extractor_only|llm_only|merged|empty",
    )

    def interface_names(self) -> list[str]:
        """Get list of interface names.

        Returns:
            List of interface names
        """
        return [i.name for i in self.interfaces]


# ==================== HELPER FUNCTIONS ====================


def _normalize_app_name(name: str) -> str:
    """Normalize application name for deduplication.

    Converts to lowercase, removes spaces/hyphens/underscores,
    and applies alias mappings.

    Args:
        name: Application name to normalize

    Returns:
        Normalized name
    """
    normalized = name.lower().strip()
    # Check for exact alias matches first
    if normalized in APPLICATION_ALIASES:
        return APPLICATION_ALIASES[normalized]
    # Remove spaces, hyphens, underscores for fuzzy matching
    normalized_fuzzy = re.sub(r"[\s\-_]", "", normalized)
    # Check fuzzy matches against aliases
    if normalized_fuzzy in APPLICATION_ALIASES:
        return APPLICATION_ALIASES[normalized_fuzzy]
    # If no alias, return the space-stripped version
    return normalized


def _deduplicate_interfaces(
    interfaces: list[DetectedInterface],
) -> list[DetectedInterface]:
    """Remove duplicate interfaces from list.

    Two interfaces are duplicates if their names normalize
    to the same value. Keeps entry with higher confidence.

    Args:
        interfaces: List of DetectedInterface objects

    Returns:
        Deduplicated list
    """
    if not interfaces:
        return []

    seen: dict[str, DetectedInterface] = {}

    for interface in interfaces:
        normalized = _normalize_app_name(interface.name)
        if normalized not in seen:
            seen[normalized] = interface
        else:
            # Keep the one with higher confidence
            if interface.confidence > seen[normalized].confidence:
                seen[normalized] = interface

    return list(seen.values())


def _merge_with_entity_results(
    llm_interfaces: list[DetectedInterface],
    entity_apps: list[ApplicationEntity],
) -> list[DetectedInterface]:
    """Merge LLM-detected interfaces with entity extractor results.

    Converts entity_apps to DetectedInterface and merges with llm_interfaces.
    Deduplicates the merged list.

    Args:
        llm_interfaces: Interfaces detected by LLM
        entity_apps: Applications extracted by entity_extractor

    Returns:
        Merged, deduplicated list of DetectedInterface
    """
    # Convert entity apps to DetectedInterface
    converted: list[DetectedInterface] = []
    for app in entity_apps:
        interface = DetectedInterface(
            name=app.name,
            type=app.type if app.type else "desktop",
            automation_method="ui_automation",
            evidence=app.notes if app.notes else "",
            confidence=0.7,  # Default confidence for entity extractor results
        )
        converted.append(interface)

    # Merge
    merged = llm_interfaces + converted

    # Deduplicate
    return _deduplicate_interfaces(merged)


def _filter_relevant_sections(
    sections: list[ExtractedSection],
) -> list[ExtractedSection]:
    """Filter sections most relevant for interface detection.

    Priority order:
    1. section_type == "applications"
    2. section_type == "process_overview"
    3. section_type == "process_steps"
    4. section_type == "general"

    Exclude: "business_rules", "exceptions"
    If no sections: return all sections.

    Args:
        sections: List of ExtractedSection objects

    Returns:
        Filtered list of relevant sections
    """
    if not sections:
        return []

    # Priority 1: applications
    priority_1 = [s for s in sections if s.section_type == "applications"]
    if priority_1:
        return priority_1

    # Priority 2: process_overview
    priority_2 = [s for s in sections if s.section_type == "process_overview"]
    if priority_2:
        return priority_2

    # Priority 3: process_steps
    priority_3 = [s for s in sections if s.section_type == "process_steps"]
    if priority_3:
        return priority_3

    # Priority 4: general
    priority_4 = [s for s in sections if s.section_type == "general"]
    if priority_4:
        return priority_4

    # Fallback: return all sections
    return sections


def _prepare_sections_text(
    sections: list[ExtractedSection], max_chars: int = 4000
) -> str:
    """Format sections for LLM prompt.

    For each section:
      Format as:
      "## {section.title} ({section.section_type})\n{section.content}\n"

    Join all formatted sections.
    If total length > max_chars: truncate to max_chars and
      append "\n[Document truncated for processing]"

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


# ==================== PUBLIC API ====================


def detect_interfaces(
    sections: list[ExtractedSection],
    entity_result=None,
    llm_manager: LLMManager | None = None,
    session_id: str = "",
):
    """Detect target applications/interfaces in a process.

    Combines two strategies:
    1. Results from entity_extractor (already performed)
    2. Fresh LLM analysis of sections
    Merges and deduplicates results.

    Args:
        sections: List of ExtractedSection objects
        entity_result: EntityExtractionResponse from entity_extractor
                       (optional, may be None)
        llm_manager: Optional LLMManager. If None, creates default.
        session_id: Optional session ID for logging

    Returns:
        InterfaceDetectionResult with interfaces, count, and source info
    """
    # STEP 1: Filter sections
    relevant = _filter_relevant_sections(sections)
    logger.debug(f"Analysing interfaces from {len(relevant)} sections")

    # STEP 2: Prepare text
    sections_text = _prepare_sections_text(relevant, max_chars=4000)

    # STEP 3: Get LLM manager
    if llm_manager is None:
        llm_manager = LLMManager.create_default()

    # STEP 4: LLM detection
    llm_interfaces: list[DetectedInterface] = []
    llm_confidence: float = 0.0
    llm_notes: str = ""

    try:
        prompt = INTERFACE_DETECTION_PROMPT.format(sections_text=sections_text)
        response = llm_manager.complete_structured(
            prompt=prompt,
            response_schema=InterfaceDetectionLLMResponse,
            system=INTERFACE_DETECTION_SYSTEM,
            max_tokens=1200,
            session_id=session_id or "interface_detector",
        )
        if isinstance(response, InterfaceDetectionLLMResponse):
            llm_interfaces = response.applications
            llm_confidence = response.detection_confidence
            llm_notes = response.notes
    except LLMProviderError as e:
        logger.warning(f"Interface detection failed on first attempt, retrying: {e}")
        # Retry with simplified prompt
        try:
            truncated = sections_text[:1500]
            retry_prompt = INTERFACE_DETECTION_RETRY_PROMPT.format(
                sections_text_truncated=truncated
            )
            response = llm_manager.complete_structured(
                prompt=retry_prompt,
                response_schema=InterfaceDetectionLLMResponse,
                system=INTERFACE_DETECTION_SYSTEM,
                max_tokens=800,
                session_id=(session_id or "interface_detector") + "_retry",
            )
            if isinstance(response, InterfaceDetectionLLMResponse):
                llm_interfaces = response.applications
                llm_confidence = response.detection_confidence
                llm_notes = response.notes
        except LLMProviderError as e:
            logger.error(f"Interface detection failed after retry: {e}")
            llm_interfaces = []
            llm_confidence = 0.0

    # STEP 5: Merge with entity extractor results
    entity_apps = entity_result.applications if entity_result else []

    if entity_apps and llm_interfaces:
        # Both sources have results
        merged = _merge_with_entity_results(llm_interfaces, entity_apps)
        source = "merged"
    elif entity_apps:
        # Only entity extractor has results
        merged = _merge_with_entity_results([], entity_apps)
        source = "entity_extractor_only"
    elif llm_interfaces:
        # Only LLM has results
        merged = _deduplicate_interfaces(llm_interfaces)
        source = "llm_only"
    else:
        # Neither source has results
        merged = []
        source = "empty"

    # STEP 6: Final deduplication pass
    merged = _deduplicate_interfaces(merged)

    # STEP 7: Calculate final confidence
    if source == "merged":
        entity_confidence = (
            entity_result.confidence.applications
            if entity_result and hasattr(entity_result.confidence, "applications")
            else 0.5
        )
        final_confidence = (llm_confidence + entity_confidence) / 2
    elif source == "llm_only":
        final_confidence = llm_confidence
    elif source == "entity_extractor_only":
        final_confidence = 0.6
    else:
        final_confidence = 0.0

    # STEP 8: Log and return
    logger.info(
        f"[{session_id or 'interface_detector'}] Interfaces detected: "
        f"{len(merged)} applications, source={source}, confidence={final_confidence:.2f}"
    )

    return InterfaceDetectionResult(
        interfaces=merged,
        total_count=len(merged),
        detection_confidence=final_confidence,
        notes=llm_notes,
        source=source,
    )


def get_interface_count(result: InterfaceDetectionResult) -> int:
    """Get count of target applications from detection result.

    Args:
        result: InterfaceDetectionResult from detect_interfaces()

    Returns:
        Number of distinct interfaces (for scoring attribute #4)
    """
    return result.total_count
