"""Safe, testable transport for Gemini ``generateContent`` requests.

The adapter deliberately has no command-line surface and does not know about
the reference image passes.  It owns only provider transport concerns:
request construction, bounded retries, response retention, and usage
normalization.  The API key is read at call time from
``CULL_AUDIT_GEMINI_API_KEY`` and is never accepted as a function argument.

All request execution can be tested without a network by supplying a
``transport`` callable.  The default callable uses :mod:`urllib.request`.
"""

from __future__ import annotations

import base64
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import time
from typing import Any
from urllib.error import HTTPError as UrllibHTTPError
from urllib.error import URLError
from urllib.parse import quote, quote_plus
from urllib.request import Request, urlopen


API_KEY_ENV = "CULL_AUDIT_GEMINI_API_KEY"
DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_TIMEOUT = 60.0
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BACKOFF_SECONDS = 1.0
DEFAULT_MIME_TYPE = "image/jpeg"

Transport = Callable[
    [str, Mapping[str, str], bytes, float],
    tuple[int, bytes],
]
Sleeper = Callable[[float], None]


def _secret_variants(secret: str | None) -> tuple[str, ...]:
    """Return forms which could expose a secret in a URL or JSON message."""
    if not secret:
        return ()
    variants = {
        secret,
        quote(secret, safe=""),
        quote_plus(secret),
        base64.b64encode(secret.encode("utf-8")).decode("ascii"),
    }
    try:
        escaped = json.dumps(secret, ensure_ascii=True)[1:-1]
    except (TypeError, ValueError):
        escaped = ""
    if escaped:
        variants.add(escaped)
    return tuple(sorted((item for item in variants if item), key=len, reverse=True))


def _scrub_text(value: object, *secrets: str | None) -> str:
    """Convert an arbitrary error value to text without exposing a key."""
    text = str(value)
    all_secrets: set[str] = set()
    for secret in secrets:
        all_secrets.update(_secret_variants(secret))
    current = os.environ.get(API_KEY_ENV)
    all_secrets.update(_secret_variants(current))
    for secret in sorted(all_secrets, key=len, reverse=True):
        text = text.replace(secret, "[REDACTED]")
    return text


def _scrub_bytes(value: bytes, secret: str | None) -> bytes:
    """Redact key forms before a response is written to disk."""
    result = value
    for variant in _secret_variants(secret):
        encoded = variant.encode("utf-8")
        if encoded:
            result = result.replace(encoded, b"[REDACTED]")
    return result


class GeminiError(Exception):
    """Base class for provider adapter errors."""

    def __init__(self, message: object, *, secret: str | None = None) -> None:
        self._secret = secret or os.environ.get(API_KEY_ENV)
        super().__init__(_scrub_text(message, self._secret))

    def __str__(self) -> str:
        return _scrub_text(super().__str__(), self._secret)


class GeminiConfigurationError(GeminiError):
    """The client or request configuration is invalid."""


class GeminiTransportError(GeminiError):
    """A network or transport operation failed."""

    def __init__(
        self,
        message: object,
        *,
        attempts: Sequence["GeminiAttempt"] = (),
        secret: str | None = None,
    ) -> None:
        self.attempt_records = tuple(attempts)
        self.attempts = len(self.attempt_records)
        super().__init__(message, secret=secret)

    @property
    def responses(self) -> tuple["GeminiAttempt", ...]:
        """Alias for callers that use response terminology."""
        return self.attempt_records


class GeminiHTTPError(GeminiError):
    """The provider returned an unsuccessful HTTP status."""

    def __init__(
        self,
        message: object,
        *,
        status_code: int,
        body: bytes = b"",
        attempts: Sequence["GeminiAttempt"] = (),
        secret: str | None = None,
    ) -> None:
        self.status_code = status_code
        self.body = _scrub_bytes(
            bytes(body),
            secret if secret is not None else os.environ.get(API_KEY_ENV),
        )
        self.raw_body = self.body
        self.attempt_records = tuple(attempts)
        self.attempts = len(self.attempt_records)
        super().__init__(message, secret=secret)

    @property
    def responses(self) -> tuple["GeminiAttempt", ...]:
        """Alias for callers that use response terminology."""
        return self.attempt_records


