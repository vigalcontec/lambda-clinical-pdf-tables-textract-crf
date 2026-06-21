#!/usr/bin/env python
"""Local test script for the Textract Lambda handler.

This script allows testing the Lambda function locally with a single event
from an events JSON file. It loads AWS credentials from the environment
and calls the handler directly.

Usage:
    # Test with default event (first event from ibrance)
    poetry run python scripts/local_test.py

    # Test with specific event file and index
    poetry run python scripts/local_test.py --events-file path/to/events.json --event-index 0

    # Test with inline event
    poetry run python scripts/local_test.py --inline '{...}'

    # Skip DynamoDB updates (dry run)
    poetry run python scripts/local_test.py --skip-dynamodb
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

# Set AWS region BEFORE any boto3 imports happen
os.environ.setdefault("AWS_REGION", "eu-west-1")
os.environ.setdefault("AWS_DEFAULT_REGION", "eu-west-1")

# Add src to path for local imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def load_event_from_file(events_file: str, event_index: int = 0) -> dict[str, Any]:
    """Load a single event from an events JSON file.

    Args:
        events_file: Path to the events JSON file
        event_index: Index of the event to load (default: 0)

    Returns:
        Event dictionary
    """
    with open(events_file) as f:
        events = json.load(f)

    if not events:
        raise ValueError(f"No events found in {events_file}")

    if event_index >= len(events):
        raise ValueError(f"Event index {event_index} out of range. File has {len(events)} events.")

    return events[event_index]


def create_mock_context() -> Any:
    """Create a mock Lambda context for local testing."""

    class MockContext:
        function_name = "clinical-pdf-textract-local"
        memory_limit_in_mb = 512
        invoked_function_arn = "arn:aws:lambda:eu-west-1:123456789:function:local-test"
        aws_request_id = "local-test-request-id"

        def get_remaining_time_in_millis(self) -> int:
            return 300000  # 5 minutes

    return MockContext()


def setup_environment(skip_dynamodb: bool = False) -> None:
    """Set up environment variables for local testing."""
    # Load from .env file if it exists
    env_file = Path(__file__).parent.parent / ".env"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ.setdefault(key.strip(), value.strip())

    # Set defaults for local testing
    os.environ.setdefault("ENVIRONMENT", "dev")
    os.environ.setdefault("AWS_REGION", "eu-west-1")
    os.environ.setdefault("LOG_LEVEL", "DEBUG")
    os.environ.setdefault("POWERTOOLS_SERVICE_NAME", "clinical-pdf-textract-local")
    os.environ.setdefault("POWERTOOLS_TRACE_DISABLED", "true")
    os.environ.setdefault("DYNAMODB_TABLE_NAME", "clinical-pdf-jobs-crf-dev")

    if skip_dynamodb:
        # Set a non-existent table to skip DynamoDB operations
        os.environ["DYNAMODB_TABLE_NAME"] = ""


def main() -> None:
    """Run the local test."""
    parser = argparse.ArgumentParser(description="Local test for Textract Lambda")
    parser.add_argument(
        "--events-file",
        type=str,
        help="Path to events JSON file",
    )
    parser.add_argument(
        "--event-index",
        type=int,
        default=0,
        help="Index of event to test (default: 0)",
    )
    parser.add_argument(
        "--inline",
        type=str,
        help="Inline JSON event (overrides --events-file)",
    )
    parser.add_argument(
        "--skip-dynamodb",
        action="store_true",
        help="Skip DynamoDB operations",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output file for results (default: stdout)",
    )

    args = parser.parse_args()

    # Set up environment
    setup_environment(skip_dynamodb=args.skip_dynamodb)

    # Load event
    if args.inline:
        event = json.loads(args.inline)
        print(f"Using inline event")
    elif args.events_file:
        event = load_event_from_file(args.events_file, args.event_index)
        print(f"Loaded event {args.event_index} from {args.events_file}")
    else:
        # Default: look for events file in common locations
        default_paths = [
            Path(__file__).parent.parent.parent / "Files" / "ibrance" / "ibrance-epar-product-information_en_events.json",
            Path(__file__).parent.parent.parent / "Files" / "keytruda" / "keytruda-epar-product-information_en_events.json",
            Path(__file__).parent.parent.parent / "Files" / "tecentriq" / "tecentriq-epar-product-information_en_events.json",
        ]

        events_file = None
        for path in default_paths:
            if path.exists():
                events_file = path
                break

        if not events_file:
            print("ERROR: No events file found. Specify --events-file or --inline")
            sys.exit(1)

        event = load_event_from_file(str(events_file), args.event_index)
        print(f"Loaded event {args.event_index} from {events_file}")

    # Print event info
    print("\n" + "=" * 60)
    print("EVENT DETAILS:")
    print("=" * 60)
    print(f"  Product: {event.get('product_name')}")
    print(f"  Table: {event.get('table_name')}")
    print(f"  Table Number: {event.get('table_number')}")
    print(f"  Page: {event.get('page')}")
    print(f"  Table Index on Page: {event.get('table_index_on_page')}")
    print(f"  S3 Key: {event.get('s3_key')}")
    if event.get("formulations"):
        print(f"  Formulations: {event.get('formulations')}")
    print("=" * 60 + "\n")

    # Import handler after environment setup
    from handler.main import handler

    # Create mock context
    context = create_mock_context()

    # Run handler
    print("Running handler...")
    print("-" * 60)

    try:
        result = handler(event, context)

        print("-" * 60)
        print("\nRESULT:")
        print("=" * 60)
        print(f"  Status: {result.get('status')}")

        if result.get("status") == "SUCCESS":
            table = result.get("table")
            if table:
                print(f"  Title: {table.get('title', 'N/A')}")
                print(f"  Rows: {table.get('row_count')}")
                print(f"  Columns: {table.get('column_count')}")
                print(f"  Confidence: {table.get('confidence', 'N/A')}")

                # Show first few rows
                rows = table.get("rows", [])
                if rows:
                    print("\n  First 3 rows:")
                    for i, row in enumerate(rows[:3]):
                        print(f"    [{i}]: {row}")
                    if len(rows) > 3:
                        print(f"    ... ({len(rows) - 3} more rows)")
            else:
                print("  Table: None (no table extracted)")
        else:
            print(f"  Error: {result.get('error')}")

        print("=" * 60)

        # Save to file if requested
        if args.output:
            with open(args.output, "w") as f:
                json.dump(result, f, indent=2)
            print(f"\nFull result saved to: {args.output}")

    except Exception as e:
        print(f"\nERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
