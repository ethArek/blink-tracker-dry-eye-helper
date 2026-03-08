"""Lazy runtime dependency loaders."""

from typing import Any

_cv2_module: Any | None = None
_mediapipe_module: Any | None = None


def get_cv2() -> Any:
    global _cv2_module
    if _cv2_module is None:
        import cv2

        _cv2_module = cv2

    return _cv2_module


def get_mediapipe() -> Any:
    global _mediapipe_module
    if _mediapipe_module is None:
        import mediapipe as mp

        _mediapipe_module = mp

    return _mediapipe_module
