"""RPA tool detector for Process Design Documents.

Pure pattern matching (no LLM) that scans document text for explicit
mentions of RPA platform names and returns the detected tool with
confidence based on mention frequency.

All RPA platform reference patterns defined locally.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator

from config.logging_config import get_logger
from core.constants import RPATool
from core.models.document import ParsedDocument

logger = get_logger("rpa_tool_detector")

# ==================== TOOL PATTERNS ====================

TOOL_PATTERNS: dict[str, list[str]] = {
    "BLUE_PRISM": [
        "blue prism",
        "blueprism",
        "blue-prism",
        "bp object",
        "bp process",
        "blue prism object",
        "blue prism process",
        "application modeller",
        "blue prism studio",
        "bp studio",
    ],
    "UIPATH": [
        "uipath",
        "ui path",
        "ui-path",
        "uipath studio",
        "orchestrator",
        "uipath robot",
        "re framework",
        "robotic enterprise",
    ],
    "POWER_AUTOMATE": [
        "power automate",
        "powerautomate",
        "power-automate",
        "pa desktop",
        "power automate desktop",
        "microsoft power automate",
        "ms power automate",
        "power platform",
    ],
    "AA360": [
        "automation anywhere",
        "a360",
        "aa360",
        "automation 360",
        "aari",
        "iqbot",
        "aa enterprise",
        "bot creator",
        "bot runner",
    ],
}

# ==================== SCHEMAS ====================


class RPAToolDetectionResult(BaseModel):
    """Result of RPA tool detection."""

    detected_tool: RPATool = Field(..., description="Detected RPA tool")
    confidence: float = Field(
        default=0.0, description="Confidence 0.0-1.0 in the detection"
    )
    mention_count: int = Field(default=0, description="Number of mentions of the tool")
    evidence: list[str] = Field(
        default_factory=list, description="Text snippets confirming detection"
    )
    detection_method: str = Field(
        default="not_found",
        description="Method: explicit_mention|alias_match|not_found",
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

    def is_known(self) -> bool:
        """Check if detected tool is known (not UNKNOWN).

        Returns:
            True if detected_tool != RPATool.UNKNOWN
        """
        return self.detected_tool != RPATool.UNKNOWN


# ==================== HELPER FUNCTIONS ====================


def _scan_text_for_tool(text: str, tool_key: str) -> tuple[int, list[str]]:
    """Scan text for patterns of a given RPA tool.

    Searches for all patterns of the tool and returns mention count
    and evidence snippets with context window (60 chars total:
    30 before, 30 after).

    Args:
        text: Lowercased text to search
        tool_key: Tool key in TOOL_PATTERNS (e.g., "BLUE_PRISM")

    Returns:
        Tuple of (mention_count, evidence_snippets)
    """
    if tool_key not in TOOL_PATTERNS:
        return 0, []

    patterns = TOOL_PATTERNS[tool_key]
    mention_count = 0
    evidence_snippets_raw = []

    for pattern in patterns:
        # Find all occurrences of the pattern (case-insensitive already due to lowercased text)
        for match in re.finditer(re.escape(pattern), text):
            mention_count += 1
            start = match.start()
            end = match.end()

            # Extract context: 30 chars before, 30 after
            context_start = max(0, start - 30)
            context_end = min(len(text), end + 30)
            context = text[context_start:context_end].strip()

            evidence_snippets_raw.append(context)

    # Deduplicate and limit to 3 evidence snippets
    evidence_snippets = []
    seen = set()
    for snippet in evidence_snippets_raw:
        if snippet not in seen:
            evidence_snippets.append(snippet)
            seen.add(snippet)
            if len(evidence_snippets) >= 3:
                break

    return mention_count, evidence_snippets


# ==================== PUBLIC API ====================


def detect_rpa_tool(
    document: ParsedDocument, entity_result=None
) -> RPAToolDetectionResult:
    """Detect RPA tool from document text using pattern matching.

    Pure pattern matching — no LLM calls. Scans document text and
    optionally incorporates entity extractor results.

    Args:
        document: ParsedDocument with full_text
        entity_result: EntityExtractionResponse with optional rpa_tool field

    Returns:
        RPAToolDetectionResult with detected tool and confidence
    """
    # STEP 1: Build search corpus
    corpus = document.full_text.lower()
    if entity_result and hasattr(entity_result, "rpa_tool") and entity_result.rpa_tool:
        corpus += " " + entity_result.rpa_tool.lower()

    # STEP 2: Scan for all tools
    results: dict[str, tuple[int, list[str]]] = {}
    for tool_key in TOOL_PATTERNS:
        count, evidence = _scan_text_for_tool(corpus, tool_key)
        results[tool_key] = (count, evidence)

    # STEP 3: Check entity_result shortcut
    entity_tool_boost = None
    if entity_result and hasattr(entity_result, "rpa_tool") and entity_result.rpa_tool:
        entity_tool = RPATool.from_string(entity_result.rpa_tool)
        if entity_tool != RPATool.UNKNOWN:
            entity_tool_boost = entity_tool.name
            current_count, current_evidence = results.get(entity_tool.name, (0, []))
            results[entity_tool.name] = (current_count + 3, current_evidence)

    # STEP 4: Find winner
    max_count = max([count for count, _ in results.values()], default=0)
    if max_count == 0:
        logger.debug("No RPA tool mentions found in document")
        return RPAToolDetectionResult(
            detected_tool=RPATool.UNKNOWN,
            confidence=0.0,
            mention_count=0,
            evidence=[],
            detection_method="not_found",
        )

    winner_key = max(results.keys(), key=lambda k: results[k][0])
    winner_count, evidence_snippets = results[winner_key]

    # STEP 5: Calculate confidence
    total_count = sum([count for count, _ in results.values()])
    if total_count == 0:
        confidence = 0.0
    else:
        confidence = min(1.0, winner_count / total_count)

    # Apply confidence bonuses/adjustments
    if winner_count >= 5:
        confidence = min(1.0, confidence + 0.1)
    if winner_count == 1:
        confidence = min(confidence, 0.4)

    # STEP 6: Determine detection_method
    if entity_tool_boost and entity_tool_boost == winner_key:
        detection_method = "explicit_mention"
    elif winner_count > 0:
        detection_method = "alias_match"
    else:
        detection_method = "not_found"

    # STEP 7: Map winner to RPATool enum
    rpa_tool = RPATool[winner_key]

    # STEP 8: Log and return
    logger.info(
        f"RPA tool detected: {rpa_tool} (confidence={confidence:.2f}, mentions={winner_count})"
    )

    return RPAToolDetectionResult(
        detected_tool=rpa_tool,
        confidence=confidence,
        mention_count=winner_count,
        evidence=evidence_snippets[:3],
        detection_method=detection_method,
    )


def get_rpa_tool(result: RPAToolDetectionResult) -> RPATool:
    """Get RPA tool from detection result.

    Convenience function for clean access.

    Args:
        result: RPAToolDetectionResult from detect_rpa_tool()

    Returns:
        Detected RPATool
    """
    return result.detected_tool
