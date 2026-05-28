"""Pytest fixtures and configuration."""

import os

# Set AWS region before importing any modules that use boto3
os.environ["AWS_DEFAULT_REGION"] = "eu-west-1"
os.environ["AWS_REGION"] = "eu-west-1"

# Disable X-Ray tracing before importing any modules
os.environ["POWERTOOLS_TRACE_DISABLED"] = "true"

# Set DynamoDB table name for tests
os.environ["DYNAMODB_TABLE_NAME"] = "test-clinical-pdf-jobs"

from collections.abc import Generator  # noqa: E402
from typing import Any  # noqa: E402
from unittest.mock import patch  # noqa: E402

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def env_vars() -> Generator[None, None, None]:
    """Set environment variables for tests."""
    with patch.dict(
        os.environ,
        {
            "ENVIRONMENT": "dev",
            "AWS_REGION": "eu-west-1",
            "LOG_LEVEL": "INFO",
        },
    ):
        yield


@pytest.fixture
def lambda_event() -> dict[str, Any]:
    """Sample Lambda event for Textract extraction."""
    return {
        "s3_bucket": "test-bucket",
        "s3_key": "test/document.pdf",
        "pages": [1, 2, [3, 4, 5]],
    }


@pytest.fixture
def lambda_context() -> Any:
    """Mock Lambda context."""

    class MockContext:
        function_name = "test-function"
        memory_limit_in_mb = 512
        invoked_function_arn = "arn:aws:lambda:eu-west-1:123456789012:function:test"
        aws_request_id = "test-request-id"

    return MockContext()


@pytest.fixture
def sample_pdf_bytes() -> bytes:
    """Minimal valid PDF bytes for testing."""
    # Minimal PDF structure
    return b"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj
xref
0 4
0000000000 65535 f 
0000000009 00000 n 
0000000052 00000 n 
0000000101 00000 n 
trailer<</Size 4/Root 1 0 R>>
startxref
172
%%EOF"""


@pytest.fixture
def textract_response() -> dict[str, Any]:
    """Sample Textract response with table data."""
    return {
        "Blocks": [
            {
                "Id": "table-1",
                "BlockType": "TABLE",
                "Confidence": 99.5,
                "Relationships": [
                    {"Type": "CHILD", "Ids": ["cell-1", "cell-2", "cell-3", "cell-4"]}
                ],
            },
            {
                "Id": "cell-1",
                "BlockType": "CELL",
                "RowIndex": 1,
                "ColumnIndex": 1,
                "Relationships": [{"Type": "CHILD", "Ids": ["word-1"]}],
            },
            {
                "Id": "cell-2",
                "BlockType": "CELL",
                "RowIndex": 1,
                "ColumnIndex": 2,
                "Relationships": [{"Type": "CHILD", "Ids": ["word-2"]}],
            },
            {
                "Id": "cell-3",
                "BlockType": "CELL",
                "RowIndex": 2,
                "ColumnIndex": 1,
                "Relationships": [{"Type": "CHILD", "Ids": ["word-3"]}],
            },
            {
                "Id": "cell-4",
                "BlockType": "CELL",
                "RowIndex": 2,
                "ColumnIndex": 2,
                "Relationships": [{"Type": "CHILD", "Ids": ["word-4"]}],
            },
            {"Id": "word-1", "BlockType": "WORD", "Text": "Header1"},
            {"Id": "word-2", "BlockType": "WORD", "Text": "Header2"},
            {"Id": "word-3", "BlockType": "WORD", "Text": "Value1"},
            {"Id": "word-4", "BlockType": "WORD", "Text": "Value2"},
        ]
    }
