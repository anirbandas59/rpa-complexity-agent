"""
RPA Complexity Assessment Agent — Streamlit Frontend.

3-page web application for uploading PDDs and viewing assessment results.
Communicates with FastAPI backend via HTTP.
"""

import os
import httpx
import streamlit as st

from config.logging_config import setup_logging

# Configure page
st.set_page_config(
    page_title="RPA Complexity Assessment Agent",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Setup logging
setup_logging()

# API configuration
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
API_TIMEOUT = 30  # seconds


# ─── API Client Functions ──────────────────────────────────────


def api_post_assess(file_bytes: bytes, filename: str, form_data: dict) -> dict:
    """
    POST a file to /api/assess with multipart form data.

    Args:
        file_bytes: Binary content of the file
        filename: Name of the file (e.g., "pdd.pdf")
        form_data: Dict with rpa_tool, project_name, etc.

    Returns:
        Response JSON dict with session_id and status

    Raises:
        Exception: If the request fails
    """
    files = {"file": (filename, file_bytes)}
    data = {k: str(v) if v is not None else "" for k, v in form_data.items()}

    url = f"{API_BASE_URL}/api/assess"
    response = httpx.post(url, files=files, data=data, timeout=API_TIMEOUT)
    response.raise_for_status()
    return response.json()


def api_get_status(session_id: str) -> dict:
    """
    GET assessment status from /api/status/{session_id}.

    Args:
        session_id: Session ID from the assessment

    Returns:
        Response JSON dict with status, complexity_tier, etc.
        Returns {"status": "not_found"} on 404
        Returns {"status": "error", "message": str} on error
    """
    url = f"{API_BASE_URL}/api/status/{session_id}"
    try:
        response = httpx.get(url, timeout=API_TIMEOUT)
        if response.status_code == 404:
            return {"status": "not_found"}
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"status": "error", "message": str(e)}


def api_get_download_url(session_id: str, file_type: str) -> str:
    """
    Build the download URL for a report file.

    Args:
        session_id: Session ID
        file_type: "excel" or "pdf"

    Returns:
        Full URL to download endpoint
    """
    return f"{API_BASE_URL}/api/download/{session_id}/{file_type}"


# ─── Session State Initialization ──────────────────────────────


def init_session_state():
    """Initialize session state with default values."""
    if "page" not in st.session_state:
        st.session_state["page"] = "upload"
    if "session_id" not in st.session_state:
        st.session_state["session_id"] = None
    if "result" not in st.session_state:
        st.session_state["result"] = None
    if "file_name" not in st.session_state:
        st.session_state["file_name"] = None
    if "poll_count" not in st.session_state:
        st.session_state["poll_count"] = 0


init_session_state()


# ─── Sidebar Navigation ────────────────────────────────────────


def render_sidebar():
    """Render sidebar with navigation and info."""
    st.sidebar.markdown("## 🤖 RPA Assessment Agent")
    st.sidebar.markdown("Powered by IBM watsonx")
    st.sidebar.divider()

    # Navigation state
    page = st.session_state.get("page", "upload")
    if page == "upload":
        st.sidebar.markdown("**📄 Step 1: Upload PDD**")
        st.sidebar.caption("Upload your Process Design Document")
    elif page == "processing":
        st.sidebar.markdown("**⚙️ Step 2: Processing**")
        st.sidebar.caption("Analyzing document...")
    elif page == "results":
        st.sidebar.markdown("**✅ Step 3: Results**")
        st.sidebar.caption("View assessment results")

    st.sidebar.divider()

    # Info box
    st.sidebar.info(
        """
        **Supported Formats:**
        - PDF (.pdf)
        - Word (.docx)

        **Processing Time:**
        ~2-5 minutes per document

        **Supported RPA Platforms:**
        - Blue Prism
        - UiPath
        - Power Automate
        - Automation Anywhere 360
        """
    )

    # New assessment button
    if st.sidebar.button("🔄 New Assessment", use_container_width=True):
        st.session_state["page"] = "upload"
        st.session_state["session_id"] = None
        st.session_state["result"] = None
        st.session_state["file_name"] = None
        st.session_state["poll_count"] = 0
        st.rerun()


# ─── Main App Logic ────────────────────────────────────────────


def main():
    """Main app entry point."""
    render_sidebar()

    page = st.session_state.get("page", "upload")

    if page == "upload":
        from frontend.pages.upload import show

        show()
    elif page == "processing":
        from frontend.pages.assessment import show

        show()
    elif page == "results":
        from frontend.pages.results import show

        show()
    else:
        st.error(f"Unknown page: {page}")


if __name__ == "__main__":
    main()
