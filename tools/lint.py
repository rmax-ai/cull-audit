"""Dependency-free repository quality checks for cull-audit."""

from __future__ import annotations

import json
import os
from pathlib import Path
import py_compile
import re
import subprocess
import sys
import tomllib


ROOT = Path(__file__).resolve().parents[1]
_SKIPPED_DIRECTORY_NAMES = {
    ".git",
    "__pycache__",
    "build",
    "dist",
    "venv",
}
# PLAN.md is a protected planning artifact for this task and already contains
# four intentional Markdown hard-break spaces in the baseline commit.
_PREEXISTING_TRAILING_WHITESPACE = {"PLAN.md"}
_DEPENDENCY_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def _python_files() -> list[Path]:
    """Return source Python files, excluding generated environments."""
    files: list[Path] = []
    for directory, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [
            name
            for name in dirnames
            if name not in _SKIPPED_DIRECTORY_NAMES
            and not name.startswith(".venv")
            and not name.endswith(".egg-info")
        ]
        files.extend(
            Path(directory) / name
            for name in filenames
            if name.endswith(".py")
        )
    return sorted(files)


def _check_python_compiles(errors: list[str]) -> None:
    for path in _python_files():
        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError as exc:
            errors.append(f"{path.relative_to(ROOT)} does not compile: {exc.msg}")


def _tracked_files() -> list[Path]:
    try:
        result = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "-z"],
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError(f"unable to list tracked files: {exc}") from exc

    return [
        ROOT / raw_path.decode("utf-8")
        for raw_path in result.stdout.split(b"\0")
        if raw_path
    ]


def _check_trailing_whitespace(errors: list[str]) -> None:
    for path in _tracked_files():
        if not path.is_file():
            continue
        if path.relative_to(ROOT).as_posix() in _PREEXISTING_TRAILING_WHITESPACE:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for line_number, line in enumerate(text.splitlines(keepends=True), 1):
            if line.rstrip("\r\n") and line.rstrip("\r\n")[-1].isspace():
                relative = path.relative_to(ROOT)
                errors.append(
                    f"{relative}:{line_number}: trailing whitespace"
                )


def _check_json_files(errors: list[str]) -> None:
    for directory_name in ("schemas", "examples"):
        directory = ROOT / directory_name
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*.json")):
            try:
                with path.open("r", encoding="utf-8") as handle:
                    json.load(handle)
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                errors.append(f"{path.relative_to(ROOT)} is not valid JSON: {exc}")


def _normalise_dependency_name(name: str) -> str:
    return name.replace("_", "-").replace(".", "-").lower()


def _declared_runtime_dependencies() -> list[str]:
    path = ROOT / "pyproject.toml"
    try:
        with path.open("rb") as handle:
            project = tomllib.load(handle)["project"]
    except (OSError, KeyError, tomllib.TOMLDecodeError) as exc:
        raise RuntimeError(f"unable to read project metadata: {exc}") from exc

    dependencies = list(project.get("dependencies", []))
    optional_dependencies = project.get("optional-dependencies", {})
    for group_dependencies in optional_dependencies.values():
        dependencies.extend(group_dependencies)
    return dependencies


def _check_dependencies(errors: list[str]) -> None:
    try:
        dependencies = _declared_runtime_dependencies()
    except RuntimeError as exc:
        errors.append(str(exc))
        return

    for dependency in dependencies:
        match = _DEPENDENCY_NAME.match(dependency)
        if match is None:
            errors.append(f"unable to parse runtime dependency: {dependency!r}")
            continue
        name = _normalise_dependency_name(match.group(1))
        if name != "pillow":
            errors.append(
                f"forbidden runtime dependency {match.group(1)!r}; "
                "only Pillow is allowed"
            )


def main() -> int:
    errors: list[str] = []
    _check_python_compiles(errors)
    try:
        _check_trailing_whitespace(errors)
    except RuntimeError as exc:
        errors.append(str(exc))
    _check_json_files(errors)
    _check_dependencies(errors)

    if errors:
        for error in errors:
            print(f"lint: {error}", file=sys.stderr)
        return 1

    print("lint: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
