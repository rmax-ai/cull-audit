"""Deterministic orchestration for the optional Gemini reference passes.

This module owns the reference workflow, not a model-specific judgment
schema.  Provider responses are reduced to the generic version 1 judgment
contract before they are written.  Raw responses remain in ``responses/`` and
the exact bytes sent to the provider remain in ``prepared/``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
from typing import Any

from . import gemini
from .gemini import (
    GeminiClient,
    GeminiConfigurationError,
    GeminiError,
    GeminiResponse,
)
from .images import (
    DEFAULT_MAX_EDGE,
    ImageInput,
    ImagePreparationError,
    image_info,
    make_contact_sheet,
    mime_type_for_format,
    prepare_dedicated,
    prepare_face_crop,
)
from .. import __version__
from ..contracts import (
    JudgmentDocument,
    JudgmentRecord,
    validate_document,
)
from ..discover import PhotoEntry, discover


DEFAULT_FINALISTS = 12
DEFAULT_REPEAT_TOP = 3
DEFAULT_REPEAT_COUNT = 2
DEFAULT_GENERATION_CONFIG: dict[str, Any] = {
    "responseMimeType": "application/json",
    "temperature": 0,
}
PASS_NAMES = ("triage", "dedicated", "face", "repeat")
PROMPT_IDS = {
    "triage": "triage-v1",
    "dedicated": "dedicated-v1",
    "face": "face-v1",
    "repeat": "repeat-v1",
}
TOOL_NAME = "cull-audit-reference"
_FALLBACK_PROMPTS = {
    "triage": """# Triage reference read

Prompt version: triage-v1

Review the contact sheet as a relative comparison. Return JSON only: an
array with one object per supplied position. Each object must contain
photo_id, verdict (accept, maybe, or reject), composite from 0 to 100,
scores, reasons, and kill_factors. Judge only visible image quality relative
to the other images; do not claim human ground truth.
""",
    "dedicated": """# Dedicated reference read

Prompt version: dedicated-v1

Review the supplied photograph at the absolute-read scale. Return one JSON
object with verdict, composite from 0 to 100, scores, reasons,
kill_factors, and, when a face is visible, bbox as normalized x0,y0,x1,y1
coordinates. Use only accept, maybe, or reject for verdict.
""",
    "face": """# Face reference read

Prompt version: face-v1

Review the supplied margin crop as a face/detail read. Return one JSON object
with verdict, composite from 0 to 100, scores, reasons, and kill_factors.
Use only accept, maybe, or reject for verdict.
""",
    "repeat": """# Repeat reference read

Prompt version: repeat-v1

