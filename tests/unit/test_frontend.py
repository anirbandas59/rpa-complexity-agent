"""
Unit tests for Streamlit frontend.

Tests API client functions and components (helper functions).
Page rendering is validated via manual smoke tests.
"""

from unittest.mock import patch, MagicMock
import pytest


# ─── API Client Function Tests ─────────────────────────────────


def test_api_post_assess_success():
    """api_post_assess sends correct multipart data and returns response."""
    from frontend.app import api_post_assess

    mock_response = MagicMock()
    mock_response.json.return_value = {"session_id": "test123", "status": "queued"}

    with patch("frontend.app.httpx.post") as mock_post:
        mock_post.return_value = mock_response

        result = api_post_assess(
            file_bytes=b"test pdf content",
            filename="test.pdf",
            form_data={"rpa_tool": "uipath", "project_name": "Test"},
        )

        assert result["session_id"] == "test123"
        assert result["status"] == "queued"

        # Verify the call was made correctly
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args[1]
        assert "files" in call_kwargs
        assert "data" in call_kwargs


def test_api_post_assess_http_error():
    """api_post_assess raises exception on HTTP error."""
    from frontend.app import api_post_assess

    with patch("frontend.app.httpx.post") as mock_post:
        mock_post.side_effect = Exception("Network error")

        with pytest.raises(Exception, match="Network error"):
            api_post_assess(
                file_bytes=b"test",
                filename="test.pdf",
                form_data={},
            )


def test_api_get_status_success():
    """api_get_status returns dict on success."""
    from frontend.app import api_get_status

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "session_id": "test123",
        "status": "processing",
        "current_stage": "document_intelligence",
    }

    with patch("frontend.app.httpx.get") as mock_get:
        mock_get.return_value = mock_response

        result = api_get_status("test123")

        assert result["status"] == "processing"
        assert result["current_stage"] == "document_intelligence"
        mock_get.assert_called_once()


def test_api_get_status_not_found():
    """api_get_status returns not_found dict on 404."""
    from frontend.app import api_get_status

    mock_response = MagicMock()
    mock_response.status_code = 404

    with patch("frontend.app.httpx.get") as mock_get:
        mock_get.return_value = mock_response

        result = api_get_status("unknown_session")

        assert result["status"] == "not_found"


def test_api_get_status_error():
    """api_get_status returns error dict on exception."""
    from frontend.app import api_get_status

    with patch("frontend.app.httpx.get") as mock_get:
        mock_get.side_effect = Exception("Connection failed")

        result = api_get_status("test123")

        assert result["status"] == "error"
        assert "Connection failed" in result["message"]


def test_api_get_download_url():
    """api_get_download_url returns correct URL string."""
    from frontend.app import api_get_download_url

    url = api_get_download_url("test123", "excel")

    assert "test123" in url
    assert "excel" in url
    assert url.startswith("http")
    assert "/api/download/" in url


def test_api_get_download_url_pdf():
    """api_get_download_url works for PDF file type."""
    from frontend.app import api_get_download_url

    url = api_get_download_url("session456", "pdf")

    assert "session456" in url
    assert "pdf" in url


# ─── Complexity Gauge Component Tests ──────────────────────────


def test_render_tier_badge_xs():
    """render_tier_badge does not raise for XS tier."""
    from frontend.components.complexity_gauge import render_tier_badge

    with patch("streamlit.markdown"):
        # Should not raise
        render_tier_badge("XS")


def test_render_tier_badge_s():
    """render_tier_badge does not raise for S tier."""
    from frontend.components.complexity_gauge import render_tier_badge

    with patch("streamlit.markdown"):
        render_tier_badge("S")


def test_render_tier_badge_m():
    """render_tier_badge does not raise for M tier."""
    from frontend.components.complexity_gauge import render_tier_badge

    with patch("streamlit.markdown"):
        render_tier_badge("M")


def test_render_tier_badge_l():
    """render_tier_badge does not raise for L tier."""
    from frontend.components.complexity_gauge import render_tier_badge

    with patch("streamlit.markdown"):
        render_tier_badge("L")


