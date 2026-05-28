"""AWS Lambda Handler - Clinical PDF Tables Textract Extractor.

This Lambda function extracts a specific table from a PDF page using AWS Textract.
It receives the S3 path to a PDF, table metadata (name, page, index), and extracts
the specified table using Textract.
"""

from typing import Any

from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.utilities.typing import LambdaContext

from handler.config import get_settings
from handler.utils import (
    create_table_record,
    delete_temp_pdf_from_s3,
    download_pdf_from_s3,
    extract_pages_as_pdf,
    flatten_pages,
    increment_tables_failed,
    increment_tables_processed,
    parse_textract_tables,
    start_textract_analysis,
    upload_temp_pdf_to_s3,
    wait_for_textract_completion,
)

logger = Logger()
tracer = Tracer()


def _extract_job_id_from_events_key(events_s3_key: str | None) -> str | None:
    """Extract job_id from the events S3 key.

    The events file is named like: {pdf_name}_events.json
    The job_id is derived from the PDF file hash, which is stored in DynamoDB.
    For now, we derive it from the events key path structure.

    Example:
        events_s3_key: "crf/clinical_pdfs/keytruda/20260522164300/keytruda-epar_events.json"
        Returns the hash of the PDF path (same logic as locator lambda)
    """
    if not events_s3_key:
        return None

    # The events key follows pattern: {path}/{pdf_name}_events.json
    # We need to reconstruct the original PDF key to get the job_id
    # For simplicity, we use the directory path as a unique identifier
    # The actual job_id should be passed from Step Functions

    # Extract directory path (everything before the filename)
    parts = events_s3_key.rsplit("/", 1)
    if len(parts) == 2:
        # Use the directory path as job identifier
        import hashlib
        return hashlib.sha256(parts[0].encode()).hexdigest()
    return None


@logger.inject_lambda_context(log_event=True)
@tracer.capture_lambda_handler
def handler(event: dict[str, Any], _context: LambdaContext) -> dict[str, Any]:
    """Lambda handler for PDF table extraction using Textract.

    Expected event payload from Step Function Distributed Map:
        {
            "s3_bucket": "bucket-name",
            "s3_key": "path/to/document.pdf",
            "product_name": "keytruda",
            "table_name": "Table 6: Efficacy results...",
            "table_number": 6,
            "page": 32,
            "table_index_on_page": 0
        }

    Returns:
        {
            "status": "SUCCESS",
            "s3_bucket": "bucket-name",
            "s3_key": "path/to/document.pdf",
            "product_name": "keytruda",
            "table_name": "Table 6: Efficacy results...",
            "table_number": 6,
            "pages_processed": [32],
            "table_index_on_page": 0,
            "table": {
                "rows": [["Header1", "Header2"], ["Value1", "Value2"]],
                "row_count": 2,
                "column_count": 2,
                "confidence": 98.5
            }
        }
    """
    settings = get_settings()
    logger.info("Starting Textract extraction", extra={"environment": settings.environment})

    # Extract job_id for DynamoDB tracking
    events_s3_key = event.get("events_s3_key")
    job_id = _extract_job_id_from_events_key(events_s3_key)
    dynamodb_table = settings.dynamodb_table_name

    try:
        # Validate input contract
        bucket = event.get("s3_bucket")
        key = event.get("s3_key")
        product_name = event.get("product_name", "")
        table_name = event.get("table_name", "")
        table_number = event.get("table_number")
        table_index = event.get("table_index_on_page", 0)

        # Support both "page" (singular from Step Functions) and "pages" (array)
        page = event.get("page")
        pages = event.get("pages", [])
        if page is not None and not pages:
            pages = [page]

        if not bucket or not key:
            raise ValueError("Missing 's3_bucket' or 's3_key' in event payload.")

        if not pages:
            logger.warning("No pages specified, returning empty result")
            return {
                "status": "SUCCESS",
                "s3_bucket": bucket,
                "s3_key": key,
                "product_name": product_name,
                "table_name": table_name,
                "table_number": table_number,
                "pages_processed": [],
                "table_index_on_page": table_index,
                "table": None,
            }

        # Flatten page groups (usually single page now)
        flat_pages = flatten_pages(pages)
        logger.info(
            f"Processing document: s3://{bucket}/{key}",
            extra={
                "pages": flat_pages,
                "product_name": product_name,
                "table_name": table_name,
                "table_index": table_index,
            },
        )

        # Download full PDF
        pdf_bytes = download_pdf_from_s3(bucket, key)

        if len(pdf_bytes) == 0:
            raise ValueError(f"Downloaded PDF is empty. Check if file exists at s3://{bucket}/{key}")

        logger.info("PDF downloaded", extra={"size_bytes": len(pdf_bytes)})

        # Extract only the pages we need
        extracted_pdf = extract_pages_as_pdf(pdf_bytes, flat_pages)
        logger.info(
            "Extracted pages to new PDF",
            extra={"extracted_size_bytes": len(extracted_pdf), "pages": flat_pages},
        )

        # Upload extracted PDF to S3 for async Textract processing
        # (Async API has better PDF format support than sync API)
        temp_key = upload_temp_pdf_to_s3(extracted_pdf, bucket, prefix="textract-temp")

        try:
            # Start async Textract analysis
            logger.info("Starting asynchronous Textract analysis")
            job_id = start_textract_analysis(bucket, temp_key)
            textract_response = wait_for_textract_completion(job_id)

            # Parse all tables from response
            all_tables = parse_textract_tables(textract_response)
        finally:
            # Clean up temp file
            delete_temp_pdf_from_s3(bucket, temp_key)

        # Select the specific table by index
        if table_index < len(all_tables):
            selected_table = all_tables[table_index]
        else:
            logger.warning(
                f"Table index {table_index} out of range. Found {len(all_tables)} tables.",
                extra={"table_index": table_index, "tables_found": len(all_tables)},
            )
            selected_table = None

        logger.info(
            "Textract extraction completed",
            extra={
                "tables_found": len(all_tables),
                "table_index_selected": table_index,
                "pages_processed": flat_pages,
            },
        )

        # Update DynamoDB: increment processed counter and create table record
        if job_id and dynamodb_table:
            try:
                increment_tables_processed(dynamodb_table, job_id)
                create_table_record(
                    table_name=dynamodb_table,
                    job_id=job_id,
                    table_number=table_number or 0,
                    page=flat_pages[0] if flat_pages else 0,
                    product_name=product_name,
                    table_title=table_name,
                    table_data=selected_table,
                    status="SUCCESS",
                )
            except Exception as db_error:
                logger.warning(
                    "Failed to update DynamoDB",
                    extra={"error": str(db_error), "job_id": job_id},
                )

        return {
            "status": "SUCCESS",
            "s3_bucket": bucket,
            "s3_key": key,
            "product_name": product_name,
            "table_name": table_name,
            "table_number": table_number,
            "pages_processed": flat_pages,
            "table_index_on_page": table_index,
            "tables_found_on_page": len(all_tables),
            "table": selected_table,
        }

    except Exception as e:
        logger.exception("Error processing event")

        # Update DynamoDB: increment failed counter
        if job_id and dynamodb_table:
            try:
                increment_tables_failed(dynamodb_table, job_id, str(e))
                # Also create a failed table record for tracking
                create_table_record(
                    table_name=dynamodb_table,
                    job_id=job_id,
                    table_number=event.get("table_number") or 0,
                    page=event.get("page") or 0,
                    product_name=event.get("product_name", ""),
                    table_title=event.get("table_name", ""),
                    table_data=None,
                    status="FAILED",
                    error_message=str(e),
                )
            except Exception as db_error:
                logger.warning(
                    "Failed to update DynamoDB on error",
                    extra={"error": str(db_error), "job_id": job_id},
                )

        return {
            "status": "FAILED",
            "error": str(e),
            "s3_bucket": event.get("s3_bucket"),
            "s3_key": event.get("s3_key"),
            "product_name": event.get("product_name"),
            "table_name": event.get("table_name"),
            "table_number": event.get("table_number"),
        }


