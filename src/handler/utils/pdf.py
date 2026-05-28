"""PDF utility functions using PyMuPDF."""

import io

import fitz  # PyMuPDF
from aws_lambda_powertools import Logger, Tracer

logger = Logger()
tracer = Tracer()


@tracer.capture_method
def extract_pages_as_pdf(pdf_bytes: bytes, pages: list[int]) -> bytes:
    """Extract specific pages from a PDF and return as new PDF bytes.

    Args:
        pdf_bytes: Original PDF content
        pages: List of 1-indexed page numbers to extract

    Returns:
        New PDF containing only the specified pages
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    new_doc = fitz.open()

    for page_num in pages:
        # Convert 1-indexed to 0-indexed
        page_idx = page_num - 1
        if 0 <= page_idx < len(doc):
            new_doc.insert_pdf(doc, from_page=page_idx, to_page=page_idx)
        else:
            logger.warning(f"Page {page_num} out of range (total: {len(doc)})")

    # Save to bytes
    pdf_buffer = io.BytesIO()
    new_doc.save(pdf_buffer)
    new_doc.close()
    doc.close()

    pdf_buffer.seek(0)
    return pdf_buffer.read()


@tracer.capture_method
def flatten_pages(pages: list[int | list[int]]) -> list[int]:
    """Flatten page groups into a single list of page numbers.

    Args:
        pages: List of page numbers or page groups (e.g., [7, 8, [16, 17, 18]])

    Returns:
        Flat list of page numbers (e.g., [7, 8, 16, 17, 18])
    """
    result = []
    for item in pages:
        if isinstance(item, list):
            result.extend(item)
        else:
            result.append(item)
    return sorted(set(result))
