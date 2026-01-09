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


    combined = np.hstack((frame, panel))
    return combined
