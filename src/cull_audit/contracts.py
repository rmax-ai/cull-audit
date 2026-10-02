"""The version 1 judgment record contract.

The JSON schema in ``schemas/`` is useful to producers, but the application
does not depend on a schema package.  This module deliberately performs the
small amount of validation needed by the command line and turns accepted
records into immutable, JSON-friendly values.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
from pathlib import PurePosixPath
from pathlib import PureWindowsPath
from typing import Any, Mapping


READ_KINDS = frozenset({"relative", "absolute", "face_crop", "other"})
VERDICTS = frozenset({"accept", "maybe", "reject"})
_MISSING = object()


@dataclass(frozen=True)
class ValidationIssue:
    """A deterministic, JSON-serializable contract diagnostic."""

    path: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"path": self.path, "message": self.message}

    def __str__(self) -> str:
        return f"{self.path}: {self.message}"


@dataclass(frozen=True)
class Cost:
    currency: str
    total: float | int | str
    source: str
    components: Mapping[str, float | int | str] = field(default_factory=dict)
    unknown_fields: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "currency": self.currency,
            "total": self.total,
            "source": self.source,
        }
        if self.components:
            value["components"] = dict(self.components)
        value.update(self.unknown_fields)
        return value


@dataclass(frozen=True)
class Usage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    thinking_tokens: int | None = None
    calls: int = 1
    cost: Cost | None = None
    unknown_fields: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for name in ("input_tokens", "output_tokens", "thinking_tokens"):
            item = getattr(self, name)
            if item is not None:
                value[name] = item
        value["calls"] = self.calls
        if self.cost is not None:
            value["cost"] = self.cost.to_dict()
        value.update(self.unknown_fields)
        return value


@dataclass(frozen=True)
class Context:
    comparison_group: str | None = None
    repeat_group: str | None = None
    repeat_index: int | None = None
    input_max_edge_px: int | None = None
    prompt_id: str | None = None
    model: str | None = None
    settings_fingerprint: str | None = None
    unknown_fields: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for name in (
            "comparison_group",
            "repeat_group",
            "repeat_index",
            "input_max_edge_px",
            "prompt_id",
            "model",
            "settings_fingerprint",
        ):
            item = getattr(self, name)
            if item is not None:
                value[name] = item
            elif name in {"repeat_group", "repeat_index"} and (
                self.repeat_group is not None or self.repeat_index is not None
            ):
                value[name] = None
        value.update(self.unknown_fields)
        return value


@dataclass(frozen=True)
class Source:
    tool: str
    tool_version: str | None = None
    unknown_fields: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {"tool": self.tool}
        if self.tool_version is not None:
            value["tool_version"] = self.tool_version
        value.update(self.unknown_fields)
        return value


@dataclass(frozen=True)
class JudgmentRecord:
    record_id: str
    photo_id: str
    stage: str
    read_kind: str
    verdict: str
    source: Source
    composite: float | int | None = None
    scores: Mapping[str, float | int] = field(default_factory=dict)
    reasons: tuple[str, ...] = ()
    kill_factors: tuple[str, ...] = ()
    context: Context | None = None
    usage: Usage | None = None
    observed_at: str | None = None
    unknown_fields: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "record_id": self.record_id,
            "photo_id": self.photo_id,
            "stage": self.stage,
            "read_kind": self.read_kind,
            "verdict": self.verdict,
        }
        if self.composite is not None:
            value["composite"] = self.composite
        if self.scores:
            value["scores"] = dict(self.scores)
        if self.reasons:
            value["reasons"] = list(self.reasons)
        if self.kill_factors:
            value["kill_factors"] = list(self.kill_factors)
        if self.context is not None:
            value["context"] = self.context.to_dict()
        if self.usage is not None:
            value["usage"] = self.usage.to_dict()
        value["source"] = self.source.to_dict()
        if self.observed_at is not None:
            value["observed_at"] = self.observed_at
        value.update(self.unknown_fields)
        return value

    # ``as_dict`` is convenient for callers that treat normalized records as
    # ordinary mappings, while ``to_dict`` makes the round-trip intent clear.
    as_dict = to_dict


@dataclass(frozen=True)
class JudgmentDocument:
    schema_version: str
    records: tuple[JudgmentRecord, ...]
    unknown_fields: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "schema_version": self.schema_version,
            "records": [record.to_dict() for record in self.records],
        }
        value.update(self.unknown_fields)
        return value

    as_dict = to_dict


def _issue(issues: list[ValidationIssue], path: str, message: str) -> None:
    issues.append(ValidationIssue(path, message))


def sort_issues(issues: list[ValidationIssue]) -> list[ValidationIssue]:
    """Return diagnostics in a stable path-then-message order."""

    return sorted(issues, key=lambda issue: (issue.path, issue.message))


def _object(value: Any, path: str, issues: list[ValidationIssue]) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        _issue(issues, path, "must be an object")
        return None
    return value


def _string(
    value: Any,
    path: str,
    issues: list[ValidationIssue],
    *,
    required: bool = False,
    nonempty: bool = False,
) -> str | None:
    if value is _MISSING:
        if required:
            _issue(issues, path, "is required")
        return None
    if not isinstance(value, str):
        _issue(issues, path, "must be a string")
        return None
    if nonempty and not value:
        _issue(issues, path, "must not be empty")
        return None
    return value


def _number(value: Any, path: str, issues: list[ValidationIssue]) -> float | int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _issue(issues, path, "must be a finite number")
        return None
    if isinstance(value, float) and not math.isfinite(value):
        _issue(issues, path, "must be a finite number")
        return None
    return value


def _bounded_number(
    value: Any, path: str, issues: list[ValidationIssue]
) -> float | int | None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or (isinstance(value, float) and not math.isfinite(value))
        or not 0 <= value <= 100
    ):
        _issue(issues, path, "must be a finite number in [0,100]")
        return None
    return value


def _nonnegative_int(value: Any, path: str, issues: list[ValidationIssue]) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        _issue(issues, path, "must be a non-negative integer")
        return None
    if value < 0:
        _issue(issues, path, "must be a non-negative integer")
        return None
    return value


def _optional_string(
    obj: Mapping[str, Any], name: str, path: str, issues: list[ValidationIssue]
) -> str | None:
    value = obj.get(name, _MISSING)
    if value is None:
        return None
    return _string(value, path, issues)


def _photo_id(value: Any, path: str, issues: list[ValidationIssue]) -> str | None:
    result = _string(value, path, issues, required=True, nonempty=True)
    if result is None:
        return None
    # PurePosixPath alone accepts "." and normalizes away ".."; inspect the
    # original spelling first so unsafe IDs cannot become safe-looking IDs.
    if (
        result.startswith("/")
        or "\\" in result
        or "\x00" in result
        or PureWindowsPath(result).drive
    ):
        _issue(issues, path, "must be a safe relative POSIX path")
        return None
    path_parts = result.split("/")
    if any(part in {"", ".", ".."} for part in path_parts):
        _issue(issues, path, "must be a safe relative POSIX path")
        return None
    parsed = PurePosixPath(result)
    if parsed.is_absolute() or str(parsed) != result:
        _issue(issues, path, "must be a safe relative POSIX path")
        return None
    return result


def _validate_context(
    value: Any, path: str, issues: list[ValidationIssue]
) -> Context | None:
    obj = _object(value, path, issues)
    if obj is None:
        return None
    comparison_group = _optional_string(obj, "comparison_group", f"{path}.comparison_group", issues)
    repeat_group = _optional_string(obj, "repeat_group", f"{path}.repeat_group", issues)
    repeat_index_value = obj.get("repeat_index", _MISSING)
    repeat_index = (
        None
        if repeat_index_value is _MISSING or repeat_index_value is None
        else _nonnegative_int(repeat_index_value, f"{path}.repeat_index", issues)
    )
    edge_value = obj.get("input_max_edge_px", _MISSING)
    edge = (
        None
        if edge_value is _MISSING or edge_value is None
        else _nonnegative_int(edge_value, f"{path}.input_max_edge_px", issues)
    )
    known = {
        "comparison_group",
        "repeat_group",
        "repeat_index",
        "input_max_edge_px",
        "prompt_id",
        "model",
        "settings_fingerprint",
    }
    return Context(
        comparison_group=comparison_group,
        repeat_group=repeat_group,
        repeat_index=repeat_index,
        input_max_edge_px=edge,
        prompt_id=_optional_string(obj, "prompt_id", f"{path}.prompt_id", issues),
        model=_optional_string(obj, "model", f"{path}.model", issues),
        settings_fingerprint=_optional_string(
            obj, "settings_fingerprint", f"{path}.settings_fingerprint", issues
        ),
        unknown_fields={key: value for key, value in obj.items() if key not in known},
    )


def _validate_cost(value: Any, path: str, issues: list[ValidationIssue]) -> Cost | None:
    obj = _object(value, path, issues)
    if obj is None:
        return None
    currency = _string(obj.get("currency", _MISSING), f"{path}.currency", issues, required=True, nonempty=True)
    total = _number(obj.get("total", _MISSING), f"{path}.total", issues)
    if total is not None and total < 0:
        _issue(issues, f"{path}.total", "must be non-negative")
        total = None
    source = _string(obj.get("source", _MISSING), f"{path}.source", issues, required=True, nonempty=True)
    components: dict[str, float | int | str] = {}
    raw_components = obj.get("components", _MISSING)
    if raw_components is not _MISSING:
        component_obj = _object(raw_components, f"{path}.components", issues)
        if component_obj is not None:
            for key in sorted(component_obj):
                if not isinstance(key, str) or not key:
                    _issue(issues, f"{path}.components", "keys must be non-empty strings")
                    continue
                number = _number(component_obj[key], f"{path}.components.{key}", issues)
                if number is not None:
                    if number < 0:
                        _issue(issues, f"{path}.components.{key}", "must be non-negative")
                    else:
                        components[key] = number
    known = {"currency", "total", "source", "components"}
    if currency is None or total is None or source is None:
        return None
    return Cost(currency, total, source, components, {k: v for k, v in obj.items() if k not in known})


def _validate_usage(value: Any, path: str, issues: list[ValidationIssue]) -> Usage | None:
    obj = _object(value, path, issues)
    if obj is None:
        return None
    counters: dict[str, int | None] = {}
    for name in ("input_tokens", "output_tokens", "thinking_tokens"):
        raw = obj.get(name, _MISSING)
        counters[name] = (
            None
            if raw is _MISSING
            else _nonnegative_int(raw, f"{path}.{name}", issues)
        )
    raw_calls = obj.get("calls", _MISSING)
    calls = 1 if raw_calls is _MISSING else _nonnegative_int(
        raw_calls, f"{path}.calls", issues
    )
    cost = None
    if "cost" in obj and obj["cost"] is not None:
        cost = _validate_cost(obj["cost"], f"{path}.cost", issues)
    known = {"input_tokens", "output_tokens", "thinking_tokens", "calls", "cost"}
    if calls is None or any(
        name in obj and obj[name] is not None and counters[name] is None
        for name in ("input_tokens", "output_tokens", "thinking_tokens")
    ):
        return None
    return Usage(**counters, calls=calls, cost=cost, unknown_fields={k: v for k, v in obj.items() if k not in known})


def validate_record(value: Any, index: int = 0) -> tuple[JudgmentRecord | None, list[ValidationIssue]]:
    """Validate and normalize one record, preserving unrecognized fields."""

    path = f"$.records[{index}]"
    issues: list[ValidationIssue] = []
    obj = _object(value, path, issues)
    if obj is None:
        return None, issues
    record_id = _string(obj.get("record_id", _MISSING), f"{path}.record_id", issues, required=True, nonempty=True)
    photo_id = _photo_id(obj.get("photo_id", _MISSING), f"{path}.photo_id", issues)
    stage = _string(obj.get("stage", _MISSING), f"{path}.stage", issues, required=True, nonempty=True)
    read_kind = _string(obj.get("read_kind", _MISSING), f"{path}.read_kind", issues, required=True)
    if read_kind is not None and read_kind not in READ_KINDS:
        _issue(issues, f"{path}.read_kind", "must be one of: absolute, face_crop, other, relative")
    verdict = _string(obj.get("verdict", _MISSING), f"{path}.verdict", issues, required=True)
    if verdict is not None and verdict not in VERDICTS:
        _issue(issues, f"{path}.verdict", "must be one of: accept, maybe, reject")

    composite = None
    if "composite" in obj:
        composite = _bounded_number(obj["composite"], f"{path}.composite", issues)
    scores: dict[str, float | int] = {}
    if "scores" in obj:
        scores_obj = _object(obj["scores"], f"{path}.scores", issues)
        if scores_obj is not None:
            for name in sorted(scores_obj):
                if not isinstance(name, str) or not name:
                    _issue(issues, f"{path}.scores", "keys must be non-empty strings")
                    continue
                score = _bounded_number(scores_obj[name], f"{path}.scores.{name}", issues)
                if score is not None:
                    scores[name] = score

    def string_array(name: str) -> tuple[str, ...]:
        raw = obj.get(name, _MISSING)
        if raw is _MISSING or raw is None:
            if raw is None:
                _issue(issues, f"{path}.{name}", "must be an array of strings")
            return ()
        if not isinstance(raw, list):
            _issue(issues, f"{path}.{name}", "must be an array of strings")
            return ()
        result: list[str] = []
        for item, item_value in enumerate(raw):
            if not isinstance(item_value, str):
                _issue(issues, f"{path}.{name}[{item}]", "must be a string")
            else:
                result.append(item_value)
        return tuple(result)

    context = None if obj.get("context", _MISSING) in (_MISSING, None) else _validate_context(
        obj["context"], f"{path}.context", issues
    )
    usage = None if obj.get("usage", _MISSING) in (_MISSING, None) else _validate_usage(
        obj["usage"], f"{path}.usage", issues
    )
    source_value = obj.get("source", _MISSING)
    source_obj = _object(source_value, f"{path}.source", issues)
    source = None
    if source_obj is not None:
        tool = _string(source_obj.get("tool", _MISSING), f"{path}.source.tool", issues, required=True, nonempty=True)
        tool_version = _optional_string(source_obj, "tool_version", f"{path}.source.tool_version", issues)
        if tool is not None:
            source = Source(tool, tool_version, {k: v for k, v in source_obj.items() if k not in {"tool", "tool_version"}})

    reasons = string_array("reasons")
    kill_factors = string_array("kill_factors")
    observed_at = _optional_string(obj, "observed_at", f"{path}.observed_at", issues)
    if "observed_at" in obj and obj["observed_at"] is None:
        _issue(issues, f"{path}.observed_at", "must be a string")

    if issues or None in (record_id, photo_id, stage, read_kind, verdict, source):
        return None, sort_issues(issues)
    known = {
        "record_id", "photo_id", "stage", "read_kind", "verdict", "composite",
        "scores", "reasons", "kill_factors", "context", "usage", "source",
        "observed_at",
    }
    return JudgmentRecord(
        record_id, photo_id, stage, read_kind, verdict, source, composite, scores,
        reasons, kill_factors, context, usage,
        observed_at, {k: v for k, v in obj.items() if k not in known},
    ), sort_issues(issues)


def validate_document(value: Any) -> tuple[JudgmentDocument | None, list[ValidationIssue]]:
    """Validate the canonical document form and cross-record invariants."""

    issues: list[ValidationIssue] = []
    obj = _object(value, "$", issues)
    if obj is None:
        return None, sort_issues(issues)
    schema_version = _string(obj.get("schema_version", _MISSING), "$.schema_version", issues, required=True)
    if schema_version is not None and schema_version != "1.0":
        _issue(issues, "$.schema_version", "must equal '1.0'")
    raw_records = obj.get("records", _MISSING)
    if not isinstance(raw_records, list):
        _issue(issues, "$.records", "must be an array")
        return None, sort_issues(issues)
    records: list[JudgmentRecord] = []
    indexed_records: list[tuple[int, JudgmentRecord]] = []
    for index, raw in enumerate(raw_records):
        record, record_issues = validate_record(raw, index)
        issues.extend(record_issues)
        if record is not None:
            records.append(record)
            indexed_records.append((index, record))

    seen: dict[str, int] = {}
    for index, record in indexed_records:
        if record.record_id in seen:
            _issue(
                issues,
                f"$.records[{index}].record_id",
                f"must be unique; already used at $.records[{seen[record.record_id]}].record_id",
            )
        else:
            seen[record.record_id] = index

    repeat_groups: dict[str, list[tuple[int, JudgmentRecord]]] = {}
    for index, record in indexed_records:
        if record.context is not None:
            if record.context.repeat_index is not None and record.context.repeat_group is None:
                _issue(issues, f"$.records[{index}].context.repeat_group", "is required when repeat_index is provided")
            if record.context.repeat_group is not None:
                repeat_groups.setdefault(record.context.repeat_group, []).append((index, record))
    for group, members in sorted(repeat_groups.items()):
        photo_ids = {record.photo_id for _, record in members}
        fingerprints = {
            record.context.settings_fingerprint
            for _, record in members
            if record.context is not None
        }
        if len(photo_ids) > 1:
            for index, record in members:
                _issue(issues, f"$.records[{index}].context.repeat_group", f"repeat group {group!r} must contain one photo_id")
        if len(fingerprints) != 1 or None in fingerprints:
            for index, record in members:
                _issue(issues, f"$.records[{index}].context.settings_fingerprint", f"repeat group {group!r} must share one settings_fingerprint")
        indexes = [record.context.repeat_index for _, record in members if record.context is not None]
        if len(indexes) != len(members) or any(item is None for item in indexes):
            for index, record in members:
                _issue(issues, f"$.records[{index}].context.repeat_index", f"repeat group {group!r} requires a zero-based repeat_index")
        elif len(indexes) != len(set(indexes)):
            for index, record in members:
                _issue(issues, f"$.records[{index}].context.repeat_index", f"repeat group {group!r} must have unique repeat_index values")
        elif min(indexes) != 0:
            for index, record in members:
                _issue(issues, f"$.records[{index}].context.repeat_index", f"repeat group {group!r} indexes must start at zero")

    if schema_version is None or schema_version != "1.0" or issues:
        return None, sort_issues(issues)
    known = {"schema_version", "records"}
    return (
        JudgmentDocument(
            schema_version,
            tuple(records),
            {k: v for k, v in obj.items() if k not in known},
        ),
        sort_issues(issues),
    )


def validate_records(records: list[Any] | tuple[Any, ...]) -> tuple[tuple[JudgmentRecord, ...], list[ValidationIssue]]:
    """Validate record objects supplied without a document wrapper."""

    document, issues = validate_document({"schema_version": "1.0", "records": list(records)})
    return (() if document is None else document.records), issues


def issues_as_json(issues: list[ValidationIssue]) -> list[dict[str, str]]:
    return [issue.as_dict() for issue in issues]


def dumps_normalized(value: JudgmentDocument | JudgmentRecord) -> str:
    """Return stable JSON useful to producers and tests."""

    payload = value.to_dict()
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