class GeminiRetryError(GeminiHTTPError):
    """All bounded retry attempts ended with retryable HTTP responses."""


class GeminiResponseError(GeminiError):
    """A successful HTTP response could not be parsed as Gemini JSON."""

    def __init__(
        self,
        message: object,
        *,
        body: bytes = b"",
        attempts: Sequence["GeminiAttempt"] = (),
        secret: str | None = None,
    ) -> None:
        self.body = _scrub_bytes(
            bytes(body),
            secret if secret is not None else os.environ.get(API_KEY_ENV),
        )
        self.raw_body = self.body
        self.attempt_records = tuple(attempts)
        self.attempts = len(self.attempt_records)
        super().__init__(message, secret=secret)


class GeminiRetentionError(GeminiError):
    """A configured response-retention directory could not be written."""


@dataclass(frozen=True, slots=True)
class GeminiUsage:
    """Provider token counters mapped to the cull-audit usage contract."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    thinking_tokens: int | None = None
    calls: int = 1

    def to_dict(self) -> dict[str, int | None]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "thinking_tokens": self.thinking_tokens,
            "calls": self.calls,
        }

    as_dict = to_dict


@dataclass(frozen=True, slots=True)
class GeminiAttempt:
    """One retained provider attempt, including failed attempts."""

    attempt: int
    status_code: int | None
    raw_body: bytes = b""
    retention_path: Path | None = None
    error: str | None = None

    @property
    def body(self) -> bytes:
        return self.raw_body

    @property
    def status(self) -> int | None:
        return self.status_code

    @property
    def attempt_number(self) -> int:
        return self.attempt


@dataclass(frozen=True, slots=True)
class GeminiResponse:
    """Parsed successful response plus every attempt used to obtain it."""

    status_code: int
    payload: Mapping[str, Any]
    raw_body: bytes
    usage: GeminiUsage
    attempts: int
    attempt_records: tuple[GeminiAttempt, ...] = ()

    @property
    def body(self) -> bytes:
        return self.raw_body

    @property
    def body_bytes(self) -> bytes:
        return self.raw_body

    @property
    def data(self) -> Mapping[str, Any]:
        return self.payload

    @property
    def json(self) -> Mapping[str, Any]:
        return self.payload

    @property
    def response_json(self) -> Mapping[str, Any]:
        return self.payload

    @property
    def responses(self) -> tuple[GeminiAttempt, ...]:
        return self.attempt_records

    @property
    def raw_bodies(self) -> tuple[bytes, ...]:
        return tuple(item.raw_body for item in self.attempt_records)

    @property
    def text(self) -> str:
        """Return concatenated text parts from the provider's candidates."""
        candidates = self.payload.get("candidates", ())
        if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes)):
            return ""
        parts: list[str] = []
        for candidate in candidates:
            if not isinstance(candidate, Mapping):
                continue
            content = candidate.get("content", {})
            if not isinstance(content, Mapping):
                continue
            raw_parts = content.get("parts", ())
            if not isinstance(raw_parts, Sequence) or isinstance(raw_parts, (str, bytes)):
                continue
            for part in raw_parts:
                if isinstance(part, Mapping) and isinstance(part.get("text"), str):
                    parts.append(part["text"])
        return "".join(parts)

    def __getitem__(self, key: str) -> Any:
        return self.payload[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.payload.get(key, default)


@dataclass(frozen=True, slots=True)
class PlannedCall:
    """One input to :func:`plan_dry_run`."""

    prompt: str
    image_bytes: bytes | None = None
    mime_type: str = DEFAULT_MIME_TYPE
    generation_config: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DryRunEstimate:
    """Request-size estimate which deliberately contains no rate or cost guess."""

    model: str
    call_count: int
    request_sizes: tuple[int, ...]
    total_request_bytes: int

    @property
    def calls(self) -> int:
        return self.call_count

    @property
    def request_size_bytes(self) -> tuple[int, ...]:
        return self.request_sizes

    @property
    def total_bytes(self) -> int:
        return self.total_request_bytes

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "call_count": self.call_count,
            "request_sizes": list(self.request_sizes),
            "total_request_bytes": self.total_request_bytes,
        }

    as_dict = to_dict


