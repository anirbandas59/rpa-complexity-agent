"""Results page — Assessment results display."""

import json

import pandas as pd
import plotly.express as px
import streamlit as st

# ── Domain constants (frontend-only, mirrors weight_matrix.json) ─────────────

_WEIGHTS: dict[str, dict[str, int]] = {
    "activities": {"XS": 2, "S": 2, "M": 4, "L": 6, "XL": 8},
    "business_rules": {"XS": 2, "S": 2, "M": 4, "L": 6, "XL": 8},
    "layouts": {"XS": 1, "S": 1, "M": 2, "L": 3, "XL": 4},
    "interfaces": {"XS": 1, "S": 1, "M": 2, "L": 3, "XL": 4},
    "technology": {"XS": 1, "S": 1, "M": 2, "L": 3, "XL": 4},
}

# Attribute display order matches scoring sheet
_ATTR_DEFS: list[tuple[str, str]] = [
    ("activities", "#1 Activities"),
    ("business_rules", "#2 Business Rules"),
    ("layouts", "#3 Digital Layouts"),
    ("interfaces", "#4 Target Interfaces"),
    ("technology", "#5 Add. Technology"),
]

_TIERS = ["XS", "S", "M", "L", "XL"]

# Colors match complexity_gauge.TIER_COLORS
_TIER_COLORS: dict[str, str] = {
    "XS": "#22c55e",
    "S": "#84cc16",
    "M": "#eab308",
    "L": "#f97316",
    "XL": "#ef4444",
}


# ── Helpers ───────────────────────────────────────────────────────────────────


def _extract_tier(val) -> str:
    """Extract a tier string from an attribute value (dict or bare string)."""
    if isinstance(val, dict):
        t = val.get("tier", "")
        if t in _TIERS:
            return t
    if isinstance(val, str) and val in _TIERS:
        return val
    return "M"  # safe default


def _classify(score: int, all_xs: bool) -> str:
    """Reproduce the backend classification bands for the frontend recalculator."""
    if all_xs:
        return "XS"
    if score <= 8:
        return "S"
    if score <= 15:
        return "M"
    if score <= 22:
        return "L"
    return "XL"


# ── Page ──────────────────────────────────────────────────────────────────────


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

    # Complexity tier badge (pill, score shown below label)
    from frontend.components.complexity_gauge import render_tier_badge

    render_tier_badge(tier, score)

    st.divider()

    # ── Two-column layout ─────────────────────────────────────────────────────
    col_left, col_right = st.columns([3, 2])

    with col_left:
        st.subheader("📊 Attribute Score Breakdown")

        # Build and display attributes table
        attrs_list = []
        if raw_attrs:
            if "activities" in raw_attrs:
                attrs_list.append(("#1 Activities", raw_attrs["activities"]))
            if "business_rules" in raw_attrs:
                attrs_list.append(("#2 Business Rules", raw_attrs["business_rules"]))
            if "layouts" in raw_attrs:
                attrs_list.append(("#3 Digital Layouts", raw_attrs["layouts"]))
            if "interfaces" in raw_attrs:
                attrs_list.append(("#4 Target Interfaces", raw_attrs["interfaces"]))
            if "technology" in raw_attrs:
                attrs_list.append(("#5 Add. Technology", raw_attrs["technology"]))

        if attrs_list:
            attrs_df = pd.DataFrame(attrs_list, columns=["Attribute", "Value"])
            st.dataframe(attrs_df, hide_index=True, use_container_width=True)

        # ── Attribute weight bar chart ────────────────────────────────────────
        chart_rows = []
        for key, label in _ATTR_DEFS:
            if key in raw_attrs:
                attr_tier = _extract_tier(raw_attrs[key])
                weight = _WEIGHTS[key].get(attr_tier, 0)
                chart_rows.append(
                    {"Attribute": label, "Weight": weight, "Tier": attr_tier}
                )

        if chart_rows:
            chart_df = pd.DataFrame(chart_rows)
            # Preserve natural display order (top = first attribute)
            attr_order = [r["Attribute"] for r in reversed(chart_rows)]

            fig = px.bar(
                chart_df,
                x="Weight",
                y="Attribute",
                orientation="h",
                color="Tier",
                color_discrete_map=_TIER_COLORS,
                category_orders={
                    "Attribute": attr_order,
                    "Tier": _TIERS,
                },
                range_x=[0, 8],
                labels={"Weight": "Weight Contribution", "Attribute": ""},
                title="Attribute Weight Contributions",
            )
            fig.update_layout(
                height=280,
                margin={"t": 40, "b": 20, "l": 0, "r": 0},
                legend_title_text="Tier",
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
            )
            fig.update_xaxes(dtick=1, gridcolor="rgba(128,128,128,0.2)")
            fig.update_yaxes(gridcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig, use_container_width=True)

        # ── Adjust & Recalculate expander ─────────────────────────────────────
        with st.expander("🔧 Adjust & Recalculate"):
            st.caption(
                "Override attribute tiers to explore how a different assessment "
                "would score. No API call is made — results are computed locally."
            )

            adj_cols = st.columns(5)
            selections: dict[str, str] = {}
            for i, (key, label) in enumerate(_ATTR_DEFS):
                with adj_cols[i]:
                    attr_data = raw_attrs.get(key, {})
                    current_tier = _extract_tier(attr_data)
                    selections[key] = st.selectbox(
                        label,
                        options=_TIERS,
                        index=_TIERS.index(current_tier),
                        key=f"_adj_{key}",
                    )

            if st.button("Recalculate", key="_recalc_btn", type="primary"):
                new_score = sum(_WEIGHTS[k].get(v, 0) for k, v in selections.items())
                all_xs = all(v == "XS" for v in selections.values())
                new_tier = _classify(new_score, all_xs)
                st.session_state["_recalc"] = {
                    "score": new_score,
                    "tier": new_tier,
                }

            recalc = st.session_state.get("_recalc")
            if recalc:
                st.success(
                    f"Adjusted score: **{recalc['score']}/28** → "
                    f"Tier: **{recalc['tier']}**"
                )
                render_tier_badge(recalc["tier"], recalc["score"])

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
        col_dl1, col_dl2, col_dl3 = st.columns(3)
        session_id = st.session_state.get("session_id", "")

        with col_dl1:
            from frontend.app import api_get_download_url

            excel_url = api_get_download_url(session_id, "excel")
            st.markdown(
                f'<a href="{excel_url}" target="_blank">📊 Excel</a>',
                unsafe_allow_html=True,
            )

        with col_dl2:
            pdf_url = api_get_download_url(session_id, "pdf")
            st.markdown(
                f'<a href="{pdf_url}" target="_blank">📄 PDF</a>',
                unsafe_allow_html=True,
            )

        with col_dl3:
            result_json = json.dumps(
                st.session_state.get("result", {}), indent=2, default=str
            )
            st.download_button(
                label="📋 JSON",
                data=result_json,
                file_name=f"assessment_{session_id}.json",
                mime="application/json",
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
        st.session_state.pop("_recalc", None)
        st.rerun()
