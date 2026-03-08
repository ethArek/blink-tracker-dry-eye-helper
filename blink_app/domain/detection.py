import logging
import math
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from blink_app.constants import (
    BLINK_ABSOLUTE_MARGIN,
    BLINK_BASELINE_DRIFT_MARGIN,
    BLINK_BASELINE_FALL_ALPHA,
    BLINK_BASELINE_OPEN_MARGIN,
    BLINK_BASELINE_RISE_ALPHA,
    BLINK_CLOSE_AVG_RATIO,
    BLINK_CLOSE_MAX_RATIO,
    BLINK_COOLDOWN_SECONDS,
    BLINK_DEEP_AVG_RATIO,
    BLINK_MAX_CLOSED_SECONDS,
    BLINK_MAX_EYE_DIFF,
    BLINK_MAX_RATIO_GAP,
    BLINK_MISSING_FACE_BASELINE_RESET_SECONDS,
    BLINK_MISSING_FACE_RESET_SECONDS,
    BLINK_MIN_CLOSED_FRAMES,
    BLINK_MIN_CLOSED_SECONDS,
    BLINK_LOCAL_REOPEN_APERTURE_MARGIN,
    BLINK_LOCAL_REOPEN_RATIO_MARGIN,
    BLINK_REOPEN_AVG_RATIO,
    BLINK_REOPEN_DELTA,
    BLINK_REOPEN_MAX_RATIO,
    BLINK_REOPEN_RATIO_DELTA,
    BLINK_SMOOTHING_ALPHA,
)
from blink_app.services.db import record_blink_event

BLINK_PHASE_OPEN = "open"
BLINK_PHASE_CLOSING = "closing"
BLINK_PHASE_CLOSED = "closed"
BLINK_PHASE_OPENING = "opening"


def _euclidean(p1: tuple[float, float], p2: tuple[float, float]) -> float:
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[midpoint]

    return (ordered[midpoint - 1] + ordered[midpoint]) / 2.0


def eye_aperture_ratio(
    landmarks: Sequence[tuple[float, float]],
    corner_indices: tuple[int, int],
    gap_pairs: Sequence[tuple[int, int]],
) -> float:
    horizontal = _euclidean(
        landmarks[corner_indices[0]],
        landmarks[corner_indices[1]],
    )
    if not math.isfinite(horizontal) or horizontal <= 1e-9:
        return 1.0

    normalized_gaps: list[float] = []
    for upper_index, lower_index in gap_pairs:
        gap = _euclidean(landmarks[upper_index], landmarks[lower_index])
        if not math.isfinite(gap):
            continue

        normalized_gap = gap / horizontal
        if math.isfinite(normalized_gap):
            normalized_gaps.append(normalized_gap)

    if not normalized_gaps:
        # Degenerate or corrupt eye geometry can occur on bad/partial landmark frames.
        # Returning a high aperture avoids false blink triggers and prevents state poisoning.
        return 1.0

    aperture = _median(normalized_gaps)
    if not math.isfinite(aperture):
        return 1.0

    return aperture


def eye_aspect_ratio(
    landmarks: Sequence[tuple[float, float]],
    eye_indices: Sequence[int],
) -> float:
    relative_landmarks = [landmarks[index] for index in eye_indices]
    return eye_aperture_ratio(
        relative_landmarks,
        corner_indices=(0, 3),
        gap_pairs=((1, 5), (2, 4)),
    )


