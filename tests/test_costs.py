from __future__ import annotations

from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest

from cull_audit.costs import (
    PriceTable,
    assess_cost,
    load_price_table,
    summarize_costs,
)


def record(record_id: str, **usage: object) -> dict[str, object]:
    return {"record_id": record_id, "stage": "triage", "usage": usage}


TABLE = {
    "schema_version": "1.0",
    "model": "vision-1",
    "currency": "USD",
    "unit": "per_1m_tokens",
    "effective": "2026-01-01",
    "prices": {"input": "0.20", "output": "0.80", "thinking": "1.00", "call": "0.01"},
}


class CostTests(unittest.TestCase):
    def test_provider_total_has_precedence_and_zero_is_known(self) -> None:
        result = assess_cost(
            record(
                "provider",
                input_tokens=100,
                cost={"currency": "USD", "total": 0, "source": "provider"},
            )
        )
        self.assertEqual(result.classification, "known")
        self.assertEqual(result.total, 0)
        self.assertEqual(result.source, "provider")

    def test_explicit_total_beats_components(self) -> None:
        result = assess_cost(
            record(
                "total-wins",
                cost={
                    "currency": "USD",
                    "total": "1.25",
                    "source": "producer",
                    "components": {"input": "9.00", "output": "8.00"},
                },
            )
        )
        self.assertEqual(result.classification, "known")
        self.assertEqual(result.total, "1.25")
        self.assertEqual(result.reason, "explicit total")

    def test_producer_total_is_preserved_exactly(self) -> None:
        result = assess_cost(
            record(
                "producer",
                cost={"currency": "USD", "total": "0.004200", "source": "producer"},
            )
        )
        self.assertEqual(result.total, "0.004200")
        self.assertEqual(result.classification, "known")

    def test_components_sum_when_non_overlapping(self) -> None:
        result = assess_cost(
            record(
                "components",
                cost={
                    "currency": "USD",
                    "source": "producer",
                    "components": {"input": "0.10", "output": 0.25, "cache_read": 0.05},
                },
            )
        )
        self.assertEqual(result.classification, "known")
        self.assertEqual(result.total, Decimal("0.40"))

    def test_overlapping_component_categories_are_unknown(self) -> None:
        result = assess_cost(
            record(
                "overlap",
                cost={
                    "currency": "USD",
                    "source": "producer",
                    "components": {"input": 1, "input_tokens": 2},
                },
            )
        )
        self.assertEqual(result.classification, "unknown")
        self.assertIn("no usable cost", result.reason or "")
        summary = summarize_costs(
            [
                record(
                    "overlap",
                    cost={
                        "currency": "USD",
                        "source": "producer",
                        "components": {"input": 1, "input_tokens": 2},
                    },
                )
            ]
        )
        self.assertEqual(summary.unknown_records, 1)
        self.assertIn("overlapping cost components rejected", summary.warnings[0])

    def test_table_uses_decimal_and_keeps_token_categories_separate(self) -> None:
        summary = summarize_costs(
            [
                {
                    "record_id": "estimate",
                    "stage": "dedicated",
                    "context": {"model": "vision-1", "currency": "USD"},
                    "usage": {
                        "input_tokens": 1_000_000,
                        "output_tokens": 2_000_000,
                        "thinking_tokens": 3_000_000,
                        "calls": 2,
                    },
                }
            ],
            TABLE,
        )
        self.assertEqual(summary.estimated_total, Decimal("4.82"))
        self.assertEqual(summary.token_totals, {
            "input_tokens": 1_000_000,
            "output_tokens": 2_000_000,
            "thinking_tokens": 3_000_000,
        })
        self.assertEqual(summary.to_dict()["estimated_total"], 4.82)
        self.assertIsInstance(summary.to_dict()["estimated_total"], (int, float))

    def test_decimal_table_arithmetic_does_not_use_binary_float(self) -> None:
        table = {
            **TABLE,
            "prices": {"input": "0.1", "output": "0.2"},
        }
        result = assess_cost(
            {
                "record_id": "decimal",
                "stage": "triage",
                "context": {"model": "vision-1", "currency": "USD"},
                "usage": {"input_tokens": 1_000_000, "output_tokens": 1_000_000},
            },
            table,
        )
        self.assertEqual(result.total, Decimal("0.3"))
        self.assertEqual(result.to_dict()["total"], 0.3)

    def test_matching_metadata_required_for_table_estimate(self) -> None:
        item = {
            "record_id": "mismatch",
            "stage": "triage",
            "context": {"model": "other-model", "currency": "USD"},
            "usage": {"input_tokens": 10},
        }
        result = assess_cost(item, TABLE)
        self.assertEqual(result.classification, "unknown")
        summary = summarize_costs([item], TABLE)
        self.assertTrue(any("model mismatch" in warning for warning in summary.warnings))

    def test_currency_unit_and_effective_mismatches_warn(self) -> None:
        item = {
            "record_id": "mismatches",
            "stage": "triage",
            "context": {
                "model": "vision-1",
                "currency": "EUR",
                "unit": "per_1k_tokens",
                "effective": "2025-01-01",
            },
            "usage": {"input_tokens": 10},
        }
        result = assess_cost(item, TABLE)
        self.assertEqual(result.classification, "unknown")
        warnings: list[str] = []
        assess_cost(item, TABLE, warnings=warnings)
        self.assertEqual(
            sorted(
                (
                    warning.split(": ", 1)[1].split(" (", 1)[0]
                    for warning in warnings
                ),
                key=str,
            ),
            ["currency mismatch", "effective mismatch", "unit mismatch"],
        )

    def test_price_table_requires_version_unit_and_effective_label(self) -> None:
        for field in ("version", "unit", "effective"):
            table = dict(TABLE)
            table.pop("schema_version" if field == "version" else field)
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    PriceTable.from_mapping(table)

    def test_missing_usage_is_unknown_not_zero(self) -> None:
        summary = summarize_costs([{"record_id": "missing", "stage": "triage"}], TABLE)
        self.assertEqual(summary.unknown_records, 1)
        self.assertEqual(summary.known_total, Decimal(0))
        self.assertEqual(summary.estimated_total, Decimal(0))
        self.assertIn("missing usage", summary.warnings[0])

    def test_model_mismatch_stays_unknown_and_warns(self) -> None:
        item = {
            "record_id": "wrong-model",
            "stage": "triage",
            "context": {"model": "other-model", "currency": "USD"},
            "usage": {"input_tokens": 1_000_000},
        }
        summary = summarize_costs([item], TABLE)
        self.assertEqual(summary.unknown_records, 1)
        self.assertEqual(summary.estimated_total, Decimal(0))
        self.assertTrue(any("model mismatch" in warning for warning in summary.warnings))

    def test_thinking_warning_is_deterministic(self) -> None:
        summary = summarize_costs(
            [record("thinking", input_tokens=1, output_tokens=2, thinking_tokens=3)],
            TABLE,
        )
        self.assertEqual(
            [warning for warning in summary.warnings if "thinking token" in warning],
            ["thinking: thinking token semantics may overlap output_tokens"],
        )

    def test_known_and_estimated_are_separate_by_stage(self) -> None:
        summary = summarize_costs(
            [
                record(
                    "known",
                    cost={"currency": "USD", "total": 1.25, "source": "provider"},
                ),
                {
                    "record_id": "estimated",
                    "stage": "dedicated",
                    "context": {"model": "vision-1", "currency": "USD"},
                    "usage": {"input_tokens": 1_000_000},
                },
                {"record_id": "unknown", "stage": "dedicated"},
            ],
            TABLE,
        )
        self.assertEqual(summary.known_total, Decimal("1.25"))
        self.assertEqual(summary.estimated_total, Decimal("0.21"))
        self.assertEqual(summary.unknown_records, 1)
        self.assertEqual(summary.by_stage["dedicated"]["unknown_records"], 1)
        self.assertEqual(summary.by_stage["dedicated"]["estimated_records"], 1)
        self.assertEqual(summary.by_stage["triage"]["known_records"], 1)
        self.assertEqual(summary.by_stage["triage"]["known_total"], Decimal("1.25"))

    def test_summary_is_deterministic_for_record_order(self) -> None:
        records = [
            {
                "record_id": "estimated",
                "stage": "dedicated",
                "context": {"model": "vision-1", "currency": "USD"},
                "usage": {"input_tokens": 1_000_000},
            },
            record(
                "known",
                cost={"currency": "USD", "total": "0.10", "source": "provider"},
            ),
            {"record_id": "unknown", "stage": "triage"},
        ]
        forward = summarize_costs(records, TABLE)
        reverse = summarize_costs(list(reversed(records)), TABLE)
        self.assertEqual(forward.to_dict(), reverse.to_dict())

    def test_price_table_path_and_version_validation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "prices.json"
            path.write_text(json.dumps(TABLE), encoding="utf-8")
            loaded = load_price_table(path)
        self.assertIsInstance(loaded, PriceTable)
        self.assertEqual(loaded.prices["input"], Decimal("0.20"))
        with self.assertRaises(ValueError):
            PriceTable.from_mapping({**TABLE, "schema_version": "2.0"})

    def test_empty_usage_and_no_table_are_unknown(self) -> None:
        result = assess_cost(record("empty", calls=1))
        self.assertEqual(result.classification, "unknown")
        self.assertEqual(result.total, None)


if __name__ == "__main__":
    unittest.main()
