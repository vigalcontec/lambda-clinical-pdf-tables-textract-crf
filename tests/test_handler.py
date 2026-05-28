"""Tests for Lambda handler."""

from typing import Any
from unittest.mock import MagicMock, patch

from handler.config import Settings, get_settings


class TestHandler:
    """Tests for main handler function."""

    @patch("handler.utils.s3.s3_client")
    @patch("handler.utils.textract.textract_client")
    def test_handler_success(
        self,
        mock_textract: MagicMock,
        mock_s3: MagicMock,
        lambda_event: dict[str, Any],
        lambda_context: Any,
        sample_pdf_bytes: bytes,
        textract_response: dict[str, Any],
    ) -> None:
        """Test successful handler execution."""
        get_settings.cache_clear()

        # Mock S3 download
        mock_s3.get_object.return_value = {"Body": MagicMock(read=lambda: sample_pdf_bytes)}

        # Mock Textract response
        mock_textract.analyze_document.return_value = textract_response

        from handler.main import handler

        result = handler(lambda_event, lambda_context)

        assert result["status"] == "SUCCESS"
        assert result["s3_bucket"] == "test-bucket"
        assert result["s3_key"] == "test/document.pdf"
        assert result["tables_extracted"] == 1

    @patch("handler.utils.s3.s3_client")
    @patch("handler.utils.textract.textract_client")
    def test_handler_extracts_tables(
        self,
        mock_textract: MagicMock,
        mock_s3: MagicMock,
        lambda_event: dict[str, Any],
        lambda_context: Any,
        sample_pdf_bytes: bytes,
        textract_response: dict[str, Any],
    ) -> None:
        """Test handler extracts table data correctly."""
        get_settings.cache_clear()

        mock_s3.get_object.return_value = {"Body": MagicMock(read=lambda: sample_pdf_bytes)}
        mock_textract.analyze_document.return_value = textract_response

        from handler.main import handler

        result = handler(lambda_event, lambda_context)

        assert len(result["tables"]) == 1
        table = result["tables"][0]
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
        assert result["tables_extracted"] == 0
        assert result["tables"] == []


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

        job_id = start_textract_analysis(b"pdf-bytes")

        assert job_id == "test-job-123"
        mock_textract.start_document_analysis.assert_called_once()


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
