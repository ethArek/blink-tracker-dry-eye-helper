import contextlib
import os
import unittest
from unittest.mock import patch

from blink_app.services.path_utils import ensure_writable_directory, resolve_runtime_output_dir


class PathUtilsTest(unittest.TestCase):
    def test_ensure_writable_directory_creates_and_returns_absolute_path(self) -> None:
        requested_path = os.path.join("relative", "output")
        expected_path = os.path.abspath(requested_path)

        with patch("blink_app.services.path_utils.os.makedirs") as makedirs_mock:
            with patch(
                "blink_app.services.path_utils.tempfile.NamedTemporaryFile",
                return_value=contextlib.nullcontext(None),
            ) as temp_file_mock:
                resolved_path = ensure_writable_directory(requested_path)

        self.assertEqual(resolved_path, expected_path)
        makedirs_mock.assert_called_once_with(expected_path, exist_ok=True)
        temp_file_mock.assert_called_once_with(dir=expected_path, delete=True)

    def test_resolve_runtime_output_dir_returns_requested_path_when_writable(self) -> None:
        expected_path = os.path.abspath(os.path.join("C:\\", "virtual-output", "runtime"))
        with patch(
            "blink_app.services.path_utils.ensure_writable_directory",
            return_value=expected_path,
        ):
            resolved_path, warning_message = resolve_runtime_output_dir(
                expected_path,
                allow_fallback=True,
            )

        self.assertEqual(resolved_path, expected_path)
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
