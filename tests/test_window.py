import unittest

try:
    from blink_app.ui.window import BlinkWindow
except Exception as exc:  # pragma: no cover - environment-dependent
    BlinkWindow = None
    IMPORT_ERROR = exc
else:
    IMPORT_ERROR = None


@unittest.skipIf(BlinkWindow is None, f"UI dependencies unavailable: {IMPORT_ERROR}")
class BlinkWindowOverlayTest(unittest.TestCase):
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
