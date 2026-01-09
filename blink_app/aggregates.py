import argparse
import csv
import logging
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta

from blink_app.alert import play_alert_sound
from blink_app.constants import ALERT_NO_BLINK_SECONDS, ALERT_REPEAT_SECONDS
from blink_app.db import count_blinks_in_range, record_aggregate
from blink_app.detection import BlinkState


@dataclass
class AggregateState:
    last_stats_time: float
    last_logged_minute: datetime | None = None
    last_logged_10minute: datetime | None = None
    last_logged_hour: datetime | None = None
    last_logged_day: datetime | None = None
    last_current_day_update: datetime | None = None
    last_alert_time: float = 0.0
    blinks_1m: int = 0
    blinks_10m: int = 0
    blinks_1h: int = 0
    blinks_day: int = 0


def write_csv_row(path: str, headers: list[str], row: list[object]) -> None:
    with open(path, "a", newline="") as csvfile:
        writer = csv.writer(csvfile)
        # Write headers if the file is empty (new or truncated).
        if csvfile.tell() == 0:
            writer.writerow(headers)
        writer.writerow(row)


def update_aggregates(
    args: argparse.Namespace,
    state: AggregateState,
    now_dt: datetime,
    now_ts: float,
    blink_state: BlinkState,
    db_conn: sqlite3.Connection,
    aggregate_logger,
    output_dir: str,
) -> None:
    if now_ts - state.last_stats_time < 1.0:
        return
    state.last_stats_time = now_ts

    if getattr(args, "enable_alerts", False):
        alert_after_seconds = getattr(args, "alert_after_seconds", ALERT_NO_BLINK_SECONDS)
        alert_repeat_seconds = getattr(args, "alert_repeat_seconds", ALERT_REPEAT_SECONDS)
        if (
            now_ts - blink_state.last_blink_time >= alert_after_seconds
            and now_ts - state.last_alert_time >= alert_repeat_seconds
        ):
            alert_sound = getattr(args, "alert_sound", "exclamation")
            alert_sound_file = getattr(args, "alert_sound_file", None)
            if alert_sound_file or (alert_sound and str(alert_sound).lower() != "none"):
                logging.getLogger("app").warning(
                    "No blink detected for %ds. Playing alert.",
                    int(now_ts - blink_state.last_blink_time),
                )
                play_alert_sound(sound=str(alert_sound), sound_file=alert_sound_file)
                state.last_alert_time = now_ts

    date_str = now_dt.strftime("%Y-%m-%d")

    # FULL MINUTE LOG
    current_minute = now_dt.replace(second=0, microsecond=0) - timedelta(minutes=1)
    if state.last_logged_minute != current_minute:
        minute_end = current_minute + timedelta(minutes=1) - timedelta(seconds=1)
        state.blinks_1m = count_blinks_in_range(db_conn, current_minute, minute_end)
        aggregate_logger.info(
            "minute_interval start=%s blinks=%d",
            current_minute.strftime("%Y-%m-%d %H:%M:%S"),
            state.blinks_1m,
        )
        record_aggregate(db_conn, "minute", current_minute, minute_end, state.blinks_1m)
        if args.csv_output:
            write_csv_row(
                os.path.join(output_dir, "blinks_per_minute.csv"),
                ["date", "interval_start", "blinks"],
                [date_str, current_minute.strftime("%H:%M:%S"), state.blinks_1m],
            )
        state.last_logged_minute = current_minute

    # FULL 10-MINUTE LOG
    minute_mod = now_dt.minute % 10
    current_10minute = now_dt.replace(
        minute=now_dt.minute - minute_mod,
        second=0,
        microsecond=0,
    ) - timedelta(minutes=10)
    if state.last_logged_10minute != current_10minute:
        ten_minute_end = current_10minute + timedelta(minutes=10) - timedelta(seconds=1)
        state.blinks_10m = count_blinks_in_range(db_conn, current_10minute, ten_minute_end)
        aggregate_logger.info(
            "ten_minute_interval start=%s blinks=%d",
            current_10minute.strftime("%Y-%m-%d %H:%M:%S"),
            state.blinks_10m,
        )
        record_aggregate(
            db_conn,
            "ten_minute",
            current_10minute,
            ten_minute_end,
            state.blinks_10m,
        )
        if args.csv_output:
            write_csv_row(
                os.path.join(output_dir, "blinks_per_10_minutes.csv"),
                ["date", "interval_start", "blinks"],
                [date_str, current_10minute.strftime("%H:%M:%S"), state.blinks_10m],
            )
        state.last_logged_10minute = current_10minute

    # FULL HOUR LOG
    current_hour = now_dt.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
    if state.last_logged_hour != current_hour:
        hour_end = current_hour + timedelta(hours=1) - timedelta(seconds=1)
        state.blinks_1h = count_blinks_in_range(db_conn, current_hour, hour_end)
        aggregate_logger.info(
            "hour_interval start=%s blinks=%d",
            current_hour.strftime("%Y-%m-%d %H:%M:%S"),
            state.blinks_1h,
        )
        record_aggregate(db_conn, "hour", current_hour, hour_end, state.blinks_1h)
        if args.csv_output:
            write_csv_row(
                os.path.join(output_dir, "blinks_per_hour.csv"),
                ["date", "interval_start", "blinks"],
                [date_str, current_hour.strftime("%H:%M:%S"), state.blinks_1h],
            )
        state.last_logged_hour = current_hour

    # DAILY LOG (aggregate previous full day, show current day total)
    current_day_start = now_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    previous_day_start = current_day_start - timedelta(days=1)
    if state.last_logged_day != previous_day_start:
        previous_day_end = current_day_start - timedelta(seconds=1)
        previous_day_total = count_blinks_in_range(
            db_conn,
            previous_day_start,
            previous_day_end,
        )
        aggregate_logger.info(
            "day_interval start=%s blinks=%d",
            previous_day_start.strftime("%Y-%m-%d %H:%M:%S"),
            previous_day_total,
        )
        record_aggregate(
            db_conn,
            "day",
            previous_day_start,
            previous_day_end,
            previous_day_total,
        )
        state.last_logged_day = previous_day_start

    # Update current day total every minute to avoid excessive DB queries and CSV writes
    current_minute_for_day = now_dt.replace(second=0, microsecond=0)
    if state.last_current_day_update != current_minute_for_day:
        state.blinks_day = count_blinks_in_range(
            db_conn,
            current_day_start,
            now_dt,
        )
        aggregate_logger.info("daily_total date=%s blinks=%d", date_str, state.blinks_day)
        if args.csv_output:
            write_csv_row(
                os.path.join(output_dir, "blinks_per_day.csv"),
                ["date", "blinks"],
                [date_str, state.blinks_day],
            )
        state.last_current_day_update = current_minute_for_day
