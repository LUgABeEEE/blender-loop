"""End-to-end demo: recover a shape's parameters from its own silhouette.

The loop never sees the target parameters. It renders a candidate, compares
the silhouette with a target render (intersection-over-union) and lets
coordinate descent walk back towards the target.
"""

from __future__ import annotations

import json
from pathlib import Path

from .blender import BlenderConfig, require_blender, run_script, version
from .metrics import load_mask, silhouette_metrics
from .params import ParamSpec, SearchSpace
from .pipeline import Evaluation, Loop, LoopResult
from .report import render_report

__all__ = ["SPACE", "TARGET_PARAMS", "run_demo"]

BLENDER_SCRIPT = r'''
import bpy, json, math, sys

argv = sys.argv[sys.argv.index("--") + 1:]
params = json.loads(argv[0])
out_png = argv[1]
resolution = int(argv[2]) if len(argv) > 2 else 128

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.mesh.primitive_uv_sphere_add(segments=64, ring_count=32, radius=1.0)
shape = bpy.context.active_object
shape.name = "shape"
shape.scale = (params["width"] / 2.0, 0.5, params["height"] / 2.0)
shape.location = (params["offset_x"], 0.0, 0.0)

scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = 1
scene.cycles.use_denoising = False
scene.render.resolution_x = resolution
scene.render.resolution_y = resolution
scene.render.resolution_percentage = 100
scene.render.film_transparent = True
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGBA"
scene.render.filepath = out_png

camera_data = bpy.data.cameras.new("camera")
camera_data.type = "ORTHO"
camera_data.ortho_scale = 4.0
camera = bpy.data.objects.new("camera", camera_data)
scene.collection.objects.link(camera)
camera.location = (0.0, -8.0, 0.0)
camera.rotation_euler = (math.pi / 2.0, 0.0, 0.0)
scene.camera = camera

material = bpy.data.materials.new("silhouette")
material.use_nodes = True
nodes = material.node_tree.nodes
for node in list(nodes):
    nodes.remove(node)
emission = nodes.new("ShaderNodeEmission")
emission.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
emission.inputs["Strength"].default_value = 1.0
output = nodes.new("ShaderNodeOutputMaterial")
material.node_tree.links.new(emission.outputs["Emission"], output.inputs["Surface"])
shape.data.materials.append(material)

bpy.ops.render.render(write_still=True)
print("BLENDER_LOOP_RENDER_OK")
'''

#: The space the search may move in.
SPACE = SearchSpace(
    [
        ParamSpec("width", 0.4, 2.0, default=1.0),
        ParamSpec("height", 0.3, 1.6, default=1.0),
        ParamSpec("offset_x", -0.6, 0.6, default=0.0),
    ]
)

#: Hidden ground truth used only to render the target image.
TARGET_PARAMS = {"width": 1.42, "height": 0.74, "offset_x": 0.22}


def run_demo(
    config: BlenderConfig,
    outdir: str | Path,
    *,
    resolution: int = 128,
    rounds: int = 4,
    budget: int = 60,
) -> LoopResult:
    """Run the silhouette demo and write history + HTML report under ``outdir``."""
    outdir = Path(outdir)
    renders = outdir / "renders"
    renders.mkdir(parents=True, exist_ok=True)

    require_blender(config)
    script = outdir / "blender_eval.py"
    script.write_text(BLENDER_SCRIPT, encoding="utf-8")

    target_png = outdir / "target.png"
    run_script(
        config, script, [json.dumps(TARGET_PARAMS, sort_keys=True), target_png, resolution]
    ).check()
    target_mask = load_mask(target_png)

    counter = {"n": 0}

    def evaluate(params: dict[str, float], workdir: Path) -> Evaluation:
        counter["n"] += 1
        png = workdir / "renders" / f"eval_{counter['n']:03d}.png"
        result = run_script(config, script, [json.dumps(params, sort_keys=True), png, resolution])
        result.check()
        metrics = silhouette_metrics(load_mask(png), target_mask)
        return Evaluation(
            params=dict(params),
            score=metrics["iou"],
            metrics=metrics,
            artifacts=[str(png)],
        )

    loop = Loop(
        SPACE,
        evaluate,
        outdir / "work",
        budget=budget,
        maximize=True,
    )
    result = loop.run_coordinate_descent(rounds=rounds)
    result.save(outdir / "history.json")

    images: dict[str, Path] = {"Target silhouette": target_png}
    if result.best and result.best.artifacts:
        images["Best render"] = Path(result.best.artifacts[0])
    if result.history and result.history[0].artifacts:
        images["First render"] = Path(result.history[0].artifacts[0])
    render_report(
        result,
        outdir / "report.html",
        title="Silhouette self-iteration demo",
        images=images,
    )
    return result


def demo_summary(config: BlenderConfig, result: LoopResult) -> str:
    """Human-readable one-screen summary printed by the CLI."""
    lines = [f"Blender: {version(config)}"]
    if result.best:
        lines.append(f"best score (IoU): {result.best.score:.4f}")
        lines.append("best params: " + json.dumps(result.best.params, sort_keys=True))
    lines.append(f"evaluations: {len(result.history)}")
    return "\n".join(lines)
