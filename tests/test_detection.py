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

    def test_blink_state_update_records_blink_when_threshold_is_met(self) -> None:
        state = BlinkState()
        db_conn = init_db(":memory:")
        now_dt = datetime(2024, 1, 1, 12, 0, 0)
        try:
            state.update(0.1, now_dt, 10.0, 0.2, 2, self.logger, db_conn)
            state.update(0.1, now_dt, 11.0, 0.2, 2, self.logger, db_conn)
            state.update(0.3, now_dt, 12.0, 0.2, 2, self.logger, db_conn)

            self.assertEqual(state.frame_counter, 0)
            self.assertEqual(state.blink_counter, 1)
            self.assertEqual(state.last_blink_time, 12.0)

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
            state.update(0.3, now_dt, 10.05, 0.2, 3, self.logger, db_conn)

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


if __name__ == "__main__":
    unittest.main()
