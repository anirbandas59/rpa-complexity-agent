"""Results page — Assessment results display."""

import pandas as pd
import streamlit as st


def show() -> None:
    """Render the results page."""
    result = st.session_state.get("result", {})

    if not result:
        st.error("No results available.")
        if st.button("Go to Upload"):
            st.session_state["page"] = "upload"
            st.rerun()
        return

    # Extract result data
    tier = result.get("complexity_tier", "Unknown")
    score = result.get("total_score", 0)
    confidence = result.get("confidence", 0.0)
    reasoning = result.get("reasoning", "")
    raw_attrs = result.get("raw_attributes", {})
    output_files = result.get("output_files", {})
    warnings = result.get("warnings", [])
    errors = result.get("errors", [])
    rpa_tool = result.get("detected_rpa_tool", "unknown")

    st.title("✅ Assessment Complete")
    st.divider()

    # Top metrics row
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Complexity Tier", tier)
    with col2:
        st.metric("Total Score", f"{score}/28")
    with col3:
        st.metric("Confidence", f"{confidence * 100:.0f}%")
    with col4:
        st.metric("RPA Platform", rpa_tool.replace("_", " ").title())

    # Complexity tier badge
    from frontend.components.complexity_gauge import render_tier_badge

    render_tier_badge(tier)

    st.divider()

    # Two column layout
    col_left, col_right = st.columns([3, 2])

    with col_left:
        st.subheader("📊 Attribute Score Breakdown")

        # Build attributes table
        attrs_list = []
        if raw_attrs:
            if "activities" in raw_attrs:
                attrs_list.append(("#1 Activities", raw_attrs["activities"]))
            if "business_rules" in raw_attrs:
                attrs_list.append(("#2 Business Rules", raw_attrs["business_rules"]))
            if "layouts" in raw_attrs:
                attrs_list.append(
                    ("#3 Digital Layouts", raw_attrs["layouts"])
                )
            if "interfaces" in raw_attrs:
                attrs_list.append(
                    ("#4 Target Interfaces", raw_attrs["interfaces"])
                )
            if "technology" in raw_attrs:
                attrs_list.append(
                    ("#5 Add. Technology", raw_attrs["technology"])
                )

        if attrs_list:
            attrs_df = pd.DataFrame(attrs_list, columns=["Attribute", "Value"])
            st.dataframe(attrs_df, hide_index=True, use_container_width=True)

        st.subheader("💭 Assessment Reasoning")
        st.info(reasoning if reasoning else "No reasoning available")

        if warnings:
            st.subheader("⚠️ Warnings")
            for warning in warnings:
                st.warning(warning)

        if errors:
            st.subheader("❌ Errors")
            for error in errors:
                st.error(error)

    with col_right:
        st.subheader("📅 Effort Estimate")

        effort = result.get("effort_estimate", {})
        timeline = result.get("timeline_summary", {})

        total_hours = timeline.get("total_hours", 0)
        total_sp = timeline.get("total_sp", 0)
        feature_count = timeline.get("feature_count", 0)

        st.metric("Total Hours", f"{total_hours:.0f}h")
        st.metric("Story Points", f"{total_sp:.1f} SP")
        st.metric("Features", feature_count)

        # Effort table
        from frontend.components.timeline_chart import render_effort_table

        render_effort_table(result)

        st.subheader("📥 Download Reports")
        col_dl1, col_dl2 = st.columns(2)
        session_id = st.session_state.get("session_id", "")

        with col_dl1:
            from frontend.app import api_get_download_url

            excel_url = api_get_download_url(session_id, "excel")
            st.markdown(
                f'<a href="{excel_url}" target="_blank">📊 Download Excel</a>',
                unsafe_allow_html=True,
            )

        with col_dl2:
            pdf_url = api_get_download_url(session_id, "pdf")
            st.markdown(
                f'<a href="{pdf_url}" target="_blank">📄 Download PDF</a>',
                unsafe_allow_html=True,
            )

        if result.get("requires_tech_lead_review"):
            st.error(
                "⚠️ **Tech Lead Review Required**\n\n"
                "This process exceeds standard XL parameters. "
                "Additional sizing from a Tech Lead is required."
            )

    st.divider()

    if st.button("🔄 Start New Assessment", type="primary", use_container_width=True):
        st.session_state["page"] = "upload"
        st.session_state["session_id"] = None
        st.session_state["result"] = None
        st.session_state["file_name"] = None
        st.session_state["poll_count"] = 0
        st.rerun()
