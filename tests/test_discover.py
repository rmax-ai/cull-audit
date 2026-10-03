import base64
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from cull_audit.discover import discover


FIXTURE_MANIFEST = (
    Path(__file__).parent / "fixtures" / "discovery" / "manifest.json"
)

# These are fixed, tiny images rather than committed binary fixtures.  The
# directory tree is built from these bytes in each test run.
PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGMQVDIGAACuAGcVHqFfAAAAAElFTkSuQmCC"
)
JPEG_BYTES = base64.b64decode(
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAABAAEDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/9oADAMBAAIRAxEAPwDx6iiiuo5j/9k="
)
CORRUPT_PNG_BYTES = b"not a png"


def _write_fixture_tree(root: Path) -> None:
    files = {
        "alpha/duplicate-a.png": PNG_BYTES,
        "alpha/nested/duplicate-b.PNG": PNG_BYTES,
        "corrupt/CORRUPT.PnG": CORRUPT_PNG_BYTES,
        "hidden/only.JpG": JPEG_BYTES,
        "ignored/notes.txt": b"not an image",
    }
    for relative_path, contents in files.items():
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents)

    hidden = root / "hidden"
    (root / "alias-to-hidden").symlink_to(hidden, target_is_directory=True)


class DiscoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        _write_fixture_tree(self.root)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_fixture_matches_checked_in_manifest(self) -> None:
        manifest = json.loads(FIXTURE_MANIFEST.read_text(encoding="utf-8"))
        result = discover(self.root)
        duplicate_paths = {
            path
            for group in manifest["duplicate_groups"]
            for path in group
        }
        expected_entries = [
            {
                "path": item["path"],
                "sha256": item["sha256"],
                "size": item["size"],
            }
            for item in manifest["entries"]
        ]
        actual_entries = [
            {
                "path": entry.path,
                "sha256": entry.sha256,
                "size": entry.size,
            }
            for entry in result.entries
        ]

        self.assertEqual(actual_entries, expected_entries)
        self.assertEqual(
            list(result.unreadable),
            [item["path"] for item in manifest["unreadable"]],
        )
        self.assertEqual(
            [list(group) for group in result.duplicate_groups],
            manifest["duplicate_groups"],
        )
        self.assertEqual(
            [entry.path in duplicate_paths for entry in result.entries],
            [item["duplicate"] for item in manifest["entries"]],
        )

    def test_symlinked_directories_are_not_traversed(self) -> None:
        result = discover(self.root)

        discovered_paths = {entry.path for entry in result.entries}
        self.assertIn("hidden/only.JpG", discovered_paths)
        self.assertNotIn("alias-to-hidden/only.JpG", discovered_paths)

    def test_identical_bytes_are_reported_as_duplicate_group(self) -> None:
        result = discover(self.root)

        self.assertEqual(
            result.duplicate_groups,
            (
                (
                    "alpha/duplicate-a.png",
                    "alpha/nested/duplicate-b.PNG",
                ),
            ),
        )

    def test_corrupt_supported_file_is_unreadable_not_an_exception(self) -> None:
        result = discover(self.root)

        self.assertEqual(result.unreadable, ("corrupt/CORRUPT.PnG",))
        self.assertNotIn(
            "corrupt/CORRUPT.PnG",
            {entry.path for entry in result.entries},
        )

    def test_supported_extensions_are_case_insensitive(self) -> None:
        result = discover(self.root)

        self.assertEqual(
            {entry.path for entry in result.entries},
            {
                "alpha/duplicate-a.png",
                "alpha/nested/duplicate-b.PNG",
                "hidden/only.JpG",
            },
        )

    def test_discovery_does_not_change_fixture_bytes_or_mtimes(self) -> None:
        input_paths = sorted(
            path
            for path in self.root.rglob("*")
            if path.is_file() and not path.is_symlink()
        )
        before_hashes = {
            path.relative_to(self.root).as_posix(): hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
            for path in input_paths
        }
        before_mtimes = {
            path.relative_to(self.root).as_posix(): path.stat().st_mtime_ns
            for path in input_paths
        }

        discover(self.root)

        after_hashes = {
            path.relative_to(self.root).as_posix(): hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
            for path in input_paths
        }
        after_mtimes = {
            path.relative_to(self.root).as_posix(): path.stat().st_mtime_ns
            for path in input_paths
        }
        self.assertEqual(after_hashes, before_hashes)
        self.assertEqual(after_mtimes, before_mtimes)


if __name__ == "__main__":
    unittest.main()
