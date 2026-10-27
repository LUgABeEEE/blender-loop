"""Unit tests for the supervised Blender process wrapper (no Blender required)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from blender_loop.blender import (
    BlenderConfig,
    BlenderError,
    build_script_argv,
    require_blender,
    run,
    run_script,
)


class CommandLineTests(unittest.TestCase):
    def test_build_script_argv(self) -> None:
        config = BlenderConfig(binary="/opt/blender/blender")
        argv = build_script_argv(config, "/tmp/eval.py", ["a", 1, {"x": 2}])
        self.assertEqual(
            argv,
            [
                "/opt/blender/blender",
                "-b",
                "--factory-startup",
                "-P",
                "/tmp/eval.py",
                "--",
                "a",
                "1",
                "{'x': 2}",
            ],
        )

    def test_extra_args_come_before_script(self) -> None:
        config = BlenderConfig(binary="blender", extra_args=("--debug",))
        argv = build_script_argv(config, "eval.py")
        self.assertEqual(argv[3], "--debug")

    def test_require_blender_resolves_executable(self) -> None:
        self.assertEqual(require_blender(BlenderConfig(binary=sys.executable)), sys.executable)

    def test_require_blender_rejects_missing(self) -> None:
        with self.assertRaises(BlenderError):
            require_blender(BlenderConfig(binary="/nonexistent/blender-binary"))

    def test_config_validation(self) -> None:
        with self.assertRaises(BlenderError):
            BlenderConfig(memory_mb=0)
        with self.assertRaises(BlenderError):
            BlenderConfig(timeout_s=-1)

    def test_run_script_rejects_missing_file(self) -> None:
        with self.assertRaises(BlenderError):
            run_script(BlenderConfig(binary=sys.executable), "/nonexistent/eval.py")


class RunTests(unittest.TestCase):
    def test_success_captures_output(self) -> None:
        result = run([sys.executable, "-c", "print('hello')"])
        self.assertTrue(result.ok)
        self.assertEqual(result.stdout.strip(), "hello")
        self.assertGreaterEqual(result.duration_s, 0.0)

    def test_failure_is_not_ok_and_check_raises(self) -> None:
        result = run([sys.executable, "-c", "import sys; sys.exit(3)"])
        self.assertFalse(result.ok)
        self.assertEqual(result.returncode, 3)
        with self.assertRaises(BlenderError):
            result.check()

    def test_timeout_is_reported(self) -> None:
        result = run([sys.executable, "-c", "import time; time.sleep(5)"], timeout_s=0.3)
        self.assertTrue(result.timed_out)
        self.assertFalse(result.ok)

    def test_memory_limit_applies_to_child(self) -> None:
        script = "import resource; print(resource.getrlimit(resource.RLIMIT_AS)[0])"
        result = run([sys.executable, "-c", script], memory_mb=256)
        self.assertTrue(result.ok)
        self.assertEqual(result.stdout.strip(), str(256 * 1024 * 1024))

    def test_lock_file_is_created(self) -> None:
        lock = Path(tempfile.mkdtemp(prefix="blender-loop-lock-")) / "nested" / "blender.lock"
        result = run([sys.executable, "-c", "print('locked')"], lock_path=lock)
        self.assertTrue(result.ok)
        self.assertTrue(lock.exists())


if __name__ == "__main__":
    unittest.main()