@dataclass(slots=True)
class BlinkState:
    frame_counter: int = 0
    blink_counter: int = 0
    last_blink_time: float = 0.0
    phase: str = BLINK_PHASE_OPEN
    eye_closed_since: float | None = None
    smoothed_left_aperture: float | None = None
    smoothed_right_aperture: float | None = None
    left_open_reference_aperture: float | None = None
    right_open_reference_aperture: float | None = None
    min_aperture_during_closure: float = 1.0
    min_ratio_during_closure: float = 1.0
    max_eye_diff_during_closure: float = 0.0
    max_ratio_gap_during_closure: float = 0.0
    cooldown_until: float = 0.0
    last_valid_sample_time: float | None = None
    previous_avg_aperture: float | None = None
    previous_avg_ratio: float | None = None
    pre_closure_avg_aperture: float | None = None
    pre_closure_avg_ratio: float | None = None
    close_avg_ratio: float = BLINK_CLOSE_AVG_RATIO
    close_max_ratio: float = BLINK_CLOSE_MAX_RATIO
    deep_avg_ratio: float = BLINK_DEEP_AVG_RATIO
    reopen_avg_ratio: float = BLINK_REOPEN_AVG_RATIO
    reopen_max_ratio: float = BLINK_REOPEN_MAX_RATIO
    reopen_ratio_delta: float = BLINK_REOPEN_RATIO_DELTA
    calibrated_aperture_threshold: float | None = None

    @staticmethod
    def _is_valid_sample(*values: float) -> bool:
        return all(math.isfinite(value) and value >= 0.0 for value in values)

    @property
    def open_reference_aperture(self) -> float | None:
        if self.left_open_reference_aperture is None or self.right_open_reference_aperture is None:
            return None

        return (self.left_open_reference_aperture + self.right_open_reference_aperture) / 2.0

    @property
    def open_reference_ear(self) -> float | None:
        return self.open_reference_aperture

    def _references_ready(self) -> bool:
        return (
            self.left_open_reference_aperture is not None
            and self.right_open_reference_aperture is not None
        )

    def aperture_threshold(self, default_threshold: float) -> float:
        if self.calibrated_aperture_threshold is None:
            return default_threshold

        return self.calibrated_aperture_threshold

    def _reset_closure(self) -> None:
        self.phase = BLINK_PHASE_OPEN
        self.frame_counter = 0
        self.eye_closed_since = None
        self.min_aperture_during_closure = 1.0
        self.min_ratio_during_closure = 1.0
        self.max_eye_diff_during_closure = 0.0
        self.max_ratio_gap_during_closure = 0.0
        self.pre_closure_avg_aperture = None
        self.pre_closure_avg_ratio = None

    def _reset_tracking(self, reset_baseline: bool) -> None:
        self._reset_closure()
        self.smoothed_left_aperture = None
        self.smoothed_right_aperture = None
        self.previous_avg_aperture = None
        self.previous_avg_ratio = None
        if reset_baseline:
            self.left_open_reference_aperture = None
            self.right_open_reference_aperture = None
            self.calibrated_aperture_threshold = None

    def observe_missing_face(self, now_ts: float) -> None:
        if self.last_valid_sample_time is None:
            return

        missing_for_seconds = max(0.0, now_ts - self.last_valid_sample_time)
        if missing_for_seconds < BLINK_MISSING_FACE_RESET_SECONDS:
            return

        self._reset_tracking(
            reset_baseline=missing_for_seconds >= BLINK_MISSING_FACE_BASELINE_RESET_SECONDS
        )

    @staticmethod
    def _smooth(previous: float | None, current: float) -> float:
        if previous is None:
            return current

        return (previous * (1.0 - BLINK_SMOOTHING_ALPHA)) + (current * BLINK_SMOOTHING_ALPHA)

    @staticmethod
    def _adapt_reference(reference: float | None, sample: float) -> float:
        if reference is None:
            return sample

        alpha = BLINK_BASELINE_RISE_ALPHA
        if sample < reference:
            alpha = BLINK_BASELINE_FALL_ALPHA

        return (reference * (1.0 - alpha)) + (sample * alpha)

    def _update_smoothed_apertures(
        self,
        left_aperture: float,
        right_aperture: float,
    ) -> tuple[float, float]:
        self.smoothed_left_aperture = self._smooth(self.smoothed_left_aperture, left_aperture)
        self.smoothed_right_aperture = self._smooth(self.smoothed_right_aperture, right_aperture)
        return self.smoothed_left_aperture, self.smoothed_right_aperture

    def _ratios(self) -> tuple[float, float, float, float, float] | None:
        if (
            self.smoothed_left_aperture is None
            or self.smoothed_right_aperture is None
            or self.left_open_reference_aperture is None
            or self.right_open_reference_aperture is None
            or self.left_open_reference_aperture <= 1e-9
            or self.right_open_reference_aperture <= 1e-9
        ):
            return None

        left_ratio = self.smoothed_left_aperture / self.left_open_reference_aperture
        right_ratio = self.smoothed_right_aperture / self.right_open_reference_aperture
        avg_ratio = (left_ratio + right_ratio) / 2.0
        max_ratio = max(left_ratio, right_ratio)
        ratio_gap = abs(left_ratio - right_ratio)
        return left_ratio, right_ratio, avg_ratio, max_ratio, ratio_gap

    def sample_ratios(
        self,
        left_aperture: float,
        right_aperture: float,
    ) -> tuple[float, float, float, float, float] | None:
        if (
            not self._references_ready()
            or not self._is_valid_sample(left_aperture, right_aperture)
            or self.left_open_reference_aperture is None
            or self.right_open_reference_aperture is None
            or self.left_open_reference_aperture <= 1e-9
            or self.right_open_reference_aperture <= 1e-9
        ):
            return None

        left_ratio = left_aperture / self.left_open_reference_aperture
        right_ratio = right_aperture / self.right_open_reference_aperture
        avg_ratio = (left_ratio + right_ratio) / 2.0
        max_ratio = max(left_ratio, right_ratio)
        ratio_gap = abs(left_ratio - right_ratio)
        return left_ratio, right_ratio, avg_ratio, max_ratio, ratio_gap

    def apply_personal_calibration(
        self,
        left_open_aperture: float,
        right_open_aperture: float,
        aperture_threshold: float | None = None,
        close_avg_ratio: float | None = None,
        close_max_ratio: float | None = None,
        deep_avg_ratio: float | None = None,
    ) -> None:
        if not self._is_valid_sample(left_open_aperture, right_open_aperture):
            return

        self.left_open_reference_aperture = left_open_aperture
        self.right_open_reference_aperture = right_open_aperture
        self.smoothed_left_aperture = left_open_aperture
        self.smoothed_right_aperture = right_open_aperture
        self.previous_avg_aperture = (left_open_aperture + right_open_aperture) / 2.0
        self.previous_avg_ratio = 1.0
        self._reset_closure()

        if aperture_threshold is not None and math.isfinite(aperture_threshold):
            self.calibrated_aperture_threshold = max(0.01, aperture_threshold)
        if close_avg_ratio is not None and math.isfinite(close_avg_ratio):
            self.close_avg_ratio = close_avg_ratio
        if close_max_ratio is not None and math.isfinite(close_max_ratio):
            self.close_max_ratio = close_max_ratio
        if deep_avg_ratio is not None and math.isfinite(deep_avg_ratio):
            self.deep_avg_ratio = deep_avg_ratio

    def _is_stable_open_sample(
        self,
        left_aperture: float,
        right_aperture: float,
        aperture_threshold: float,
        eye_diff: float,
    ) -> bool:
        avg_aperture = (left_aperture + right_aperture) / 2.0
        if eye_diff > BLINK_MAX_EYE_DIFF:
            return False
        if min(left_aperture, right_aperture) < (aperture_threshold + BLINK_BASELINE_OPEN_MARGIN):
            if self.previous_avg_aperture is None:
                return False

            local_open_floor = max(
                aperture_threshold + 0.002,
                self.previous_avg_aperture - BLINK_BASELINE_DRIFT_MARGIN,
            )
            if avg_aperture < local_open_floor:
                return False

        ratios = self._ratios()
        if ratios is None:
            return True

        if (
            ratios[4] <= BLINK_MAX_RATIO_GAP
            and self.previous_avg_aperture is not None
            and avg_aperture >= (self.previous_avg_aperture - BLINK_BASELINE_DRIFT_MARGIN)
        ):
            return True

        return (
            ratios[2] >= self.reopen_avg_ratio
            and ratios[3] >= self.reopen_max_ratio
            and ratios[4] <= BLINK_MAX_RATIO_GAP
        )

    def _update_open_reference(
        self,
        left_aperture: float,
        right_aperture: float,
        aperture_threshold: float,
        eye_diff: float,
        now_ts: float,
    ) -> None:
        if self.phase != BLINK_PHASE_OPEN or now_ts < self.cooldown_until:
            return
        if not self._is_stable_open_sample(
            left_aperture,
            right_aperture,
            aperture_threshold,
            eye_diff,
        ):
            return

        self.left_open_reference_aperture = self._adapt_reference(
            self.left_open_reference_aperture,
            left_aperture,
        )
        self.right_open_reference_aperture = self._adapt_reference(
            self.right_open_reference_aperture,
            right_aperture,
        )

    def _close_condition(
        self,
        avg_aperture: float,
        max_aperture: float,
        eye_diff: float,
        aperture_threshold: float,
    ) -> bool:
        if not self._references_ready():
            return False

        ratios = self._ratios()
        if ratios is None:
            return False

        close_by_absolute = (
            eye_diff <= BLINK_MAX_EYE_DIFF
            and avg_aperture <= (aperture_threshold - BLINK_ABSOLUTE_MARGIN)
            and max_aperture <= (aperture_threshold + 0.01)
        )
        close_by_relative = (
            eye_diff <= BLINK_MAX_EYE_DIFF
            and ratios[4] <= BLINK_MAX_RATIO_GAP
            and ratios[2] <= self.close_avg_ratio
            and ratios[3] <= self.close_max_ratio
        )
        return close_by_absolute or close_by_relative

    def _deep_close_condition(
        self,
        avg_aperture: float,
        avg_ratio: float | None,
        aperture_threshold: float,
    ) -> bool:
        if avg_aperture <= (aperture_threshold - BLINK_ABSOLUTE_MARGIN):
            return True
        if avg_ratio is not None and avg_ratio <= self.deep_avg_ratio:
            return True

        return False

    def _open_condition(
        self,
        avg_aperture: float,
        max_aperture: float,
        aperture_threshold: float,
    ) -> bool:
        open_reference = self.open_reference_aperture
        if open_reference is None:
            return False

        ratios = self._ratios()
        if ratios is not None and (
            ratios[2] >= self.reopen_avg_ratio
            and ratios[3] >= self.reopen_max_ratio
            and ratios[4] <= BLINK_MAX_RATIO_GAP
        ):
            return True

        if (
            ratios is not None
            and self.pre_closure_avg_ratio is not None
            and ratios[4] <= BLINK_MAX_RATIO_GAP
            and ratios[2] >= max(
                self.min_ratio_during_closure + self.reopen_ratio_delta,
                self.pre_closure_avg_ratio - BLINK_LOCAL_REOPEN_RATIO_MARGIN,
            )
        ):
            return True

        if self.pre_closure_avg_aperture is not None:
            local_reopen_floor = max(
                aperture_threshold - BLINK_ABSOLUTE_MARGIN,
                self.pre_closure_avg_aperture - BLINK_LOCAL_REOPEN_APERTURE_MARGIN,
            )
            if (
                avg_aperture >= local_reopen_floor
                and max_aperture >= (local_reopen_floor + 0.004)
            ):
                return True

        return (
            avg_aperture >= max(aperture_threshold + 0.012, open_reference * 0.9)
            and max_aperture >= max(aperture_threshold + 0.02, open_reference * 0.94)
        )

    def _closing_trend(self, avg_aperture: float, avg_ratio: float | None) -> bool:
        if self.previous_avg_aperture is None:
            return True
        if avg_aperture <= self.previous_avg_aperture:
            return True
        if (
            avg_ratio is not None
            and self.previous_avg_ratio is not None
            and avg_ratio <= self.previous_avg_ratio
        ):
            return True

        return False

    def _opening_trend(self, avg_aperture: float, avg_ratio: float | None) -> bool:
        if self.previous_avg_aperture is None:
            return True
        if avg_aperture >= self.previous_avg_aperture:
            return True
        if (
            avg_ratio is not None
            and self.previous_avg_ratio is not None
            and avg_ratio >= self.previous_avg_ratio
        ):
            return True

        return False

    def _begin_closure(
        self,
        now_ts: float,
        avg_aperture: float,
        eye_diff: float,
        avg_ratio: float | None,
        aperture_threshold: float,
    ) -> None:
        self.phase = BLINK_PHASE_CLOSING
        self.frame_counter = 1
        self.eye_closed_since = now_ts
        self.min_aperture_during_closure = avg_aperture
        self.max_eye_diff_during_closure = eye_diff
        self.min_ratio_during_closure = 1.0 if avg_ratio is None else avg_ratio
        self.max_ratio_gap_during_closure = 0.0
        self.pre_closure_avg_aperture = self.previous_avg_aperture
        if self.pre_closure_avg_aperture is None:
            self.pre_closure_avg_aperture = avg_aperture
        self.pre_closure_avg_ratio = self.previous_avg_ratio
        if self.pre_closure_avg_ratio is None:
            self.pre_closure_avg_ratio = avg_ratio

        ratios = self._ratios()
        if ratios is not None:
            self.max_ratio_gap_during_closure = ratios[4]

        if self._deep_close_condition(avg_aperture, avg_ratio, aperture_threshold):
            self.phase = BLINK_PHASE_CLOSED

    def _accumulate_closure(
        self,
        avg_aperture: float,
        eye_diff: float,
        avg_ratio: float | None,
        aperture_threshold: float,
    ) -> None:
        self.frame_counter += 1
        self.min_aperture_during_closure = min(self.min_aperture_during_closure, avg_aperture)
        self.max_eye_diff_during_closure = max(self.max_eye_diff_during_closure, eye_diff)
        if avg_ratio is not None:
            self.min_ratio_during_closure = min(self.min_ratio_during_closure, avg_ratio)

        ratios = self._ratios()
        if ratios is not None:
            self.max_ratio_gap_during_closure = max(self.max_ratio_gap_during_closure, ratios[4])

        if self._deep_close_condition(avg_aperture, avg_ratio, aperture_threshold):
            self.phase = BLINK_PHASE_CLOSED

    def _finalize_closure(
        self,
        now_dt: datetime,
        now_ts: float,
        avg_aperture: float,
        aperture_threshold: float,
        aperture_consec_frames: int,
        blink_logger: logging.Logger,
        db_conn: sqlite3.Connection,
    ) -> None:
        if self.eye_closed_since is None:
            return

        closure_duration_seconds = max(0.0, now_ts - self.eye_closed_since)
        min_frames_for_blink = max(BLINK_MIN_CLOSED_FRAMES, min(aperture_consec_frames, 4))
        enough_frames = self.frame_counter >= min_frames_for_blink
        enough_duration = closure_duration_seconds >= BLINK_MIN_CLOSED_SECONDS
        quick_enough = closure_duration_seconds <= BLINK_MAX_CLOSED_SECONDS
        deep_absolute = self.min_aperture_during_closure <= (aperture_threshold - BLINK_ABSOLUTE_MARGIN)
        deep_relative = self.min_ratio_during_closure <= self.deep_avg_ratio

        ratios = self._ratios()
        reopen_ratio = None if ratios is None else ratios[2]
        reopened_by_absolute = (avg_aperture - self.min_aperture_during_closure) >= BLINK_REOPEN_DELTA
        reopened_by_ratio = (
            reopen_ratio is not None
            and (reopen_ratio - self.min_ratio_during_closure) >= self.reopen_ratio_delta
        )
        symmetric_enough = (
            self.max_eye_diff_during_closure <= BLINK_MAX_EYE_DIFF
            and self.max_ratio_gap_during_closure <= BLINK_MAX_RATIO_GAP
        )

        if (
            quick_enough
            and symmetric_enough
            and (enough_frames or enough_duration)
            and (deep_absolute or deep_relative)
            and (reopened_by_absolute or reopened_by_ratio)
        ):
            self.blink_counter += 1
            self.last_blink_time = now_ts
            self.cooldown_until = now_ts + BLINK_COOLDOWN_SECONDS
            blink_logger.info("Blink #%d", self.blink_counter)
            record_blink_event(db_conn, now_dt)

        self._reset_closure()

    def _store_previous_metrics(
        self,
        avg_aperture: float,
        avg_ratio: float | None,
    ) -> None:
        self.previous_avg_aperture = avg_aperture
        self.previous_avg_ratio = avg_ratio

    def update(
        self,
        aperture: float,
        now_dt: datetime,
        now_ts: float,
        ear_threshold: float,
        ear_consec_frames: int,
        blink_logger: logging.Logger,
        db_conn: sqlite3.Connection,
        left_aperture: float | None = None,
        right_aperture: float | None = None,
    ) -> None:
        left_eye_aperture = aperture if left_aperture is None else left_aperture
        right_eye_aperture = aperture if right_aperture is None else right_aperture
        if not self._is_valid_sample(aperture, left_eye_aperture, right_eye_aperture):
            self.observe_missing_face(now_ts)
            return

        self.last_valid_sample_time = now_ts
        left_eye_aperture, right_eye_aperture = self._update_smoothed_apertures(
            left_eye_aperture,
            right_eye_aperture,
        )
        aperture_threshold = self.aperture_threshold(ear_threshold)
        avg_aperture = (left_eye_aperture + right_eye_aperture) / 2.0
        max_aperture = max(left_eye_aperture, right_eye_aperture)
        eye_diff = abs(left_eye_aperture - right_eye_aperture)

        self._update_open_reference(
            left_eye_aperture,
            right_eye_aperture,
            aperture_threshold,
            eye_diff,
            now_ts,
        )

        ratios = self._ratios()
        avg_ratio = None if ratios is None else ratios[2]
        close_condition = self._close_condition(
            avg_aperture,
            max_aperture,
            eye_diff,
            aperture_threshold,
        )
        open_condition = self._open_condition(avg_aperture, max_aperture, aperture_threshold)

        if self.eye_closed_since is None:
            if (
                close_condition
                and self._closing_trend(avg_aperture, avg_ratio)
                and now_ts >= self.cooldown_until
            ):
                self._begin_closure(
                    now_ts,
                    avg_aperture,
                    eye_diff,
                    avg_ratio,
                    aperture_threshold,
                )

            self._store_previous_metrics(avg_aperture, avg_ratio)
            return

        if open_condition and self._opening_trend(avg_aperture, avg_ratio):
            self.phase = BLINK_PHASE_OPENING
            self._finalize_closure(
                now_dt,
                now_ts,
                avg_aperture,
                aperture_threshold,
                ear_consec_frames,
                blink_logger,
                db_conn,
            )
            self._store_previous_metrics(avg_aperture, avg_ratio)
            return

        if close_condition:
            self._accumulate_closure(
                avg_aperture,
                eye_diff,
                avg_ratio,
                aperture_threshold,
            )
            self._store_previous_metrics(avg_aperture, avg_ratio)
            return

        if self._opening_trend(avg_aperture, avg_ratio) and self.phase != BLINK_PHASE_OPENING:
            self.phase = BLINK_PHASE_OPENING

        if (now_ts - self.eye_closed_since) > BLINK_MAX_CLOSED_SECONDS:
            self._reset_closure()

        self._store_previous_metrics(avg_aperture, avg_ratio)