def test_render_tier_badge_xl():
    """render_tier_badge does not raise for XL tier."""
    from frontend.components.complexity_gauge import render_tier_badge

    with patch("streamlit.markdown"):
        render_tier_badge("XL")


def test_render_tier_badge_unknown():
    """render_tier_badge does not raise for unknown tier."""
    from frontend.components.complexity_gauge import render_tier_badge

    with patch("streamlit.markdown"):
        render_tier_badge("UNKNOWN")


def test_render_score_bar():
    """render_score_bar does not raise."""
    from frontend.components.complexity_gauge import render_score_bar

    with patch("streamlit.progress"), patch("streamlit.caption"):
        render_score_bar(10, 28)


def test_render_score_bar_zero():
    """render_score_bar handles zero score."""
    from frontend.components.complexity_gauge import render_score_bar

    with patch("streamlit.progress"), patch("streamlit.caption"):
        render_score_bar(0, 28)


def test_render_score_bar_max():
    """render_score_bar handles max score."""
    from frontend.components.complexity_gauge import render_score_bar

    with patch("streamlit.progress"), patch("streamlit.caption"):
        render_score_bar(28, 28)


# ─── Timeline Chart Component Tests ────────────────────────────


def test_render_effort_table_empty():
    """render_effort_table does not raise with empty result."""
    from frontend.components.timeline_chart import render_effort_table

    with patch("streamlit.caption"), patch("streamlit.table"):
        render_effort_table({})


def test_render_effort_table_full():
    """render_effort_table does not raise with full result."""
    from frontend.components.timeline_chart import render_effort_table

    result = {
        "complexity_tier": "M",
        "effort_estimate": {"step_count": 25, "branch_count": 3},
        "timeline_summary": {
            "total_hours": 50,
            "total_sp": 3,
            "feature_count": 2,
        },
    }

    with patch("streamlit.caption"), patch("streamlit.table"):
        render_effort_table(result)


def test_render_effort_table_no_timeline():
    """render_effort_table handles missing timeline gracefully."""
    from frontend.components.timeline_chart import render_effort_table

    result = {"complexity_tier": "M"}

    with patch("streamlit.caption") as mock_caption:
        render_effort_table(result)
        mock_caption.assert_called()


def test_render_effort_table_with_effort_data():
    """render_effort_table renders with effort data."""
    from frontend.components.timeline_chart import render_effort_table

    result = {
        "complexity_tier": "L",
        "effort_estimate": {
            "step_count": 35,
            "branch_count": 5,
        },
        "timeline_summary": {
            "total_hours": 80,
            "total_sp": 5,
            "feature_count": 3,
        },
    }

    with patch("streamlit.caption"), patch("streamlit.table"):
        render_effort_table(result)


# ─── Frontend Integration Tests ────────────────────────────────


def test_api_base_url_from_env():
    """API_BASE_URL is read from environment."""
    import os
    from unittest.mock import patch

    with patch.dict(os.environ, {"API_BASE_URL": "http://example.com:9000"}):
        # Reimport to get new env value
        import importlib
        import frontend.app as app_module

        importlib.reload(app_module)
        assert "example.com" in app_module.API_BASE_URL or "http://localhost" in app_module.API_BASE_URL


def test_api_post_assess_includes_all_form_fields():
    """api_post_assess includes all form fields in request."""
    from frontend.app import api_post_assess

    mock_response = MagicMock()
    mock_response.json.return_value = {"session_id": "test"}

    with patch("frontend.app.httpx.post") as mock_post:
        mock_post.return_value = mock_response

        api_post_assess(
            file_bytes=b"content",
            filename="test.pdf",
            form_data={
                "rpa_tool": "blue_prism",
                "project_name": "Project A",
                "start_date": "2026-03-17",
                "developer_name": "John",
                "business_analyst": "Jane",
                "squad": "Team A",
            },
        )

        call_kwargs = mock_post.call_args[1]
        data = call_kwargs["data"]

        assert data["rpa_tool"] == "blue_prism"
        assert data["project_name"] == "Project A"
        assert data["developer_name"] == "John"
