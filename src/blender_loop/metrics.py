"""Image and mask metrics used as loop objectives.

Masks are boolean ``numpy`` arrays of shape ``(height, width)``. The helpers
read PNG silhouettes produced by a Blender render (alpha or luminance channel)
so the objective never depends on Blender itself.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PIL import Image

__all__ = [
    "MaskError",
    "bbox",
    "centroid",
    "load_mask",
    "mask_iou",
    "mask_rmse",
    "pixel_agreement",
    "silhouette_metrics",
]


class MaskError(ValueError):
    """Raised when a mask cannot be read or is malformed."""


def load_mask(
    path: str | Path,
    *,
    channel: str = "alpha",
    threshold: int = 127,
) -> np.ndarray:
    """Load ``path`` as a boolean mask.

    ``channel="alpha"`` uses the alpha channel (transparent-film renders);
    ``channel="luminance"`` uses the grey level (opaque renders).
    """
    try:
        with Image.open(path) as image:
            if channel == "alpha":
                if "A" not in image.getbands():
                    raise MaskError(f"{path}: no alpha channel (use channel='luminance')")
                array = np.asarray(image.convert("RGBA"))[:, :, 3]
            elif channel == "luminance":
                array = np.asarray(image.convert("L"))
            else:
                raise MaskError(f"unknown channel: {channel!r}")
    except OSError as exc:
        raise MaskError(f"cannot open mask {path}: {exc}") from exc
    return array > threshold


def _check_pair(a: np.ndarray, b: np.ndarray) -> None:
    if a.shape != b.shape:
        raise MaskError(f"mask shapes differ: {a.shape} vs {b.shape}")


def mask_iou(a: np.ndarray, b: np.ndarray) -> float:
    """Intersection over union; ``1.0`` when both masks are empty."""
    _check_pair(a, b)
    union = np.logical_or(a, b).sum()
    if union == 0:
        return 1.0
    return float(np.logical_and(a, b).sum()) / float(union)


def mask_rmse(a: np.ndarray, b: np.ndarray) -> float:
    """Root-mean-square difference of the two binary masks in [0, 1]."""
    _check_pair(a, b)
    diff = a.astype(np.float64) - b.astype(np.float64)
    return float(math.sqrt(float(np.mean(diff * diff))))


def pixel_agreement(a: np.ndarray, b: np.ndarray) -> float:
    """Fraction of pixels that agree (both inside or both outside)."""
    _check_pair(a, b)
    return float(np.mean(a == b))


def centroid(mask: np.ndarray) -> tuple[float, float] | None:
    """Centroid in pixel coordinates ``(x, y)`` or ``None`` for an empty mask."""
    ys, xs = np.nonzero(mask)
    if xs.size == 0:
        return None
    return float(xs.mean()), float(ys.mean())


def bbox(mask: np.ndarray) -> tuple[int, int, int, int] | None:
    """Bounding box ``(x0, y0, x1, y1)`` in pixels (inclusive) or ``None``."""
    ys, xs = np.nonzero(mask)
    if xs.size == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


def silhouette_metrics(a: np.ndarray, b: np.ndarray) -> dict[str, float]:
    """A compact metric bundle suitable for a loop's ``metrics`` field."""
    metrics = {
        "iou": mask_iou(a, b),
        "rmse": mask_rmse(a, b),
        "agreement": pixel_agreement(a, b),
    }
    ca, cb = centroid(a), centroid(b)
    if ca is not None and cb is not None:
        metrics["centroid_distance_px"] = math.hypot(ca[0] - cb[0], ca[1] - cb[1])
    return metrics
