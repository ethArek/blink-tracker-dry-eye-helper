import json
import os
import sqlite3
import unittest
from unittest.mock import mock_open, patch

import export_blinks


class ExportBlinksTest(unittest.TestCase):
    def test_export_table_routes_csv_exports(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE blink_events (id INTEGER, event_time TEXT)")
        conn.execute("INSERT INTO blink_events (id, event_time) VALUES (?, ?)", (1, "2024-01-01 12:00:00"))

        with patch("export_blinks.export_rows_to_csv") as export_csv_mock:
            export_blinks.export_table(conn, "blink_events", "C:\\virtual-output", "csv")

        self.assertEqual(export_csv_mock.call_count, 1)
        self.assertEqual(
            export_csv_mock.call_args.args[0],
            os.path.join("C:\\virtual-output", "blink_events.csv"),
        )
        self.assertEqual(export_csv_mock.call_args.args[1], ["id", "event_time"])
        self.assertEqual(list(export_csv_mock.call_args.args[2]), [(1, "2024-01-01 12:00:00")])

    def test_export_table_routes_json_exports(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE blink_aggregates (id INTEGER, blink_count INTEGER)")
        conn.execute("INSERT INTO blink_aggregates (id, blink_count) VALUES (?, ?)", (1, 4))

        with patch("export_blinks.export_rows_to_json") as export_json_mock:
            export_blinks.export_table(conn, "blink_aggregates", "C:\\virtual-output", "json")

        self.assertEqual(export_json_mock.call_count, 1)
        self.assertEqual(
            export_json_mock.call_args.args[0],
            os.path.join("C:\\virtual-output", "blink_aggregates.json"),
        )
        self.assertEqual(export_json_mock.call_args.args[1], ["id", "blink_count"])
        self.assertEqual(list(export_json_mock.call_args.args[2]), [(1, 4)])

    def test_export_rows_to_csv_writes_headers_and_rows(self) -> None:
        handle = mock_open()
        with patch("export_blinks.open", handle):
            export_blinks.export_rows_to_csv(
                "ignored.csv",
                ["id", "event_time"],
                [(1, "2024-01-01 12:00:00"), (2, "2024-01-01 12:01:00")],
            )

        written = "".join(call.args[0] for call in handle().write.call_args_list)
        self.assertIn("id,event_time", written)
        self.assertIn("1,2024-01-01 12:00:00", written)
        self.assertIn("2,2024-01-01 12:01:00", written)

    def test_export_rows_to_json_writes_json_array(self) -> None:
        handle = mock_open()
        with patch("export_blinks.open", handle):
            export_blinks.export_rows_to_json(
                "ignored.json",
                ["id", "interval_type"],
                [(1, "minute"), (2, "hour")],
            )

        written = "".join(call.args[0] for call in handle().write.call_args_list)
        payload = json.loads(written)
        self.assertEqual(
            payload,
            [
                {"id": 1, "interval_type": "minute"},
                {"id": 2, "interval_type": "hour"},
            ],
        )

    def test_main_fails_when_database_file_is_missing(self) -> None:
        with patch("export_blinks.os.makedirs") as makedirs_mock:
            with patch("export_blinks.os.path.exists", return_value=False):
                with self.assertRaises(FileNotFoundError):
                    export_blinks.main(
                        [
                            "--db-path",
                            "C:\\virtual-output\\missing.db",
                            "--output-dir",
                            "C:\\virtual-output",
                        ]
                    )

        makedirs_mock.assert_called_once_with("C:\\virtual-output", exist_ok=True)

    def test_main_exports_selected_tables(self) -> None:
        real_connect = sqlite3.connect
        output_dir = "C:\\virtual-output"

        with patch("export_blinks.os.makedirs"):
            with patch("export_blinks.os.path.exists", return_value=True):
                with patch(
                    "export_blinks.sqlite3.connect",
                    side_effect=lambda *args, **kwargs: real_connect(":memory:", timeout=30.0),
                ):
                    with patch("export_blinks.export_table") as export_table_mock:
                        exit_code = export_blinks.main(
                            [
                                "--db-path",
                                "C:\\virtual-output\\blinks.db",
                                "--output-dir",
                                output_dir,
                                "--format",
                                "csv",
                                "--table",
                                "both",
                            ]
                        )

                        self.assertEqual(exit_code, 0)
                        self.assertEqual(
                            [call.args[1] for call in export_table_mock.call_args_list],
                            ["blink_events", "blink_aggregates"],
                        )
                        self.assertTrue(all(call.args[2] == output_dir for call in export_table_mock.call_args_list))
                        self.assertTrue(all(call.args[3] == "csv" for call in export_table_mock.call_args_list))

        with patch("export_blinks.os.makedirs"):
            with patch("export_blinks.os.path.exists", return_value=True):
                with patch(
                    "export_blinks.sqlite3.connect",
                    side_effect=lambda *args, **kwargs: real_connect(":memory:", timeout=30.0),
                ):
                    with patch("export_blinks.export_table") as export_table_mock:
                        exit_code = export_blinks.main(
                            [
                                "--db-path",
                                "C:\\virtual-output\\blinks.db",
                                "--output-dir",
                                output_dir,
                                "--format",
                                "json",
                                "--table",
                                "aggregates",
                            ]
                        )

                        self.assertEqual(exit_code, 0)
                        self.assertEqual(len(export_table_mock.call_args_list), 1)
                        self.assertEqual(export_table_mock.call_args.args[1], "blink_aggregates")
                        self.assertEqual(export_table_mock.call_args.args[2], output_dir)
                        self.assertEqual(export_table_mock.call_args.args[3], "json")


if __name__ == "__main__":
    unittest.main()
