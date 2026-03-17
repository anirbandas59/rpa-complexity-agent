"""
Assessment processing endpoints for the RPA Complexity Assessment API.

Handles document uploads, background assessment processing, status polling,
and output file downloads.
"""

import uuid
import logging
import shutil
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, UploadFile, File, Form, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from agents import run_assessment
from config.logging_config import get_logger
from config.settings import get_settings

router = APIRouter(prefix="/api", tags=["assessment"])

logger = get_logger("api.assessment")

# In-memory session store: session_id → result dict
# Status values: "queued" | "processing" | "success" | "partial" | "failed"
_sessions: dict[str, dict] = {}


# ─── Pydantic Models ────────────────────────────────────────────────────


class AssessmentRequest(BaseModel):
    """Request parameters for assessment."""

    rpa_tool: str = "unknown"
    project_name: str = ""
    start_date: str = ""
    developer_name: str = "TBD"
    business_analyst: str = "TBD"
    squad: str = "RPA Team"


class AssessmentResponse(BaseModel):
    """Response from POST /api/assess."""

    session_id: str
    status: str
    message: str


class StatusResponse(BaseModel):
    """Response from GET /api/status/{session_id}."""

    session_id: str
    status: str
    complexity_tier: Optional[str] = None
    total_score: Optional[int] = None
    confidence: Optional[float] = None
    reasoning: Optional[str] = None
    requires_tech_lead_review: Optional[bool] = None
    raw_attributes: Optional[dict] = None
    detected_rpa_tool: Optional[str] = None
    effort_estimate: Optional[dict] = None
    timeline_summary: Optional[dict] = None
    output_files: Optional[dict] = None
    warnings: list[str] = []
    errors: list[str] = []
    completed_at: Optional[str] = None
    message: str = ""


# ─── Background Task ────────────────────────────────────────────────────


def _run_assessment_task(
    session_id: str,
    file_path: str,
    request: AssessmentRequest,
) -> None:
    """
    Run assessment in background.

    Steps:
    1. Update status to "processing"
    2. Call run_assessment()
    3. Store result
    4. Clean up uploaded file
    5. On error, set status to "failed" and store error
    """
    try:
        # Step 1: Update status
        _sessions[session_id]["status"] = "processing"
        logger.info(f"[{session_id}] Assessment processing started")

        # Step 2: Call run_assessment
        result = run_assessment(
            file_path=file_path,
            rpa_tool=request.rpa_tool,
            project_name=request.project_name,
            start_date=request.start_date,
            developer_name=request.developer_name,
            business_analyst=request.business_analyst,
            squad=request.squad,
            session_id=session_id,
        )

        # Step 3: Store result
        _sessions[session_id].update(result)
        _sessions[session_id]["status"] = result.get("status", "failed")
        logger.info(
            f"[{session_id}] Assessment completed with status={result.get('status')}"
        )

    except Exception as e:
        logger.error(f"[{session_id}] Assessment failed: {e}", exc_info=True)
        _sessions[session_id]["status"] = "failed"
        _sessions[session_id]["errors"] = [str(e)]

    finally:
        # Step 4: Clean up uploaded file
        try:
            Path(file_path).unlink(missing_ok=True)
            logger.debug(f"[{session_id}] Cleaned up uploaded file")
        except Exception as e:
            logger.warning(f"[{session_id}] Failed to clean up file: {e}")


# ─── Endpoints ──────────────────────────────────────────────────────────


