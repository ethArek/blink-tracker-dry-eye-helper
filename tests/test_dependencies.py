import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from blink_app.runtime import dependencies


class RuntimeDependenciesTest(unittest.TestCase):
    def setUp(self) -> None:
        self._original_cv2_module = dependencies._cv2_module
        self._original_mediapipe_module = dependencies._mediapipe_module
        dependencies._cv2_module = None
        dependencies._mediapipe_module = None

    def tearDown(self) -> None:
        dependencies._cv2_module = self._original_cv2_module
        dependencies._mediapipe_module = self._original_mediapipe_module

    def test_get_cv2_imports_and_caches_module(self) -> None:
        fake_cv2 = SimpleNamespace(name="fake-cv2")

        with patch.dict(sys.modules, {"cv2": fake_cv2}):
            first = dependencies.get_cv2()
            second = dependencies.get_cv2()

        self.assertIs(first, fake_cv2)
        self.assertIs(second, fake_cv2)

    def test_get_mediapipe_imports_and_caches_module(self) -> None:
        fake_mediapipe = SimpleNamespace(name="fake-mediapipe")

        with patch.dict(sys.modules, {"mediapipe": fake_mediapipe}):
            first = dependencies.get_mediapipe()
            second = dependencies.get_mediapipe()

        self.assertIs(first, fake_mediapipe)
        self.assertIs(second, fake_mediapipe)


if __name__ == "__main__":
    unittest.main()
