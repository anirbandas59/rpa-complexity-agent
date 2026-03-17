"""Complexity gauge component — Tier badge visualization."""

import streamlit as st


def render_tier_badge(tier: str) -> None:
    """
    Render a large colored tier badge.

    Args:
        tier: Complexity tier (XS, S, M, L, XL)
    """
    tier_styles = {
        "XS": {
            "bg": "#92D050",
            "text": "#1a1a1a",
            "label": "Extra Small",
        },
        "S": {
            "bg": "#70AD47",
            "text": "#ffffff",
            "label": "Small",
        },
        "M": {
            "bg": "#FFC000",
            "text": "#1a1a1a",
            "label": "Medium",
        },
        "L": {
            "bg": "#FF0000",
            "text": "#ffffff",
            "label": "Large",
        },
        "XL": {
            "bg": "#7030A0",
            "text": "#ffffff",
            "label": "Extra Large",
        },
    }

    style = tier_styles.get(tier, {"bg": "#808080", "text": "#ffffff", "label": "Unknown"})

    st.markdown(
        f"""
        <div style="
            background-color: {style['bg']};
            color: {style['text']};
            padding: 20px 40px;
            border-radius: 12px;
            text-align: center;
            font-size: 48px;
            font-weight: bold;
            margin: 20px 0;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        ">
            {tier}
            <div style="font-size: 18px; font-weight: normal; margin-top: 8px;">
                {style['label']} Complexity
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_score_bar(score: int, max_score: int = 28) -> None:
    """
    Render a visual progress bar showing score position with tier boundaries.

    Args:
        score: Current score
        max_score: Maximum possible score (default 28)
    """
    st.progress(score / max_score)
    st.caption("Tier boundaries: S(7) | M(9) | L(16) | XL(23)")
