from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from tools.release_check import DEFAULT_PATTERNS, load_extra_patterns, scan_text


class ReleaseCheckTests(unittest.TestCase):
    def test_generic_secret_shape_is_detected(self) -> None:
        value = "sk-" + "a" * 12
        findings = scan_text("fixture.txt", value, patterns=DEFAULT_PATTERNS)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].pattern_name, "OpenAI-style key")

    def test_inline_allow_pragma_is_honored(self) -> None:
        value = "sk-" + "a" * 12 + "  # release-scan:allow"
        findings = scan_text("fixture.txt", value, patterns=DEFAULT_PATTERNS)
        self.assertEqual(findings, [])

    def test_external_extra_pattern_is_honored(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pattern_file = Path(directory) / "patterns.txt"
            pattern_file.write_text(
                "# operator-private pattern\nCUSTOM_[A-Z]{4}\n",
                encoding="utf-8",
            )
            patterns = load_extra_patterns(pattern_file)
            findings = scan_text(
                "fixture.txt",
                "CUSTOM_TEST",
                patterns=patterns,
            )
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].pattern_name, "extra pattern line 2")


if __name__ == "__main__":
    unittest.main()
