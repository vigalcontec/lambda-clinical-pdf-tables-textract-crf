"""S3 utility functions."""

import boto3
from aws_lambda_powertools import Logger, Tracer

logger = Logger()
tracer = Tracer()

s3_client = boto3.client("s3")


@tracer.capture_method
def download_pdf_from_s3(bucket: str, key: str) -> bytes:
    """Download PDF from S3 directly into memory.

    Args:
        bucket: S3 bucket name
        key: S3 object key

    Returns:
        PDF content as bytes
    """
    logger.info("Downloading PDF from S3", extra={"bucket": bucket, "key": key})
    response = s3_client.get_object(Bucket=bucket, Key=key)
    return bytes(response["Body"].read())
