import cv2
import logging
import os
import sys
import threading
import time
from datetime import datetime
from typing import TypedDict

import mediapipe as mp
import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

from blink_app.aggregates import AggregateState, update_aggregates
from blink_app.cli import parse_args
from blink_app.constants import LEFT_EYE, RIGHT_EYE
from blink_app.db import init_db
from blink_app.detection import BlinkState, eye_aspect_ratio
from blink_app.logging_utils import setup_logging
from blink_app.render import render_overlay


class CameraResult(TypedDict):
    error: str | None
    cap: cv2.VideoCapture | None
    backend: str | None
    open_seconds: float | None
    first_frame_seconds: float | None


class BlinkWindow(QtWidgets.QMainWindow):
    def __init__(
        self,
        args,
        output_dir: str,
        app_logger: logging.Logger,
        blink_logger: logging.Logger,
        aggregate_logger: logging.Logger,
        db_conn,
    ) -> None:
        super().__init__()
        self._args = args
        self._output_dir = output_dir
        self._app_logger = app_logger
        self._blink_logger = blink_logger
        self._aggregate_logger = aggregate_logger
        self._db_conn = db_conn

        self._cap: cv2.VideoCapture | None = None
        self._face_mesh: mp.solutions.face_mesh.FaceMesh | None = None
        self._frame_timer: QtCore.QTimer | None = None
        self._init_timer: QtCore.QTimer | None = None
        self._closing = False

        self._camera_ready = threading.Event()
        self._camera_result: CameraResult = {
            "error": None,
            "cap": None,
            "backend": None,
            "open_seconds": None,
            "first_frame_seconds": None,
        }

        self._blink_state = BlinkState(last_blink_time=time.time())
        self._aggregate_state = AggregateState(last_stats_time=time.time())

        self.setWindowTitle("Blink detection")
        self._video_label = QtWidgets.QLabel(alignment=QtCore.Qt.AlignmentFlag.AlignCenter)
        self._video_label.setMinimumSize(640, 480)

        central_widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(central_widget)
        layout.addWidget(self._video_label)
        self.setCentralWidget(central_widget)

        self._waiting_frame = self._build_waiting_frame()
        self._camera_thread = threading.Thread(target=self._open_camera, daemon=False)
        self._camera_thread.start()

        self._init_timer = QtCore.QTimer(self)
        self._init_timer.timeout.connect(self._update_initializing_frame)
        self._init_timer.start(50)

    def _build_waiting_frame(self) -> np.ndarray:
        try:
            waiting_height = int(os.getenv("BLINK_APP_INIT_HEIGHT", "480"))
        except (TypeError, ValueError):
            waiting_height = 480
        try:
            waiting_width = int(os.getenv("BLINK_APP_INIT_WIDTH", "640"))
        except (TypeError, ValueError):
            waiting_width = 640

        frame = np.zeros((waiting_height, waiting_width, 3), dtype=np.uint8)
        cv2.putText(
            frame,
            "Initializing camera...",
            (30, 240),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
        return frame

    def _open_camera(self) -> None:
        try:
            backends: list[tuple[str, int | None]] = []
            if hasattr(cv2, "CAP_DSHOW"):
                backends.append(("DSHOW", cv2.CAP_DSHOW))
            backends.append(("DEFAULT", None))

            last_error: str | None = None
            for backend_name, backend_id in backends:
                open_start = time.perf_counter()
                local_cap = (
                    cv2.VideoCapture(self._args.camera_index, backend_id)
                    if backend_id is not None
                    else cv2.VideoCapture(self._args.camera_index)
                )
                open_seconds = time.perf_counter() - open_start

                if not local_cap.isOpened():
                    last_error = f"backend={backend_name} open={open_seconds:.2f}s isOpened=False"
                    local_cap.release()
                    continue

                if self._args.fps is not None:
                    local_cap.set(cv2.CAP_PROP_FPS, self._args.fps)

                first_frame_start = time.perf_counter()
                got_frame = False
                for _ in range(60):
                    ret, _frame = local_cap.read()
                    if ret:
                        got_frame = True
                        break
                    time.sleep(0.05)
                first_frame_seconds = time.perf_counter() - first_frame_start

                if not got_frame:
                    last_error = (
                        f"backend={backend_name} open={open_seconds:.2f}s "
                        f"first_frame>{first_frame_seconds:.2f}s"
                    )
                    local_cap.release()
                    continue

                self._camera_result["cap"] = local_cap
                self._camera_result["backend"] = backend_name
                self._camera_result["open_seconds"] = open_seconds
                self._camera_result["first_frame_seconds"] = first_frame_seconds
                return

            self._camera_result["error"] = (
                "Cannot open camera / get first frame."
                + (f" Last attempt: {last_error}" if last_error else "")
            )
        except Exception as e:
            self._camera_result["error"] = f"Camera initialization error: {e}"
        finally:
            self._camera_ready.set()

    def _update_initializing_frame(self) -> None:
        if self._closing:
            return
        if not self._camera_ready.is_set():
            self._show_frame(self._waiting_frame)
            return

        if self._init_timer is not None:
            self._init_timer.stop()
        if self._camera_result["error"]:
            self._app_logger.error("%s", self._camera_result["error"])
            QtWidgets.QMessageBox.critical(self, "Camera Error", self._camera_result["error"])
            self.close()
            return

        self._cap = self._camera_result["cap"]
        if self._cap is None:
            self._app_logger.error("Camera did not initialize.")
            QtWidgets.QMessageBox.critical(self, "Camera Error", "Camera did not initialize.")
            self.close()
            return

        if self._camera_result["backend"] is not None:
            self._app_logger.info(
                "Camera initialized (backend=%s, open=%.2fs, first_frame=%.2fs).",
                self._camera_result["backend"],
                self._camera_result["open_seconds"] or 0.0,
                self._camera_result["first_frame_seconds"] or 0.0,
            )

        face_mesh_start = time.perf_counter()
        mp_face_mesh = mp.solutions.face_mesh
        self._face_mesh = mp_face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=1,
            refine_landmarks=True,
        )
        self._app_logger.info(
            "FaceMesh initialized in %.2fs.",
            time.perf_counter() - face_mesh_start,
        )
        self._app_logger.info("Camera started. Press Esc or close window to exit.")

        self._frame_timer = QtCore.QTimer(self)
        self._frame_timer.timeout.connect(self._update_frame)
        self._frame_timer.start(30)

    def _update_frame(self) -> None:
        if self._cap is None or self._face_mesh is None:
            return
        ret, frame = self._cap.read()
        if not ret:
            self._app_logger.warning("Failed to read frame.")
            self.close()
            return

        h, w = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self._face_mesh.process(rgb)
        now_dt = datetime.now()
        now_ts = time.time()

        if results.multi_face_landmarks:
            for face_landmarks in results.multi_face_landmarks:
                landmarks = [(lm.x * w, lm.y * h) for lm in face_landmarks.landmark]

                left_ear = eye_aspect_ratio(landmarks, LEFT_EYE)
                right_ear = eye_aspect_ratio(landmarks, RIGHT_EYE)
                ear = (left_ear + right_ear) / 2.0

                self._blink_state.update(
                    ear,
                    now_dt,
                    now_ts,
                    self._args.ear_threshold,
                    self._args.ear_consec_frames,
                    self._blink_logger,
                    self._db_conn,
                )

        update_aggregates(
            self._args,
            self._aggregate_state,
            now_dt,
            now_ts,
            self._blink_state,
            self._db_conn,
            self._aggregate_logger,
            self._output_dir,
        )

        rendered = render_overlay(
            frame,
            self._aggregate_state,
            self._blink_state,
            now_ts,
            self._args.enable_alerts,
        )
        self._show_frame(rendered)

    def _show_frame(self, frame: np.ndarray) -> None:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        height, width = rgb.shape[:2]
        bytes_per_line = 3 * width
        image = QtGui.QImage(
            rgb.data,
            width,
            height,
            bytes_per_line,
            QtGui.QImage.Format.Format_RGB888,
        )
        pixmap = QtGui.QPixmap.fromImage(image.copy())
        scaled = pixmap.scaled(
            self._video_label.size(),
            QtCore.Qt.AspectRatioMode.KeepAspectRatio,
            QtCore.Qt.TransformationMode.SmoothTransformation,
        )
        self._video_label.setPixmap(scaled)

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        if event.key() == QtCore.Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        self._closing = True
        if self._init_timer is not None:
            self._init_timer.stop()
        if self._frame_timer is not None:
            self._frame_timer.stop()
        if self._camera_thread.is_alive():
            self._camera_thread.join(timeout=10.0)
        if self._face_mesh is not None:
            self._face_mesh.close()
        if self._cap is not None:
            self._cap.release()
        self._db_conn.close()
        self._app_logger.info("Camera and windows closed. Goodbye!")
        super().closeEvent(event)


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir
    try:
        os.makedirs(output_dir, exist_ok=True)
    except OSError as e:
        logging.basicConfig(level=logging.INFO)
        logging.getLogger("app").error(
            "Could not create output directory '%s': %s",
            output_dir,
            e,
        )
        sys.exit(1)

    app_logger, blink_logger, aggregate_logger = setup_logging(output_dir)
    db_path = args.db_path or os.path.join(output_dir, "blinks.db")
    db_conn = init_db(db_path)

    app_logger.info("Starting blink detection. Initializing camera...")

    app = QtWidgets.QApplication(sys.argv)
    window = BlinkWindow(
        args,
        output_dir,
        app_logger,
        blink_logger,
        aggregate_logger,
        db_conn,
    )
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
