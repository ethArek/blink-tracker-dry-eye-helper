import logging
from types import SimpleNamespace
import unittest

try:
    from blink_app.domain.detection import BlinkState
    from blink_app.ui.window import BlinkWindow
except Exception as exc:  # pragma: no cover - environment-dependent
    BlinkWindow = None
    BlinkState = None
    IMPORT_ERROR = exc
else:
    IMPORT_ERROR = None


@unittest.skipIf(BlinkWindow is None, f"UI dependencies unavailable: {IMPORT_ERROR}")
class BlinkWindowOverlayTest(unittest.TestCase):
    def _build_dummy_window(
        self,
        calibration_seconds: float = 1.0,
        calibration_blinks: int = 0,
        ear_threshold: float = 0.21,
    ) -> SimpleNamespace:
        window = SimpleNamespace()
        window._args = SimpleNamespace(
            calibration_seconds=calibration_seconds,
            calibration_blinks=calibration_blinks,
            ear_threshold=ear_threshold,
        )
        window._app_logger = logging.getLogger("test.window.calibration")
        window._app_logger.addHandler(logging.NullHandler())
        window._blink_state = BlinkState(last_blink_time=0.0)
        window._percentile = lambda values, percentile: BlinkWindow._percentile(
            values,
            percentile,
        )
        window._stable_open_sample = lambda left_aperture, right_aperture: BlinkWindow._stable_open_sample(
            window,
            left_aperture,
            right_aperture,
        )
        window._apply_open_eye_calibration = lambda: BlinkWindow._apply_open_eye_calibration(window)
        window._finish_calibration = lambda now_ts: BlinkWindow._finish_calibration(window, now_ts)
        window._calibration = BlinkWindow._build_calibration_session(window)
        return window

    def test_eye_indicator_rect_builds_square_around_eye(self) -> None:
        rect = BlinkWindow._eye_indicator_rect(
            [
                (100.0, 120.0),
                (112.0, 116.0),
                (124.0, 120.0),
                (112.0, 124.0),
            ],
            frame_width=640,
            frame_height=480,
        )

        self.assertIsNotNone(rect)
        top_left, bottom_right = rect
        width = bottom_right[0] - top_left[0]
        height = bottom_right[1] - top_left[1]
        self.assertLessEqual(abs(width - height), 1)
        self.assertLess(top_left[0], 112)
        self.assertLess(top_left[1], 120)
        self.assertGreater(bottom_right[0], 112)
        self.assertGreater(bottom_right[1], 120)

    def test_eye_indicator_rect_returns_none_for_non_finite_landmarks(self) -> None:
        rect = BlinkWindow._eye_indicator_rect(
            [
                (100.0, 120.0),
                (float("nan"), 116.0),
                (124.0, 120.0),
            ],
            frame_width=640,
            frame_height=480,
        )

        self.assertIsNone(rect)

    def test_build_calibration_session_uses_requested_seconds_and_blinks(self) -> None:
        window = self._build_dummy_window(calibration_seconds=3.5, calibration_blinks=2)

        self.assertTrue(window._calibration.enabled)
        self.assertAlmostEqual(window._calibration.required_open_seconds, 3.5)
        self.assertEqual(window._calibration.blink_target_count, 2)

    def test_stable_open_sample_allows_smaller_symmetric_open_eyes(self) -> None:
        window = self._build_dummy_window(ear_threshold=0.21)

        self.assertTrue(BlinkWindow._stable_open_sample(window, 0.17, 0.18))
        self.assertFalse(BlinkWindow._stable_open_sample(window, 0.11, 0.12))
        self.assertFalse(BlinkWindow._stable_open_sample(window, 0.17, 0.25))

    def test_handle_calibration_requires_real_stable_time(self) -> None:
        window = self._build_dummy_window(calibration_seconds=1.0)
        completion_seen = False

        for index in range(12):
            lines = BlinkWindow._handle_calibration(window, 0.18, 0.18, index * 0.03)

        self.assertFalse(window._calibration.completed)
        self.assertEqual(window._calibration.stage, "open")
        self.assertIn("Stable time remaining", lines[1])

        for index in range(12, 36):
            lines = BlinkWindow._handle_calibration(window, 0.18, 0.18, index * 0.03)
            if lines == ["Calibration complete"]:
                completion_seen = True

        self.assertTrue(window._calibration.completed)
        self.assertEqual(window._calibration.stage, "done")
        self.assertTrue(completion_seen)
        self.assertIsNotNone(window._blink_state.open_reference_aperture)
