"""Agent modules for RPA Complexity Assessment.

Available agents:
  - document_intelligence: Parses PDFs/DOCXs and extracts sections/entities
  - process_analysis: Analyzes activities, rules, layouts, interfaces, technology
  - complexity_assessment: Scores and classifies complexity
  - orchestrator: Wires all agents into end-to-end pipeline

Public API:
  run_assessment(): Single entry point for the entire pipeline
"""

import uuid
from datetime import date
from pathlib import Path

from agents.document_intelligence import run as run_document_intelligence
from agents.orchestrator import _graph
from config.logging_config import get_logger
from core.exceptions import AgentExecutionError

logger = get_logger("agents")


def run_assessment(
    file_path: str,
    rpa_tool: str = "unknown",
    project_name: str = "",
    start_date: str = "",
    developer_name: str = "TBD",
    business_analyst: str = "TBD",
    squad: str = "RPA Team",
    session_id: str | None = None,
) -> dict:
    """Run the complete RPA Complexity Assessment pipeline.

    This is the ONLY public entry point. It orchestrates all four agents
    (Document Intelligence, Process Analysis, Complexity Assessment) plus
    output generation to produce a comprehensive assessment result with
    Excel and PDF reports.

    Args:
        file_path: Path to PDD document (PDF or DOCX)
        rpa_tool: Detected or user-specified RPA tool (default "unknown")
        project_name: Optional user-provided project name
        start_date: Optional project start date in ISO format "YYYY-MM-DD"
        developer_name: Assigned developer name (default "TBD")
        business_analyst: Assigned BA name (default "TBD")
        squad: Team/squad name (default "RPA Team")
        session_id: Optional session identifier; auto-generated if not provided

    Returns:
        Dict with assessment results:
          session_id: Unique pipeline execution ID
          status: "success" | "partial" | "failed"
          complexity_tier: "XS" | "S" | "M" | "L" | "XL" or None
          total_score: 0-28 or None
          confidence: 0.0-1.0 or None
          reasoning: Assessment explanation or None
          requires_tech_lead_review: Boolean or None
          raw_attributes: Dict with activities, business_rules, layouts, interfaces, technology
          detected_rpa_tool: Detected tool name
          effort_estimate: Dict with step counts and branch info
          timeline_summary: Dict with hours, story points, feature count
          output_files: Dict with "excel" and "pdf" paths
          warnings: List of non-critical issues
          errors: List of errors encountered
          completed_at: ISO timestamp when pipeline finished

    Raises:
        AgentExecutionError: If file not found, unsupported format, or pipeline fails
    """
    # Generate session_id if not provided
    if session_id is None:
        session_id = str(uuid.uuid4())[:8]

    # Validate file_path
    file_path_obj = Path(file_path)
    if not file_path_obj.exists():
        raise AgentExecutionError(
            message=f"PDD file not found: {file_path}",
            context={"file_path": file_path},
        )

    # Validate file extension
    ext = file_path_obj.suffix.lower()
    if ext not in [".pdf", ".docx"]:
        raise AgentExecutionError(
            message=f"Unsupported file type: {ext}",
            context={"supported": [".pdf", ".docx"], "provided": ext},
        )

    # Build initial state
    from agents.orchestrator import PipelineState

    initial_state: PipelineState = {
        "file_path": str(file_path_obj.absolute()),
        "session_id": session_id,
        "rpa_tool_override": rpa_tool,
        "project_name": project_name,
        "start_date": start_date or date.today().isoformat(),
        "developer_name": developer_name,
        "business_analyst": business_analyst,
        "squad": squad,
        "di_state": {},
        "pa_state": {},
        "ca_state": {},
        "decomposition": {},
        "timeline": {},
        "excel_path": "",
        "pdf_path": "",
        "_assessment_result_obj": None,
        "_decomposition_obj": None,
        "_timeline_obj": None,
        "status": "running",
        "current_stage": "initializing",
        "warnings": [],
        "errors": [],
        "completed_at": "",
    }

    # Run pipeline
    logger.info(f"[{session_id}] Pipeline starting: {file_path}")
    final_state = _graph.invoke(initial_state)

    # Extract assessment result safely
    ca_state = final_state.get("ca_state", {})
    assessment_result = ca_state.get("assessment_result")

    # Build and return clean result dict
    return {
        "session_id": session_id,
        "status": final_state.get("status", "failed"),
        "complexity_tier": (
            assessment_result.complexity_tier.value
            if assessment_result
            else None
        ),
        "total_score": assessment_result.total_score if assessment_result else None,
        "confidence": (
            assessment_result.confidence_score if assessment_result else None
        ),
        "reasoning": assessment_result.reasoning if assessment_result else None,
        "requires_tech_lead_review": (
            assessment_result.requires_tech_lead_review
            if assessment_result
            else None
        ),
        "raw_attributes": final_state.get("pa_state", {}).get("raw_attributes", {}),
        "detected_rpa_tool": final_state.get("pa_state", {}).get(
            "detected_rpa_tool", "unknown"
        ),
        "effort_estimate": final_state.get("decomposition", {}),
        "timeline_summary": final_state.get("timeline", {}),
        "output_files": {
            "excel": final_state.get("excel_path", ""),
            "pdf": final_state.get("pdf_path", ""),
        },
        "warnings": final_state.get("warnings", []),
        "errors": final_state.get("errors", []),
        "completed_at": final_state.get("completed_at", ""),
    }


__all__ = ["run_document_intelligence", "run_assessment"]
