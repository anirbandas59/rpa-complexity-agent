"""
Complexity Assessment Agent using LangGraph.

Orchestrates the Phase 5 scoring pipeline, converting raw attribute counts
from the Process Analysis Agent (Phase 4) into a complete AssessmentResult
with deterministic classification and LLM-generated reasoning narratives.

The agent executes two sequential nodes:
1. score_attributes: Convert raw counts to AttributeScore objects
2. classify_complexity: Run classification and generate reasoning

Pure orchestration — all business logic lives in tools.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from config.logging_config import get_logger
from core.constants import RPATool
from core.exceptions import AgentExecutionError, ScoringValidationError
from core.models.assessment import AssessmentResult, AttributeScore
from core.models.document import ExtractedSection, ParsedDocument
from tools.scoring.attribute_scorer import score_attribute
from tools.scoring.classifier_tool import classify_and_explain

logger = get_logger("complexity_assessment_agent")


# ==================== STATE DEFINITION ====================


class ComplexityAssessmentState(TypedDict, total=False):
    """State for Complexity Assessment Agent.

    Carries forward all relevant data from Process Analysis Agent,
    plus Phase 5 scoring results.
    """

    # Inputs from Document Intelligence Agent (Phase 3)
    file_path: str
    session_id: str
    parsed_document: ParsedDocument | None
    sections: list[ExtractedSection]
    entities: Any  # EntityExtractionResponse or None

    # Inputs from Process Analysis Agent (Phase 4)
    raw_attributes: dict[str, int]  # activities, business_rules, layouts, etc.
    detected_rpa_tool: str  # RPATool.value

    # Phase 5 results
    attribute_scores: list[AttributeScore]
    assessment_result: AssessmentResult | None

    # Status
    status: str  # "running" | "success" | "failed"
    warnings: list[str]
    errors: list[str]
    completed_at: str


# ==================== NODE FUNCTIONS ====================


def score_attributes(state: ComplexityAssessmentState) -> dict[str, Any]:
    """Node: Convert raw_attributes to AttributeScore list.

    Maps raw attribute counts from Process Analysis (Phase 4) into a list
    of 5 AttributeScore objects using the deterministic Phase 1 weight matrix.

    Args:
        state: Current complexity assessment state

    Returns:
        Dict with attribute_scores field on success, or error status

    Raises:
        No exceptions raised — failures captured in status/errors
    """
    # Step 1: Skip if already failed
    if state.get("status") == "failed":
        return {}

    session_id = state.get("session_id", "complexity_assessment")
    raw_attributes = state.get("raw_attributes", {})

    # Step 2: Validate raw_attributes
    if not raw_attributes:
        logger.error(f"[{session_id}] No raw attributes provided")
        errors = state.get("errors", [])
        errors.append("No raw attributes from Process Analysis Agent")
        return {"status": "failed", "errors": errors}

    try:
        # Step 3: Parse RPA tool
        rpa_tool_str = state.get("detected_rpa_tool", "unknown")
        try:
            rpa_tool = RPATool.from_string(rpa_tool_str)
        except (ValueError, KeyError):
            rpa_tool = RPATool.UNKNOWN
            logger.debug(f"[{session_id}] Unknown RPA tool: {rpa_tool_str}")

        # Step 4: Determine surface automation flag (conservative approximation)
        has_surface = False
        if raw_attributes.get("technology", 0) > 0 and rpa_tool != RPATool.UNKNOWN:
            has_surface = True
        # TODO: Improve by passing technology_result flags from Phase 4

        # Step 5: Score all 5 attributes
        attribute_scores = []
        for attr_id in range(1, 6):
            # Map raw attribute name to dict key
            attr_key_map = {
                1: "activities",
                2: "business_rules",
                3: "layouts",
                4: "interfaces",
                5: "technology",
            }
            attr_key = attr_key_map.get(attr_id, "")
            raw_value = raw_attributes.get(attr_key, 0)

            # Score this attribute
            score = score_attribute(attr_id, raw_value)
            attribute_scores.append(score)

        logger.info(
            f"[{session_id}] Attributes scored. "
            f"Weights: {[s.weight for s in attribute_scores]}"
        )

        return {"attribute_scores": attribute_scores}

    except ScoringValidationError as e:
        logger.error(f"[{session_id}] Scoring validation failed: {e}")
        errors = state.get("errors", [])
        errors.append(f"Scoring validation failed: {str(e)}")
        return {"status": "failed", "errors": errors}
    except Exception as e:
        logger.error(f"[{session_id}] Unexpected error in score_attributes: {e}")
        errors = state.get("errors", [])
        errors.append(f"Unexpected error: {str(e)}")
        return {"status": "failed", "errors": errors}


def classify_complexity(state: ComplexityAssessmentState) -> dict[str, Any]:
    """Node: Run classification and generate AssessmentResult.

    Orchestrates the Phase 1 deterministic classifier and LLM-based
    reasoning generation into a complete AssessmentResult.

    Args:
        state: Current complexity assessment state

    Returns:
        Dict with assessment_result and status on success

    Raises:
        No exceptions raised — failures captured in status/errors
    """
    # Step 1: Skip if already failed or no attributes
    if state.get("status") == "failed":
        return {}

    attribute_scores = state.get("attribute_scores", [])
    if not attribute_scores:
        logger.warning("Skipping classify_complexity: no attribute_scores")
        return {}

    session_id = state.get("session_id", "complexity_assessment")

    try:
        # Step 2: Parse project name and RPA tool
        file_path = state.get("file_path", "unknown")
        project_name = Path(file_path).stem

        rpa_tool_str = state.get("detected_rpa_tool", "unknown")
        try:
            rpa_tool = RPATool.from_string(rpa_tool_str)
        except (ValueError, KeyError):
            rpa_tool = RPATool.UNKNOWN

        # Step 3: Classify and explain
        result = classify_and_explain(
            attribute_scores=attribute_scores,
            project_name=project_name,
            rpa_tool=rpa_tool,
            session_id=session_id,
        )

        logger.info(
            f"[{session_id}] Classification complete. "
            f"Tier: {result.complexity_tier.value}, "
            f"Score: {result.total_score}, "
            f"Confidence: {result.confidence_score:.2f}"
        )

        return {
            "assessment_result": result,
            "status": "success",
            "completed_at": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"[{session_id}] Classification failed: {e}")
        errors = state.get("errors", [])
        errors.append(f"Classification failed: {str(e)}")
        return {"status": "failed", "errors": errors}


# ==================== GRAPH CONSTRUCTION ====================


def _build_graph() -> StateGraph:
    """Build the LangGraph state machine.

    Returns:
        Compiled StateGraph for complexity assessment
    """
    graph = StateGraph(ComplexityAssessmentState)

    # Add nodes
    graph.add_node("score_attributes", score_attributes)
    graph.add_node("classify_complexity", classify_complexity)

    # Set entry point and edges
    graph.set_entry_point("score_attributes")
    graph.add_edge("score_attributes", "classify_complexity")
    graph.add_edge("classify_complexity", END)

    return graph.compile()


_graph = _build_graph()


# ==================== PUBLIC FUNCTION ====================


def run(
    process_analysis_state: dict,
    session_id: str | None = None,
) -> ComplexityAssessmentState:
    """Execute the Complexity Assessment Agent.

    Accepts ProcessAnalysisState from Phase 4 and produces a complete
    ComplexityAssessmentState with AssessmentResult.

    Args:
        process_analysis_state: Dict with Process Analysis results
        session_id: Optional session identifier; if None, inherited from input

    Returns:
        ComplexityAssessmentState with assessment_result populated

    Raises:
        AgentExecutionError: If graph execution fails
    """
    # Build initial state
    initial_state: ComplexityAssessmentState = {
        # Inherit from process_analysis_state
        "file_path": process_analysis_state.get("file_path", ""),
        "session_id": session_id or process_analysis_state.get("session_id", ""),
        "parsed_document": process_analysis_state.get("parsed_document"),
        "sections": process_analysis_state.get("sections", []),
        "entities": process_analysis_state.get("entities"),
        "raw_attributes": process_analysis_state.get("raw_attributes", {}),
        "detected_rpa_tool": process_analysis_state.get("detected_rpa_tool", ""),
        # Initialize Phase 5 state
        "attribute_scores": [],
        "assessment_result": None,
        "status": "running",
        "warnings": process_analysis_state.get("warnings", []),
        "errors": process_analysis_state.get("errors", []),
        "completed_at": "",
    }

    try:
        # Execute graph
        final_state = _graph.invoke(initial_state)
        return final_state
    except Exception as e:
        logger.error(f"Complexity Assessment Agent execution failed: {e}")
        raise AgentExecutionError(
            "Complexity Assessment Agent failed",
            context={"error": str(e)},
        ) from e
