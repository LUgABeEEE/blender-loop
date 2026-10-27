"""Generate a single-file HTML report for a loop run.

The report is deliberately dependency-free: inline CSS, an inline SVG score
chart, optional base64-embedded images and a table of every evaluation.
"""

from __future__ import annotations

import base64
import html
import math
from collections.abc import Mapping
from pathlib import Path

from .pipeline import LoopResult

__all__ = ["render_report"]

_CSS = """
:root { color-scheme: light dark; --fg:#1d2330; --muted:#5b6678; --bg:#fbfcfe;
  --card:#fff; --line:#e3e8f0; --accent:#2f6df6; --good:#1a9b62; }
@media (prefers-color-scheme: dark) {
  :root { --fg:#e8edf6; --muted:#9aa7bb; --bg:#12161d; --card:#1a2029;
    --line:#2a3340; --accent:#6f9bff; --good:#3ddc97; }
}
* { box-sizing: border-box; }
body { margin:0; font:15px/1.6 -apple-system,"Segoe UI",Roboto,"PingFang SC",
  "Microsoft YaHei",sans-serif; color:var(--fg); background:var(--bg); }
main { max-width: 980px; margin: 0 auto; padding: 40px 24px 64px; }
h1 { font-size: 26px; margin: 0 0 4px; }
.sub { color: var(--muted); margin: 0 0 28px; }
.cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:12px; }
.card { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:14px 16px; }
.card .k { color:var(--muted); font-size:12px; letter-spacing:.04em; text-transform:uppercase; }
.card .v { font-size:22px; font-weight:650; margin-top:4px; font-variant-numeric:tabular-nums; }
section { margin-top: 34px; }
h2 { font-size: 18px; margin: 0 0 12px; }
table { width:100%; border-collapse:collapse; background:var(--card);
  border:1px solid var(--line); border-radius:12px; overflow:hidden; font-size:14px; }
th, td { padding:8px 10px; border-bottom:1px solid var(--line); text-align:left; }
th { color:var(--muted); font-weight:600; font-size:12px; letter-spacing:.04em;
  text-transform:uppercase; background:var(--bg); }
tr:last-child td { border-bottom:0; }
td.num { font-variant-numeric: tabular-nums; text-align:right; }
tr.best td { background: color-mix(in srgb, var(--good) 12%, transparent); font-weight:600; }
.figs { display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:12px; }
.figs figure { margin:0; background:var(--card); border:1px solid var(--line);
  border-radius:12px; padding:10px; }
.figs img { width:100%; height:auto; display:block; border-radius:8px; image-rendering: pixelated; }
.figs figcaption { color:var(--muted); font-size:12px; margin-top:6px; }
code { font-family: ui-monospace,SFMono-Regular,Menlo,monospace; font-size:13px; }
footer { margin-top: 44px; color: var(--muted); font-size: 12px; }
"""


def _fmt(value: float) -> str:
    return f"{value:.4f}" if abs(value) < 1e4 else f"{value:.2e}"


def _score_chart(scores: list[float], width: int = 860, height: int = 220) -> str:
    if not scores:
        return "<p>no evaluations</p>"
    pad = 28
    lo, hi = min(scores), max(scores)
    if math.isclose(lo, hi):
        lo, hi = lo - 1.0, hi + 1.0
    inner_w, inner_h = width - 2 * pad, height - 2 * pad
    step = inner_w / max(len(scores) - 1, 1)
    points = []
    for index, score in enumerate(scores):
        x = pad + index * step
        y = pad + inner_h - (score - lo) / (hi - lo) * inner_h
        points.append(f"{x:.1f},{y:.1f}")
    labels = (
        f'<text x="{pad}" y="{height - 6}" fill="currentColor" font-size="11"'
        f' opacity="0.6">iteration 1</text>'
        f'<text x="{width - pad}" y="{height - 6}" fill="currentColor" font-size="11"'
        f' text-anchor="end" opacity="0.6">{len(scores)}</text>'
        f'<text x="{pad}" y="16" fill="currentColor" font-size="11" opacity="0.6">'
        f'max {hi:.3f}</text>'
        f'<text x="{pad}" y="{pad + inner_h + 12}" fill="currentColor" font-size="11"'
        f' opacity="0.6">min {lo:.3f}</text>'
    )
    return (
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="score per evaluation"'
        f' style="width:100%;height:auto;background:var(--card);border:1px solid var(--line);'
        f'border-radius:12px">'
        f'<polyline fill="none" stroke="var(--accent)" stroke-width="2" '
        f'points="{" ".join(points)}"/>'
        f"{labels}</svg>"
    )


