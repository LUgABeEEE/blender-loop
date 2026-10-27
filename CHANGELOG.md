# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-10-27

### Added

- `SearchSpace` / `ParamSpec`: bounded parameters, sampling, quantisation and
  content hashing for cache keys.
- `coordinate_descent` and `random_search` with an interruptible budget.
- `Loop`: cached, budgeted evaluation loop with JSON history.
- `blender` runner: `RLIMIT_AS` cap, `flock` serialisation, timeouts and a
  structured `RunResult`.
- Mask metrics: IoU, RMSE, pixel agreement, centroid and bounding box.
- Single-file HTML report with inline SVG score chart and base64 images.
- `blender-loop demo`: end-to-end silhouette self-iteration example.
- `blender-loop bench`: machine benchmark (startup, render, boolean, RSS).
- 54 unit tests that run without Blender; GitHub Actions CI.
