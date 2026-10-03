from __future__ import annotations

import base64
from contextlib import redirect_stderr, redirect_stdout
from http.server import BaseHTTPRequestHandler, HTTPServer
import io
import json
import os
from pathlib import Path
import threading
import tempfile
import unittest
from unittest.mock import patch

from cull_audit.reference.gemini import (
    API_KEY_ENV,
    GeminiClient,
    GeminiHTTPError,
    GeminiResponseError,
    GeminiRetryError,
    GeminiTransportError,
    GeminiUsage,
    build_request_body,
    parse_response,
    parse_usage,
    plan_dry_run,
)


SENTINEL = "t08-sentinel-key-never-write-this"
MODEL = "gemini-test-model"


def response_payload(**usage: int) -> bytes:
    payload: dict[str, object] = {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": "accepted"}],
                    "role": "model",
                },
                "finishReason": "STOP",
            }
        ],
    }
    if usage:
        payload["usageMetadata"] = usage
    return json.dumps(payload).encode("utf-8")


class FakeTransport:
    def __init__(self, results: list[object]) -> None:
        self.results = list(results)
        self.calls: list[tuple[str, dict[str, str], bytes, float]] = []

    def __call__(
        self,
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout: float,
    ) -> tuple[int, bytes]:
        self.calls.append((url, dict(headers), body, timeout))
        result = self.results.pop(0) if self.results else (200, response_payload())
        if isinstance(result, BaseException):
            raise result
        return result  # type: ignore[return-value]


class GeminiRequestTests(unittest.TestCase):
    def test_request_shape_headers_and_timeout(self) -> None:
        fake = FakeTransport([(200, response_payload(promptTokenCount=11))])
        with patch.dict(os.environ, {API_KEY_ENV: SENTINEL}, clear=False):
            result = GeminiClient(
                MODEL,
                transport=fake,
                timeout=12.5,
                sleeper=lambda _: None,
            ).generate_content(
                "describe this",
                image_bytes=b"\x00\x01image",
                generation_config={"temperature": 0.2, "maxOutputTokens": 17},
                mime_type="image/png",
            )

        self.assertEqual(result.text, "accepted")
        self.assertEqual(len(fake.calls), 1)
        url, headers, body, timeout = fake.calls[0]
        self.assertIn("models/gemini-test-model:generateContent", url)
        self.assertNotIn(SENTINEL, url)
        self.assertEqual(headers, {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "x-goog-api-key": SENTINEL,
        })
        self.assertEqual(timeout, 12.5)
        payload = json.loads(body)
        self.assertEqual(payload["generationConfig"], {
            "temperature": 0.2,
            "maxOutputTokens": 17,
        })
        content = payload["contents"][0]
        self.assertEqual(content["role"], "user")
        self.assertEqual(content["parts"][0], {"text": "describe this"})
        self.assertEqual(
            content["parts"][1]["inlineData"],
            {
                "mimeType": "image/png",
                "data": base64.b64encode(b"\x00\x01image").decode("ascii"),
            },
        )

    def test_text_only_request_still_has_generation_config(self) -> None:
        payload = json.loads(build_request_body("hello"))
        self.assertEqual(payload["contents"][0]["parts"], [{"text": "hello"}])
        self.assertEqual(payload["generationConfig"], {})

    def test_retry_cap_and_backoff_are_injected(self) -> None:
        fake = FakeTransport([(429, b"busy"), (503, b"down"), (500, b"still down")])
        sleeps: list[float] = []
        with patch.dict(os.environ, {API_KEY_ENV: SENTINEL}, clear=False):
            with self.assertRaises(GeminiRetryError) as raised:
                GeminiClient(
                    MODEL,
                    transport=fake,
                    sleeper=sleeps.append,
                    backoff=0.25,
                ).generate_content("retry")
        self.assertEqual(len(fake.calls), 3)
        self.assertEqual(sleeps, [0.25, 0.5])
        self.assertEqual(raised.exception.attempts, 3)
        self.assertEqual(
            [attempt.raw_body for attempt in raised.exception.attempt_records],
            [b"busy", b"down", b"still down"],
        )

    def test_non_retryable_400_is_one_attempt(self) -> None:
        fake = FakeTransport([(400, b'{"error":{"message":"bad request"}}')])
        with patch.dict(os.environ, {API_KEY_ENV: SENTINEL}, clear=False):
            with self.assertRaises(GeminiHTTPError) as raised:
                GeminiClient(
                    MODEL,
                    transport=fake,
                    sleeper=lambda _: self.fail("400 must not sleep"),
                ).generate_content("bad")
        self.assertEqual(len(fake.calls), 1)
        self.assertEqual(raised.exception.status_code, 400)
        self.assertNotIn(SENTINEL, str(raised.exception))

    def test_network_errors_retry_and_are_retained(self) -> None:
        from urllib.error import URLError

        fake = FakeTransport([URLError("connection refused"), (200, response_payload())])
        sleeps: list[float] = []
        with patch.dict(os.environ, {API_KEY_ENV: SENTINEL}, clear=False):
            result = GeminiClient(
                MODEL,
                transport=fake,
                sleeper=sleeps.append,
                backoff=0,
            ).generate_content("network")
        self.assertEqual(len(fake.calls), 2)
        self.assertEqual(result.attempts, 2)
        self.assertEqual(result.attempt_records[0].status_code, None)
        self.assertEqual(result.attempt_records[0].raw_body, b"")
        self.assertEqual(sleeps, [0])


