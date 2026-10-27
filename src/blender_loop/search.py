"""Deterministic search strategies for closed-loop parameter fitting.

The contract is deliberately small: an evaluator maps a parameter vector to a
single scalar score, and every strategy records each evaluated point. Higher
scores are better unless ``maximize=False`` is passed.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable
from dataclasses import dataclass, field

from .params import ParamError, ParamSpec, SearchSpace

__all__ = [
    "BudgetExhausted",
    "EvalPoint",
    "SearchSummary",
    "coordinate_descent",
    "random_search",
    "suggested_initial_step",
]

Evaluator = Callable[[dict[str, float]], float]


class BudgetExhausted(RuntimeError):
    """Raised by a budget-aware evaluator when the evaluation budget is spent."""


@dataclass(frozen=True)
class EvalPoint:
    """One evaluated parameter vector."""

    params: dict[str, float]
    score: float


@dataclass
class SearchSummary:
    """Best point plus the full evaluation trace."""

    best: EvalPoint | None
    history: list[EvalPoint] = field(default_factory=list)

    @property
    def evaluations(self) -> int:
        return len(self.history)

    @property
    def scores(self) -> list[float]:
        return [point.score for point in self.history]


def suggested_initial_step(spec: ParamSpec) -> float:
    """Initial step size for one parameter: its hint, else 25% of the span."""
    if spec.step is not None:
        return float(spec.step)
    return spec.span * 0.25


def _is_better(candidate: float, incumbent: float, maximize: bool) -> bool:
    if math.isnan(candidate):
        return False
    if math.isnan(incumbent):
        return True
    return candidate > incumbent if maximize else candidate < incumbent


def coordinate_descent(
    space: SearchSpace,
    evaluate: Evaluator,
    *,
    initial: dict[str, float] | None = None,
    rounds: int = 4,
    step_fraction: float = 0.25,
    shrink: float = 0.5,
    maximize: bool = False,
) -> SearchSummary:
    """Greedy coordinate descent with shrinking steps.

    Each round visits every parameter in name order, tries ``+step`` and
    ``-step`` (clamped into bounds) and keeps the best candidate. Steps shrink
    by ``shrink`` per round. ``BudgetExhausted`` from the evaluator stops the
    search and returns the trace collected so far.
    """
    if rounds < 1:
        raise ParamError("rounds must be >= 1")
    if not 0 < step_fraction <= 1:
        raise ParamError("step_fraction must be in (0, 1]")
    if not 0 < shrink < 1:
        raise ParamError("shrink must be in (0, 1)")

    current = space.clip(initial if initial is not None else space.initial())
    history: list[EvalPoint] = []

    def probe(params: dict[str, float]) -> float:
        score = float(evaluate(params))
        history.append(EvalPoint(params=dict(params), score=score))
        return score

    try:
        best_score = probe(current)
        best_params = dict(current)
        for round_index in range(rounds):
            for spec in sorted(space.specs, key=lambda item: item.name):
                step = spec.span * step_fraction * (shrink**round_index)
                if step <= 0:
                    continue
                for direction in (1.0, -1.0):
                    candidate = dict(best_params)
                    candidate[spec.name] = spec.clip(best_params[spec.name] + direction * step)
                    if candidate[spec.name] == best_params[spec.name]:
                        continue
                    score = probe(candidate)
                    if _is_better(score, best_score, maximize):
                        best_score = score
                        best_params = candidate
    except BudgetExhausted:
        pass

    best_point = EvalPoint(params=best_params, score=best_score) if history else None
    return SearchSummary(best=best_point, history=history)


def random_search(
    space: SearchSpace,
    evaluate: Evaluator,
    *,
    samples: int = 30,
    seed: int = 0,
    maximize: bool = False,
) -> SearchSummary:
    """Uniform random sampling inside the box (useful as a baseline)."""
    if samples < 1:
        raise ParamError("samples must be >= 1")
    rng = random.Random(seed)
    history: list[EvalPoint] = []
    best: EvalPoint | None = None
    try:
        for _ in range(samples):
            params = space.sample(rng)
            score = float(evaluate(params))
            point = EvalPoint(params=params, score=score)
            history.append(point)
            if best is None or _is_better(score, best.score, maximize):
                best = point
    except BudgetExhausted:
        pass
    return SearchSummary(best=best, history=history)