def _validate_model(model: str) -> str:
    if not isinstance(model, str) or not model.strip():
        raise GeminiConfigurationError("model must be a non-empty string")
    return model.strip().removeprefix("models/")


def _validate_prompt(prompt: str) -> str:
    if not isinstance(prompt, str):
        raise GeminiConfigurationError("prompt must be a string")
    return prompt


def _coerce_image_bytes(image_bytes: bytes | bytearray | memoryview | None) -> bytes | None:
    if image_bytes is None:
        return None
    if not isinstance(image_bytes, (bytes, bytearray, memoryview)):
        raise GeminiConfigurationError("image_bytes must be bytes-like")
    return bytes(image_bytes)


def build_request_body(
    prompt: str,
    image_bytes: bytes | bytearray | memoryview | None = None,
    generation_config: Mapping[str, Any] | None = None,
    mime_type: str = DEFAULT_MIME_TYPE,
    *,
    image_data: bytes | bytearray | memoryview | None = None,
    image_mime_type: str | None = None,
) -> bytes:
    """Build deterministic JSON for one Gemini ``generateContent`` request."""
    if image_data is not None:
        if image_bytes is not None:
            raise GeminiConfigurationError(
                "provide only one of image_bytes and image_data"
            )
        image_bytes = image_data
    if image_mime_type is not None:
        if mime_type != DEFAULT_MIME_TYPE and mime_type != image_mime_type:
            raise GeminiConfigurationError(
                "provide only one of mime_type and image_mime_type"
            )
        mime_type = image_mime_type
    prompt = _validate_prompt(prompt)
    if not isinstance(mime_type, str) or not mime_type:
        raise GeminiConfigurationError("mime_type must be a non-empty string")
    image = _coerce_image_bytes(image_bytes)
    parts: list[dict[str, Any]] = [{"text": prompt}]
    if image is not None:
        parts.append(
            {
                "inlineData": {
                    "mimeType": mime_type,
                    "data": base64.b64encode(image).decode("ascii"),
                }
            }
        )
    if generation_config is None:
        config: Mapping[str, Any] = {}
    elif isinstance(generation_config, Mapping):
        config = generation_config
    else:
        raise GeminiConfigurationError("generation_config must be an object")
    payload = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": dict(config),
    }
    try:
        return json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise GeminiConfigurationError(
            "request payload contains a value which is not JSON serializable"
        ) from exc


def build_payload(
    prompt: str,
    image_bytes: bytes | bytearray | memoryview | None = None,
    generation_config: Mapping[str, Any] | None = None,
    mime_type: str = DEFAULT_MIME_TYPE,
) -> dict[str, Any]:
    """Return the request object before JSON serialization."""
    raw = build_request_body(prompt, image_bytes, generation_config, mime_type)
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict):
        raise GeminiConfigurationError("request payload must be an object")
    return value


def parse_usage(
    response: Mapping[str, Any],
    attempts: int = 1,
    *,
    calls: int | None = None,
) -> GeminiUsage:
    """Map Gemini ``usageMetadata`` counters without inventing missing values."""
    if not isinstance(response, Mapping):
        raise GeminiResponseError("provider response must be a JSON object")
    raw_usage: Any = response.get("usageMetadata")
    if raw_usage is None:
        raw_usage = response.get("usage_metadata")
    if raw_usage is None:
        raw_usage = response
    if not isinstance(raw_usage, Mapping):
        raw_usage = {}

    def token(name: str) -> int | None:
        value = raw_usage.get(name)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return None
        return value

    count = attempts if calls is None else calls
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        count = 1
    return GeminiUsage(
        input_tokens=token("promptTokenCount"),
        output_tokens=token("candidatesTokenCount"),
        thinking_tokens=token("thoughtsTokenCount"),
        calls=count,
    )


