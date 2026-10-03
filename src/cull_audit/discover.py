"""Read-only discovery of supported photos under a directory."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
from typing import Iterator

from PIL import Image


SUPPORTED_EXTENSIONS = frozenset(
    {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}
)
HASH_CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True, slots=True)
class PhotoEntry:
    """A decoded photo and its content identity."""

    path: str
    sha256: str
    size: int

    @property
    def photo_id(self) -> str:
        """Return the stable ID used by judgment records."""
        return self.path

    @property
    def relative_path(self) -> str:
        """Return the POSIX relative path represented by this entry."""
        return self.path


@dataclass(frozen=True, slots=True)
class DiscoveryResult:
    """Deterministic discovery output.

    ``entries`` contains only files with a supported suffix that Pillow could
    decode.  ``unreadable`` contains stable relative IDs for supported files
    that could not be decoded or hashed.  Duplicate groups contain the
    relative IDs of entries with identical bytes.
    """

    entries: tuple[PhotoEntry, ...]
    unreadable: tuple[str, ...]
    duplicate_groups: tuple[tuple[str, ...], ...]

    @property
    def supported(self) -> tuple[PhotoEntry, ...]:
        """Alias for callers that name the successful entries ``supported``."""
        return self.entries

    @property
    def photos(self) -> tuple[PhotoEntry, ...]:
        """Alias for callers that name the successful entries ``photos``."""
        return self.entries

    @property
    def duplicates(self) -> tuple[tuple[str, ...], ...]:
        """Alias for the duplicate-byte groups."""
        return self.duplicate_groups


def _iter_regular_files(root: Path) -> Iterator[Path]:
    """Yield regular, non-symlink files below ``root``.

    ``os.walk`` does not follow symlinked directories by default.  Removing
    those directory names explicitly makes that policy visible and also
    prevents a later change to the walk options from changing it silently.
    """

    for directory, dirnames, filenames in os.walk(
        root, topdown=True, followlinks=False
    ):
        directory_path = Path(directory)
        dirnames[:] = sorted(
            name
            for name in dirnames
            if not (directory_path / name).is_symlink()
        )
        for name in sorted(filenames):
            path = directory_path / name
            if path.is_symlink():
                continue
            try:
                if path.is_file():
                    yield path
            except OSError:
                # A disappearing or inaccessible non-photo is not a
                # discovery result.  Supported files are handled below,
                # where the stable ID is available for diagnostics.
                continue


def _can_decode(path: Path) -> None:
    """Raise if Pillow cannot verify and decode ``path``."""

    # ``verify`` catches truncated files without materializing the image.
    # Opening it again is required before ``load`` and catches decoders that
    # only report an error while reading pixel data.
    with Image.open(path) as image:
        image.verify()
    with Image.open(path) as image:
        image.load()


def _hash_file(path: Path) -> tuple[str, int]:
    """Return the SHA-256 digest and byte count for ``path``."""

    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while chunk := handle.read(HASH_CHUNK_SIZE):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _relative_id(path: Path, root: Path) -> str:
    """Convert a discovered path to its normalized POSIX photo ID."""

    return path.relative_to(root).as_posix()


def discover(photo_root: str | os.PathLike[str]) -> DiscoveryResult:
    """Discover decodable photos below ``photo_root`` without mutating it.

    Supported suffix matching is case-insensitive.  Files with a supported
    suffix that Pillow cannot read are returned in ``unreadable`` rather than
    raising an image-decoding error.  The root must already be a directory.
    """

    root = Path(photo_root)
    if not root.is_dir():
        raise NotADirectoryError(f"photo root is not a directory: {photo_root}")

    candidates = sorted(
        (
            path
            for path in _iter_regular_files(root)
            if path.suffix.lower() in SUPPORTED_EXTENSIONS
        ),
        key=lambda path: _relative_id(path, root),
    )

    entries: list[PhotoEntry] = []
    unreadable: list[str] = []
    for path in candidates:
        relative_id = _relative_id(path, root)
        try:
            _can_decode(path)
            sha256, size = _hash_file(path)
        except Exception:
            # Pillow uses several exception types for malformed data,
            # depending on the image plugin.  Discovery reports all ordinary
            # read/decode failures uniformly, while still allowing process
            # control exceptions such as KeyboardInterrupt through.
            unreadable.append(relative_id)
            continue
        entries.append(PhotoEntry(relative_id, sha256, size))

    bytes_to_paths: dict[str, list[str]] = {}
    for entry in entries:
        bytes_to_paths.setdefault(entry.sha256, []).append(entry.path)
    duplicate_groups = tuple(
        sorted(
            (
                tuple(paths)
                for paths in bytes_to_paths.values()
                if len(paths) > 1
            ),
        )
    )
    return DiscoveryResult(
        entries=tuple(entries),
        unreadable=tuple(unreadable),
        duplicate_groups=duplicate_groups,
    )


discover_photos = discover
