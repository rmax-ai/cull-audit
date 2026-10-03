#!/usr/bin/env python3
"""Acquire and verify the licensed Wikimedia open-photo demo set.

The public commands are intentionally small:

* ``report`` validates a manifest without network access.
* ``fetch`` downloads manifest rows and verifies their checksums.
* ``verify`` checks an already downloaded directory without network access.

``discover`` and ``prepare`` are maintainer helpers used to build a manifest
from Wikimedia Commons.  They are kept here so the curation path uses the
same urllib transport as the documented acquisition command.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import hashlib
import html
import json
from pathlib import Path
import re
import sys
import tempfile
import time
from typing import Any, Callable, Mapping, Sequence, TextIO
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import Request, urlopen


MAX_ASSET_BYTES = 25 * 1024 * 1024
DOWNLOAD_DELAY_SECONDS = 1.0
RETRY_ATTEMPTS = 4
RETRY_BASE_DELAY_SECONDS = 5.0
REQUEST_TIMEOUT_SECONDS = 60
USER_AGENT = "cull-audit-open-demo/1.0 (Wikimedia Commons acquisition)"
WIKIMEDIA_API = "https://commons.wikimedia.org/w/api.php"
SUPPORTED_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"})
ALLOWED_LICENSES = frozenset(
    {
        "CC0",
        "CC0 1.0",
        "CC BY 2.0",
        "CC BY 3.0",
        "CC BY 4.0",
        "CC BY-SA 2.0",
        "CC BY-SA 3.0",
        "CC BY-SA 4.0",
        "Public Domain",
    }
)
MANIFEST_FIELDS = ("version", "source", "set", "assets")
SET_FIELDS = ("title", "event", "selection_note", "acquired")
ASSET_FIELDS = (
    "file",
    "commons_page",
    "download_url",
    "creator",
    "license",
    "license_url",
    "attribution",
    "bytes",
    "sha256",
    "redistribution",
)
ASSET_STRING_FIELDS = frozenset(
    {
        "file",
        "commons_page",
        "download_url",
        "creator",
        "license",
        "license_url",
        "attribution",
        "sha256",
    }
)
FILE_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]*\.(?:jpg|jpeg|png|webp|tif|tiff)$"
)
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass
class ManifestDiagnostics:
    """Stable, human-readable manifest validation counters."""

    assets: int = 0
    missing: int = 0
    duplicates: int = 0
    disallowed: int = 0
    unsorted: int = 0
    invalid: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def problems(self) -> int:
        return (
            self.missing
            + self.duplicates
            + self.disallowed
            + self.unsorted
            + self.invalid
        )

    def summary(self) -> str:
        return (
            f"assets={self.assets} missing={self.missing} "
            f"duplicates={self.duplicates} disallowed={self.disallowed} "
            f"unsorted={self.unsorted} invalid={self.invalid}"
        )


@dataclass
class VerificationResult:
    """Result of checking files against one valid manifest."""

    assets: int
    verified: int = 0
    missing: int = 0
    mismatched: int = 0
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"assets={self.assets} verified={self.verified} "
            f"missing={self.missing} mismatched={self.mismatched}"
        )


@dataclass
class FetchResult:
    """Result of a sequential fetch."""

    assets: int
    fetched: int = 0
    already: int = 0
    failures: list[str] = field(default_factory=list)
    bytes_downloaded: int = 0

    def summary(self) -> str:
        return (
            f"assets={self.assets} fetched={self.fetched} already={self.already} "
            f"failures={len(self.failures)} bytes={self.bytes_downloaded}"
        )


def _is_non_empty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_https_url(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlsplit(value)
    return parsed.scheme == "https" and bool(parsed.netloc)


def _add_error(diagnostics: ManifestDiagnostics, message: str) -> None:
    diagnostics.errors.append(message)


def inspect_manifest(manifest: Any) -> ManifestDiagnostics:
    """Validate a decoded manifest and return deterministic diagnostics."""

    diagnostics = ManifestDiagnostics()
    if not isinstance(manifest, dict):
        diagnostics.invalid += 1
        _add_error(diagnostics, "manifest root must be an object")
        return diagnostics

    for name in MANIFEST_FIELDS:
        if name not in manifest or manifest[name] is None:
            diagnostics.missing += 1
            _add_error(diagnostics, f"manifest missing {name}")

    if manifest.get("version") != "1.0":
        diagnostics.invalid += 1
        _add_error(diagnostics, "manifest version must be 1.0")
    if manifest.get("source") != "wikimedia-commons":
        diagnostics.invalid += 1
        _add_error(diagnostics, "manifest source must be wikimedia-commons")

    metadata = manifest.get("set")
    if not isinstance(metadata, dict):
        diagnostics.missing += 1
        _add_error(diagnostics, "manifest set must be an object")
    else:
        for name in SET_FIELDS:
            if not _is_non_empty(metadata.get(name)):
                diagnostics.missing += 1
                _add_error(diagnostics, f"set missing {name}")
        acquired = metadata.get("acquired")
        if _is_non_empty(acquired) and DATE_PATTERN.fullmatch(acquired) is None:
            diagnostics.invalid += 1
            _add_error(diagnostics, "set acquired must be YYYY-MM-DD")

    assets = manifest.get("assets")
    if not isinstance(assets, list):
        diagnostics.invalid += 1
        _add_error(diagnostics, "manifest assets must be an array")
        return diagnostics

    diagnostics.assets = len(assets)
    seen_files: set[str] = set()
    seen_pages: set[str] = set()
    file_names: list[str] = []

    for index, asset in enumerate(assets):
        prefix = f"assets[{index}]"
        if not isinstance(asset, dict):
            diagnostics.missing += 1
            _add_error(diagnostics, f"{prefix} must be an object")
            continue

        for name in ASSET_FIELDS:
            if name not in asset or asset[name] is None:
                diagnostics.missing += 1
                _add_error(diagnostics, f"{prefix} missing {name}")
            elif isinstance(asset[name], str) and not asset[name].strip():
                diagnostics.missing += 1
                _add_error(diagnostics, f"{prefix} empty {name}")
            elif (
                name in ASSET_STRING_FIELDS
                and not isinstance(asset[name], str)
            ):
                diagnostics.invalid += 1
                _add_error(diagnostics, f"{prefix} {name} must be a string")

        file_name = asset.get("file")
        if isinstance(file_name, str):
            file_names.append(file_name)
            if FILE_PATTERN.fullmatch(file_name) is None:
                diagnostics.invalid += 1
                _add_error(diagnostics, f"{prefix} has an unsafe file name")
            elif not file_name.isascii():
                diagnostics.invalid += 1
                _add_error(diagnostics, f"{prefix} file name is not ASCII")
            if file_name in seen_files:
                diagnostics.duplicates += 1
                _add_error(diagnostics, f"{prefix} duplicates file {file_name}")
            seen_files.add(file_name)

        commons_page = asset.get("commons_page")
        if isinstance(commons_page, str):
            if not commons_page.startswith("https://commons.wikimedia.org/wiki/File:"):
                diagnostics.invalid += 1
                _add_error(diagnostics, f"{prefix} has an invalid Commons page")
            if commons_page in seen_pages:
                diagnostics.duplicates += 1
                _add_error(diagnostics, f"{prefix} duplicates commons_page")
            seen_pages.add(commons_page)

        if not _is_https_url(asset.get("download_url")):
            diagnostics.invalid += 1
            _add_error(diagnostics, f"{prefix} download_url must be HTTPS")
        if not _is_https_url(asset.get("license_url")):
            diagnostics.invalid += 1
            _add_error(diagnostics, f"{prefix} license_url must be HTTPS")

        license_name = asset.get("license")
        if _is_non_empty(license_name) and license_name not in ALLOWED_LICENSES:
            diagnostics.disallowed += 1
            _add_error(diagnostics, f"{prefix} has disallowed license")

        byte_count = asset.get("bytes")
        if (
            isinstance(byte_count, bool)
            or not isinstance(byte_count, int)
            or byte_count <= 0
            or byte_count > MAX_ASSET_BYTES
        ):
            diagnostics.invalid += 1
            _add_error(diagnostics, f"{prefix} has invalid bytes")

        digest = asset.get("sha256")
        if not isinstance(digest, str) or SHA256_PATTERN.fullmatch(digest) is None:
            diagnostics.invalid += 1
            _add_error(diagnostics, f"{prefix} has invalid sha256")

        if not isinstance(asset.get("redistribution"), bool):
            diagnostics.invalid += 1
            _add_error(diagnostics, f"{prefix} redistribution must be boolean")

    if file_names and file_names != sorted(file_names):
        diagnostics.unsorted = 1
        _add_error(diagnostics, "assets are not sorted by file")

    return diagnostics


def load_manifest(path: Path) -> dict[str, Any]:
    """Load a UTF-8 JSON manifest."""

    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError("manifest root must be an object")
    return value


def _load_and_report(path: Path) -> tuple[dict[str, Any] | None, ManifestDiagnostics]:
    try:
        manifest = load_manifest(path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        diagnostics = ManifestDiagnostics(invalid=1)
        _add_error(diagnostics, f"unable to load manifest: {exc}")
        return None, diagnostics
    return manifest, inspect_manifest(manifest)


def report_manifest(path: Path, stream: TextIO = sys.stdout) -> int:
    """Print a manifest report and return a process-style status code."""

    _, diagnostics = _load_and_report(path)
    print(diagnostics.summary(), file=stream)
    if diagnostics.problems:
        for error in diagnostics.errors:
            print(f"report: {error}", file=sys.stderr)
        return 1
    return 0


def _sha256_file(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    byte_count = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            byte_count += len(chunk)
            digest.update(chunk)
    return byte_count, digest.hexdigest()


def verify_assets(manifest: Mapping[str, Any], directory: Path) -> VerificationResult:
    """Verify all rows in a manifest that has already passed validation."""

    assets = manifest.get("assets", [])
    result = VerificationResult(assets=len(assets))
    for asset in assets:
        file_name = asset["file"]
        path = directory / file_name
        if not path.is_file():
            result.missing += 1
            result.errors.append(f"{file_name}: missing")
            continue
        try:
            byte_count, digest = _sha256_file(path)
        except OSError as exc:
            result.mismatched += 1
            result.errors.append(f"{file_name}: unable to read ({exc})")
            continue
        if byte_count != asset["bytes"] or digest != asset["sha256"]:
            result.mismatched += 1
            result.errors.append(f"{file_name}: bytes or sha256 mismatch")
            continue
        result.verified += 1
    return result


def verify_manifest(path: Path, directory: Path, stream: TextIO = sys.stdout) -> int:
    """Validate a manifest and verify its corresponding local files."""

    manifest, diagnostics = _load_and_report(path)
    if manifest is None or diagnostics.problems:
        print("verify: invalid manifest", file=stream)
        for error in diagnostics.errors:
            print(f"verify: {error}", file=sys.stderr)
        return 1
    result = verify_assets(manifest, directory)
    print(result.summary(), file=stream)
    if result.errors:
        for error in result.errors:
            print(f"verify: {error}", file=sys.stderr)
        return 1
    return 0


def _open_request(request: Request, opener: Callable[..., Any] | None) -> Any:
    if opener is None:
        return urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS)
    return opener(request)


def _retry_delay(error: HTTPError, attempt: int) -> float:
    retry_after = error.headers.get("Retry-After")
    if retry_after:
        try:
            return max(float(retry_after), RETRY_BASE_DELAY_SECONDS)
        except ValueError:
            pass
    return RETRY_BASE_DELAY_SECONDS * (2**attempt)


def _open_request_with_retry(
    request: Request,
    opener: Callable[..., Any] | None,
) -> Any:
    for attempt in range(RETRY_ATTEMPTS):
        try:
            return _open_request(request, opener)
        except HTTPError as exc:
            retryable = exc.code == 429 or 500 <= exc.code < 600
            if not retryable or attempt == RETRY_ATTEMPTS - 1:
                raise
            time.sleep(_retry_delay(exc, attempt))
    raise AssertionError("request retry loop did not return or raise")


def _download_to_path(
    url: str,
    destination: Path,
    *,
    expected_bytes: int | None = None,
    expected_sha256: str | None = None,
    opener: Callable[..., Any] | None = None,
) -> tuple[int, str]:
    """Download one URL to a temporary sibling, then atomically install it."""

    request = Request(
        url,
        headers={
            "Accept": "image/*",
            "User-Agent": USER_AGENT,
        },
    )
    temporary_path: Path | None = None
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{destination.name}.",
            suffix=".part",
            dir=destination.parent,
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            digest = hashlib.sha256()
            byte_count = 0
            with _open_request_with_retry(request, opener) as response:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    byte_count += len(chunk)
                    if byte_count > MAX_ASSET_BYTES:
                        raise ValueError(
                            f"download exceeds {MAX_ASSET_BYTES} byte limit"
                        )
                    temporary.write(chunk)
                    digest.update(chunk)
            checksum = digest.hexdigest()
        if expected_bytes is not None and byte_count != expected_bytes:
            raise ValueError(
                f"byte count {byte_count} does not match expected {expected_bytes}"
            )
        if expected_sha256 is not None and checksum != expected_sha256:
            raise ValueError("sha256 does not match manifest")
        if temporary_path is None:
            raise RuntimeError("download did not create a temporary file")
        temporary_path.replace(destination)
        temporary_path = None
        return byte_count, checksum
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass


def _existing_matches(path: Path, expected_bytes: int, expected_sha256: str) -> bool:
    """Return True when an existing file matches the manifest record."""

    try:
        if not path.is_file() or path.stat().st_size != expected_bytes:
            return False
        byte_count, digest = _sha256_file(path)
    except OSError:
        return False
    return byte_count == expected_bytes and digest == expected_sha256


def fetch_assets(
    manifest: Mapping[str, Any],
    directory: Path,
    *,
    limit: int | None = None,
    opener: Callable[..., Any] | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    delay: float = DOWNLOAD_DELAY_SECONDS,
) -> FetchResult:
    """Fetch manifest rows in sorted order and verify each download.

    The fetch is resumable: a file that already exists with the recorded byte
    count and SHA-256 is left untouched and counted as ``already``.  Only
    missing or mismatched files cause a network request, so a fetch throttled
    part-way through (Wikimedia can return 429 with Retry-After under bursty
    load) can simply be repeated until the set reports complete.
    """

    assets = list(manifest["assets"])
    selected = assets if limit is None else assets[:limit]
    result = FetchResult(assets=len(selected))
    directory.mkdir(parents=True, exist_ok=True)
    for asset in selected:
        file_name = asset["file"]
        destination = directory / file_name
        if _existing_matches(destination, asset["bytes"], asset["sha256"]):
            result.already += 1
            continue
        if result.fetched or result.failures:
            sleep_fn(delay)
        try:
            byte_count, _ = _download_to_path(
                asset["download_url"],
                destination,
                expected_bytes=asset["bytes"],
                expected_sha256=asset["sha256"],
                opener=opener,
            )
        except (OSError, HTTPError, URLError, ValueError, RuntimeError) as exc:
            result.failures.append(f"{file_name}: {exc}")
            continue
        result.fetched += 1
        result.bytes_downloaded += byte_count
    return result


def fetch_manifest(
    path: Path,
    directory: Path,
    *,
    limit: int | None = None,
    stream: TextIO = sys.stdout,
) -> int:
    """Fetch a manifest from the command line."""

    manifest, diagnostics = _load_and_report(path)
    if manifest is None or diagnostics.problems:
        print("fetch: invalid manifest", file=stream)
        for error in diagnostics.errors:
            print(f"fetch: {error}", file=sys.stderr)
        return 1
    result = fetch_assets(manifest, directory, limit=limit)
    print(result.summary(), file=stream)
    if result.failures:
        for error in result.failures:
            print(f"fetch: {error}", file=sys.stderr)
        return 1
    return 0


def _clean_metadata(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("value", "")
    if not isinstance(value, str):
        return ""
    value = html.unescape(value)
    value = re.sub(r"<[^>]*>", "", value)
    return " ".join(value.split())


def _api_json(
    parameters: Mapping[str, str],
    *,
    opener: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    query = urlencode(parameters)
    request = Request(
        f"{WIKIMEDIA_API}?{query}",
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
    )
    with _open_request(request, opener) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Wikimedia API returned a non-object response")
    return payload


def _commons_page(title: str) -> str:
    return "https://commons.wikimedia.org/wiki/" + quote(
        title.replace(" ", "_"), safe=":/()'!,"
    )


def _candidate_from_page(page: Mapping[str, Any]) -> dict[str, Any] | None:
    info_values = page.get("imageinfo")
    if not isinstance(info_values, list) or not info_values:
        return None
    info = info_values[0]
    if not isinstance(info, dict):
        return None
    title = page.get("title")
    url = info.get("url")
    mime = info.get("mime")
    size = info.get("size")
    if not isinstance(title, str) or not isinstance(url, str):
        return None
    if not isinstance(mime, str) or not mime.startswith("image/"):
        return None
    if not isinstance(size, int) or size <= 0 or size > MAX_ASSET_BYTES:
        return None
    suffix = Path(urlsplit(url).path).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        return None

    metadata = info.get("extmetadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
    creator = _clean_metadata(metadata.get("Artist"))
    license_name = _clean_metadata(metadata.get("LicenseShortName"))
    license_url = _clean_metadata(metadata.get("LicenseUrl"))
    if not creator or license_name not in ALLOWED_LICENSES or not _is_https_url(license_url):
        return None
    title_for_attribution = title.removeprefix("File:").replace("_", " ")
    return {
        "file_title": title,
        "title": title_for_attribution,
        "commons_page": _commons_page(title),
        "download_url": url,
        "creator": creator,
        "license": license_name,
        "license_url": license_url,
        "attribution": (
            f'{creator}, "{title_for_attribution}", via Wikimedia Commons, '
            f"{license_name}"
        ),
        "bytes": size,
        "mime": mime,
        "extension": suffix,
    }


def discover_candidates(
    category: str,
    *,
    limit: int | None = None,
    creator_filter: str | None = None,
    opener: Callable[..., Any] | None = None,
) -> list[dict[str, Any]]:
    """Read clear-license image metadata from one Commons category."""

    category_title = category
    if not category_title.startswith("Category:"):
        category_title = f"Category:{category_title}"
    candidates: list[dict[str, Any]] = []
    continuation: str | None = None
    while True:
        parameters = {
            "action": "query",
            "generator": "categorymembers",
            "gcmtitle": category_title,
            "gcmtype": "file",
            "gcmlimit": "500",
            "prop": "imageinfo",
            "iiprop": "url|size|mime|extmetadata",
            "iilimit": "1",
            "format": "json",
            "formatversion": "2",
        }
        if continuation:
            parameters["gcmcontinue"] = continuation
        payload = _api_json(parameters, opener=opener)
        query = payload.get("query", {})
        pages = query.get("pages", []) if isinstance(query, dict) else []
        if isinstance(pages, list):
            for page in pages:
                if not isinstance(page, dict):
                    continue
                candidate = _candidate_from_page(page)
                if candidate is None:
                    continue
                if (
                    creator_filter
                    and creator_filter.casefold() not in candidate["creator"].casefold()
                ):
                    continue
                candidates.append(candidate)
        if limit is not None and len(candidates) >= limit:
            break
        continuation_data = payload.get("continue")
        if not isinstance(continuation_data, dict):
            break
        next_value = continuation_data.get("gcmcontinue")
        if not isinstance(next_value, str) or not next_value:
            break
        continuation = next_value

    candidates.sort(key=lambda item: (item["file_title"], item["download_url"]))
    return candidates if limit is None else candidates[:limit]


def search_commons(
    query: str,
    *,
    limit: int = 50,
    opener: Callable[..., Any] | None = None,
) -> list[str]:
    """Search Wikimedia Commons for category names used by curation."""

    payload = _api_json(
        {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srnamespace": "14",
            "srlimit": str(limit),
            "format": "json",
            "formatversion": "2",
        },
        opener=opener,
    )
    query_data = payload.get("query", {})
    results = query_data.get("search", []) if isinstance(query_data, dict) else []
    titles = [
        item["title"]
        for item in results
        if isinstance(item, dict) and isinstance(item.get("title"), str)
    ]
    return sorted(titles)


def search_command(query: str, output: Path | None, limit: int) -> int:
    try:
        titles = search_commons(query, limit=limit)
        if output is None:
            for title in titles:
                print(title)
        else:
            _write_json(output, {"query": query, "categories": titles})
            print(f"categories={len(titles)} output={output}")
    except (OSError, HTTPError, URLError, ValueError, json.JSONDecodeError) as exc:
        print(f"search: {exc}", file=sys.stderr)
        return 1
    return 0


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def discover_command(
    category: str,
    output: Path,
    *,
    limit: int | None = None,
    creator_filter: str | None = None,
) -> int:
    try:
        candidates = discover_candidates(
            category,
            limit=limit,
            creator_filter=creator_filter,
        )
        _write_json(
            output,
            {
                "source": "wikimedia-commons",
                "category": category,
                "assets": candidates,
            },
        )
    except (OSError, HTTPError, URLError, ValueError, json.JSONDecodeError) as exc:
        print(f"discover: {exc}", file=sys.stderr)
        return 1
    print(f"candidates={len(candidates)} output={output}")
    return 0


def _download_candidate(
    candidate: Mapping[str, Any],
    destination: Path,
    *,
    opener: Callable[..., Any] | None = None,
) -> tuple[int, str]:
    return _download_to_path(candidate["download_url"], destination, opener=opener)


def prepare_manifest(
    candidates_path: Path,
    manifest_path: Path,
    output_directory: Path,
    *,
    title: str,
    event: str,
    selection_note: str,
    acquired: str,
    count: int,
    creator_filter: str | None = None,
) -> int:
    """Download selected candidates and write a checksum-complete manifest."""

    try:
        with candidates_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        candidates = payload["assets"]
        if not isinstance(candidates, list):
            raise ValueError("candidate assets must be an array")
        selected: list[Mapping[str, Any]] = []
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            if (
                creator_filter
                and creator_filter.casefold() not in candidate["creator"].casefold()
            ):
                continue
            selected.append(candidate)
        selected.sort(key=lambda item: (item["file_title"], item["download_url"]))
        selected = selected[:count]
        if len(selected) != count:
            raise ValueError(f"requested {count} candidates but found {len(selected)}")

        assets: list[dict[str, Any]] = []
        total_bytes = 0
        for index, candidate in enumerate(selected, start=1):
            if index > 1:
                time.sleep(DOWNLOAD_DELAY_SECONDS)
            extension = candidate["extension"]
            file_name = f"{index:04d}{extension}"
            destination = output_directory / file_name
            byte_count, checksum = _download_candidate(candidate, destination)
            asset = {
                "file": file_name,
                "commons_page": candidate["commons_page"],
                "download_url": candidate["download_url"],
                "creator": candidate["creator"],
                "license": candidate["license"],
                "license_url": candidate["license_url"],
                "attribution": candidate["attribution"],
                "bytes": byte_count,
                "sha256": checksum,
                "redistribution": False,
            }
            assets.append(asset)
            total_bytes += byte_count
        manifest = {
            "version": "1.0",
            "source": "wikimedia-commons",
            "set": {
                "title": title,
                "event": event,
                "selection_note": selection_note,
                "acquired": acquired,
            },
            "assets": assets,
        }
        diagnostics = inspect_manifest(manifest)
        if diagnostics.problems:
            raise ValueError("; ".join(diagnostics.errors))
        _write_json(manifest_path, manifest)
    except (OSError, HTTPError, URLError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"prepare: {exc}", file=sys.stderr)
        return 1
    print(
        f"prepared={len(assets)} bytes={total_bytes} manifest={manifest_path} "
        f"directory={output_directory}"
    )
    return 0


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    report_parser = subparsers.add_parser("report", help="validate a manifest")
    report_parser.add_argument("--manifest", type=Path, required=True)

    verify_parser = subparsers.add_parser(
        "verify", help="verify downloaded files against a manifest"
    )
    verify_parser.add_argument("--manifest", type=Path, required=True)
    verify_parser.add_argument("--dir", type=Path, required=True)

    fetch_parser = subparsers.add_parser("fetch", help="download manifest assets")
    fetch_parser.add_argument("--manifest", type=Path, required=True)
    fetch_parser.add_argument("--out", type=Path, required=True)
    fetch_parser.add_argument("--limit", type=_positive_int)

    discover_parser = subparsers.add_parser(
        "discover", help="discover clear-license files in a Commons category"
    )
    discover_parser.add_argument("--category", required=True)
    discover_parser.add_argument("--out", type=Path, required=True)
    discover_parser.add_argument("--limit", type=_positive_int)
    discover_parser.add_argument("--creator")

    search_parser = subparsers.add_parser(
        "search", help="search Commons category names"
    )
    search_parser.add_argument("--query", required=True)
    search_parser.add_argument("--out", type=Path)
    search_parser.add_argument("--limit", type=_positive_int, default=50)

    prepare_parser = subparsers.add_parser(
        "prepare", help="download candidates and create a checksum manifest"
    )
    prepare_parser.add_argument("--candidates", type=Path, required=True)
    prepare_parser.add_argument("--manifest", type=Path, required=True)
    prepare_parser.add_argument("--out", type=Path, required=True)
    prepare_parser.add_argument("--title", required=True)
    prepare_parser.add_argument("--event", required=True)
    prepare_parser.add_argument("--selection-note", required=True)
    prepare_parser.add_argument("--acquired", required=True)
    prepare_parser.add_argument("--count", type=_positive_int, required=True)
    prepare_parser.add_argument("--creator")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "report":
        return report_manifest(args.manifest)
    if args.command == "verify":
        return verify_manifest(args.manifest, args.dir)
    if args.command == "fetch":
        return fetch_manifest(args.manifest, args.out, limit=args.limit)
    if args.command == "discover":
        return discover_command(
            args.category,
            args.out,
            limit=args.limit,
            creator_filter=args.creator,
        )
    if args.command == "search":
        return search_command(args.query, args.out, args.limit)
    if args.command == "prepare":
        return prepare_manifest(
            args.candidates,
            args.manifest,
            args.out,
            title=args.title,
            event=args.event,
            selection_note=args.selection_note,
            acquired=args.acquired,
            count=args.count,
            creator_filter=args.creator,
        )
    raise AssertionError(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
