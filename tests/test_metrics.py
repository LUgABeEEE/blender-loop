"""Unit tests for mask metrics (no Blender required)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from blender_loop.metrics import (
    MaskError,
    bbox,
    centroid,
    load_mask,
    mask_iou,
    mask_rmse,
    pixel_agreement,
    silhouette_metrics,
)


def rectangle_mask(size: int = 20, box: tuple[int, int, int, int] = (2, 2, 10, 10)) -> np.ndarray:
    mask = np.zeros((size, size), dtype=bool)
    mask[box[1] : box[3], box[0] : box[2]] = True
    return mask


class MaskMetricTests(unittest.TestCase):
    def test_iou_identical(self) -> None:
        mask = rectangle_mask()
        self.assertAlmostEqual(mask_iou(mask, mask), 1.0)

    def test_iou_disjoint(self) -> None:
        left = rectangle_mask(box=(0, 0, 5, 5))
        right = rectangle_mask(box=(10, 10, 15, 15))
        self.assertEqual(mask_iou(left, right), 0.0)

    def test_iou_is_three_quarters(self) -> None:
        first = rectangle_mask(box=(0, 0, 4, 4))
        second = rectangle_mask(box=(0, 0, 2, 2))
        self.assertAlmostEqual(mask_iou(first, second), 4 / 16)

    def test_empty_masks_are_equal(self) -> None:
        empty = np.zeros((5, 5), dtype=bool)
        self.assertEqual(mask_iou(empty, empty), 1.0)

    def test_shape_mismatch_raises(self) -> None:
        with self.assertRaises(MaskError):
            mask_iou(np.zeros((2, 2), dtype=bool), np.zeros((3, 3), dtype=bool))

    def test_rmse_and_agreement(self) -> None:
        first = rectangle_mask(box=(0, 0, 10, 10))
        second = rectangle_mask(box=(5, 5, 15, 15))
        self.assertGreater(mask_rmse(first, second), 0.0)
        self.assertAlmostEqual(pixel_agreement(first, first), 1.0)

    def test_centroid_and_bbox(self) -> None:
        mask = rectangle_mask(box=(2, 4, 6, 8))
        self.assertEqual(centroid(mask), (3.5, 5.5))
        self.assertEqual(bbox(mask), (2, 4, 5, 7))
        self.assertIsNone(centroid(np.zeros((4, 4), dtype=bool)))
        self.assertIsNone(bbox(np.zeros((4, 4), dtype=bool)))

    def test_silhouette_metrics_bundle(self) -> None:
        first = rectangle_mask(box=(0, 0, 10, 10))
        second = rectangle_mask(box=(0, 0, 10, 10))
        metrics = silhouette_metrics(first, second)
        self.assertAlmostEqual(metrics["iou"], 1.0)
        self.assertIn("centroid_distance_px", metrics)


class LoadMaskTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="blender-loop-metrics-"))

    def _write_rgba(self, name: str, box: tuple[int, int, int, int]) -> Path:
        image = Image.new("RGBA", (20, 20), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rectangle(box, fill=(255, 255, 255, 255))
        path = self.tmp / name
        image.save(path)
        return path

    def test_alpha_channel(self) -> None:
        path = self._write_rgba("alpha.png", (2, 2, 10, 10))
        mask = load_mask(path)
        self.assertEqual(int(mask.sum()), 9 * 9)  # PIL rectangles are inclusive

    def test_luminance_channel(self) -> None:
        image = Image.new("L", (10, 10), 0)
        ImageDraw.Draw(image).rectangle((0, 0, 5, 5), fill=255)
        path = self.tmp / "lum.png"
        image.save(path)
        mask = load_mask(path, channel="luminance")
        self.assertEqual(int(mask.sum()), 36)

    def test_missing_alpha_raises(self) -> None:
        image = Image.new("RGB", (10, 10), (255, 255, 255))
        path = self.tmp / "rgb.png"
        image.save(path)
        with self.assertRaises(MaskError):
            load_mask(path)

    def test_missing_file_raises(self) -> None:
        with self.assertRaises(MaskError):
            load_mask(self.tmp / "nope.png")

    def test_unknown_channel_raises(self) -> None:
        path = self._write_rgba("ok.png", (1, 1, 3, 3))
        with self.assertRaises(MaskError):
            load_mask(path, channel="depth")


if __name__ == "__main__":
    unittest.main()
