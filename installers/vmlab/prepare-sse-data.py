#!/usr/bin/env python3
"""Create recent HEC batches from an SSE application package."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from sse_data import PreparationError, PreparationOptions, prepare_package


def parse_anchor(value: str) -> datetime:
    """Parse a timezone-aware ISO 8601 anchor and normalize it to UTC."""
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        anchor = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"invalid ISO 8601 anchor: {value}") from error
    if anchor.tzinfo is None:
        raise argparse.ArgumentTypeError("anchor must include a timezone")
    return anchor.astimezone(UTC)


def build_parser() -> argparse.ArgumentParser:
    """Build the preparation command argument parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--index", required=True)
    parser.add_argument("--anchor", type=parse_anchor)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--batch-size", type=int, default=5_000)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Prepare data and print a machine-readable summary."""
    arguments = build_parser().parse_args(argv)
    anchor = arguments.anchor or datetime.now(UTC)
    try:
        report = prepare_package(
            PreparationOptions(
                package=arguments.package,
                output_dir=arguments.output_dir,
                index=arguments.index,
                anchor=anchor,
                dry_run=arguments.dry_run,
                batch_size=arguments.batch_size,
            )
        )
    except PreparationError as error:
        print(f"prepare-sse-data: {error}", file=sys.stderr)
        return 1

    summary = {
        "import_id": report.import_id,
        "dataset_count": len(report.datasets),
        "event_count": report.total_rows,
        "batch_count": len(report.batches),
        "anchor": report.anchor.isoformat().replace("+00:00", "Z"),
        "delta_seconds": report.delta.total_seconds(),
        "original_min": report.global_min.isoformat().replace("+00:00", "Z"),
        "original_max": report.global_max.isoformat().replace("+00:00", "Z"),
        "shifted_min": report.shifted_min.isoformat().replace("+00:00", "Z"),
        "shifted_max": report.shifted_max.isoformat().replace("+00:00", "Z"),
        "dry_run": report.dry_run,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
