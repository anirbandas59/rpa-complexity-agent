"""Entity extractor for Process Design Documents.

Uses LLM-powered named entity recognition to extract entities
relevant to RPA complexity assessment. Extracts applications,
technologies, file types, SAP transaction codes, process triggers,
and business roles.

All prompts defined in tools/document/prompts.py.
All LLM access via llm.manager.LLMManager abstraction.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from pydantic import BaseModel, Field

from config.logging_config import get_logger
from core.constants import RPATool
from core.exceptions import DocumentProcessingError, LLMProviderError
from core.models.document import ExtractedSection
from llm.manager import LLMManager
from tools.document.prompts import (
    ENTITY_EXTRACTION_PROMPT,
    ENTITY_EXTRACTION_RETRY_PROMPT,
    ENTITY_EXTRACTION_SYSTEM,
)

logger = get_logger("entity_extractor")

# Application name aliases for deduplication
APPLICATION_ALIASES: dict[str, str] = {
    "sapecc": "sap",
    "sapec2": "sap",
    "msexcel": "excel",
    "microsoftexcel": "excel",
    "msoutlook": "outlook",
    "microsoftoutlook": "outlook",
    "microsoftteams": "teams",
    "msteams": "teams",
}


# ==================== INTERNAL SCHEMAS ====================


class ApplicationEntity(BaseModel):
    """Represents an application/system in the RPA process."""

    name: str
    type: str = "desktop"
    notes: str = ""


class TechnologyEntity(BaseModel):
    """Represents an additional technology required in the process."""

    name: str
    category: str = "other"
    notes: str = ""


class ProcessTrigger(BaseModel):
    """Represents how the process is triggered."""

    type: str = "manual"
    description: str = ""


class ConfidenceScores(BaseModel):
    """Confidence scores for extracted entities."""

    applications: float = 0.5
    technologies: float = 0.5
    overall: float = 0.5


class EntityExtractionResponse(BaseModel):
    """Response schema for entity extraction from LLM."""

    rpa_tool: str | None = None
    applications: list[ApplicationEntity] = Field(default_factory=list)
    technologies: list[TechnologyEntity] = Field(default_factory=list)
    file_types: list[str] = Field(default_factory=list)
    sap_tcodes: list[str] = Field(default_factory=list)
    process_triggers: list[ProcessTrigger] = Field(default_factory=list)
    roles: list[str] = Field(default_factory=list)
    confidence: ConfidenceScores = Field(default_factory=ConfidenceScores)


# ==================== HELPER FUNCTIONS ====================


def _prepare_sections_text(sections: list[ExtractedSection], max_chars: int = 6000) -> str:
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
    formatted_parts = []

    for section in sections:
        formatted = f"## {section.title} ({section.section_type})\n{section.content}\n"
        formatted_parts.append(formatted)

    full_text = "".join(formatted_parts)

    if len(full_text) > max_chars:
        full_text = full_text[:max_chars]
        full_text += "\n[Document truncated for processing]"

    return full_text


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
    # Remove spaces, hyphens, underscores
    normalized = re.sub(r"[\s\-_]", "", normalized)
    # Apply aliases
    return APPLICATION_ALIASES.get(normalized, normalized)


def _deduplicate_applications(apps: list[ApplicationEntity]) -> list[ApplicationEntity]:
    """Remove duplicate applications from list.

    Two applications are duplicates if their names normalize
    to the same value. Keeps first occurrence.

    Args:
        apps: List of ApplicationEntity objects

    Returns:
        Deduplicated list
    """
    seen_normalized = set()
    result = []

    for app in apps:
        normalized = _normalize_app_name(app.name)
        if normalized not in seen_normalized:
            seen_normalized.add(normalized)
            result.append(app)

    return result


def _validate_rpa_tool(raw_value: str | None) -> RPATool:
    """Map LLM's rpa_tool string to RPATool enum.

    Uses RPATool.from_string() for conversion.
    Returns RPATool.UNKNOWN if raw_value is None or unrecognised.
    Never raises.

    Args:
        raw_value: String value from LLM response

    Returns:
        RPATool enum value (never None)
    """
    if raw_value is None:
        return RPATool.UNKNOWN

    try:
        return RPATool.from_string(raw_value)
    except Exception:  # noqa: BLE001
        logger.debug(f"Failed to map RPA tool '{raw_value}' to enum, using UNKNOWN")
        return RPATool.UNKNOWN


# ==================== PUBLIC API ====================


def extract_entities(
    sections: list[ExtractedSection], llm_manager: LLMManager | None = None
) -> EntityExtractionResponse:
    """Extract named entities from document sections using LLM.

    Uses LLM as primary strategy with retry on failure.
    Returns empty response on complete failure (does not raise).

    Args:
        sections: List of ExtractedSection objects from section_identifier
        llm_manager: Optional LLMManager. If None, creates default instance.

    Returns:
        EntityExtractionResponse with extracted entities.
        Returns empty EntityExtractionResponse if sections is empty
        or LLM extraction fails.
    """
    # STEP 1: Validate input
    if not sections:
        logger.warning("No sections provided for entity extraction")
        return EntityExtractionResponse()

    # STEP 2: Build prompt
    sections_text = _prepare_sections_text(sections)
    prompt = ENTITY_EXTRACTION_PROMPT.format(sections_text=sections_text)

    # STEP 3: Get LLM manager
    if llm_manager is None:
        llm_manager = LLMManager.create_default()

    # STEP 4: First attempt
    result = None
    try:
        result = llm_manager.complete_structured(
            prompt=prompt,
            response_schema=EntityExtractionResponse,
            system=ENTITY_EXTRACTION_SYSTEM,
            max_tokens=1500,
            session_id="entity_extractor",
        )
    except LLMProviderError as e:
        logger.warning(f"Entity extraction failed on first attempt, retrying: {e}")
        # Go to Step 5 (retry)
        pass

    # STEP 5: Retry with simplified prompt if first attempt failed
    if result is None:
        try:
            truncated = sections_text[:2000]
            retry_prompt = ENTITY_EXTRACTION_RETRY_PROMPT.format(
                sections_text_truncated=truncated
            )
            result = llm_manager.complete_structured(
                prompt=retry_prompt,
                response_schema=EntityExtractionResponse,
                system=ENTITY_EXTRACTION_SYSTEM,
                max_tokens=1000,
                session_id="entity_extractor_retry",
            )
        except LLMProviderError as e:
            logger.error(f"Entity extraction failed after retry: {e}")
            return EntityExtractionResponse()

    # STEP 6: Post-process result
    # a) Deduplicate applications
    result.applications = _deduplicate_applications(result.applications)

    # b) Validate and normalize rpa_tool
    detected_tool = _validate_rpa_tool(result.rpa_tool)
    result.rpa_tool = detected_tool.value  # Store string value, not enum

    # c) Normalize file_types
    normalized_file_types = []
    for ft in result.file_types:
        normalized = ft.lower().strip()
        # Remove leading dots and extra whitespace
        normalized = re.sub(r"^\.", "", normalized)
        if normalized:
            normalized_file_types.append(normalized)
    result.file_types = normalized_file_types

    # STEP 7: Log and return
    logger.info(
        f"Entities extracted: {len(result.applications)} applications, "
        f"{len(result.technologies)} technologies, "
        f"rpa_tool={result.rpa_tool}, confidence={result.confidence.overall}"
    )
    return result


def get_application_count(result: EntityExtractionResponse) -> int:
    """Get count of applications from extraction result.

    Args:
        result: EntityExtractionResponse from extract_entities()

    Returns:
        Number of applications (for scoring attribute #4)
    """
    return len(result.applications)


def get_technology_count(result: EntityExtractionResponse) -> int:
    """Get count of additional technologies from extraction result.

    Args:
        result: EntityExtractionResponse from extract_entities()

    Returns:
        Number of technologies (for scoring attribute #5)
    """
    return len(result.technologies)
