"""Tests for tools.document.docx_parser module.

Tests cover file validation, text extraction with heading markers,
table extraction, metadata extraction, and ParsedDocument model compliance.
Also verifies schema consistency with parse_pdf.
"""

from pathlib import Path
import tempfile
import pytest

from tools.document.docx_parser import parse_docx
from tools.document.pdf_parser import parse_pdf
from core.models.document import ParsedDocument
from core.exceptions import DocumentProcessingError


# ==================== FIXTURES ====================


@pytest.fixture
def sample_process_docx() -> Path:
    """Path to sample_process.docx test fixture."""
    path = Path(__file__).parent.parent / "fixtures" / "sample_process.docx"
    assert path.exists(), f"Test fixture not found: {path}"
    return path


@pytest.fixture
def empty_docx() -> Path:
    """Create a temporary empty DOCX file."""
    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
        return Path(f.name)


@pytest.fixture
def empty_file() -> Path:
    """Create a temporary empty non-DOCX file."""
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
        return Path(f.name)


# ==================== FILE VALIDATION TESTS ====================


def test_parse_docx_file_not_found():
    """Test that parse_docx raises DocumentProcessingError for non-existent file."""
    with pytest.raises(DocumentProcessingError) as exc_info:
        parse_docx("/nonexistent/path/to/file.docx")

    assert "not found" in str(exc_info.value).lower()
    assert "file_path" in exc_info.value.context


def test_parse_docx_not_docx_extension(empty_file: Path):
    """Test that parse_docx raises DocumentProcessingError for non-DOCX files."""
    try:
        with pytest.raises(DocumentProcessingError) as exc_info:
            parse_docx(str(empty_file))

        assert "not a docx" in str(exc_info.value).lower()
        assert "extension" in exc_info.value.context
    finally:
        empty_file.unlink()


def test_parse_docx_empty_file(empty_docx: Path):
    """Test that parse_docx raises DocumentProcessingError for empty DOCX files."""
    try:
        with pytest.raises(DocumentProcessingError) as exc_info:
            parse_docx(str(empty_docx))

        assert "empty" in str(exc_info.value).lower()
    finally:
        empty_docx.unlink()


# ==================== SUCCESSFUL PARSING TESTS ====================


def test_parse_docx_returns_parsed_document(sample_process_docx: Path):
    """Test that parse_docx returns a ParsedDocument instance."""
    result = parse_docx(str(sample_process_docx))
    assert isinstance(result, ParsedDocument)


def test_parse_docx_file_type_is_docx(sample_process_docx: Path):
    """Test that file_type is set to 'docx'."""
    result = parse_docx(str(sample_process_docx))
    assert result.file_type == "docx"


def test_parse_docx_source_path_is_absolute(sample_process_docx: Path):
    """Test that source_path is an absolute path string."""
    result = parse_docx(str(sample_process_docx))
    assert isinstance(result.source_path, str)
    assert result.source_path.startswith("/")
    assert Path(result.source_path).is_absolute()


def test_parse_docx_full_text_not_empty(sample_process_docx: Path):
    """Test that full_text is non-empty string."""
    result = parse_docx(str(sample_process_docx))
    assert result.full_text
    assert isinstance(result.full_text, str)
    assert len(result.full_text) > 0


def test_parse_docx_full_text_contains_sap(sample_process_docx: Path):
    """Test that full_text contains expected content from fixture."""
    result = parse_docx(str(sample_process_docx))
    assert "SAP" in result.full_text


def test_parse_docx_word_count_above_threshold(sample_process_docx: Path):
    """Test that word_count is above 100."""
    result = parse_docx(str(sample_process_docx))
    assert result.word_count() > 100


# ==================== STRUCTURE PRESERVATION TESTS ====================


def test_parse_docx_contains_heading_1_markers(sample_process_docx: Path):
    """Test that full_text contains Heading 1 markers (===)."""
    result = parse_docx(str(sample_process_docx))
    assert "===" in result.full_text


def test_parse_docx_contains_heading_2_markers(sample_process_docx: Path):
    """Test that full_text contains Heading 2 markers (---)."""
    result = parse_docx(str(sample_process_docx))
    assert "---" in result.full_text


def test_parse_docx_contains_heading_text_process_overview(sample_process_docx: Path):
    """Test that Heading 1 text is preserved."""
    result = parse_docx(str(sample_process_docx))
    assert "Process Overview" in result.full_text


def test_parse_docx_contains_heading_text_process_steps(sample_process_docx: Path):
    """Test that another Heading 1 text is preserved."""
    result = parse_docx(str(sample_process_docx))
    assert "Process Steps" in result.full_text


def test_parse_docx_contains_business_rules_heading(sample_process_docx: Path):
    """Test that Business Rules section heading is preserved."""
    result = parse_docx(str(sample_process_docx))
    assert "Business Rules" in result.full_text


# ==================== TABLE EXTRACTION TESTS ====================


def test_parse_docx_tables_is_list(sample_process_docx: Path):
    """Test that tables is a list."""
    result = parse_docx(str(sample_process_docx))
    assert isinstance(result.tables, list)


def test_parse_docx_tables_non_empty(sample_process_docx: Path):
    """Test that tables is non-empty for sample_process.docx."""
    result = parse_docx(str(sample_process_docx))
    assert len(result.tables) > 0, "sample_process.docx should contain at least one table"


def test_parse_docx_first_table_has_data_rows(sample_process_docx: Path):
    """Test that first table has at least 4 data rows."""
    result = parse_docx(str(sample_process_docx))
    assert len(result.tables[0]) >= 4, "First table should have at least 4 data rows"


