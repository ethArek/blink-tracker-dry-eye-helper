import time
from dataclasses import dataclass
from typing import Any

from blink_app.runtime.dependencies import get_cv2


@dataclass(slots=True)
class CameraProbeResult:
    error: str | None = None
    backend: str | None = None
    backend_id: int | None = None
    ready_seconds: float | None = None
    camera_index: int | None = None


def _camera_backends(cv2_module: Any) -> list[tuple[str, int | None]]:
    backends: list[tuple[str, int | None]] = []
    if hasattr(cv2_module, "CAP_DSHOW"):
        backends.append(("DSHOW", cv2_module.CAP_DSHOW))
    if hasattr(cv2_module, "CAP_MSMF"):
        backends.append(("MSMF", cv2_module.CAP_MSMF))
    backends.append(("DEFAULT", None))

    return backends


def open_video_capture(camera_index: int, backend_id: int | None, fps: float | None) -> Any:
    cv2_module = get_cv2()
    capture = (
        cv2_module.VideoCapture(camera_index, backend_id)
        if backend_id is not None
        else cv2_module.VideoCapture(camera_index)
    )
    if fps is not None:
        capture.set(cv2_module.CAP_PROP_FPS, fps)

    return capture


def _wait_for_first_frame(local_cap: Any, startup_timeout_seconds: float) -> bool:
    deadline = time.perf_counter() + max(0.05, float(startup_timeout_seconds))
    while time.perf_counter() < deadline:
        ret, _ = local_cap.read()
        if ret:
            return True

        time.sleep(0.02)

    return False


def _probe_camera_index(
    cv2_module: Any,
    camera_index: int,
    fps: float | None,
    startup_timeout_seconds: float,
) -> tuple[CameraProbeResult | None, list[str]]:
    attempt_errors: list[str] = []

    for backend_name, backend_id in _camera_backends(cv2_module):
        ready_start = time.perf_counter()
        local_cap = open_video_capture(camera_index, backend_id, fps)
        ready_seconds = time.perf_counter() - ready_start

        if not local_cap.isOpened():
            attempt_errors.append(
                f"index={camera_index} backend={backend_name} open={ready_seconds:.2f}s isOpened=False"
            )
            local_cap.release()
            continue

        try:
            frame_ready = _wait_for_first_frame(local_cap, startup_timeout_seconds)
        except Exception as exc:
            attempt_errors.append(
                f"index={camera_index} backend={backend_name} frame-check failed: {exc}"
            )
            local_cap.release()
            continue

        ready_seconds = time.perf_counter() - ready_start
        if not frame_ready:
            attempt_errors.append(
                f"index={camera_index} backend={backend_name} ready={ready_seconds:.2f}s "
                f"first_frame_timeout={float(startup_timeout_seconds):.2f}s"
            )
            local_cap.release()
            continue

        local_cap.release()
        return (
            CameraProbeResult(
                backend=backend_name,
                backend_id=backend_id,
                ready_seconds=ready_seconds,
                camera_index=camera_index,
            ),
            attempt_errors,
        )

    return None, attempt_errors


def probe_camera(
    camera_index: int,
    fps: float | None,
    startup_timeout_seconds: float,
) -> CameraProbeResult:
    cv2_module = get_cv2()
    candidate_indices = [camera_index]
    if camera_index == 0:
        candidate_indices.extend([1, 2, 3, 4])

    all_attempt_errors: list[str] = []
    for candidate_index in candidate_indices:
        result, attempt_errors = _probe_camera_index(
            cv2_module,
            candidate_index,
            fps,
            startup_timeout_seconds,
        )
        all_attempt_errors.extend(attempt_errors)
        if result is not None:
            return result

    summary = ""
    if all_attempt_errors:
        summary = " Attempts: " + "; ".join(all_attempt_errors[-4:])

    return CameraProbeResult(error="Cannot open camera." + summary)
