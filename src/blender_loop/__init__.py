"""blender-loop: headless Blender modeling, machine tuning and self-iteration."""

from __future__ import annotations

__version__ = "0.1.0"

from .blender import BlenderConfig, BlenderError, RunResult, build_script_argv, run_script
from .metrics import load_mask, mask_iou, silhouette_metrics
from .params import ParamError, ParamSpec, SearchSpace
from .pipeline import Evaluation, Loop, LoopResult
from .report import render_report
from .search import BudgetExhausted, coordinate_descent, random_search

__all__ = [
    "BlenderConfig",
    "BlenderError",
    "BudgetExhausted",
    "Evaluation",
    "Loop",
    "LoopResult",
    "ParamError",
    "ParamSpec",
    "RunResult",
    "SearchSpace",
    "build_script_argv",
    "coordinate_descent",
    "load_mask",
    "mask_iou",
    "random_search",
    "render_report",
    "run_script",
    "silhouette_metrics",
    "__version__",
]
