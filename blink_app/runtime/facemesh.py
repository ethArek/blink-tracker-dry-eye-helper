import logging
import time
from typing import Any

from blink_app.runtime.dependencies import get_cv2, get_mediapipe


def prepare_facemesh_frame(rgb_frame: Any, max_width: int) -> Any:
    frame_height, frame_width = rgb_frame.shape[:2]
    safe_max_width = max(1, int(max_width))
    if frame_width <= safe_max_width:
        return rgb_frame

    scale = safe_max_width / float(frame_width)
    target_height = max(1, int(round(frame_height * scale)))
    cv2_module = get_cv2()
    return cv2_module.resize(
        rgb_frame,
        (safe_max_width, target_height),
        interpolation=cv2_module.INTER_AREA,
    )


def create_face_mesh(app_logger: logging.Logger, refine_landmarks: bool) -> Any:
    mp = get_mediapipe()
    if not hasattr(mp, "solutions"):
        raise RuntimeError(
            "Installed mediapipe "
            f"{getattr(mp, '__version__', 'unknown')} does not provide "
            "mp.solutions FaceMesh. Install mediapipe==0.10.21."
        )

    face_mesh_start = time.perf_counter()
    mp_face_mesh = mp.solutions.face_mesh
    face_mesh = mp_face_mesh.FaceMesh(
        static_image_mode=False,
        max_num_faces=1,
        refine_landmarks=refine_landmarks,
    )
    app_logger.info(
        "FaceMesh initialized in %.2fs (refine_landmarks=%s).",
        time.perf_counter() - face_mesh_start,
        refine_landmarks,
    )

    return face_mesh
