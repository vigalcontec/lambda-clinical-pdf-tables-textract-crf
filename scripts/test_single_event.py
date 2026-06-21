#!/usr/bin/env python
"""Quick test script for a single Textract event.

This is a simplified script for rapid testing. Edit the EVENT dict below
to test different tables.

Usage:
    poetry run python scripts/test_single_event.py
"""

import json
import os
import sys
from pathlib import Path

# Set environment BEFORE any imports that use boto3
os.environ.setdefault("AWS_REGION", "eu-west-1")
os.environ.setdefault("AWS_DEFAULT_REGION", "eu-west-1")
os.environ.setdefault("ENVIRONMENT", "dev")
os.environ.setdefault("LOG_LEVEL", "INFO")
os.environ.setdefault("POWERTOOLS_SERVICE_NAME", "clinical-pdf-textract-local")
os.environ.setdefault("POWERTOOLS_TRACE_DISABLED", "true")
os.environ.setdefault("DYNAMODB_TABLE_NAME", "clinical-pdf-jobs-crf-dev")

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# ============================================================================
# CONFIGURE YOUR TEST EVENT HERE
# ============================================================================
EVENT =   {
    "job_id": "73a98bcaed2e5b347266ff9f037099270b545348fdf729a2479eedc3e06fd319",
    "s3_bucket": "datalake-raw-vigalcontec-dev-002332700133",
    "s3_key": "crf/clinical_pdfs/ibrance/20260603164300/ibrance-epar-product-information_en.pdf",
    "product_name": "ibrance",
    "table_name": "Table 5: Laboratory abnormalities observed in pooled dataset from 3 randomised studies",
    "table_number": 5,
    "page": 11,
    "table_index_on_page": 1,
    "formulation_key": "28e423a2c598",
    "formulations": [
      "IBRANCE 75 mg hard capsules",
      "IBRANCE 100 mg hard capsules",
      "IBRANCE 125 mg hard capsules"
    ]
  }
# ============================================================================


class MockContext:
    """Mock Lambda context."""
    function_name = "local-test"
    memory_limit_in_mb = 512
    invoked_function_arn = "arn:aws:lambda:eu-west-1:123456789:function:local"
    aws_request_id = "local-request"

    def get_remaining_time_in_millis(self) -> int:
        return 300000


def main() -> None:
    """Run the test."""
    print("=" * 70)
    print("TEXTRACT LAMBDA LOCAL TEST")
    print("=" * 70)
    print(f"Product:     {EVENT['product_name']}")
    print(f"Table:       {EVENT['table_name']}")
    print(f"Page:        {EVENT['page']}")
    print(f"Table Index: {EVENT['table_index_on_page']}")
    print("=" * 70)

    from handler.main import handler

    print("\nCalling handler...\n")

    result = handler(EVENT, MockContext())

    print("\n" + "=" * 70)
    print("RESULT")
    print("=" * 70)
    print(f"Status: {result['status']}")

    if result["status"] == "SUCCESS":
        table = result.get("table")
        if table:
            print(f"Title:  {table.get('title', 'N/A')}")
            print(f"Rows:   {table.get('row_count')}")
            print(f"Cols:   {table.get('column_count')}")
            print(f"Conf:   {table.get('confidence', 'N/A')}")

            print("\nTable Preview:")
            print("-" * 70)
            for i, row in enumerate(table.get("rows", [])[:5]):
                # Truncate long cells for display
                display_row = [str(cell)[:30] + "..." if len(str(cell)) > 30 else str(cell) for cell in row]
                print(f"  Row {i}: {display_row}")
            if table.get("row_count", 0) > 5:
                print(f"  ... ({table['row_count'] - 5} more rows)")
        else:
            print("No table extracted")
    else:
        print(f"Error: {result.get('error')}")

    print("=" * 70)

    # Save full result
    output_file = Path(__file__).parent.parent / "ouput_example" / "local_test_result.json"
    output_file.parent.mkdir(exist_ok=True)
    with open(output_file, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\nFull result saved to: {output_file}")


if __name__ == "__main__":
    main()
