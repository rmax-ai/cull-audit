import subprocess
import sys
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

    def test_stub_commands_report_not_implemented(self) -> None:
        for command in ("validate", "audit", "demo"):
            with self.subTest(command=command):
                result = self.run_console(command)
                self.assertEqual(result.returncode, 3)
                self.assertIn("not implemented yet", result.stderr)
                self.assertEqual(result.stdout, "")
