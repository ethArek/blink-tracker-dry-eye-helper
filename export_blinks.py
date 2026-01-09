import argparse
import csv
import json
import os
import sqlite3
from typing import Iterable


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export blink data from SQLite.")
    parser.add_argument(
        "--db-path",
        default=None,
        help="Path to SQLite database (default: <output-dir>/blinks.db).",
    )
    parser.add_argument(
        "--output-dir",
        default=".",
        help="Directory for export files (default: current directory).",
    )
    parser.add_argument(
        "--format",
        choices=("csv", "json"),
        default="csv",
        help="Export format (default: csv).",
    )
    parser.add_argument(
        "--table",
        choices=("events", "aggregates", "both"),
        default="both",
        help="Which table(s) to export (default: both).",
    )
    return parser.parse_args()


def export_rows_to_csv(path: str, headers: Iterable[str], rows: Iterable[tuple]) -> None:
    with open(path, "w", newline="") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(headers)
        writer.writerows(rows)


def export_rows_to_json(path: str, headers: Iterable[str], rows: Iterable[tuple]) -> None:
    payload = [dict(zip(headers, row)) for row in rows]
    with open(path, "w") as jsonfile:
        json.dump(payload, jsonfile, indent=2)


def export_table(
    conn: sqlite3.Connection,
    table_name: str,
    output_dir: str,
    fmt: str,
) -> None:
    cursor = conn.execute(f"SELECT * FROM {table_name} ORDER BY id ASC")
    rows = cursor.fetchall()
    headers = [col[0] for col in cursor.description]
    filename = f"{table_name}.{fmt}"
    path = os.path.join(output_dir, filename)
    if fmt == "csv":
        export_rows_to_csv(path, headers, rows)
    else:
        export_rows_to_json(path, headers, rows)


def main() -> None:
    args = parse_args()
    os.makedirs(args.output_dir, exist_ok=True)
    db_path = args.db_path or os.path.join(args.output_dir, "blinks.db")
    conn = sqlite3.connect(db_path)
    try:
        tables = {
            "events": "blink_events",
            "aggregates": "blink_aggregates",
        }
        if args.table == "both":
            selected_tables = list(tables.values())
        else:
            selected_tables = [tables[args.table]]
        for table_name in selected_tables:
            export_table(conn, table_name, args.output_dir, args.format)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
