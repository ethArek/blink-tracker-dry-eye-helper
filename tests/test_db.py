import unittest
from datetime import datetime

from blink_app.services.db import init_db, record_aggregate


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


if __name__ == "__main__":
    unittest.main()
