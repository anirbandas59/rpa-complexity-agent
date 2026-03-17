"""Timeline chart component — Effort and timeline display."""

import pandas as pd
import streamlit as st


def render_effort_table(result: dict) -> None:
    """
    Render effort estimate summary table.

    Args:
        result: Assessment result dict
    """
    effort = result.get("effort_estimate", {})
    timeline = result.get("timeline_summary", {})

    if not timeline:
        st.caption("Effort data not available")
        return

    tier = result.get("complexity_tier", "Unknown")

    # Simple effort summary
    st.caption(f"Effort estimate for {tier} tier complexity")

    # Build effort data table
    effort_data = {
        "Phase": [
            "Define",
            "Design & Build",
            "UAT",
            "Deploy",
            "**Total**",
        ],
        "Status": [
            "See Excel report",
            "See Excel report",
            "See Excel report",
            "See Excel report",
            "Complete",
        ],
    }

    effort_df = pd.DataFrame(effort_data)
    st.table(effort_df)

    # Summary metrics
    total_hours = timeline.get("total_hours", 0)
    total_sp = timeline.get("total_sp", 0)
    feature_count = timeline.get("feature_count", 0)

    summary_text = (
        f"**Total Effort:** {total_hours:.0f}h / {total_sp:.1f} SP / {feature_count} features"
    )
    st.caption(summary_text)
