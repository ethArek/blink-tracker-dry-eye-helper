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
) -> np.ndarray:
    height, width = frame.shape[:2]
    panel_width = 360
    panel = np.zeros((height, panel_width, 3), dtype=np.uint8)
    panel[:] = (24, 24, 28)

    def add_text(
        text: str,
        origin: tuple[int, int],
        color: tuple[int, int, int] = (255, 255, 255),
        scale: float = 0.6,
    ) -> None:
        cv2.putText(
            panel,
            text,
            origin,
            cv2.FONT_HERSHEY_SIMPLEX,
            scale,
            color,
            2,
        )

    def draw_section_box(top: int, height_px: int, title: str) -> int:
        padding = 14
        left = 12
        right = panel_width - 12
        cv2.rectangle(
            panel,
            (left, top),
            (right, top + height_px),
            (60, 60, 70),
            2,
        )
        add_text(title, (left + padding, top + 28), (0, 255, 255), 0.62)
        return top + 45

    def draw_button(origin: tuple[int, int], size: tuple[int, int], label: str) -> None:
        x, y = origin
        w, h = size
        cv2.rectangle(panel, (x, y), (x + w, y + h), (80, 80, 95), -1)
        cv2.rectangle(panel, (x, y), (x + w, y + h), (120, 120, 140), 2)
        text_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)[0]
        text_x = x + (w - text_size[0]) // 2
        text_y = y + (h + text_size[1]) // 2
        add_text(label, (text_x, text_y), (240, 240, 240), 0.55)

    add_text("Blink Monitor", (20, 30), (0, 255, 255), 0.75)
    add_text(f"Session blinks: {blink_state.blink_counter}", (20, 60))
    add_text(
        f"Last blink: {_format_last_blink(blink_state.last_blink_time, now_ts)}",
        (20, 85),
    )

    stats_top = 110
    stats_cursor = draw_section_box(stats_top, 140, "Stats")
    add_text(f"1 min:  {state.blinks_1m}", (28, stats_cursor + 5))
    add_text(f"10 min: {state.blinks_10m}", (28, stats_cursor + 30))
    add_text(f"1 hour: {state.blinks_1h}", (28, stats_cursor + 55))
    add_text(f"Today:  {state.blinks_day}", (28, stats_cursor + 80))

    charts_top = stats_top + 160
    charts_cursor = draw_section_box(charts_top, 160, "Charts")
    chart_left = 28
    chart_top = charts_cursor + 10
    chart_width = panel_width - 56
    chart_height = 80
    cv2.rectangle(
        panel,
        (chart_left, chart_top),
        (chart_left + chart_width, chart_top + chart_height),
        (90, 90, 110),
        2,
    )
    add_text("Placeholder chart", (chart_left + 12, chart_top + 45), (160, 160, 180), 0.55)

    filters_top = charts_top + 180
    draw_section_box(filters_top, 170, "Filters")
    draw_button((28, filters_top + 55), (140, 42), "Last 5 min")
    draw_button((190, filters_top + 55), (140, 42), "Last hour")
    draw_button((28, filters_top + 110), (140, 42), "Today")
    draw_button((190, filters_top + 110), (140, 42), "All time")

    combined = np.hstack((frame, panel))
    return combined
