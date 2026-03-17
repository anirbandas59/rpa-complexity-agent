"""
PDF document parser using PyMuPDF (fitz) and pdfplumber.

Extracts text, tables, and metadata from PDF documents.
Primary text extraction via fitz; table extraction via pdfplumber.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF
import pdfplumber

from config.logging_config import get_logger
from core.exceptions import DocumentProcessingError
from core.models.document import ParsedDocument

logger = get_logger("pdf_parser")


def parse_pdf(file_path: str) -> ParsedDocument:
    """
    Parse a PDF document and extract text, tables, and metadata.

    STEP 1: File validation
    STEP 2: Open document with fitz
    STEP 3: Check encryption status
    STEP 4: Extract metadata
    STEP 5: Extract text (page by page)
    STEP 6: Extract tables (using pdfplumber)
    STEP 7: Build and return ParsedDocument

    Args:
        file_path: Path to the PDF file to parse

    Returns:
        ParsedDocument: Parsed document model with all extracted content

    Raises:
        DocumentProcessingError: If file validation fails, opening fails,
                                or document is encrypted
    """
    path = Path(file_path)

    # STEP 1: FILE VALIDATION
    _validate_pdf_file(path)

    doc = None
    pdfplumber_doc = None

    try:
        # STEP 2: OPEN DOCUMENT
        try:
            doc = fitz.open(str(path))
            logger.info(f"Opened PDF: {path}")
        except Exception as e:
            raise DocumentProcessingError(
                message=f"Failed to open PDF: {path}",
                context={"error": str(e), "file_path": str(path)},
            )

        # STEP 3: ENCRYPTION CHECK
        if doc.is_encrypted:
            logger.warning(f"PDF is encrypted, attempting to authenticate: {path}")
            if not doc.authenticate(""):
                raise DocumentProcessingError(
                    message=f"PDF is encrypted and cannot be processed: {path}",
                    context={"file_path": str(path)},
                )
            logger.info("Successfully authenticated with empty password")

        # STEP 4: EXTRACT METADATA
        metadata = _extract_metadata(doc, path)

        # STEP 5: EXTRACT TEXT
        full_text, extraction_warnings = _extract_text(doc)

        # STEP 6: EXTRACT TABLES
        tables = _extract_tables(path, extraction_warnings)

        # STEP 7: BUILD AND RETURN ParsedDocument
        parsed_doc = ParsedDocument(
            source_path=str(path.absolute()),
            file_type="pdf",
            full_text=full_text,
            tables=tables,
            page_count=len(doc),
            metadata=metadata,
            extraction_warnings=extraction_warnings,
        )

        logger.info(
            f"Successfully parsed PDF: {path} "
            f"({len(doc)} pages, {parsed_doc.word_count()} words)"
        )
        return parsed_doc

    finally:
        # Close documents to prevent file handle leaks
        if doc is not None:
            doc.close()
        if pdfplumber_doc is not None:
            pdfplumber_doc.close()


def _validate_pdf_file(path: Path) -> None:
    """
    Validate PDF file before processing.

    Checks for:
    - File existence
    - PDF extension (.pdf, case-insensitive)
    - Non-empty file

    Args:
        path: Path object to validate

    Raises:
        DocumentProcessingError: If any validation check fails
    """
    # Check existence
    if not path.exists():
        raise DocumentProcessingError(
            message=f"PDF file not found: {path}",
            context={"file_path": str(path)},
        )

    # Check extension
    if path.suffix.lower() != ".pdf":
        raise DocumentProcessingError(
            message=f"File is not a PDF: {path}",
            context={"file_path": str(path), "extension": path.suffix},
        )

    # Check file size
    file_size = os.path.getsize(str(path))
    if file_size == 0:
        raise DocumentProcessingError(
            message=f"PDF file is empty: {path}",
            context={"file_path": str(path)},
        )

    logger.debug(f"File validation passed: {path} ({file_size} bytes)")


def _extract_metadata(doc: Any, path: Path) -> dict[str, str]:
    """
    Extract metadata from PDF document.

    Extracts author, title, subject, creator, producer,
    creationDate, modDate. Adds page_count and file_size_bytes.
    All values are converted to strings; None values are removed.

    Args:
        doc: fitz document object
        path: Path to the PDF file

    Returns:
        Dictionary with metadata (all string values)
    """
    metadata = {}

    # Extract fitz metadata
    fitz_meta = doc.metadata or {}

    # Map fitz keys to standard names
    for key in ["author", "title", "subject", "creator", "producer", "creationDate", "modDate"]:
        value = fitz_meta.get(key)
        cleaned = _clean_metadata_value(value)
        if cleaned is not None:
            metadata[key] = cleaned

    # Add file-level metadata
    metadata["page_count"] = str(doc.page_count)
    metadata["file_size_bytes"] = str(os.path.getsize(str(path)))

    logger.debug(f"Extracted metadata: {len(metadata)} fields")
    return metadata


def _clean_metadata_value(value: str | None) -> str | None:
    """
    Clean metadata value by stripping whitespace and removing empty strings.

    Args:
        value: Raw metadata value (may be None or string)

    Returns:
        Cleaned string or None if value is empty/None
    """
    if value is None:
        return None
    stripped = str(value).strip()
    return stripped if stripped else None


def _extract_text(doc: Any) -> tuple[str, list[str]]:
    """
    Extract text from all pages of a PDF document.

    Adds page markers (--- Page N ---) between pages.
    Tracks warnings for empty pages (image-based content).

    Args:
        doc: fitz document object

    Returns:
        Tuple of (full_text, extraction_warnings)
    """
    full_text_parts = []
    warnings = []

    for page_num in range(len(doc)):
        try:
            page = doc[page_num]
            text = page.get_text("text")

            if not text.strip():
                warnings.append(
                    f"Page {page_num + 1} contains no extractable text — "
                    "may be image-based"
                )

            # Add page marker and text
            page_marker = f"\n--- Page {page_num + 1} ---\n"
            full_text_parts.append(page_marker)
            full_text_parts.append(text)

        except Exception as e:
            warnings.append(f"Failed to extract text from page {page_num + 1}: {e}")

    full_text = "".join(full_text_parts)
    logger.debug(f"Extracted text: {len(full_text)} characters, {len(warnings)} warnings")
    return full_text, warnings


def _extract_tables(path: Path, warnings: list[str]) -> list[list[dict[str, Any]]]:
    """
    Extract tables from PDF using pdfplumber.

    Handles failures gracefully by adding warnings and returning empty list.
    Does not raise exceptions on pdfplumber failures.

    Args:
        path: Path to the PDF file
        warnings: List to append warnings to (modified in place)

    Returns:
        List of tables (each table is a list of dicts)
    """
    tables = []

    try:
        pdfplumber_doc = pdfplumber.open(str(path))
        logger.debug(f"Opened PDF with pdfplumber: {path}")

        try:
            for page_idx, page in enumerate(pdfplumber_doc.pages):
                try:
                    raw_tables = page.extract_tables()
                    if not raw_tables:
                        continue

                    for raw_table in raw_tables:
                        if not raw_table:
                            continue

                        dict_table = _table_to_dict_list(raw_table)
                        if dict_table:  # Only add non-empty tables
                            tables.append(dict_table)

                except Exception as e:
                    warnings.append(f"Table extraction failed on page {page_idx + 1}: {e}")

        finally:
            pdfplumber_doc.close()

    except Exception as e:
        warnings.append(f"Table extraction failed: {e}")
        logger.warning(f"Table extraction failed for {path}: {e}")

    logger.debug(f"Extracted {len(tables)} tables")
    return tables


def _table_to_dict_list(raw_table: list[list[str | None]]) -> list[dict[str, str]]:
    """
    Convert a pdfplumber table (list of lists) to list of dicts.

    Uses first row as column headers. Skips rows with all None/empty cells.
    Replaces None cells with empty string. Generates column names for
    missing or empty headers.

    Args:
        raw_table: Raw table from pdfplumber (list of lists)

    Returns:
        List of dicts with string keys and values
    """
    if not raw_table:
        return []

    # Extract headers (first row)
    headers = raw_table[0]
    if not headers:
        return []

    # Clean and standardize headers
    clean_headers = []
    for idx, header in enumerate(headers):
        if header is None or str(header).strip() == "":
            clean_headers.append(f"column_{idx}")
        else:
            clean_headers.append(str(header).strip())

    # If only headers, no data rows
    if len(raw_table) == 1:
        return []

    # Convert rows to dicts
    result = []
    for row_idx in range(1, len(raw_table)):
        row = raw_table[row_idx]

        # Skip rows where all cells are None or empty
        if all(cell is None or str(cell).strip() == "" for cell in row):
            continue

        # Build dict, handling None cells
        row_dict = {}
        for col_idx, header in enumerate(clean_headers):
            cell_value = row[col_idx] if col_idx < len(row) else None
            row_dict[header] = "" if cell_value is None else str(cell_value).strip()

        result.append(row_dict)

    return result
