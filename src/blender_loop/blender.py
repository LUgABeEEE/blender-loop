"""Run Blender headless, safely and reproducibly.

The wrapper exists because a runaway Boolean or subdivision can exhaust a
whole machine: every child gets an address-space cap, an optional global lock
so only one Blender runs at a time, a wall-clock timeout, and a structured
result object instead of a bare exit code.

It never imports ``bpy``; it only builds command lines and supervises the
process, so it is testable without Blender installed.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "BlenderConfig",
    "BlenderError",
    "RunResult",
    "build_script_argv",
    "require_blender",
    "run",
    "run_script",
    "version",
]

IS_POSIX = os.name == "posix"


class BlenderError(RuntimeError):
    """Raised for configuration problems (missing binary, bad limits)."""


@dataclass
class BlenderConfig:
    """Everything needed to launch one Blender process."""

    binary: str = "blender"
    memory_mb: int = 8192
    timeout_s: float = 900.0
    lock_path: Path | None = None
    extra_args: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.memory_mb <= 0:
            raise BlenderError("memory_mb must be > 0")
        if self.timeout_s <= 0:
            raise BlenderError("timeout_s must be > 0")


@dataclass(frozen=True)
class RunResult:
    """Outcome of one supervised process."""

    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    duration_s: float
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out

    def check(self) -> RunResult:
        if not self.ok:
            tail = (self.stderr or self.stdout).strip().splitlines()[-8:]
            raise BlenderError(
                f"command failed (rc={self.returncode}, timeout={self.timed_out}):\n"
                + "\n".join(tail)
            )
        return self


def build_script_argv(
    config: BlenderConfig,
    script: str | Path,
    args: Sequence[object] = (),
) -> list[str]:
    """Blender command line that runs ``script`` in background factory mode."""
    return [
        config.binary,
        "-b",
        "--factory-startup",
        *config.extra_args,
        "-P",
        str(script),
        "--",
        *[str(arg) for arg in args],
    ]


def require_blender(config: BlenderConfig) -> str:
    """Return the resolved binary path or raise a helpful error."""
    resolved = shutil.which(config.binary) if os.path.sep not in config.binary else config.binary
    if resolved and Path(resolved).is_file():
        return resolved
    raise BlenderError(
        f"Blender binary not found: {config.binary!r}. "
        "Pass --blender /path/to/blender or install Blender (>= 3.6)."
    )


def version(config: BlenderConfig) -> str:
    """First line of ``blender --version`` (e.g. ``Blender 4.2.9 LTS``)."""
    result = run([require_blender(config), "--version"], timeout_s=120)
    result.check()
    return result.stdout.strip().splitlines()[0] if result.stdout.strip() else "unknown"


@contextmanager
def _locked(path: Path | None) -> Iterator[None]:
    """Cross-process exclusive lock (POSIX only; a no-op elsewhere)."""
    if path is None or not IS_POSIX:
        yield
        return
    import fcntl

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _memory_limiter(memory_mb: int):
    """Return a ``preexec_fn`` that caps the child's address space."""
    if not IS_POSIX:
        return None

    def apply() -> None:  # pragma: no cover - runs in the child process
        import resource

        limit = int(memory_mb) * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))

    return apply


def run(
    argv: Sequence[str],
    *,
    timeout_s: float | None = None,
    memory_mb: int | None = None,
    lock_path: Path | None = None,
    cwd: str | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> RunResult:
    """Supervise one process with an optional memory cap, lock and timeout."""
    started = time.monotonic()
    child_env = dict(os.environ)
    if env:
        child_env.update(env)
    kwargs: dict[str, object] = {
        "capture_output": True,
        "text": True,
        "cwd": str(cwd) if cwd is not None else None,
        "env": child_env,
    }
    if memory_mb is not None:
        preexec = _memory_limiter(memory_mb)
        if preexec is not None:
            kwargs["preexec_fn"] = preexec

    timed_out = False
    try:
        with _locked(lock_path):
            proc = subprocess.run(list(argv), timeout=timeout_s, check=False, **kwargs)
        stdout, stderr, returncode = proc.stdout, proc.stderr, proc.returncode
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", "replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", "replace")
        returncode = -1

    return RunResult(
        argv=tuple(str(item) for item in argv),
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        duration_s=time.monotonic() - started,
        timed_out=timed_out,
    )


def run_script(
    config: BlenderConfig,
    script: str | Path,
    args: Sequence[object] = (),
    *,
    cwd: str | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> RunResult:
    """Run ``script`` inside Blender headless with the configured limits."""
    if not Path(script).is_file():
        raise BlenderError(f"script not found: {script}")
    argv = build_script_argv(config, script, args)
    return run(
        argv,
        timeout_s=config.timeout_s,
        memory_mb=config.memory_mb,
        lock_path=config.lock_path,
        cwd=cwd,
        env=env,
    )
