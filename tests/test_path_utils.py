import os
import tempfile
import unittest
from unittest.mock import patch

from blink_app.services.path_utils import ensure_writable_directory, resolve_runtime_output_dir


class PathUtilsTest(unittest.TestCase):
    def test_ensure_writable_directory_creates_and_returns_absolute_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            writable_dir = os.path.join(tmp_dir, "output")

            resolved_path = ensure_writable_directory(writable_dir)

            self.assertTrue(os.path.isabs(resolved_path))
            self.assertTrue(os.path.isdir(resolved_path))
            probe_path = os.path.join(resolved_path, "probe.txt")
            with open(probe_path, "w", encoding="utf-8") as handle:
                handle.write("ok")
            self.assertTrue(os.path.exists(probe_path))

    def test_resolve_runtime_output_dir_returns_requested_path_when_writable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = os.path.join(tmp_dir, "runtime")

            resolved_path, warning_message = resolve_runtime_output_dir(
                output_dir,
                allow_fallback=True,
            )

            self.assertEqual(resolved_path, os.path.abspath(output_dir))
            self.assertIsNone(warning_message)

    def test_resolve_runtime_output_dir_raises_without_fallback(self) -> None:
        with patch(
            "blink_app.services.path_utils.ensure_writable_directory",
            side_effect=PermissionError("denied"),
        ):
            with self.assertRaises(PermissionError):
                resolve_runtime_output_dir(".", allow_fallback=False)

    def test_resolve_runtime_output_dir_falls_back_when_enabled(self) -> None:
        fallback_dir = os.path.join("C:\\", "Users", "tester", "AppData", "Local", "BlinkTracker")
        with patch(
            "blink_app.services.path_utils.ensure_writable_directory",
            side_effect=[PermissionError("denied"), fallback_dir],
        ):
            with patch(
                "blink_app.services.path_utils.default_output_dir",
                return_value=fallback_dir,
            ):
                resolved_path, warning_message = resolve_runtime_output_dir(
                    ".",
                    allow_fallback=True,
                )

        self.assertEqual(resolved_path, fallback_dir)
        self.assertIsNotNone(warning_message)
        self.assertIn("not writable", warning_message or "")
        self.assertIn(fallback_dir, warning_message or "")

    def test_resolve_runtime_output_dir_raises_when_fallback_is_unwritable(self) -> None:
        with patch(
            "blink_app.services.path_utils.ensure_writable_directory",
            side_effect=[PermissionError("denied"), PermissionError("still denied")],
        ):
            with patch(
                "blink_app.services.path_utils.default_output_dir",
                return_value=os.path.join("C:\\", "Users", "tester", "AppData", "Local", "BlinkTracker"),
            ):
                with self.assertRaises(PermissionError) as context:
                    resolve_runtime_output_dir(".", allow_fallback=True)

        self.assertIn("still denied", str(context.exception))


if __name__ == "__main__":
    unittest.main()