@router.post("/assess", response_model=AssessmentResponse)
async def upload_assessment(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None,
    rpa_tool: str = Form("unknown"),
    project_name: str = Form(""),
    start_date: str = Form(""),
    developer_name: str = Form("TBD"),
    business_analyst: str = Form("TBD"),
    squad: str = Form("RPA Team"),
):
    """
    Upload a PDD file and start assessment.

    Accepts multipart form data:
    - file: PDF or DOCX document
    - rpa_tool, project_name, start_date, developer_name, business_analyst, squad

    Returns immediately with session_id. Client polls GET /api/status/{session_id}.
    """
    # Step 1: Validate file
    if not file.filename:
        raise HTTPException(status_code=400, detail="File name is required")

    ext = Path(file.filename).suffix.lower()
    if ext not in [".pdf", ".docx"]:
        raise HTTPException(
            status_code=400,
            detail="Only PDF and DOCX files are supported",
        )

    # Step 2: Generate session_id
    session_id = str(uuid.uuid4())[:8]

    # Step 3: Save uploaded file to data/temp/
    save_dir = Path("data/temp")
    save_dir.mkdir(parents=True, exist_ok=True)
    save_path = save_dir / f"{session_id}{ext}"

    try:
        with save_path.open("wb") as f:
            shutil.copyfileobj(file.file, f)
    except Exception as e:
        logger.error(f"[{session_id}] Failed to save file: {e}")
        raise HTTPException(status_code=500, detail="Failed to save uploaded file")

    # Step 4: Initialize session
    request = AssessmentRequest(
        rpa_tool=rpa_tool,
        project_name=project_name,
        start_date=start_date,
        developer_name=developer_name,
        business_analyst=business_analyst,
        squad=squad,
    )
    _sessions[session_id] = {
        "session_id": session_id,
        "status": "queued",
        "file_name": file.filename,
    }

    # Step 5: Add background task
    background_tasks.add_task(
        _run_assessment_task,
        session_id,
        str(save_path),
        request,
    )

    # Step 6: Return immediately
    return AssessmentResponse(
        session_id=session_id,
        status="queued",
        message=f"Assessment queued. Poll GET /api/status/{session_id}",
    )


@router.get("/status/{session_id}", response_model=StatusResponse)
async def get_status(session_id: str):
    """
    Poll assessment status by session_id.

    Returns current status and results if available. Status can be:
    - "queued": Waiting to start
    - "processing": In progress
    - "success": Completed successfully
    - "partial": Completed with warnings
    - "failed": Assessment failed
    """
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    session = _sessions[session_id]
    status = session.get("status", "unknown")

    # Build message based on status
    messages = {
        "queued": "Assessment is queued for processing",
        "processing": "Assessment is in progress",
        "success": "Assessment complete",
        "partial": "Assessment complete with warnings",
        "failed": "Assessment failed — see errors",
    }
    message = messages.get(status, "Unknown status")

    return StatusResponse(
        **session,
        message=message,
    )


@router.get("/download/{session_id}/{file_type}")
async def download_output(session_id: str, file_type: str):
    """
    Download assessment output file (excel or pdf).

    file_type must be "excel" or "pdf".

    Returns 404 if session not found, 400 if still processing or failed,
    or 404 if file does not exist.
    """
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    if file_type not in ["excel", "pdf"]:
        raise HTTPException(status_code=400, detail="file_type must be excel or pdf")

    session = _sessions[session_id]
    status = session.get("status", "unknown")

    # Only allow download if assessment succeeded
    if status not in ["success", "partial"]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot download while assessment is {status}",
        )

    # Get file path from output_files
    output_files = session.get("output_files", {})
    file_path = output_files.get(file_type, "")

    if not file_path or not Path(file_path).exists():
        raise HTTPException(status_code=404, detail=f"{file_type} file not found")

    return FileResponse(
        path=file_path,
        filename=Path(file_path).name,
        media_type="application/octet-stream",
    )


@router.get("/sessions")
async def list_sessions():
    """
    Get all sessions (for debugging).

    Returns list of session summaries: session_id, status, file_name, complexity_tier.
    """
    summaries = []
    for session_id, session in _sessions.items():
        summaries.append(
            {
                "session_id": session_id,
                "status": session.get("status", "unknown"),
                "file_name": session.get("file_name", ""),
                "complexity_tier": session.get("complexity_tier"),
            }
        )
    return summaries
