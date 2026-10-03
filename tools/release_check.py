"""Run deterministic, stdlib-only checks before a public release."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
import subprocess
import sys
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
HISTORY_LIMIT = 200
ALLOW_PRAGMA = "release-scan:allow"


@dataclass(frozen=True)
class PatternSpec:
    name: str
    regex: re.Pattern[str]


@dataclass(frozen=True)
class Finding:
    location: str
    line_number: int
    pattern_name: str

    def message(self) -> str:
        return f"{self.location}:{self.line_number}: possible {self.pattern_name}"


def _pattern(name: str, expression: str, *, flags: int = 0) -> PatternSpec:
    return PatternSpec(name, re.compile(expression, flags))


DEFAULT_PATTERNS = (
    _pattern("private-key header", r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----"),
    _pattern("OpenAI-style key", r"\bsk-[A-Za-z0-9_-]{8,}\b"),
    _pattern("Google API key", r"\bAIza[A-Za-z0-9_-]{20,}\b"),
    _pattern("GitHub token", r"\b(?:ghp_|gho_)[A-Za-z0-9_]{20,}\b"),
    _pattern("Slack token", r"\bxox[baprs]-[A-Za-z0-9-]{8,}\b"),
    _pattern("AWS access key", r"\bAKIA[0-9A-Z]{16}\b"),
    _pattern(
        "bearer token",
        r"\bBearer\s+[A-Za-z0-9._~+/=-]{20,}\b",
        flags=re.IGNORECASE,
    ),
)

REQUIRED_FILES = (
    "CONTRIBUTING.md",
    "SECURITY.md",
    ".github/ISSUE_TEMPLATE/bug_report.yml",
    ".github/ISSUE_TEMPLATE/feature_request.yml",
    ".github/ISSUE_TEMPLATE/config.yml",
    ".github/PULL_REQUEST_TEMPLATE.md",
    "examples/producer-adapter-template/README.md",
    "examples/producer-adapter-template/producer_adapter.py",
    "CHANGELOG.md",
    "CITATION.cff",
    "docs/release-checklist.md",
    "docs/release-notes-v0.1.0.md",
    "tools/release_check.py",
    "tests/test_release_check.py",
    "src/cull_audit/__init__.py",
    ".github/workflows/ci.yml",
    "README.md",
    "pyproject.toml",
)


def load_extra_patterns(path: Path, *, root: Path = ROOT) -> tuple[PatternSpec, ...]:
    """Load one regex per non-comment line from a file outside the repository."""
    resolved = path.expanduser().resolve()
    repository = root.resolve()
    if resolved == repository or repository in resolved.parents:
        raise ValueError("--extra-patterns must point outside the repository")
    try:
        lines = resolved.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"unable to read extra patterns file: {exc}") from exc
    patterns: list[PatternSpec] = []
    for number, line in enumerate(lines, 1):
        expression = line.strip()
        if not expression or expression.startswith("#"):
            continue
        try:
            patterns.append(_pattern(f"extra pattern line {number}", expression))
        except re.error as exc:
            raise ValueError(f"invalid extra pattern on line {number}: {exc}") from exc
    return tuple(patterns)


def scan_text(location: str, text: str, *, patterns: Iterable[PatternSpec] = DEFAULT_PATTERNS) -> list[Finding]:
    """Find pattern hits, except on lines with the explicit allow pragma."""
    findings: list[Finding] = []
    for number, line in enumerate(text.splitlines(), 1):
        if ALLOW_PRAGMA in line:
            continue
        for spec in patterns:
            if spec.regex.search(line):
                findings.append(Finding(location, number, spec.name))
    return findings


def _git_file_set() -> list[Path]:
    command = ["git", "-C", str(ROOT), "ls-files", "--cached", "--others",
               "--exclude-standard", "-z"]
    try:
        result = subprocess.run(command, check=True, capture_output=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError(f"unable to list release files: {exc}") from exc
    files = [
        ROOT / raw.decode("utf-8")
        for raw in result.stdout.split(b"\0")
        if raw
    ]
    return sorted(files, key=lambda item: item.relative_to(ROOT).as_posix())


def _scan_tree(patterns: Iterable[PatternSpec]) -> tuple[list[Finding], int]:
    findings: list[Finding] = []
    files = _git_file_set()
    for path in files:
        location = path.relative_to(ROOT).as_posix()
        if not path.is_file():
            findings.append(Finding(location, 0, "missing file"))
            continue
        try:
            text = path.read_bytes().decode("utf-8", errors="replace")
        except OSError as exc:
            findings.append(Finding(location, 0, f"unreadable file ({type(exc).__name__})"))
            continue
        findings.extend(scan_text(location, text, patterns=patterns))
    return findings, len(files)


def _required_checks() -> list[Finding]:
    findings: list[Finding] = []
    for relative in REQUIRED_FILES:
        if not (ROOT / relative).is_file():
            findings.append(Finding(relative, 0, "required release file"))

    version = ROOT / "src/cull_audit/__init__.py"
    if version.is_file() and not re.search(
        r"""(?m)^\s*__version__\s*=\s*["']0\.1\.0["']\s*$""",
        version.read_text(encoding="utf-8"),
    ):
        findings.append(Finding(str(version.relative_to(ROOT)), 1, '__version__ must be "0.1.0"'))

    changelog = ROOT / "CHANGELOG.md"
    if changelog.is_file() and not re.search(
        r"\b0\.1\.0\b", changelog.read_text(encoding="utf-8")
    ):
        findings.append(Finding("CHANGELOG.md", 1, "CHANGELOG mentions 0.1.0"))

    for relative in (
        ".github/ISSUE_TEMPLATE/bug_report.yml",
        ".github/ISSUE_TEMPLATE/feature_request.yml",
    ):
        path = ROOT / relative
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for key in ("name", "description", "body"):
            if not re.search(rf"(?m)^\s*{key}\s*:", text):
                findings.append(Finding(relative, 1, f"issue form lacks {key}:"))

    citation = ROOT / "CITATION.cff"
    if citation.is_file():
        text = citation.read_text(encoding="utf-8")
        for key in ("cff-version", "title", "authors", "version", "license"):
            if not re.search(rf"(?m)^\s*{re.escape(key)}\s*:", text):
                findings.append(Finding("CITATION.cff", 1, f"CITATION lacks {key}:"))
    return findings


