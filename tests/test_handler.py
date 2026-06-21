"""Tests for Lambda handler."""

from typing import Any
from unittest.mock import MagicMock, patch

from handler.config import Settings, get_settings


class TestHandler:
    """Tests for main handler function."""

    @patch("handler.utils.textract.s3_client")
    @patch("handler.utils.s3.s3_client")
    @patch("handler.utils.textract.textract_client")
    def test_handler_success(
        self,
        mock_textract: MagicMock,
        mock_s3: MagicMock,
        mock_textract_s3: MagicMock,
        lambda_event: dict[str, Any],
        lambda_context: Any,
        sample_pdf_bytes: bytes,
        textract_response: dict[str, Any],
    ) -> None:
        """Test successful handler execution."""
        get_settings.cache_clear()

        # Mock S3 download
        mock_s3.get_object.return_value = {"Body": MagicMock(read=lambda: sample_pdf_bytes)}

        # Mock S3 upload for temp PDF (in textract module)
        mock_textract_s3.put_object.return_value = {}

        # Mock async Textract flow
        mock_textract.start_document_analysis.return_value = {"JobId": "test-job-123"}
        mock_textract.get_document_analysis.return_value = {
            "JobStatus": "SUCCEEDED",
            **textract_response,
        }

        from handler.main import handler

        result = handler(lambda_event, lambda_context)

        assert result["status"] == "SUCCESS"
        assert result["s3_bucket"] == "test-bucket"
        assert result["s3_key"] == "test/document.pdf"

    @patch("handler.utils.textract.s3_client")
    @patch("handler.utils.s3.s3_client")
    @patch("handler.utils.textract.textract_client")
    def test_handler_extracts_tables(
        self,
        mock_textract: MagicMock,
        mock_s3: MagicMock,
        mock_textract_s3: MagicMock,
        lambda_event: dict[str, Any],
        lambda_context: Any,
        sample_pdf_bytes: bytes,
        textract_response: dict[str, Any],
    ) -> None:
        """Test handler extracts table data correctly."""
        get_settings.cache_clear()

        mock_s3.get_object.return_value = {"Body": MagicMock(read=lambda: sample_pdf_bytes)}
        mock_textract_s3.put_object.return_value = {}
        mock_textract.start_document_analysis.return_value = {"JobId": "test-job-123"}
        mock_textract.get_document_analysis.return_value = {
            "JobStatus": "SUCCEEDED",
            **textract_response,
        }

        from handler.main import handler

        result = handler(lambda_event, lambda_context)

        assert result["status"] == "SUCCESS"
        assert result["table"] is not None
        table = result["table"]
        assert table["row_count"] == 2
        assert table["column_count"] == 2
        assert table["rows"][0] == ["Header1", "Header2"]
        assert table["rows"][1] == ["Value1", "Value2"]

    def test_handler_missing_bucket(self, lambda_context: Any) -> None:
        """Test handler with missing s3_bucket."""
        get_settings.cache_clear()

        from handler.main import handler

        result = handler({"s3_key": "test.pdf", "pages": [1]}, lambda_context)

        assert result["status"] == "FAILED"
        assert "s3_bucket" in result["error"]

    def test_handler_missing_key(self, lambda_context: Any) -> None:
        """Test handler with missing s3_key."""
        get_settings.cache_clear()

        from handler.main import handler

        result = handler({"s3_bucket": "bucket", "pages": [1]}, lambda_context)

        assert result["status"] == "FAILED"
        assert "s3_key" in result["error"]

    def test_handler_empty_pages(self, lambda_context: Any) -> None:
        """Test handler with empty pages list."""
        get_settings.cache_clear()

        from handler.main import handler

        result = handler(
            {"s3_bucket": "bucket", "s3_key": "test.pdf", "pages": []},
            lambda_context,
        )

        assert result["status"] == "SUCCESS"
        assert result["pages_processed"] == []
        assert result["table"] is None