class GeminiUsageTests(unittest.TestCase):
    def test_usage_maps_all_provider_fields_and_attempts(self) -> None:
        usage = parse_usage(
            {
                "usageMetadata": {
                    "promptTokenCount": 101,
                    "candidatesTokenCount": 23,
                    "thoughtsTokenCount": 7,
                }
            },
            attempts=3,
        )
        self.assertEqual(
            usage,
            GeminiUsage(
                input_tokens=101,
                output_tokens=23,
                thinking_tokens=7,
                calls=3,
            ),
        )

    def test_missing_usage_fields_remain_none(self) -> None:
        usage = parse_usage({"candidates": []}, attempts=2)
        self.assertIsNone(usage.input_tokens)
        self.assertIsNone(usage.output_tokens)
        self.assertIsNone(usage.thinking_tokens)
        self.assertEqual(usage.calls, 2)

    def test_response_parser_and_client_usage(self) -> None:
        parsed = parse_response(response_payload(promptTokenCount=9), attempts=4)
        self.assertEqual(parsed.usage.input_tokens, 9)
        self.assertIsNone(parsed.usage.output_tokens)
        self.assertEqual(parsed.usage.calls, 4)

        fake = FakeTransport([(200, response_payload(
            promptTokenCount=1,
            candidatesTokenCount=2,
            thoughtsTokenCount=3,
        ))])
        with patch.dict(os.environ, {API_KEY_ENV: SENTINEL}, clear=False):
            result = GeminiClient(MODEL, transport=fake).generate_content("usage")
        self.assertEqual(result.usage.to_dict(), {
            "input_tokens": 1,
            "output_tokens": 2,
            "thinking_tokens": 3,
            "calls": 1,
        })

    def test_invalid_success_body_is_a_response_error(self) -> None:
        fake = FakeTransport([(200, b"not json")])
        with patch.dict(os.environ, {API_KEY_ENV: SENTINEL}, clear=False):
            with self.assertRaises(GeminiResponseError):
                GeminiClient(MODEL, transport=fake).generate_content("parse")


class GeminiRetentionTests(unittest.TestCase):
    def test_attempt_bodies_have_deterministic_retention_names(self) -> None:
        fake = FakeTransport([(429, b"first"), (200, response_payload())])
        sleeps: list[float] = []
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {API_KEY_ENV: SENTINEL}, clear=False):
                result = GeminiClient(
                    MODEL,
                    transport=fake,
                    retention_dir=directory,
                    sleeper=sleeps.append,
                    backoff=0,
                ).generate_content("retain")
            paths = sorted(Path(directory).iterdir())
            self.assertEqual(
                [path.name for path in paths],
                [
                    "call-000001-attempt-000001.bin",
                    "call-000001-attempt-000002.bin",
                ],
            )
            self.assertEqual((Path(directory) / paths[0].name).read_bytes(), b"first")
            self.assertEqual((Path(directory) / paths[1].name).read_bytes(), result.raw_body)
            self.assertEqual(
                [attempt.retention_path for attempt in result.attempt_records],
                paths,
            )

    def test_retention_redacts_a_key_echoed_by_provider(self) -> None:
        fake = FakeTransport([(400, SENTINEL.encode("utf-8"))])
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {API_KEY_ENV: SENTINEL}, clear=False):
                with self.assertRaises(GeminiHTTPError):
                    GeminiClient(
                        MODEL,
                        transport=fake,
                        retention_dir=directory,
                    ).generate_content("echo")
            written = b"".join(path.read_bytes() for path in Path(directory).iterdir())
        self.assertNotIn(SENTINEL.encode("utf-8"), written)


