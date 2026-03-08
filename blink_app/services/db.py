import os
import sqlite3
from datetime import datetime

DEFAULT_DB_FILENAME = "blinks.db"


def format_db_timestamp(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")


def resolve_db_path(output_dir: str, db_path_arg: str | None) -> str:
    if db_path_arg:
        db_path = os.path.abspath(db_path_arg)
    else:
        db_path = os.path.join(output_dir, DEFAULT_DB_FILENAME)

    if os.path.isdir(db_path):
        raise IsADirectoryError(f"Database path is a directory: {db_path}")

    db_parent = os.path.dirname(db_path)
    if db_parent:
        os.makedirs(db_parent, exist_ok=True)

    return db_path


def init_db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")

    with conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS blink_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_time TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS blink_aggregates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                interval_type TEXT NOT NULL,
                interval_start TEXT NOT NULL,
                interval_end TEXT NOT NULL,
                blink_count INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(interval_type, interval_start)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_blink_events_time ON blink_events(event_time)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_blink_aggregates_type_start ON blink_aggregates(interval_type, interval_start)"
        )

    return conn


def record_blink_event(conn: sqlite3.Connection, event_time: datetime) -> None:
    with conn:
        conn.execute(
            "INSERT INTO blink_events (event_time) VALUES (?)",
            (format_db_timestamp(event_time),),
        )


def count_blinks_in_range(conn: sqlite3.Connection, start: datetime, end: datetime) -> int:
    cursor = conn.execute(
        "SELECT COUNT(*) FROM blink_events WHERE event_time >= ? AND event_time <= ?",
        (
            format_db_timestamp(start),
            format_db_timestamp(end),
        ),
    )
    row = cursor.fetchone()
    return int(row[0]) if row else 0


def record_aggregate(
    conn: sqlite3.Connection,
    interval_type: str,
    start: datetime,
    end: datetime,
    blink_count: int,
) -> None:
    with conn:
        conn.execute(
            """
            INSERT INTO blink_aggregates (
                interval_type,
                interval_start,
                interval_end,
                blink_count
            )
            VALUES (?, ?, ?, ?)
            ON CONFLICT(interval_type, interval_start)
            DO UPDATE SET blink_count = excluded.blink_count, interval_end = excluded.interval_end
            """,
            (
                interval_type,
                format_db_timestamp(start),
                format_db_timestamp(end),
                blink_count,
            ),
        )


def fetch_recent_aggregates(
    conn: sqlite3.Connection,
    interval_type: str,
    limit: int,
) -> list[tuple[str, int]]:
    safe_limit = max(0, int(limit))
    if safe_limit == 0:
        return []

    cursor = conn.execute(
        """
        SELECT interval_start, blink_count
        FROM blink_aggregates
        WHERE interval_type = ?
        ORDER BY interval_start DESC
        LIMIT ?
        """,
        (interval_type, safe_limit),
    )
    rows = cursor.fetchall()
    return [(str(interval_start), int(blink_count)) for interval_start, blink_count in rows]
