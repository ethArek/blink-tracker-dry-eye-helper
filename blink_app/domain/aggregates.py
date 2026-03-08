import argparse
import csv
import logging
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta

from blink_app.constants import ALERT_NO_BLINK_SECONDS, ALERT_REPEAT_SECONDS
from blink_app.domain.detection import BlinkState
from blink_app.services.alert import play_alert_sound
from blink_app.services.db import count_blinks_in_range, record_aggregate


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


@dataclass(frozen=True, slots=True)
class CompletedInterval:
    state_attr: str
    logged_attr: str
    interval_type: str
    log_label: str
    csv_filename: str
    interval_start: datetime
    interval_end: datetime
    csv_row: tuple[object, ...]


def write_csv_row(path: str, headers: list[str], row: list[object]) -> None:
    with open(path, "a", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        if csvfile.tell() == 0:
            writer.writerow(headers)
        writer.writerow(row)


def _maybe_play_alert(
    args: argparse.Namespace,
    state: AggregateState,
    now_ts: float,
    blink_state: BlinkState,
) -> None:
    if not getattr(args, "enable_alerts", False):
        return

    alert_after_seconds = max(
        0.1,
        float(getattr(args, "alert_after_seconds", ALERT_NO_BLINK_SECONDS)),
    )
    alert_repeat_seconds = max(
        1.0,
        float(getattr(args, "alert_repeat_seconds", ALERT_REPEAT_SECONDS)),
    )
    if (
        now_ts - blink_state.last_blink_time < alert_after_seconds
        or now_ts - state.last_alert_time < alert_repeat_seconds
    ):
        return

    alert_sound = getattr(args, "alert_sound", "exclamation")
    alert_sound_file = getattr(args, "alert_sound_file", None)
    if not alert_sound_file and (not alert_sound or str(alert_sound).lower() == "none"):
        return

    logging.getLogger("app").warning(
        "No blink detected for %ds. Playing alert.",
        int(now_ts - blink_state.last_blink_time),
    )
    play_alert_sound(sound=str(alert_sound), sound_file=alert_sound_file)
    state.last_alert_time = now_ts


def _record_completed_interval(
    aggregate_logger: logging.Logger,
    db_conn: sqlite3.Connection,
    interval_type: str,
    log_label: str,
    interval_start: datetime,
    interval_end: datetime,
    blink_count: int,
) -> None:
    aggregate_logger.info(
        "%s start=%s blinks=%d",
        log_label,
        interval_start.strftime("%Y-%m-%d %H:%M:%S"),
        blink_count,
    )
    record_aggregate(db_conn, interval_type, interval_start, interval_end, blink_count)


def _completed_intervals(now_dt: datetime, date_str: str) -> list[CompletedInterval]:
    current_minute = now_dt.replace(second=0, microsecond=0) - timedelta(minutes=1)
    minute_end = current_minute + timedelta(minutes=1) - timedelta(seconds=1)

    minute_mod = now_dt.minute % 10
    current_10minute = now_dt.replace(
        minute=now_dt.minute - minute_mod,
        second=0,
        microsecond=0,
    ) - timedelta(minutes=10)
    ten_minute_end = current_10minute + timedelta(minutes=10) - timedelta(seconds=1)

    current_hour = now_dt.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
    hour_end = current_hour + timedelta(hours=1) - timedelta(seconds=1)

    return [
        CompletedInterval(
            state_attr="blinks_1m",
            logged_attr="last_logged_minute",
            interval_type="minute",
            log_label="minute_interval",
            csv_filename="blinks_per_minute.csv",
            interval_start=current_minute,
            interval_end=minute_end,
            csv_row=(date_str, current_minute.strftime("%H:%M:%S"), 0),
        ),
        CompletedInterval(
            state_attr="blinks_10m",
            logged_attr="last_logged_10minute",
            interval_type="ten_minute",
            log_label="ten_minute_interval",
            csv_filename="blinks_per_10_minutes.csv",
            interval_start=current_10minute,
            interval_end=ten_minute_end,
            csv_row=(date_str, current_10minute.strftime("%H:%M:%S"), 0),
        ),
        CompletedInterval(
            state_attr="blinks_1h",
            logged_attr="last_logged_hour",
            interval_type="hour",
            log_label="hour_interval",
            csv_filename="blinks_per_hour.csv",
            interval_start=current_hour,
            interval_end=hour_end,
            csv_row=(date_str, current_hour.strftime("%H:%M:%S"), 0),
        ),
    ]


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

    _maybe_play_alert(args, state, now_ts, blink_state)

    date_str = now_dt.strftime("%Y-%m-%d")
    csv_headers = ["date", "interval_start", "blinks"]
    for interval in _completed_intervals(now_dt, date_str):
        if getattr(state, interval.logged_attr) == interval.interval_start:
            continue

        blink_count = count_blinks_in_range(db_conn, interval.interval_start, interval.interval_end)
        setattr(state, interval.state_attr, blink_count)
        _record_completed_interval(
            aggregate_logger,
            db_conn,
            interval.interval_type,
            interval.log_label,
            interval.interval_start,
            interval.interval_end,
            blink_count,
        )
        if args.csv_output:
            csv_row = list(interval.csv_row[:-1]) + [blink_count]
            write_csv_row(
                os.path.join(output_dir, interval.csv_filename),
                csv_headers,
                csv_row,
            )
        setattr(state, interval.logged_attr, interval.interval_start)

    current_day_start = now_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    previous_day_start = current_day_start - timedelta(days=1)
    if state.last_logged_day != previous_day_start:
        previous_day_end = current_day_start - timedelta(seconds=1)
        previous_day_total = count_blinks_in_range(
            db_conn,
            previous_day_start,
            previous_day_end,
        )
        _record_completed_interval(
            aggregate_logger,
            db_conn,
            "day",
            "day_interval",
            previous_day_start,
            previous_day_end,
            previous_day_total,
        )
        state.last_logged_day = previous_day_start

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