if __name__ == "__main__":
    import os
    import sys
    os.environ.setdefault("POWERTOOLS_TRACE_DISABLED", "true")

    # Test with local file if provided as argument
    if len(sys.argv) > 1:
        local_pdf_path = sys.argv[1]
        pages_arg = sys.argv[2] if len(sys.argv) > 2 else "1"

        # Parse pages argument (e.g., "1,2,3" or "1-5")
        test_pages = []
        for part in pages_arg.split(","):
            if "-" in part:
                start, end = map(int, part.split("-"))
                test_pages.extend(range(start, end + 1))
            else:
                test_pages.append(int(part))

        print(f"Testing with local file: {local_pdf_path}")
        print(f"Pages to extract: {test_pages}")

        with open(local_pdf_path, "rb") as f:
            pdf_bytes = f.read()

        print(f"PDF size: {len(pdf_bytes)} bytes")

        # Extract pages
        extracted_pdf = extract_pages_as_pdf(pdf_bytes, test_pages)
        print(f"Extracted PDF size: {len(extracted_pdf)} bytes")

        # Note: Textract requires AWS credentials
        print("\nTo test Textract extraction, run in AWS environment or with valid credentials.")

    else:
        import json

        # Mock Lambda context for local testing
        class MockContext:
            function_name = "local-test"
            memory_limit_in_mb = 256
            invoked_function_arn = "arn:aws:lambda:eu-west-1:123456789012:function:local-test"
            aws_request_id = "local-request-id"

        # Test event from Step Functions Distributed Map
        # Note: Step Functions sends "page" (singular), handler converts to "pages" array
        # events_s3_key is used to derive job_id for DynamoDB tracking
        test_event = {
            "s3_bucket": "datalake-raw-vigalcontec-dev-002332700133",
            "s3_key": "crf/clinical_pdfs/keytruda/20260522164300/keytruda-epar-product-information_en.pdf",
            "product_name": "keytruda",
            "table_name": "Table 7: Efficacy results by BRAF mutation status in KEYNOTE-006",
            "table_number": 7,
            "page": 32,
            "table_index_on_page": 1,
            "events_s3_key": "crf/clinical_pdfs/keytruda/20260522164300/keytruda-epar-product-information_en_events.json"
        }

        print(f"\n{'='*60}")
        print(f"Testing: {test_event['table_name']}")
        print(f"Page: {test_event['page']}, Table Index: {test_event['table_index_on_page']}")
        print(f"{'='*60}")
        result = handler(test_event, MockContext())
        print(json.dumps(result, indent=2, ensure_ascii=False))

