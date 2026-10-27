"""The closed loop: evaluate parameters, cache, search, record, report.

A :class:`Loop` owns a parameter space, an evaluator, an evaluation budget and
the full history. Evaluations are cached by quantised parameter hash, so
re-running a search after a crash is cheap and deterministic.

The evaluator is any callable ``(params, workdir) -> Evaluation``; it may
render with Blender, run a solver, or be a pure function in tests.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .params import ParamError, SearchSpace
from .search import BudgetExhausted, coordinate_descent, random_search

__all__ = ["Evaluation", "Evaluator", "Loop", "LoopResult"]

Evaluator = Callable[[dict[str, float], Path], "Evaluation"]


@dataclass
class Evaluation:
    """One evaluated parameter vector and its evidence."""

    params: dict[str, float]
    score: float
    metrics: dict[str, float] = field(default_factory=dict)
    artifacts: list[str] = field(default_factory=list)
    duration_s: float = 0.0

    def as_dict(self) -> dict[str, object]:
        return {
            "params": dict(self.params),
            "score": self.score,
            "metrics": dict(self.metrics),
            "artifacts": list(self.artifacts),
            "duration_s": self.duration_s,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> Evaluation:
        return cls(
            params={str(k): float(v) for k, v in dict(payload.get("params", {})).items()},
            score=float(payload["score"]),
            metrics={str(k): float(v) for k, v in dict(payload.get("metrics", {})).items()},
            artifacts=[str(item) for item in payload.get("artifacts", [])],
            duration_s=float(payload.get("duration_s", 0.0)),
        )


@dataclass
class LoopResult:
    """Best point plus the complete, ordered evaluation history."""

    best: Evaluation | None
    history: list[Evaluation] = field(default_factory=list)
    space: SearchSpace | None = None
    workdir: Path | None = None

    @property
    def scores(self) -> list[float]:
        return [item.score for item in self.history]

    def as_dict(self) -> dict[str, object]:
        return {
            "version": 1,
            "space": self.space.as_dict() if self.space else [],
            "best": self.best.as_dict() if self.best else None,
            "history": [item.as_dict() for item in self.history],
        }

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.as_dict(), indent=1) + "\n", encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: str | Path) -> LoopResult:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        best = Evaluation.from_dict(payload["best"]) if payload.get("best") else None
        history = [Evaluation.from_dict(item) for item in payload.get("history", [])]
        return cls(best=best, history=history)


class Loop:
    """Budgeted, cached optimisation loop."""

    def __init__(
        self,
        space: SearchSpace,
        evaluator: Evaluator,
        workdir: str | Path,
        *,
        budget: int = 40,
        maximize: bool = False,
    ) -> None:
        if budget < 1:
            raise ParamError("budget must be >= 1")
        self.space = space
        self.evaluator = evaluator
        self.workdir = Path(workdir)
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.budget = budget
        self.maximize = maximize
        self._cache: dict[str, Evaluation] = {}
        self._history: list[Evaluation] = []
        self._evaluations = 0

    # -- evaluation ----------------------------------------------------------
    @property
    def evaluations(self) -> int:
        """Number of distinct evaluator calls (cache misses)."""
        return self._evaluations

    @property
    def budget_left(self) -> int:
        return self.budget - self._evaluations

    @property
    def history(self) -> list[Evaluation]:
        return list(self._history)

    def evaluate(self, params: dict[str, float]) -> Evaluation:
        """Evaluate (or reuse) one vector; raises :class:`BudgetExhausted`."""
        quantised = self.space.quantize(params)
        key = self.space.key(quantised)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        if self._evaluations >= self.budget:
            raise BudgetExhausted(f"evaluation budget of {self.budget} exhausted")
        started = time.monotonic()
        result = self.evaluator(quantised, self.workdir)
        if not isinstance(result, Evaluation):
            raise TypeError("evaluator must return an Evaluation")
        if result.duration_s <= 0:
            result.duration_s = time.monotonic() - started
        result.params = dict(quantised)
        self._evaluations += 1
        self._cache[key] = result
        self._history.append(result)
        return result

    # -- searches ------------------------------------------------------------
    def _to_result(self, summary: object) -> LoopResult:
        best: Evaluation | None = None
        point = getattr(summary, "best", None)
        if point is not None:
            key = self.space.key(self.space.quantize(point.params))
            best = self._cache.get(key)
        if best is None and self._history:
            best = sorted(self._history, key=lambda item: item.score, reverse=self.maximize)[0]
        return LoopResult(
            best=best,
            history=list(self._history),
            space=self.space,
            workdir=self.workdir,
        )

    def run_coordinate_descent(
        self,
        *,
        initial: dict[str, float] | None = None,
        rounds: int = 4,
        step_fraction: float = 0.25,
        shrink: float = 0.5,
    ) -> LoopResult:
        """Greedy coordinate descent using this loop's evaluator and budget."""
        summary = coordinate_descent(
            self.space,
            lambda params: self.evaluate(params).score,
            initial=initial,
            rounds=rounds,
            step_fraction=step_fraction,
            shrink=shrink,
            maximize=self.maximize,
        )
        return self._to_result(summary)

    def run_random(self, *, samples: int = 30, seed: int = 0) -> LoopResult:
        """Uniform random search inside the parameter box."""
        summary = random_search(
            self.space,
            lambda params: self.evaluate(params).score,
            samples=samples,
            seed=seed,
            maximize=self.maximize,
        )
        return self._to_result(summary)
