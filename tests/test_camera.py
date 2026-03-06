from types import SimpleNamespace
import unittest
from unittest.mock import patch

from blink_app.runtime.camera import _camera_backends, probe_camera


class FakeCapture:
    def __init__(self, opened: bool) -> None:
        self._opened = opened
        self.released = False

    def isOpened(self) -> bool:
        return self._opened

    def release(self) -> None:
        self.released = True

    def read(self):
        return False, None


class CameraProbeTest(unittest.TestCase):
    def test_camera_backends_prioritize_windows_backends_before_default(self) -> None:
        fake_cv2 = SimpleNamespace(CAP_DSHOW=700, CAP_MSMF=1400)

        backends = _camera_backends(fake_cv2)

        self.assertEqual(backends, [("DSHOW", 700), ("MSMF", 1400), ("DEFAULT", None)])

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


if __name__ == "__main__":
    unittest.main()
