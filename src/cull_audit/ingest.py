"""Input readers for canonical JSON and JSON Lines judgment files."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import sys
from typing import Any, TextIO

from .contracts import (
    JudgmentDocument,
    JudgmentRecord,
    ValidationIssue,
    issues_as_json,
    sort_issues,
    validate_document,
    validate_records,
)


@dataclass(frozen=True)
class IngestResult:
    """Normalized input plus diagnostics; readers never raise input errors."""

    records: tuple[JudgmentRecord, ...] = ()
    document: JudgmentDocument | None = None
    errors: tuple[ValidationIssue, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.errors

    def errors_as_dict(self) -> list[dict[str, str]]:
        return issues_as_json(list(self.errors))


def _strict_json(text: str, path: str) -> tuple[Any | None, list[ValidationIssue]]:
    try:
        return json.loads(
            text,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ValueError(f"invalid JSON constant {token}")
            ),
        ), []
    except (json.JSONDecodeError, ValueError) as exc:
        return None, [ValidationIssue("$", f"malformed JSON in {path}: {exc}")]


def _read_text(path: str | Path, stream: TextIO | None = None) -> tuple[str | None, list[ValidationIssue]]:
    label = "<stdin>" if path == "-" else str(path)
    try:
        if path == "-":
            return (sys.stdin if stream is None else stream).read(), []
        return Path(path).read_text(encoding="utf-8"), []
    except (OSError, UnicodeError) as exc:
        return None, [ValidationIssue("$", f"unable to read {label}: {exc}")]


def ingest_json(text: str, *, source: str = "<string>") -> IngestResult:
    """Parse and validate one canonical JSON document."""

    value, parse_errors = _strict_json(text, source)
    if parse_errors:
        return IngestResult(errors=tuple(parse_errors))
    document, errors = validate_document(value)
    return IngestResult(
        records=() if document is None else document.records,
        document=document,
        errors=tuple(errors),
    )


def ingest_jsonl(text: str, *, source: str = "<string>") -> IngestResult:
    """Parse and validate one JSON object per non-empty line."""

    values: list[Any] = []
    errors: list[ValidationIssue] = []
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        value, line_errors = _strict_json(line, f"{source}:{line_number}")
        if line_errors:
            errors.extend(
                ValidationIssue(f"$.lines[{line_number}]", issue.message)
                for issue in line_errors
            )
        else:
            values.append(value)
    records, contract_errors = validate_records(values)
    errors.extend(contract_errors)
    ordered_errors = tuple(sort_issues(errors))
    document = (
        JudgmentDocument("1.0", records)
        if not ordered_errors
        else None
    )
    return IngestResult(
        records=records,
        document=document,
        errors=ordered_errors,
    )


def ingest(path: str | Path, *, stream: TextIO | None = None) -> IngestResult:
    """Read a path, using ``-`` for stdin, and infer JSONL from its suffix.

    A JSON document is preferred for stdin.  JSONL stdin is also accepted when
    the first non-whitespace value is not an object containing ``records``.
    """

    text, errors = _read_text(path, stream)
    if errors:
        return IngestResult(errors=tuple(errors))
    assert text is not None
    if str(path).lower().endswith((".jsonl", ".ndjson")):
        return ingest_jsonl(text, source=str(path))
    if path == "-":
        value, parse_errors = _strict_json(text, "<stdin>")
        if (
            not parse_errors
            and isinstance(value, dict)
            and ("records" in value or "schema_version" in value)
            and "record_id" not in value
            and "photo_id" not in value
        ):
            document, validation_errors = validate_document(value)
            return IngestResult(
                records=() if document is None else document.records,
                document=document,
                errors=tuple(validation_errors),
            )
        # A failed whole-document parse may still be a useful JSONL stream.
        return ingest_jsonl(text, source="<stdin>")
    return ingest_json(text, source=str(path))


read_judgments = ingest
load_judgments = ingest
