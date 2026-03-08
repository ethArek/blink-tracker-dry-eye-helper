import argparse
import unittest

from blink_app.cli import (
    ear_threshold_value,
    non_negative_int,
    parse_args,
    positive_float,
    positive_int,
)
from blink_app.constants import (
    CAMERA_STARTUP_TIMEOUT_SECONDS,
    FACEMESH_MAX_WIDTH,
    FACEMESH_REFINE_LANDMARKS,
)


class CliParseArgsTest(unittest.TestCase):
    def test_defaults(self) -> None:
        args = parse_args([])
        self.assertEqual(args.camera_index, 0)
        self.assertEqual(args.camera_startup_timeout_seconds, CAMERA_STARTUP_TIMEOUT_SECONDS)
        self.assertEqual(args.facemesh_max_width, FACEMESH_MAX_WIDTH)
        self.assertEqual(args.refine_landmarks, FACEMESH_REFINE_LANDMARKS)
        self.assertFalse(args.enable_alerts)

    def test_enable_alerts_flag(self) -> None:
        args = parse_args(["--enable-alerts"])
        self.assertTrue(args.enable_alerts)

    def test_disable_alerts_flag(self) -> None:
        args = parse_args(["--disable-alerts"])
        self.assertFalse(args.enable_alerts)

    def test_refine_landmarks_flag(self) -> None:
        args = parse_args(["--refine-landmarks"])
        self.assertTrue(args.refine_landmarks)

    def test_conflicting_alert_flags_fail(self) -> None:
        with self.assertRaises(SystemExit) as context:
            parse_args(["--enable-alerts", "--disable-alerts"])
        self.assertEqual(context.exception.code, 2)

    def test_invalid_ear_threshold_fails(self) -> None:
        with self.assertRaises(SystemExit) as context:
            parse_args(["--ear-threshold", "1.2"])
        self.assertEqual(context.exception.code, 2)

    def test_invalid_ear_consec_frames_fails(self) -> None:
        with self.assertRaises(SystemExit) as context:
            parse_args(["--ear-consec-frames", "0"])
        self.assertEqual(context.exception.code, 2)

    def test_invalid_fps_fails(self) -> None:
        with self.assertRaises(SystemExit) as context:
            parse_args(["--fps", "0"])
        self.assertEqual(context.exception.code, 2)

    def test_invalid_camera_startup_timeout_fails(self) -> None:
        with self.assertRaises(SystemExit) as context:
            parse_args(["--camera-startup-timeout-seconds", "0"])
        self.assertEqual(context.exception.code, 2)

    def test_invalid_facemesh_max_width_fails(self) -> None:
        with self.assertRaises(SystemExit) as context:
            parse_args(["--facemesh-max-width", "0"])
        self.assertEqual(context.exception.code, 2)

    def test_custom_camera_startup_timeout_is_applied(self) -> None:
        args = parse_args(["--camera-startup-timeout-seconds", "2.5"])
        self.assertEqual(args.camera_startup_timeout_seconds, 2.5)

    def test_custom_facemesh_max_width_is_applied(self) -> None:
        args = parse_args(["--facemesh-max-width", "512"])
        self.assertEqual(args.facemesh_max_width, 512)

    def test_non_negative_int_rejects_invalid_values(self) -> None:
        with self.assertRaises(argparse.ArgumentTypeError):
            non_negative_int("abc")
        with self.assertRaises(argparse.ArgumentTypeError):
            non_negative_int("-1")

    def test_positive_int_rejects_invalid_values(self) -> None:
        with self.assertRaises(argparse.ArgumentTypeError):
            positive_int("abc")
        with self.assertRaises(argparse.ArgumentTypeError):
            positive_int("0")

    def test_positive_float_rejects_invalid_values(self) -> None:
        with self.assertRaises(argparse.ArgumentTypeError):
            positive_float("abc")
        with self.assertRaises(argparse.ArgumentTypeError):
            positive_float("0")

    def test_ear_threshold_value_accepts_in_range_value(self) -> None:
        self.assertEqual(ear_threshold_value("0.25"), 0.25)

    def test_version_exits_cleanly(self) -> None:
        with self.assertRaises(SystemExit) as context:
            parse_args(["--version"])
        self.assertEqual(context.exception.code, 0)


if __name__ == "__main__":
    unittest.main()
