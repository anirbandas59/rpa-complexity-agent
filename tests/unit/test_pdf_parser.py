"""Tests for tools.document.pdf_parser module.

Tests cover file validation, text extraction, table extraction,
metadata extraction, and ParsedDocument model compliance.
"""

from pathlib import Path
import pytest
import tempfile

from tools.document.pdf_parser import parse_pdf
from core.models.document import ParsedDocument
from core.exceptions import DocumentProcessingError


# ==================== FIXTURES ====================


@pytest.fixture
def sample_simple_pdf() -> Path:
    """Path to sample_simple.pdf test fixture."""
    path = Path(__file__).parent.parent.parent / "data" / "sample_pdds" / "sample_simple.pdf"
    assert path.exists(), f"Test fixture not found: {path}"
    return path


@pytest.fixture
def sample_table_pdf() -> Path:
    """Path to sample_table.pdf test fixture."""
    path = Path(__file__).parent.parent.parent / "data" / "sample_pdds" / "sample_table.pdf"
    assert path.exists(), f"Test fixture not found: {path}"
    return path


@pytest.fixture
def empty_pdf() -> Path:
    """Create a temporary empty PDF file."""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        return Path(f.name)


@pytest.fixture
def empty_file() -> Path:
    """Create a temporary empty non-PDF file."""
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
        return Path(f.name)


# ==================== FILE VALIDATION TESTS ====================


def test_parse_pdf_file_not_found():
    """Test that parse_pdf raises DocumentProcessingError for non-existent file."""
    with pytest.raises(DocumentProcessingError) as exc_info:
        parse_pdf("/nonexistent/path/to/file.pdf")

    assert "not found" in str(exc_info.value).lower()
    assert "file_path" in exc_info.value.context


def test_parse_pdf_not_pdf_extension(empty_file: Path):
    """Test that parse_pdf raises DocumentProcessingError for non-PDF files."""
    try:
        with pytest.raises(DocumentProcessingError) as exc_info:
            parse_pdf(str(empty_file))

        assert "not a pdf" in str(exc_info.value).lower()
        assert "extension" in exc_info.value.context
    finally:
        empty_file.unlink()


def test_parse_pdf_empty_file(empty_pdf: Path):
    """Test that parse_pdf raises DocumentProcessingError for empty PDF files."""
    try:
        with pytest.raises(DocumentProcessingError) as exc_info:
            parse_pdf(str(empty_pdf))

        assert "empty" in str(exc_info.value).lower()
    finally:
        empty_pdf.unlink()


# ==================== SUCCESSFUL PARSING TESTS ====================


def test_parse_pdf_returns_parsed_document(sample_simple_pdf: Path):
    """Test that parse_pdf returns a ParsedDocument instance."""
    result = parse_pdf(str(sample_simple_pdf))
    assert isinstance(result, ParsedDocument)


def test_parse_pdf_source_path_is_absolute(sample_simple_pdf: Path):
    """Test that source_path in ParsedDocument is an absolute path string."""
    result = parse_pdf(str(sample_simple_pdf))
    assert isinstance(result.source_path, str)
    assert result.source_path.startswith("/")
    # Verify it's absolute
    assert Path(result.source_path).is_absolute()


def test_parse_pdf_file_type_is_pdf(sample_simple_pdf: Path):
    """Test that file_type is set to 'pdf'."""
    result = parse_pdf(str(sample_simple_pdf))
    assert result.file_type == "pdf"


def test_parse_pdf_full_text_not_empty(sample_simple_pdf: Path):
    """Test that full_text is non-empty."""
    result = parse_pdf(str(sample_simple_pdf))
    assert result.full_text
    assert isinstance(result.full_text, str)
    assert len(result.full_text) > 0


def test_parse_pdf_full_text_contains_expected_content(sample_simple_pdf: Path):
    """Test that full_text contains expected content from fixture."""
    result = parse_pdf(str(sample_simple_pdf))
    # The fixture content includes "SAP" and "Process"
    full_text_lower = result.full_text.lower()
    assert "sap" in full_text_lower or "process" in full_text_lower


def test_parse_pdf_page_count_is_two(sample_simple_pdf: Path):
    """Test that page_count is 2 for sample_simple.pdf."""
    result = parse_pdf(str(sample_simple_pdf))
    assert result.page_count == 2


def test_parse_pdf_metadata_is_dict(sample_simple_pdf: Path):
    """Test that metadata is a dict and contains expected keys."""
    result = parse_pdf(str(sample_simple_pdf))
    assert isinstance(result.metadata, dict)
    # page_count and file_size_bytes should be added
    assert "page_count" in result.metadata
    assert "file_size_bytes" in result.metadata


def test_parse_pdf_extraction_warnings_is_list(sample_simple_pdf: Path):
    """Test that extraction_warnings is a list."""
    result = parse_pdf(str(sample_simple_pdf))
    assert isinstance(result.extraction_warnings, list)


# ==================== TEXT EXTRACTION TESTS ====================


def test_parse_pdf_page_markers_in_text(sample_simple_pdf: Path):
    """Test that full_text contains page markers."""
    result = parse_pdf(str(sample_simple_pdf))
    assert "--- Page 1 ---" in result.full_text
    assert "--- Page 2 ---" in result.full_text


