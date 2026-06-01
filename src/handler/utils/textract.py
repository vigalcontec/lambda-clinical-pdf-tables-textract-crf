"""AWS Textract utility functions for table extraction."""

import time
import uuid
from typing import Any

import boto3
from aws_lambda_powertools import Logger, Tracer

logger = Logger()
tracer = Tracer()

textract_client = boto3.client("textract")
s3_client = boto3.client("s3")


@tracer.capture_method
def extract_tables_sync(pdf_bytes: bytes) -> dict[str, Any]:
    """Extract tables using synchronous Textract API.

    Note: Sync API is restrictive with PDF formats. Use async API for better compatibility.

    Args:
        pdf_bytes: PDF content to analyze (PNG/JPEG work best)

    Returns:
        Textract analysis results
    """
    response = textract_client.analyze_document(
        Document={"Bytes": pdf_bytes},
        FeatureTypes=["TABLES"],
    )
    return dict(response)


@tracer.capture_method
def upload_temp_pdf_to_s3(pdf_bytes: bytes, bucket: str, prefix: str = "textract-temp") -> str:
    """Upload PDF to S3 for async Textract processing.

    Args:
        pdf_bytes: PDF content to upload
        bucket: S3 bucket name
        prefix: S3 key prefix for temp files

    Returns:
        S3 key of uploaded file
    """
    temp_key = f"{prefix}/{uuid.uuid4()}.pdf"
    s3_client.put_object(Bucket=bucket, Key=temp_key, Body=pdf_bytes)
    logger.info("Uploaded temp PDF to S3", extra={"bucket": bucket, "key": temp_key})
    return temp_key


@tracer.capture_method
def delete_temp_pdf_from_s3(bucket: str, key: str) -> None:
    """Delete temporary PDF from S3 after processing.

    Args:
        bucket: S3 bucket name
        key: S3 object key
    """
    try:
        s3_client.delete_object(Bucket=bucket, Key=key)
        logger.info("Deleted temp PDF from S3", extra={"bucket": bucket, "key": key})
    except Exception as e:
        logger.warning(f"Failed to delete temp PDF: {e}", extra={"bucket": bucket, "key": key})


@tracer.capture_method
def start_textract_analysis(bucket: str, key: str) -> str:
    """Start async Textract table analysis from S3 document.

    Args:
        bucket: S3 bucket containing the PDF
        key: S3 object key

    Returns:
        Textract job ID
    """
    response = textract_client.start_document_analysis(
        DocumentLocation={"S3Object": {"Bucket": bucket, "Name": key}},
        FeatureTypes=["TABLES"],
    )
    job_id: str = response["JobId"]
    logger.info("Started Textract job", extra={"job_id": job_id, "bucket": bucket, "key": key})
    return job_id


@tracer.capture_method
def wait_for_textract_completion(job_id: str, max_wait_seconds: int = 300) -> dict[str, Any]:
    """Wait for Textract job to complete and return all results (with pagination).

    Args:
        job_id: Textract job ID
        max_wait_seconds: Maximum time to wait for completion

    Returns:
        Textract analysis results with all blocks from all pages
    """
    start_time = time.time()

    # Wait for job to complete
    while True:
        response = textract_client.get_document_analysis(JobId=job_id)
        status = response["JobStatus"]

        if status == "SUCCEEDED":
            logger.info("Textract job completed", extra={"job_id": job_id})
            break
        elif status == "FAILED":
            error_msg = response.get("StatusMessage", "Unknown error")
            raise RuntimeError(f"Textract job failed: {error_msg}")
        elif status in ("IN_PROGRESS", "PARTIAL_SUCCESS"):
            elapsed = time.time() - start_time
            if elapsed > max_wait_seconds:
                raise TimeoutError(f"Textract job timed out after {max_wait_seconds}s")
            time.sleep(2)
        else:
            raise RuntimeError(f"Unknown Textract status: {status}")

    # Collect all blocks from all pages (handle pagination)
    all_blocks = response.get("Blocks", [])
    next_token = response.get("NextToken")

    while next_token:
        logger.info("Fetching next page of Textract results", extra={"job_id": job_id})
        response = textract_client.get_document_analysis(JobId=job_id, NextToken=next_token)
        all_blocks.extend(response.get("Blocks", []))
        next_token = response.get("NextToken")

    logger.info(
        "Collected all Textract blocks",
        extra={"job_id": job_id, "total_blocks": len(all_blocks)},
    )

    # Return response with all blocks combined
    response["Blocks"] = all_blocks
    return dict(response)


@tracer.capture_method
def parse_textract_tables(textract_response: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse Textract response to extract structured table data.

    Args:
        textract_response: Raw Textract response

    Returns:
        List of tables with rows and cells
    """
    blocks = textract_response.get("Blocks", [])

    # Build block lookup
    block_map: dict[str, dict] = {block["Id"]: block for block in blocks}

    # Find all TABLE blocks
    tables = []
    for block in blocks:
        if block["BlockType"] == "TABLE":
            table_data = _extract_table_data(block, block_map)
            tables.append(table_data)

    return tables


def _extract_table_data(table_block: dict, block_map: dict[str, dict]) -> dict[str, Any]:
    """Extract structured data from a TABLE block.

    Args:
        table_block: Textract TABLE block
        block_map: Lookup map of all blocks by ID

    Returns:
        Structured table data with rows and cells
    """
    rows: dict[int, dict[int, str]] = {}

    # Get all CELL blocks that belong to this table
    relationships = table_block.get("Relationships", [])
    for rel in relationships:
        if rel["Type"] == "CHILD":
            for cell_id in rel["Ids"]:
                cell_block = block_map.get(cell_id)
                if cell_block and cell_block["BlockType"] == "CELL":
                    row_idx = cell_block.get("RowIndex", 1)
                    col_idx = cell_block.get("ColumnIndex", 1)
                    cell_text = _get_cell_text(cell_block, block_map)

                    if row_idx not in rows:
                        rows[row_idx] = {}
                    rows[row_idx][col_idx] = cell_text

    # Convert to list of rows
    if not rows:
        return {"rows": [], "row_count": 0, "column_count": 0}

    max_row = max(rows.keys())
    max_col = max(max(cols.keys()) for cols in rows.values()) if rows else 0

    table_rows = []
    for row_idx in range(1, max_row + 1):
        row_data = []
        for col_idx in range(1, max_col + 1):
            cell_text = rows.get(row_idx, {}).get(col_idx, "")
            row_data.append(cell_text)
        table_rows.append(row_data)

    return {
        "rows": table_rows,
        "row_count": max_row,
        "column_count": max_col,
        "confidence": table_block.get("Confidence", 0),
    }


def _get_cell_text(cell_block: dict, block_map: dict[str, dict]) -> str:
    """Extract text content from a CELL block.

    Args:
        cell_block: Textract CELL block
        block_map: Lookup map of all blocks by ID

    Returns:
        Cell text content
    """
    text_parts = []
    relationships = cell_block.get("Relationships", [])

    for rel in relationships:
        if rel["Type"] == "CHILD":
            for word_id in rel["Ids"]:
                word_block = block_map.get(word_id)
                if word_block and word_block["BlockType"] in ("WORD", "SELECTION_ELEMENT"):
                    if word_block["BlockType"] == "WORD":
                        text_parts.append(word_block.get("Text", ""))
                    elif word_block["BlockType"] == "SELECTION_ELEMENT":
                        # Checkbox: SELECTED or NOT_SELECTED
                        status = word_block.get("SelectionStatus", "")
                        text_parts.append("[X]" if status == "SELECTED" else "[ ]")

    return " ".join(text_parts)
