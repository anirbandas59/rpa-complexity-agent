"""Process Analysis Agent using LangGraph.

Orchestrates all five analysis tools (activity, interface, rules, layouts,
technology) plus RPA tool detection. Compiles raw attribute counts for
Phase 5 scoring engine.

The agent executes all tools independently — failures in one tool do not
block others. Final status reflects overall analysis quality.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from config.logging_config import get_logger
from core.constants import RPATool
from core.exceptions import AgentExecutionError
from core.models.document import ExtractedSection, ParsedDocument
from tools.analysis.activity_analyzer import analyze_activities
from tools.analysis.interface_detector import detect_interfaces
from tools.analysis.layout_identifier import identify_layouts
from tools.analysis.rpa_tool_detector import detect_rpa_tool
from tools.analysis.rule_extractor import extract_business_rules
from tools.analysis.technology_detector import detect_technology

logger = get_logger("process_analysis_agent")


# ==================== STATE DEFINITION ====================


class ProcessAnalysisState(TypedDict, total=False):
    """State for Process Analysis Agent."""

    # Inputs (from Document Intelligence)
    file_path: str
    session_id: str
    parsed_document: ParsedDocument | None
    sections: list[ExtractedSection]
    entities: Any  # EntityExtractionResponse or None

    # Analysis results
    activity_result: Any  # ActivityAnalysisResult
    interface_result: Any  # InterfaceDetectionResult
    rule_result: Any  # BusinessRuleExtractionResult
    layout_result: Any  # LayoutIdentificationResult
    technology_result: Any  # TechnologyDetectionResult
    rpa_tool_result: Any  # RPAToolDetectionResult

    # Compiled attributes
    raw_attributes: dict[
        str, int
    ]  # activities, business_rules, layouts, interfaces, technology
    detected_rpa_tool: str  # RPATool.value

    # Status
    status: str  # "success" | "partial" | "failed"
    warnings: list[str]
    errors: list[str]
    completed_at: str


# ==================== NODE FUNCTIONS ====================


def run_activity_analysis(state: ProcessAnalysisState) -> dict[str, Any]:
    """Run activity analysis.

    Args:
        state: Current process analysis state

    Returns:
        Dict with activity_result field
    """
    if state.get("status") == "failed":
        return {}

    try:
        result = analyze_activities(
            sections=state["sections"],
            session_id=state.get("session_id", "process_analysis"),
        )
        logger.info(f"[{state.get('session_id')}] Activity analysis completed")
        return {"activity_result": result}
    except Exception as e:
        logger.warning(f"Activity analysis failed: {e}")
        warnings = state.get("warnings", [])
        warnings.append(f"Activity analysis failed: {str(e)}")
        return {"activity_result": None, "warnings": warnings}


def run_interface_detection(state: ProcessAnalysisState) -> dict[str, Any]:
    """Run interface detection.

    Args:
        state: Current process analysis state

    Returns:
        Dict with interface_result field
    """
    if state.get("status") == "failed":
        return {}

    try:
        result = detect_interfaces(
            sections=state["sections"],
            entity_result=state.get("entities"),
            session_id=state.get("session_id", "process_analysis"),
        )
        logger.info(f"[{state.get('session_id')}] Interface detection completed")
        return {"interface_result": result}
    except Exception as e:
        logger.warning(f"Interface detection failed: {e}")
        warnings = state.get("warnings", [])
        warnings.append(f"Interface detection failed: {str(e)}")
        return {"interface_result": None, "warnings": warnings}


def run_rule_extraction(state: ProcessAnalysisState) -> dict[str, Any]:
    """Run business rule extraction.

    Args:
        state: Current process analysis state

    Returns:
        Dict with rule_result field
    """
    if state.get("status") == "failed":
        return {}

    try:
        result = extract_business_rules(
            sections=state["sections"],
            session_id=state.get("session_id", "process_analysis"),
        )
        logger.info(f"[{state.get('session_id')}] Business rule extraction completed")
        return {"rule_result": result}
    except Exception as e:
        logger.warning(f"Business rule extraction failed: {e}")
        warnings = state.get("warnings", [])
        warnings.append(f"Business rule extraction failed: {str(e)}")
        return {"rule_result": None, "warnings": warnings}


def run_layout_identification(state: ProcessAnalysisState) -> dict[str, Any]:
    """Run layout identification.

    Args:
        state: Current process analysis state

    Returns:
        Dict with layout_result field
    """
    if state.get("status") == "failed":
        return {}

    try:
        result = identify_layouts(
            sections=state["sections"],
            session_id=state.get("session_id", "process_analysis"),
        )
        logger.info(f"[{state.get('session_id')}] Layout identification completed")
        return {"layout_result": result}
    except Exception as e:
        logger.warning(f"Layout identification failed: {e}")
        warnings = state.get("warnings", [])
        warnings.append(f"Layout identification failed: {str(e)}")
        return {"layout_result": None, "warnings": warnings}


def run_technology_detection(state: ProcessAnalysisState) -> dict[str, Any]:
    """Run technology detection.

    Args:
        state: Current process analysis state

    Returns:
        Dict with technology_result field
    """
    if state.get("status") == "failed":
        return {}

    try:
        result = detect_technology(
            sections=state["sections"],
            entity_result=state.get("entities"),
            session_id=state.get("session_id", "process_analysis"),
        )
        logger.info(f"[{state.get('session_id')}] Technology detection completed")
        return {"technology_result": result}
    except Exception as e:
        logger.warning(f"Technology detection failed: {e}")
        warnings = state.get("warnings", [])
        warnings.append(f"Technology detection failed: {str(e)}")
        return {"technology_result": None, "warnings": warnings}


def run_rpa_tool_detection(state: ProcessAnalysisState) -> dict[str, Any]:
    """Run RPA tool detection (pure pattern matching).

    Args:
        state: Current process analysis state

    Returns:
        Dict with rpa_tool_result field
    """
    if state.get("status") == "failed":
        return {}

    try:
        result = detect_rpa_tool(
            document=state["parsed_document"],
            entity_result=state.get("entities"),
        )
        logger.info(f"[{state.get('session_id')}] RPA tool detection completed")
        return {"rpa_tool_result": result}
    except Exception as e:
        logger.warning(f"RPA tool detection failed: {e}")
        warnings = state.get("warnings", [])
        warnings.append(f"RPA tool detection failed: {str(e)}")
        return {"rpa_tool_result": None, "warnings": warnings}


def compile_attributes(state: ProcessAnalysisState) -> dict[str, Any]:
    """Compile all analysis results into raw attribute counts.

    Assembles the final raw_attributes dict that Phase 5 scoring
    engine will consume. Also determines overall status.

    Args:
        state: Current process analysis state

    Returns:
        Dict with raw_attributes, detected_rpa_tool, status, warnings, completed_at
    """
    # Safely extract counts
    activity_result = state.get("activity_result")
    interface_result = state.get("interface_result")
    rule_result = state.get("rule_result")
    layout_result = state.get("layout_result")
    technology_result = state.get("technology_result")
    rpa_tool_result = state.get("rpa_tool_result")

    activities = 0
    if activity_result and hasattr(activity_result, "raw_activity_count"):
        activities = activity_result.raw_activity_count or 0

    business_rules = 0
    if rule_result and hasattr(rule_result, "total_qualifying_count"):
        business_rules = rule_result.total_qualifying_count or 0

    layouts = 0
    if layout_result and hasattr(layout_result, "total_count"):
        layouts = layout_result.total_count or 0

    interfaces = 0
    if interface_result and hasattr(interface_result, "total_count"):
        interfaces = interface_result.total_count or 0

    technology = 0
    if technology_result and hasattr(technology_result, "total_count"):
        technology = technology_result.total_count or 0

    # Build raw_attributes
    raw_attributes = {
        "activities": activities,
        "business_rules": business_rules,
        "layouts": layouts,
        "interfaces": interfaces,
        "technology": technology,
    }

    # Determine detected_rpa_tool
    detected_rpa_tool = RPATool.UNKNOWN.value
    if rpa_tool_result and hasattr(rpa_tool_result, "is_known"):
        if rpa_tool_result.is_known():
            detected_rpa_tool = rpa_tool_result.detected_tool.value

    # Determine status
    warnings = state.get("warnings", []).copy()
    if state.get("parsed_document") is None:
        status = "failed"
    else:
        status = "success"
        # Check for partial results (zero count with low confidence)
        if (
            activities == 0
            and activity_result
            and hasattr(activity_result, "count_confidence")
        ):
            try:
                if float(activity_result.count_confidence) < 0.3:
                    status = "partial"
            except (TypeError, ValueError):
                pass
        if (
            layouts == 0
            and layout_result
            and hasattr(layout_result, "detection_confidence")
        ):
            try:
                if float(layout_result.detection_confidence) < 0.3:
                    status = "partial"
            except (TypeError, ValueError):
                pass

    # Collect warnings
    if layout_result and hasattr(layout_result, "exceeds_ceiling"):
        if layout_result.exceeds_ceiling:
            warnings.append("Layout count exceeds XL ceiling (>10)")

    if activity_result and hasattr(activity_result, "count_confidence"):
        try:
            if float(activity_result.count_confidence) < 0.4:
                warnings.append("Activity count confidence is low (<0.4)")
        except (TypeError, ValueError):
            pass

    if interface_result and hasattr(interface_result, "total_count"):
        if interface_result.total_count == 0:
            warnings.append(
                "No interfaces detected — verify document contains application references"
            )

    # Log
    logger.info(
        f"[{state.get('session_id')}] Attributes compiled: "
        f"activities={activities}, rules={business_rules}, "
        f"layouts={layouts}, interfaces={interfaces}, "
        f"technology={technology}, rpa_tool={detected_rpa_tool}"
    )

    return {
        "raw_attributes": raw_attributes,
        "detected_rpa_tool": detected_rpa_tool,
        "status": status,
        "warnings": warnings,
        "completed_at": datetime.utcnow().isoformat(),
    }


# ==================== GRAPH CONSTRUCTION ====================


def _build_graph() -> StateGraph:
    """Build the Process Analysis StateGraph.

    All 7 nodes run sequentially with no conditional edges except
    initial document validation.

    Returns:
        Compiled StateGraph
    """
    graph = StateGraph(ProcessAnalysisState)

    # Add nodes
    graph.add_node("run_activity_analysis", run_activity_analysis)
    graph.add_node("run_interface_detection", run_interface_detection)
    graph.add_node("run_rule_extraction", run_rule_extraction)
    graph.add_node("run_layout_identification", run_layout_identification)
    graph.add_node("run_technology_detection", run_technology_detection)
    graph.add_node("run_rpa_tool_detection", run_rpa_tool_detection)
    graph.add_node("compile_attributes", compile_attributes)

    # Define entry condition: check if parsed_document is None
    def check_document(state: ProcessAnalysisState) -> str:
        """Route based on document availability."""
        if state.get("parsed_document") is None:
            return "compile_attributes"  # Skip to final node if no document
        return "run_activity_analysis"

    graph.set_conditional_entry_point(
        check_document,
        {
            "compile_attributes": "compile_attributes",
            "run_activity_analysis": "run_activity_analysis",
        },
    )

    # Linear flow: all 5 analysis nodes -> rpa tool detection -> compile -> end
    graph.add_edge("run_activity_analysis", "run_interface_detection")
    graph.add_edge("run_interface_detection", "run_rule_extraction")
    graph.add_edge("run_rule_extraction", "run_layout_identification")
    graph.add_edge("run_layout_identification", "run_technology_detection")
    graph.add_edge("run_technology_detection", "run_rpa_tool_detection")
    graph.add_edge("run_rpa_tool_detection", "compile_attributes")
    graph.add_edge("compile_attributes", END)

    return graph.compile()


_graph = _build_graph()


# ==================== PUBLIC API ====================


def run(document_state: dict, session_id: str | None = None) -> ProcessAnalysisState:
    """Run Process Analysis Agent.

    Accepts output from Document Intelligence Agent and orchestrates
    all analysis tools. Returns final state with compiled attributes
    ready for Phase 5 scoring.

    Args:
        document_state: Output dict from Document Intelligence Agent
        session_id: Optional session ID; uses document_state value if not provided

    Returns:
        ProcessAnalysisState with all analysis results and raw attributes

    Raises:
        AgentExecutionError: If execution fails critically
    """
    # Determine session_id
    if session_id is None:
        session_id = document_state.get("session_id", "process_analysis")

    # Build initial state
    initial_state: ProcessAnalysisState = {
        "file_path": document_state.get("file_path", ""),
        "session_id": session_id,
        "parsed_document": document_state.get("parsed_document"),
        "sections": document_state.get("sections", []),
        "entities": document_state.get("entities"),
        "activity_result": None,
        "interface_result": None,
        "rule_result": None,
        "layout_result": None,
        "technology_result": None,
        "rpa_tool_result": None,
        "raw_attributes": {},
        "detected_rpa_tool": RPATool.UNKNOWN.value,
        "status": "running",
        "warnings": document_state.get("warnings", []),
        "errors": document_state.get("errors", []),
        "completed_at": "",
    }

    try:
        logger.info(f"[{session_id}] Starting Process Analysis Agent")
        result = _graph.invoke(initial_state)
        logger.info(
            f"[{session_id}] Process Analysis Agent completed with status={result.get('status')}"
        )
        return result
    except Exception as e:
        logger.error(f"[{session_id}] Process Analysis Agent failed: {e}")
        raise AgentExecutionError(
            f"Process Analysis Agent failed: {str(e)}",
            context={"session_id": session_id},
        )