class TestConfig:
    """Tests for configuration."""

    def test_get_settings_returns_settings(self) -> None:
        """Test get_settings returns Settings instance."""
        get_settings.cache_clear()
        settings = get_settings()

        assert isinstance(settings, Settings)

    def test_get_settings_cached(self) -> None:
        """Test get_settings returns cached instance."""
        get_settings.cache_clear()
        settings1 = get_settings()
        settings2 = get_settings()

        assert settings1 is settings2

    def test_settings_default_values(self) -> None:
        """Test Settings has correct default values."""
        get_settings.cache_clear()
        settings = get_settings()

        assert settings.environment == "dev"
        assert settings.aws_region == "eu-west-1"
        assert settings.log_level == "INFO"

    def test_settings_from_env(self) -> None:
        """Test Settings reads from environment variables."""
        import os
        from unittest.mock import patch

        with patch.dict(os.environ, {"ENVIRONMENT": "prod", "LOG_LEVEL": "DEBUG"}):
            get_settings.cache_clear()
            settings = get_settings()

            assert settings.environment == "prod"
            assert settings.log_level == "DEBUG"


class TestPDFUtils:
    """Tests for PDF utility functions."""

    def test_flatten_pages_simple(self) -> None:
        """Test flatten_pages with simple list."""
        from handler.utils.pdf import flatten_pages

        result = flatten_pages([1, 2, 3])
        assert result == [1, 2, 3]

    def test_flatten_pages_nested(self) -> None:
        """Test flatten_pages with nested lists."""
        from handler.utils.pdf import flatten_pages

        result = flatten_pages([1, 2, [3, 4, 5], 6])
        assert result == [1, 2, 3, 4, 5, 6]

    def test_flatten_pages_duplicates(self) -> None:
        """Test flatten_pages removes duplicates."""
        from handler.utils.pdf import flatten_pages

        result = flatten_pages([1, 2, [2, 3], 3])
        assert result == [1, 2, 3]

    def test_flatten_pages_empty(self) -> None:
        """Test flatten_pages with empty list."""
        from handler.utils.pdf import flatten_pages

        result = flatten_pages([])
        assert result == []

    def test_flatten_pages_sorted(self) -> None:
        """Test flatten_pages returns sorted list."""
        from handler.utils.pdf import flatten_pages

        result = flatten_pages([5, 1, [3, 2]])
        assert result == [1, 2, 3, 5]


