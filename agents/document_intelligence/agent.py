"""Document Intelligence Agent using LangGraph.

Orchestrates document parsing, section identification, and entity extraction.
Zero business logic — nodes call tools only.

Exposed API:
  run(file_path, session_id=None) -> DocumentIntelligenceState
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional, TypedDict

from langgraph.graph import END, StateGraph

from config.logging_config import get_logger
from core.exceptions import AgentExecutionError, DocumentProcessingError
from core.models.document import ExtractedSection, ParsedDocument
from tools.document.docx_parser import parse_docx
from tools.document.entity_extractor import (
    EntityExtractionResponse,
    extract_entities,
)
from tools.document.pdf_parser import parse_pdf
from tools.document.section_identifier import identify_sections

logger = get_logger("document_intelligence_agent")


# ==================== STATE DEFINITION ====================


class DocumentIntelligenceState(TypedDict):
    """State for Document Intelligence Agent graph.

    Fields:
      file_path: Path to the document file to process
      session_id: Unique session identifier for logging
      parsed_document: Parsed document from PDF/DOCX parser
      sections: List of identified sections
      entities: Extracted entities from sections
      status: "success", "needs_review", or "failed"
      warnings: List of warning messages
      errors: List of error messages
      completed_at: ISO timestamp of completion
    """

    file_path: str
    session_id: str
    parsed_document: Optional[ParsedDocument]
    sections: list[ExtractedSection]
    entities: Optional[EntityExtractionResponse]
    status: str
    warnings: list[str]
    errors: list[str]
    completed_at: str


# ==================== NODE FUNCTIONS ====================


def ingest_document(state: DocumentIntelligenceState) -> dict[str, Any]:
    """Parse raw file into ParsedDocument.

    Supports .pdf and .docx files.
    Sets status='failed' on unsupported extension or parse error.

    Args:
        state: Current graph state

    Returns:
        Dict with parsed_document and updated warnings/errors
    """
    session_id = state["session_id"]
    file_path = state["file_path"]

    logger.info(f"[{session_id}] Starting document ingestion: {file_path}")

    # Determine file type
    ext = file_path.lower().split(".")[-1]

    try:
        if ext == "pdf":
            parsed_doc = parse_pdf(file_path)
        elif ext == "docx":
            parsed_doc = parse_docx(file_path)
        else:
            return {
                "status": "failed",
                "errors": [f"Unsupported file type: .{ext}. Supported: .pdf, .docx"],
                "parsed_document": None,
            }

        # Accumulate extraction warnings
        warnings = state.get("warnings", []) + parsed_doc.extraction_warnings

        logger.info(
            f"[{session_id}] Document ingested: {parsed_doc.page_count} pages, "
            f"{parsed_doc.word_count()} words"
        )

        return {
            "parsed_document": parsed_doc,
            "warnings": warnings,
        }

    except DocumentProcessingError as e:
        return {
            "status": "failed",
            "errors": [str(e)],
            "parsed_document": None,
        }


def identify_document_sections(state: DocumentIntelligenceState) -> dict[str, Any]:
    """Extract sections from parsed document.

    Skips if document failed to parse.
    Adds warnings on section identification failure (recoverable).

    Args:
        state: Current graph state

    Returns:
        Dict with sections and updated warnings
    """
    session_id = state["session_id"]
    parsed_doc = state.get("parsed_document")

    # Skip if document parsing failed
    if state.get("status") == "failed" or parsed_doc is None:
        return {}

    logger.info(f"[{session_id}] Identifying document sections")

    try:
        sections = identify_sections(parsed_doc, llm_manager=None)

        logger.info(f"[{session_id}] Found {len(sections)} sections")

        return {"sections": sections}

    except Exception as e:
        logger.warning(f"[{session_id}] Section identification failed: {e}")
        warnings = state.get("warnings", [])
        warnings.append(f"Section identification failed: {e}")
        return {
            "sections": [],
            "warnings": warnings,
        }


def extract_document_entities(state: DocumentIntelligenceState) -> dict[str, Any]:
    """Extract named entities from identified sections.

    Skips if document failed to parse.
    Creates catch-all section if no sections identified.
    Adds warnings on entity extraction failure (recoverable).

    Args:
        state: Current graph state

    Returns:
        Dict with entities and updated warnings
    """
    session_id = state["session_id"]
    parsed_doc = state.get("parsed_document")

    # Skip if document parsing failed
    if state.get("status") == "failed" or parsed_doc is None:
        return {}

    sections = state.get("sections", [])

    # If no sections, create catch-all from full text
    if not sections:
        logger.warning(
            f"[{session_id}] No sections found — extracting entities from "
            "full document text"
        )
        sections = [
            ExtractedSection(
                title="Full Document",
                content=parsed_doc.full_text[:5000],
                section_type="general",
                confidence_score=0.1,
                page_number=None,
            )
        ]

    try:
        entities = extract_entities(sections, llm_manager=None)

        logger.info(
            f"[{session_id}] Entities extracted: "
            f"{len(entities.applications)} applications, "
            f"{len(entities.technologies)} technologies, "
            f"tool={entities.rpa_tool}"
        )

        return {"entities": entities}

    except Exception as e:
        logger.warning(f"[{session_id}] Entity extraction failed: {e}")
        warnings = state.get("warnings", [])
        warnings.append(f"Entity extraction failed: {e}")
        return {
            "entities": EntityExtractionResponse(),
            "warnings": warnings,
        }


def validate_output(state: DocumentIntelligenceState) -> dict[str, Any]:
    """Validate complete output and set final status.

    Checks for failure conditions and needs_review conditions.
    Sets completed_at timestamp.

    Args:
        state: Current graph state

    Returns:
        Dict with status, warnings, and completed_at
    """
    session_id = state["session_id"]
    warnings = list(state.get("warnings", []))
    parsed_doc = state.get("parsed_document")

    # Failure conditions
    if state.get("status") == "failed" or parsed_doc is None:
        final_status = "failed"
    else:
        # Check needs_review conditions
        needs_review = False

        # a) Low word count
        word_count = parsed_doc.word_count()
        if word_count < 200:
            warning = (
                f"Document has very few words ({word_count}) — "
                "assessment accuracy may be low"
            )
            warnings.append(warning)
            needs_review = True

        # b) Few sections
        if len(state.get("sections", [])) < 2:
            warning = (
                f"Only {len(state.get('sections', []))} sections identified — "
                "document structure may be unclear"
            )
            warnings.append(warning)
            needs_review = True

        # c) No applications
        entities = state.get("entities")
        if entities is None or len(entities.applications) == 0:
            warning = (
                "No target applications identified — "
                "manual review of attribute #4 required"
            )
            warnings.append(warning)
            needs_review = True

        # d) Document validity
        if not parsed_doc.is_valid():
            warning = (
                "Document failed validity check — " "may be image-based or corrupted"
            )
            warnings.append(warning)
            needs_review = True

        final_status = "needs_review" if needs_review else "success"

    logger.info(
        f"[{session_id}] Validation complete. Status: {final_status}, "
        f"warnings: {len(warnings)}, errors: {len(state.get('errors', []))}"
    )

    return {
        "status": final_status,
        "warnings": warnings,
        "completed_at": datetime.utcnow().isoformat(),
    }


# ==================== ROUTING ====================


def should_continue(state: DocumentIntelligenceState) -> str:
    """Conditional routing after document ingestion.

    Returns 'end' if document parsing failed, 'continue' otherwise.

    Args:
        state: Current graph state

    Returns:
        'end' or 'continue'
    """
    if state.get("status") == "failed":
        return "end"
    return "continue"


# ==================== GRAPH CONSTRUCTION ====================


def _build_graph() -> Any:
    """Build and compile the LangGraph StateGraph.

    Returns:
        Compiled StateGraph
    """
    graph: StateGraph[DocumentIntelligenceState] = StateGraph(DocumentIntelligenceState)

    # Add nodes
    graph.add_node("ingest_document", ingest_document)
    graph.add_node("identify_sections", identify_document_sections)
    graph.add_node("extract_entities", extract_document_entities)
    graph.add_node("validate_output", validate_output)

    # Entry point
    graph.set_entry_point("ingest_document")

    # Conditional edge after ingest — skip remaining if failed
    graph.add_conditional_edges(
        "ingest_document",
        should_continue,
        {
            "continue": "identify_sections",
            "end": END,
        },
    )

    # Linear edges for remaining nodes
    graph.add_edge("identify_sections", "extract_entities")
    graph.add_edge("extract_entities", "validate_output")
    graph.add_edge("validate_output", END)

    return graph.compile()


# Module-level compiled graph (built once on import)
_graph = _build_graph()


# ==================== PUBLIC API ====================


def run(file_path: str, session_id: Optional[str] = None) -> Any:
    """Run the Document Intelligence Agent.

    Parses document, identifies sections, extracts entities,
    and validates output. Single entry point for this agent.

    Args:
        file_path: Path to PDF or DOCX document
        session_id: Optional session ID for logging.
                    Generated if not provided.

    Returns:
        Final state dict with all results and status

    Raises:
        AgentExecutionError: If graph execution fails
    """
    if session_id is None:
        session_id = str(uuid.uuid4())[:8]

    initial_state: DocumentIntelligenceState = {
        "file_path": file_path,
        "session_id": session_id,
        "parsed_document": None,
        "sections": [],
        "entities": None,
        "status": "running",
        "warnings": [],
        "errors": [],
        "completed_at": "",
    }

    logger.info(f"[{session_id}] Document Intelligence Agent starting: {file_path}")

    try:
        final_state: Any = _graph.invoke(initial_state)
    except Exception as e:
        logger.error(f"[{session_id}] Document Intelligence Agent failed: {e}")
        raise AgentExecutionError(
            message="Document Intelligence Agent failed",
            context={
                "session_id": session_id,
                "file_path": file_path,
                "error": str(e),
            },
        ) from e

    logger.info(
        f"[{session_id}] Document Intelligence Agent complete. "
        f"Status: {final_state['status']}"
    )

    return final_state
