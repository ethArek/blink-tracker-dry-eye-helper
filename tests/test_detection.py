import logging
import unittest
from datetime import datetime

from blink_app.domain.detection import BlinkState, eye_aspect_ratio
from blink_app.services.db import count_blinks_in_range, init_db


class DetectionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.logger = logging.getLogger("test.detection")
        self.logger.addHandler(logging.NullHandler())

    def test_eye_aspect_ratio_computes_expected_value(self) -> None:
        landmarks = [
            (0.0, 0.0),
            (1.0, 1.0),
            (3.0, 1.0),
            (4.0, 0.0),
            (3.0, -1.0),
            (1.0, -1.0),
        ]
        ear = eye_aspect_ratio(landmarks, [0, 1, 2, 3, 4, 5])
        self.assertAlmostEqual(ear, 0.5)

    def test_eye_aspect_ratio_handles_degenerate_horizontal_distance(self) -> None:
        landmarks = [
            (1.0, 1.0),
            (1.0, 2.0),
            (2.0, 2.0),
            (1.0, 1.0),
            (2.0, 0.0),
            (1.0, 0.0),
        ]
        ear = eye_aspect_ratio(landmarks, [0, 1, 2, 3, 4, 5])
        self.assertEqual(ear, 1.0)

    def test_eye_aspect_ratio_handles_non_finite_landmarks(self) -> None:
        landmarks = [
            (0.0, 0.0),
            (1.0, 1.0),
            (float("nan"), 1.0),
            (4.0, 0.0),
            (3.0, -1.0),
            (1.0, -1.0),
        ]
        ear = eye_aspect_ratio(landmarks, [0, 1, 2, 3, 4, 5])
        self.assertEqual(ear, 1.0)

    def test_blink_state_update_records_blink_when_threshold_is_met(self) -> None:
        state = BlinkState()
        db_conn = init_db(":memory:")
        now_dt = datetime(2024, 1, 1, 12, 0, 0)
        try:
            state.update(0.1, now_dt, 10.0, 0.2, 2, self.logger, db_conn)
            state.update(0.1, now_dt, 10.07, 0.2, 2, self.logger, db_conn)
            state.update(0.3, now_dt, 10.14, 0.2, 2, self.logger, db_conn)

            self.assertEqual(state.frame_counter, 0)
            self.assertEqual(state.blink_counter, 1)
            self.assertEqual(state.last_blink_time, 10.14)

            count = count_blinks_in_range(db_conn, now_dt, now_dt)
            self.assertEqual(count, 1)
        finally:
            db_conn.close()

    def test_blink_state_update_does_not_record_blink_before_threshold(self) -> None:
        state = BlinkState()
        db_conn = init_db(":memory:")
        now_dt = datetime(2024, 1, 1, 12, 0, 0)
        try:
            state.update(0.1, now_dt, 10.0, 0.2, 3, self.logger, db_conn)
            state.update(0.3, now_dt, 10.04, 0.2, 3, self.logger, db_conn)

            self.assertEqual(state.frame_counter, 0)
            self.assertEqual(state.blink_counter, 0)
            self.assertEqual(state.last_blink_time, 0.0)

            count = count_blinks_in_range(db_conn, now_dt, now_dt)
            self.assertEqual(count, 0)
        finally:
            db_conn.close()

    def test_blink_state_update_records_blink_with_duration_fallback(self) -> None:
        state = BlinkState()
        db_conn = init_db(":memory:")
        now_dt = datetime(2024, 1, 1, 12, 0, 0)
        try:
            state.update(0.16, now_dt, 10.0, 0.2, 3, self.logger, db_conn)
            state.update(0.3, now_dt, 10.15, 0.2, 3, self.logger, db_conn)

            self.assertEqual(state.frame_counter, 0)
            self.assertEqual(state.blink_counter, 1)
            self.assertEqual(state.last_blink_time, 10.15)

            count = count_blinks_in_range(db_conn, now_dt, now_dt)
            self.assertEqual(count, 1)
        finally:
            db_conn.close()

    def test_blink_state_update_ignores_short_borderline_closure(self) -> None:
        state = BlinkState()
        db_conn = init_db(":memory:")
        now_dt = datetime(2024, 1, 1, 12, 0, 0)
        try:
            state.update(0.199, now_dt, 10.0, 0.2, 3, self.logger, db_conn)
            state.update(0.3, now_dt, 10.05, 0.2, 3, self.logger, db_conn)

            self.assertEqual(state.frame_counter, 0)
            self.assertEqual(state.blink_counter, 0)
            self.assertEqual(state.last_blink_time, 0.0)

            count = count_blinks_in_range(db_conn, now_dt, now_dt)
            self.assertEqual(count, 0)
        finally:
            db_conn.close()

    def test_blink_state_update_counts_relative_drop_blink(self) -> None:
        state = BlinkState()
        db_conn = init_db(":memory:")
        now_dt = datetime(2024, 1, 1, 12, 0, 0)
        try:
            state.update(0.29, now_dt, 10.00, 0.2, 3, self.logger, db_conn)
            state.update(0.295, now_dt, 10.03, 0.2, 3, self.logger, db_conn)
            state.update(0.24, now_dt, 10.10, 0.2, 3, self.logger, db_conn)
            state.update(0.24, now_dt, 10.17, 0.2, 3, self.logger, db_conn)
            state.update(0.29, now_dt, 10.24, 0.2, 3, self.logger, db_conn)

            self.assertEqual(state.frame_counter, 0)
            self.assertEqual(state.blink_counter, 1)
            self.assertEqual(state.last_blink_time, 10.24)

            count = count_blinks_in_range(db_conn, now_dt, now_dt)
            self.assertEqual(count, 1)
        finally:
            db_conn.close()

    def test_blink_state_update_ignores_asymmetric_eye_change(self) -> None:
        state = BlinkState()
        db_conn = init_db(":memory:")
        now_dt = datetime(2024, 1, 1, 12, 0, 0)
        try:
            state.update(0.29, now_dt, 10.00, 0.2, 3, self.logger, db_conn, 0.29, 0.29)
            state.update(0.21, now_dt, 10.06, 0.2, 3, self.logger, db_conn, 0.15, 0.27)
            state.update(0.22, now_dt, 10.12, 0.2, 3, self.logger, db_conn, 0.16, 0.28)
            state.update(0.29, now_dt, 10.18, 0.2, 3, self.logger, db_conn, 0.29, 0.29)

            self.assertEqual(state.blink_counter, 0)
            self.assertEqual(state.last_blink_time, 0.0)

            count = count_blinks_in_range(db_conn, now_dt, now_dt)
            self.assertEqual(count, 0)
        finally:
            db_conn.close()

    def test_blink_state_update_ignores_small_jitter_without_blink(self) -> None:
        state = BlinkState()
        db_conn = init_db(":memory:")
        now_dt = datetime(2024, 1, 1, 12, 0, 0)
        try:
            samples = [0.29, 0.288, 0.294, 0.287, 0.292, 0.286, 0.291, 0.289, 0.293]
            for idx, ear in enumerate(samples):
                state.update(ear, now_dt, 10.0 + (idx * 0.03), 0.2, 3, self.logger, db_conn)

            self.assertEqual(state.blink_counter, 0)
            self.assertEqual(state.last_blink_time, 0.0)

            count = count_blinks_in_range(db_conn, now_dt, now_dt)
            self.assertEqual(count, 0)
        finally:
            db_conn.close()

    def test_blink_state_update_ignores_non_finite_samples_without_poisoning_baseline(self) -> None:
        state = BlinkState()
        db_conn = init_db(":memory:")
        now_dt = datetime(2024, 1, 1, 12, 0, 0)
        try:
            state.update(0.29, now_dt, 10.00, 0.2, 3, self.logger, db_conn)
            state.update(float("nan"), now_dt, 10.03, 0.2, 3, self.logger, db_conn)
            state.update(0.24, now_dt, 10.10, 0.2, 3, self.logger, db_conn)
            state.update(0.24, now_dt, 10.17, 0.2, 3, self.logger, db_conn)
            state.update(0.29, now_dt, 10.24, 0.2, 3, self.logger, db_conn)

            self.assertEqual(state.blink_counter, 1)
            self.assertEqual(state.last_blink_time, 10.24)

            count = count_blinks_in_range(db_conn, now_dt, now_dt)
            self.assertEqual(count, 1)
        finally:
            db_conn.close()

    def test_blink_state_update_keeps_baseline_stable_during_asymmetric_noise(self) -> None:
        state = BlinkState()
        db_conn = init_db(":memory:")
        now_dt = datetime(2024, 1, 1, 12, 0, 0)
        try:
            state.update(0.30, now_dt, 10.00, 0.2, 3, self.logger, db_conn, 0.30, 0.30)
            state.update(0.30, now_dt, 10.03, 0.2, 3, self.logger, db_conn, 0.30, 0.30)
            for idx in range(20):
                state.update(
                    0.22,
                    now_dt,
                    10.06 + (idx * 0.03),
                    0.2,
                    3,
                    self.logger,
                    db_conn,
                    0.18,
                    0.26,
                )
            state.update(0.245, now_dt, 10.70, 0.2, 3, self.logger, db_conn, 0.245, 0.245)
            state.update(0.245, now_dt, 10.77, 0.2, 3, self.logger, db_conn, 0.245, 0.245)
            state.update(0.30, now_dt, 10.84, 0.2, 3, self.logger, db_conn, 0.30, 0.30)

            self.assertEqual(state.blink_counter, 1)
            self.assertEqual(state.last_blink_time, 10.84)

            count = count_blinks_in_range(db_conn, now_dt, now_dt)
            self.assertEqual(count, 1)
        finally:
            db_conn.close()

    def test_blink_state_update_recovers_when_startup_sample_is_closed(self) -> None:
        state = BlinkState()
        db_conn = init_db(":memory:")
        now_dt = datetime(2024, 1, 1, 12, 0, 0)
        try:
            state.update(0.10, now_dt, 10.00, 0.2, 3, self.logger, db_conn, 0.10, 0.10)
            state.update(0.30, now_dt, 10.03, 0.2, 3, self.logger, db_conn, 0.30, 0.30)
            state.update(0.30, now_dt, 10.06, 0.2, 3, self.logger, db_conn, 0.30, 0.30)
            state.update(0.30, now_dt, 10.09, 0.2, 3, self.logger, db_conn, 0.30, 0.30)
            state.update(0.24, now_dt, 10.15, 0.2, 3, self.logger, db_conn, 0.24, 0.24)
            state.update(0.24, now_dt, 10.22, 0.2, 3, self.logger, db_conn, 0.24, 0.24)
            state.update(0.30, now_dt, 10.29, 0.2, 3, self.logger, db_conn, 0.30, 0.30)

            self.assertEqual(state.blink_counter, 1)
            self.assertEqual(state.last_blink_time, 10.29)

            count = count_blinks_in_range(db_conn, now_dt, now_dt)
            self.assertEqual(count, 1)
        finally:
            db_conn.close()


if __name__ == "__main__":
    unittest.main()