Review this exact prepared input with the exact repeat settings. Return one
JSON object with verdict, composite from 0 to 100, scores, reasons, and
kill_factors. Use only accept, maybe, or reject for verdict.
""",
}


class ReferenceError(Exception):
    """Base class for reference-run failures."""


class ReferenceConfigurationError(ReferenceError):
    """The reference run options are invalid."""


class ReferenceContractError(ReferenceError):
    """Provider output could not be reduced to a valid contract document."""


class ReferenceIOError(ReferenceError):
    """A local photo or artifact operation failed."""


class ReferenceProviderError(ReferenceError):
    """The configured provider could not complete a request."""


@dataclass(frozen=True, slots=True)
class ReferencePhoto:
    """One source photo held as immutable bytes for a run."""

    photo_id: str
    data: bytes
    source_path: Path | None = None


@dataclass(frozen=True, slots=True)
class PlannedReferenceCall:
    """A printable, deterministic description of a planned provider call."""

    pass_name: str
    photo_ids: tuple[str, ...]
    prompt_id: str
    image_bytes: int
    prepared_path: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "pass": self.pass_name,
            "photo_ids": list(self.photo_ids),
            "prompt_id": self.prompt_id,
            "image_bytes": self.image_bytes,
            "prepared": self.prepared_path,
        }


@dataclass(frozen=True, slots=True)
class ReferenceRunResult:
    """Artifacts and normalized records returned by :func:`run_reference`."""

    records: tuple[JudgmentRecord, ...] = ()
    document: JudgmentDocument | None = None
    output_dir: Path | None = None
    prepared_paths: tuple[Path, ...] = ()
    response_paths: tuple[Path, ...] = ()
    planned_calls: tuple[PlannedReferenceCall, ...] = ()
    dry_run: bool = False

    @property
    def judgments_path(self) -> Path | None:
        if self.output_dir is None or self.dry_run:
            return None
        return self.output_dir / "judgments.json"

    @property
    def judgments(self) -> tuple[JudgmentRecord, ...]:
        """Alias for callers that name normalized records judgments."""

        return self.records

    @property
    def prepared(self) -> tuple[Path, ...]:
        """Alias for the prepared artifact paths."""

        return self.prepared_paths

    @property
    def responses(self) -> tuple[Path, ...]:
        """Alias for retained response artifact paths."""

        return self.response_paths

    def __iter__(self):
        return iter(self.records)

    def __len__(self) -> int:
        return len(self.records)

    def __getitem__(self, index: int) -> JudgmentRecord:
        return self.records[index]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "records": [record.to_dict() for record in self.records],
        }


def _read_prompt(pass_name: str, prompt_dir: str | os.PathLike[str] | None = None) -> str:
    """Read a versioned prompt file, with a source-install fallback."""

    if pass_name not in PROMPT_IDS:
        raise ReferenceConfigurationError(f"unknown pass {pass_name!r}")
    candidates: list[Path] = []
    if prompt_dir is not None:
        candidates.append(Path(prompt_dir) / f"{pass_name}.md")
    # In a source checkout, prompts are deliberately kept at the repository
    # root as human-reviewable files rather than hidden in Python strings.
    candidates.append(Path(__file__).resolve().parents[3] / "prompts" / f"{pass_name}.md")
    for path in candidates:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if text.strip():
            return text
    return _FALLBACK_PROMPTS[pass_name]


def prompt_text(
    pass_name: str,
    *,
    prompt_dir: str | os.PathLike[str] | None = None,
) -> str:
    """Public prompt loader used by tests and integrations."""

    return _read_prompt(pass_name, prompt_dir)


def prompt_id(pass_name: str) -> str:
    """Return the stable ID recorded in a judgment context."""

    try:
        return PROMPT_IDS[pass_name]
    except KeyError as exc:
        raise ReferenceConfigurationError(f"unknown pass {pass_name!r}") from exc


def settings_fingerprint(
    *,
    model: str,
    prompt: str,
    generation_config: Mapping[str, Any] | None = None,
    mime_type: str = "image/png",
) -> str:
    """Hash only model, prompt, and generation settings, never response data."""

    payload = {
        "model": model.removeprefix("models/").strip(),
        "prompt": prompt,
        "generation_config": {} if generation_config is None else dict(generation_config),
        "mime_type": mime_type,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")
    return slug or "photo"


def _write_prepared(
    output_dir: Path | None,
    pass_name: str,
    ordinal: int,
    photo_id: str,
    data: bytes,
    *,
    suffix: str = ".png",
) -> Path | None:
    if output_dir is None:
        return None
    directory = output_dir / "prepared" / pass_name
    try:
        directory.mkdir(parents=True, exist_ok=True)
        slug = _safe_slug(photo_id)
        if suffix and slug.lower().endswith(suffix.lower()):
            slug = slug[: -len(suffix)]
        path = directory / f"{ordinal:06d}-{slug}{suffix}"
        path.write_bytes(data)
    except OSError as exc:
        raise ReferenceIOError(f"unable to write prepared input {photo_id}: {exc}") from exc
    return path


def _normalise_photo_collection(
    photos: str | os.PathLike[str] | Mapping[str, Any] | Iterable[Any],
) -> tuple[ReferencePhoto, ...]:
    """Load photos from a root or normalize an in-memory collection."""

    if isinstance(photos, (str, os.PathLike)):
        root = Path(photos)
        try:
            result = discover(root)
        except (OSError, ValueError) as exc:
            raise ReferenceIOError(f"unable to discover photos under {photos}: {exc}") from exc
        if result.unreadable:
            names = ", ".join(result.unreadable)
            raise ReferenceIOError(f"unable to decode photo(s) under {photos}: {names}")
        values: list[ReferencePhoto] = []
        for entry in result.entries:
            try:
                values.append(ReferencePhoto(entry.photo_id, (root / entry.path).read_bytes(), root / entry.path))
            except OSError as exc:
                raise ReferenceIOError(f"unable to read photo {entry.path}: {exc}") from exc
        if not values:
            raise ReferenceIOError(f"no supported photos found under {photos}")
        return tuple(values)

    if isinstance(photos, Mapping):
        iterable: Iterable[Any] = photos.items()
    else:
        iterable = photos
    values = []
    for item in iterable:
        if isinstance(item, ReferencePhoto):
            values.append(item)
            continue
        if isinstance(item, PhotoEntry):
            raise ReferenceIOError(
                "PhotoEntry inputs need a photo-root path; pass photos as a directory"
            )
        if isinstance(item, ImageInput):
            values.append(ReferencePhoto(item.photo_id, bytes(item.data)))
            continue
        if isinstance(item, tuple) and len(item) == 2:
            photo_id, source = item
        elif isinstance(item, Mapping):
            photo_id = item.get("photo_id", item.get("id", item.get("path")))
            source = item.get("data", item.get("bytes", item.get("image")))
        else:
            photo_id = getattr(item, "photo_id", getattr(item, "path", None))
            source = getattr(item, "data", getattr(item, "bytes", None))
        if not isinstance(photo_id, str) or not photo_id:
            raise ReferenceIOError("each photo input needs a non-empty photo_id")
        if source is None:
            raise ReferenceIOError(f"photo {photo_id!r} has no image data")
        if isinstance(source, (str, os.PathLike)):
            try:
                data = Path(source).read_bytes()
            except OSError as exc:
                raise ReferenceIOError(f"unable to read photo {source}: {exc}") from exc
            source_path = Path(source)
        elif isinstance(source, (bytes, bytearray, memoryview)):
            data = bytes(source)
            source_path = None
        else:
            raise ReferenceIOError(f"photo {photo_id!r} has unsupported image data")
        values.append(ReferencePhoto(photo_id, data, source_path))
    values.sort(key=lambda item: item.photo_id)
    if not values:
        raise ReferenceIOError("no photos supplied")
    return tuple(values)


def _validate_options(
    passes: Sequence[str],
    finalists: int,
    repeat_top: int,
    repeat_count: int,
) -> tuple[str, ...]:
    if not passes:
        raise ReferenceConfigurationError("at least one reference pass is required")
    if isinstance(passes, str):
        passes = tuple(item for item in passes.split(",") if item.strip())
    selected = tuple(item.strip().lower() for item in passes)
    if any(item not in PASS_NAMES for item in selected):
        unknown = sorted(set(selected) - set(PASS_NAMES))
        raise ReferenceConfigurationError(f"unknown reference pass(es): {', '.join(unknown)}")
    if len(set(selected)) != len(selected):
        raise ReferenceConfigurationError("reference passes must not be repeated")
    for name, value in (
        ("finalists", finalists),
        ("repeat_top", repeat_top),
        ("repeat_count", repeat_count),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ReferenceConfigurationError(f"{name} must be a positive integer")
    return selected


def _number(value: Any, *, low: float = 0, high: float = 100) -> float | int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if not low <= value <= high:
        return None
    return value


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if not isinstance(value, Sequence) or isinstance(value, (bytes, bytearray)):
        return []
    return [item for item in value if isinstance(item, str)]


def _bbox(value: Any) -> tuple[float, float, float, float] | None:
    if isinstance(value, Mapping):
        nested = value.get("bbox", value.get("face_bbox", value.get("bounding_box")))
        value = nested if nested is not None else (
            value.get("x0"),
            value.get("y0"),
            value.get("x1"),
            value.get("y1"),
        )
    try:
        values = tuple(value)
    except (TypeError, ValueError):
        return None
    if len(values) != 4:
        return None
    if any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in values):
        return None
    result = tuple(float(item) for item in values)
    x0, y0, x1, y1 = result
    if (
        any(not math.isfinite(item) or not 0 <= item <= 1 for item in result)
        or not x0 < x1
        or not y0 < y1
    ):
        return None
    return result


def _json_candidate(text: str) -> Any:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].lstrip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, TypeError):
        lower = cleaned.lower()
        for verdict in ("accept", "maybe", "reject"):
            if re.search(rf"\b{verdict}\b", lower):
                return {"verdict": verdict}
    raise ReferenceContractError("provider response did not contain JSON judgment data")


def _response_items(response: GeminiResponse) -> list[dict[str, Any]]:
    """Extract judgment-shaped objects from common JSON response envelopes."""

    value: Any
    if response.text.strip():
        value = _json_candidate(response.text)
    else:
        value = response.payload
    if isinstance(value, Mapping):
        for key in ("records", "judgments", "results", "items", "data"):
            candidate = value.get(key)
            if isinstance(candidate, list):
                value = candidate
                break
        else:
            # A map keyed by photo ID is also a useful compact fake/provider
            # response.  Keep already judgment-shaped maps as one item.
            if not any(key in value for key in ("verdict", "composite", "score", "scores")):
                mapped = []
                for key, item in value.items():
                    if isinstance(item, Mapping):
                        mapped_item = dict(item)
                        mapped_item.setdefault("photo_id", key)
                        mapped.append(mapped_item)
                value = mapped or [dict(value)]
            else:
                value = [dict(value)]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        items = [dict(item) for item in value if isinstance(item, Mapping)]
    elif isinstance(value, Mapping):
        items = [dict(value)]
    else:
        items = []
    if not items:
        raise ReferenceContractError("provider response contained no judgment objects")
    return items


def _assign_items(
    items: Sequence[Mapping[str, Any]],
    expected_photo_ids: Sequence[str],
) -> list[tuple[str, dict[str, Any]]]:
    """Attach provider items to expected IDs deterministically."""

    expected = tuple(expected_photo_ids)
    assigned: list[tuple[str, dict[str, Any]]] = []
    used: set[str] = set()
    for position, raw in enumerate(items):
        item = dict(raw)
        candidate = item.get("photo_id", item.get("id", item.get("image_id")))
        photo_id: str | None = candidate if isinstance(candidate, str) else None
        if photo_id not in expected and isinstance(candidate, int):
            if 0 <= candidate < len(expected):
                photo_id = expected[candidate]
            elif 1 <= candidate <= len(expected):
                photo_id = expected[candidate - 1]
        if photo_id not in expected:
            remaining = [item_id for item_id in expected if item_id not in used]
            if not remaining:
                continue
            photo_id = remaining[0]
        if photo_id in used:
            continue
        used.add(photo_id)
        assigned.append((photo_id, item))
    # A single compact response for a one-photo call is the usual case.  For
    # a sheet, missing positions are a provider contract failure rather than
    # silently inventing judgments.
    if len(assigned) != len(expected):
        missing = ", ".join(item_id for item_id in expected if item_id not in used)
        raise ReferenceContractError(f"provider response omitted photo judgment(s): {missing}")
    return sorted(assigned, key=lambda item: expected.index(item[0]))


def _judgment_values(item: Mapping[str, Any]) -> dict[str, Any]:
    """Keep only generic judgment fields plus an optional normalized bbox."""

    verdict_value = item.get("verdict", item.get("decision", item.get("label")))
    verdict = str(verdict_value).strip().lower() if verdict_value is not None else ""
    if verdict not in {"accept", "maybe", "reject"}:
        raise ReferenceContractError("provider judgment verdict must be accept, maybe, or reject")
    composite = item.get("composite", item.get("score"))
    normalized_composite = _number(composite)
    if composite is not None and normalized_composite is None:
        raise ReferenceContractError("provider composite must be a finite number in [0,100]")
    scores_value = item.get("scores", {})
    scores: dict[str, float | int] = {}
    if isinstance(scores_value, Mapping):
        for name in sorted(scores_value):
            score = _number(scores_value[name])
            if score is not None:
                scores[str(name)] = score
    result: dict[str, Any] = {
        "verdict": verdict,
        "composite": normalized_composite,
        "scores": scores,
        "reasons": _string_list(item.get("reasons", item.get("reason", []))),
        "kill_factors": _string_list(item.get("kill_factors", item.get("killFactors", []))),
    }
    bbox_keys = ("bbox", "face_bbox", "bounding_box")
    raw_bbox = next((item[key] for key in bbox_keys if key in item), None)
    bbox = _bbox(raw_bbox)
    if raw_bbox is not None and bbox is None:
        raise ReferenceContractError(
            "provider bbox must be normalized x0,y0,x1,y1 with strict bounds"
        )
    if bbox is not None:
        result["bbox"] = list(bbox)
    return result


def _usage_dict(response: GeminiResponse) -> dict[str, Any] | None:
    value = response.usage.to_dict()
    if all(value.get(key) is None for key in ("input_tokens", "output_tokens", "thinking_tokens")):
        return None
    return {key: item for key, item in value.items() if item is not None}


def _record(
    *,
    record_id: str,
    photo_id: str,
    stage: str,
    read_kind: str,
    values: Mapping[str, Any],
    model: str,
    prompt_id_value: str,
    settings: str,
    input_max_edge_px: int | None = DEFAULT_MAX_EDGE,
    comparison_group: str | None = None,
    repeat_group: str | None = None,
    repeat_index: int | None = None,
    usage: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    context: dict[str, Any] = {
        "prompt_id": prompt_id_value,
        "model": model,
        "settings_fingerprint": settings,
    }
    if input_max_edge_px is not None:
        context["input_max_edge_px"] = input_max_edge_px
    if comparison_group is not None:
        context["comparison_group"] = comparison_group
    if repeat_group is not None:
        context["repeat_group"] = repeat_group
        context["repeat_index"] = repeat_index
    result: dict[str, Any] = {
        "record_id": record_id,
        "photo_id": photo_id,
        "stage": stage,
        "read_kind": read_kind,
        "verdict": values["verdict"],
        "source": {"tool": TOOL_NAME, "tool_version": __version__},
        "context": context,
    }
    if values.get("composite") is not None:
        result["composite"] = values["composite"]
    if values.get("scores"):
        result["scores"] = values["scores"]
    if values.get("reasons"):
        result["reasons"] = values["reasons"]
    if values.get("kill_factors"):
        result["kill_factors"] = values["kill_factors"]
    if "bbox" in values:
        result["face_bbox"] = values["bbox"]
    if usage is not None:
        result["usage"] = dict(usage)
    return result


def _record_value(record: JudgmentRecord | Mapping[str, Any], name: str) -> Any:
    if isinstance(record, JudgmentRecord):
        return getattr(record, name)
    return record.get(name)


def _composite_sort_key(
    record: JudgmentRecord | Mapping[str, Any],
) -> tuple[float, str]:
    value = _record_value(record, "composite")
    score = (
        float(value)
        if isinstance(value, (int, float)) and not isinstance(value, bool)
        else float("-inf")
    )
    return (-score, str(_record_value(record, "photo_id") or ""))


def select_top_records(
    records: Iterable[JudgmentRecord | Mapping[str, Any]],
    limit: int,
) -> tuple[JudgmentRecord | Mapping[str, Any], ...]:
    """Select top records by composite, breaking ties by photo ID."""

    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ReferenceConfigurationError("limit must be a positive integer")
    values = list(records)
    return tuple(sorted(values, key=_composite_sort_key)[:limit])


def select_finalists(
    triage_records: Iterable[JudgmentRecord | Mapping[str, Any]],
    limit: int,
) -> tuple[str, ...]:
    """Return stable top-N triage photo IDs."""

    selected = select_top_records(triage_records, limit)
    return tuple(
        str(_record_value(item, "photo_id"))
        for item in selected
    )


def select_repeat_photos(
    dedicated_records: Iterable[JudgmentRecord | Mapping[str, Any]],
    limit: int,
) -> tuple[str, ...]:
    """Return stable top-N dedicated photo IDs."""

    return select_finalists(dedicated_records, limit)


def _prepared_suffix(data: bytes, default: str = ".png") -> str:
    try:
        info = image_info(data)
    except ImagePreparationError:
        return default
    return {
        "JPEG": ".jpg",
        "PNG": ".png",
        "WEBP": ".webp",
        "TIFF": ".tif",
    }.get(info.format.upper(), default)


class ReferenceRunner:
    """Run the reference passes with an injectable Gemini transport."""

    def __init__(
        self,
        model: str,
        *,
        transport: gemini.Transport | None = None,
        client: GeminiClient | None = None,
        timeout: float = gemini.DEFAULT_TIMEOUT,
        max_attempts: int = gemini.DEFAULT_MAX_ATTEMPTS,
        sleeper: Callable[[float], None] | None = None,
        backoff: float = gemini.DEFAULT_BACKOFF_SECONDS,
        prompt_dir: str | os.PathLike[str] | None = None,
        generation_config: Mapping[str, Any] | None = None,
    ) -> None:
        if not isinstance(model, str) or not model.strip():
            raise ReferenceConfigurationError("model must be a non-empty string")
        if client is not None and transport is not None:
            raise ReferenceConfigurationError("provide client or transport, not both")
        self.model = model.strip().removeprefix("models/")
        self.transport = transport
        self.client = client
        self.timeout = timeout
        self.max_attempts = max_attempts
        self.sleeper = sleeper
        self.backoff = backoff
        self.prompt_dir = prompt_dir
        self.generation_config = dict(
            DEFAULT_GENERATION_CONFIG if generation_config is None else generation_config
        )

    def _client_for(self, output_dir: Path | None) -> GeminiClient:
        if self.client is not None:
            if output_dir is not None:
                # Keep injected clients subject to the same artifact policy
                # as clients created by the runner.  GeminiClient redacts
                # response bodies before retaining them.
                try:
                    self.client.retention_dir = output_dir / "responses"
                except (AttributeError, TypeError):
                    # A minimal fake client may only implement
                    # ``generate_content``.  Such a client owns its own
                    # response retention policy.
                    pass
            return self.client
        kwargs: dict[str, Any] = {
            "transport": self.transport,
            "timeout": self.timeout,
            "max_attempts": self.max_attempts,
            "backoff": self.backoff,
            "retention_dir": None if output_dir is None else output_dir / "responses",
        }
        if self.sleeper is not None:
            kwargs["sleeper"] = self.sleeper
        return GeminiClient(self.model, **kwargs)

    def _prompt(self, pass_name: str) -> tuple[str, str]:
        return prompt_id(pass_name), _read_prompt(pass_name, self.prompt_dir)

    def _planned(
        self,
        pass_name: str,
        photo_ids: Sequence[str],
        data: bytes,
        prepared_path: Path | None,
    ) -> PlannedReferenceCall:
        return PlannedReferenceCall(
            pass_name=pass_name,
            photo_ids=tuple(photo_ids),
            prompt_id=prompt_id(pass_name),
            image_bytes=len(data),
            prepared_path="" if prepared_path is None else prepared_path.as_posix(),
        )

    def _call(
        self,
        client: GeminiClient,
        pass_name: str,
        photo_ids: Sequence[str],
        data: bytes,
        prepared_path: Path | None,
        planned: list[PlannedReferenceCall],
        *,
        dry_run: bool,
        mime_type: str = "image/png",
    ) -> tuple[GeminiResponse | None, list[tuple[str, dict[str, Any]]]]:
        prompt_id_value, prompt = self._prompt(pass_name)
        del prompt_id_value
        planned.append(self._planned(pass_name, photo_ids, data, prepared_path))
        if dry_run:
            return None, []
        try:
            # GeminiClient intentionally requires the environment key even
            # with a fake transport.  For this runner's explicitly injected
            # transport, use a process-local placeholder only while invoking
            # the fake.  It is never sent by the default urllib transport,
            # never written to artifacts, and is restored immediately.
            injected_key = self.transport is not None and not os.environ.get(
                gemini.API_KEY_ENV
            )
            previous_key = os.environ.get(gemini.API_KEY_ENV)
            if injected_key:
                os.environ[gemini.API_KEY_ENV] = "injected-reference-transport"
            try:
                response = client.generate_content(
                    prompt,
                    image_bytes=data,
                    generation_config=self.generation_config,
                    mime_type=mime_type,
                )
            finally:
                if injected_key:
                    if previous_key is None:
                        os.environ.pop(gemini.API_KEY_ENV, None)
                    else:
                        os.environ[gemini.API_KEY_ENV] = previous_key
        except GeminiConfigurationError as exc:
            raise ReferenceConfigurationError(str(exc)) from exc
        except GeminiError as exc:
            raise ReferenceProviderError(str(exc)) from exc
        items = _assign_items(_response_items(response), photo_ids)
        return response, items

    def run(
        self,
        photos: str | os.PathLike[str] | Mapping[str, Any] | Iterable[Any],
        *,
        output: str | os.PathLike[str] | None = None,
        passes: Sequence[str] = PASS_NAMES,
        finalists: int = DEFAULT_FINALISTS,
        repeat_top: int = DEFAULT_REPEAT_TOP,
        repeat_count: int = DEFAULT_REPEAT_COUNT,
        dry_run: bool = False,
        bboxes: Mapping[str, Any] | None = None,
    ) -> ReferenceRunResult:
        """Prepare inputs and execute the selected reference passes."""

        selected = _validate_options(passes, finalists, repeat_top, repeat_count)
        source_photos = _normalise_photo_collection(photos)
        output_dir = None if output is None else Path(output)
        if output_dir is not None:
            try:
                output_dir.mkdir(parents=True, exist_ok=True)
                (output_dir / "prepared").mkdir(parents=True, exist_ok=True)
                if not dry_run:
                    (output_dir / "responses").mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise ReferenceIOError(f"unable to create reference output {output}: {exc}") from exc

        client = self._client_for(output_dir) if not dry_run else None
        prepared_paths: list[Path] = []
        prepared_artifacts: dict[bytes, Path] = {}
        planned: list[PlannedReferenceCall] = []
        raw_records: list[dict[str, Any]] = []
        triage_records: list[dict[str, Any]] = []
        dedicated_records: list[dict[str, Any]] = []
        bbox_by_photo: dict[str, tuple[float, float, float, float]] = {}
        photo_by_id = {photo.photo_id: photo for photo in source_photos}

        def write_prepared(
            pass_name: str,
            ordinal: int,
            photo_id: str,
            data: bytes,
            *,
            suffix: str = ".png",
        ) -> Path | None:
            """Write one prepared byte string once per reference run."""

            if output_dir is None:
                return None
            cached = prepared_artifacts.get(data)
            if cached is not None:
                return cached
            path = _write_prepared(
                output_dir,
                pass_name,
                ordinal,
                photo_id,
                data,
                suffix=suffix,
            )
            if path is not None:
                prepared_artifacts[data] = path
            return path

        def track_prepared(path: Path | None) -> None:
            if path is not None and path not in prepared_paths:
                prepared_paths.append(path)

        if "triage" in selected:
            for sheet_number, start in enumerate(range(0, len(source_photos), 9), 1):
                sheet_photos = source_photos[start : start + 9]
                sheet_data = make_contact_sheet(
                    [(photo.photo_id, photo.data) for photo in sheet_photos]
                )
                sheet_path = write_prepared(
                    "triage",
                    sheet_number,
                    f"sheet-{sheet_number:04d}",
                    sheet_data,
                )
                track_prepared(sheet_path)
                assert client is not None or dry_run
                response, items = self._call(
                    client,  # type: ignore[arg-type]
                    "triage",
                    [photo.photo_id for photo in sheet_photos],
                    sheet_data,
                    sheet_path,
                    planned,
                    dry_run=dry_run,
                    mime_type="image/png",
                )
                if dry_run:
                    continue
                assert response is not None
                settings = settings_fingerprint(
                    model=self.model,
                    prompt=self._prompt("triage")[1],
                    generation_config=self.generation_config,
                    mime_type="image/png",
                )
                usage = _usage_dict(response)
                for offset, (photo_id, item) in enumerate(items):
                    values = _judgment_values(item)
                    if "bbox" in values:
                        bbox_by_photo[photo_id] = tuple(values["bbox"])  # type: ignore[assignment]
                    record = _record(
                        record_id=f"triage/sheet-{sheet_number:04d}/{offset:02d}",
                        photo_id=photo_id,
                        stage="triage",
                        read_kind="relative",
                        values=values,
                        model=self.model,
                        prompt_id_value=prompt_id("triage"),
                        settings=settings,
                        input_max_edge_px=DEFAULT_MAX_EDGE,
                        comparison_group=f"sheet-{sheet_number:04d}",
                        usage=usage,
                    )
                    triage_records.append(record)
                    raw_records.append(record)

        if "triage" in selected and not dry_run:
            finalists_ids = tuple(
                str(item["photo_id"])
                for item in select_top_records(triage_records, finalists)
            )
        else:
            finalists_ids = tuple(photo.photo_id for photo in source_photos[:finalists])

        if "dedicated" in selected:
            for ordinal, photo_id in enumerate(finalists_ids, 1):
                photo = photo_by_id[photo_id]
                prepared_data = prepare_dedicated(photo.data, max_edge=DEFAULT_MAX_EDGE)
                suffix = _prepared_suffix(prepared_data)
                path = write_prepared(
                    "dedicated",
                    ordinal,
                    photo_id,
                    prepared_data,
                    suffix=suffix,
                )
                track_prepared(path)
                assert client is not None or dry_run
                response, items = self._call(
                    client,  # type: ignore[arg-type]
                    "dedicated",
                    [photo_id],
                    prepared_data,
                    path,
                    planned,
                    dry_run=dry_run,
                    mime_type=mime_type_for_format(image_info(prepared_data).format),
                )
                if dry_run:
                    continue
                assert response is not None
                item_photo_id, item = items[0]
                values = _judgment_values(item)
                if "bbox" in values:
                    bbox_by_photo[item_photo_id] = tuple(values["bbox"])  # type: ignore[assignment]
                settings = settings_fingerprint(
                    model=self.model,
                    prompt=self._prompt("dedicated")[1],
                    generation_config=self.generation_config,
                    mime_type=mime_type_for_format(image_info(prepared_data).format),
                )
                record = _record(
                    record_id=f"dedicated/{ordinal:06d}",
                    photo_id=item_photo_id,
                    stage="dedicated",
                    read_kind="absolute",
                    values=values,
                    model=self.model,
                    prompt_id_value=prompt_id("dedicated"),
                    settings=settings,
                    input_max_edge_px=DEFAULT_MAX_EDGE,
                    usage=_usage_dict(response),
                )
                dedicated_records.append(record)
                raw_records.append(record)

        if "dedicated" in selected and not dry_run:
            selected_for_face = tuple(
                str(item["photo_id"])
                for item in select_top_records(dedicated_records, finalists)
            )
        else:
            selected_for_face = finalists_ids
        if bboxes:
            for photo_id, value in bboxes.items():
                parsed = _bbox(value)
                if parsed is None:
                    raise ReferenceContractError(f"invalid face bbox for {photo_id!r}")
                bbox_by_photo[photo_id] = parsed

        if "face" in selected:
            for ordinal, photo_id in enumerate(selected_for_face, 1):
                photo = photo_by_id[photo_id]
                bbox = bbox_by_photo.get(photo_id, (0.0, 0.0, 1.0, 1.0))
                try:
                    crop_data = prepare_face_crop(photo.data, bbox)
                    prepared_data = prepare_dedicated(crop_data, max_edge=DEFAULT_MAX_EDGE)
                    prepared_edge = image_info(prepared_data).long_edge
                except ImagePreparationError as exc:
                    raise ReferenceIOError(f"unable to prepare face crop for {photo_id}: {exc}") from exc
                path = write_prepared(
                    "face",
                    ordinal,
                    photo_id,
                    prepared_data,
                )
                track_prepared(path)
                assert client is not None or dry_run
                response, items = self._call(
                    client,  # type: ignore[arg-type]
                    "face",
                    [photo_id],
                    prepared_data,
                    path,
                    planned,
                    dry_run=dry_run,
                    mime_type="image/png",
                )
                if dry_run:
                    continue
                assert response is not None
                item_photo_id, item = items[0]
                values = _judgment_values(item)
                settings = settings_fingerprint(
                    model=self.model,
                    prompt=self._prompt("face")[1],
                    generation_config=self.generation_config,
                    mime_type="image/png",
                )
                record = _record(
                    record_id=f"face/{ordinal:06d}",
                    photo_id=item_photo_id,
                    stage="face",
                    read_kind="face_crop",
                    values=values,
                    model=self.model,
                    prompt_id_value=prompt_id("face"),
                    settings=settings,
                    input_max_edge_px=prepared_edge,
                    usage=_usage_dict(response),
                )
                raw_records.append(record)

        if "repeat" in selected:
            if not dedicated_records and not dry_run:
                raise ReferenceContractError(
                    "repeat pass requires dedicated records for ranking"
                )
            repeat_source = dedicated_records
            repeat_ids = (
                tuple(
                    str(item["photo_id"])
                    for item in select_top_records(repeat_source, repeat_top)
                )
                if not dry_run
                else tuple(photo.photo_id for photo in source_photos[:repeat_top])
            )
            repeat_prompt = self._prompt("repeat")[1]
            for ordinal, photo_id in enumerate(repeat_ids, 1):
                if photo_id not in photo_by_id:
                    raise ReferenceContractError(f"repeat photo is not present: {photo_id}")
                if dedicated_records:
                    prepared_data = prepare_dedicated(
                        photo_by_id[photo_id].data,
                        max_edge=DEFAULT_MAX_EDGE,
                    )
                else:
                    prepared_data = prepare_dedicated(
                        photo_by_id[photo_id].data,
                        max_edge=DEFAULT_MAX_EDGE,
                    )
                # Repeats use the same prepared bytes and therefore the same
                # provider MIME type on every read for this photo.
                repeat_mime_type = mime_type_for_format(
                    image_info(prepared_data).format
                )
                repeat_settings = settings_fingerprint(
                    model=self.model,
                    prompt=repeat_prompt,
                    generation_config=self.generation_config,
                    mime_type=repeat_mime_type,
                )
                # All repeats intentionally use one prepared byte string and
                # one prompt/configuration object per photo.
                repeat_group = f"repeat/{_safe_slug(photo_id)}"
                path = write_prepared(
                    "repeat",
                    ordinal,
                    photo_id,
                    prepared_data,
                    suffix=_prepared_suffix(prepared_data),
                )
                track_prepared(path)
                for repeat_index in range(repeat_count):
                    assert client is not None or dry_run
                    response, items = self._call(
                        client,  # type: ignore[arg-type]
                        "repeat",
                        [photo_id],
                        prepared_data,
                        path,
                        planned,
                        dry_run=dry_run,
                        mime_type=mime_type_for_format(image_info(prepared_data).format),
                    )
                    if dry_run:
                        continue
                    assert response is not None
                    item_photo_id, item = items[0]
                    values = _judgment_values(item)
                    raw_records.append(
                        _record(
                            record_id=f"repeat/{ordinal:06d}/{repeat_index:02d}",
                            photo_id=item_photo_id,
                            stage="repeat",
                            read_kind="absolute",
                            values=values,
                            model=self.model,
                            prompt_id_value=prompt_id("repeat"),
                            settings=repeat_settings,
                            input_max_edge_px=DEFAULT_MAX_EDGE,
                            repeat_group=repeat_group,
                            repeat_index=repeat_index,
                            usage=_usage_dict(response),
                        )
                    )

        if dry_run:
            return ReferenceRunResult(
                output_dir=output_dir,
                prepared_paths=tuple(prepared_paths),
                planned_calls=tuple(planned),
                dry_run=True,
            )

        document_value = {"schema_version": "1.0", "records": raw_records}
        document, issues = validate_document(document_value)
        if issues or document is None:
            detail = "; ".join(str(issue) for issue in issues)
            raise ReferenceContractError(f"generated judgments failed contract validation: {detail}")
        if output_dir is not None:
            try:
                judgments_path = output_dir / "judgments.json"
                judgments_path.write_text(
                    json.dumps(
                        document.to_dict(),
                        ensure_ascii=False,
                        sort_keys=False,
                        separators=(",", ":"),
                    )
                    + "\n",
                    encoding="utf-8",
                )
            except OSError as exc:
                raise ReferenceIOError(f"unable to write judgments.json: {exc}") from exc
            response_dir = output_dir / "responses"
            try:
                response_paths = tuple(sorted(path for path in response_dir.iterdir() if path.is_file()))
            except OSError as exc:
                raise ReferenceIOError(f"unable to list provider responses: {exc}") from exc
        else:
            response_paths = ()
        return ReferenceRunResult(
            records=document.records,
            document=document,
            output_dir=output_dir,
            prepared_paths=tuple(prepared_paths),
            response_paths=response_paths,
            planned_calls=tuple(planned),
            dry_run=False,
        )


def run_reference(
    photos: str | os.PathLike[str] | Mapping[str, Any] | Iterable[Any],
    model: str,
    *,
    output: str | os.PathLike[str] | None = None,
    passes: Sequence[str] = PASS_NAMES,
    finalists: int = DEFAULT_FINALISTS,
    repeat_top: int = DEFAULT_REPEAT_TOP,
    repeat_count: int = DEFAULT_REPEAT_COUNT,
    dry_run: bool = False,
    transport: gemini.Transport | None = None,
    client: GeminiClient | None = None,
    timeout: float = gemini.DEFAULT_TIMEOUT,
    max_attempts: int = gemini.DEFAULT_MAX_ATTEMPTS,
    sleeper: Callable[[float], None] | None = None,
    backoff: float = gemini.DEFAULT_BACKOFF_SECONDS,
    prompt_dir: str | os.PathLike[str] | None = None,
    generation_config: Mapping[str, Any] | None = None,
    bboxes: Mapping[str, Any] | None = None,
) -> ReferenceRunResult:
    """Convenience wrapper around :class:`ReferenceRunner`."""

    return ReferenceRunner(
        model,
        transport=transport,
        client=client,
        timeout=timeout,
        max_attempts=max_attempts,
        sleeper=sleeper,
        backoff=backoff,
        prompt_dir=prompt_dir,
        generation_config=generation_config,
    ).run(
        photos,
        output=output,
        passes=passes,
        finalists=finalists,
        repeat_top=repeat_top,
        repeat_count=repeat_count,
        dry_run=dry_run,
        bboxes=bboxes,
    )


run_passes = run_reference
run_reference_passes = run_reference
ReferencePassRunner = ReferenceRunner
run_pass = run_reference
run = run_reference


def planned_calls_for(
    photos: str | os.PathLike[str] | Mapping[str, Any] | Iterable[Any],
    *,
    model: str,
    passes: Sequence[str] = PASS_NAMES,
    finalists: int = DEFAULT_FINALISTS,
    repeat_top: int = DEFAULT_REPEAT_TOP,
    repeat_count: int = DEFAULT_REPEAT_COUNT,
) -> tuple[PlannedReferenceCall, ...]:
    """Build the dry-run plan without requiring an API key."""

    result = run_reference(
        photos,
        model=model,
        passes=passes,
        finalists=finalists,
        repeat_top=repeat_top,
        repeat_count=repeat_count,
        dry_run=True,
    )
    return result.planned_calls


__all__ = [
    "DEFAULT_FINALISTS",
    "DEFAULT_GENERATION_CONFIG",
    "DEFAULT_REPEAT_COUNT",
    "DEFAULT_REPEAT_TOP",
    "PASS_NAMES",
    "PROMPT_IDS",
    "PlannedReferenceCall",
    "ReferenceConfigurationError",
    "ReferenceContractError",
    "ReferenceError",
    "ReferenceIOError",
    "ReferencePhoto",
    "ReferenceProviderError",
    "ReferencePassRunner",
    "ReferenceRunResult",
    "ReferenceRunner",
    "prompt_id",
    "prompt_text",
    "planned_calls_for",
    "run_passes",
    "run_pass",
    "run",
    "run_reference",
    "run_reference_passes",
    "select_finalists",
    "select_repeat_photos",
    "select_top_records",
    "settings_fingerprint",
]