def test_parse_docx_table_entries_are_dicts(sample_process_docx: Path):
    """Test that each table entry is a dict."""
    result = parse_docx(str(sample_process_docx))
    for table in result.tables:
        assert isinstance(table, list)
        for row in table:
            assert isinstance(row, dict)


def test_parse_docx_table_contains_step_key(sample_process_docx: Path):
    """Test that table contains 'Step' key (from fixture header)."""
    result = parse_docx(str(sample_process_docx))
    first_table = result.tables[0]
    assert len(first_table) > 0
    assert "Step" in first_table[0], "Table should have 'Step' column"


# ==================== METADATA TESTS ====================


def test_parse_docx_metadata_is_dict(sample_process_docx: Path):
    """Test that metadata is a dict."""
    result = parse_docx(str(sample_process_docx))
    assert isinstance(result.metadata, dict)


def test_parse_docx_metadata_contains_paragraph_count(sample_process_docx: Path):
    """Test that metadata contains paragraph_count."""
    result = parse_docx(str(sample_process_docx))
    assert "paragraph_count" in result.metadata


def test_parse_docx_metadata_contains_table_count(sample_process_docx: Path):
    """Test that metadata contains table_count."""
    result = parse_docx(str(sample_process_docx))
    assert "table_count" in result.metadata


def test_parse_docx_metadata_contains_file_size(sample_process_docx: Path):
    """Test that metadata contains file_size_bytes."""
    result = parse_docx(str(sample_process_docx))
    assert "file_size_bytes" in result.metadata


def test_parse_docx_metadata_contains_page_count_estimated_flag(sample_process_docx: Path):
    """Test that metadata contains page_count_estimated flag."""
    result = parse_docx(str(sample_process_docx))
    assert "page_count_estimated" in result.metadata
    assert result.metadata["page_count_estimated"] == "true"


# ==================== PAGE COUNT ESTIMATION TESTS ====================


def test_parse_docx_page_count_is_estimated(sample_process_docx: Path):
    """Test that page_count is estimated (>= 1)."""
    result = parse_docx(str(sample_process_docx))
    assert result.page_count >= 1


def test_parse_docx_page_count_based_on_word_count(sample_process_docx: Path):
    """Test that page_count estimation is reasonable (250 words per page)."""
    result = parse_docx(str(sample_process_docx))
    word_count = result.word_count()
    expected_pages = max(1, word_count // 250)
    assert result.page_count == expected_pages


# ==================== PARSED DOCUMENT MODEL TESTS ====================


def test_parsed_document_is_valid(sample_process_docx: Path):
    """Test that ParsedDocument.is_valid() returns True."""
    result = parse_docx(str(sample_process_docx))
    assert result.is_valid() is True


def test_parsed_document_extraction_warnings_is_list(sample_process_docx: Path):
    """Test that extraction_warnings is a list."""
    result = parse_docx(str(sample_process_docx))
    assert isinstance(result.extraction_warnings, list)


# ==================== SCHEMA CONSISTENCY TESTS ====================


def test_parse_pdf_and_docx_return_same_model_type(sample_process_docx: Path):
    """Test that both parsers return ParsedDocument instances."""
    docx_result = parse_docx(str(sample_process_docx))
    assert isinstance(docx_result, ParsedDocument)

    # Both should be ParsedDocument
    assert hasattr(docx_result, "file_type")
    assert hasattr(docx_result, "full_text")
    assert hasattr(docx_result, "tables")
    assert hasattr(docx_result, "page_count")
    assert hasattr(docx_result, "metadata")
    assert hasattr(docx_result, "extraction_warnings")


def test_parse_pdf_and_docx_file_type_set_correctly():
    """Test that both parsers set file_type correctly."""
    sample_pdf = Path(__file__).parent.parent / "fixtures" / "sample_simple.pdf"
    sample_docx = Path(__file__).parent.parent / "fixtures" / "sample_process.docx"

    if sample_pdf.exists():
        pdf_result = parse_pdf(str(sample_pdf))
        assert pdf_result.file_type == "pdf"

    if sample_docx.exists():
        docx_result = parse_docx(str(sample_docx))
        assert docx_result.file_type == "docx"


def test_parse_docx_tables_structure_matches_schema(sample_process_docx: Path):
    """Test that tables structure matches list[list[dict[str, Any]]] schema."""
    result = parse_docx(str(sample_process_docx))

    # tables should be a list
    assert isinstance(result.tables, list)

    # Each element should be a list (table)
    for table in result.tables:
        assert isinstance(table, list)
        # Each row should be a dict
        for row in table:
            assert isinstance(row, dict)
            # Keys and values should be strings
            for key, value in row.items():
                assert isinstance(key, str)
                assert isinstance(value, str)


def test_parse_docx_metadata_all_strings(sample_process_docx: Path):
    """Test that all metadata values are strings (schema requirement)."""
    result = parse_docx(str(sample_process_docx))

    for key, value in result.metadata.items():
        assert isinstance(value, str), f"Metadata[{key}] should be string, got {type(value)}"


# ==================== INTEGRATION TESTS ====================


def test_parse_docx_full_workflow(sample_process_docx: Path):
    """Test full workflow: parse DOCX and validate all fields."""
    result = parse_docx(str(sample_process_docx))

    # Validate all fields present and correctly typed
    assert isinstance(result.source_path, str)
    assert isinstance(result.file_type, str)
    assert isinstance(result.full_text, str)
    assert isinstance(result.tables, list)
    assert isinstance(result.page_count, int)
    assert isinstance(result.metadata, dict)
    assert isinstance(result.extraction_warnings, list)

    # Validate field constraints
    assert result.source_path != ""
    assert result.file_type == "docx"
    assert result.full_text != ""
    assert result.page_count >= 1
    assert result.is_valid()
    assert result.word_count() > 0
