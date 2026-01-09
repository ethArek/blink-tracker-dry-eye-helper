import logging
import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from collections.abc import Sequence

from blink_app.db import record_blink_event


def eye_aspect_ratio(
    landmarks: Sequence[tuple[float, float]],
    eye_indices: Sequence[int],
) -> float:
    def euclidean(p1: tuple[float, float], p2: tuple[float, float]) -> float:
        return math.dist(p1, p2)

    p = [landmarks[i] for i in eye_indices]
    A = euclidean(p[1], p[5])
    B = euclidean(p[2], p[4])
    C = euclidean(p[0], p[3])
    ear = (A + B) / (2.0 * C)
    return ear


@dataclass
class BlinkState:
    frame_counter: int = 0
    blink_counter: int = 0
    last_blink_time: float = 0.0

    def update(
        self,
        ear: float,
        now_dt: datetime,
        now_ts: float,
        ear_threshold: float,
        ear_consec_frames: int,
        blink_logger: logging.Logger,
        db_conn: sqlite3.Connection,
    ) -> None:
        if ear < ear_threshold:
            self.frame_counter += 1
        else:
            if self.frame_counter >= ear_consec_frames:
                self.blink_counter += 1
                self.last_blink_time = now_ts
                blink_logger.info("Blink #%d", self.blink_counter)
                record_blink_event(db_conn, now_dt)
            self.frame_counter = 0
