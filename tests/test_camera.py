from types import SimpleNamespace
import unittest
from unittest.mock import patch

from blink_app.runtime.camera import (
    _camera_backends,
    _probe_camera_index,
    _wait_for_first_frame,
    open_video_capture,
    probe_camera,
)


class FakeCapture:
    def __init__(self, opened: bool) -> None:
        self._opened = opened
        self.released = False
        self.set_calls: list[tuple[int, float]] = []

    def isOpened(self) -> bool:
        return self._opened

    def release(self) -> None:
        self.released = True

    def read(self):
        return False, None

    def set(self, prop: int, value: float) -> None:
        self.set_calls.append((prop, value))


class SequenceCapture(FakeCapture):
    def __init__(self, responses: list[tuple[bool, object | None]]) -> None:
        super().__init__(opened=True)
        self._responses = iter(responses)

    def read(self):
        return next(self._responses)


class CameraProbeTest(unittest.TestCase):
    def test_camera_backends_prioritize_windows_backends_before_default(self) -> None:
        fake_cv2 = SimpleNamespace(CAP_DSHOW=700, CAP_MSMF=1400)

        backends = _camera_backends(fake_cv2)

        self.assertEqual(backends, [("DSHOW", 700), ("MSMF", 1400), ("DEFAULT", None)])

    def test_open_video_capture_uses_backend_and_sets_fps(self) -> None:
        capture = FakeCapture(opened=True)
        fake_cv2 = SimpleNamespace(
            CAP_PROP_FPS=5,
            VideoCapture=lambda camera_index, backend_id: capture,
        )

        with patch("blink_app.runtime.camera.get_cv2", return_value=fake_cv2):
            result = open_video_capture(2, 1400, 30.0)

        self.assertIs(result, capture)
        self.assertEqual(capture.set_calls, [(5, 30.0)])

    def test_open_video_capture_without_backend_does_not_set_fps(self) -> None:
        capture = FakeCapture(opened=True)
        fake_cv2 = SimpleNamespace(VideoCapture=lambda camera_index: capture)

        with patch("blink_app.runtime.camera.get_cv2", return_value=fake_cv2):
            result = open_video_capture(0, None, None)

        self.assertIs(result, capture)
        self.assertEqual(capture.set_calls, [])

    def test_wait_for_first_frame_returns_true_after_retry(self) -> None:
        capture = SequenceCapture([(False, None), (True, object())])
        perf_counter_values = iter([0.0, 0.0, 0.01])

        with patch("blink_app.runtime.camera.time.perf_counter", side_effect=lambda: next(perf_counter_values)):
            with patch("blink_app.runtime.camera.time.sleep"):
                ready = _wait_for_first_frame(capture, 0.05)

        self.assertTrue(ready)

    def test_wait_for_first_frame_returns_false_after_timeout(self) -> None:
        capture = SequenceCapture([(False, None)])
        perf_counter_values = iter([0.0, 0.0, 0.06])

        with patch("blink_app.runtime.camera.time.perf_counter", side_effect=lambda: next(perf_counter_values)):
            with patch("blink_app.runtime.camera.time.sleep"):
                ready = _wait_for_first_frame(capture, 0.05)

        self.assertFalse(ready)

    def test_probe_camera_uses_first_backend_with_frame_ready(self) -> None:
        fake_cv2 = SimpleNamespace(CAP_DSHOW=700, CAP_MSMF=1400)
        dshow_capture = FakeCapture(opened=False)
        msmf_capture = FakeCapture(opened=True)

        def open_capture(camera_index: int, backend_id: int | None, fps: float | None):
            self.assertEqual(camera_index, 1)
            self.assertEqual(fps, 30.0)
            if backend_id == fake_cv2.CAP_DSHOW:
                return dshow_capture

            return msmf_capture

        with patch("blink_app.runtime.camera.get_cv2", return_value=fake_cv2):
            with patch("blink_app.runtime.camera.open_video_capture", side_effect=open_capture):
                with patch("blink_app.runtime.camera._wait_for_first_frame", return_value=True) as wait_mock:
                    result = probe_camera(1, 30.0, 2.0)

        self.assertIsNone(result.error)
        self.assertEqual(result.backend, "MSMF")
        self.assertEqual(result.backend_id, fake_cv2.CAP_MSMF)
        self.assertEqual(result.camera_index, 1)
        self.assertIsNotNone(result.ready_seconds)
        self.assertTrue(dshow_capture.released)
        self.assertTrue(msmf_capture.released)
        wait_mock.assert_called_once_with(msmf_capture, 2.0)

    def test_probe_camera_reports_frame_timeout_when_all_backends_fail(self) -> None:
        fake_cv2 = SimpleNamespace(CAP_DSHOW=700)
        capture = FakeCapture(opened=True)

        with patch("blink_app.runtime.camera.get_cv2", return_value=fake_cv2):
            with patch("blink_app.runtime.camera.open_video_capture", return_value=capture):
                with patch("blink_app.runtime.camera._wait_for_first_frame", return_value=False):
                    result = probe_camera(0, None, 1.5)

        self.assertIsNotNone(result.error)
        self.assertIn("first_frame_timeout=1.50s", result.error or "")
        self.assertTrue(capture.released)

    def test_probe_camera_index_records_frame_check_exception(self) -> None:
        fake_cv2 = SimpleNamespace()
        capture = FakeCapture(opened=True)

        with patch("blink_app.runtime.camera.open_video_capture", return_value=capture):
            with patch(
                "blink_app.runtime.camera._wait_for_first_frame",
                side_effect=RuntimeError("probe failed"),
            ):
                result, attempt_errors = _probe_camera_index(fake_cv2, 0, None, 1.0)

        self.assertIsNone(result)
        self.assertEqual(len(attempt_errors), 1)
        self.assertIn("frame-check failed: probe failed", attempt_errors[0])
        self.assertTrue(capture.released)

    def test_probe_camera_falls_back_to_next_index_when_zero_cannot_open(self) -> None:
        fake_cv2 = SimpleNamespace(CAP_DSHOW=700)
        closed_capture = FakeCapture(opened=False)
        open_capture = FakeCapture(opened=True)

        def open_video_capture(camera_index: int, backend_id: int | None, fps: float | None):
            self.assertIsNone(fps)
            if camera_index == 0:
                return closed_capture
            if camera_index == 1:
                if backend_id == fake_cv2.CAP_DSHOW:
                    return open_capture
                return FakeCapture(opened=False)
            return FakeCapture(opened=False)

        with patch("blink_app.runtime.camera.get_cv2", return_value=fake_cv2):
            with patch("blink_app.runtime.camera.open_video_capture", side_effect=open_video_capture):
                with patch("blink_app.runtime.camera._wait_for_first_frame", return_value=True):
                    result = probe_camera(0, None, 1.5)

        self.assertIsNone(result.error)
        self.assertEqual(result.camera_index, 1)
        self.assertEqual(result.backend, "DSHOW")
        self.assertTrue(closed_capture.released)
        self.assertTrue(open_capture.released)


if __name__ == "__main__":
    unittest.main()
