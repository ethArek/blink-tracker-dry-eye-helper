import unittest
from datetime import datetime

from blink_app.services.db import (
    count_blinks_in_range,
    fetch_recent_aggregates,
    init_db,
    record_aggregate,
    record_blink_event,
)


class DatabaseAggregatesTest(unittest.TestCase):
    def test_record_aggregate_updates_existing_rows(self) -> None:
        db_conn = init_db(":memory:")
        start = datetime(2024, 1, 1, 10, 0, 0)
        end = datetime(2024, 1, 1, 10, 59, 59)

        record_aggregate(db_conn, "hour", start, end, 4)
        record_aggregate(db_conn, "hour", start, end, 7)

        cursor = db_conn.execute(
            "SELECT blink_count FROM blink_aggregates WHERE interval_type = ? AND interval_start = ?",
            ("hour", start.strftime("%Y-%m-%d %H:%M:%S")),
        )
        row = cursor.fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], 7)

    def test_count_blinks_in_range_is_inclusive(self) -> None:
        db_conn = init_db(":memory:")
        start = datetime(2024, 1, 1, 10, 0, 0)
        end = datetime(2024, 1, 1, 10, 0, 59)

        record_blink_event(db_conn, start)
        record_blink_event(db_conn, datetime(2024, 1, 1, 10, 0, 30))
        record_blink_event(db_conn, end)
        record_blink_event(db_conn, datetime(2024, 1, 1, 10, 1, 0))

        count = count_blinks_in_range(db_conn, start, end)
        self.assertEqual(count, 3)

    def test_fetch_recent_aggregates_applies_limit_and_order(self) -> None:
        db_conn = init_db(":memory:")
        base_start = datetime(2024, 1, 1, 10, 0, 0)
        for offset in range(5):
            start = base_start.replace(minute=offset)
            end = start.replace(second=59)
            record_aggregate(db_conn, "minute", start, end, offset)

        rows = fetch_recent_aggregates(db_conn, "minute", limit=3)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0][0], "2024-01-01 10:04:00")
        self.assertEqual(rows[0][1], 4)
        self.assertEqual(rows[1][0], "2024-01-01 10:03:00")
        self.assertEqual(rows[2][0], "2024-01-01 10:02:00")


if __name__ == "__main__":
    unittest.main()
