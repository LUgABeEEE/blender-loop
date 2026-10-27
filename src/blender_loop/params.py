"""Parameter spaces for closed-loop modeling.

A space is a named set of bounded scalars. Evaluators always receive a plain
``dict[str, float]`` so a run can be cached, serialised, replayed and audited.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass

__all__ = ["ParamError", "ParamSpec", "SearchSpace"]


class ParamError(ValueError):
    """Raised for an invalid parameter space or parameter vector."""


@dataclass(frozen=True)
class ParamSpec:
    """One bounded scalar parameter.

    ``default`` falls back to the midpoint of ``[low, high]``; ``step`` is a
    hint for search algorithms and is not enforced by the space.
    """

    name: str
    low: float
    high: float
    default: float | None = None
    step: float | None = None

    def __post_init__(self) -> None:
        if not self.name:
            raise ParamError("param name must not be empty")
        if not math.isfinite(self.low) or not math.isfinite(self.high):
            raise ParamError(f"{self.name}: bounds must be finite")
        if self.low >= self.high:
            raise ParamError(f"{self.name}: low ({self.low}) must be < high ({self.high})")
        if self.default is None:
            object.__setattr__(self, "default", (self.low + self.high) / 2.0)
        if not self.low <= self.default <= self.high:
            raise ParamError(f"{self.name}: default {self.default} outside [{self.low}, {self.high}]")
        if self.step is not None and self.step <= 0:
            raise ParamError(f"{self.name}: step must be > 0")

    @property
    def span(self) -> float:
        return self.high - self.low

    def clip(self, value: float) -> float:
        """Clamp ``value`` into this parameter's bounds (NaN raises)."""
        value = float(value)
        if math.isnan(value):
            raise ParamError(f"{self.name}: value is NaN")
        return min(max(value, self.low), self.high)


class SearchSpace:
    """An ordered collection of :class:`ParamSpec` objects."""

    def __init__(self, specs: Iterable[ParamSpec]) -> None:
        self._specs = tuple(specs)
        if not self._specs:
            raise ParamError("a search space needs at least one parameter")
        names = [spec.name for spec in self._specs]
        if len(set(names)) != len(names):
            raise ParamError("duplicate parameter names are not allowed")
        self._by_name = {spec.name: spec for spec in self._specs}

    # -- collection protocol -------------------------------------------------
    def __len__(self) -> int:
        return len(self._specs)

    def __iter__(self) -> Iterator[ParamSpec]:
        return iter(self._specs)

    def __contains__(self, name: object) -> bool:
        return name in self._by_name

    @property
    def specs(self) -> tuple[ParamSpec, ...]:
        return self._specs

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(spec.name for spec in self._specs)

    def spec(self, name: str) -> ParamSpec:
        try:
            return self._by_name[name]
        except KeyError as exc:
            raise ParamError(f"unknown parameter: {name!r}") from exc

    # -- vectors -------------------------------------------------------------
    def clip(self, params: Mapping[str, float]) -> dict[str, float]:
        """Validate names and clamp every value into its bounds."""
        missing = sorted(set(self._by_name) - set(params))
        unknown = sorted(set(params) - set(self._by_name))
        if missing:
            raise ParamError(f"missing parameters: {', '.join(missing)}")
        if unknown:
            raise ParamError(f"unknown parameters: {', '.join(unknown)}")
        return {spec.name: spec.clip(params[spec.name]) for spec in self._specs}

    def initial(self) -> dict[str, float]:
        """The default vector (midpoints unless a default was given)."""
        return {spec.name: float(spec.default) for spec in self._specs}

    def sample(self, rng: random.Random | None = None) -> dict[str, float]:
        """A uniform random vector inside the box."""
        rng = rng or random.Random()
        return {spec.name: rng.uniform(spec.low, spec.high) for spec in self._specs}

    def quantize(self, params: Mapping[str, float], decimals: int = 6) -> dict[str, float]:
        """Round values so equivalent evaluations share a cache key."""
        if decimals < 0:
            raise ParamError("decimals must be >= 0")
        clipped = self.clip(params)
        return {name: round(value, decimals) for name, value in clipped.items()}

    def key(self, params: Mapping[str, float]) -> str:
        """Stable content hash of a parameter vector (order independent)."""
        payload = json.dumps(params, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def as_dict(self) -> list[dict[str, float | str]]:
        return [
            {
                "name": spec.name,
                "low": spec.low,
                "high": spec.high,
                "default": float(spec.default),
                "step": spec.step,
            }
            for spec in self._specs
        ]
