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
import os
from pathlib import Path
import sys
from typing import Sequence

from . import __version__
from .audit import AuditContractError, AuditIOError, run_audit
from .contracts import JudgmentRecord, ValidationIssue
from .demo import run_demo
from .ingest import ingest
from .reference.gemini import API_KEY_ENV, GeminiConfigurationError
from .reference.images import ImagePreparationError
from .reference.passes import (
    DEFAULT_FINALISTS,
    DEFAULT_REPEAT_TOP,
    PASS_NAMES,
    ReferenceConfigurationError,
    ReferenceContractError,
    ReferenceIOError,
    ReferenceProviderError,
    run_reference,
)

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
    audit = subparsers.add_parser("audit")
    audit.add_argument("--judgments", required=True, metavar="PATH")
    audit.add_argument("--baseline-stage", required=True, metavar="NAME")
    audit.add_argument("--decisive-stage", required=True, metavar="NAME")
    audit.add_argument("--output", required=True, metavar="DIR")
    audit.add_argument("--photos", metavar="DIR")
    audit.add_argument("--prices", metavar="PATH")
    audit.add_argument("--source-date-epoch", metavar="UNIX_SECONDS")
    audit.add_argument("--strict", action="store_true")
    demo = subparsers.add_parser("demo")
    demo.add_argument("--output", required=True, metavar="DIR")
    reference = subparsers.add_parser("reference")
    reference_subparsers = reference.add_subparsers(
        dest="reference_command",
        required=True,
    )
    reference_run = reference_subparsers.add_parser("run")
    reference_run.add_argument("--photos", required=True, metavar="DIR")
    reference_run.add_argument("--output", required=True, metavar="DIR")
    reference_run.add_argument("--model", required=True, metavar="NAME")
    reference_run.add_argument(
        "--passes",
        default=",".join(PASS_NAMES),
        metavar="NAMES",
        help="comma-separated passes: triage,dedicated,face,repeat",
    )
    reference_run.add_argument(
        "--finalists",
        type=int,
        default=DEFAULT_FINALISTS,
        metavar="N",
    )
    reference_run.add_argument(
        "--repeat-top",
        type=int,
        default=DEFAULT_REPEAT_TOP,
        metavar="N",
    )
    reference_run.add_argument("--dry-run", action="store_true")
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


def _audit(args: argparse.Namespace) -> int:
    try:
        run_audit(
            args.judgments,
            baseline_stage=args.baseline_stage,
            decisive_stage=args.decisive_stage,
            output=args.output,
            photos=args.photos,
            prices=args.prices,
            source_date_epoch=args.source_date_epoch,
            strict=args.strict,
        )
    except AuditContractError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_CONTRACT
    except AuditIOError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_IO
    return EXIT_SUCCESS


def _demo(args: argparse.Namespace) -> int:
    try:
        audit_path, report_path = run_demo(args.output)
    except AuditContractError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_CONTRACT
    except AuditIOError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_IO
    print(f"Wrote {audit_path}")
    print(f"Wrote {report_path}")
    return EXIT_SUCCESS


def _reference_run(args: argparse.Namespace) -> int:
    """Run the opt-in provider-backed reference image workflow."""

    passes = tuple(item.strip() for item in args.passes.split(",") if item.strip())
    if not args.dry_run and not os.environ.get(API_KEY_ENV):
        print(
            f"error: {API_KEY_ENV} must be set for a non-dry reference run",
            file=sys.stderr,
        )
        return EXIT_CONTRACT
    try:
        result = run_reference(
            args.photos,
            output=args.output,
            model=args.model,
            passes=passes,
            finalists=args.finalists,
            repeat_top=args.repeat_top,
            dry_run=args.dry_run,
        )
    except (ReferenceConfigurationError, ReferenceContractError, GeminiConfigurationError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_CONTRACT
    except (ReferenceIOError, ImagePreparationError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_IO
    except ReferenceProviderError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_PROVIDER

    if result.dry_run:
        print(f"Dry run: {len(result.planned_calls)} provider call(s), no HTTP requests sent")
        for index, planned in enumerate(result.planned_calls, 1):
            photo_ids = ", ".join(planned.photo_ids)
            print(
                f"{index:03d}: pass={planned.pass_name} "
                f"prompt={planned.prompt_id} photos={photo_ids} "
                f"prepared_bytes={planned.image_bytes}"
            )
        return EXIT_SUCCESS
    if result.judgments_path is not None:
        print(f"Wrote {result.judgments_path}")
    print(f"Completed {len(result.records)} judgment record(s)")
    return EXIT_SUCCESS


def main(argv: Sequence[str] | None = None) -> int:
    """Parse arguments and dispatch commands."""
    args = build_parser().parse_args(argv)
    if args.command == "validate":
        return _validate(args)
    if args.command == "audit":
        return _audit(args)
    if args.command == "demo":
        return _demo(args)
    if args.command == "reference" and args.reference_command == "run":
        return _reference_run(args)
    return EXIT_USAGE
