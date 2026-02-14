import argparse
import csv
import logging
import tempfile
import unittest
from datetime import datetime
from unittest.mock import patch

from blink_app.domain.aggregates import AggregateState, update_aggregates
from blink_app.services.db import init_db, record_blink_event
from blink_app.domain.detection import BlinkState


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

        # Minute range: 12:33:00 - 12:33:59
        record_blink_event(db_conn, datetime(2024, 1, 2, 12, 33, 5))
        record_blink_event(db_conn, datetime(2024, 1, 2, 12, 33, 42))

        # Ten minute range: 12:20:00 - 12:29:59
        record_blink_event(db_conn, datetime(2024, 1, 2, 12, 20, 1))
        record_blink_event(db_conn, datetime(2024, 1, 2, 12, 29, 59))

        # Hour range: 11:00:00 - 11:59:59
        record_blink_event(db_conn, datetime(2024, 1, 2, 11, 0, 5))
        record_blink_event(db_conn, datetime(2024, 1, 2, 11, 30, 0))
        record_blink_event(db_conn, datetime(2024, 1, 2, 11, 59, 59))

        # Previous day range: 2024-01-01
        record_blink_event(db_conn, datetime(2024, 1, 1, 0, 0, 1))
        record_blink_event(db_conn, datetime(2024, 1, 1, 23, 59, 59))

        # Current day totals
        record_blink_event(db_conn, datetime(2024, 1, 2, 0, 0, 0))
        record_blink_event(db_conn, datetime(2024, 1, 2, 10, 0, 0))

        with tempfile.TemporaryDirectory() as tmp_dir:
            update_aggregates(
                args=args,
                state=state,
                now_dt=now_dt,
                now_ts=now_ts,
                blink_state=blink_state,
                db_conn=db_conn,
                aggregate_logger=self.logger,
                output_dir=tmp_dir,
            )

            self.assertEqual(state.blinks_1m, 2)
            self.assertEqual(state.blinks_10m, 2)
            self.assertEqual(state.blinks_1h, 3)
            self.assertEqual(state.blinks_day, 9)

            with open(f"{tmp_dir}/blinks_per_minute.csv", newline="") as handle:
                rows = list(csv.reader(handle))
            self.assertEqual(rows[0], ["date", "interval_start", "blinks"])
            self.assertEqual(rows[1], ["2024-01-02", "12:33:00", "2"])

            with open(f"{tmp_dir}/blinks_per_10_minutes.csv", newline="") as handle:
                rows = list(csv.reader(handle))
            self.assertEqual(rows[1], ["2024-01-02", "12:20:00", "2"])

            with open(f"{tmp_dir}/blinks_per_hour.csv", newline="") as handle:
                rows = list(csv.reader(handle))
            self.assertEqual(rows[1], ["2024-01-02", "11:00:00", "3"])

            with open(f"{tmp_dir}/blinks_per_day.csv", newline="") as handle:
                rows = list(csv.reader(handle))
            self.assertEqual(rows[1], ["2024-01-02", "9"])

    def test_update_aggregates_returns_early_when_called_too_soon(self) -> None:
        now_dt = datetime(2024, 1, 2, 12, 34, 56)
        now_ts = 1704198896.0
        state = AggregateState(last_stats_time=now_ts - 0.2)
        blink_state = BlinkState(last_blink_time=now_ts - 10.0)
        args = argparse.Namespace(csv_output=False, enable_alerts=False)

        db_conn = init_db(":memory:")
        with tempfile.TemporaryDirectory() as tmp_dir:
            update_aggregates(
                args=args,
                state=state,
                now_dt=now_dt,
                now_ts=now_ts,
                blink_state=blink_state,
                db_conn=db_conn,
                aggregate_logger=self.logger,
                output_dir=tmp_dir,
            )
        self.assertIsNone(state.last_logged_minute)
        self.assertEqual(state.last_stats_time, now_ts - 0.2)

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
        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch("blink_app.domain.aggregates.play_alert_sound") as alert_mock:
                update_aggregates(
                    args=args,
                    state=state,
                    now_dt=now_dt,
                    now_ts=now_ts,
                    blink_state=blink_state,
                    db_conn=db_conn,
                    aggregate_logger=self.logger,
                    output_dir=tmp_dir,
                )
                alert_mock.assert_called_once_with(sound="beep", sound_file=None)

        self.assertEqual(state.last_alert_time, now_ts)


if __name__ == "__main__":
    unittest.main()
