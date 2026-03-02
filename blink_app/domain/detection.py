import logging
import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from collections.abc import Sequence

from blink_app.constants import BLINK_MIN_CLOSED_SECONDS
from blink_app.services.db import record_blink_event


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
    if C <= 1e-9:
        # Degenerate eye geometry can occur on bad/partial landmark frames.
        # Returning a high EAR avoids false blink triggers and prevents crashes.
        return 1.0
    ear = (A + B) / (2.0 * C)
    return ear


@dataclass
class BlinkState:
    frame_counter: int = 0
    blink_counter: int = 0
    last_blink_time: float = 0.0
    eye_closed_since: float | None = None
    min_ear_during_closure: float = 1.0

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
            if self.eye_closed_since is None:
                self.eye_closed_since = now_ts
                self.min_ear_during_closure = ear
            elif ear < self.min_ear_during_closure:
                self.min_ear_during_closure = ear
        else:
            closure_duration_seconds = 0.0
            if self.eye_closed_since is not None:
                closure_duration_seconds = max(0.0, now_ts - self.eye_closed_since)

            enough_frames = self.frame_counter >= ear_consec_frames
            enough_duration = (
                self.frame_counter > 0
                and closure_duration_seconds >= BLINK_MIN_CLOSED_SECONDS
                and self.min_ear_during_closure <= ear_threshold - 0.015
            )

            if enough_frames or enough_duration:
                self.blink_counter += 1
                self.last_blink_time = now_ts
                blink_logger.info("Blink #%d", self.blink_counter)
                record_blink_event(db_conn, now_dt)
            self.frame_counter = 0
            self.eye_closed_since = None
            self.min_ear_during_closure = 1.0
