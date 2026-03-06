import logging
import math
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from blink_app.constants import (
    BLINK_ABSOLUTE_MARGIN,
    BLINK_BASELINE_FALL_ALPHA,
    BLINK_BASELINE_OPEN_MARGIN,
    BLINK_BASELINE_RISE_ALPHA,
    BLINK_COOLDOWN_SECONDS,
    BLINK_MAX_CLOSED_SECONDS,
    BLINK_MAX_EYE_DIFF,
    BLINK_MIN_CLOSED_FRAMES,
    BLINK_MIN_CLOSED_SECONDS,
    BLINK_RELATIVE_CLOSE_DROP,
    BLINK_RELATIVE_DEEP_DROP,
    BLINK_REOPEN_DELTA,
    BLINK_SINGLE_FRAME_DEEP_MARGIN,
)
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
    if not all(math.isfinite(value) for value in (A, B, C)) or C <= 1e-9:
        # Degenerate or corrupt eye geometry can occur on bad/partial landmark frames.
        # Returning a high EAR avoids false blink triggers and prevents state poisoning.
        return 1.0
    ear = (A + B) / (2.0 * C)
    if not math.isfinite(ear):
        return 1.0

    return ear


@dataclass
class BlinkState:
    frame_counter: int = 0
    blink_counter: int = 0
    last_blink_time: float = 0.0
    eye_closed_since: float | None = None
    min_ear_during_closure: float = 1.0
    max_drop_during_closure: float = 0.0
    max_eye_diff_during_closure: float = 0.0
    open_reference_ear: float | None = None
    cooldown_until: float = 0.0

    @staticmethod
    def _is_valid_sample(*values: float) -> bool:
        return all(math.isfinite(value) and value >= 0.0 for value in values)

    def _reset_closure(self) -> None:
        self.frame_counter = 0
        self.eye_closed_since = None
        self.min_ear_during_closure = 1.0
        self.max_drop_during_closure = 0.0
        self.max_eye_diff_during_closure = 0.0

    def _update_open_reference(
        self,
        ear: float,
        ear_threshold: float,
        eye_diff: float,
        eye_min: float,
        now_ts: float,
    ) -> None:
        stable_open_sample = (
            eye_diff <= BLINK_MAX_EYE_DIFF
            and eye_min >= (ear_threshold + BLINK_BASELINE_OPEN_MARGIN)
        )

        if self.open_reference_ear is None:
            if stable_open_sample:
                self.open_reference_ear = ear

            return

        if self.eye_closed_since is not None or now_ts < self.cooldown_until or not stable_open_sample:
            return

        alpha = BLINK_BASELINE_RISE_ALPHA
        if ear < self.open_reference_ear:
            alpha = BLINK_BASELINE_FALL_ALPHA
        self.open_reference_ear = (self.open_reference_ear * (1.0 - alpha)) + (ear * alpha)

    def update(
        self,
        ear: float,
        now_dt: datetime,
        now_ts: float,
        ear_threshold: float,
        ear_consec_frames: int,
        blink_logger: logging.Logger,
        db_conn: sqlite3.Connection,
        left_ear: float | None = None,
        right_ear: float | None = None,
    ) -> None:
        left_eye_ear = ear if left_ear is None else left_ear
        right_eye_ear = ear if right_ear is None else right_ear
        if not self._is_valid_sample(ear, left_eye_ear, right_eye_ear):
            if self.eye_closed_since is not None and (now_ts - self.eye_closed_since) > BLINK_MAX_CLOSED_SECONDS:
                self._reset_closure()
            return

        eye_diff = abs(left_eye_ear - right_eye_ear)
        eye_min = min(left_eye_ear, right_eye_ear)
        eye_max = max(left_eye_ear, right_eye_ear)

        self._update_open_reference(ear, ear_threshold, eye_diff, eye_min, now_ts)

        baseline_drop = 0.0
        if self.open_reference_ear is not None:
            baseline_drop = max(0.0, self.open_reference_ear - ear)

        close_by_absolute = (
            eye_min <= (ear_threshold - BLINK_ABSOLUTE_MARGIN)
            and eye_max <= (ear_threshold + 0.004)
            and eye_diff <= BLINK_MAX_EYE_DIFF
        )
        close_by_relative = (
            baseline_drop >= BLINK_RELATIVE_CLOSE_DROP
            and ear <= (ear_threshold + 0.05)
            and eye_diff <= BLINK_MAX_EYE_DIFF
        )
        close_condition = close_by_absolute or close_by_relative

        open_threshold = ear_threshold + 0.015
        if self.open_reference_ear is not None:
            open_threshold = max(open_threshold, self.open_reference_ear - 0.008)

        if self.eye_closed_since is None:
            if close_condition and now_ts >= self.cooldown_until:
                self.frame_counter = 1
                self.eye_closed_since = now_ts
                self.min_ear_during_closure = ear
                self.max_drop_during_closure = baseline_drop
                self.max_eye_diff_during_closure = eye_diff
            return

        if close_condition:
            self.frame_counter += 1
            if ear < self.min_ear_during_closure:
                self.min_ear_during_closure = ear
            if baseline_drop > self.max_drop_during_closure:
                self.max_drop_during_closure = baseline_drop
            if eye_diff > self.max_eye_diff_during_closure:
                self.max_eye_diff_during_closure = eye_diff
            return

        closure_duration_seconds = max(0.0, now_ts - self.eye_closed_since)
        if ear >= open_threshold:
            min_frames_for_blink = max(BLINK_MIN_CLOSED_FRAMES, min(ear_consec_frames, 4))
            enough_frames = self.frame_counter >= min_frames_for_blink
            allow_single_frame_deep = (
                self.frame_counter == 1
                and closure_duration_seconds >= BLINK_MIN_CLOSED_SECONDS
                and self.min_ear_during_closure <= (ear_threshold - BLINK_SINGLE_FRAME_DEEP_MARGIN)
            )
            enough_duration = (
                closure_duration_seconds >= BLINK_MIN_CLOSED_SECONDS
                and (self.frame_counter >= BLINK_MIN_CLOSED_FRAMES or allow_single_frame_deep)
            )
            deep_absolute = self.min_ear_during_closure <= (ear_threshold - BLINK_ABSOLUTE_MARGIN)
            deep_relative = self.max_drop_during_closure >= BLINK_RELATIVE_DEEP_DROP
            deep_enough = deep_absolute or deep_relative
            reopened_strongly = (ear - self.min_ear_during_closure) >= BLINK_REOPEN_DELTA
            quick_enough = closure_duration_seconds <= BLINK_MAX_CLOSED_SECONDS
            symmetric_enough = self.max_eye_diff_during_closure <= BLINK_MAX_EYE_DIFF

            if (
                deep_enough
                and reopened_strongly
                and quick_enough
                and symmetric_enough
                and (enough_frames or enough_duration)
            ):
                self.blink_counter += 1
                self.last_blink_time = now_ts
                self.cooldown_until = now_ts + BLINK_COOLDOWN_SECONDS
                blink_logger.info("Blink #%d", self.blink_counter)
                record_blink_event(db_conn, now_dt)

            self._reset_closure()
            return

        if closure_duration_seconds > BLINK_MAX_CLOSED_SECONDS:
            self._reset_closure()

