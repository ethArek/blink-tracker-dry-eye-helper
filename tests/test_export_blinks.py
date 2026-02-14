import csv
import json
import os
import tempfile
import unittest
from datetime import datetime

import export_blinks
from blink_app.services.db import init_db, record_aggregate, record_blink_event


class ExportBlinksTest(unittest.TestCase):
    def test_main_fails_when_database_file_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            missing_db_path = os.path.join(tmp_dir, "missing.db")
            with self.assertRaises(FileNotFoundError):
                export_blinks.main(
                    [
                        "--db-path",
                        missing_db_path,
                        "--output-dir",
                        tmp_dir,
                    ]
                )

    def test_main_exports_csv_and_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = os.path.join(tmp_dir, "blinks.db")
            db_conn = init_db(db_path)
            try:
                event_time = datetime(2024, 1, 1, 12, 0, 0)
                record_blink_event(db_conn, event_time)
                record_aggregate(
                    db_conn,
                    "minute",
                    datetime(2024, 1, 1, 11, 59, 0),
                    datetime(2024, 1, 1, 11, 59, 59),
                    1,
                )
            finally:
                db_conn.close()

            exit_code = export_blinks.main(
                [
                    "--db-path",
                    db_path,
                    "--output-dir",
                    tmp_dir,
                    "--format",
                    "csv",
                    "--table",
                    "both",
                ]
            )
            self.assertEqual(exit_code, 0)

            events_csv_path = os.path.join(tmp_dir, "blink_events.csv")
            aggregates_csv_path = os.path.join(tmp_dir, "blink_aggregates.csv")
            self.assertTrue(os.path.exists(events_csv_path))
            self.assertTrue(os.path.exists(aggregates_csv_path))

            with open(events_csv_path, newline="", encoding="utf-8") as handle:
                rows = list(csv.reader(handle))
            self.assertIn("event_time", rows[0])
            self.assertEqual(len(rows), 2)

            exit_code = export_blinks.main(
                [
                    "--db-path",
                    db_path,
                    "--output-dir",
                    tmp_dir,
                    "--format",
                    "json",
                    "--table",
                    "aggregates",
                ]
            )
            self.assertEqual(exit_code, 0)

            aggregates_json_path = os.path.join(tmp_dir, "blink_aggregates.json")
            with open(aggregates_json_path, encoding="utf-8") as handle:
                payload = json.load(handle)
            self.assertEqual(len(payload), 1)
            self.assertEqual(payload[0]["interval_type"], "minute")


if __name__ == "__main__":
    unittest.main()
