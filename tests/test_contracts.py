import json
from pathlib import Path
import unittest

from cull_audit.contracts import validate_document


FIXTURES = Path(__file__).parent / "fixtures" / "records"


class ContractTests(unittest.TestCase):
    def test_valid_document_normalizes_and_keeps_unknown_fields(self) -> None:
        value = json.loads((FIXTURES / "valid.json").read_text())
        document, errors = validate_document(value)
        self.assertEqual(errors, [])
        self.assertIsNotNone(document)
        assert document is not None
        self.assertEqual(document.unknown_fields["producer_metadata"]["fixture"], "contract-v1")
        self.assertEqual(document.records[0].unknown_fields["future_metadata"]["kept"], True)

    def test_repeat_group_requires_matching_fingerprint_and_photo(self) -> None:
        value = json.loads(
            (FIXTURES / "invalid" / "mixed-fingerprint.json").read_text()
        )
        document, errors = validate_document(value)
        self.assertIsNone(document)
        self.assertEqual(
            [issue.path for issue in errors],
            [
                "$.records[0].context.settings_fingerprint",
                "$.records[1].context.settings_fingerprint",
            ],
        )

    def test_invalid_fixtures_have_path_addressed_errors(self) -> None:
        for path in sorted((FIXTURES / "invalid").glob("*.json")):
            if path.name == "malformed.json":
                continue
            with self.subTest(path=path.name):
                value = json.loads(path.read_text(), parse_constant=lambda _: None)
                document, errors = validate_document(value)
                self.assertIsNone(document)
                self.assertTrue(errors)
                self.assertTrue(all(issue.path.startswith("$") for issue in errors))

    def test_duplicate_record_ids_are_rejected_deterministically(self) -> None:
        value = {
            "schema_version": "1.0",
            "records": [
                {
                    "record_id": "same",
                    "photo_id": "a.jpg",
                    "stage": "x",
                    "read_kind": "relative",
                    "verdict": "maybe",
                    "source": {"tool": "test"},
                },
                {
                    "record_id": "same",
                    "photo_id": "b.jpg",
                    "stage": "x",
                    "read_kind": "relative",
                    "verdict": "maybe",
                    "source": {"tool": "test"},
                },
            ],
        }
        _, errors = validate_document(value)
        self.assertEqual(errors[-1].path, "$.records[1].record_id")
