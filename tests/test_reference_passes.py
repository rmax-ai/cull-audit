from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from cull_audit.contracts import validate_document
from cull_audit.costs import load_price_table, summarize_costs
from cull_audit.reference.passes import (
    run_reference,
    select_finalists,
    select_repeat_photos,
)


def image_bytes(color: tuple[int, int, int]) -> bytes:
    output = BytesIO()
    Image.new("RGB", (80, 60), color).save(
        output,
        format="PNG",
        optimize=False,
        compress_level=9,
    )
    return output.getvalue()


class CountingTransport:
    def __init__(self) -> None:
        self.calls: list[bytes] = []

    def __call__(
        self,
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout: float,
    ) -> tuple[int, bytes]:
        del url, headers, timeout
        self.calls.append(body)
        request = json.loads(body)
        prompt = request["contents"][0]["parts"][0]["text"]
        if "contact sheet" in prompt.lower():
            response_value: object = [
                {"photo_id": "a.png", "verdict": "accept", "composite": 90},
                {"photo_id": "b.png", "verdict": "maybe", "composite": 90},
                {"photo_id": "c.png", "verdict": "maybe", "composite": 70},
            ]
        else:
            response_value = {
                "verdict": "accept",
                "composite": 80,
                "bbox": [0.25, 0.25, 0.50, 0.50],
                "reasons": ["clear synthetic evidence"],
            }
        payload = {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": json.dumps(response_value)}],
                    }
                }
            ],
            "usageMetadata": {
                "promptTokenCount": 10,
                "candidatesTokenCount": 5,
            },
        }
        return 200, json.dumps(payload).encode("utf-8")


class ReferencePassTests(unittest.TestCase):
    def setUp(self) -> None:
        self.photos = {
            "c.png": image_bytes((30, 30, 30)),
            "a.png": image_bytes((10, 10, 10)),
            "b.png": image_bytes((20, 20, 20)),
        }

    def test_finalist_and_repeat_selection_use_photo_id_tie_breaks(self) -> None:
        triage = [
            {"photo_id": "b.png", "composite": 90},
            {"photo_id": "a.png", "composite": 90},
            {"photo_id": "c.png", "composite": 50},
        ]
        dedicated = [
            {"photo_id": "c.png", "composite": 99},
            {"photo_id": "b.png", "composite": 80},
            {"photo_id": "a.png", "composite": 80},
        ]
        self.assertEqual(select_finalists(triage, 2), ("a.png", "b.png"))
        self.assertEqual(select_repeat_photos(dedicated, 2), ("c.png", "a.png"))

    def test_fake_end_to_end_emits_valid_records_and_repeat_groups(self) -> None:
        transport = CountingTransport()
        with tempfile.TemporaryDirectory() as directory:
            result = run_reference(
                self.photos,
                output=directory,
                model="fake-model",
                transport=transport,
                passes=("triage", "dedicated", "face", "repeat"),
                finalists=2,
                repeat_top=1,
                repeat_count=3,
            )
            self.assertEqual(len(transport.calls), 1 + 2 + 2 + 3)
            self.assertIsNotNone(result.document)
            document, issues = validate_document(
                json.loads((Path(directory) / "judgments.json").read_text())
            )
            self.assertIsNotNone(document)
            self.assertEqual(issues, [])
            self.assertEqual(len(result.records), 3 + 2 + 2 + 3)
            repeat = [record for record in result.records if record.stage == "repeat"]
            self.assertEqual(len({record.photo_id for record in repeat}), 1)
            self.assertEqual(
                [record.context.repeat_index for record in repeat if record.context],
                [0, 1, 2],
            )
            self.assertEqual(
                {record.context.settings_fingerprint for record in repeat if record.context},
                {repeat[0].context.settings_fingerprint},
            )
            self.assertTrue(list((Path(directory) / "prepared").rglob("*")))
            self.assertTrue(list((Path(directory) / "responses").rglob("*")))
            # Every written record carries model + billing currency metadata, so a
            # pinned price table can estimate costs without guessing
            # (audit --prices path).
            written = json.loads((Path(directory) / "judgments.json").read_text())
            for record in written["records"]:
                self.assertEqual(record["context"].get("model"), "fake-model")
                self.assertEqual(record["context"].get("currency"), "USD")
            table = load_price_table(
                {
                    "version": "1.0",
                    "model": "fake-model",
                    "currency": "USD",
                    "unit": "per_million_tokens",
                    "effective": "2026-10-01",
                    "prices": {"input": "1", "output": "2", "thinking": "2"},
                }
            )
            summary = summarize_costs(written["records"], table)
            self.assertEqual(summary.unknown_records, 0)
            self.assertEqual(summary.estimated_records, len(written["records"]))

    def test_dry_run_plans_calls_without_using_counting_transport(self) -> None:
        transport = CountingTransport()
        with tempfile.TemporaryDirectory() as directory:
            result = run_reference(
                self.photos,
                output=directory,
                model="fake-model",
                transport=transport,
                passes=("triage", "dedicated", "repeat"),
                finalists=2,
                repeat_top=1,
                repeat_count=2,
                dry_run=True,
            )
        self.assertEqual(transport.calls, [])
        self.assertTrue(result.dry_run)
        self.assertEqual(len(result.planned_calls), 1 + 2 + 2)
        self.assertIsNone(result.judgments_path)


if __name__ == "__main__":
    unittest.main()
