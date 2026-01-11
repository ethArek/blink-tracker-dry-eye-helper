import sqlite3
from datetime import datetime


def init_db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
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
    conn.commit()
    return conn


def record_blink_event(conn: sqlite3.Connection, event_time: datetime) -> None:
    conn.execute(
        "INSERT INTO blink_events (event_time) VALUES (?)",
        (event_time.strftime("%Y-%m-%d %H:%M:%S"),),
    )
    conn.commit()


def count_blinks_in_range(conn: sqlite3.Connection, start: datetime, end: datetime) -> int:
    cursor = conn.execute(
        "SELECT COUNT(*) FROM blink_events WHERE event_time >= ? AND event_time <= ?",
        (
            start.strftime("%Y-%m-%d %H:%M:%S"),
            end.strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )
    row = cursor.fetchone()
    return row[0] if row else 0


def record_aggregate(
    conn: sqlite3.Connection,
    interval_type: str,
    start: datetime,
    end: datetime,
    blink_count: int,
) -> None:
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
            start.strftime("%Y-%m-%d %H:%M:%S"),
            end.strftime("%Y-%m-%d %H:%M:%S"),
            blink_count,
        ),
    )
    conn.commit()