def _parse_json_body(body: bytes | bytearray | memoryview | str) -> tuple[bytes, Mapping[str, Any]]:
    if isinstance(body, str):
        raw = body.encode("utf-8")
    elif isinstance(body, (bytes, bytearray, memoryview)):
        raw = bytes(body)
    else:
        raise GeminiResponseError("provider response body must be bytes or text")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GeminiResponseError("provider returned invalid JSON", body=raw) from exc
    if not isinstance(value, Mapping):
        raise GeminiResponseError("provider response JSON must be an object", body=raw)
    return raw, value


def parse_response(
    body: bytes | bytearray | memoryview | str | Mapping[str, Any],
    *,
    attempts: int = 1,
    status_code: int = 200,
    attempt_records: Sequence[GeminiAttempt] = (),
) -> GeminiResponse:
    """Parse one successful body into a response and normalized usage."""
    if isinstance(body, Mapping):
        payload = body
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    else:
        raw, payload = _parse_json_body(body)
    records = tuple(attempt_records)
    count = len(records) if records else attempts
    if count < 1:
        count = 1
    return GeminiResponse(
        status_code=status_code,
        payload=payload,
        raw_body=raw,
        usage=parse_usage(payload, count),
        attempts=count,
        attempt_records=records,
    )


def _read_http_error_body(error: UrllibHTTPError) -> bytes:
    try:
        value = error.read()
    except (OSError, ValueError):
        return b""
    return value if isinstance(value, bytes) else bytes(value)


def urllib_transport(
    url: str,
    headers: Mapping[str, str],
    body_bytes: bytes,
    timeout: float,
) -> tuple[int, bytes]:
    """Default POST transport implemented only with Python's urllib."""
    request = Request(
        url,
        data=body_bytes,
        headers=dict(headers),
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            status = int(getattr(response, "status", response.getcode()))
            return status, response.read()
    except UrllibHTTPError as exc:
        return int(exc.code), _read_http_error_body(exc)


def _endpoint_url(base_url: str, model: str) -> str:
    root = base_url.rstrip("/")
    if "{model}" in root:
        root = root.format(model=quote(model, safe=""))
    elif root.endswith(":generateContent"):
        pass
    else:
        root = f"{root}/models/{quote(model, safe='')}:generateContent"
    return root


def _read_api_key() -> str:
    value = os.environ.get(API_KEY_ENV)
    if not value:
        raise GeminiConfigurationError(
            f"{API_KEY_ENV} must be set for a provider request"
        )
    return value


def _normalise_transport_result(value: object) -> tuple[int, bytes]:
    if (
        not isinstance(value, tuple)
        or len(value) != 2
        or isinstance(value[0], bool)
        or not isinstance(value[0], int)
    ):
        raise GeminiTransportError(
            "transport must return a (status, body_bytes) tuple"
        )
    status, body = value
    if not isinstance(body, (bytes, bytearray, memoryview)):
        raise GeminiTransportError("transport must return response body bytes")
    return status, bytes(body)


def _planned_call(
    value: PlannedCall | Mapping[str, Any] | Sequence[Any] | str,
    *,
    default_generation_config: Mapping[str, Any] | None,
    default_mime_type: str,
) -> PlannedCall:
    if isinstance(value, PlannedCall):
        return value
    if isinstance(value, str):
        return PlannedCall(
            prompt=value,
            mime_type=default_mime_type,
            generation_config=(
                {} if default_generation_config is None else default_generation_config
            ),
        )
    if isinstance(value, Mapping):
        prompt = value.get("prompt", value.get("prompt_text", value.get("text")))
        if prompt is None:
            raise GeminiConfigurationError("each planned call needs a prompt")
        image = value.get("image_bytes", value.get("image_data", value.get("image")))
        config = value.get("generation_config", value.get("generationConfig"))
        if config is None:
            config = {} if default_generation_config is None else default_generation_config
        mime = value.get("mime_type", value.get("mimeType", default_mime_type))
        return PlannedCall(prompt, image, mime, config)
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, memoryview)):
        if not value:
            raise GeminiConfigurationError("a planned call sequence cannot be empty")
        prompt = value[0]
        image = value[1] if len(value) > 1 else None
        config = value[2] if len(value) > 2 else default_generation_config
        mime = value[3] if len(value) > 3 else default_mime_type
        if config is None:
            config = {}
        return PlannedCall(prompt, image, mime, config)
    raise GeminiConfigurationError("planned calls must contain prompt specifications")


