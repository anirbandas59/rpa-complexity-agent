"""
Assessment processing endpoints for the RPA Complexity Assessment API.

Handles document uploads, background assessment processing, status polling,
and output file downloads.
"""

import asyncio
import json
import time
import uuid
from pathlib import Path
from typing import Optional

import aiosqlite
from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from agents import run_assessment
from api.limiter import limiter
from config.logging_config import get_logger

router = APIRouter(prefix="/api", tags=["assessment"])

logger = get_logger("api.assessment")

DB_PATH = "data/sessions.db"


# ─── SQLite session helpers ──────────────────────────────────────────────────


async def get_session(session_id: str) -> dict | None:
    """Return session data dict, or None if not found."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT status, result_json FROM sessions WHERE session_id = ?",
            (session_id,),
        ) as cursor:
            row = await cursor.fetchone()

    if row is None:
        return None

    result: dict = json.loads(row[1]) if row[1] else {}
    # DB columns are authoritative for frequently-updated fields
    result["session_id"] = session_id
    result["status"] = row[0]
    return result


async def set_session(session_id: str, data: dict) -> None:
    """Upsert session row.  created_at is preserved on conflict."""
    status = data.get("status", "queued")
    output_files = data.get("output_files") or {}
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO sessions
                (session_id, status, created_at, result_json, errors,
                 output_excel, output_pdf)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                status       = excluded.status,
                result_json  = excluded.result_json,
                errors       = excluded.errors,
                output_excel = excluded.output_excel,
                output_pdf   = excluded.output_pdf
            """,
            (
                session_id,
                status,
                time.time(),
                json.dumps(data),
                json.dumps(data.get("errors", [])),
                output_files.get("excel", ""),
                output_files.get("pdf", ""),
            ),
        )
        await db.commit()


async def _patch_status(session_id: str, status: str) -> None:
    """Update only the status column (used for the processing→queued transition)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE sessions SET status = ? WHERE session_id = ?",
            (status, session_id),
        )
        await db.commit()


# ─── Pydantic Models ─────────────────────────────────────────────────────────


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


# ─── Background Task ─────────────────────────────────────────────────────────


async def _run_assessment_task(
    session_id: str,
    file_path: str,
    request: AssessmentRequest,
) -> None:
    """
    Run assessment in background (async).

    Steps:
    1. Update status to "processing"
    2. Call run_assessment() via thread executor (sync function)
    3. Persist full result
    4. Clean up uploaded file
    5. On error, set status to "failed" and store error
    """
    try:
        # Step 1: Update status
        await _patch_status(session_id, "processing")
        logger.info(f"[{session_id}] Assessment processing started")

        # Step 2: Run sync assessment in thread pool so the event loop stays free
        loop = asyncio.get_event_loop()
        result: dict = await loop.run_in_executor(
            None,
            lambda: run_assessment(
                file_path=file_path,
                rpa_tool=request.rpa_tool,
                project_name=request.project_name,
                start_date=request.start_date,
                developer_name=request.developer_name,
                business_analyst=request.business_analyst,
                squad=request.squad,
                session_id=session_id,
            ),
        )

        # Step 3: Persist result
        result["session_id"] = session_id
        await set_session(session_id, result)
        logger.info(
            f"[{session_id}] Assessment completed with status={result.get('status')}"
        )

    except Exception as e:
        logger.error(f"[{session_id}] Assessment failed: {e}", exc_info=True)
        await set_session(
            session_id,
            {"session_id": session_id, "status": "failed", "errors": [str(e)]},
        )

    finally:
        # Step 4: Clean up uploaded file
        try:
            Path(file_path).unlink(missing_ok=True)
            logger.debug(f"[{session_id}] Cleaned up uploaded file")
        except Exception as e:
            logger.warning(f"[{session_id}] Failed to clean up file: {e}")


# ─── Endpoints ───────────────────────────────────────────────────────────────


@router.post("/assess", response_model=AssessmentResponse)
@limiter.limit("10/minute")
async def upload_assessment(
    request: Request,
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
    # Step 1: Validate file name and extension
    if not file.filename:
        raise HTTPException(status_code=400, detail="File name is required")

    ext = Path(file.filename).suffix.lower()
    if ext not in [".pdf", ".docx"]:
        raise HTTPException(
            status_code=400,
            detail="Only PDF and DOCX files are supported",
        )

    # Step 2: Read contents and enforce 20 MB size limit
    contents = await file.read()
    if len(contents) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File exceeds 20MB limit")

    # Step 3: Generate session_id
    session_id = str(uuid.uuid4())[:8]

    # Step 4: Save uploaded file to data/temp/
    save_dir = Path("data/temp")
    save_dir.mkdir(parents=True, exist_ok=True)
    save_path = save_dir / f"{session_id}{ext}"

    try:
        with save_path.open("wb") as f:
            f.write(contents)
    except Exception as e:
        logger.error(f"[{session_id}] Failed to save file: {e}")
        raise HTTPException(status_code=500, detail="Failed to save uploaded file")

    # Step 5: Persist initial session record
    assessment_request = AssessmentRequest(
        rpa_tool=rpa_tool,
        project_name=project_name,
        start_date=start_date,
        developer_name=developer_name,
        business_analyst=business_analyst,
        squad=squad,
    )
    await set_session(
        session_id,
        {
            "session_id": session_id,
            "status": "queued",
            "file_name": file.filename,
        },
    )

    # Step 6: Add background task
    background_tasks.add_task(
        _run_assessment_task,
        session_id,
        str(save_path),
        assessment_request,
    )

    # Step 7: Return immediately
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
    session = await get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

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
    session = await get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    if file_type not in ["excel", "pdf"]:
        raise HTTPException(status_code=400, detail="file_type must be excel or pdf")

    status = session.get("status", "unknown")

    # Only allow download if assessment succeeded
    if status not in ["success", "partial"]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot download while assessment is {status}",
        )

    # Get file path from output_files
    output_files = session.get("output_files") or {}
    file_path = output_files.get(file_type, "")

    if not file_path or not Path(file_path).exists():
        raise HTTPException(status_code=404, detail=f"{file_type} file not found")

    return FileResponse(
        path=file_path,
        filename=Path(file_path).name,
        media_type="application/octet-stream",
    )
