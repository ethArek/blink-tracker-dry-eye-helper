import logging
import unittest
from datetime import datetime

from blink_app.domain.detection import BlinkState, eye_aperture_ratio
from blink_app.services.db import count_blinks_in_range, init_db

TEST_EYE_CORNERS = (0, 1)
TEST_EYE_GAP_PAIRS = (
    (2, 7),
    (3, 8),
    (4, 9),
    (5, 10),
    (6, 11),
)


class DetectionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.logger = logging.getLogger("test.detection")
        self.logger.addHandler(logging.NullHandler())
        self.now_dt = datetime(2024, 1, 1, 12, 0, 0)

    def _update(
        self,
        state: BlinkState,
        db_conn,
        now_ts: float,
        left_ear: float,
        right_ear: float | None = None,
        ear_threshold: float = 0.2,
        ear_consec_frames: int = 3,
    ) -> None:
        right_eye_ear = left_ear if right_ear is None else right_ear
        ear = (left_ear + right_eye_ear) / 2.0
        state.update(
            ear,
            self.now_dt,
            now_ts,
            ear_threshold,
            ear_consec_frames,
            self.logger,
            db_conn,
            left_aperture=left_ear,
            right_aperture=right_eye_ear,
        )

    def _seed_open(self, state: BlinkState, db_conn, start_ts: float, ear: float = 0.3) -> None:
        for index in range(4):
            self._update(state, db_conn, start_ts + (index * 0.03), ear, ear)

    def _blink_count(self, db_conn) -> int:
        return count_blinks_in_range(db_conn, self.now_dt, self.now_dt)

    def test_eye_aperture_ratio_computes_expected_value(self) -> None:
        landmarks = [
            (0.0, 0.0),
            (4.0, 0.0),
            (0.8, 1.0),
            (1.5, 1.0),
            (2.0, 1.0),
            (2.5, 1.0),
            (3.2, 1.0),
            (0.8, -1.0),
            (1.5, -1.0),
            (2.0, -1.0),
            (2.5, -1.0),
            (3.2, -1.0),
        ]
        aperture = eye_aperture_ratio(landmarks, TEST_EYE_CORNERS, TEST_EYE_GAP_PAIRS)
        self.assertAlmostEqual(aperture, 0.5)

    def test_eye_aperture_ratio_uses_median_gap_to_ignore_one_bad_pair(self) -> None:
        landmarks = [
            (0.0, 0.0),
            (4.0, 0.0),
            (0.8, 1.0),
            (1.5, 1.0),
            (2.0, 1.0),
            (2.5, 6.0),
            (3.2, 1.0),
            (0.8, -1.0),
            (1.5, -1.0),
            (2.0, -1.0),
            (2.5, -6.0),
            (3.2, -1.0),
        ]
        aperture = eye_aperture_ratio(landmarks, TEST_EYE_CORNERS, TEST_EYE_GAP_PAIRS)
        self.assertAlmostEqual(aperture, 0.5)

    def test_eye_aperture_ratio_handles_degenerate_horizontal_distance(self) -> None:
        landmarks = [
            (1.0, 1.0),
            (1.0, -1.0),
            (1.0, 2.0),
            (1.0, 2.0),
            (1.0, 2.0),
            (1.0, 2.0),
            (1.0, 2.0),
            (1.0, 0.0),
            (1.0, 0.0),
            (1.0, 0.0),
            (1.0, 0.0),
            (1.0, 0.0),
        ]
        aperture = eye_aperture_ratio(landmarks, TEST_EYE_CORNERS, TEST_EYE_GAP_PAIRS)
        self.assertEqual(aperture, 1.0)

    def test_eye_aperture_ratio_handles_non_finite_landmarks(self) -> None:
        landmarks = [
            (0.0, 0.0),
            (4.0, 0.0),
            (0.8, 1.0),
            (1.5, 1.0),
            (float("nan"), 1.0),
            (2.5, 1.0),
            (3.2, 1.0),
            (0.8, -1.0),
            (1.5, -1.0),
            (2.0, -1.0),
            (2.5, -1.0),
            (3.2, -1.0),
        ]
        aperture = eye_aperture_ratio(landmarks, TEST_EYE_CORNERS, TEST_EYE_GAP_PAIRS)
        self.assertAlmostEqual(aperture, 0.5)

    def test_blink_state_records_symmetric_blink(self) -> None:
        state = BlinkState()
        db_conn = init_db(":memory:")
        try:
            self._seed_open(state, db_conn, 10.00)
            for now_ts in (10.12, 10.15, 10.18):
                self._update(state, db_conn, now_ts, 0.18, 0.18)
            for now_ts in (10.21, 10.24, 10.27):
                self._update(state, db_conn, now_ts, 0.31, 0.31)

            self.assertEqual(state.blink_counter, 1)
            self.assertGreater(state.last_blink_time, 10.18)
            self.assertEqual(self._blink_count(db_conn), 1)
        finally:
            db_conn.close()

    def test_blink_state_counts_relative_blink_above_absolute_threshold(self) -> None:
        state = BlinkState()
        db_conn = init_db(":memory:")
        try:
            self._seed_open(state, db_conn, 10.00, ear=0.31)
            for now_ts in (10.12, 10.15, 10.18):
                self._update(state, db_conn, now_ts, 0.24, 0.24)
            for now_ts in (10.21, 10.24, 10.27):
                self._update(state, db_conn, now_ts, 0.31, 0.31)

            self.assertEqual(state.blink_counter, 1)
            self.assertEqual(self._blink_count(db_conn), 1)
        finally:
            db_conn.close()

    def test_blink_state_counts_blink_from_lower_downward_gaze_open_level(self) -> None:
        state = BlinkState()
        db_conn = init_db(":memory:")
        try:
            self._seed_open(state, db_conn, 10.00, ear=0.30)

            for now_ts in (10.12, 10.15, 10.18, 10.21):
                self._update(state, db_conn, now_ts, 0.24, 0.24, ear_threshold=0.21)

            self.assertIsNone(state.eye_closed_since)

            for now_ts in (10.24, 10.27, 10.30):
                self._update(state, db_conn, now_ts, 0.14, 0.14, ear_threshold=0.21)
            for now_ts in (10.33, 10.36, 10.39, 10.42):
                self._update(state, db_conn, now_ts, 0.24, 0.24, ear_threshold=0.21)

            self.assertEqual(state.blink_counter, 1)
            self.assertEqual(self._blink_count(db_conn), 1)
        finally:
            db_conn.close()

    def test_blink_state_ignores_small_jitter_without_blink(self) -> None:
        state = BlinkState()
        db_conn = init_db(":memory:")
        try:
            self._seed_open(state, db_conn, 10.00)
            for index, ear in enumerate((0.298, 0.294, 0.301, 0.296, 0.302, 0.297, 0.300, 0.295)):
                self._update(state, db_conn, 10.20 + (index * 0.03), ear, ear)

            self.assertEqual(state.blink_counter, 0)
            self.assertEqual(self._blink_count(db_conn), 0)
        finally:
            db_conn.close()

    def test_blink_state_ignores_asymmetric_wink_like_signal(self) -> None:
        state = BlinkState()
        db_conn = init_db(":memory:")
        try:
            self._seed_open(state, db_conn, 10.00)
            for now_ts in (10.12, 10.15, 10.18):
                self._update(state, db_conn, now_ts, 0.16, 0.30)
            for now_ts in (10.21, 10.24, 10.27):
                self._update(state, db_conn, now_ts, 0.30, 0.30)

            self.assertEqual(state.blink_counter, 0)
            self.assertEqual(self._blink_count(db_conn), 0)
        finally:
            db_conn.close()

    def test_blink_state_ignores_non_finite_sample_and_recovers(self) -> None:
        state = BlinkState()
        db_conn = init_db(":memory:")
        try:
            self._seed_open(state, db_conn, 10.00)
            state.update(
                float("nan"),
                self.now_dt,
                10.12,
                0.2,
                3,
                self.logger,
                db_conn,
                left_aperture=float("nan"),
                right_aperture=0.30,
            )
            for now_ts in (10.18, 10.21, 10.24):
                self._update(state, db_conn, now_ts, 0.19, 0.19)
            for now_ts in (10.27, 10.30, 10.33):
                self._update(state, db_conn, now_ts, 0.31, 0.31)

            self.assertEqual(state.blink_counter, 1)
            self.assertEqual(self._blink_count(db_conn), 1)
        finally:
            db_conn.close()

    def test_blink_state_ignores_startup_closed_frames_until_baseline_exists(self) -> None:
        state = BlinkState()
        db_conn = init_db(":memory:")
        try:
            for now_ts in (10.00, 10.03, 10.06):
                self._update(state, db_conn, now_ts, 0.10, 0.10)
            self.assertIsNone(state.open_reference_ear)
            self.assertEqual(state.blink_counter, 0)

            self._seed_open(state, db_conn, 10.12)
            for now_ts in (10.30, 10.33, 10.36):
                self._update(state, db_conn, now_ts, 0.18, 0.18)
            for now_ts in (10.39, 10.42, 10.45):
                self._update(state, db_conn, now_ts, 0.31, 0.31)

            self.assertEqual(state.blink_counter, 1)
            self.assertEqual(self._blink_count(db_conn), 1)
        finally:
            db_conn.close()

    def test_blink_state_resets_partial_closure_when_face_is_missing(self) -> None:
        state = BlinkState()
        db_conn = init_db(":memory:")
        try:
            self._seed_open(state, db_conn, 10.00)
            self._update(state, db_conn, 10.12, 0.18, 0.18)
            self._update(state, db_conn, 10.15, 0.18, 0.18)
            state.observe_missing_face(10.40)
            for now_ts in (10.43, 10.46, 10.49):
                self._update(state, db_conn, now_ts, 0.31, 0.31)

            self.assertEqual(state.blink_counter, 0)
            self.assertEqual(self._blink_count(db_conn), 0)

            for now_ts in (10.60, 10.63, 10.66):
                self._update(state, db_conn, now_ts, 0.18, 0.18)
            for now_ts in (10.69, 10.72, 10.75):
                self._update(state, db_conn, now_ts, 0.31, 0.31)

            self.assertEqual(state.blink_counter, 1)
            self.assertEqual(self._blink_count(db_conn), 1)
        finally:
            db_conn.close()

    def test_blink_state_resets_baseline_after_long_face_loss(self) -> None:
        state = BlinkState()
        db_conn = init_db(":memory:")
        try:
            self._seed_open(state, db_conn, 10.00)
            self.assertIsNotNone(state.open_reference_ear)

            state.observe_missing_face(12.50)
            self.assertIsNone(state.open_reference_ear)

            self._seed_open(state, db_conn, 12.53, ear=0.28)
            self.assertIsNotNone(state.open_reference_ear)
            for now_ts in (12.65, 12.68, 12.71):
                self._update(state, db_conn, now_ts, 0.20, 0.20)
            for now_ts in (12.74, 12.77, 12.80):
                self._update(state, db_conn, now_ts, 0.29, 0.29)

            self.assertEqual(state.blink_counter, 1)
            self.assertEqual(self._blink_count(db_conn), 1)
        finally:
            db_conn.close()

    def test_blink_state_ignores_long_closure(self) -> None:
        state = BlinkState()
        db_conn = init_db(":memory:")
        try:
            self._seed_open(state, db_conn, 10.00)
            for index in range(14):
                self._update(state, db_conn, 10.12 + (index * 0.04), 0.17, 0.17)
            for now_ts in (10.72, 10.75, 10.78):
                self._update(state, db_conn, now_ts, 0.31, 0.31)

            self.assertEqual(state.blink_counter, 0)
            self.assertEqual(self._blink_count(db_conn), 0)
        finally:
            db_conn.close()


if __name__ == "__main__":
    unittest.main()

