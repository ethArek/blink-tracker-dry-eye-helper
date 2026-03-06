from types import SimpleNamespace
import logging
import unittest
from unittest.mock import patch

from blink_app.runtime.facemesh import create_face_mesh, prepare_facemesh_frame


class FakeFrame:
    def __init__(self, shape: tuple[int, int, int]) -> None:
        self.shape = shape


class FaceMeshRuntimeTest(unittest.TestCase):
    def test_prepare_facemesh_frame_returns_original_when_frame_is_small_enough(self) -> None:
        rgb_frame = FakeFrame((240, 320, 3))

        prepared_frame = prepare_facemesh_frame(rgb_frame, 640)

        self.assertIs(prepared_frame, rgb_frame)

    def test_prepare_facemesh_frame_downscales_preserving_aspect_ratio(self) -> None:
        rgb_frame = FakeFrame((360, 1280, 3))
        resized_frame = FakeFrame((180, 640, 3))

        def resize(image, size, interpolation):
            self.assertIs(image, rgb_frame)
            self.assertEqual(size, (640, 180))
            self.assertEqual(interpolation, 7)
            return resized_frame

        fake_cv2 = SimpleNamespace(INTER_AREA=7, resize=resize)
        with patch("blink_app.runtime.facemesh.get_cv2", return_value=fake_cv2):
            prepared_frame = prepare_facemesh_frame(rgb_frame, 640)

        self.assertIs(prepared_frame, resized_frame)

    def test_create_face_mesh_uses_requested_refine_landmarks_setting(self) -> None:
        logger = logging.getLogger("test.facemesh")
        logger.addHandler(logging.NullHandler())
        face_mesh_calls: list[dict[str, object]] = []

        class FakeFaceMeshModule:
            @staticmethod
            def FaceMesh(**kwargs):
                face_mesh_calls.append(kwargs)
                return object()

        fake_mp = SimpleNamespace(
            __version__="0.10.21",
            solutions=SimpleNamespace(face_mesh=FakeFaceMeshModule),
        )

        with patch("blink_app.runtime.facemesh.get_mediapipe", return_value=fake_mp):
            create_face_mesh(logger, refine_landmarks=False)
            create_face_mesh(logger, refine_landmarks=True)

        self.assertEqual(len(face_mesh_calls), 2)
        self.assertFalse(face_mesh_calls[0]["refine_landmarks"])
        self.assertTrue(face_mesh_calls[1]["refine_landmarks"])
        self.assertEqual(face_mesh_calls[0]["max_num_faces"], 1)
        self.assertFalse(face_mesh_calls[0]["static_image_mode"])


if __name__ == "__main__":
    unittest.main()
