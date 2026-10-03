import subprocess
import sys
import json
import unittest
from pathlib import Path

from cull_audit import __version__


class CliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.console_script = Path(sys.executable).with_name("cull-audit")

    def run_console(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(self.console_script), *arguments],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_console_version_matches_package(self) -> None:
        result = self.run_console("--version")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), __version__)
        self.assertEqual(result.stderr, "")

    def test_module_version_matches_console(self) -> None:
        console_result = self.run_console("--version")
        module_result = subprocess.run(
            [sys.executable, "-m", "cull_audit", "--version"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(module_result.returncode, 0)
        self.assertEqual(module_result.stdout, console_result.stdout)
        self.assertEqual(module_result.stderr, "")

    def test_demo_stub_reports_not_implemented(self) -> None:
        result = self.run_console("demo")
        self.assertEqual(result.returncode, 3)
        self.assertIn("not implemented yet", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_audit_requires_its_required_options(self) -> None:
        result = self.run_console("audit")
        self.assertEqual(result.returncode, 2)
        self.assertIn("the following arguments are required", result.stderr)

    def test_validate_accepts_document_and_json_output(self) -> None:
        fixture = Path(__file__).parent / "fixtures" / "records" / "valid.json"
        result = self.run_console(
            "validate", "--judgments", str(fixture), "--format", "json"
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)["records"], 9)
        self.assertEqual(json.loads(result.stdout)["errors"], [])

    def test_validate_contract_failure_uses_exit_three(self) -> None:
        fixture = (
            Path(__file__).parent
            / "fixtures"
            / "records"
            / "invalid"
            / "duplicate-ids.json"
        )
        result = self.run_console("validate", "--judgments", str(fixture))
        self.assertEqual(result.returncode, 3)
        self.assertIn("$.records[1].record_id", result.stderr)

    def test_validate_json_diagnostics_go_to_stdout(self) -> None:
        fixture = (
            Path(__file__).parent
            / "fixtures"
            / "records"
            / "invalid"
            / "out-of-range-score.json"
        )
        result = self.run_console(
            "validate", "--judgments", str(fixture), "--format", "json"
        )
        payload = json.loads(result.stdout)
        self.assertEqual(result.returncode, 3)
        self.assertFalse(payload["valid"])
        self.assertEqual(payload["errors"][0]["path"], "$.records[0].composite")
        self.assertEqual(result.stderr, "")
