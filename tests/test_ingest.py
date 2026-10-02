import json
from pathlib import Path
import unittest

from cull_audit.ingest import ingest


FIXTURES = Path(__file__).parent / "fixtures" / "records"


class IngestTests(unittest.TestCase):
    def test_document_and_jsonl_normalize_to_same_records(self) -> None:
        document = ingest(FIXTURES / "valid.json")
        jsonl = ingest(FIXTURES / "valid.jsonl")
        self.assertTrue(document.ok)
        self.assertTrue(jsonl.ok)
        self.assertEqual(
            [record.to_dict() for record in document.records],
            [record.to_dict() for record in jsonl.records],
        )

    def test_malformed_and_unreadable_inputs_do_not_raise(self) -> None:
        malformed = ingest(FIXTURES / "invalid" / "malformed.json")
        missing = ingest(FIXTURES / "invalid" / "does-not-exist.json")
        self.assertFalse(malformed.ok)
        self.assertFalse(missing.ok)
        self.assertTrue(malformed.errors)
        self.assertTrue(missing.errors)

    def test_stdin_jsonl(self) -> None:
        text = (FIXTURES / "valid.jsonl").read_text()
        result = ingest("-", stream=__import__("io").StringIO(text))
        self.assertTrue(result.ok)
        self.assertEqual(len(result.records), 9)