class TestTextractUtils:
    """Tests for Textract utility functions."""

    def test_parse_textract_tables(self, textract_response: dict[str, Any]) -> None:
        """Test parse_textract_tables extracts table data."""
        from handler.utils.textract import parse_textract_tables

        tables = parse_textract_tables(textract_response)

        assert len(tables) == 1
        table = tables[0]
        assert table["row_count"] == 2
        assert table["column_count"] == 2
        assert table["confidence"] == 99.5
        assert table["rows"][0] == ["Header1", "Header2"]
        assert table["rows"][1] == ["Value1", "Value2"]

    def test_parse_textract_tables_empty(self) -> None:
        """Test parse_textract_tables with no tables."""
        from handler.utils.textract import parse_textract_tables

        result = parse_textract_tables({"Blocks": []})
        assert result == []

    def test_parse_textract_tables_no_blocks(self) -> None:
        """Test parse_textract_tables with missing Blocks key."""
        from handler.utils.textract import parse_textract_tables

        result = parse_textract_tables({})
        assert result == []

    @patch("handler.utils.textract.textract_client")
    def test_extract_tables_sync(self, mock_textract: MagicMock) -> None:
        """Test extract_tables_sync calls Textract API."""
        from handler.utils.textract import extract_tables_sync

        mock_textract.analyze_document.return_value = {"Blocks": []}

        result = extract_tables_sync(b"pdf-bytes")

        mock_textract.analyze_document.assert_called_once_with(
            Document={"Bytes": b"pdf-bytes"},
            FeatureTypes=["TABLES"],
        )
        assert result == {"Blocks": []}

    @patch("handler.utils.textract.textract_client")
    def test_start_textract_analysis(self, mock_textract: MagicMock) -> None:
        """Test start_textract_analysis starts async job."""
        from handler.utils.textract import start_textract_analysis

        mock_textract.start_document_analysis.return_value = {"JobId": "test-job-123"}

        job_id = start_textract_analysis("test-bucket", "test-key.pdf")

        assert job_id == "test-job-123"
        mock_textract.start_document_analysis.assert_called_once_with(
            DocumentLocation={"S3Object": {"Bucket": "test-bucket", "Name": "test-key.pdf"}},
            FeatureTypes=["TABLES", "LAYOUT"],
        )

    def test_extract_layout_titles(self) -> None:
        """Test extracting LAYOUT_TITLE blocks from Textract response."""
        from handler.utils.textract import _extract_layout_titles

        blocks = [
            {
                "Id": "title-1",
                "BlockType": "LAYOUT_TITLE",
                "Geometry": {"BoundingBox": {"Top": 0.1, "Left": 0.1, "Width": 0.5, "Height": 0.05}},
                "Page": 1,
                "Relationships": [{"Type": "CHILD", "Ids": ["word-1", "word-2"]}],
            },
            {
                "Id": "word-1",
                "BlockType": "WORD",
                "Text": "Table",
            },
            {
                "Id": "word-2",
                "BlockType": "WORD",
                "Text": "1:",
            },
            {
                "Id": "table-1",
                "BlockType": "TABLE",
            },
        ]
        block_map = {b["Id"]: b for b in blocks}

        titles = _extract_layout_titles(blocks, block_map)

        assert len(titles) == 1
        assert titles[0]["text"] == "Table 1:"
        assert titles[0]["page"] == 1
        assert abs(titles[0]["bottom"] - 0.15) < 0.001  # Top + Height (float comparison)

    def test_extract_layout_titles_with_line_blocks(self) -> None:
        """Test extracting titles when child blocks are LINE type."""
        from handler.utils.textract import _extract_layout_titles

        blocks = [
            {
                "Id": "title-1",
                "BlockType": "LAYOUT_TITLE",
                "Geometry": {"BoundingBox": {"Top": 0.1, "Left": 0.1, "Width": 0.5, "Height": 0.05}},
                "Page": 1,
                "Relationships": [{"Type": "CHILD", "Ids": ["line-1"]}],
            },
            {
                "Id": "line-1",
                "BlockType": "LINE",
                "Text": "Table 1: Adverse Reactions",
            },
        ]
        block_map = {b["Id"]: b for b in blocks}

        titles = _extract_layout_titles(blocks, block_map)

        assert len(titles) == 1
        assert titles[0]["text"] == "Table 1: Adverse Reactions"

    def test_extract_layout_titles_empty(self) -> None:
        """Test extracting titles when no LAYOUT_TITLE blocks exist."""
        from handler.utils.textract import _extract_layout_titles

        blocks = [{"Id": "table-1", "BlockType": "TABLE"}]
        block_map = {b["Id"]: b for b in blocks}

        titles = _extract_layout_titles(blocks, block_map)

        assert titles == []

    def test_get_block_text(self) -> None:
        """Test getting text from a block's children."""
        from handler.utils.textract import _get_block_text

        block = {
            "Id": "parent",
            "Relationships": [{"Type": "CHILD", "Ids": ["word-1", "word-2", "word-3"]}],
        }
        block_map = {
            "parent": block,
            "word-1": {"BlockType": "WORD", "Text": "Hello"},
            "word-2": {"BlockType": "WORD", "Text": "World"},
            "word-3": {"BlockType": "WORD", "Text": "!"},
        }

        text = _get_block_text(block, block_map)

        assert text == "Hello World !"

    def test_get_block_text_no_relationships(self) -> None:
        """Test getting text from a block with no relationships."""
        from handler.utils.textract import _get_block_text

        block = {"Id": "parent"}
        block_map = {"parent": block}

        text = _get_block_text(block, block_map)

        assert text == ""

    def test_find_table_title(self) -> None:
        """Test finding a title for a table based on spatial proximity."""
        from handler.utils.textract import _find_table_title

        table_block = {
            "Id": "table-1",
            "BlockType": "TABLE",
            "Geometry": {"BoundingBox": {"Top": 0.3, "Left": 0.1, "Width": 0.8, "Height": 0.4}},
            "Page": 1,
        }

        layout_titles = [
            {
                "text": "Table 1: Adverse Reactions",
                "geometry": {"Top": 0.2, "Left": 0.1, "Width": 0.5, "Height": 0.05},
                "page": 1,
                "bottom": 0.25,
            },
        ]

        title = _find_table_title(table_block, layout_titles)

        assert title == "Table 1: Adverse Reactions"

    def test_find_table_title_no_match(self) -> None:
        """Test finding title when no title is close enough."""
        from handler.utils.textract import _find_table_title

        table_block = {
            "Id": "table-1",
            "BlockType": "TABLE",
            "Geometry": {"BoundingBox": {"Top": 0.8, "Left": 0.1, "Width": 0.8, "Height": 0.1}},
            "Page": 1,
        }

        layout_titles = [
            {
                "text": "Some Title",
                "geometry": {"Top": 0.1, "Left": 0.1, "Width": 0.5, "Height": 0.05},
                "page": 1,
                "bottom": 0.15,  # Too far from table (0.65 gap > 0.1 threshold)
            },
        ]

        title = _find_table_title(table_block, layout_titles)

        assert title is None

    def test_find_table_title_different_page(self) -> None:
        """Test finding title when title is on different page."""
        from handler.utils.textract import _find_table_title

        table_block = {
            "Id": "table-1",
            "BlockType": "TABLE",
            "Geometry": {"BoundingBox": {"Top": 0.3, "Left": 0.1, "Width": 0.8, "Height": 0.4}},
            "Page": 2,
        }

        layout_titles = [
            {
                "text": "Table 1: Adverse Reactions",
                "geometry": {"Top": 0.2, "Left": 0.1, "Width": 0.5, "Height": 0.05},
                "page": 1,  # Different page
                "bottom": 0.25,
            },
        ]

        title = _find_table_title(table_block, layout_titles)

        assert title is None

    def test_find_table_title_below_table(self) -> None:
        """Test that titles below the table are not matched."""
        from handler.utils.textract import _find_table_title

        table_block = {
            "Id": "table-1",
            "BlockType": "TABLE",
            "Geometry": {"BoundingBox": {"Top": 0.2, "Left": 0.1, "Width": 0.8, "Height": 0.3}},
            "Page": 1,
        }

        layout_titles = [
            {
                "text": "Title Below Table",
                "geometry": {"Top": 0.6, "Left": 0.1, "Width": 0.5, "Height": 0.05},
                "page": 1,
                "bottom": 0.65,  # Below the table
            },
        ]

        title = _find_table_title(table_block, layout_titles)

        assert title is None

    def test_find_table_title_closest_match(self) -> None:
        """Test that the closest title is selected when multiple candidates exist."""
        from handler.utils.textract import _find_table_title

        table_block = {
            "Id": "table-1",
            "BlockType": "TABLE",
            "Geometry": {"BoundingBox": {"Top": 0.4, "Left": 0.1, "Width": 0.8, "Height": 0.3}},
            "Page": 1,
        }

        layout_titles = [
            {
                "text": "Far Title",
                "geometry": {"Top": 0.25, "Left": 0.1, "Width": 0.5, "Height": 0.05},
                "page": 1,
                "bottom": 0.32,  # 0.08 gap
            },
            {
                "text": "Close Title",
                "geometry": {"Top": 0.33, "Left": 0.1, "Width": 0.5, "Height": 0.05},
                "page": 1,
                "bottom": 0.38,  # 0.02 gap - closer
            },
        ]

        title = _find_table_title(table_block, layout_titles)

        assert title == "Close Title"

    def test_parse_textract_tables_with_title(self) -> None:
        """Test parse_textract_tables includes extracted titles."""
        from handler.utils.textract import parse_textract_tables

        response = {
            "Blocks": [
                {
                    "Id": "title-1",
                    "BlockType": "LAYOUT_TITLE",
                    "Geometry": {"BoundingBox": {"Top": 0.1, "Left": 0.1, "Width": 0.5, "Height": 0.05}},
                    "Page": 1,
                    "Relationships": [{"Type": "CHILD", "Ids": ["line-1"]}],
                },
                {
                    "Id": "line-1",
                    "BlockType": "LINE",
                    "Text": "Table 1: Test Results",
                },
                {
                    "Id": "table-1",
                    "BlockType": "TABLE",
                    "Geometry": {"BoundingBox": {"Top": 0.2, "Left": 0.1, "Width": 0.8, "Height": 0.3}},
                    "Page": 1,
                    "Confidence": 99.0,
                    "Relationships": [{"Type": "CHILD", "Ids": ["cell-1"]}],
                },
                {
                    "Id": "cell-1",
                    "BlockType": "CELL",
                    "RowIndex": 1,
                    "ColumnIndex": 1,
                    "Relationships": [{"Type": "CHILD", "Ids": ["word-1"]}],
                },
                {
                    "Id": "word-1",
                    "BlockType": "WORD",
                    "Text": "Data",
                },
            ]
        }

        tables = parse_textract_tables(response)

        assert len(tables) == 1
        assert tables[0].get("title") == "Table 1: Test Results"


