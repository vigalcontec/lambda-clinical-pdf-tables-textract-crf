"""Utility modules."""

from handler.utils.dynamodb import (
    create_table_record,
    increment_tables_failed,
    increment_tables_processed,
)
from handler.utils.pdf import extract_pages_as_pdf, flatten_pages
from handler.utils.s3 import download_pdf_from_s3
from handler.utils.ssm import get_parameter, get_parameters_by_path
from handler.utils.textract import (
    delete_temp_pdf_from_s3,
    extract_tables_sync,
    parse_textract_tables,
    start_textract_analysis,
    upload_temp_pdf_to_s3,
    wait_for_textract_completion,
)

__all__ = [
    # S3
    "download_pdf_from_s3",
    # PDF
    "extract_pages_as_pdf",
    "flatten_pages",
    # Textract
    "extract_tables_sync",
    "upload_temp_pdf_to_s3",
    "delete_temp_pdf_from_s3",
    "start_textract_analysis",
    "wait_for_textract_completion",
    "parse_textract_tables",
    # SSM
    "get_parameter",
    "get_parameters_by_path",
    # DynamoDB
    "increment_tables_processed",
    "increment_tables_failed",
    "create_table_record",
]