def test_parse_pdf_word_count_above_threshold(sample_simple_pdf: Path):
    """Test that word_count is above 50 for sample_simple.pdf."""
    result = parse_pdf(str(sample_simple_pdf))
    assert result.word_count() > 50


def test_parse_pdf_word_count_returns_integer(sample_simple_pdf: Path):
    """Test that word_count() returns an integer."""
    result = parse_pdf(str(sample_simple_pdf))
    count = result.word_count()
    assert isinstance(count, int)
    assert count > 0


# ==================== TABLE EXTRACTION TESTS ====================


def test_parse_pdf_tables_is_list(sample_table_pdf: Path):
    """Test that tables is a list."""
    result = parse_pdf(str(sample_table_pdf))
    assert isinstance(result.tables, list)


def test_parse_pdf_tables_non_empty(sample_table_pdf: Path):
    """Test that tables list is non-empty for sample_table.pdf."""
    result = parse_pdf(str(sample_table_pdf))
    assert len(result.tables) > 0, "sample_table.pdf should contain at least one table"


def test_parse_pdf_tables_are_list_of_dicts(sample_table_pdf: Path):
    """Test that each table is a list of dicts with string keys."""
    result = parse_pdf(str(sample_table_pdf))
    if result.tables:
        # tables is a list of tables
        for table in result.tables:
            assert isinstance(table, list), "Each table should be a list of rows"
            # Each row should be a dict
            for row in table:
                assert isinstance(row, dict), "Each row should be a dict"
                for key, value in row.items():
                    assert isinstance(key, str), "Dict keys should be strings"
                    assert isinstance(value, str), "Dict values should be strings"


def test_parse_pdf_table_structure(sample_table_pdf: Path):
    """Test that tables have expected structure for sample_table.pdf."""
    result = parse_pdf(str(sample_table_pdf))
    if result.tables:
        # At least one table with at least 3 rows (3 data rows + 1 header = 4 total)
        for table in result.tables:
            assert len(table) >= 3, "Table should have at least 3 data rows"
            # Check that headers are consistent
            first_row_keys = set(table[0].keys())
            for row in table[1:]:
                assert set(row.keys()) == first_row_keys, "All rows should have same keys"


# ==================== PARSED DOCUMENT MODEL TESTS ====================


def test_parsed_document_is_valid(sample_simple_pdf: Path):
    """Test that ParsedDocument.is_valid() returns True for sample_simple.pdf."""
    result = parse_pdf(str(sample_simple_pdf))
    assert result.is_valid() is True


def test_parsed_document_word_count_method(sample_simple_pdf: Path):
    """Test that ParsedDocument.word_count() returns correct value."""
    result = parse_pdf(str(sample_simple_pdf))
    word_count = result.word_count()
    expected = len(result.full_text.split())
    assert word_count == expected


def test_parsed_document_model_config(sample_simple_pdf: Path):
    """Test that ParsedDocument model is correctly configured."""
    result = parse_pdf(str(sample_simple_pdf))
    # Should be able to access attributes
    assert hasattr(result, "source_path")
    assert hasattr(result, "file_type")
    assert hasattr(result, "full_text")
    assert hasattr(result, "tables")
    assert hasattr(result, "page_count")
    assert hasattr(result, "metadata")
    assert hasattr(result, "extraction_warnings")


# ==================== INTEGRATION TESTS ====================


def test_parse_pdf_full_workflow_simple(sample_simple_pdf: Path):
    """Test full workflow: parse simple PDF and validate all fields."""
    result = parse_pdf(str(sample_simple_pdf))

    # Validate all fields are present and correctly typed
    assert isinstance(result.source_path, str)
    assert isinstance(result.file_type, str)
    assert isinstance(result.full_text, str)
    assert isinstance(result.tables, list)
    assert isinstance(result.page_count, int)
    assert isinstance(result.metadata, dict)
    assert isinstance(result.extraction_warnings, list)

    # Validate constraints
    assert result.source_path != ""
    assert result.file_type == "pdf"
    assert result.full_text != ""
    assert result.page_count == 2
    assert result.is_valid()


def test_parse_pdf_full_workflow_table(sample_table_pdf: Path):
    """Test full workflow: parse PDF with tables and validate extraction."""
    result = parse_pdf(str(sample_table_pdf))

    # Validate PDF was parsed
    assert result.page_count > 0
    assert result.word_count() > 0

    # Validate tables were extracted
    assert isinstance(result.tables, list)
    if result.tables:
        assert all(isinstance(t, list) for t in result.tables)


def test_parse_pdf_metadata_contains_file_info(sample_simple_pdf: Path):
    """Test that metadata contains file-level information."""
    result = parse_pdf(str(sample_simple_pdf))

    # Check for file-level metadata added by the parser
    assert "page_count" in result.metadata
    assert "file_size_bytes" in result.metadata

    # Values should be strings
    assert isinstance(result.metadata["page_count"], str)
    assert isinstance(result.metadata["file_size_bytes"], str)

    # page_count should match document page count
    assert int(result.metadata["page_count"]) == result.page_count
