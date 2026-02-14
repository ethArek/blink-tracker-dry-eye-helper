import unittest
from datetime import datetime

from blink_app.services.db import (
    count_blinks_in_range,
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


if __name__ == "__main__":
    unittest.main()
