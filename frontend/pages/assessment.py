"""Assessment page — Live progress during processing."""

import time

import streamlit as st

MAX_POLL_ATTEMPTS = 120  # 6 minutes at 3-second intervals

# ── Error message mapping ─────────────────────────────────────────────────────

_ERROR_PATTERNS: list[tuple[tuple[str, ...], str]] = [
    (
        ("encrypted", "password"),
        "Your PDF is password-protected. Please provide an unprotected version.",
    ),
    (
        ("ocr", "image-only", "no text"),
        "Your PDF appears to be scanned. Try a text-based PDF.",
    ),
    (
        ("rate", "429"),
        "LLM quota exceeded. Try switching to Ollama in .env settings.",
    ),
    (
        ("no steps", "no activities"),
        "No RPA process steps were detected. Verify this is a Process Design Document.",
    ),
]


def _friendly_error(raw: str) -> str:
    """Map a known error string to a user-friendly message.

    Falls back to the raw string if no pattern matches.
    """
    lower = raw.lower()
    for keywords, message in _ERROR_PATTERNS:
        if any(kw in lower for kw in keywords):
            return message
    return raw


def show() -> None:
    """Render the assessment progress page."""
    session_id = st.session_state.get("session_id")
    file_name = st.session_state.get("file_name", "Unknown")

    if session_id is None:
        st.error("No active session. Please upload a document.")
        if st.button("Go to Upload"):
            st.session_state["page"] = "upload"
            st.rerun()
        return

    st.title("⚙️ Assessment In Progress")
    st.markdown(f"Processing: **{file_name}**")
    st.divider()

    # Define pipeline stages
    stages = [
        ("📄", "Document Intelligence", "Parsing and extracting document content"),
        ("🔍", "Process Analysis", "Identifying activities, rules, and interfaces"),
        ("📊", "Complexity Assessment", "Calculating complexity score"),
        ("📋", "Effort Estimation", "Generating timeline and decomposition"),
        ("💾", "Output Generation", "Creating Excel and PDF reports"),
    ]

    # Poll status from API
    from frontend.app import api_get_status

    status_data = api_get_status(session_id)
    current_status = status_data.get("status", "queued")
    current_stage = status_data.get("current_stage", "")

    # Map stage names to indices
    stage_mapping = {
        "initializing": -1,
        "document_intelligence": 0,
        "process_analysis": 1,
        "complexity_assessment": 2,
        "effort_estimation": 3,
        "generate_outputs": 4,
    }
    current_stage_idx = stage_mapping.get(current_stage, -1)

    # Display stage progress
    st.subheader("📈 Pipeline Progress")
    for idx, (icon, name, desc) in enumerate(stages):
        if idx < current_stage_idx:
            st.success(f"{icon} {name}: ✅ Complete")
            st.caption(desc)
        elif idx == current_stage_idx and current_status == "processing":
            st.info(f"{icon} {name}: ⚙️ In Progress")
            st.caption(desc)
        else:
            st.empty()
            st.markdown(f"{icon} {name}: ⏳ Pending")
            st.caption(desc)

    # Progress bar
    if current_status == "queued":
        progress_value = 5
    elif current_status == "processing":
        progress_map = {
            "document_intelligence": 20,
            "process_analysis": 40,
            "complexity_assessment": 60,
            "effort_estimation": 80,
            "generate_outputs": 95,
        }
        progress_value = progress_map.get(current_stage, 50)
    elif current_status in ["success", "partial"]:
        progress_value = 100
    else:
        progress_value = 0

    st.progress(progress_value / 100)

    # Status messages
    if current_status == "queued":
        st.info("⏳ Assessment is queued and will begin shortly...")
    elif current_status == "processing":
        st.info(f"⚙️ Processing stage: {current_stage}")
    elif current_status in ["success", "partial"]:
        st.success("✅ Assessment complete! Loading results...")
        st.session_state["result"] = status_data
        st.session_state["page"] = "results"
        st.rerun()
    elif current_status == "failed":
        errors = status_data.get("errors", [])
        friendly = [_friendly_error(e) for e in errors] if errors else ["Unknown error"]
        for msg in friendly:
            st.error(f"❌ {msg}")
        if st.button("Try Again"):
            st.session_state["page"] = "upload"
            st.rerun()
        return
    elif current_status == "not_found":
        st.error("❌ Session not found. Please upload a document again.")
        if st.button("Go to Upload"):
            st.session_state["page"] = "upload"
            st.rerun()
        return
    elif current_status == "error":
        error_msg = status_data.get("message", "Unknown error")
        st.error(f"❌ {_friendly_error(error_msg)}")
        return

    # Auto-refresh with bounded poll count
    poll_count = st.session_state.get("poll_count", 0)

    st.caption(f"Auto-refreshing... (poll #{poll_count + 1}/{MAX_POLL_ATTEMPTS})")

    if poll_count < MAX_POLL_ATTEMPTS and current_status not in [
        "success",
        "partial",
        "failed",
    ]:
        st.session_state["poll_count"] = poll_count + 1
        time.sleep(3)
        st.rerun()
    elif poll_count >= MAX_POLL_ATTEMPTS:
        st.error("Assessment is taking too long. Please try again.")