class GeminiDryRunTests(unittest.TestCase):
    def test_dry_run_counts_sizes_and_does_not_transport(self) -> None:
        calls = 0

        def transport(*_: object) -> tuple[int, bytes]:
            nonlocal calls
            calls += 1
            return 200, response_payload()

        planned = [
            {"prompt": "one"},
            {
                "prompt": "two",
                "image_bytes": b"image",
                "mime_type": "image/png",
                "generation_config": {"temperature": 0},
            },
        ]
        estimate = plan_dry_run(MODEL, planned)
        self.assertEqual(estimate.call_count, 2)
        self.assertEqual(len(estimate.request_sizes), 2)
        self.assertEqual(
            estimate.total_request_bytes,
            sum(estimate.request_sizes),
        )
        with patch.dict(os.environ, {}, clear=False):
            client = GeminiClient(MODEL, transport=transport)
            self.assertEqual(client.plan_dry_run(planned), estimate)
        self.assertEqual(calls, 0)


class GeminiSecretTests(unittest.TestCase):
    def test_sentinel_is_absent_from_output_errors_and_artifacts(self) -> None:
        def leaking_transport(
            url: str,
            headers: dict[str, str],
            body: bytes,
            timeout: float,
        ) -> tuple[int, bytes]:
            del headers, body, timeout
            raise OSError(f"connection failed for {url} and {SENTINEL}")

        stdout = io.StringIO()
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {API_KEY_ENV: SENTINEL}, clear=False):
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    with self.assertRaises(GeminiTransportError) as raised:
                        GeminiClient(
                            MODEL,
                            transport=leaking_transport,
                            retention_dir=directory,
                            sleeper=lambda _: None,
                        ).generate_content("secret scan")
            artifact_bytes = b"".join(
                path.read_bytes() for path in Path(directory).iterdir()
            )
        captured = "\n".join((stdout.getvalue(), stderr.getvalue(), str(raised.exception)))
        self.assertNotIn(SENTINEL, captured)
        self.assertNotIn(SENTINEL.encode("utf-8"), artifact_bytes)

    def test_key_is_required_only_when_sending(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            estimate = plan_dry_run(MODEL, ["no network"])
            self.assertEqual(estimate.call_count, 1)
            with self.assertRaisesRegex(Exception, API_KEY_ENV):
                GeminiClient(MODEL, transport=lambda *_: (200, b"{}")).generate_content(
                    "requires key"
                )


class _LoopbackHandler(BaseHTTPRequestHandler):
    requests: list[tuple[str, bytes]] = []

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers["Content-Length"])
        body = self.rfile.read(length)
        type(self).requests.append((self.path, body))
        response = response_payload(promptTokenCount=4, candidatesTokenCount=2)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, format: str, *args: object) -> None:
        del format, args


def _loopback_available() -> bool:
    try:
        server = HTTPServer(("127.0.0.1", 0), _LoopbackHandler)
    except OSError:
        return False
    server.server_close()
    return True


@unittest.skipUnless(_loopback_available(), "loopback binding unavailable")
class GeminiLoopbackTests(unittest.TestCase):
    def test_default_urllib_transport_end_to_end(self) -> None:
        _LoopbackHandler.requests = []
        server = HTTPServer(("127.0.0.1", 0), _LoopbackHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with patch.dict(os.environ, {API_KEY_ENV: SENTINEL}, clear=False):
                result = GeminiClient(
                    MODEL,
                    base_url=f"http://127.0.0.1:{server.server_port}/v1beta",
                ).generate_content("loopback")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
        self.assertEqual(result.text, "accepted")
        self.assertEqual(result.usage.input_tokens, 4)
        self.assertEqual(len(_LoopbackHandler.requests), 1)
        request_path, request_body = _LoopbackHandler.requests[0]
        self.assertNotIn("key=", request_path)
        self.assertEqual(json.loads(request_body)["contents"][0]["parts"][0]["text"], "loopback")


if __name__ == "__main__":
    unittest.main()
