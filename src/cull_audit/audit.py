"""Orchestration for deterministic cull-audit artifacts.

This module is intentionally a thin boundary around the already-pure
contract, discovery, metric, and cost modules.  It owns filesystem access and
the audit output shape; it does not contain a second implementation of any
metric.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import TYPE_CHECKING, Any, Mapping, Sequence

from .contracts import JudgmentRecord
from .costs import CostSummary, PriceTable, load_price_table, summarize_costs
from .ingest import IngestResult, ingest
from .metrics import MetricsResult, compute_metrics
from .render import render_report

if TYPE_CHECKING:
    from .discover import DiscoveryResult


class AuditError(Exception):
    """Base class for errors which should be shown by the CLI."""


class AuditContractError(AuditError):
    """The input or requested audit configuration is invalid."""


class AuditIOError(AuditError):
    """A local file or directory could not be read or written."""


def _generated_at(source_date_epoch: int | float | str | None) -> str:
    if source_date_epoch is None:
        source_date_epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if source_date_epoch is None:
        value = datetime.now(timezone.utc)
    else:
        try:
            value = datetime.fromtimestamp(float(source_date_epoch), timezone.utc)
        except (OverflowError, OSError, TypeError, ValueError) as exc:
            raise AuditContractError("source_date_epoch must be a valid Unix timestamp") from exc
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def _read_input(path: str | os.PathLike[str]) -> tuple[IngestResult, str]:
    """Read judgments once, retaining the digest of their raw UTF-8 bytes."""
    if str(path) == "-":
        import sys

        try:
            text = sys.stdin.read()
            raw = text.encode("utf-8")
        except (OSError, UnicodeError) as exc:
            raise AuditIOError(f"unable to read judgments <stdin>: {exc}") from exc
        result = ingest("-", stream=__import__("io").StringIO(text))
        return result, hashlib.sha256(raw).hexdigest()
    try:
        raw = Path(path).read_bytes()
    except (OSError, UnicodeError) as exc:
        raise AuditIOError(f"unable to read judgments {path}: {exc}") from exc
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AuditContractError(f"judgments are not valid UTF-8: {path}") from exc
    if str(path).lower().endswith((".jsonl", ".ndjson")):
        from .ingest import ingest_jsonl

        result = ingest_jsonl(text, source=str(path))
    else:
        from .ingest import ingest_json

        result = ingest_json(text, source=str(path))
    return result, hashlib.sha256(raw).hexdigest()


def _json_number(value: Any) -> Any:
    """Convert Decimal values returned by cost accounting to JSON numbers."""
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return float(value)
    return value


def _cost_dict(summary: CostSummary) -> dict[str, Any]:
    value = summary.to_dict()
    # Cost assessments and cost warnings are internal accounting details:
    # warnings are promoted to the audit warning list and the public cost
    # contract contains only its documented summary fields.
    return {
        "currency": value["currency"],
        "known_total": _json_number(value["known_total"]),
        "estimated_total": _json_number(value["estimated_total"]),
        "unknown_records": value["unknown_records"],
        "by_stage": {
            stage: {
                key: _json_number(raw) if key.endswith("_total") else raw
                for key, raw in (
                    (key, value["by_stage"][stage][key])
                    for key in (
                        "known_total",
                        "estimated_total",
                        "known_records",
                        "estimated_records",
                        "unknown_records",
                    )
                    if key in value["by_stage"][stage]
                )
            }
            for stage in sorted(value["by_stage"])
        },
        "token_totals": {
            key: value["token_totals"][key]
            for key in ("input_tokens", "output_tokens", "thinking_tokens")
        },
    }


def _discovery_warnings(
    discovery: DiscoveryResult, records: Sequence[JudgmentRecord]
) -> list[str]:
    referenced = {record.photo_id for record in records}
    warnings: list[str] = []
    warnings.extend(f"unreadable photo: {photo_id}" for photo_id in discovery.unreadable)
    warnings.extend(
        "duplicate photo bytes: " + ", ".join(group)
        for group in discovery.duplicate_groups
    )
    warnings.extend(
        f"discovered photo is not referenced by judgments: {entry.path}"
        for entry in discovery.entries
        if entry.photo_id not in referenced
    )
    discovered = {entry.photo_id for entry in discovery.entries}
    warnings.extend(
        f"judgment photo is not discoverable: {photo_id}"
        for photo_id in sorted(referenced - discovered - set(discovery.unreadable))
    )
    return warnings


def _metric_warnings(metrics: MetricsResult) -> list[str]:
    warnings = [
        f"photo {item.photo_id} excluded from pairing: {item.reason}"
        for item in metrics.coverage.exclusions
    ]
    warnings.extend(
        f"repeat group {item.repeat_group} excluded from stability: {item.reason}"
        for item in metrics.stability.exclusions
    )
    return warnings


def _photo_joins(
    records: Sequence[JudgmentRecord],
    metrics: MetricsResult,
    discovery: DiscoveryResult | None,
    cost: CostSummary,
) -> list[dict[str, Any]]:
    ids = {record.photo_id for record in records}
    if discovery is not None:
        ids.update(entry.photo_id for entry in discovery.entries)
        ids.update(discovery.unreadable)
    flip_by_photo = {item.photo_id: item.to_dict() for item in metrics.flips.items}
    stability_by_photo: dict[str, list[dict[str, Any]]] = {}
    for item in metrics.stability.items:
        stability_by_photo.setdefault(item.photo_id, []).append(item.to_dict())
    assessments = {item.record_id: item.to_dict() for item in cost.assessments}
    records_by_photo: dict[str, list[JudgmentRecord]] = {}
    for record in records:
        records_by_photo.setdefault(record.photo_id, []).append(record)

    result: list[dict[str, Any]] = []
    discovered_ids = (
        {entry.photo_id for entry in discovery.entries} if discovery is not None else set()
    )
    for photo_id in sorted(ids):
        photo_records = sorted(records_by_photo.get(photo_id, ()), key=lambda item: item.record_id)
        result.append(
            {
                "photo_id": photo_id,
                "discovered": photo_id in discovered_ids,
                "record_ids": [item.record_id for item in photo_records],
                "judgments": [
                    {
                        "record_id": item.record_id,
                        "stage": item.stage,
                        "verdict": item.verdict,
                        "composite": item.composite,
                        "reasons": list(item.reasons),
                        "kill_factors": list(item.kill_factors),
                    }
                    for item in photo_records
                ],
                "costs": [
                    assessments[item.record_id]
                    for item in photo_records
                    if item.record_id in assessments
                ],
                "flip": flip_by_photo.get(photo_id),
                "stability": stability_by_photo.get(photo_id, []),
            }
        )
    return result


def build_audit(
    records: Sequence[JudgmentRecord],
    *,
    baseline_stage: str,
    decisive_stage: str,
    input_sha256: str,
    generated_at: str,
    photo_root: str | os.PathLike[str] | None = None,
    discovery: DiscoveryResult | None = None,
    price_table: PriceTable | Mapping[str, Any] | str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """Build the complete normalized audit object without writing files."""
    if not isinstance(input_sha256, str) or len(input_sha256) != 64:
        raise AuditContractError("input_sha256 must be a SHA-256 hex digest")
    try:
        metrics = compute_metrics(records, baseline_stage, decisive_stage)
    except (TypeError, ValueError) as exc:
        raise AuditContractError(str(exc)) from exc
    try:
        costs = summarize_costs(records, price_table)
    except ValueError as exc:
        raise AuditContractError(str(exc)) from exc

    warnings = _metric_warnings(metrics)
    warnings.extend(costs.warnings)
    if discovery is not None:
        warnings.extend(_discovery_warnings(discovery, records))
    warnings = sorted(set(warnings))

    coverage = metrics.coverage.to_dict()
    coverage = {
        "photos_discovered": 0 if discovery is None else len(discovery.entries),
        "baseline_unique_photos": coverage["baseline_unique_photos"],
        "decisive_unique_photos": coverage["decisive_unique_photos"],
        "paired_photos": coverage["paired_photos"],
        "excluded_photos": coverage["excluded_photos"],
    }
    stability = metrics.stability.to_dict()
    # Stability exclusions are represented as warnings, while the v1 audit
    # contract keeps the stability object focused on its denominator and
    # eligible findings.
    stability.pop("exclusions", None)
    return {
        "schema_version": "1.0",
        "tool": {"name": "cull-audit", "version": __import__("cull_audit").__version__},
        "run": {
            "baseline_stage": baseline_stage,
            "decisive_stage": decisive_stage,
            "photo_root": None if photo_root is None else str(photo_root),
            "input_sha256": input_sha256,
            "generated_at": generated_at,
        },
        "coverage": coverage,
        "flips": metrics.flips.to_dict(),
        "stability": stability,
        "cost": _cost_dict(costs),
        "photos": _photo_joins(records, metrics, discovery, costs),
        "warnings": warnings,
    }


def _atomic_write(path: Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = handle.name
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    except OSError as exc:
        raise AuditIOError(f"unable to write {path}: {exc}") from exc
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except OSError:
                pass


def run_audit(
    judgments: str | os.PathLike[str],
    *,
    baseline_stage: str,
    decisive_stage: str,
    output: str | os.PathLike[str],
    photos: str | os.PathLike[str] | None = None,
    prices: str | os.PathLike[str] | Mapping[str, Any] | None = None,
    source_date_epoch: int | float | str | None = None,
    strict: bool = False,
) -> dict[str, Any]:
    """Read inputs, calculate an audit, and atomically write both artifacts."""
    result, input_sha256 = _read_input(judgments)
    if result.errors:
        raise AuditContractError("; ".join(str(issue) for issue in result.errors))
    if result.document is None:
        raise AuditContractError("judgments did not produce a valid document")

    discovery: DiscoveryResult | None = None
    if photos is not None:
        try:
            from .discover import discover

            discovery = discover(photos)
        except (OSError, ValueError) as exc:
            raise AuditIOError(f"unable to discover photos under {photos}: {exc}") from exc

    price_table: PriceTable | Mapping[str, Any] | None = None
    if prices is not None:
        try:
            price_table = load_price_table(prices)
        except OSError as exc:
            raise AuditIOError(f"unable to read prices {prices}: {exc}") from exc
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise AuditContractError(f"invalid price table {prices}: {exc}") from exc

    audit = build_audit(
        result.records,
        baseline_stage=baseline_stage,
        decisive_stage=decisive_stage,
        input_sha256=input_sha256,
        generated_at=_generated_at(source_date_epoch),
        photo_root=photos,
        discovery=discovery,
        price_table=price_table,
    )
    if strict and audit["warnings"]:
        raise AuditContractError(
            "strict audit rejected warnings: " + "; ".join(audit["warnings"])
        )

    output_path = Path(output)
    try:
        audit_json = json.dumps(
            audit, ensure_ascii=False, sort_keys=False, separators=(",", ":")
        )
        report = render_report(audit)
        _atomic_write(output_path / "audit.json", audit_json + "\n")
        _atomic_write(output_path / "report.md", report)
    except AuditIOError:
        raise
    except OSError as exc:
        raise AuditIOError(f"unable to write audit output {output}: {exc}") from exc
    return audit