def plan_dry_run(
    model: str,
    planned_calls: Sequence[
        PlannedCall | Mapping[str, Any] | Sequence[Any] | str
    ],
    *,
    default_generation_config: Mapping[str, Any] | None = None,
    default_mime_type: str = DEFAULT_MIME_TYPE,
) -> DryRunEstimate:
    """Estimate request count and JSON body sizes without reading the API key."""
    model_name = _validate_model(model)
    sizes: list[int] = []
    for item in planned_calls:
        call = _planned_call(
            item,
            default_generation_config=default_generation_config,
            default_mime_type=default_mime_type,
        )
        body = build_request_body(
            call.prompt,
            call.image_bytes,
            call.generation_config,
            call.mime_type,
        )
        sizes.append(len(body))
    return DryRunEstimate(model_name, len(sizes), tuple(sizes), sum(sizes))


dry_run_plan = plan_dry_run
estimate_dry_run = plan_dry_run


class GeminiClient:
    """A bounded, injectable Gemini ``generateContent`` client."""

    def __init__(
        self,
        model: str,
        *,
        transport: Transport | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        sleeper: Sleeper = time.sleep,
        backoff: float = DEFAULT_BACKOFF_SECONDS,
        retention_dir: str | os.PathLike[str] | None = None,
        base_url: str = DEFAULT_BASE_URL,
        max_retries: int | None = None,
        backoff_seconds: float | None = None,
    ) -> None:
        self.model = _validate_model(model)
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
            raise GeminiConfigurationError("timeout must be a positive number")
        if max_retries is not None:
            if isinstance(max_retries, bool) or not isinstance(max_retries, int) or max_retries < 0:
                raise GeminiConfigurationError("max_retries must be a non-negative integer")
            max_attempts = max_retries + 1
        if isinstance(max_attempts, bool) or not isinstance(max_attempts, int) or max_attempts < 1:
            raise GeminiConfigurationError("max_attempts must be a positive integer")
        if backoff_seconds is not None:
            backoff = backoff_seconds
        if isinstance(backoff, bool) or not isinstance(backoff, (int, float)) or backoff < 0:
            raise GeminiConfigurationError("backoff must be a non-negative number")
        if not isinstance(base_url, str) or not base_url.strip():
            raise GeminiConfigurationError("base_url must be a non-empty string")
        if transport is not None and not callable(transport):
            raise GeminiConfigurationError("transport must be callable")
        if not callable(sleeper):
            raise GeminiConfigurationError("sleeper must be callable")
        self.transport = urllib_transport if transport is None else transport
        self.timeout = float(timeout)
        self.max_attempts = max_attempts
        self.sleeper = sleeper
        self.backoff = float(backoff)
        self.retention_dir = None if retention_dir is None else Path(retention_dir)
        self.base_url = base_url
        self._call_number = 0

    def _retention_path(
        self,
        call_number: int,
        attempt_number: int,
        body: bytes,
        secret: str,
    ) -> Path | None:
        if self.retention_dir is None:
            return None
        path = self.retention_dir / (
            f"call-{call_number:06d}-attempt-{attempt_number:06d}.bin"
        )
        try:
            self.retention_dir.mkdir(parents=True, exist_ok=True)
            path.write_bytes(_scrub_bytes(body, secret))
        except OSError as exc:
            raise GeminiRetentionError(
                "unable to retain provider response",
                secret=secret,
            ) from exc
        return path

    def _record_attempt(
        self,
        call_number: int,
        attempt_number: int,
        *,
        status_code: int | None,
        body: bytes = b"",
        error: str | None = None,
        secret: str,
    ) -> GeminiAttempt:
        return GeminiAttempt(
            attempt=attempt_number,
            status_code=status_code,
            raw_body=body,
            retention_path=self._retention_path(
                call_number, attempt_number, body, secret
            ),
            error=None if error is None else _scrub_text(error, secret),
        )

    def build_request(
        self,
        prompt: str,
        image_bytes: bytes | bytearray | memoryview | None = None,
        generation_config: Mapping[str, Any] | None = None,
        mime_type: str = DEFAULT_MIME_TYPE,
    ) -> tuple[str, dict[str, str], bytes]:
        """Build URL, headers, and body using the environment-only key."""
        secret = _read_api_key()
        body = build_request_body(
            prompt,
            image_bytes,
            generation_config,
            mime_type,
        )
        return (
            _endpoint_url(self.base_url, self.model),
            {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "x-goog-api-key": secret,
            },
            body,
        )

    def generate_content(
        self,
        prompt: str,
        image_bytes: bytes | bytearray | memoryview | None = None,
        generation_config: Mapping[str, Any] | None = None,
        mime_type: str = DEFAULT_MIME_TYPE,
        *,
        image_data: bytes | bytearray | memoryview | None = None,
        image_mime_type: str | None = None,
    ) -> GeminiResponse:
        """Send one request and return parsed JSON plus retained attempts."""
        secret = _read_api_key()
        body = build_request_body(
            prompt,
            image_bytes,
            generation_config,
            mime_type,
            image_data=image_data,
            image_mime_type=image_mime_type,
        )
        self._call_number += 1
        call_number = self._call_number
        url = _endpoint_url(self.base_url, self.model)
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "x-goog-api-key": secret,
        }
        attempts: list[GeminiAttempt] = []
        for attempt_number in range(1, self.max_attempts + 1):
            try:
                result = self.transport(url, headers, body, self.timeout)
                status, response_body = _normalise_transport_result(result)
                attempt = self._record_attempt(
                    call_number,
                    attempt_number,
                    status_code=status,
                    body=response_body,
                    secret=secret,
                )
                attempts.append(attempt)
            except UrllibHTTPError as exc:
                status = int(exc.code)
                response_body = _read_http_error_body(exc)
                attempt = self._record_attempt(
                    call_number,
                    attempt_number,
                    status_code=status,
                    body=response_body,
                    error=_scrub_text(exc, secret),
                    secret=secret,
                )
                attempts.append(attempt)
            except (OSError, URLError, TimeoutError) as exc:
                attempt = self._record_attempt(
                    call_number,
                    attempt_number,
                    status_code=None,
                    error=_scrub_text(exc, secret),
                    secret=secret,
                )
                attempts.append(attempt)
                if attempt_number < self.max_attempts:
                    self.sleeper(self.backoff * (2 ** (attempt_number - 1)))
                    continue
                raise GeminiTransportError(
                    "provider transport failed after bounded retries",
                    attempts=attempts,
                    secret=secret,
                ) from exc
            except GeminiError:
                raise
            except Exception as exc:
                raise GeminiTransportError(
                    "transport callable failed",
                    attempts=attempts,
                    secret=secret,
                ) from exc

            retryable = status == 429 or 500 <= status <= 599
            if 200 <= status <= 299:
                try:
                    return parse_response(
                        response_body,
                        attempts=len(attempts),
                        status_code=status,
                        attempt_records=attempts,
                    )
                except GeminiResponseError as exc:
                    raise GeminiResponseError(
                        str(exc),
                        body=response_body,
                        attempts=attempts,
                        secret=secret,
                    ) from exc
            if retryable and attempt_number < self.max_attempts:
                self.sleeper(self.backoff * (2 ** (attempt_number - 1)))
                continue
            error_type = GeminiRetryError if retryable else GeminiHTTPError
            raise error_type(
                f"provider returned HTTP status {status}",
                status_code=status,
                body=response_body,
                attempts=attempts,
                secret=secret,
            )
        raise GeminiTransportError(
            "provider request ended without a response",
            attempts=attempts,
            secret=secret,
        )

    request = generate_content
    generate = generate_content
    call = generate_content

    def plan_dry_run(
        self,
        planned_calls: Sequence[
            PlannedCall | Mapping[str, Any] | Sequence[Any] | str
        ],
        *,
        default_generation_config: Mapping[str, Any] | None = None,
        default_mime_type: str = DEFAULT_MIME_TYPE,
    ) -> DryRunEstimate:
        """Plan requests without reading the key or invoking the transport."""
        return plan_dry_run(
            self.model,
            planned_calls,
            default_generation_config=default_generation_config,
            default_mime_type=default_mime_type,
        )

    dry_run = plan_dry_run


