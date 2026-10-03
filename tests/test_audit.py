from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from PIL import Image

from cull_audit.audit import AuditContractError, AuditIOError, run_audit


ROOT = Path(__file__).parent
FIXTURE = ROOT / "fixtures" / "audit"


class AuditTests(unittest.TestCase):
    def test_fixture_matches_json_and_markdown_goldens(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            run_audit(
                FIXTURE / "judgments.json",
                baseline_stage="triage",
                decisive_stage="dedicated",
                output=output,
                prices=FIXTURE / "prices.json",
                source_date_epoch=1700000000,
            )
            self.assertEqual(
                (output / "audit.json").read_bytes(),
                (ROOT / "golden" / "audit.golden.json").read_bytes(),
            )
            report = (output / "report.md").read_text(encoding="utf-8")
            self.assertEqual(
                report.encode("utf-8"),
                (ROOT / "golden" / "report.golden.md").read_bytes(),
            )

            audit = json.loads((output / "audit.json").read_text(encoding="utf-8"))
            self.assertEqual(audit["flips"]["direction_counts"]["upward"], 1)
            self.assertEqual(audit["flips"]["direction_counts"]["downward"], 1)
            self.assertEqual(audit["flips"]["direction_counts"]["lateral"], 1)
            self.assertEqual(
                audit["coverage"]["excluded_photos"][0]["reason"],
                "duplicate_decisive",
            )
            self.assertEqual(audit["stability"]["class_counts"], {
                "robust": 1,
                "soft": 1,
                "unstable": 1,
            })
            self.assertEqual(audit["cost"]["unknown_records"], 15)
            self.assertIn(
                f"Verdict flips: {audit['flips']['count']} / "
                f"{audit['flips']['paired']}",
                report,
            )
            self.assertIn(
                f"- Robust: {audit['stability']['class_counts']['robust']}",
                report,
            )
            self.assertIn(f"- Known total: {audit['cost']['known_total']}", report)
            self.assertIn(
                f"- Estimated total: {audit['cost']['estimated_total']}",
                report,
            )
            self.assertIn(
                f"- Unknown records: {audit['cost']['unknown_records']}",
                report,
            )

    def test_invalid_input_and_strict_warning_leave_no_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "out"
            with self.assertRaises(AuditIOError):
                run_audit(
                    FIXTURE / "missing.json",
                    baseline_stage="triage",
                    decisive_stage="dedicated",
                    output=output,
                )
            self.assertFalse(output.exists())

            with self.assertRaises(AuditContractError):
                run_audit(
                    FIXTURE / "judgments.json",
                    baseline_stage="triage",
                    decisive_stage="dedicated",
                    output=output,
                    prices=FIXTURE / "prices.json",
                    source_date_epoch=0,
                    strict=True,
                )
            self.assertFalse(output.exists())

    def test_cli_contract_and_strict_failures_leave_no_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "out"
            invalid = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cull_audit",
                    "audit",
                    "--judgments",
                    str(ROOT / "fixtures" / "records" / "invalid" / "malformed.json"),
                    "--baseline-stage",
                    "triage",
                    "--decisive-stage",
                    "dedicated",
                    "--output",
                    str(output),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(invalid.returncode, 3)
            self.assertFalse(output.exists())

            strict = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cull_audit",
                    "audit",
                    "--judgments",
                    str(FIXTURE / "judgments.json"),
                    "--baseline-stage",
                    "triage",
                    "--decisive-stage",
                    "dedicated",
                    "--prices",
                    str(FIXTURE / "prices.json"),
                    "--output",
                    str(output),
                    "--source-date-epoch",
                    "1700000000",
                    "--strict",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(strict.returncode, 3)
            self.assertFalse(output.exists())

    def test_source_date_epoch_is_stable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first"
            second = Path(directory) / "second"
            arguments = {
                "baseline_stage": "triage",
                "decisive_stage": "dedicated",
                "prices": FIXTURE / "prices.json",
                "source_date_epoch": 123,
            }
            run_audit(FIXTURE / "judgments.json", output=first, **arguments)
            run_audit(FIXTURE / "judgments.json", output=second, **arguments)
            self.assertEqual(
                (first / "audit.json").read_bytes(),
                (second / "audit.json").read_bytes(),
            )
            self.assertEqual(
                (first / "report.md").read_bytes(),
                (second / "report.md").read_bytes(),
            )

    def test_photos_option_discovers_and_joins_photo_entries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            photos = root / "photos"
            output = root / "output"
            photos.mkdir()
            with Image.new("RGB", (2, 2), (32, 64, 96)) as image:
                image.save(photos / "a.jpg", format="JPEG")

            run_audit(
                FIXTURE / "judgments.json",
                baseline_stage="triage",
                decisive_stage="dedicated",
                output=output,
                photos=photos,
                prices=FIXTURE / "prices.json",
                source_date_epoch=1700000000,
            )
            audit = json.loads((output / "audit.json").read_text(encoding="utf-8"))
            self.assertEqual(audit["coverage"]["photos_discovered"], 1)
            photo = next(item for item in audit["photos"] if item["photo_id"] == "a.jpg")
            self.assertTrue(photo["discovered"])
            self.assertIn("judgment photo is not discoverable", "\n".join(audit["warnings"]))


if __name__ == "__main__":
    unittest.main()
