"""Orchestrator Agent — Phase 7 capstone component.

Wires all four agents into a single end-to-end workflow:
  1. Document Intelligence → Parse document
  2. Process Analysis → Analyze process elements
  3. Complexity Assessment → Score and classify
  4. Effort & Decomposition → Estimate effort
  5. Generate Outputs → Create Excel and PDF reports

State flows linearly through these 5 stages with checkpointing
after each stage for debugging and recovery.

The orchestrator NEVER calls tools directly — only agent run()
functions and output generation tools (which are not agents).

Exposed API:
  _graph: Compiled LangGraph StateGraph (5-node pipeline)
  run_assessment(): Single public entry point (see agents/__init__.py)
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional, TypedDict

from langgraph.graph import END, StateGraph

from agents.complexity_assessment.agent import run as ca_run
from agents.document_intelligence.agent import run as di_run
from agents.process_analysis.agent import run as pa_run
from config.logging_config import get_logger
from core.exceptions import AgentExecutionError, OutputGenerationError
from core.models.assessment import AssessmentResult
from core.models.document import ExtractedSection
from core.models.timeline import DeliveryTimeline
from tools.analysis.rule_extractor import BusinessRuleExtractionResult
from tools.output.excel_generator import generate_excel_report
from tools.output.pdf_reporter import generate_pdf_report
from tools.output.step_decomposer import (
    StepDecompositionResult,
    decompose_steps,
)
from tools.output.timeline_builder import build_timeline

logger = get_logger("orchestrator")


# ==================== PIPELINE STATE =====================


class PipelineState(TypedDict):
    """State dict flowing through the 5-stage orchestrator pipeline.

    Inputs from user/API:
      file_path: Absolute path to PDD document (PDF or DOCX)
      session_id: Unique identifier for this pipeline execution
      rpa_tool_override: User-specified RPA tool ("unknown" if not set)
      project_name: User-provided project name
      start_date: ISO date string "YYYY-MM-DD"
      developer_name: Assigned developer
      business_analyst: Assigned BA
      squad: Team/squad name

    Agent outputs (populated progressively):
      di_state: Output from Document Intelligence Agent
      pa_state: Output from Process Analysis Agent
      ca_state: Output from Complexity Assessment Agent

    Generation outputs:
      decomposition: StepDecompositionResult summary
      timeline: DeliveryTimeline summary
      excel_path: Path to generated Excel report
      pdf_path: Path to generated PDF report

    Object references (for stage 4→5 transition):
      _assessment_result_obj: AssessmentResult object
      _decomposition_obj: StepDecompositionResult object
      _timeline_obj: DeliveryTimeline object

    Pipeline status:
      status: "running" | "success" | "partial" | "failed"
      current_stage: Human-readable stage name
      warnings: Accumulated warning messages
      errors: Accumulated error messages
      completed_at: ISO timestamp when pipeline finished
    """

    # Inputs
    file_path: str
    session_id: str
    rpa_tool_override: str
    project_name: str
    start_date: str
    developer_name: str
    business_analyst: str
    squad: str

    # Agent outputs
    di_state: dict[str, Any]
    pa_state: dict[str, Any]
    ca_state: dict[str, Any]

    # Generation outputs
    decomposition: dict[str, Any]
    timeline: dict[str, Any]
    excel_path: str
    pdf_path: str

    # Object references (preserved through graph execution)
    _assessment_result_obj: Optional[Any]
    _decomposition_obj: Optional[Any]
    _timeline_obj: Optional[Any]

    # Pipeline status
    status: str
    current_stage: str
    warnings: list[str]
    errors: list[str]
    completed_at: str


# ==================== CHECKPOINT HELPER ====================


def _save_checkpoint(state: PipelineState, stage: str) -> None:
    """Save pipeline state to disk for recovery/debugging.

    Creates data/temp/{session_id}_checkpoint.json with serializable fields.
    Non-serializable objects are skipped. Failures are logged but never raised.

    Args:
        state: Current pipeline state
        stage: Stage name for logging

    Note:
        This is non-critical — failures are logged only and do not crash
        the pipeline.
    """
    try:
        # Create temp directory if needed
        temp_dir = Path("data/temp")
        temp_dir.mkdir(parents=True, exist_ok=True)

        # Extract serializable fields only
        checkpoint = {
            "session_id": state["session_id"],
            "file_path": state["file_path"],
            "status": state["status"],
            "current_stage": state["current_stage"],
            "stage": stage,
            "warnings": state["warnings"],
            "errors": state["errors"],
            "completed_at": state["completed_at"],
            "timestamp": datetime.utcnow().isoformat(),
        }

        checkpoint_path = temp_dir / f"{state['session_id']}_checkpoint.json"
        with open(checkpoint_path, "w") as f:
            json.dump(checkpoint, f, indent=2)

        logger.debug(f"[{state['session_id']}] Checkpoint saved: {checkpoint_path}")

    except Exception as e:
        # Never raise from checkpoint — log and continue
        logger.warning(
            f"[{state.get('session_id', 'unknown')}] "
            f"Checkpoint save failed (non-critical): {e}"
        )


# ==================== NODE FUNCTIONS ====================


def stage_document_intelligence(state: PipelineState) -> dict[str, Any]:
    """Stage 1/5: Document Intelligence Agent.

    Parses the PDD document and extracts sections and entities.

    Args:
        state: Current pipeline state

    Returns:
        Dict with di_state and warnings/errors
    """
    session_id = state["session_id"]
    logger.info(f"[{session_id}] Stage 1/5: Document Intelligence")

    # Update current stage
    state["current_stage"] = "document_intelligence"

    try:
        # Call Document Intelligence Agent
        di_state = di_run(file_path=state["file_path"], session_id=session_id)

        # Check for failure
        if di_state.get("status") == "failed":
            logger.warning(f"[{session_id}] Document Intelligence failed")
            return {
                "status": "failed",
                "errors": state["errors"] + di_state.get("errors", []),
                "current_stage": "document_intelligence",
            }

        # Save checkpoint
        _save_checkpoint(state, "document_intelligence")

        # Return accumulated state
        return {
            "di_state": dict(di_state),
            "current_stage": "document_intelligence",
            "warnings": state["warnings"] + di_state.get("warnings", []),
        }

    except Exception as e:
        logger.error(f"[{session_id}] Document Intelligence error: {e}")
        return {
            "status": "failed",
            "errors": state["errors"] + [f"Document Intelligence: {str(e)}"],
            "current_stage": "document_intelligence",
        }


def stage_process_analysis(state: PipelineState) -> dict[str, Any]:
    """Stage 2/5: Process Analysis Agent.

    Analyzes activities, interfaces, business rules, layouts, and technology.

    Args:
        state: Current pipeline state

    Returns:
        Dict with pa_state and warnings/errors
    """
    session_id = state["session_id"]

    # Skip if previous stage failed
    if state.get("status") == "failed":
        return {}

    logger.info(f"[{session_id}] Stage 2/5: Process Analysis")
    state["current_stage"] = "process_analysis"

    try:
        # Call Process Analysis Agent
        pa_state = pa_run(
            document_state=state["di_state"], session_id=session_id
        )

        # Apply RPA tool override if specified
        if state["rpa_tool_override"] != "unknown":
            pa_state["detected_rpa_tool"] = state["rpa_tool_override"]
            logger.info(
                f"[{session_id}] RPA tool override applied: "
                f"{state['rpa_tool_override']}"
            )

        # Save checkpoint
        _save_checkpoint(state, "process_analysis")

        # Return accumulated state
        return {
            "pa_state": dict(pa_state),
            "current_stage": "process_analysis",
            "warnings": state["warnings"] + pa_state.get("warnings", []),
        }

    except Exception as e:
        logger.error(f"[{session_id}] Process Analysis error: {e}")
        return {
            "status": "failed",
            "errors": state["errors"] + [f"Process Analysis: {str(e)}"],
            "current_stage": "process_analysis",
        }


def stage_complexity_assessment(state: PipelineState) -> dict[str, Any]:
    """Stage 3/5: Complexity Assessment Agent.

    Scores attributes and classifies complexity tier.

    Args:
        state: Current pipeline state

    Returns:
        Dict with ca_state and warnings/errors
    """
    session_id = state["session_id"]

    # Skip if previous stage failed
    if state.get("status") == "failed":
        return {}

    logger.info(f"[{session_id}] Stage 3/5: Complexity Assessment")
    state["current_stage"] = "complexity_assessment"

    try:
        # Call Complexity Assessment Agent
        ca_state = ca_run(
            process_analysis_state=state["pa_state"], session_id=session_id
        )

        # Save checkpoint
        _save_checkpoint(state, "complexity_assessment")

        # Return accumulated state
        return {
            "ca_state": dict(ca_state),
            "current_stage": "complexity_assessment",
            "warnings": state["warnings"] + ca_state.get("warnings", []),
        }

    except Exception as e:
        logger.error(f"[{session_id}] Complexity Assessment error: {e}")
        return {
            "status": "failed",
            "errors": state["errors"] + [f"Complexity Assessment: {str(e)}"],
            "current_stage": "complexity_assessment",
        }


def stage_effort_and_decomposition(state: PipelineState) -> dict[str, Any]:
    """Stage 4/5: Effort Estimation and Step Decomposition.

    Decomposes process into steps, builds delivery timeline.

    Args:
        state: Current pipeline state

    Returns:
        Dict with decomposition, timeline, and object references for next stage
    """
    session_id = state["session_id"]

    # Skip if previous stage failed
    if state.get("status") == "failed":
        return {}

    logger.info(f"[{session_id}] Stage 4/5: Effort Estimation")
    state["current_stage"] = "effort_estimation"

    try:
        # Extract assessment result
        ca_state = state.get("ca_state", {})
        assessment_result: Optional[AssessmentResult] = ca_state.get(
            "assessment_result"
        )
        if assessment_result is None:
            raise AgentExecutionError(
                message="Assessment result not found in CA state",
                context={"stage": "effort_estimation"},
            )

        # Override project_name if user provided one
        if state["project_name"]:
            assessment_result.project_name = state["project_name"]

        # Get sections from DI state
        di_state = state.get("di_state", {})
        sections: list[ExtractedSection] = di_state.get("sections", [])

        # Get rule result from PA state
        pa_state = state.get("pa_state", {})
        rule_result_raw = pa_state.get("rule_result")
        rule_result: Optional[BusinessRuleExtractionResult] = None
        if rule_result_raw is not None:
            try:
                if isinstance(rule_result_raw, dict):
                    rule_result = BusinessRuleExtractionResult(**rule_result_raw)
                elif isinstance(rule_result_raw, BusinessRuleExtractionResult):
                    rule_result = rule_result_raw
            except Exception as e:
                logger.warning(f"[{session_id}] Failed to deserialize rule_result: {e}")

        # Call step decomposition tool
        decomposition: StepDecompositionResult = decompose_steps(
            sections=sections,
            assessment_result=assessment_result,
            rule_result=rule_result,
            session_id=session_id,
        )

        # Parse start date
        try:
            start_date = date.fromisoformat(state["start_date"])
        except Exception:
            start_date = date.today()
            logger.warning(
                f"[{session_id}] Invalid start_date, using today: {start_date}"
            )

        # Build timeline
        timeline: DeliveryTimeline = build_timeline(
            decomposition=decomposition,
            assessment_result=assessment_result,
            start_date=start_date,
            developer_name=state["developer_name"] or "TBD",
            business_analyst=state["business_analyst"] or "TBD",
            squad=state["squad"] or "RPA Team",
        )

        # Save checkpoint
        _save_checkpoint(state, "effort_estimation")

        # Return state with both serializable summaries and object references
        # (for next node to use)
        return {
            "decomposition": {
                "total_step_count": decomposition.total_step_count,
                "total_weighted_steps": decomposition.total_weighted_steps,
                "branch_count": len(decomposition.branches),
            },
            "timeline": {
                "total_hours": timeline.total_hours,  # total_hours is a computed field (property)
                "total_sp": timeline.total_sp,  # total_sp is a computed field (property)
                "feature_count": len(timeline.features),
            },
            "_decomposition_obj": decomposition,  # Keep for next node
            "_timeline_obj": timeline,  # Keep for next node
            "_assessment_result_obj": assessment_result,  # Keep for next node
            "current_stage": "effort_estimation",
        }

    except Exception as e:
        logger.error(f"[{session_id}] Effort estimation error: {e}")
        return {
            "status": "failed",
            "errors": state["errors"] + [f"Effort estimation: {str(e)}"],
            "current_stage": "effort_estimation",
        }


def stage_generate_outputs(state: PipelineState) -> dict[str, Any]:
    """Stage 5/5: Generate Excel and PDF reports.

    Args:
        state: Current pipeline state (with _*_obj references from stage 4)

    Returns:
        Dict with excel_path, pdf_path, final status
    """
    session_id = state["session_id"]

    # Skip if previous stage failed
    if state.get("status") == "failed":
        return {}

    logger.info(f"[{session_id}] Stage 5/5: Generating Outputs")
    state["current_stage"] = "generate_outputs"

    try:
        # Retrieve objects from state
        assessment_result: Optional[AssessmentResult] = state.get(
            "_assessment_result_obj"
        )
        decomposition: Optional[StepDecompositionResult] = state.get(
            "_decomposition_obj"
        )
        timeline: Optional[DeliveryTimeline] = state.get("_timeline_obj")


        if assessment_result is None or decomposition is None or timeline is None:
            raise AgentExecutionError(
                message="Missing output generation objects",
                context={"stage": "generate_outputs"},
            )

        excel_path = ""
        pdf_path = ""
        warnings = state.get("warnings", []).copy()

        # Generate Excel report
        try:
            excel_path = generate_excel_report(
                assessment_result=assessment_result,
                decomposition=decomposition,
                timeline=timeline,
                session_id=session_id,
            )
            logger.info(f"[{session_id}] Excel report generated: {excel_path}")
        except OutputGenerationError as e:
            logger.warning(f"[{session_id}] Excel generation failed: {e}")
            warnings.append(f"Excel generation failed: {str(e)}")

        # Generate PDF report
        try:
            pdf_path = generate_pdf_report(
                assessment_result=assessment_result,
                timeline=timeline,
                session_id=session_id,
            )
            logger.info(f"[{session_id}] PDF report generated: {pdf_path}")
        except OutputGenerationError as e:
            logger.warning(f"[{session_id}] PDF generation failed: {e}")
            warnings.append(f"PDF generation failed: {str(e)}")

        # Determine final status
        if not excel_path and not pdf_path:
            final_status = "failed"
        elif not excel_path or not pdf_path:
            final_status = "partial"
        else:
            final_status = "success"

        # Save checkpoint
        _save_checkpoint(state, "complete")

        # Return final state
        return {
            "excel_path": excel_path,
            "pdf_path": pdf_path,
            "status": final_status,
            "current_stage": "complete",
            "completed_at": datetime.utcnow().isoformat(),
            "warnings": warnings,
        }

    except Exception as e:
        logger.error(f"[{session_id}] Output generation error: {e}")
        return {
            "status": "failed",
            "errors": state["errors"] + [f"Output generation: {str(e)}"],
            "current_stage": "generate_outputs",
            "completed_at": datetime.utcnow().isoformat(),
        }


# ==================== ROUTING FUNCTION ====================


def _should_continue(state: PipelineState) -> str:
    """Route: continue to next node or end pipeline.

    Returns:
        "continue" to proceed to next stage
        "end" to stop pipeline (on failure)
    """
    if state.get("status") == "failed":
        return "end"
    return "continue"


# ==================== GRAPH CONSTRUCTION ====================


def _build_graph() -> StateGraph:
    """Build and return the compiled 5-stage orchestrator graph.

    Returns:
        Compiled StateGraph ready for invocation
    """
    graph = StateGraph(PipelineState)

    # Add all 5 nodes
    graph.add_node("document_intelligence", stage_document_intelligence)
    graph.add_node("process_analysis", stage_process_analysis)
    graph.add_node("complexity_assessment", stage_complexity_assessment)
    graph.add_node("effort_estimation", stage_effort_and_decomposition)
    graph.add_node("generate_outputs", stage_generate_outputs)

    # Set entry point
    graph.set_entry_point("document_intelligence")

    # Add conditional edges (stop on failure)
    for src, dst in [
        ("document_intelligence", "process_analysis"),
        ("process_analysis", "complexity_assessment"),
        ("complexity_assessment", "effort_estimation"),
        ("effort_estimation", "generate_outputs"),
    ]:
        graph.add_conditional_edges(
            src, _should_continue, {"continue": dst, "end": END}
        )

    # Final node always ends
    graph.add_edge("generate_outputs", END)

    return graph.compile()


# Compile the graph once at module load
_graph = _build_graph()