def build_request(
    model: str,
    prompt: str,
    image_bytes: bytes | bytearray | memoryview | None = None,
    generation_config: Mapping[str, Any] | None = None,
    mime_type: str = DEFAULT_MIME_TYPE,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    base_url: str = DEFAULT_BASE_URL,
) -> tuple[str, dict[str, str], bytes]:
    """Build one provider request without sending it."""
    client = GeminiClient(
        model,
        timeout=timeout,
        base_url=base_url,
    )
    return client.build_request(prompt, image_bytes, generation_config, mime_type)


def generate_content(
    model: str,
    prompt: str,
    image_bytes: bytes | bytearray | memoryview | None = None,
    generation_config: Mapping[str, Any] | None = None,
    mime_type: str = DEFAULT_MIME_TYPE,
    *,
    transport: Transport | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    sleeper: Sleeper = time.sleep,
    backoff: float = DEFAULT_BACKOFF_SECONDS,
    retention_dir: str | os.PathLike[str] | None = None,
    base_url: str = DEFAULT_BASE_URL,
    max_retries: int | None = None,
    backoff_seconds: float | None = None,
) -> GeminiResponse:
    """Convenience wrapper around :class:`GeminiClient`."""
    client = GeminiClient(
        model,
        transport=transport,
        timeout=timeout,
        max_attempts=max_attempts,
        sleeper=sleeper,
        backoff=backoff,
        retention_dir=retention_dir,
        base_url=base_url,
        max_retries=max_retries,
        backoff_seconds=backoff_seconds,
    )
    return client.generate_content(
        prompt,
        image_bytes,
        generation_config,
        mime_type,
    )


