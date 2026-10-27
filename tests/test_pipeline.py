"""Unit tests for the optimisation loop (no Blender required)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from blender_loop.params import ParamSpec, SearchSpace
from blender_loop.pipeline import Evaluation, Loop, LoopResult
from blender_loop.search import BudgetExhausted


def build_space() -> SearchSpace:
    return SearchSpace(
        [
            ParamSpec("x", 0.0, 10.0, default=5.0),
            ParamSpec("y", 0.0, 10.0, default=5.0),
        ]
    )


class LoopTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workdir = Path(tempfile.mkdtemp(prefix="blender-loop-pipeline-"))
        self.calls: list[dict[str, float]] = []

    def evaluator(self, params: dict[str, float], workdir: Path) -> Evaluation:
        self.calls.append(dict(params))
        score = (params["x"] - 7.0) ** 2 + (params["y"] - 2.0) ** 2
        return Evaluation(params=dict(params), score=score)

    def test_coordinate_descent_recovers_target(self) -> None:
        loop = Loop(build_space(), self.evaluator, self.workdir, budget=200)
        result = loop.run_coordinate_descent(rounds=8, step_fraction=0.3, shrink=0.6)
        self.assertIsNotNone(result.best)
        assert result.best is not None
        self.assertAlmostEqual(result.best.params["x"], 7.0, delta=0.2)
        self.assertAlmostEqual(result.best.params["y"], 2.0, delta=0.2)
        self.assertLess(result.best.score, 0.1)
        self.assertEqual(len(result.history), loop.evaluations)

    def test_cache_prevents_duplicate_calls(self) -> None:
        loop = Loop(build_space(), self.evaluator, self.workdir, budget=50)
        first = loop.evaluate({"x": 3.0, "y": 4.0})
        calls_after_first = len(self.calls)
        second = loop.evaluate({"x": 3.0, "y": 4.0})
        self.assertEqual(calls_after_first, len(self.calls))
        self.assertIs(first, second)

    def test_budget_is_enforced(self) -> None:
        loop = Loop(build_space(), self.evaluator, self.workdir, budget=4)
        result = loop.run_coordinate_descent(rounds=20)
        self.assertLessEqual(loop.evaluations, 4)
        self.assertEqual(len(result.history), loop.evaluations)
        with self.assertRaises(BudgetExhausted):
            loop.evaluate({"x": 1.0, "y": 1.0})

    def test_maximize_keeps_highest_score(self) -> None:
        def evaluator(params: dict[str, float], workdir: Path) -> Evaluation:
            return Evaluation(params=dict(params), score=params["x"] + params["y"])

        loop = Loop(build_space(), evaluator, self.workdir, budget=80, maximize=True)
        result = loop.run_coordinate_descent(rounds=5)
        assert result.best is not None
        self.assertGreater(result.best.score, 19.0)

    def test_random_search_is_reproducible(self) -> None:
        loop_a = Loop(build_space(), self.evaluator, self.workdir / "a", budget=30)
        loop_b = Loop(build_space(), self.evaluator, self.workdir / "b", budget=30)
        first = loop_a.run_random(samples=10, seed=5)
        second = loop_b.run_random(samples=10, seed=5)
        self.assertEqual([p.params for p in first.history], [p.params for p in second.history])

    def test_result_roundtrip(self) -> None:
        loop = Loop(build_space(), self.evaluator, self.workdir, budget=20)
        result = loop.run_coordinate_descent(rounds=2)
        path = result.save(self.workdir / "history.json")
        loaded = LoopResult.load(path)
        self.assertEqual(len(loaded.history), len(result.history))
        assert loaded.best is not None and result.best is not None
        self.assertAlmostEqual(loaded.best.score, result.best.score, places=6)
        self.assertEqual(loaded.best.params, result.best.params)

    def test_invalid_budget(self) -> None:
        with self.assertRaises(ValueError):
            Loop(build_space(), self.evaluator, self.workdir, budget=0)


if __name__ == "__main__":
    unittest.main()
