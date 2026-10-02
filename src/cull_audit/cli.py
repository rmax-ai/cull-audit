"""Command-line interface for cull-audit.

Exit codes:
    EXIT_SUCCESS: The command completed successfully.
    EXIT_USAGE: The command line was invalid.
    EXIT_CONTRACT: Input or output did not satisfy a cull-audit contract.
    EXIT_IO: A local filesystem or image operation failed.
    EXIT_PROVIDER: A provider operation failed.
"""

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

from . import __version__
from .contracts import JudgmentRecord, ValidationIssue
from .ingest import ingest

EXIT_SUCCESS = 0
EXIT_USAGE = 2
EXIT_CONTRACT = 3
EXIT_IO = 4
EXIT_PROVIDER = 5


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(prog="cull-audit")
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate")
    validate.add_argument("--judgments", required=True, metavar="PATH")
    validate.add_argument("--photos", metavar="DIR")
    validate.add_argument("--format", choices=("text", "json"), default="text")
    for command in ("audit", "demo"):
        subparsers.add_parser(command)
    return parser


def _photo_warnings(
    photo_root: str, records: tuple[JudgmentRecord, ...]
) -> tuple[list[str], list[ValidationIssue]]:
    root = Path(photo_root)
    if not root.is_dir():
        return [], [ValidationIssue("$.photos", f"photo directory does not exist or is not a directory: {photo_root}")]
    warnings = [
        f"photo_id not found under {photo_root}: {record.photo_id}"
        for record in records
        if not (root / record.photo_id).is_file()
    ]
    return warnings, []


def _validate(args: argparse.Namespace) -> int:
    result = ingest(args.judgments)
    warnings = list(result.warnings)
    errors = list(result.errors)
    if args.photos and not errors:
        photo_warnings, photo_errors = _photo_warnings(args.photos, result.records)
        warnings.extend(photo_warnings)
        errors.extend(photo_errors)

    if args.format == "json":
        payload = {
            "valid": not errors,
            "records": len(result.records),
            "errors": [issue.as_dict() for issue in errors],
            "warnings": warnings,
        }
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        for warning in warnings:
            print(f"warning: {warning}", file=sys.stderr)
    else:
        if errors:
            for issue in errors:
                print(f"error: {issue}", file=sys.stderr)
        else:
            print(f"valid: {len(result.records)} judgment record(s)")
        for warning in warnings:
            print(f"warning: {warning}", file=sys.stderr)
    return EXIT_SUCCESS if not errors else EXIT_CONTRACT


def main(argv: Sequence[str] | None = None) -> int:
    """Parse arguments and dispatch commands."""
    args = build_parser().parse_args(argv)
    if args.command == "validate":
        return _validate(args)
    print(f"{args.command}: not implemented yet", file=sys.stderr)
    return EXIT_CONTRACT
