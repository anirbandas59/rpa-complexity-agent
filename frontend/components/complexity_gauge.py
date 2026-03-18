"""Complexity gauge component — Tier badge visualization."""

from typing import Optional

import streamlit as st

# Canonical color map shared with results.py bar chart
TIER_COLORS: dict[str, str] = {
    "XS": "#22c55e",
    "S": "#84cc16",
    "M": "#eab308",
    "L": "#f97316",
    "XL": "#ef4444",
}

_TIER_STYLES: dict[str, dict] = {
    "XS": {"bg": "#22c55e", "text": "#1a1a1a", "label": "Extra Small"},
    "S": {"bg": "#84cc16", "text": "#1a1a1a", "label": "Small"},
    "M": {"bg": "#eab308", "text": "#1a1a1a", "label": "Medium"},
    "L": {"bg": "#f97316", "text": "#ffffff", "label": "Large"},
    "XL": {"bg": "#ef4444", "text": "#ffffff", "label": "Extra Large"},
}


def render_tier_badge(tier: str, score: Optional[int] = None) -> None:
    """
    Render a large colored pill badge for the complexity tier.

    Args:
        tier:  Complexity tier label (XS, S, M, L, XL).
        score: Optional numeric score to display beneath the label.
    """
    style = _TIER_STYLES.get(
        tier, {"bg": "#808080", "text": "#ffffff", "label": "Unknown"}
    )

    score_html = (
        f'<div style="font-size:16px;font-weight:600;margin-top:6px;opacity:0.85;">'
        f"{score}/28"
        f"</div>"
        if score is not None
        else ""
    )

    st.markdown(
        f"""
        <div style="
            background-color:{style['bg']};
            color:{style['text']};
            padding:24px 40px;
            border-radius:100px;
            text-align:center;
            font-size:52px;
            font-weight:bold;
            margin:20px 0;
            box-shadow:0 4px 12px rgba(0,0,0,0.15);
            width:100%;
            box-sizing:border-box;
        ">
            {tier}
            <div style="font-size:18px;font-weight:normal;margin-top:8px;">
                {style['label']} Complexity
            </div>
            {score_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_score_bar(score: int, max_score: int = 28) -> None:
    """
    Render a visual progress bar showing score position with tier boundaries.

    Args:
        score:     Current score.
        max_score: Maximum possible score (default 28).
    """
    st.progress(score / max_score)
    st.caption("Tier boundaries: S(7) | M(9) | L(16) | XL(23)")
