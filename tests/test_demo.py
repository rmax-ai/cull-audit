from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from cull_audit.demo import run_demo


class DemoTests(unittest.TestCase):
    def test_demo_writes_expected_classes_and_cost_categories(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            audit_path, report_path = run_demo(Path(directory) / "demo")
            self.assertTrue(audit_path.is_file())
            self.assertTrue(report_path.is_file())
            self.assertGreater(audit_path.stat().st_size, 0)
            self.assertGreater(report_path.stat().st_size, 0)

            audit = json.loads(audit_path.read_text(encoding="utf-8"))
            self.assertGreaterEqual(audit["flips"]["direction_counts"]["upward"], 1)
            self.assertGreaterEqual(audit["flips"]["direction_counts"]["downward"], 1)
            self.assertGreaterEqual(audit["flips"]["direction_counts"]["lateral"], 1)
            for stability_class in ("robust", "soft", "unstable"):
                self.assertGreaterEqual(
                    audit["stability"]["class_counts"][stability_class], 1
                )
            self.assertGreater(audit["cost"]["known_total"], 0)
            self.assertGreater(audit["cost"]["estimated_total"], 0)
            self.assertGreaterEqual(audit["cost"]["unknown_records"], 1)
            self.assertTrue(audit["coverage"]["excluded_photos"])
            self.assertTrue(audit["warnings"])
            self.assertTrue(
                report_path.read_text(encoding="utf-8").startswith("# Cull audit report")
            )

    def test_demo_is_byte_identical_across_runs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first_audit, first_report = run_demo(root / "first")
            second_audit, second_report = run_demo(root / "second")
            self.assertEqual(first_audit.read_bytes(), second_audit.read_bytes())
            self.assertEqual(first_report.read_bytes(), second_report.read_bytes())

    def test_module_demo_matches_console_demo(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            console_output = root / "console"
            console_script = Path(sys.executable).with_name("cull-audit")
            console_result = subprocess.run(
                [
                    str(console_script),
                    "demo",
                    "--output",
                    str(console_output),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(console_result.returncode, 0, console_result.stderr)
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cull_audit",
                    "demo",
                    "--output",
                    str(root / "module"),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                (console_output / "audit.json").read_bytes(),
                (root / "module" / "audit.json").read_bytes(),
            )
            self.assertEqual(
                (console_output / "report.md").read_bytes(),
                (root / "module" / "report.md").read_bytes(),
            )


if __name__ == "__main__":
    unittest.main()