send_generate_content = generate_content
request_content = generate_content
parse_usage_metadata = parse_usage
make_request_body = build_request_body
build_body = build_request_body
TransportError = GeminiTransportError
HTTPError = GeminiHTTPError
ResponseError = GeminiResponseError


__all__ = [
    "API_KEY_ENV",
    "DEFAULT_BASE_URL",
    "DEFAULT_TIMEOUT",
    "DEFAULT_MAX_ATTEMPTS",
    "DEFAULT_BACKOFF_SECONDS",
    "DEFAULT_MIME_TYPE",
    "DryRunEstimate",
    "GeminiAttempt",
    "GeminiClient",
    "GeminiConfigurationError",
    "GeminiError",
    "GeminiHTTPError",
    "GeminiResponse",
    "GeminiResponseError",
    "GeminiRetryError",
    "GeminiRetentionError",
    "GeminiTransportError",
    "GeminiUsage",
    "PlannedCall",
    "Transport",
    "build_payload",
    "build_request",
    "build_request_body",
    "dry_run_plan",
    "estimate_dry_run",
    "generate_content",
    "make_request_body",
    "parse_response",
    "parse_usage",
    "parse_usage_metadata",
    "plan_dry_run",
    "request_content",
    "send_generate_content",
    "urllib_transport",
]
