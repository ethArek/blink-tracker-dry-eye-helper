import logging
import os
import threading
import time
from datetime import datetime
from typing import Any

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

from blink_app.constants import (
    ALERT_NO_BLINK_SECONDS,
    FACEMESH_MAX_WIDTH,
    FACEMESH_REFINE_LANDMARKS,
    LEFT_EYE,
    RIGHT_EYE,
)
from blink_app.domain.aggregates import AggregateState, update_aggregates
from blink_app.domain.detection import BlinkState, eye_aspect_ratio
from blink_app.metadata import APP_NAME
from blink_app.runtime.camera import CameraProbeResult, open_video_capture, probe_camera
from blink_app.runtime.dependencies import get_cv2
from blink_app.runtime.facemesh import create_face_mesh, prepare_facemesh_frame
from blink_app.services.db import fetch_recent_aggregates
from blink_app.ui.widgets import ToggleSwitch

EYE_EAR_INDICES = (0, 1, 2, 3, 4, 5)


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

        self._cap: Any | None = None
        self._face_mesh: Any | None = None
        self._frame_timer: QtCore.QTimer | None = None
        self._init_timer: QtCore.QTimer | None = None
        self._closing = False

        self._camera_ready = threading.Event()
        self._camera_result = CameraProbeResult()
        self._camera_init_started_at = time.perf_counter()
        self._camera_init_hard_timeout_seconds = max(
            15.0,
            float(self._args.camera_startup_timeout_seconds) + 12.0,
        )
        self._consecutive_read_failures = 0
        self._max_read_failures = 90

        self._blink_state = BlinkState(last_blink_time=time.time())
        self._aggregate_state = AggregateState(last_stats_time=time.time())
        self._alerts_enabled = bool(getattr(args, "enable_alerts", False))
        self._alert_after_input: QtWidgets.QDoubleSpinBox | None = None
        self._alert_status_label: QtWidgets.QLabel | None = None
        self._alert_toggle: ToggleSwitch | None = None
        self._minute_table: QtWidgets.QTableWidget | None = None
        self._minute_panel: QtWidgets.QWidget | None = None
        self._side_tabs: QtWidgets.QTabWidget | None = None
        self._last_minute_table_refresh: datetime | None = None
        self._minute_table_limit = 360
        self._facemesh_max_width = max(
            160,
            int(getattr(args, "facemesh_max_width", FACEMESH_MAX_WIDTH)),
        )
        self._refine_landmarks = bool(
            getattr(args, "refine_landmarks", FACEMESH_REFINE_LANDMARKS)
        )

        self.setWindowTitle(APP_NAME)
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
        self._camera_thread = threading.Thread(target=self._probe_camera, daemon=True)
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
            QSpinBox, QDoubleSpinBox {
                background-color: #1a2130;
                color: #f6f7fb;
                border: 1px solid #242c3f;
                border-radius: 8px;
                padding: 2px 6px;
            }
            QTabWidget::pane {
                border: 0;
            }
            QTabBar::tab {
                background-color: #131823;
                color: #a3aec2;
                padding: 8px 12px;
                border: 1px solid #1d2332;
                border-bottom: none;
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
                min-width: 80px;
            }
            QTabBar::tab:selected {
                background-color: #1a2130;
                color: #f6f7fb;
                border-color: #242c3f;
            }
            QTabWidget::tab-bar {
                left: 10px;
            }
            QTableWidget {
                background-color: #1a2130;
                color: #f6f7fb;
                gridline-color: #242c3f;
                border: 1px solid #242c3f;
                border-radius: 10px;
            }
            QTableWidget::item {
                color: #f6f7fb;
                background-color: #1a2130;
            }
            QTableWidget::item:alternate {
                background-color: #161c27;
            }
            QTableWidget::item:selected {
                background-color: #2a3550;
                color: #f6f7fb;
            }
            QHeaderView::section {
                background-color: #131823;
                color: #a3aec2;
                border: 1px solid #242c3f;
                padding: 4px 6px;
            }
            QScrollBar:vertical {
                background: #131823;
                width: 10px;
                margin: 2px;
                border: 1px solid #1d2332;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background: #2a3550;
                min-height: 20px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical:hover {
                background: #334264;
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0px;
                width: 0px;
            }
            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {
                background: none;
            }
            QScrollBar:horizontal {
                background: #131823;
                height: 10px;
                margin: 2px;
                border: 1px solid #1d2332;
                border-radius: 6px;
            }
            QScrollBar::handle:horizontal {
                background: #2a3550;
                min-width: 20px;
                border-radius: 5px;
            }
            QScrollBar::handle:horizontal:hover {
                background: #334264;
            }
            QScrollBar::add-line:horizontal,
            QScrollBar::sub-line:horizontal {
                height: 0px;
                width: 0px;
            }
            QScrollBar::add-page:horizontal,
            QScrollBar::sub-page:horizontal {
                background: none;
            }
            """
        )

    def _build_side_panel(self) -> QtWidgets.QWidget:
        tabs = QtWidgets.QTabWidget()
        tabs.setMinimumWidth(320)
        tabs.setMaximumWidth(360)
        tabs.addTab(self._build_stats_panel(), "Stats")
        self._minute_panel = self._build_minute_panel()
        tabs.addTab(self._minute_panel, "Per-minute")
        tabs.currentChanged.connect(self._handle_tab_changed)
        self._side_tabs = tabs
        return tabs

    def _build_stats_panel(self) -> QtWidgets.QWidget:
        panel = QtWidgets.QFrame()
        panel.setObjectName("StatsPanel")
        panel.setMinimumWidth(320)
        panel.setMaximumWidth(360)

        panel_layout = QtWidgets.QVBoxLayout(panel)
        panel_layout.setContentsMargins(18, 18, 18, 18)
        panel_layout.setSpacing(16)

        title = QtWidgets.QLabel(APP_NAME)
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

    def _build_minute_panel(self) -> QtWidgets.QWidget:
        panel = QtWidgets.QFrame()
        panel.setObjectName("StatsPanel")
        panel.setMinimumWidth(320)
        panel.setMaximumWidth(360)

        panel_layout = QtWidgets.QVBoxLayout(panel)
        panel_layout.setContentsMargins(18, 18, 18, 18)
        panel_layout.setSpacing(12)

        title = QtWidgets.QLabel("Per-minute blinks")
        title.setObjectName("PanelTitle")
        subtitle = QtWidgets.QLabel("Most recent first")
        subtitle.setObjectName("PanelSubtitle")
        panel_layout.addWidget(title)
        panel_layout.addWidget(subtitle)

        table = QtWidgets.QTableWidget()
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels(["Minute", "Blinks"])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        table.setAlternatingRowColors(True)
        table.setSortingEnabled(False)
        table.horizontalHeader().setStretchLastSection(False)
        table.horizontalHeader().setSectionResizeMode(
            0,
            QtWidgets.QHeaderView.ResizeMode.Stretch,
        )
        table.horizontalHeader().setSectionResizeMode(
            1,
            QtWidgets.QHeaderView.ResizeMode.ResizeToContents,
        )

        self._minute_table = table
        panel_layout.addWidget(table, stretch=1)
        self._refresh_minute_table()
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

        alert_row = QtWidgets.QWidget()
        alert_row_layout = QtWidgets.QHBoxLayout(alert_row)
        alert_row_layout.setContentsMargins(0, 0, 0, 0)
        alert_row_layout.setSpacing(8)
        alert_after_label = QtWidgets.QLabel("After")
        alert_after_label.setObjectName("CardTitle")
        alert_suffix_label = QtWidgets.QLabel("(s) without blinking")
        alert_suffix_label.setObjectName("CardTitle")
        self._alert_after_input = QtWidgets.QDoubleSpinBox()
        self._alert_after_input.setDecimals(1)
        self._alert_after_input.setSingleStep(1.0)
        self._alert_after_input.setRange(0.1, 86400.0)
        self._alert_after_input.setFixedWidth(65)
        self._alert_after_input.setValue(
            max(
                0.1,
                float(
                    getattr(
                        self._args,
                        "alert_after_seconds",
                        ALERT_NO_BLINK_SECONDS,
                    )
                ),
            )
        )
        self._alert_after_input.valueChanged.connect(self._update_alert_after_seconds)
        alert_row_layout.addWidget(alert_after_label)
        alert_row_layout.addWidget(self._alert_after_input)
        alert_row_layout.addWidget(alert_suffix_label)
        alert_row_layout.addStretch()
        label_stack.addWidget(alert_row)

        self._alert_toggle = ToggleSwitch()
        self._alert_toggle.setObjectName("AlertToggle")
        self._alert_toggle.setChecked(self._alerts_enabled)
        self._alert_toggle.toggled.connect(self._toggle_alerts)

        card_layout.addLayout(label_stack)
        card_layout.addStretch()
        card_layout.addWidget(self._alert_toggle)
        self._refresh_alert_status()
        return card

    def _toggle_alerts(self, enabled: bool) -> None:
        self._alerts_enabled = enabled
        self._args.enable_alerts = enabled
        self._refresh_alert_status()

    def _update_alert_after_seconds(self, value: float) -> None:
        self._args.alert_after_seconds = float(value)

    def _refresh_alert_status(self) -> None:
        if self._alert_status_label is None:
            return

        if self._alerts_enabled:
            self._alert_status_label.setText("Alerts ON")
        else:
            self._alert_status_label.setText("Alerts OFF")

    @staticmethod
    def _format_last_blink(last_blink_time: float, now_ts: float) -> str:
        if last_blink_time <= 0:
            return "--"
        seconds_ago = max(0, int(now_ts - last_blink_time))
        return f"{seconds_ago}s ago"

    @staticmethod
    def _eye_landmarks(
        face_landmarks: Any,
        eye_indices: list[int],
        width: int,
        height: int,
    ) -> list[tuple[float, float]]:
        return [
            (
                face_landmarks.landmark[index].x * width,
                face_landmarks.landmark[index].y * height,
            )
            for index in eye_indices
        ]

    def _build_waiting_frame(self) -> np.ndarray:
        try:
            waiting_height = int(os.getenv("BLINK_APP_INIT_HEIGHT", "480"))
        except (TypeError, ValueError):
            waiting_height = 480
        try:
            waiting_width = int(os.getenv("BLINK_APP_INIT_WIDTH", "640"))
        except (TypeError, ValueError):
            waiting_width = 640

        return np.zeros((waiting_height, waiting_width, 3), dtype=np.uint8)

    def _probe_camera(self) -> None:
        try:
            self._camera_result = probe_camera(
                self._args.camera_index,
                self._args.fps,
                self._args.camera_startup_timeout_seconds,
            )
        except Exception as exc:
            self._camera_result = CameraProbeResult(error=f"Camera initialization error: {exc}")
        finally:
            self._camera_ready.set()

    def _update_initializing_frame(self) -> None:
        if self._closing:
            return
        if not self._camera_ready.is_set():
            elapsed = time.perf_counter() - self._camera_init_started_at
            if elapsed >= self._camera_init_hard_timeout_seconds:
                self._camera_result.error = "Camera initialization timed out before startup probe completed."
                self._camera_ready.set()
            else:
                self._show_frame(self._waiting_frame, rgb_frame=self._waiting_frame)
                return

        if self._init_timer is not None:
            self._init_timer.stop()
        if self._camera_result.error:
            self._app_logger.error("%s", self._camera_result.error)
            QtWidgets.QMessageBox.critical(self, "Camera Error", self._camera_result.error)
            self.close()
            return

        self._cap = open_video_capture(
            self._args.camera_index,
            self._camera_result.backend_id,
            self._args.fps,
        )
        if self._cap is None:
            self._app_logger.error("Camera did not initialize.")
            QtWidgets.QMessageBox.critical(self, "Camera Error", "Camera did not initialize.")
            self.close()
            return
        if not self._cap.isOpened():
            self._app_logger.error("Camera backend probe passed, but open in UI thread failed.")
            QtWidgets.QMessageBox.critical(
                self,
                "Camera Error",
                "Camera opened during probe, but failed to open for live capture.",
            )
            self.close()
            return

        if self._camera_result.backend is not None:
            self._app_logger.info(
                "Camera initialized (backend=%s, ready=%.2fs).",
                self._camera_result.backend,
                self._camera_result.ready_seconds or 0.0,
            )

        try:
            self._face_mesh = create_face_mesh(
                self._app_logger,
                refine_landmarks=self._refine_landmarks,
            )
        except Exception as exc:
            self._app_logger.exception("FaceMesh initialization failed.")
            QtWidgets.QMessageBox.critical(
                self,
                "FaceMesh Error",
                f"FaceMesh initialization failed: {exc}",
            )
            self.close()
            return
        self._app_logger.info("Camera started. Press Esc or close window to exit.")

        self._frame_timer = QtCore.QTimer(self)
        self._frame_timer.timeout.connect(self._update_frame)
        self._frame_timer.start(30)

    def _update_frame(self) -> None:
        if self._closing:
            return
        if self._cap is None or self._face_mesh is None:
            return
        ret, frame = self._cap.read()
        if not ret:
            self._consecutive_read_failures += 1
            if self._consecutive_read_failures <= self._max_read_failures:
                if self._consecutive_read_failures == 1 or self._consecutive_read_failures % 30 == 0:
                    self._app_logger.warning(
                        "Failed to read frame (%d/%d).",
                        self._consecutive_read_failures,
                        self._max_read_failures,
                    )
                self._show_frame(self._waiting_frame, rgb_frame=self._waiting_frame)
                return
            self._app_logger.error(
                "Failed to read frame too many times (%d). Closing.",
                self._consecutive_read_failures,
            )
            self.close()
            return
        self._consecutive_read_failures = 0

        cv2_module = get_cv2()
        rgb_frame = cv2_module.cvtColor(frame, cv2_module.COLOR_BGR2RGB)
        process_rgb_frame = prepare_facemesh_frame(rgb_frame, self._facemesh_max_width)
        process_rgb_frame.flags.writeable = False
        try:
            results = self._face_mesh.process(process_rgb_frame)
        except Exception:
            if self._closing:
                return
            self._app_logger.exception("FaceMesh processing failed.")
            self.close()
            return
        finally:
            process_rgb_frame.flags.writeable = True
        now_ts = time.time()
        now_dt = datetime.fromtimestamp(now_ts)

        first_face = None
        if results.multi_face_landmarks:
            first_face = results.multi_face_landmarks[0]

        if first_face is not None:
            height, width = frame.shape[:2]
            left_landmarks = self._eye_landmarks(first_face, LEFT_EYE, width, height)
            right_landmarks = self._eye_landmarks(first_face, RIGHT_EYE, width, height)
            left_ear = eye_aspect_ratio(left_landmarks, EYE_EAR_INDICES)
            right_ear = eye_aspect_ratio(right_landmarks, EYE_EAR_INDICES)
            ear = (left_ear + right_ear) / 2.0
            self._blink_state.update(
                ear,
                now_dt,
                now_ts,
                self._args.ear_threshold,
                self._args.ear_consec_frames,
                self._blink_logger,
                self._db_conn,
                left_ear=left_ear,
                right_ear=right_ear,
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
        self._refresh_minute_table_if_needed()
        self._show_frame(frame, rgb_frame=rgb_frame)

    def _handle_tab_changed(self, index: int) -> None:
        if self._side_tabs is None or self._minute_panel is None:
            return
        if self._side_tabs.widget(index) is not self._minute_panel:
            return

        self._refresh_minute_table()
        self._last_minute_table_refresh = self._aggregate_state.last_logged_minute

    def _update_stats_panel(self, now_ts: float) -> None:
        self._session_blinks_value.setText(str(self._blink_state.blink_counter))
        self._last_blink_value.setText(
            self._format_last_blink(self._blink_state.last_blink_time, now_ts)
        )
        self._blinks_per_minute_value.setText(str(self._aggregate_state.blinks_1m))
        self._blinks_per_hour_value.setText(str(self._aggregate_state.blinks_1h))
        self._blinks_today_value.setText(str(self._aggregate_state.blinks_day))

    def _refresh_minute_table_if_needed(self) -> None:
        if self._minute_table is None or self._side_tabs is None or self._minute_panel is None:
            return
        if self._side_tabs.currentWidget() is not self._minute_panel:
            return

        last_logged_minute = self._aggregate_state.last_logged_minute
        if last_logged_minute is None:
            if self._minute_table.rowCount() == 0:
                self._refresh_minute_table()
            return

        if self._last_minute_table_refresh == last_logged_minute:
            return

        self._refresh_minute_table()
        self._last_minute_table_refresh = last_logged_minute

    def _refresh_minute_table(self) -> None:
        if self._minute_table is None:
            return

        rows = fetch_recent_aggregates(
            self._db_conn,
            interval_type="minute",
            limit=self._minute_table_limit,
        )
        self._minute_table.setRowCount(len(rows))
        for row_index, (interval_start, blink_count) in enumerate(rows):
            time_item = QtWidgets.QTableWidgetItem(interval_start)
            time_item.setTextAlignment(
                QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter
            )
            count_item = QtWidgets.QTableWidgetItem(str(blink_count))
            count_item.setTextAlignment(
                QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter
            )
            self._minute_table.setItem(row_index, 0, time_item)
            self._minute_table.setItem(row_index, 1, count_item)
        self._minute_table.resizeRowsToContents()

    def _show_frame(self, frame: np.ndarray, rgb_frame: np.ndarray | None = None) -> None:
        display_frame = rgb_frame
        if display_frame is None:
            cv2_module = get_cv2()
            display_frame = cv2_module.cvtColor(frame, cv2_module.COLOR_BGR2RGB)

        height, width = display_frame.shape[:2]
        bytes_per_line = 3 * width
        image = QtGui.QImage(
            display_frame.data,
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
            if self._camera_thread.is_alive():
                self._app_logger.warning("Camera initialization thread did not stop cleanly.")
        if self._face_mesh is not None:
            self._face_mesh.close()
        if self._cap is not None:
            self._cap.release()
        self._db_conn.close()
        self._app_logger.info("Camera and windows closed. Goodbye!")
        super().closeEvent(event)



