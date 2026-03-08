import logging
import math
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

from blink_app.constants import (
    ALERT_NO_BLINK_SECONDS,
    BLINK_MAX_EYE_DIFF,
    BLINK_MAX_RATIO_GAP,
    CALIBRATION_BLINKS,
    CALIBRATION_SECONDS,
    EYE_APERTURE_CORNERS,
    EYE_APERTURE_GAP_PAIRS,
    FACEMESH_MAX_WIDTH,
    FACEMESH_REFINE_LANDMARKS,
    LEFT_EYE,
    RIGHT_EYE,
)
from blink_app.domain.aggregates import AggregateState, update_aggregates
from blink_app.domain.detection import BlinkState, eye_aperture_ratio
from blink_app.metadata import APP_NAME
from blink_app.runtime.camera import CameraProbeResult, open_video_capture, probe_camera
from blink_app.runtime.dependencies import get_cv2
from blink_app.runtime.facemesh import create_face_mesh, prepare_facemesh_frame
from blink_app.services.db import fetch_recent_aggregates
from blink_app.ui.widgets import ToggleSwitch


@dataclass(slots=True)
class CalibrationSession:
    enabled: bool
    required_open_seconds: float
    blink_target_count: int
    open_started_at: float | None = None
    last_open_sample_at: float | None = None
    stable_open_elapsed: float = 0.0
    blink_started_at: float | None = None
    stage: str = "idle"
    open_samples_left: list[float] | None = None
    open_samples_right: list[float] | None = None
    collected_blink_minima: list[float] | None = None
    blink_active: bool = False
    current_blink_min_ratio: float = 1.0
    completed: bool = False

    def __post_init__(self) -> None:
        if self.open_samples_left is None:
            self.open_samples_left = []
        if self.open_samples_right is None:
            self.open_samples_right = []
        if self.collected_blink_minima is None:
            self.collected_blink_minima = []


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
        self._camera_index_in_use = self._args.camera_index
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
        self._calibration = self._build_calibration_session()

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

    def _build_calibration_session(self) -> CalibrationSession:
        calibration_seconds = max(
            0.0,
            float(getattr(self._args, "calibration_seconds", CALIBRATION_SECONDS)),
        )
        blink_target_count = max(
            0,
            int(getattr(self._args, "calibration_blinks", CALIBRATION_BLINKS)),
        )
        enabled = calibration_seconds > 0.0
        return CalibrationSession(
            enabled=enabled,
            required_open_seconds=calibration_seconds,
            blink_target_count=blink_target_count,
        )

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

    @staticmethod
    def _eye_indicator_rect(
        eye_landmarks: list[tuple[float, float]],
        frame_width: int,
        frame_height: int,
    ) -> tuple[tuple[int, int], tuple[int, int]] | None:
        if not eye_landmarks:
            return None

        xs = [point[0] for point in eye_landmarks if math.isfinite(point[0])]
        ys = [point[1] for point in eye_landmarks if math.isfinite(point[1])]
        if len(xs) != len(eye_landmarks) or len(ys) != len(eye_landmarks):
            return None

        min_x = min(xs)
        max_x = max(xs)
        min_y = min(ys)
        max_y = max(ys)
        span_x = max_x - min_x
        span_y = max_y - min_y
        side = max(span_x, span_y) * 1.8
        side = max(12.0, side)

        center_x = (min_x + max_x) / 2.0
        center_y = (min_y + max_y) / 2.0
        half_side = side / 2.0

        left = max(0, int(round(center_x - half_side)))
        top = max(0, int(round(center_y - half_side)))
        right = min(frame_width - 1, int(round(center_x + half_side)))
        bottom = min(frame_height - 1, int(round(center_y + half_side)))
        if right <= left or bottom <= top:
            return None

        return (left, top), (right, bottom)

    @staticmethod
    def _draw_eye_indicator(
        rgb_frame: np.ndarray,
        eye_landmarks: list[tuple[float, float]],
    ) -> None:
        height, width = rgb_frame.shape[:2]
        rect = BlinkWindow._eye_indicator_rect(eye_landmarks, width, height)
        if rect is None:
            return

        cv2_module = get_cv2()
        cv2_module.rectangle(
            rgb_frame,
            rect[0],
            rect[1],
            (72, 255, 140),
            2,
        )

    @staticmethod
    def _percentile(values: list[float], percentile: float) -> float:
        if not values:
            raise ValueError("Cannot compute percentile of an empty list.")

        ordered = sorted(values)
        index = max(0, min(len(ordered) - 1, int(round((len(ordered) - 1) * percentile))))
        return ordered[index]

    def _draw_status_overlay(
        self,
        rgb_frame: np.ndarray,
        lines: list[str],
        color: tuple[int, int, int] = (255, 228, 120),
    ) -> None:
        if not lines:
            return

        cv2_module = get_cv2()
        line_height = 28
        box_height = 20 + (line_height * len(lines))
        cv2_module.rectangle(
            rgb_frame,
            (12, 12),
            (min(rgb_frame.shape[1] - 12, 520), 12 + box_height),
            (24, 32, 48),
            -1,
        )
        for index, line in enumerate(lines):
            y = 40 + (index * line_height)
            cv2_module.putText(
                rgb_frame,
                line,
                (24, y),
                cv2_module.FONT_HERSHEY_SIMPLEX,
                0.7,
                color,
                2,
                cv2_module.LINE_AA,
            )

    def _stable_open_sample(
        self,
        left_aperture: float,
        right_aperture: float,
    ) -> bool:
        eye_diff = abs(left_aperture - right_aperture)
        if eye_diff > BLINK_MAX_EYE_DIFF:
            return False

        minimum_open_aperture = max(
            0.12,
            (self._args.ear_threshold * 0.7),
        )
        return min(left_aperture, right_aperture) >= minimum_open_aperture

    def _apply_open_eye_calibration(self) -> None:
        if not self._calibration.open_samples_left or not self._calibration.open_samples_right:
            return

        left_open = self._percentile(self._calibration.open_samples_left, 0.85)
        right_open = self._percentile(self._calibration.open_samples_right, 0.85)
        average_open = (left_open + right_open) / 2.0
        aperture_threshold = max(0.12, min(0.35, average_open * 0.8))
        self._blink_state.apply_personal_calibration(
            left_open,
            right_open,
            aperture_threshold=aperture_threshold,
        )
        self._app_logger.info(
            "Open-eye calibration applied (left=%.3f, right=%.3f, threshold=%.3f).",
            left_open,
            right_open,
            aperture_threshold,
        )

    def _finish_calibration(self, now_ts: float) -> None:
        blink_minima = self._calibration.collected_blink_minima or []
        if blink_minima:
            median_min_ratio = self._percentile(blink_minima, 0.5)
            close_avg_ratio = max(0.74, min(0.9, median_min_ratio + 0.22))
            close_max_ratio = max(close_avg_ratio + 0.03, min(0.95, median_min_ratio + 0.28))
            deep_avg_ratio = max(0.58, min(close_avg_ratio - 0.04, median_min_ratio + 0.08))
            self._blink_state.apply_personal_calibration(
                self._blink_state.left_open_reference_aperture or 0.0,
                self._blink_state.right_open_reference_aperture or 0.0,
                aperture_threshold=self._blink_state.calibrated_aperture_threshold,
                close_avg_ratio=close_avg_ratio,
                close_max_ratio=close_max_ratio,
                deep_avg_ratio=deep_avg_ratio,
            )
            self._app_logger.info(
                "Blink calibration applied (min_ratio=%.3f, close_ratio=%.3f, deep_ratio=%.3f).",
                median_min_ratio,
                close_avg_ratio,
                deep_avg_ratio,
            )

        self._blink_state.last_blink_time = now_ts
        self._calibration.stage = "done"
        self._calibration.completed = True

    def _handle_calibration(
        self,
        left_aperture: float,
        right_aperture: float,
        now_ts: float,
    ) -> list[str]:
        if not self._calibration.enabled or self._calibration.completed:
            return []

        if self._calibration.stage == "idle":
            self._calibration.stage = "open"
            self._calibration.open_started_at = now_ts

        if self._calibration.stage == "open":
            if self._stable_open_sample(left_aperture, right_aperture):
                self._calibration.open_samples_left.append(left_aperture)
                self._calibration.open_samples_right.append(right_aperture)
                if self._calibration.last_open_sample_at is not None:
                    stable_delta = max(0.0, now_ts - self._calibration.last_open_sample_at)
                    self._calibration.stable_open_elapsed += min(stable_delta, 0.2)
                self._calibration.last_open_sample_at = now_ts
            else:
                self._calibration.last_open_sample_at = None

            collected = len(self._calibration.open_samples_left)
            if collected >= 12 and self._calibration.stable_open_elapsed >= self._calibration.required_open_seconds:
                self._apply_open_eye_calibration()
                if self._calibration.blink_target_count > 0:
                    self._calibration.stage = "blink"
                    self._calibration.blink_started_at = now_ts
                else:
                    self._finish_calibration(now_ts)
            else:
                remaining_seconds = max(
                    0.0,
                    self._calibration.required_open_seconds - self._calibration.stable_open_elapsed,
                )
                return [
                    "Calibrating: keep your eyes open",
                    f"Stable time remaining: {remaining_seconds:.1f}s",
                ]

        if self._calibration.stage == "blink":
            ratios = self._blink_state.sample_ratios(left_aperture, right_aperture)
            if ratios is not None:
                avg_ratio = ratios[2]
                ratio_gap = ratios[4]
                eye_diff = abs(left_aperture - right_aperture)
                symmetric = eye_diff <= BLINK_MAX_EYE_DIFF and ratio_gap <= BLINK_MAX_RATIO_GAP
                if self._calibration.blink_active:
                    self._calibration.current_blink_min_ratio = min(
                        self._calibration.current_blink_min_ratio,
                        avg_ratio,
                    )
                    if avg_ratio >= 0.96:
                        if self._calibration.current_blink_min_ratio <= 0.86:
                            self._calibration.collected_blink_minima.append(
                                self._calibration.current_blink_min_ratio
                            )
                        self._calibration.blink_active = False
                        self._calibration.current_blink_min_ratio = 1.0
                elif symmetric and avg_ratio <= 0.88:
                    self._calibration.blink_active = True
                    self._calibration.current_blink_min_ratio = avg_ratio

            collected_blinks = len(self._calibration.collected_blink_minima)
            if collected_blinks >= self._calibration.blink_target_count:
                self._finish_calibration(now_ts)
            else:
                remaining = self._calibration.blink_target_count - collected_blinks
                return [
                    "Calibration: blink naturally a few times",
                    f"Blinks remaining: {remaining}",
                ]

        if self._calibration.completed:
            return ["Calibration complete"]

        return []

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

        if self._camera_result.camera_index is not None:
            self._camera_index_in_use = self._camera_result.camera_index

        self._cap = open_video_capture(
            self._camera_index_in_use,
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
                "Camera initialized (index=%d, backend=%s, ready=%.2fs).",
                self._camera_index_in_use,
                self._camera_result.backend,
                self._camera_result.ready_seconds or 0.0,
            )
            if self._camera_index_in_use != self._args.camera_index:
                self._app_logger.warning(
                    "Requested camera index %d was unavailable. Falling back to index %d.",
                    self._args.camera_index,
                    self._camera_index_in_use,
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

        overlay_lines: list[str] = []
        if first_face is not None:
            height, width = frame.shape[:2]
            left_landmarks = self._eye_landmarks(first_face, LEFT_EYE, width, height)
            right_landmarks = self._eye_landmarks(first_face, RIGHT_EYE, width, height)
            self._draw_eye_indicator(rgb_frame, left_landmarks)
            self._draw_eye_indicator(rgb_frame, right_landmarks)
            left_aperture = eye_aperture_ratio(
                left_landmarks,
                EYE_APERTURE_CORNERS,
                EYE_APERTURE_GAP_PAIRS,
            )
            right_aperture = eye_aperture_ratio(
                right_landmarks,
                EYE_APERTURE_CORNERS,
                EYE_APERTURE_GAP_PAIRS,
            )
            aperture = (left_aperture + right_aperture) / 2.0
            overlay_lines = self._handle_calibration(left_aperture, right_aperture, now_ts)
            if self._calibration.completed or not self._calibration.enabled:
                self._blink_state.update(
                    aperture,
                    now_dt,
                    now_ts,
                    self._args.ear_threshold,
                    self._args.ear_consec_frames,
                    self._blink_logger,
                    self._db_conn,
                    left_aperture=left_aperture,
                    right_aperture=right_aperture,
                )
        else:
            self._blink_state.observe_missing_face(now_ts)
            if self._calibration.enabled and not self._calibration.completed:
                if self._calibration.stage == "blink":
                    overlay_lines = ["Calibration: blink naturally a few times", "Face not detected"]
                else:
                    overlay_lines = ["Calibrating: keep your eyes open", "Face not detected"]

        if overlay_lines:
            self._draw_status_overlay(rgb_frame, overlay_lines)

        if self._calibration.completed or not self._calibration.enabled:
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

