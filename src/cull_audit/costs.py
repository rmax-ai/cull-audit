"""Pure, auditable cost accounting for normalized judgment records.

The module never contacts a pricing service.  A caller-supplied price table is
a versioned JSON object with this shape (prices are decimal strings)::

    {
      "version": "1.0",
      "model": "provider/model",
      "currency": "USD",
      "unit": "per_million_tokens",
      "effective": "2026-01-01",
      "prices": {
        "input": "0.20",
        "output": "0.80",
        "thinking": "0.80"
      }
    }

``effective`` is the table's effective label.  An optional ``call`` price
may be supplied for a per-call charge, and ``units`` may override the token
unit for an individual category.  ``schema_version`` is accepted as a
backward-compatible spelling of ``version``.  The module reads only the path
provided by the caller; it does not make network requests.

Cost precedence is deliberately conservative: an explicit provider/producer
total is known; otherwise non-overlapping producer components are known;
otherwise a matching table is used for a Decimal calculation and the result
is estimated; otherwise the record is unknown.  Explicit totals are retained
without conversion, including an explicit zero.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence


_TOKEN_NAMES = ("input_tokens", "output_tokens", "thinking_tokens")
_COMPONENT_GROUPS = {
    "input": "input",
    "input_tokens": "input",
    "output": "output",
    "output_tokens": "output",
    "thinking": "thinking",
    "thinking_tokens": "thinking",
    "call": "call",
    "calls": "call",
}
_UNIT_DENOMINATORS = {
    "token": Decimal(1),
    "per_token": Decimal(1),
    "per_million_tokens": Decimal(1000000),
    "per_1k_tokens": Decimal(1000),
    "per_1000_tokens": Decimal(1000),
    "per_1m_tokens": Decimal(1000000),
    "per_1000000_tokens": Decimal(1000000),
}


def _json_number(value: Decimal | int | float | str) -> int | float:
    """Turn an internal Decimal into a JSON number, never a quoted string."""
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("cost values must be finite")
        if value == value.to_integral_value():
            return int(value)
        return float(value)
    if isinstance(value, bool):
        raise ValueError("cost values must be numeric")
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("cost values must be finite")
        return value
    return _json_number(_decimal(value, "cost"))


def _decimal(value: Any, label: str) -> Decimal:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a finite non-negative number")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{label} must be a finite non-negative number") from exc
    if not result.is_finite() or result < 0:
        raise ValueError(f"{label} must be a finite non-negative number")
    return result


def _value(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    value = getattr(obj, name, default)
    if value is not default:
        return value
    unknown_fields = getattr(obj, "unknown_fields", {})
    if isinstance(unknown_fields, Mapping):
        return unknown_fields.get(name, default)
    return default


def _record_metadata(record: Any, name: str) -> Any:
    """Read metadata from mappings and contracts without requiring one shape."""
    aliases = {
        "effective": ("effective", "effective_label"),
        "unit": ("unit",),
        "currency": ("currency",),
        "model": ("model",),
    }.get(name, (name,))
    for candidate_name in aliases:
        direct = _value(record, candidate_name)
        if direct is not None:
            return direct
    for container_name in ("context", "usage", "cost"):
        container = _value(record, container_name)
        for candidate_name in aliases:
            candidate = _value(container, candidate_name)
            if candidate is not None:
                return candidate
    return None


def _record_usage(record: Any) -> Any:
    return _value(record, "usage")


def _record_id(record: Any, fallback: int | str = "?") -> str:
    return str(_value(record, "record_id", fallback))


def _record_stage(record: Any) -> str:
    return str(_value(record, "stage", ""))


@dataclass(frozen=True, slots=True)
class PriceTable:
    """A validated, immutable local price table."""

    schema_version: str
    model: str
    currency: str
    unit: str
    effective: str
    prices: Mapping[str, Decimal]
    units: Mapping[str, str] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "PriceTable":
        if not isinstance(value, Mapping):
            raise ValueError("price table must be an object")
        version = value.get("schema_version", value.get("version"))
        if version not in {"1.0", "1"}:
            raise ValueError("price table version must be '1.0'")
        effective = value.get("effective", value.get("effective_label"))
        required = ("model", "currency", "unit")
        missing = [
            name
            for name in required
            if not isinstance(value.get(name), str) or not value[name]
        ]
        if not isinstance(effective, str) or not effective:
            missing.append("effective")
        if missing:
            raise ValueError("price table missing " + ", ".join(missing))
        if value["unit"] not in _UNIT_DENOMINATORS:
            raise ValueError(f"unsupported price table unit: {value['unit']}")
        raw_prices = value.get("prices", value.get("rates"))
        if not isinstance(raw_prices, Mapping) or not raw_prices:
            raise ValueError("price table prices must be a non-empty object")
        prices: dict[str, Decimal] = {}
        for name, raw in raw_prices.items():
            if name not in {"input", "output", "thinking", "call", "input_tokens", "output_tokens", "thinking_tokens", "calls"}:
                raise ValueError(f"unknown price table category: {name}")
            canonical = _COMPONENT_GROUPS[name]
            if canonical in prices:
                raise ValueError(f"duplicate price table category: {canonical}")
            prices[canonical] = _decimal(raw, f"price table prices.{name}")
        raw_units = value.get("units", {})
        if not isinstance(raw_units, Mapping):
            raise ValueError("price table units must be an object")
        units: dict[str, str] = {}
        for name, raw_unit in raw_units.items():
            canonical = _COMPONENT_GROUPS.get(name, name)
            if canonical not in {"input", "output", "thinking", "call"}:
                raise ValueError(f"unknown price table unit category: {name}")
            if not isinstance(raw_unit, str) or raw_unit not in _UNIT_DENOMINATORS:
                raise ValueError(f"unsupported price table unit: {raw_unit}")
            units[canonical] = raw_unit
        return cls(
            str(version),
            value["model"],
            value["currency"],
            value["unit"],
            effective,
            prices,
            units,
        )

    @property
    def version(self) -> str:
        """The canonical version label for callers using the documented name."""
        return self.schema_version

    @property
    def effective_label(self) -> str:
        """The effective label under the descriptive field name."""
        return self.effective

    def to_dict(self) -> dict[str, Any]:
        prices = {name: _json_number(self.prices[name]) for name in sorted(self.prices)}
        result: dict[str, Any] = {
            "version": self.schema_version,
            "model": self.model,
            "currency": self.currency,
            "unit": self.unit,
            "effective": self.effective,
            "prices": prices,
        }
        if self.units:
            result["units"] = {name: self.units[name] for name in sorted(self.units)}
        return result

    as_dict = to_dict


def load_price_table(path: str | Path | Mapping[str, Any]) -> PriceTable:
    """Load and validate a versioned table from a path or mapping."""
    if isinstance(path, Mapping):
        return PriceTable.from_mapping(path)
    with Path(path).open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    return PriceTable.from_mapping(value)


@dataclass(frozen=True, slots=True)
class CostAssessment:
    """Classification and value for one record."""

    record_id: str
    stage: str
    classification: str
    total: Any | None
    currency: str | None
    source: str | None
    reason: str | None = None

    @property
    def status(self) -> str:
        """Alias used by callers that call the classification a status."""
        return self.classification

    def to_dict(self) -> dict[str, Any]:
        if self.classification == "known" and self.reason == "explicit total":
            serialized_total = self.total
        else:
            serialized_total = None if self.total is None else _json_number(self.total)
        result = {
            "record_id": self.record_id,
            "stage": self.stage,
            "classification": self.classification,
            "total": serialized_total,
            "currency": self.currency,
            "source": self.source,
        }
        if self.reason is not None:
            result["reason"] = self.reason
        return result

    as_dict = to_dict


@dataclass(frozen=True, slots=True)
class CostSummary:
    """Deterministic aggregate suitable for embedding in ``audit.json``."""

    currency: str | None
    known_total: Any
    estimated_total: Any
    unknown_records: int
    by_stage: Mapping[str, Mapping[str, Any]]
    token_totals: Mapping[str, int]
    assessments: tuple[CostAssessment, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def known(self) -> Any:
        return self.known_total

    @property
    def estimated(self) -> Any:
        return self.estimated_total

    @property
    def known_records(self) -> int:
        return sum(item.classification == "known" for item in self.assessments)

    @property
    def estimated_records(self) -> int:
        return sum(item.classification == "estimated" for item in self.assessments)

    def to_dict(self) -> dict[str, Any]:
        def stage_dict(item: Mapping[str, Any]) -> dict[str, Any]:
            return {
                name: _json_number(item[name]) if name.endswith("_total") else item[name]
                for name in sorted(item)
            }

        return {
            "currency": self.currency,
            "known_total": _json_number(self.known_total),
            "estimated_total": _json_number(self.estimated_total),
            "known_records": self.known_records,
            "estimated_records": self.estimated_records,
            "unknown_records": self.unknown_records,
            "by_stage": {
                stage: stage_dict(self.by_stage[stage]) for stage in sorted(self.by_stage)
            },
            "token_totals": {
                name: self.token_totals[name] for name in ("input_tokens", "output_tokens", "thinking_tokens")
            },
            "assessments": [item.to_dict() for item in self.assessments],
            "warnings": list(self.warnings),
        }

    as_dict = to_dict

    def to_json(self, **kwargs: Any) -> str:
        """Serialize as JSON, retaining table-derived values as JSON numbers."""
        return json.dumps(self.to_dict(), **kwargs)


def _table_metadata_warnings(record: Any, table: PriceTable) -> list[str]:
    warnings: list[str] = []
    required_checks = (
        ("model", table.model, "model"),
        ("currency", table.currency, "currency"),
    )
    for field_name, expected, display_name in required_checks:
        actual = _record_metadata(record, field_name)
        if actual is None:
            warnings.append(f"{_record_id(record)}: missing {display_name} metadata")
        elif actual != expected:
            warnings.append(
                f"{_record_id(record)}: {display_name} mismatch "
                f"({actual!r} != {expected!r})"
            )
    optional_checks = (
        ("unit", table.unit, "unit"),
        ("effective", table.effective, "effective"),
    )
    for field_name, expected, display_name in optional_checks:
        actual = _record_metadata(record, field_name)
        if actual is not None and actual != expected:
            warnings.append(
                f"{_record_id(record)}: {display_name} mismatch "
                f"({actual!r} != {expected!r})"
            )
    return warnings


def _cost_object(record: Any) -> Any:
    usage = _record_usage(record)
    return _value(usage, "cost")


def _explicit_total(record: Any) -> tuple[Any, str] | None:
    cost = _cost_object(record)
    total = _value(cost, "total")
    source = _value(cost, "source")
    if total is not None and source in {"provider", "producer"}:
        _decimal(total, "explicit cost total")
        return total, str(source)
    return None


def _components(record: Any) -> tuple[Decimal, str] | None:
    cost = _cost_object(record)
    raw = _value(cost, "components")
    source = _value(cost, "source")
    if not isinstance(raw, Mapping) or source not in {"provider", "producer"} or not raw:
        return None
    groups: set[str] = set()
    total = Decimal(0)
    for key in sorted(raw):
        group = _COMPONENT_GROUPS.get(str(key))
        if group is None:
            group = str(key)
        if group in groups:
            return None
        groups.add(group)
        total += _decimal(raw[key], f"cost component {key}")
    return total, str(source)


def _has_component_overlap(record: Any) -> bool:
    cost = _cost_object(record)
    raw = _value(cost, "components")
    if not isinstance(raw, Mapping):
        return False
    groups: set[str] = set()
    for key in raw:
        group = _COMPONENT_GROUPS.get(str(key), str(key))
        if group in groups:
            return True
        groups.add(group)
    return False


def _table_cost(record: Any, table: PriceTable) -> Decimal | None:
    usage = _record_usage(record)
    if usage is None:
        return None
    total = Decimal(0)
    found = False
    for token_name in _TOKEN_NAMES:
        count = _value(usage, token_name)
        if count is None:
            continue
        group = token_name.removesuffix("_tokens")
        price = table.prices.get(group)
        if price is None:
            return None
        unit = table.units.get(group, table.unit)
        total += _decimal(count, token_name) * price / _UNIT_DENOMINATORS[unit]
        found = True
    calls = _value(usage, "calls", 1)
    if calls is not None and "call" in table.prices:
        total += _decimal(calls, "calls") * table.prices["call"]
        found = True
    return total if found else None


def assess_cost(
    record: Any,
    price_table: PriceTable | Mapping[str, Any] | str | Path | None = None,
    *,
    warnings: list[str] | None = None,
) -> CostAssessment:
    """Classify one record according to the documented precedence."""
    table = None if price_table is None else (
        price_table if isinstance(price_table, PriceTable) else load_price_table(price_table)
    )
    record_id = _record_id(record)
    stage = _record_stage(record)
    cost = _cost_object(record)
    currency = _value(cost, "currency")
    local_warnings: list[str] = []
    if _record_usage(record) is None:
        local_warnings.append(f"{record_id}: missing usage")
    else:
        usage = _record_usage(record)
        if _value(usage, "thinking_tokens") is not None and _value(usage, "output_tokens") is not None:
            local_warnings.append(
                f"{record_id}: thinking token semantics may overlap output_tokens"
            )
    if _has_component_overlap(record):
        local_warnings.append(f"{record_id}: overlapping cost components rejected")

    explicit = _explicit_total(record)
    if explicit is not None:
        result = CostAssessment(record_id, stage, "known", explicit[0], currency, explicit[1], "explicit total")
    else:
        components = _components(record)
        if components is not None:
            result = CostAssessment(record_id, stage, "known", components[0], currency, components[1], "explicit components")
        elif table is not None and not _has_component_overlap(record):
            metadata_warnings = (
                _table_metadata_warnings(record, table)
                if _record_usage(record) is not None
                else []
            )
            local_warnings.extend(metadata_warnings)
            if not metadata_warnings:
                calculated = _table_cost(record, table)
            else:
                calculated = None
            if calculated is not None:
                result = CostAssessment(
                    record_id,
                    stage,
                    "estimated",
                    calculated,
                    table.currency,
                    "price_table",
                    "local Decimal calculation",
                )
            else:
                result = CostAssessment(record_id, stage, "unknown", None, currency, None, "insufficient usage or price table")
        else:
            result = CostAssessment(record_id, stage, "unknown", None, currency, None, "no usable cost")
    if warnings is not None:
        warnings.extend(local_warnings)
    return result


def summarize_costs(
    records: Sequence[Any],
    price_table: PriceTable | Mapping[str, Any] | str | Path | None = None,
) -> CostSummary:
    """Summarize records without mutating them or making network requests."""
    table = None if price_table is None else (
        price_table if isinstance(price_table, PriceTable) else load_price_table(price_table)
    )
    warnings: list[str] = []
    assessments: list[CostAssessment] = []
    known = Decimal(0)
    estimated = Decimal(0)
    unknown = 0
    token_totals = {name: 0 for name in _TOKEN_NAMES}
    by_stage: dict[str, dict[str, Any]] = {}
    currencies: set[str] = set()
    for record in records:
        usage = _record_usage(record)
        if usage is not None:
            for name in _TOKEN_NAMES:
                value = _value(usage, name)
                if value is not None:
                    token_totals[name] += int(value)
        assessment = assess_cost(record, table, warnings=warnings)
        assessments.append(assessment)
        if assessment.currency:
            currencies.add(assessment.currency)
        if assessment.classification == "known":
            known += _decimal(assessment.total, "known cost")
        elif assessment.classification == "estimated":
            estimated += _decimal(assessment.total, "estimated cost")
        else:
            unknown += 1
        stage = assessment.stage
        bucket = by_stage.setdefault(
            stage,
            {
                "known_total": Decimal(0),
                "estimated_total": Decimal(0),
                "known_records": 0,
                "estimated_records": 0,
                "unknown_records": 0,
            },
        )
        if assessment.classification == "known":
            bucket["known_total"] += _decimal(assessment.total, "known stage cost")
            bucket["known_records"] += 1
        elif assessment.classification == "estimated":
            bucket["estimated_total"] += _decimal(assessment.total, "estimated stage cost")
            bucket["estimated_records"] += 1
        else:
            bucket["unknown_records"] += 1
    warnings = sorted(set(warnings))
    currency: str | None
    if len(currencies) == 1:
        currency = next(iter(currencies))
    elif len(currencies) > 1:
        currency = "mixed"
        warnings.append("multiple currencies present; totals are not directly comparable")
    else:
        currency = table.currency if table is not None else None
    return CostSummary(
        currency,
        known,
        estimated,
        unknown,
        {stage: by_stage[stage] for stage in sorted(by_stage)},
        token_totals,
        tuple(sorted(assessments, key=lambda item: (item.stage, item.record_id))),
        tuple(sorted(set(warnings))),
    )


# Friendly aliases for callers that use the verbs from the CLI/task wording.
parse_cost = assess_cost
calculate_costs = summarize_costs
parse_costs = summarize_costs
calculate_cost_summary = summarize_costs
load_prices = load_price_table
parse_price_table = load_price_table
CostResult = CostAssessment
CostReport = CostSummary
