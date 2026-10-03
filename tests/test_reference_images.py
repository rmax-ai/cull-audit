from __future__ import annotations

from io import BytesIO
from pathlib import Path
import unittest

from PIL import Image

from cull_audit.reference.images import (
    ImagePreparationError,
    crop_box_for_bbox,
    make_contact_sheet,
    prepare_dedicated,
    prepare_face_crop,
    validate_bbox,
)


def image_bytes(size: tuple[int, int], color: tuple[int, int, int]) -> bytes:
    output = BytesIO()
    Image.new("RGB", size, color).save(
        output,
        format="PNG",
        optimize=False,
        compress_level=9,
    )
    return output.getvalue()


class ReferenceImageTests(unittest.TestCase):
    def test_nine_up_sorts_ids_labels_positions_and_is_deterministic(self) -> None:
        colors = {
            "z-photo.png": (255, 0, 0),
            "a-photo.png": (0, 255, 0),
            "m-photo.png": (0, 0, 255),
        }
        inputs = {
            photo_id: image_bytes((30, 20), color)
            for photo_id, color in colors.items()
        }
        first = make_contact_sheet(inputs, cell_size=96)
        second = make_contact_sheet(
            [
                ("m-photo.png", inputs["m-photo.png"]),
                ("z-photo.png", inputs["z-photo.png"]),
                ("a-photo.png", inputs["a-photo.png"]),
            ],
            cell_size=96,
        )
        self.assertEqual(first, second)
        with Image.open(BytesIO(first)) as sheet:
            self.assertEqual(sheet.format, "PNG")
            self.assertEqual(sheet.size, (288, 288))
            # The image centers prove stable sorted placement: a, m, z.
            self.assertEqual(sheet.getpixel((48, 48)), colors["a-photo.png"])
            self.assertEqual(sheet.getpixel((144, 48)), colors["m-photo.png"])
            self.assertEqual(sheet.getpixel((240, 48)), colors["z-photo.png"])
            # The first cell includes an in-frame position/ID label.
            self.assertNotEqual(sheet.getpixel((12, 12)), colors["a-photo.png"])

    def test_dedicated_read_preserves_small_bytes_and_caps_long_edge(self) -> None:
        small = image_bytes((120, 80), (10, 20, 30))
        self.assertIs(prepare_dedicated(small), small)
        self.assertEqual(prepare_dedicated(small), small)

        large = image_bytes((2000, 1000), (40, 50, 60))
        prepared = prepare_dedicated(large)
        with Image.open(BytesIO(prepared)) as image:
            self.assertEqual(image.size, (1536, 768))
            self.assertEqual(max(image.size), 1536)

        tall = image_bytes((1000, 2000), (40, 50, 60))
        with Image.open(BytesIO(prepare_dedicated(tall))) as image:
            self.assertEqual(image.size, (768, 1536))

    def test_face_margin_is_exact_when_unclamped_and_clamps_at_edges(self) -> None:
        source = image_bytes((100, 100), (100, 110, 120))
        bbox = (0.20, 0.20, 0.40, 0.40)
        self.assertEqual(validate_bbox(bbox), bbox)
        self.assertEqual(crop_box_for_bbox((100, 100), bbox), (12, 12, 48, 48))
        with Image.open(BytesIO(prepare_face_crop(source, bbox))) as crop:
            self.assertEqual(crop.size, (36, 36))

        clamped = (0.0, 0.20, 0.20, 0.40)
        self.assertEqual(crop_box_for_bbox((100, 100), clamped), (0, 12, 28, 48))
        with Image.open(BytesIO(prepare_face_crop(source, clamped))) as crop:
            self.assertEqual(crop.size, (28, 36))

        for invalid in (
            (-0.1, 0.1, 0.2, 0.3),
            (0.1, 0.1, 1.1, 0.3),
            (0.3, 0.1, 0.2, 0.3),
            (0.1, 0.3, 0.2, 0.2),
        ):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ImagePreparationError):
                    validate_bbox(invalid)

    def test_prepared_outputs_are_byte_identical_across_reruns(self) -> None:
        photos = {
            "b.png": image_bytes((180, 120), (1, 2, 3)),
            "a.png": image_bytes((1800, 900), (4, 5, 6)),
        }
        first = make_contact_sheet(photos, cell_size=128)
        second = make_contact_sheet(photos, cell_size=128)
        self.assertEqual(first, second)
        self.assertEqual(prepare_dedicated(photos["a.png"]), prepare_dedicated(photos["a.png"]))
        self.assertEqual(
            prepare_face_crop(photos["b.png"], (0.2, 0.2, 0.6, 0.6)),
            prepare_face_crop(photos["b.png"], (0.2, 0.2, 0.6, 0.6)),
        )


if __name__ == "__main__":
    unittest.main()
