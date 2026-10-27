"""A minimal evaluator that needs no Blender at all.

Run it with the package installed (``pip install -e .``) or:

    PYTHONPATH=src python examples/custom_evaluator.py

It fits two parameters to a quadratic bowl, which is the smallest possible
demonstration of the evaluator contract: ``(params, workdir) -> Evaluation``.
"""

from __future__ import annotations

from pathlib import Path

from blender_loop import Evaluation, Loop, ParamSpec, SearchSpace, render_report

TARGET = {"x": 3.0, "y": -2.0}


def evaluate(params: dict[str, float], workdir: Path) -> Evaluation:
    """Squared distance to an unknown target — the loop only sees the score."""
    score = (params["x"] - TARGET["x"]) ** 2 + (params["y"] - TARGET["y"]) ** 2
    return Evaluation(
        params=params,
        score=score,
        metrics={"distance": score**0.5},
    )


def main() -> None:
    space = SearchSpace(
        [
            ParamSpec("x", -10.0, 10.0),
            ParamSpec("y", -10.0, 10.0),
        ]
    )
    loop = Loop(space, evaluate, Path("out/custom"), budget=60)
    result = loop.run_coordinate_descent(rounds=6)

    assert result.best is not None
    print("best:", result.best.params, "score:", round(result.best.score, 6))
    result.save(Path("out/custom/history.json"))
    render_report(result, Path("out/custom/report.html"), title="Custom evaluator demo")
    print("report -> out/custom/report.html")


if __name__ == "__main__":
    main()
