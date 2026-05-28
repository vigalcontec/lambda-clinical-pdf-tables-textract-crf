"""DynamoDB utility functions for job tracking and table record updates."""

from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

import boto3
from aws_lambda_powertools import Logger, Tracer

logger = Logger()
tracer = Tracer()


@lru_cache
def _get_dynamodb_resource() -> Any:
    """Get cached DynamoDB resource."""
    return boto3.resource("dynamodb")


@tracer.capture_method
def increment_tables_processed(
    table_name: str,
    job_id: str,
) -> None:
    """Increment tables_processed counter for a job.

    Args:
        table_name: DynamoDB table name
        job_id: Job identifier
    """
    if not table_name:
        logger.warning("DynamoDB table name not configured, skipping update")
        return

    table = _get_dynamodb_resource().Table(table_name)
    now = datetime.now(UTC).isoformat()

    logger.info("Incrementing tables_processed", extra={"job_id": job_id})
    table.update_item(
        Key={"PK": f"JOB#{job_id}", "SK": "METADATA"},
        UpdateExpression="SET tables_processed = tables_processed + :inc, updated_at = :now",
        ExpressionAttributeValues={
            ":inc": 1,
            ":now": now,
        },
    )


@tracer.capture_method
def increment_tables_failed(
    table_name: str,
    job_id: str,
    error_message: str | None = None,
) -> None:
    """Increment tables_failed counter for a job.

    Args:
        table_name: DynamoDB table name
        job_id: Job identifier
        error_message: Optional error message to store
    """
    if not table_name:
        logger.warning("DynamoDB table name not configured, skipping update")
        return

    table = _get_dynamodb_resource().Table(table_name)
    now = datetime.now(UTC).isoformat()

    update_expr = "SET tables_failed = tables_failed + :inc, updated_at = :now"
    expr_values: dict[str, Any] = {
        ":inc": 1,
        ":now": now,
    }

    # Optionally store last error message
    if error_message:
        update_expr += ", last_error = :error"
        expr_values[":error"] = error_message

    logger.info("Incrementing tables_failed", extra={"job_id": job_id})
    table.update_item(
        Key={"PK": f"JOB#{job_id}", "SK": "METADATA"},
        UpdateExpression=update_expr,
        ExpressionAttributeValues=expr_values,
    )


@tracer.capture_method
def create_table_record(
    table_name: str,
    job_id: str,
    table_number: int,
    page: int,
    product_name: str,
    table_title: str,
    table_data: dict[str, Any] | None,
    status: str = "SUCCESS",
    error_message: str | None = None,
    ttl_days: int = 90,
) -> dict[str, Any] | None:
    """Create or update a table extraction record in DynamoDB.

    Args:
        table_name: DynamoDB table name
        job_id: Job identifier
        table_number: Table number in the document
        page: Page number where table was found
        product_name: Product name
        table_title: Table title/name
        table_data: Extracted table data (rows, columns, confidence)
        status: Extraction status (SUCCESS, FAILED)
        error_message: Error message if status is FAILED
        ttl_days: Days until record expires (default 90)

    Returns:
        The created DynamoDB item or None if table_name not configured
    """
    if not table_name:
        logger.warning("DynamoDB table name not configured, skipping record creation")
        return None

    table = _get_dynamodb_resource().Table(table_name)
    now = datetime.now(UTC)
    ttl = int(now.timestamp()) + (ttl_days * 24 * 60 * 60)

    item: dict[str, Any] = {
        "PK": f"JOB#{job_id}",
        "SK": f"TABLE#{table_number}#PAGE#{page}",
        "job_id": job_id,
        "table_number": table_number,
        "page": page,
        "product_name": product_name,
        "table_name": table_title,
        "status": status,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "ttl": ttl,
    }

    if table_data:
        item["row_count"] = table_data.get("row_count", 0)
        item["column_count"] = table_data.get("column_count", 0)
        item["confidence"] = table_data.get("confidence", 0)
        # Store table rows as JSON (DynamoDB supports nested structures)
        item["table_rows"] = table_data.get("rows", [])

    if error_message:
        item["error_message"] = error_message

    logger.info(
        "Creating table record",
        extra={
            "job_id": job_id,
            "table_number": table_number,
            "page": page,
            "status": status,
        },
    )
    table.put_item(Item=item)

    return item