class TestS3Utils:
    """Tests for S3 utility functions."""

    @patch("handler.utils.s3.s3_client")
    def test_download_pdf_from_s3(self, mock_s3: MagicMock) -> None:
        """Test download_pdf_from_s3 fetches from S3."""
        from handler.utils.s3 import download_pdf_from_s3

        mock_s3.get_object.return_value = {
            "Body": MagicMock(read=lambda: b"pdf-content")
        }

        result = download_pdf_from_s3("test-bucket", "test/file.pdf")

        assert result == b"pdf-content"
        mock_s3.get_object.assert_called_once_with(
            Bucket="test-bucket", Key="test/file.pdf"
        )


class TestDynamoDBUtils:
    """Tests for DynamoDB utility functions."""

    @patch("handler.utils.dynamodb._get_dynamodb_resource")
    def test_increment_tables_processed(self, mock_resource: MagicMock) -> None:
        """Test increment_tables_processed updates DynamoDB."""
        from handler.utils.dynamodb import increment_tables_processed

        mock_table = MagicMock()
        mock_resource.return_value.Table.return_value = mock_table

        increment_tables_processed("test-table", "job-123")

        mock_table.update_item.assert_called_once()
        call_args = mock_table.update_item.call_args
        assert call_args.kwargs["Key"] == {"PK": "JOB#job-123", "SK": "METADATA"}

    def test_increment_tables_processed_no_table(self) -> None:
        """Test increment_tables_processed with no table name."""
        from handler.utils.dynamodb import increment_tables_processed

        # Should not raise, just log warning
        increment_tables_processed("", "job-123")

    @patch("handler.utils.dynamodb._get_dynamodb_resource")
    def test_increment_tables_failed(self, mock_resource: MagicMock) -> None:
        """Test increment_tables_failed updates DynamoDB."""
        from handler.utils.dynamodb import increment_tables_failed

        mock_table = MagicMock()
        mock_resource.return_value.Table.return_value = mock_table

        increment_tables_failed("test-table", "job-123", "Test error")

        mock_table.update_item.assert_called_once()
        call_args = mock_table.update_item.call_args
        assert ":error" in call_args.kwargs["ExpressionAttributeValues"]

    def test_increment_tables_failed_no_table(self) -> None:
        """Test increment_tables_failed with no table name."""
        from handler.utils.dynamodb import increment_tables_failed

        # Should not raise, just log warning
        increment_tables_failed("", "job-123")

    @patch("handler.utils.dynamodb._get_dynamodb_resource")
    def test_create_table_record(self, mock_resource: MagicMock) -> None:
        """Test create_table_record creates DynamoDB item with GSI keys."""
        from handler.utils.dynamodb import create_table_record

        mock_table = MagicMock()
        mock_resource.return_value.Table.return_value = mock_table

        table_data = {
            "row_count": 5,
            "column_count": 3,
            "confidence": 99.5,
            "rows": [["a", "b", "c"]],
        }

        result = create_table_record(
            table_name="test-table",
            job_id="job-123",
            table_number=1,
            page=7,
            product_name="Keytruda",
            table_title="Table 1",
            table_data=table_data,
        )

        assert result is not None
        assert result["job_id"] == "job-123"
        assert result["table_number"] == 1
        # Verify GSI1 keys for product filtering
        assert result["GSI1PK"] == "PRODUCT#keytruda"
        assert result["GSI1SK"] == "STATUS#SUCCESS#TABLE#1#PAGE#7"
        assert result["status"] == "SUCCESS"
        mock_table.put_item.assert_called_once()

    def test_create_table_record_no_table(self) -> None:
        """Test create_table_record with no table name."""
        from handler.utils.dynamodb import create_table_record

        result = create_table_record(
            table_name="",
            job_id="job-123",
            table_number=1,
            page=7,
            product_name="keytruda",
            table_title="Table 1",
            table_data=None,
        )

        assert result is None

    @patch("handler.utils.dynamodb._get_dynamodb_resource")
    def test_create_table_record_with_error(self, mock_resource: MagicMock) -> None:
        """Test create_table_record with error message includes GSI keys for filtering."""
        from handler.utils.dynamodb import create_table_record

        mock_table = MagicMock()
        mock_resource.return_value.Table.return_value = mock_table

        result = create_table_record(
            table_name="test-table",
            job_id="job-123",
            table_number=1,
            page=7,
            product_name="keytruda",
            table_title="Table 1",
            table_data=None,
            status="FAILED",
            error_message="Extraction failed",
        )

        assert result is not None
        assert result["status"] == "FAILED"
        assert result["error_message"] == "Extraction failed"
        # Verify GSI1 keys allow filtering failed tables by product
        assert result["GSI1PK"] == "PRODUCT#keytruda"
        assert result["GSI1SK"] == "STATUS#FAILED#TABLE#1#PAGE#7"

    @patch("handler.utils.dynamodb._get_dynamodb_resource")
    def test_create_table_record_normalizes_product_name(self, mock_resource: MagicMock) -> None:
        """Test create_table_record normalizes product name for GSI keys."""
        from handler.utils.dynamodb import create_table_record

        mock_table = MagicMock()
        mock_resource.return_value.Table.return_value = mock_table

        result = create_table_record(
            table_name="test-table",
            job_id="job-123",
            table_number=2,
            page=10,
            product_name="Product With Spaces",
            table_title="Table 2",
            table_data=None,
        )

        assert result is not None
        # Product name should be normalized (lowercase, spaces replaced with hyphens)
        assert result["GSI1PK"] == "PRODUCT#product-with-spaces"
        assert result["product_name"] == "Product With Spaces"  # Original preserved

    @patch("handler.utils.dynamodb._get_dynamodb_resource")
    def test_create_table_record_empty_product_name(self, mock_resource: MagicMock) -> None:
        """Test create_table_record handles empty product name."""
        from handler.utils.dynamodb import create_table_record

        mock_table = MagicMock()
        mock_resource.return_value.Table.return_value = mock_table

        result = create_table_record(
            table_name="test-table",
            job_id="job-123",
            table_number=1,
            page=5,
            product_name="",
            table_title="Table 1",
            table_data=None,
        )

        assert result is not None
        assert result["GSI1PK"] == "PRODUCT#unknown"


