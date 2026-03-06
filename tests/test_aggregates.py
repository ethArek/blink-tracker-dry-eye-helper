import argparse
import logging
import os
import unittest
from datetime import datetime
from unittest.mock import call, patch

from blink_app.domain.aggregates import AggregateState, update_aggregates
from blink_app.domain.detection import BlinkState
from blink_app.services.db import init_db, record_blink_event


class UpdateAggregatesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.logger = logging.getLogger("test.aggregates")
        self.logger.addHandler(logging.NullHandler())

    def test_update_aggregates_records_counts_and_csv(self) -> None:
        now_dt = datetime(2024, 1, 2, 12, 34, 56)
        now_ts = 1704198896.0
        state = AggregateState(last_stats_time=now_ts - 2.0)
        blink_state = BlinkState(last_blink_time=now_ts - 10.0)
        args = argparse.Namespace(csv_output=True, enable_alerts=False)

        db_conn = init_db(":memory:")

        record_blink_event(db_conn, datetime(2024, 1, 2, 12, 33, 5))
        record_blink_event(db_conn, datetime(2024, 1, 2, 12, 33, 42))

        record_blink_event(db_conn, datetime(2024, 1, 2, 12, 20, 1))
        record_blink_event(db_conn, datetime(2024, 1, 2, 12, 29, 59))

        record_blink_event(db_conn, datetime(2024, 1, 2, 11, 0, 5))
        record_blink_event(db_conn, datetime(2024, 1, 2, 11, 30, 0))
        record_blink_event(db_conn, datetime(2024, 1, 2, 11, 59, 59))

        record_blink_event(db_conn, datetime(2024, 1, 1, 0, 0, 1))
        record_blink_event(db_conn, datetime(2024, 1, 1, 23, 59, 59))

        record_blink_event(db_conn, datetime(2024, 1, 2, 0, 0, 0))
        record_blink_event(db_conn, datetime(2024, 1, 2, 10, 0, 0))

        output_dir = os.path.join("C:\\", "virtual-output")
        with patch("blink_app.domain.aggregates.write_csv_row") as write_csv_row_mock:
            update_aggregates(
                args=args,
                state=state,
                now_dt=now_dt,
                now_ts=now_ts,
                blink_state=blink_state,
                db_conn=db_conn,
                aggregate_logger=self.logger,
                output_dir=output_dir,
            )

        self.assertEqual(state.blinks_1m, 2)
        self.assertEqual(state.blinks_10m, 2)
        self.assertEqual(state.blinks_1h, 3)
        self.assertEqual(state.blinks_day, 9)

        self.assertEqual(
            write_csv_row_mock.call_args_list,
            [
                call(
                    os.path.join(output_dir, "blinks_per_minute.csv"),
                    ["date", "interval_start", "blinks"],
                    ["2024-01-02", "12:33:00", 2],
                ),
                call(
                    os.path.join(output_dir, "blinks_per_10_minutes.csv"),
                    ["date", "interval_start", "blinks"],
                    ["2024-01-02", "12:20:00", 2],
                ),
                call(
                    os.path.join(output_dir, "blinks_per_hour.csv"),
                    ["date", "interval_start", "blinks"],
                    ["2024-01-02", "11:00:00", 3],
                ),
                call(
                    os.path.join(output_dir, "blinks_per_day.csv"),
                    ["date", "blinks"],
                    ["2024-01-02", 9],
                ),
            ],
        )

        rows = db_conn.execute(
            "SELECT interval_type, interval_start, blink_count FROM blink_aggregates ORDER BY interval_type, interval_start"
        ).fetchall()
        self.assertEqual(
            rows,
            [
                ("day", "2024-01-01 00:00:00", 2),
                ("hour", "2024-01-02 11:00:00", 3),
                ("minute", "2024-01-02 12:33:00", 2),
                ("ten_minute", "2024-01-02 12:20:00", 2),
            ],
        )

    def test_update_aggregates_returns_early_when_called_too_soon(self) -> None:
        now_dt = datetime(2024, 1, 2, 12, 34, 56)
        now_ts = 1704198896.0
        state = AggregateState(last_stats_time=now_ts - 0.2)
        blink_state = BlinkState(last_blink_time=now_ts - 10.0)
        args = argparse.Namespace(csv_output=False, enable_alerts=False)

        db_conn = init_db(":memory:")
        with patch("blink_app.domain.aggregates.write_csv_row") as write_csv_row_mock:
            update_aggregates(
                args=args,
                state=state,
                now_dt=now_dt,
                now_ts=now_ts,
                blink_state=blink_state,
                db_conn=db_conn,
                aggregate_logger=self.logger,
                output_dir="ignored",
            )

        self.assertIsNone(state.last_logged_minute)
        self.assertEqual(state.last_stats_time, now_ts - 0.2)
        write_csv_row_mock.assert_not_called()

    def test_update_aggregates_plays_alert_when_enabled(self) -> None:
        now_dt = datetime(2024, 1, 2, 12, 34, 56)
        now_ts = 1704198896.0
        state = AggregateState(
            last_stats_time=now_ts - 2.0,
            last_alert_time=now_ts - 60.0,
        )
        blink_state = BlinkState(last_blink_time=now_ts - 20.0)
        args = argparse.Namespace(
            csv_output=False,
            enable_alerts=True,
            alert_after_seconds=5.0,
            alert_repeat_seconds=5.0,
            alert_sound="beep",
            alert_sound_file=None,
        )

        db_conn = init_db(":memory:")
        with patch("blink_app.domain.aggregates.play_alert_sound") as alert_mock:
            update_aggregates(
                args=args,
                state=state,
                now_dt=now_dt,
                now_ts=now_ts,
                blink_state=blink_state,
                db_conn=db_conn,
                aggregate_logger=self.logger,
                output_dir="ignored",
            )

        alert_mock.assert_called_once_with(sound="beep", sound_file=None)
        self.assertEqual(state.last_alert_time, now_ts)

    def test_update_aggregates_clamps_alert_repeat_to_one_second(self) -> None:
        now_dt = datetime(2024, 1, 2, 12, 34, 56)
        now_ts = 1704198896.0
        state = AggregateState(
            last_stats_time=now_ts - 2.0,
            last_alert_time=now_ts - 0.5,
        )
        blink_state = BlinkState(last_blink_time=now_ts - 20.0)
        args = argparse.Namespace(
            csv_output=False,
            enable_alerts=True,
            alert_after_seconds=5.0,
            alert_repeat_seconds=0.05,
            alert_sound="beep",
            alert_sound_file=None,
        )

        db_conn = init_db(":memory:")
        with patch("blink_app.domain.aggregates.play_alert_sound") as alert_mock:
            update_aggregates(
                args=args,
                state=state,
                now_dt=now_dt,
                now_ts=now_ts,
                blink_state=blink_state,
                db_conn=db_conn,
                aggregate_logger=self.logger,
                output_dir="ignored",
            )

        alert_mock.assert_not_called()
        self.assertEqual(state.last_alert_time, now_ts - 0.5)


if __name__ == "__main__":
    unittest.main()