def _history_findings(patterns: Iterable[PatternSpec]) -> list[Finding]:
    command = ["git", "-C", str(ROOT), "log", "-p", "--all",
               f"--max-count={HISTORY_LIMIT}", "--format=%x1e%H", "--no-ext-diff"]
    try:
        result = subprocess.run(
            command, check=True, capture_output=True, text=True
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError(f"unable to read repository history: {exc}") from exc

    findings: list[Finding] = []
    for chunk in result.stdout.split("\x1e"):
        lines = chunk.splitlines()
        if not lines or not lines[0].strip():
            continue
        location = f"commit {lines[0].strip()[:12]}"
        findings.extend(scan_text(location, "\n".join(lines[1:]), patterns=patterns))
    return findings


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scan the release tree and optionally bounded Git history."
    )
    parser.add_argument(
        "--extra-patterns",
        type=Path,
        help="external file containing one additional regex per line",
    )
    parser.add_argument(
        "--history",
        action="store_true",
        help=f"scan up to {HISTORY_LIMIT} commits from all refs",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        extra = (
            load_extra_patterns(args.extra_patterns)
            if args.extra_patterns is not None
            else ()
        )
        patterns = DEFAULT_PATTERNS + extra
        findings, file_count = _scan_tree(patterns)
        findings.extend(_required_checks())
        if args.history:
            findings.extend(_history_findings(patterns))
    except (RuntimeError, ValueError, OSError, UnicodeError) as exc:
        print(f"release-check: {exc}", file=sys.stderr)
        return 1

    findings.sort(key=lambda item: (item.location, item.line_number, item.pattern_name))
    if findings:
        print(
            f"release-check: {len(findings)} finding(s) across {file_count} tree files",
            file=sys.stderr,
        )
        for finding in findings:
            print(f"- {finding.message()}", file=sys.stderr)
        return 1

    suffix = " and history" if args.history else ""
    print(f"release-check: passed ({file_count} tree files{suffix})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