class TestSSMUtils:
    """Tests for SSM utilities."""

    @patch("handler.utils.ssm.boto3.client")
    def test_get_parameter(self, mock_boto_client: MagicMock) -> None:
        """Test get_parameter fetches from SSM."""
        from handler.utils.ssm import get_parameter

        # Clear cache
        get_parameter.cache_clear()

        # Setup mock
        mock_ssm = MagicMock()
        mock_boto_client.return_value = mock_ssm
        mock_ssm.get_parameter.return_value = {
            "Parameter": {"Value": "test-value"}
        }

        # Act
        result = get_parameter("/dev/my-app/secret")

        # Assert
        assert result == "test-value"
        mock_ssm.get_parameter.assert_called_once_with(
            Name="/dev/my-app/secret", WithDecryption=True
        )

    @patch("handler.utils.ssm.boto3.client")
    def test_get_parameter_no_decrypt(self, mock_boto_client: MagicMock) -> None:
        """Test get_parameter with decrypt=False."""
        from handler.utils.ssm import get_parameter

        get_parameter.cache_clear()

        mock_ssm = MagicMock()
        mock_boto_client.return_value = mock_ssm
        mock_ssm.get_parameter.return_value = {
            "Parameter": {"Value": "plain-value"}
        }

        result = get_parameter("/dev/my-app/config", decrypt=False)

        assert result == "plain-value"
        mock_ssm.get_parameter.assert_called_once_with(
            Name="/dev/my-app/config", WithDecryption=False
        )

    @patch("handler.utils.ssm.boto3.client")
    def test_get_parameters_by_path(self, mock_boto_client: MagicMock) -> None:
        """Test get_parameters_by_path fetches all parameters under path."""
        from handler.utils.ssm import get_parameters_by_path

        mock_ssm = MagicMock()
        mock_boto_client.return_value = mock_ssm

        # Setup paginator mock
        mock_paginator = MagicMock()
        mock_ssm.get_paginator.return_value = mock_paginator
        mock_paginator.paginate.return_value = [
            {
                "Parameters": [
                    {"Name": "/dev/my-app/db-host", "Value": "localhost"},
                    {"Name": "/dev/my-app/db-port", "Value": "5432"},
                ]
            }
        ]

        result = get_parameters_by_path("/dev/my-app/")

        assert result == {"db-host": "localhost", "db-port": "5432"}

    @patch("handler.utils.ssm.boto3.client")
    def test_get_parameters_by_path_empty(self, mock_boto_client: MagicMock) -> None:
        """Test get_parameters_by_path with no parameters."""
        from handler.utils.ssm import get_parameters_by_path

        mock_ssm = MagicMock()
        mock_boto_client.return_value = mock_ssm

        mock_paginator = MagicMock()
        mock_ssm.get_paginator.return_value = mock_paginator
        mock_paginator.paginate.return_value = [{"Parameters": []}]

        result = get_parameters_by_path("/dev/empty/")

        assert result == {}
