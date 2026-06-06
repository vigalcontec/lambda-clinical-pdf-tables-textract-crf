# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-06-06

### Added

- **GSI1 Keys for Product Filtering** - Table records now include GSI1PK and GSI1SK for efficient product-based queries
  - `GSI1PK`: `PRODUCT#{normalized_product_name}` - Query all tables for a specific product
  - `GSI1SK`: `STATUS#{status}#TABLE#{table_number}#PAGE#{page}` - Filter by status within a product
  - Product names are normalized (lowercase, spaces replaced with hyphens)

### Changed

- **Improved Error Tracking** - Failed table extractions are now properly recorded in DynamoDB with:
  - `status`: "FAILED"
  - `error_message`: Detailed error description
  - GSI1 keys for filtering failed tables by product

### Example Queries

```python
# Get all tables for a product
response = table.query(
    IndexName="GSI1",
    KeyConditionExpression="GSI1PK = :pk",
    ExpressionAttributeValues={":pk": "PRODUCT#keytruda"}
)

# Get all failed tables for a product
response = table.query(
    IndexName="GSI1",
    KeyConditionExpression="GSI1PK = :pk AND begins_with(GSI1SK, :sk)",
    ExpressionAttributeValues={
        ":pk": "PRODUCT#keytruda",
        ":sk": "STATUS#FAILED"
    }
)
```

---

## [0.1.0] - 2026-05-17

### Added

- **Textract Table Extraction** - Extract tables from PDF pages using AWS Textract
- **PDF Page Extraction** - Use PyMuPDF to extract specific pages from PDF
- **Sync/Async API** - Auto-select based on document size (sync for ≤5 pages, <5MB)
- **Page Group Flattening** - Handle nested page groups from locator lambda
- **Structured Table Output** - Parse Textract response to rows/columns JSON
- **Error Handling** - Graceful error handling with detailed error responses

### Input/Output Contract

**Input Event:**
```json
{
  "s3_bucket": "datalake-raw-...",
  "s3_key": "clinical_pdfs/document.pdf",
  "pages": [7, 8, [16, 17, 18], 26]
}
```

**Output:**
```json
{
  "status": "SUCCESS",
  "s3_bucket": "...",
  "s3_key": "...",
  "pages_processed": [7, 8, 16, 17, 18, 26],
  "tables_extracted": 5,
  "tables": [
    {
      "rows": [["Header1", "Header2"], ["Value1", "Value2"]],
      "row_count": 2,
      "column_count": 2,
      "confidence": 98.5
    }
  ]
}
```

---

## [0.0.0] - 2026-04-30

### Added

- **Lambda Function Template** - Production-ready Python 3.12 Lambda with Poetry
- **Docker Container Deployment** - Multi-stage Dockerfile for ECR
- **Terraform Infrastructure** - Lambda, IAM roles, CloudWatch Logs, SSM exports
- **GitHub Actions CI/CD** - OIDC authentication, multi-environment support
- **AWS Lambda Powertools** - Logger, Tracer, structured logging
- **SSM Integration** - Read datalake bucket/KMS ARNs from Parameter Store
- **Unit Tests** - pytest with 80% coverage requirement
- **Code Quality** - ruff linter, mypy type checking
- **Makefile** - Common development commands

### CI/CD Features

- **Manual Trigger** - `workflow_dispatch` for deploy/destroy actions
- **Environment Detection** - Automatic env based on branch (main→prod, release/*→qa, *→dev)
- **ECR Management** - Automatic repository creation via AWS CLI
- **Terraform Destroy** - Manual cleanup action to remove all infrastructure

### Template Mode

- Workflow triggers commented out by default
- Step-by-step setup instructions in README
- Configure GitHub secrets and uncomment triggers to enable

### Infrastructure Created

| Resource | Description |
|----------|-------------|
| Lambda Function | Container-based with X-Ray tracing |
| IAM Role | Execution role with S3, KMS, CloudWatch permissions |
| ECR Repository | Created by CI/CD, lifecycle policy managed by Terraform |
| CloudWatch Logs | Log group with 14-day retention |
| SSM Parameters | Function ARN, name, invoke ARN, role ARN exports |
