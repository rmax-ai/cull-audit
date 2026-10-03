from __future__ import annotations

from pathlib import Path
import re
import unittest
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
MARKDOWN_LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)\s]+)(?:\s+[^)]*)?\)")


class ReadmeTests(unittest.TestCase):
    def test_relative_markdown_links_resolve(self) -> None:
        readme = README.read_text(encoding="utf-8")
        for raw_target in MARKDOWN_LINK.findall(readme):
            target = raw_target.strip("<>")
            parsed = urlsplit(target)
            if parsed.scheme in {"http", "https"} or target.startswith("#"):
                continue
            relative_target = parsed.path
            self.assertTrue(relative_target, f"empty README link: {target}")
            resolved = (README.parent / relative_target).resolve()
            self.assertTrue(
                resolved.exists(),
                f"README link does not resolve: {target}",
            )


if __name__ == "__main__":
    unittest.main()
