"""Convert producer-owned score JSONL into cull-audit judgment JSONL."""

# See ../../schemas/judgments-1.0.schema.json; validate with the ``validate`` CLI.

from __future__ import annotations

import argparse
from collections.abc import Mapping
import json
from pathlib import Path
import sys
from typing import Any, TextIO


def _required_text(value: Mapping[str, Any], name: str) -> str:
    item = value.get(name)
    if not isinstance(item, str) or not item:
        raise ValueError(f"{name} must be a non-empty string")
    return item


def judgment_from_score(
    score: Mapping[str, Any],
    source_tool: str,
    default_stage: str,
    default_read_kind: str,
) -> dict[str, Any]:
    """Build one v1 record without changing producer-owned judgments."""
    record: dict[str, Any] = {
        "record_id": _required_text(score, "record_id"),
        "photo_id": _required_text(score, "photo_id"),
        "stage": score.get("stage", default_stage),
        "read_kind": score.get("read_kind", default_read_kind),
        "verdict": _required_text(score, "verdict"),
        "source": {"tool": source_tool},
        "context": {
            "repeat_group": score.get("repeat_group"),
            "repeat_index": score.get("repeat_index"),
            "settings_fingerprint": score.get("settings_fingerprint"),
        },
    }
    for name in ("stage", "read_kind"):
        if not isinstance(record[name], str) or not record[name]:
            raise ValueError(f"{name} must be a non-empty string")

    if "source_tool_version" in score:
        record["source"]["tool_version"] = score["source_tool_version"]
    for name in ("model", "prompt_id"):
        if name in score:
            record["context"][name] = score[name]
    for name in ("composite", "scores", "reasons", "kill_factors", "usage", "observed_at"):
        if name in score:
            record[name] = score[name]
    return record


def convert_lines(
    source: TextIO,
    destination: TextIO,
    *,
    source_tool: str,
    default_stage: str,
    default_read_kind: str,
) -> None:
    """Convert non-empty input lines."""
    for line_number, line in enumerate(source, 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError("line must contain a JSON object")
            record = judgment_from_score(
                value, source_tool, default_stage, default_read_kind
            )
        except (ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"line {line_number}: {exc}") from exc
        destination.write(
            json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="producer JSONL or -")
    parser.add_argument("--output", type=Path, default=Path("-"), help="judgment JSONL or -")
    parser.add_argument("--source-tool", default="example-producer")
    parser.add_argument("--stage", default="producer")
    parser.add_argument("--read-kind", default="other")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    input_handle: TextIO
    output_handle: TextIO
    try:
        input_handle = sys.stdin if str(args.input) == "-" else args.input.open("r", encoding="utf-8")
        output_handle = sys.stdout if str(args.output) == "-" else args.output.open("w", encoding="utf-8")
        try:
            convert_lines(
                input_handle,
                output_handle,
                source_tool=args.source_tool,
                default_stage=args.stage,
                default_read_kind=args.read_kind,
            )
        finally:
            if input_handle is not sys.stdin:
                input_handle.close()
            if output_handle is not sys.stdout:
                output_handle.close()
    except (OSError, ValueError) as exc:
        print(f"producer_adapter: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