def _embed(path: Path) -> str:
    suffix = path.suffix.lower().lstrip(".") or "png"
    mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "gif": "image/gif", "webp": "image/webp"}.get(suffix, "application/octet-stream")
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{data}"


def _figures(images: Mapping[str, Path], embed: bool) -> str:
    blocks = []
    for caption, path in images.items():
        if not path.is_file():
            continue
        src = _embed(path) if embed else path.as_uri()
        blocks.append(
            f"<figure><img src='{src}' alt='{html.escape(caption)}'>"
            f"<figcaption>{html.escape(caption)}</figcaption></figure>"
        )
    if not blocks:
        return ""
    return f'<section><h2>Artifacts</h2><div class="figs">{"".join(blocks)}</div></section>'


def render_report(
    result: LoopResult,
    out_html: str | Path,
    *,
    title: str = "Self-iteration report",
    images: Mapping[str, Path] | None = None,
    embed_images: bool = True,
    max_rows: int = 60,
) -> Path:
    """Write ``out_html`` and return its path."""
    out_html = Path(out_html)
    out_html.parent.mkdir(parents=True, exist_ok=True)

    scores = result.scores
    best = result.best
    param_names = list(best.params) if best else []

    cards = [
        ("Evaluations", str(len(scores))),
        ("Best score", _fmt(best.score) if best else "—"),
        ("Score range", f"{_fmt(min(scores))} → {_fmt(max(scores))}" if scores else "—"),
        ("Best params", ", ".join(f"{name}={best.params[name]:.4g}" for name in param_names)
         if best else "—"),
    ]
    cards_html = "".join(
        f'<div class="card"><div class="k">{html.escape(k)}</div>'
        f'<div class="v">{html.escape(v)}</div></div>'
        for k, v in cards
    )

    rows = []
    best_key = tuple(sorted((name, round(value, 9)) for name, value in best.params.items())) if best else ()
    for index, item in enumerate(result.history[-max_rows:], start=len(result.history) - min(
            len(result.history), max_rows) + 1):
        cells = "".join(f'<td class="num">{item.params.get(name, float("nan")):.4g}</td>'
                        for name in param_names)
        key = tuple(sorted((name, round(value, 9)) for name, value in item.params.items()))
        row_class = ' class="best"' if key == best_key else ""
        rows.append(
            f"<tr{row_class}><td class='num'>{index}</td>{cells}"
            f"<td class='num'>{_fmt(item.score)}</td>"
            f"<td class='num'>{item.duration_s:.2f}s</td></tr>"
        )
    head_cells = "".join(f"<th>{html.escape(name)}</th>" for name in param_names)
    table = (
        "<table><thead><tr><th>#</th>"
        f"{head_cells}<th class='num'>score</th><th class='num'>time</th>"
        "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    ) if rows else "<p>no evaluations recorded</p>"

    figures = _figures(images or {}, embed_images)
    best_json = html.escape(
        repr(best.params) if best else "{}",
    )
    document = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>{_CSS}</style>
</head>
<body>
<main>
  <h1>{html.escape(title)}</h1>
  <p class="sub">Closed-loop parameter fitting · generated by
    <code>blender-loop</code></p>
  <div class="cards">{cards_html}</div>

  <section>
    <h2>Score per evaluation</h2>
    {_score_chart(scores)}
  </section>

  <section>
    <h2>Evaluations</h2>
    {table}
  </section>

  <section>
    <h2>Best parameters</h2>
    <pre><code>{best_json}</code></pre>
  </section>

  {figures}

  <footer>Deterministic by construction: every evaluation is cached by a
    content hash of its parameter vector.</footer>
</main>
</body>
</html>
"""
    out_html.write_text(document, encoding="utf-8")
    return out_html
