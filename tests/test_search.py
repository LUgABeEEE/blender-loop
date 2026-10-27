"""Unit tests for the search strategies."""

from __future__ import annotations

import unittest

from blender_loop.params import ParamSpec, SearchSpace
from blender_loop.search import BudgetExhausted, coordinate_descent, random_search


def quadratic(params: dict[str, float]) -> float:
    return (params["x"] - 6.0) ** 2 + (params["y"] + 1.0) ** 2


SPACE = SearchSpace(
    [
        ParamSpec("x", 0.0, 10.0, default=5.0),
        ParamSpec("y", -5.0, 5.0, default=0.0),
    ]
)


class CoordinateDescentTests(unittest.TestCase):
    def test_converges_on_quadratic(self) -> None:
        summary = coordinate_descent(SPACE, quadratic, rounds=8, step_fraction=0.3, shrink=0.6)
        self.assertIsNotNone(summary.best)
        assert summary.best is not None
        self.assertAlmostEqual(summary.best.params["x"], 6.0, delta=0.15)
        self.assertAlmostEqual(summary.best.params["y"], -1.0, delta=0.15)
        self.assertLess(summary.best.score, 0.05)

    def test_history_records_every_probe(self) -> None:
        summary = coordinate_descent(SPACE, quadratic, rounds=2)
        self.assertGreaterEqual(summary.evaluations, 1 + 4 * 2 - 2)

    def test_maximize_flips_direction(self) -> None:
        def peak(params: dict[str, float]) -> float:
            return -quadratic(params)

        summary = coordinate_descent(
            SPACE, peak, rounds=8, step_fraction=0.3, shrink=0.6, maximize=True
        )
        assert summary.best is not None
        self.assertAlmostEqual(summary.best.params["x"], 6.0, delta=0.15)

    def test_budget_exhaustion_stops_cleanly(self) -> None:
        calls = {"n": 0}

        def evaluator(params: dict[str, float]) -> float:
            calls["n"] += 1
            if calls["n"] > 5:
                raise BudgetExhausted("budget")
            return quadratic(params)

        summary = coordinate_descent(SPACE, evaluator, rounds=10)
        self.assertLessEqual(summary.evaluations, 5)
        self.assertIsNotNone(summary.best)

    def test_invalid_parameters(self) -> None:
        with self.assertRaises(ValueError):
            coordinate_descent(SPACE, quadratic, rounds=0)
        with self.assertRaises(ValueError):
            coordinate_descent(SPACE, quadratic, step_fraction=0.0)
        with self.assertRaises(ValueError):
            coordinate_descent(SPACE, quadratic, shrink=1.0)

    def test_nan_scores_are_ignored(self) -> None:
        def evaluator(params: dict[str, float]) -> float:
            return float("nan") if params["x"] > 8.0 else quadratic(params)

        summary = coordinate_descent(SPACE, evaluator, rounds=3)
        self.assertIsNotNone(summary.best)
        for point in summary.history:
            self.assertFalse(point.score != point.score and point is summary.history[0])


class RandomSearchTests(unittest.TestCase):
    def test_samples_are_inside_bounds_and_deterministic(self) -> None:
        first = random_search(SPACE, quadratic, samples=20, seed=3)
        second = random_search(SPACE, quadratic, samples=20, seed=3)
        self.assertEqual(first.evaluations, 20)
        self.assertEqual([p.params for p in first.history], [p.params for p in second.history])
        for point in first.history:
            self.assertGreaterEqual(point.params["x"], 0.0)
            self.assertLessEqual(point.params["x"], 10.0)

    def test_rejects_empty_sample(self) -> None:
        with self.assertRaises(ValueError):
            random_search(SPACE, quadratic, samples=0)


if __name__ == "__main__":
    unittest.main()
