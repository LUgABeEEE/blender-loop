"""Command line interface: ``blender-loop <command>``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .bench import run_benchmark
from .blender import BlenderConfig, BlenderError
from .demo import demo_summary, run_demo
from .pipeline import LoopResult
from .report import render_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="blender-loop",
        description="Headless Blender modeling, machine tuning and self-iteration loops.",
    )
    parser.add_argument("--version", action="version", version=f"blender-loop {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    version = sub.add_parser("version", help="print the package version as JSON")
    version.set_defaults(handler="version")

    bench = sub.add_parser("bench", help="measure render/boolean cost on this machine")
    bench.add_argument("--out", default="out/bench", help="output directory (default: out/bench)")
    _add_blender_args(bench)
    bench.set_defaults(handler="bench")

    demo = sub.add_parser("demo", help="run the silhouette self-iteration demo")
    demo.add_argument("--out", default="out/demo", help="output directory (default: out/demo)")
    demo.add_argument("--resolution", type=int, default=128, help="render size in pixels")
    demo.add_argument("--rounds", type=int, default=4, help="coordinate-descent rounds")
    demo.add_argument("--budget", type=int, default=60, help="maximum evaluations")
    _add_blender_args(demo)
    demo.set_defaults(handler="demo")

    report = sub.add_parser("report", help="render an HTML report from a history.json")
    report.add_argument("--history", required=True, help="path to history.json")
    report.add_argument("--out", default="out/report.html", help="output HTML path")
    report.add_argument("--title", default="Self-iteration report", help="report title")
    report.set_defaults(handler="report")
    return parser


def _add_blender_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--blender", default="blender", help="Blender binary (default: blender on PATH)")
    parser.add_argument("--memory-mb", type=int, default=8192, help="address-space cap per process")
    parser.add_argument("--timeout", type=float, default=900.0, help="per-call timeout in seconds")
    parser.add_argument("--lock", default=None, help="optional global lock file (serialise runs)")


def _config(args: argparse.Namespace) -> BlenderConfig:
    return BlenderConfig(
        binary=args.blender,
        memory_mb=args.memory_mb,
        timeout_s=args.timeout,
        lock_path=Path(args.lock) if args.lock else None,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.handler == "version":
        print(json.dumps({"name": "blender-loop", "version": __version__}))
        return 0

    if args.handler == "report":
        result = LoopResult.load(args.history)
        path = render_report(result, args.out, title=args.title)
        print(f"report -> {path}")
        return 0

    try:
        config = _config(args)
        if args.handler == "bench":
            report = run_benchmark(config, args.out)
            print(f"Blender: {report['blender_version']}")
            for item in report["measured"]["renders"]:
                print(
                    f"render {item['resolution']:>4}px/{item['samples']:>2}spp: "
                    f"{item['seconds']:.3f}s"
                )
            boolean = report["measured"]["boolean"]
            print(f"exact boolean: {boolean['seconds']:.3f}s ({boolean['vertices']} verts)")
            print(f"written -> {Path(args.out) / 'bench.html'}")
            return 0
        if args.handler == "demo":
            result = run_demo(
                config,
                args.out,
                resolution=args.resolution,
                rounds=args.rounds,
                budget=args.budget,
            )
            print(demo_summary(config, result))
            print(f"history -> {Path(args.out) / 'history.json'}")
            print(f"report  -> {Path(args.out) / 'report.html'}")
            return 0
    except BlenderError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
