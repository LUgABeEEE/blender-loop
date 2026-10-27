"""Unit tests for the parameter space."""

from __future__ import annotations

import random
import unittest

from blender_loop.params import ParamError, ParamSpec, SearchSpace


class ParamSpecTests(unittest.TestCase):
    def test_default_is_midpoint(self) -> None:
        spec = ParamSpec("width", 1.0, 3.0)
        self.assertEqual(spec.default, 2.0)

    def test_explicit_default_must_be_inside_bounds(self) -> None:
        with self.assertRaises(ParamError):
            ParamSpec("width", 1.0, 3.0, default=5.0)

    def test_rejects_inverted_bounds(self) -> None:
        with self.assertRaises(ParamError):
            ParamSpec("width", 3.0, 1.0)

    def test_rejects_non_positive_step(self) -> None:
        with self.assertRaises(ParamError):
            ParamSpec("width", 1.0, 3.0, step=0.0)

    def test_clip(self) -> None:
        spec = ParamSpec("width", 1.0, 3.0)
        self.assertEqual(spec.clip(0.5), 1.0)
        self.assertEqual(spec.clip(9.0), 3.0)
        self.assertEqual(spec.clip(2.0), 2.0)
        with self.assertRaises(ParamError):
            spec.clip(float("nan"))


class SearchSpaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.space = SearchSpace(
            [
                ParamSpec("width", 0.0, 10.0, default=5.0),
                ParamSpec("height", -2.0, 2.0),
            ]
        )

    def test_rejects_duplicate_names(self) -> None:
        with self.assertRaises(ParamError):
            SearchSpace([ParamSpec("x", 0, 1), ParamSpec("x", 0, 1)])

    def test_rejects_unknown_or_missing_names(self) -> None:
        with self.assertRaises(ParamError):
            self.space.clip({"width": 1.0})
        with self.assertRaises(ParamError):
            self.space.clip({"width": 1.0, "height": 0.0, "depth": 1.0})

    def test_clip_returns_all_names_in_order(self) -> None:
        clipped = self.space.clip({"height": 99.0, "width": -1.0})
        self.assertEqual(list(clipped), ["width", "height"])
        self.assertEqual(clipped["width"], 0.0)
        self.assertEqual(clipped["height"], 2.0)

    def test_initial_uses_defaults(self) -> None:
        self.assertEqual(self.space.initial(), {"width": 5.0, "height": 0.0})

    def test_sample_stays_inside_bounds(self) -> None:
        rng = random.Random(7)
        for _ in range(50):
            vector = self.space.sample(rng)
            self.assertGreaterEqual(vector["width"], 0.0)
            self.assertLessEqual(vector["width"], 10.0)
            self.assertGreaterEqual(vector["height"], -2.0)
            self.assertLessEqual(vector["height"], 2.0)

    def test_quantize_and_key_are_stable(self) -> None:
        a = {"width": 1.234567891, "height": -0.5}
        b = {"height": -0.5, "width": 1.234567892}
        self.assertEqual(self.space.key(self.space.quantize(a)), self.space.key(self.space.quantize(b)))
        other = {"width": 1.3, "height": -0.5}
        self.assertNotEqual(
            self.space.key(self.space.quantize(a)),
            self.space.key(self.space.quantize(other)),
        )


if __name__ == "__main__":
    unittest.main()
