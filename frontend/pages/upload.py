"""Upload page — PDD file upload form."""

from datetime import date

import streamlit as st


def show() -> None:
    """Render the upload page."""
    st.title("🤖 RPA Complexity Assessment Agent")
    st.markdown(
        "Upload a Process Design Document (PDD) to automatically assess "
        "its RPA implementation complexity."
    )
    st.divider()

    col_left, col_right = st.columns([2, 1])

    # LEFT COLUMN — Upload form
    with col_left:
        st.subheader("📄 Upload Process Design Document")

        file = st.file_uploader(
            "Select PDD file",
            type=["pdf", "docx"],
            help="Upload a Word (.docx) or PDF (.pdf) PDD file",
        )

        st.subheader("⚙️ Assessment Configuration")

        project_name = st.text_input(
            "Project Name",
            placeholder="e.g. SAP ASM Automation",
            help="Name of the automation project",
        )

        rpa_tool = st.selectbox(
            "RPA Platform",
            options=["unknown", "blue_prism", "uipath", "power_automate", "aa360"],
            format_func=lambda x: {
                "unknown": "Auto-detect",
                "blue_prism": "Blue Prism",
                "uipath": "UiPath",
                "power_automate": "Power Automate",
                "aa360": "Automation Anywhere 360",
            }[x],
            help="Select the target RPA platform or auto-detect",
        )

        col_a, col_b = st.columns(2)
        with col_a:
            developer_name = st.text_input(
                "Developer Name", placeholder="e.g. John Smith"
            )
            business_analyst = st.text_input(
                "Business Analyst", placeholder="e.g. Jane Doe"
            )
        with col_b:
            squad = st.text_input("Squad / Team", placeholder="e.g. RPA Team")
            start_date = st.date_input("Project Start Date", value=date.today())

        st.divider()

        run_button = st.button(
            "🚀 Run Assessment",
            type="primary",
            disabled=(file is None),
            use_container_width=True,
        )

        if run_button and file is not None:
            with st.spinner("Uploading document..."):
                try:
                    from frontend.app import api_post_assess

                    response = api_post_assess(
                        file_bytes=file.read(),
                        filename=file.name,
                        form_data={
                            "rpa_tool": rpa_tool,
                            "project_name": project_name or file.name,
                            "start_date": str(start_date),
                            "developer_name": developer_name or "TBD",
                            "business_analyst": business_analyst or "TBD",
                            "squad": squad or "RPA Team",
                        },
                    )
                    st.session_state["session_id"] = response["session_id"]
                    st.session_state["file_name"] = file.name
                    st.session_state["poll_count"] = 0
                    st.session_state["page"] = "processing"
                    st.rerun()
                except Exception as e:
                    st.error(f"Upload failed: {str(e)}")

    # RIGHT COLUMN — Information panel
    with col_right:
        st.subheader("ℹ️ About This Tool")
        st.info("""
            This tool automates RPA complexity assessment by:

            1. **Parsing** your PDD document
            2. **Extracting** process attributes
            3. **Scoring** against 5 complexity dimensions
            4. **Generating** effort estimates

            **Complexity Tiers:**
            - 🟢 XS — Extra Small (≤10 days)
            - ⬜ S — Small (20-40 days)
            - ⬜ M — Medium (50 days)
            - 🔴 L — Large (60 days)
            - 🟣 XL — Extra Large (80 days)
            """)

        st.subheader("📊 Scoring Dimensions")
        st.markdown("""
            | # | Attribute | Max Score |
            |---|-----------|-----------|
            | 1 | Activities | 8 |
            | 2 | Business Rules | 8 |
            | 3 | Digital Layouts | 4 |
            | 4 | Target Interfaces | 4 |
            | 5 | Add. Technology | 4 |
            | | **Total** | **28** |
            """)
