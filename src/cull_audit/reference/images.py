"""Deterministic image preparation for the optional reference runner.

The reference runner deliberately keeps image preparation separate from
provider calls.  Every function in this module either returns bytes or a
small description of bytes; it never mutates the source image.  PNG encoding
uses fixed settings so prepared inputs can be hashed and compared across
runs.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from io import BytesIO
import math
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageOps


CONTACT_SHEET_COLUMNS = 3
CONTACT_SHEET_ROWS = 3
CONTACT_SHEET_SIZE = 512
CONTACT_SHEET_COUNT = CONTACT_SHEET_COLUMNS * CONTACT_SHEET_ROWS
DEFAULT_MAX_EDGE = 1536
FACE_MARGIN_RATIO = 0.40


class ImagePreparationError(ValueError):
    """Raised when an image or normalized bounding box is invalid."""


@dataclass(frozen=True, slots=True)
class ImageInput:
    """An image and its stable identifier.

    The dataclass is convenient for callers, but all public preparation
    functions also accept mappings and ``(photo_id, bytes-or-path)`` pairs.
    """

    photo_id: str
    data: bytes


@dataclass(frozen=True, slots=True)
class ImageInfo:
    """Decoded metadata for a prepared image."""

    width: int
    height: int
    format: str
    mime_type: str

    @property
    def long_edge(self) -> int:
        return max(self.width, self.height)


def _as_bytes(value: bytes | bytearray | memoryview | str | Path | Image.Image) -> bytes:
    """Read one image source without changing an already supplied byte string."""

    if isinstance(value, bytes):
        return value
    if isinstance(value, (bytearray, memoryview)):
        return bytes(value)
    if isinstance(value, (str, Path)):
        try:
            return Path(value).read_bytes()
        except OSError as exc:
            raise ImagePreparationError(f"unable to read image {value}: {exc}") from exc
    if isinstance(value, Image.Image):
        output = BytesIO()
        _save_png(value.convert("RGBA"), output)
        return output.getvalue()
    raise ImagePreparationError("image input must be bytes, a path, or a Pillow image")


def _open(data: bytes) -> Image.Image:
    """Decode an image and materialize it before the source stream closes."""

    try:
        with Image.open(BytesIO(data)) as source:
            image = ImageOps.exif_transpose(source)
            return image.copy()
    except Exception as exc:
        raise ImagePreparationError(f"unable to decode image: {exc}") from exc


def image_info(value: bytes | bytearray | memoryview | str | Path) -> ImageInfo:
    """Return dimensions, format, and MIME type for an image source."""

    data = _as_bytes(value)
    try:
        with Image.open(BytesIO(data)) as image:
            image_format = (image.format or "PNG").upper()
            width, height = image.size
    except Exception as exc:
        raise ImagePreparationError(f"unable to inspect image: {exc}") from exc
    return ImageInfo(
        width=width,
        height=height,
        format=image_format,
        mime_type=mime_type_for_format(image_format),
    )


def mime_type_for_format(image_format: str) -> str:
    """Map a Pillow format name to the MIME type sent to the provider."""

    value = str(image_format).upper()
    return {
        "JPEG": "image/jpeg",
        "JPG": "image/jpeg",
        "PNG": "image/png",
        "WEBP": "image/webp",
        "TIFF": "image/tiff",
        "TIF": "image/tiff",
        "GIF": "image/gif",
    }.get(value, "image/png")


def _save_png(image: Image.Image, output: BytesIO) -> None:
    """Write a metadata-free deterministic PNG."""

    image.save(
        output,
        format="PNG",
        optimize=False,
        compress_level=9,
    )


def _save_prepared(image: Image.Image, output_format: str) -> bytes:
    """Encode a resized/cropped image with deterministic format settings."""

    output = BytesIO()
    normalized = image
    format_name = output_format.upper()
    if format_name in {"JPEG", "JPG"}:
        if normalized.mode not in {"RGB", "L", "CMYK"}:
            background = Image.new("RGB", normalized.size, (255, 255, 255))
            if "A" in normalized.getbands():
                background.paste(normalized, mask=normalized.getchannel("A"))
            else:
                background.paste(normalized.convert("RGB"))
            normalized = background
        normalized.save(
            output,
            format="JPEG",
            quality=95,
            optimize=False,
            progressive=False,
            subsampling=0,
        )
    elif format_name == "WEBP":
        normalized.save(
            output,
            format="WEBP",
            quality=95,
            method=6,
            lossless=True,
        )
    else:
        _save_png(normalized, output)
    return output.getvalue()


def _iter_image_inputs(
    images: Mapping[str, bytes | bytearray | memoryview | str | Path]
    | Iterable[ImageInput | tuple[str, Any] | Mapping[str, Any]],
) -> list[ImageInput]:
    """Normalize supported image collections and sort them by photo ID."""

    values: list[ImageInput] = []
    if isinstance(images, Mapping):
        iterable: Iterable[Any] = images.items()
    else:
        iterable = images
    for item in iterable:
        if isinstance(item, ImageInput):
            values.append(ImageInput(item.photo_id, bytes(item.data)))
            continue
        if isinstance(item, (str, Path)):
            path = Path(item)
            values.append(ImageInput(path.as_posix(), _as_bytes(path)))
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
            raise ImagePreparationError("each image input needs a non-empty photo_id")
        if source is None:
            raise ImagePreparationError(f"image input {photo_id!r} has no image data")
        values.append(ImageInput(photo_id, _as_bytes(source)))
    return sorted(values, key=lambda item: item.photo_id)


def _draw_label(
    draw: ImageDraw.ImageDraw,
    cell_x: int,
    cell_y: int,
    position: int,
    photo_id: str,
) -> None:
    """Draw a high-contrast, in-frame position and ID label."""

    # ``load_default`` is bundled with Pillow and avoids a machine-dependent
    # font lookup.  The position number is the primary stable label; the
    # short ID makes a sheet usable without a separate manifest.
    font = ImageFont.load_default()
    safe_photo_id = photo_id.encode("ascii", "replace").decode("ascii")
    label = f"{position:02d}  {safe_photo_id}"
    left = cell_x + 10
    top = cell_y + 10
    try:
        bounds = draw.textbbox((left, top), label, font=font)
        right, bottom = bounds[2] + 5, bounds[3] + 4
    except AttributeError:
        width, height = draw.textsize(label, font=font)
        right, bottom = left + width + 5, top + height + 4
    draw.rectangle((left - 5, top - 4, right, bottom), fill=(255, 255, 255))
    draw.text((left, top), label, fill=(15, 15, 15), font=font)


def make_contact_sheet(
    images: Mapping[str, bytes | bytearray | memoryview | str | Path]
    | Iterable[ImageInput | tuple[str, Any] | Mapping[str, Any]],
    *,
    cell_size: int = CONTACT_SHEET_SIZE,
) -> bytes:
    """Render up to nine sorted images into one deterministic 3x3 PNG.

    Empty cells remain a fixed neutral background.  The contact sheet is
    always square and always has nine positions, including for a short final
    sheet.  More than nine inputs is rejected; use :func:`make_contact_sheets`
    to split a larger collection.
    """

    if isinstance(cell_size, bool) or not isinstance(cell_size, int) or cell_size < 32:
        raise ImagePreparationError("cell_size must be an integer of at least 32")
    values = _iter_image_inputs(images)
    if len(values) > CONTACT_SHEET_COUNT:
        raise ImagePreparationError("one contact sheet can contain at most nine images")

    canvas_size = cell_size * CONTACT_SHEET_COLUMNS
    sheet = Image.new("RGB", (canvas_size, canvas_size), (238, 238, 238))
    draw = ImageDraw.Draw(sheet)
    for index, item in enumerate(values):
        row, column = divmod(index, CONTACT_SHEET_COLUMNS)
        cell_x, cell_y = column * cell_size, row * cell_size
        draw.rectangle(
            (cell_x, cell_y, cell_x + cell_size - 1, cell_y + cell_size - 1),
            outline=(190, 190, 190),
            width=1,
        )
        image = _open(item.data).convert("RGB")
        inner_size = cell_size - 16
        fitted = ImageOps.contain(
            image,
            (inner_size, inner_size),
            method=Image.Resampling.LANCZOS,
        )
        image_x = cell_x + (cell_size - fitted.width) // 2
        image_y = cell_y + (cell_size - fitted.height) // 2
        sheet.paste(fitted, (image_x, image_y))
        _draw_label(draw, cell_x, cell_y, index + 1, item.photo_id)

    output = BytesIO()
    _save_png(sheet, output)
    return output.getvalue()


def make_contact_sheets(
    images: Mapping[str, bytes | bytearray | memoryview | str | Path]
    | Iterable[ImageInput | tuple[str, Any] | Mapping[str, Any]],
    *,
    cell_size: int = CONTACT_SHEET_SIZE,
) -> tuple[bytes, ...]:
    """Split sorted inputs into deterministic groups of nine contact sheets."""

    values = _iter_image_inputs(images)
    return tuple(
        make_contact_sheet(values[start : start + CONTACT_SHEET_COUNT], cell_size=cell_size)
        for start in range(0, len(values), CONTACT_SHEET_COUNT)
    )


def contact_sheet(
    images: Mapping[str, bytes | bytearray | memoryview | str | Path]
    | Iterable[ImageInput | tuple[str, Any] | Mapping[str, Any]],
    *,
    cell_size: int = CONTACT_SHEET_SIZE,
) -> bytes:
    """Alias for :func:`make_contact_sheet` used by small integrations."""

    return make_contact_sheet(images, cell_size=cell_size)


def prepare_dedicated(
    value: bytes | bytearray | memoryview | str | Path,
    *,
    max_edge: int = DEFAULT_MAX_EDGE,
    max_long_edge: int | None = None,
) -> bytes:
    """Resize an image to ``max_edge`` on its long side.

    Sources already at or below the limit are returned byte-for-byte without
    opening and re-encoding them.  Larger sources use their original format
    where Pillow supports deterministic settings, and otherwise use PNG.
    """

    if max_long_edge is not None:
        max_edge = max_long_edge
    if isinstance(max_edge, bool) or not isinstance(max_edge, int) or max_edge < 1:
        raise ImagePreparationError("max_edge must be a positive integer")
    data = _as_bytes(value)
    info = image_info(data)
    if info.long_edge <= max_edge:
        return data
    image = _open(data)
    if image.width >= image.height:
        width = max_edge
        height = max(1, round(max_edge * image.height / image.width))
    else:
        height = max_edge
        width = max(1, round(max_edge * image.width / image.height))
    resized = image.resize((width, height), Image.Resampling.LANCZOS)
    return _save_prepared(resized, info.format)


def dedicated_read(
    value: bytes | bytearray | memoryview | str | Path,
    *,
    max_edge: int = DEFAULT_MAX_EDGE,
    max_long_edge: int | None = None,
) -> bytes:
    """Alias for :func:`prepare_dedicated`."""

    return prepare_dedicated(value, max_edge=max_edge, max_long_edge=max_long_edge)


def resize_for_dedicated(
    value: bytes | bytearray | memoryview | str | Path,
    *,
    max_edge: int = DEFAULT_MAX_EDGE,
    max_long_edge: int | None = None,
) -> bytes:
    """Descriptive alias for the absolute-read preparation step."""

    return prepare_dedicated(value, max_edge=max_edge, max_long_edge=max_long_edge)


def validate_bbox(bbox: Any) -> tuple[float, float, float, float]:
    """Validate and normalize a bbox expressed in the unit square."""

    if isinstance(bbox, Mapping):
        values = tuple(bbox.get(name) for name in ("x0", "y0", "x1", "y1"))
    else:
        try:
            values = tuple(bbox)
        except TypeError as exc:
            raise ImagePreparationError(
                "bbox must be a four-item sequence or x0/y0/x1/y1 mapping"
            ) from exc
    if len(values) != 4:
        raise ImagePreparationError("bbox must contain exactly four values")
    if any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in values):
        raise ImagePreparationError("bbox values must be finite numbers")
    result = tuple(float(item) for item in values)
    if any(not math.isfinite(item) or not 0.0 <= item <= 1.0 for item in result):
        raise ImagePreparationError("bbox values must be within [0,1]")
    x0, y0, x1, y1 = result
    if not x0 < x1 or not y0 < y1:
        raise ImagePreparationError("bbox must satisfy x0<x1 and y0<y1")
    return result


def crop_box_for_bbox(
    size: tuple[int, int],
    bbox: Any,
    *,
    margin_ratio: float = FACE_MARGIN_RATIO,
) -> tuple[int, int, int, int]:
    """Return an integer crop box with a 40% per-side bbox margin.

    The margin is calculated independently on each axis from the bbox width
    or height.  ``floor``/``ceil`` preserve every covered source pixel; when
    the resulting box is not clamped, its dimensions represent the exact
    requested 40% margin for integer-aligned bbox edges.  Clamping at an image
    edge is intentionally allowed to shorten that margin.
    """

    if (
        not isinstance(size, tuple)
        or len(size) != 2
        or any(isinstance(item, bool) or not isinstance(item, int) or item < 1 for item in size)
    ):
        raise ImagePreparationError("image size must be a pair of positive integers")
    if (
        isinstance(margin_ratio, bool)
        or not isinstance(margin_ratio, (int, float))
        or not math.isfinite(float(margin_ratio))
        or margin_ratio < 0
    ):
        raise ImagePreparationError("margin_ratio must be a non-negative number")
    x0, y0, x1, y1 = validate_bbox(bbox)
    width, height = size
    left_edge = x0 * width
    top_edge = y0 * height
    right_edge = x1 * width
    bottom_edge = y1 * height
    bbox_width = right_edge - left_edge
    bbox_height = bottom_edge - top_edge
    margin_x = bbox_width * float(margin_ratio)
    margin_y = bbox_height * float(margin_ratio)
    left = math.floor(left_edge - margin_x)
    top = math.floor(top_edge - margin_y)
    right = math.ceil(right_edge + margin_x)
    bottom = math.ceil(bottom_edge + margin_y)
    return (
        max(0, left),
        max(0, top),
        min(width, right),
        min(height, bottom),
    )


def prepare_face_crop(
    value: bytes | bytearray | memoryview | str | Path,
    bbox: Any,
    *,
    margin_ratio: float = FACE_MARGIN_RATIO,
) -> bytes:
    """Crop a validated normalized bbox with a clamped 40% margin."""

    data = _as_bytes(value)
    image = _open(data)
    box = crop_box_for_bbox(image.size, bbox, margin_ratio=margin_ratio)
    if box[2] <= box[0] or box[3] <= box[1]:
        raise ImagePreparationError("bbox produced an empty crop")
    return _save_prepared(image.crop(box), "PNG")


def face_crop(
    value: bytes | bytearray | memoryview | str | Path,
    bbox: Any,
    *,
    margin_ratio: float = FACE_MARGIN_RATIO,
) -> bytes:
    """Alias for :func:`prepare_face_crop`."""

    return prepare_face_crop(value, bbox, margin_ratio=margin_ratio)


def crop_face(
    value: bytes | bytearray | memoryview | str | Path,
    bbox: Any,
    *,
    margin_ratio: float = FACE_MARGIN_RATIO,
) -> bytes:
    """Compatibility alias for :func:`prepare_face_crop`."""

    return prepare_face_crop(value, bbox, margin_ratio=margin_ratio)


def crop_with_margin(
    value: bytes | bytearray | memoryview | str | Path,
    bbox: Any,
    *,
    margin_ratio: float = FACE_MARGIN_RATIO,
) -> bytes:
    """Descriptive alias for :func:`prepare_face_crop`."""

    return prepare_face_crop(value, bbox, margin_ratio=margin_ratio)


def create_contact_sheet(
    images: Mapping[str, bytes | bytearray | memoryview | str | Path]
    | Iterable[ImageInput | tuple[str, Any] | Mapping[str, Any]],
    *,
    cell_size: int = CONTACT_SHEET_SIZE,
) -> bytes:
    """Compatibility alias for :func:`make_contact_sheet`."""

    return make_contact_sheet(images, cell_size=cell_size)


def validate_normalized_bbox(bbox: Any) -> tuple[float, float, float, float]:
    """Compatibility alias for :func:`validate_bbox`."""

    return validate_bbox(bbox)


contact_sheet_of_nine = make_contact_sheet
resize_max_edge = prepare_dedicated
crop_face_bbox = prepare_face_crop
build_contact_sheet = make_contact_sheet
prepare_contact_sheet = make_contact_sheet
read_dedicated = prepare_dedicated
crop_bbox = prepare_face_crop


__all__ = [
    "CONTACT_SHEET_COLUMNS",
    "CONTACT_SHEET_COUNT",
    "CONTACT_SHEET_ROWS",
    "CONTACT_SHEET_SIZE",
    "DEFAULT_MAX_EDGE",
    "FACE_MARGIN_RATIO",
    "ImageInfo",
    "ImageInput",
    "ImagePreparationError",
    "build_contact_sheet",
    "contact_sheet",
    "contact_sheet_of_nine",
    "create_contact_sheet",
    "crop_bbox",
    "crop_face",
    "crop_box_for_bbox",
    "crop_with_margin",
    "crop_face_bbox",
    "dedicated_read",
    "face_crop",
    "image_info",
    "make_contact_sheet",
    "make_contact_sheets",
    "mime_type_for_format",
    "prepare_contact_sheet",
    "prepare_dedicated",
    "prepare_face_crop",
    "resize_for_dedicated",
    "resize_max_edge",
    "read_dedicated",
    "validate_bbox",
    "validate_normalized_bbox",
]
