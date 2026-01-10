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
        self._alerts_enabled = bool(getattr(args, "enable_alerts", False))

        self.setWindowTitle("Blink detection")
        self._video_label = QtWidgets.QLabel(alignment=QtCore.Qt.AlignmentFlag.AlignCenter)
        self._video_label.setMinimumSize(640, 480)
        self._video_label.setStyleSheet("background-color: #0f1116; border-radius: 12px;")

        central_widget = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(central_widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(18)
        layout.addWidget(self._video_label, stretch=1)
        layout.addWidget(self._build_side_panel())
        self.setCentralWidget(central_widget)
        self._apply_theme()

        self._waiting_frame = self._build_waiting_frame()
        self._camera_thread = threading.Thread(target=self._open_camera, daemon=False)
        self._camera_thread.start()

        self._init_timer = QtCore.QTimer(self)
        self._init_timer.timeout.connect(self._update_initializing_frame)
        self._init_timer.start(50)

    def _apply_theme(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow {
                background-color: #0b0d12;
            }
            QLabel#PanelTitle {
                color: #e8ecf4;
                font-size: 18px;
                font-weight: 600;
            }
            QLabel#PanelSubtitle {
                color: #a3aec2;
                font-size: 12px;
            }
            QFrame#StatsPanel {
                background-color: #131823;
                border: 1px solid #1d2332;
                border-radius: 18px;
            }
            QFrame#StatCard {
                background-color: #1a2130;
                border: 1px solid #242c3f;
                border-radius: 14px;
            }
            QLabel#CardTitle {
                color: #9aa6bf;
                font-size: 12px;
                font-weight: 600;
            }
            QLabel#CardValue {
                color: #f6f7fb;
                font-size: 20px;
                font-weight: 700;
            }
            QLabel#CardSubValue {
                color: #e1e6f0;
                font-size: 14px;
                font-weight: 600;
            }
            QCheckBox#AlertToggle::indicator {
                width: 46px;
                height: 24px;
                border-radius: 12px;
                background-color: #2b3142;
                border: 1px solid #3a4257;
            }
            QCheckBox#AlertToggle::indicator:checked {
                background-color: #42d37d;
                border: 1px solid #3fd072;
            }
            """
        )

    def _build_side_panel(self) -> QtWidgets.QWidget:
        panel = QtWidgets.QFrame()
        panel.setObjectName("StatsPanel")
        panel.setMinimumWidth(320)
        panel.setMaximumWidth(360)

        panel_layout = QtWidgets.QVBoxLayout(panel)
        panel_layout.setContentsMargins(18, 18, 18, 18)
        panel_layout.setSpacing(16)

        title = QtWidgets.QLabel("Blink Tracker")
        title.setObjectName("PanelTitle")
        subtitle = QtWidgets.QLabel("Live session insights")
        subtitle.setObjectName("PanelSubtitle")

        panel_layout.addWidget(title)
        panel_layout.addWidget(subtitle)

        self._session_blinks_value = self._build_stat_card(
            panel_layout,
            "Session blinks",
            "0",
        )
        self._last_blink_value = self._build_stat_card(
            panel_layout,
            "Last blink",
            "--",
            use_subvalue=True,
        )
        self._blinks_per_minute_value = self._build_stat_card(
            panel_layout,
            "Blinks / minute",
            "0",
        )
        self._blinks_per_hour_value = self._build_stat_card(
            panel_layout,
            "Blinks / hour",
            "0",
        )
        self._blinks_today_value = self._build_stat_card(
            panel_layout,
            "Today",
            "0",
        )

        panel_layout.addWidget(self._build_alert_card())
        panel_layout.addStretch()

        footer = QtWidgets.QLabel("Press Esc or close the window to exit.")
        footer.setObjectName("PanelSubtitle")
        panel_layout.addWidget(footer)
        return panel

    def _build_stat_card(
        self,
        layout: QtWidgets.QVBoxLayout,
        title: str,
        value: str,
        use_subvalue: bool = False,
    ) -> QtWidgets.QLabel:
        card = QtWidgets.QFrame()
        card.setObjectName("StatCard")
        card_layout = QtWidgets.QVBoxLayout(card)
        card_layout.setContentsMargins(16, 14, 16, 14)
        card_layout.setSpacing(6)

        title_label = QtWidgets.QLabel(title)
        title_label.setObjectName("CardTitle")
        value_label = QtWidgets.QLabel(value)
        value_label.setObjectName("CardSubValue" if use_subvalue else "CardValue")

        card_layout.addWidget(title_label)
        card_layout.addWidget(value_label)
        layout.addWidget(card)
        return value_label

    def _build_alert_card(self) -> QtWidgets.QWidget:
        card = QtWidgets.QFrame()
        card.setObjectName("StatCard")
        card_layout = QtWidgets.QHBoxLayout(card)
        card_layout.setContentsMargins(16, 14, 16, 14)
        card_layout.setSpacing(12)

        label_stack = QtWidgets.QVBoxLayout()
        title_label = QtWidgets.QLabel("Alerts")
        title_label.setObjectName("CardTitle")
        self._alert_status_label = QtWidgets.QLabel("")
        self._alert_status_label.setObjectName("CardSubValue")
        label_stack.addWidget(title_label)
        label_stack.addWidget(self._alert_status_label)

        self._alert_toggle = QtWidgets.QCheckBox()
        self._alert_toggle.setObjectName("AlertToggle")
        self._alert_toggle.setChecked(self._alerts_enabled)
        self._alert_toggle.stateChanged.connect(self._toggle_alerts)

        card_layout.addLayout(label_stack)
        card_layout.addStretch()
        card_layout.addWidget(self._alert_toggle)
        self._refresh_alert_status()
        return card

    def _toggle_alerts(self, state: int) -> None:
        self._alerts_enabled = state == QtCore.Qt.CheckState.Checked
        self._args.enable_alerts = self._alerts_enabled
        self._refresh_alert_status()

    def _refresh_alert_status(self) -> None:
        if self._alerts_enabled:
            self._alert_status_label.setText("Enabled")
        else:
            self._alert_status_label.setText("Muted")

    @staticmethod
    def _format_last_blink(last_blink_time: float, now_ts: float) -> str:
        if last_blink_time <= 0:
            return "--"
        seconds_ago = max(0, int(now_ts - last_blink_time))
        return f"{seconds_ago}s ago"

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

        self._update_stats_panel(now_ts)
        self._show_frame(frame)

    def _update_stats_panel(self, now_ts: float) -> None:
        self._session_blinks_value.setText(str(self._blink_state.blink_counter))
        self._last_blink_value.setText(
            self._format_last_blink(self._blink_state.last_blink_time, now_ts)
        )
        self._blinks_per_minute_value.setText(str(self._aggregate_state.blinks_1m))
        self._blinks_per_hour_value.setText(str(self._aggregate_state.blinks_1h))
        self._blinks_today_value.setText(str(self._aggregate_state.blinks_day))

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
