from collections.abc import Callable

import cv2
import numpy as np

from blink_app.aggregates import AggregateState
from blink_app.detection import BlinkState


def _format_last_blink(last_blink_time: float, now_ts: float) -> str:
    if last_blink_time <= 0:
        return "--"
    seconds_ago = max(0, int(now_ts - last_blink_time))
    return f"{seconds_ago}s ago"


def render_overlay(
    frame: np.ndarray,
    state: AggregateState,
    blink_state: BlinkState,
    now_ts: float,
    alerts_enabled: bool,
) -> np.ndarray:
    height, width = frame.shape[:2]
    panel_width = 360
    panel = np.zeros((height, panel_width, 3), dtype=np.uint8)
    panel[:] = (20, 22, 28)

    def add_text(
        text: str,
        origin: tuple[int, int],
        color: tuple[int, int, int] = (255, 255, 255),
        scale: float = 0.6,
        thickness: int = 2,
    ) -> None:
        cv2.putText(
            panel,
            text,
            origin,
            cv2.FONT_HERSHEY_SIMPLEX,
            scale,
            color,
            thickness,
        )

    def draw_card(
        top: int,
        title: str,
        value: str | None,
        value_color: tuple[int, int, int] | None = None,
        right_drawer: Callable[[int, int, int, int], None] | None = None,
    ) -> int:
        left = 14
        right = panel_width - 14
        height_px = 62
        cv2.rectangle(panel, (left, top), (right, top + height_px), (42, 46, 56), -1)
        cv2.rectangle(panel, (left, top), (right, top + height_px), (70, 74, 88), 2)
        add_text(title, (left + 16, top + 26), (200, 205, 220), 0.6, 1)
        if value is not None and value_color is not None:
            (value_width, _), _ = cv2.getTextSize(
                value,
                cv2.FONT_HERSHEY_SIMPLEX,
                0.72,
                2,
            )
            value_x = right - 14 - value_width
            add_text(value, (value_x, top + 32), value_color, 0.72, 2)
        if right_drawer is not None:
            right_drawer(left, right, top, height_px)
        return top + height_px + 14

    def draw_toggle(
        left: int,
        right: int,
        top: int,
        height_px: int,
        enabled: bool,
    ) -> None:
        track_width = 52
        track_height = 24
        track_left = right - 18 - track_width
        track_top = top + (height_px - track_height) // 2
        track_color = (80, 220, 120) if enabled else (78, 82, 94)
        knob_color = (245, 245, 245) if enabled else (200, 202, 210)
        radius = track_height // 2
        cv2.rectangle(
            panel,
            (track_left + radius, track_top),
            (track_left + track_width - radius, track_top + track_height),
            track_color,
            -1,
        )
        cv2.circle(panel, (track_left + radius, track_top + radius), radius, track_color, -1)
        cv2.circle(
            panel,
            (track_left + track_width - radius, track_top + radius),
            radius,
            track_color,
            -1,
        )
        knob_x = track_left + track_width - radius if enabled else track_left + radius
        cv2.circle(panel, (knob_x, track_top + radius), radius - 2, knob_color, -1)
        cv2.circle(panel, (knob_x, track_top + radius), radius - 2, (70, 74, 88), 1)

    add_text("Blink Tracker — Live Preview", (18, 34), (210, 230, 255), 0.62, 2)

    cursor = 68
    cursor = draw_card(cursor, "Session blinks", f"{blink_state.blink_counter}", (255, 255, 255))
    cursor = draw_card(
        cursor,
        "Last blink",
        _format_last_blink(blink_state.last_blink_time, now_ts),
        (255, 255, 255),
    )
    cursor = draw_card(cursor, "Blinks / minute", f"{state.blinks_1m}", (255, 255, 255))
    cursor = draw_card(
        cursor,
        "Reminder",
        None,
        right_drawer=lambda left, right, top, height_px: draw_toggle(
            left,
            right,
            top,
            height_px,
            alerts_enabled,
        ),
    )

    add_text("Press ESC to exit • Data", (18, cursor + 6), (170, 175, 190), 0.52, 1)
    add_text("saved locally", (18, cursor + 30), (170, 175, 190), 0.52, 1)

    combined = np.hstack((frame, panel))
    return combined
