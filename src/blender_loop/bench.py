"""Machine-tuning benchmark: measure what this box actually does in Blender.

Reports Blender version, CPU/RAM, cold-start cost, render time per
resolution/sample count and the cost of one exact Boolean. Run it before a
long loop so budgets and timeouts are based on measurements, not guesses.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
from pathlib import Path

from .blender import BlenderConfig, require_blender, run_script, version

__all__ = ["BENCH_RENDERS", "benchmark", "collect_host_info", "run_benchmark"]

#: ``(resolution, samples)`` pairs measured by the benchmark script.
BENCH_RENDERS: tuple[tuple[int, int], ...] = (
    (128, 1),
    (512, 1),
    (1024, 1),
    (512, 16),
    (1024, 16),
    (1024, 64),
)

BENCH_SCRIPT = r'''
import bpy, json, math, sys, time

argv = sys.argv[sys.argv.index("--") + 1:]
out_json, pairs_json = argv[0], argv[1]
pairs = json.loads(pairs_json)
result = {"engine": "CYCLES", "device": "CPU", "renders": [], "boolean": {}}

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.mesh.primitive_uv_sphere_add(segments=64, ring_count=32, radius=1.0)
shape = bpy.context.active_object
shape.name = "bench_shape"

scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.use_denoising = False
scene.render.film_transparent = True
scene.render.image_settings.file_format = "PNG"

camera_data = bpy.data.cameras.new("camera")
camera_data.type = "ORTHO"
camera_data.ortho_scale = 4.0
camera = bpy.data.objects.new("camera", camera_data)
scene.collection.objects.link(camera)
camera.location = (0.0, -8.0, 0.0)
camera.rotation_euler = (math.pi / 2.0, 0.0, 0.0)
scene.camera = camera

scene.render.filepath = "/dev/null"
for resolution, samples in pairs:
    scene.render.resolution_x = resolution
    scene.render.resolution_y = resolution
    scene.cycles.samples = samples
    started = time.perf_counter()
    bpy.ops.render.render(write_still=False)
    result["renders"].append(
        {
            "resolution": resolution,
            "samples": samples,
            "seconds": round(time.perf_counter() - started, 3),
        }
    )

# One EXACT Boolean on a moderately dense mesh (the usual memory suspect).
bpy.ops.mesh.primitive_uv_sphere_add(segments=64, ring_count=32, radius=1.0)
target = bpy.context.active_object
target.name = "boolean_target"
subdivision = target.modifiers.new("subdivision", "SUBSURF")
subdivision.levels = 2
subdivision.render_levels = 2
bpy.context.view_layer.objects.active = target
target.select_set(True)
bpy.ops.object.modifier_apply(modifier="subdivision")

bpy.ops.mesh.primitive_cube_add(size=1.2, location=(0.4, 0.0, 0.2))
cutter = bpy.context.active_object
target.select_set(False)

boolean = target.modifiers.new("cut", "BOOLEAN")
boolean.operation = "DIFFERENCE"
boolean.solver = "EXACT"
boolean.object = cutter
bpy.context.view_layer.objects.active = target
target.select_set(True)

started = time.perf_counter()
bpy.ops.object.modifier_apply(modifier="cut")
result["boolean"] = {
    "seconds": round(time.perf_counter() - started, 3),
    "vertices": len(target.data.vertices),
    "polygons": len(target.data.polygons),
}

with open(out_json, "w", encoding="utf-8") as handle:
    json.dump(result, handle, indent=1)
print("BLENDER_LOOP_BENCH_OK")
'''

STARTUP_SCRIPT = "print('BLENDER_LOOP_STARTUP_OK')\n"


def collect_host_info() -> dict[str, object]:
    """Static facts about the machine (no Blender needed)."""
    try:
        import resource

        max_rss_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
    except Exception:  # pragma: no cover - non-POSIX
        max_rss_mb = None
    info: dict[str, object] = {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "cpu_count": os.cpu_count(),
        "max_rss_mb": round(max_rss_mb, 1) if max_rss_mb else None,
    }
    try:
        info["mem_total_mb"] = round(
            os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1024**2
        )
    except (ValueError, OSError, AttributeError):
        pass
    info["blender_on_path"] = shutil.which("blender") or None
    return info


def _peak_child_rss_mb() -> float | None:
    try:
        import resource

        return round(resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024.0, 1)
    except Exception:  # pragma: no cover - non-POSIX
        return None


def benchmark(config: BlenderConfig, outdir: str | Path) -> dict[str, object]:
    """Run the Blender benchmark script and merge in host facts."""
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    script = outdir / "blender_bench.py"
    script.write_text(BENCH_SCRIPT, encoding="utf-8")
    startup_script = outdir / "blender_startup.py"
    startup_script.write_text(STARTUP_SCRIPT, encoding="utf-8")
    raw_json = outdir / "bench_raw.json"

    require_blender(config)
    startup = run_script(config, startup_script)
    startup.check()
    measured_run = run_script(config, script, [raw_json, json.dumps(BENCH_RENDERS)])
    measured_run.check()
    measured = json.loads(raw_json.read_text(encoding="utf-8"))

    report: dict[str, object] = {
        "version": 1,
        "blender_version": version(config),
        "host": collect_host_info(),
        "startup_seconds": round(startup.duration_s, 3),
        "peak_child_rss_mb": _peak_child_rss_mb(),
        "measured": measured,
    }
    (outdir / "bench.json").write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    (outdir / "bench.html").write_text(_render_html(report), encoding="utf-8")
    return report


def _render_html(report: dict[str, object]) -> str:
    host = report.get("host", {})
    measured = report.get("measured", {})
    renders = measured.get("renders", []) if isinstance(measured, dict) else []
    rows = "".join(
        f"<tr><td>{item['resolution']} × {item['resolution']}</td>"
        f"<td class='num'>{item['samples']}</td>"
        f"<td class='num'>{item['seconds']:.3f} s</td></tr>"
        for item in renders
    )
    boolean = measured.get("boolean", {}) if isinstance(measured, dict) else {}
    host_rows = "".join(f"<tr><td>{key}</td><td>{value}</td></tr>" for key, value in host.items())
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Blender machine benchmark</title>
<style>
body{{font:15px/1.6 -apple-system,"Segoe UI",Roboto,sans-serif;max-width:760px;
margin:40px auto;padding:0 20px;color:#1d2330}}
table{{width:100%;border-collapse:collapse;margin:12px 0 28px}}
th,td{{padding:8px 10px;border-bottom:1px solid #e3e8f0;text-align:left}}
th{{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:#5b6678}}
td.num{{text-align:right;font-variant-numeric:tabular-nums}}
h1{{font-size:24px}} h2{{font-size:17px;margin-top:28px}}
</style></head><body>
<h1>Blender machine benchmark</h1>
<p>{report.get('blender_version')} · {host.get('platform')}</p>
<h2>Host</h2><table>{host_rows}</table>
<h2>Process baseline</h2>
<table><tr><td>Cold start (headless, no scene)</td>
<td class="num">{report.get('startup_seconds')} s</td></tr>
<tr><td>Peak child RSS (all runs)</td>
<td class="num">{report.get('peak_child_rss_mb')} MB</td></tr></table>
<h2>Cycles render (CPU)</h2>
<table><thead><tr><th>Resolution</th><th class="num">Samples</th><th class="num">Time</th></tr></thead>
<tbody>{rows}</tbody></table>
<h2>One EXACT Boolean</h2>
<table><tr><td>Time</td><td class="num">{boolean.get('seconds')} s</td></tr>
<tr><td>Result</td><td>{boolean.get('vertices')} vertices / {boolean.get('polygons')} polygons</td></tr></table>
</body></html>
"""


def run_benchmark(config: BlenderConfig, outdir: str | Path) -> dict[str, object]:
    """Alias kept for a friendlier CLI name."""
    return benchmark(config, outdir)
