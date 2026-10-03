"""The deterministic, image-free cull-audit demonstration.

The demo is deliberately a small judgment fixture rather than a photo
fixture.  It exercises the same ingestion, validation, audit assembly, cost,
and Markdown rendering paths used by the normal ``audit`` command without
requiring a key, a network, or any image files.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from .audit import (
    AuditContractError,
    _atomic_write,
    _generated_at,
    build_audit,
)
from .ingest import ingest_json
from .render import render_report


# Used when callers have not pinned SOURCE_DATE_EPOCH themselves.  Keeping
# this value in the demo makes a fresh install reproducible by default.
DEFAULT_SOURCE_DATE_EPOCH = 1_700_000_000
DEMO_BASELINE_STAGE = "triage"
DEMO_DECISIVE_STAGE = "dedicated"
DEMO_PRICE_TABLE = {
    "version": "1.0",
    "model": "demo-model",
    "currency": "USD",
    "unit": "per_million_tokens",
    "effective": "demo-fixed-2023",
    "prices": {"input": "0.20"},
}


def _record(
    record_id: str,
    photo_id: str,
    stage: str,
    read_kind: str,
    verdict: str,
    *,
    composite: int | float | None = None,
    context: dict[str, Any] | None = None,
    usage: dict[str, Any] | None = None,
    reasons: list[str] | None = None,
    kill_factors: list[str] | None = None,
) -> dict[str, Any]:
    """Create one raw record for the in-memory fixture."""
    record: dict[str, Any] = {
        "record_id": record_id,
        "photo_id": photo_id,
        "stage": stage,
        "read_kind": read_kind,
        "verdict": verdict,
        "source": {"tool": "cull-audit-demo", "tool_version": "1"},
    }
    if composite is not None:
        record["composite"] = composite
    if context is not None:
        record["context"] = context
    if usage is not None:
        record["usage"] = usage
    if reasons is not None:
        record["reasons"] = reasons
    if kill_factors is not None:
        record["kill_factors"] = kill_factors
    return record


def _repeat_context(repeat_group: str, repeat_index: int) -> dict[str, Any]:
    return {
        "repeat_group": repeat_group,
        "repeat_index": repeat_index,
        "settings_fingerprint": "demo-settings-v1",
    }


def _demo_document() -> dict[str, Any]:
    """Return the complete synthetic document without touching the filesystem."""
    return {
        "schema_version": "1.0",
        "records": [
            _record(
                "triage/upward",
                "demo/upward.jpg",
                DEMO_BASELINE_STAGE,
                "relative",
                "reject",
                composite=25,
                usage={
                    "calls": 1,
                    "cost": {
                        "currency": "USD",
                        "total": 0.10,
                        "source": "producer",
                    },
                },
                kill_factors=["context-sensitive framing"],
            ),
            _record(
                "dedicated/upward",
                "demo/upward.jpg",
                DEMO_DECISIVE_STAGE,
                "absolute",
                "maybe",
                composite=55,
                reasons=["more detail in the decisive read"],
                usage={"calls": 1},
            ),
            _record(
                "triage/downward",
                "demo/downward.jpg",
                DEMO_BASELINE_STAGE,
                "relative",
                "accept",
                composite=88,
                usage={"calls": 1},
            ),
            _record(
                "dedicated/downward",
                "demo/downward.jpg",
                DEMO_DECISIVE_STAGE,
                "absolute",
                "reject",
                composite=32,
                usage={"calls": 1},
            ),
            _record(
                "triage/lateral",
                "demo/lateral.jpg",
                DEMO_BASELINE_STAGE,
                "relative",
                "maybe",
                composite=40,
                usage={"calls": 1},
            ),
            _record(
                "dedicated/lateral",
                "demo/lateral.jpg",
                DEMO_DECISIVE_STAGE,
                "absolute",
                "maybe",
                composite=70,
                usage={"calls": 1},
            ),
            _record(
                "triage/excluded",
                "demo/excluded.jpg",
                DEMO_BASELINE_STAGE,
                "relative",
                "maybe",
                composite=50,
                usage={"calls": 1},
            ),
            _record(
                "dedicated/excluded-a",
                "demo/excluded.jpg",
                DEMO_DECISIVE_STAGE,
                "absolute",
                "maybe",
                composite=50,
                usage={"calls": 1},
            ),
            _record(
                "dedicated/excluded-b",
                "demo/excluded.jpg",
                DEMO_DECISIVE_STAGE,
                "absolute",
                "accept",
                composite=75,
                usage={"calls": 1},
            ),
            _record(
                "repeat/robust-0",
                "demo/robust.jpg",
                "repeat",
                "absolute",
                "maybe",
                composite=50,
                context=_repeat_context("demo-robust", 0),
                usage={"calls": 1},
            ),
            _record(
                "repeat/robust-1",
                "demo/robust.jpg",
                "repeat",
                "absolute",
                "maybe",
                composite=54,
                context=_repeat_context("demo-robust", 1),
                usage={"calls": 1},
            ),
            _record(
                "repeat/soft-0",
                "demo/soft.jpg",
                "repeat",
                "absolute",
                "maybe",
                composite=60,
                context=_repeat_context("demo-soft", 0),
                usage={"calls": 1},
            ),
            _record(
                "repeat/soft-1",
                "demo/soft.jpg",
                "repeat",
                "absolute",
                "accept",
                composite=70,
                context=_repeat_context("demo-soft", 1),
                usage={"calls": 1},
            ),
            _record(
                "repeat/unstable-0",
                "demo/unstable.jpg",
                "repeat",
                "absolute",
                "accept",
                composite=80,
                context=_repeat_context("demo-unstable", 0),
                usage={"calls": 1},
            ),
            _record(
                "repeat/unstable-1",
                "demo/unstable.jpg",
                "repeat",
                "absolute",
                "reject",
                composite=20,
                context=_repeat_context("demo-unstable", 1),
                usage={"calls": 1},
            ),
            _record(
                "cost/estimated",
                "demo/estimated.jpg",
                "cost-estimate",
                "other",
                "maybe",
                context={"model": "demo-model", "currency": "USD"},
                usage={"input_tokens": 1_000_000, "calls": 1},
            ),
            _record(
                "cost/unknown",
                "demo/unknown.jpg",
                "cost-unknown",
                "other",
                "maybe",
            ),
        ],
    }


def _source_date_epoch() -> str | int:
    return os.environ.get("SOURCE_DATE_EPOCH", DEFAULT_SOURCE_DATE_EPOCH)


def run_demo(output_dir: str | os.PathLike[str]) -> tuple[Path, Path]:
    """Run the keyless demo and return ``(audit.json, report.md)`` paths.

    The raw document is serialized only in memory.  It is then passed through
    the normal JSON ingestion and contract validation path before the shared
    audit builder and renderer write both artifacts atomically.
    """
    raw_document = _demo_document()
    raw_input = json.dumps(
        raw_document, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    result = ingest_json(raw_input.decode("utf-8"), source="<demo>")
    if result.errors or result.document is None:
        details = "; ".join(str(issue) for issue in result.errors)
        raise AuditContractError(f"built-in demo fixture is invalid: {details}")

    audit = build_audit(
        result.records,
        baseline_stage=DEMO_BASELINE_STAGE,
        decisive_stage=DEMO_DECISIVE_STAGE,
        input_sha256=hashlib.sha256(raw_input).hexdigest(),
        generated_at=_generated_at(_source_date_epoch()),
        photo_root=None,
        discovery=None,
        price_table=DEMO_PRICE_TABLE,
    )
    audit_json = json.dumps(
        audit, ensure_ascii=False, sort_keys=False, separators=(",", ":")
    )
    report = render_report(audit)
    output_path = Path(output_dir)
    audit_path = output_path / "audit.json"
    report_path = output_path / "report.md"
    _atomic_write(audit_path, audit_json + "\n")
    _atomic_write(report_path, report)
    return audit_path, report_path
