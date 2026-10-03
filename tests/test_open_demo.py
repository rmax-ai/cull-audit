from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = ROOT / "tools" / "open_demo_fetch.py"
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "open-demo"


def load_tool():
    spec = importlib.util.spec_from_file_location("open_demo_fetch", TOOL_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load open_demo_fetch.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


TOOL = load_tool()


def fixture_manifest() -> dict[str, object]:
    return json.loads(
        (FIXTURE_DIR / "valid-manifest.json").read_text(encoding="utf-8")
    )


class OpenDemoReportTests(unittest.TestCase):
    def run_report(self, manifest: dict[str, object]) -> tuple[int, str]:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stderr(io.StringIO()):
                code = TOOL.report_manifest(path, stream=output)
            return code, output.getvalue()

    def test_valid_fixture_passes_report(self) -> None:
        code, output = self.run_report(fixture_manifest())
        self.assertEqual(code, 0)
        self.assertIn("assets=1 missing=0 duplicates=0", output)

    def test_missing_field_fails_report(self) -> None:
        manifest = fixture_manifest()
        del manifest["assets"][0]["license"]
        code, output = self.run_report(manifest)
        self.assertNotEqual(code, 0)
        self.assertIn("missing=1", output)

    def test_duplicate_file_and_page_fail_report(self) -> None:
        manifest = fixture_manifest()
        manifest["assets"].append(dict(manifest["assets"][0]))
        code, output = self.run_report(manifest)
        self.assertNotEqual(code, 0)
        self.assertIn("duplicates=2", output)

    def test_disallowed_license_fails_report(self) -> None:
        manifest = fixture_manifest()
        manifest["assets"][0]["license"] = "CC BY-NC 4.0"
        code, output = self.run_report(manifest)
        self.assertNotEqual(code, 0)
        self.assertIn("disallowed=1", output)

    def test_unsorted_assets_fail_report(self) -> None:
        manifest = fixture_manifest()
        first = dict(manifest["assets"][0])
        second = dict(first)
        second["file"] = "0002.jpg"
        second["commons_page"] = "https://commons.wikimedia.org/wiki/File:Fixture-2.jpg"
        manifest["assets"] = [second, first]
        code, output = self.run_report(manifest)
        self.assertNotEqual(code, 0)
        self.assertIn("unsorted=1", output)

    def test_real_manifest_passes_report_without_network(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stderr(io.StringIO()):
            code = TOOL.report_manifest(
                ROOT / "examples" / "open-demo" / "manifest.json",
                stream=output,
            )
        self.assertEqual(code, 0)
        self.assertIn("missing=0", output.getvalue())


class OpenDemoVerifyTests(unittest.TestCase):
    def test_fixture_bytes_pass_verification(self) -> None:
        manifest = fixture_manifest()
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            fixture = FIXTURE_DIR / "0001.jpg"
            (output_dir / "0001.jpg").write_bytes(fixture.read_bytes())
            result = TOOL.verify_assets(manifest, output_dir)
        self.assertEqual(result.verified, 1)
        self.assertEqual(result.missing, 0)
        self.assertEqual(result.mismatched, 0)

    def test_checksum_mismatch_fails_verification(self) -> None:
        manifest = fixture_manifest()
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            (output_dir / "0001.jpg").write_bytes(b"changed fixture bytes")
            result = TOOL.verify_assets(manifest, output_dir)
        self.assertEqual(result.verified, 0)
        self.assertEqual(result.mismatched, 1)

    def test_fetch_verifies_download_before_installing(self) -> None:
        content = b"offline fetch bytes"
        digest = hashlib.sha256(content).hexdigest()
        manifest = fixture_manifest()
        asset = manifest["assets"][0]
        asset["bytes"] = len(content)
        asset["sha256"] = digest

        class Response:
            def __init__(self):
                self.sent = False

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self, size: int = -1) -> bytes:
                if self.sent:
                    return b""
                self.sent = True
                return content

        def opener(request):
            self.assertEqual(request.headers["User-agent"], TOOL.USER_AGENT)
            return Response()

        with tempfile.TemporaryDirectory() as directory:
            result = TOOL.fetch_assets(
                manifest,
                Path(directory),
                opener=opener,
                sleep_fn=lambda _: None,
            )
            self.assertEqual(result.fetched, 1)
            self.assertEqual((Path(directory) / "0001.jpg").read_bytes(), content)


if __name__ == "__main__":
    unittest.main()
