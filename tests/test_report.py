"""Unit tests for the HTML report writer."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from blender_loop.params import ParamSpec, SearchSpace
from blender_loop.pipeline import Evaluation, LoopResult
from blender_loop.report import render_report


def build_result() -> LoopResult:
    space = SearchSpace([ParamSpec("x", 0.0, 10.0), ParamSpec("y", 0.0, 10.0)])
    history = [
        Evaluation(params={"x": 1.0, "y": 1.0}, score=0.25, duration_s=0.1),
        Evaluation(params={"x": 2.0, "y": 3.0}, score=0.50, duration_s=0.2),
        Evaluation(params={"x": 4.0, "y": 2.0}, score=0.81, duration_s=0.3),
    ]
    return LoopResult(best=history[-1], history=history, space=space)


class ReportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="blender-loop-report-"))

    def test_writes_self_contained_html(self) -> None:
        path = render_report(build_result(), self.tmp / "report.html", title="Demo run")
        document = path.read_text(encoding="utf-8")
        self.assertTrue(path.is_file())
        self.assertIn("<title>Demo run</title>", document)
        self.assertIn("Best parameters", document)
        self.assertIn("0.8100", document)
        self.assertNotIn("<script", document.lower())

    def test_escapes_user_supplied_text(self) -> None:
        path = render_report(
            build_result(),
            self.tmp / "escaped.html",
            title='<script>alert("x")</script>',
        )
        document = path.read_text(encoding="utf-8")
        self.assertNotIn('<script>alert("x")</script>', document)
        self.assertIn("&lt;script&gt;", document)

    def test_embeds_images_as_base64(self) -> None:
        image = Image.new("RGBA", (8, 8), (255, 0, 0, 255))
        png = self.tmp / "mask.png"
        image.save(png)
        path = render_report(
            build_result(),
            self.tmp / "with-image.html",
            images={"target": png},
        )
        document = path.read_text(encoding="utf-8")
        self.assertIn("data:image/png;base64,", document)
        self.assertIn("Artifacts", document)

    def test_handles_empty_history(self) -> None:
        result = LoopResult(best=None, history=[])
        path = render_report(result, self.tmp / "empty.html")
        document = path.read_text(encoding="utf-8")
        self.assertIn("no evaluations", document)


if __name__ == "__main__":
    unittest.main()
