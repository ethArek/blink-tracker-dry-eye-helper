import argparse
import csv
import cv2
import logging
import logging.handlers
import mediapipe as mp
import math
import os
import platform
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta

# EAR - Eye Aspect Ratio
def eye_aspect_ratio(landmarks, eye_indices):
    def euclidean(p1, p2):
        return math.dist(p1, p2)
    
    p = [landmarks[i] for i in eye_indices]
    A = euclidean(p[1], p[5])
    B = euclidean(p[2], p[4])
    C = euclidean(p[0], p[3])
    ear = (A + B) / (2.0 * C)
    return ear

# Eye landmark indices (MediaPipe)
LEFT_EYE = [33, 160, 158, 133, 153, 144]
RIGHT_EYE = [362, 385, 387, 263, 373, 380]

# Thresholds
EAR_THRESHOLD = 0.21
EAR_CONSEC_FRAMES = 3
ALERT_NO_BLINK_SECONDS = 30
ALERT_REPEAT_SECONDS = 30

frame_counter = 0
blink_counter = 0
def non_negative_int(value: str) -> int:
    try:
        ivalue = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Invalid integer value: {value}") from exc
    if ivalue < 0:
        raise argparse.ArgumentTypeError("Camera index must be a non-negative integer.")
    return ivalue

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Detect blinks and log blink counts.")
    parser.add_argument(
        "--camera-index",
        type=non_negative_int,
        default=0,
        help="Camera index to open (must be a non-negative integer, default: 0).",
    )
    parser.add_argument(
        "--ear-threshold",
        type=float,
        default=EAR_THRESHOLD,
        help=f"EAR threshold for blink detection (default: {EAR_THRESHOLD}).",
    )
    parser.add_argument(
        "--ear-consec-frames",
        type=int,
        default=EAR_CONSEC_FRAMES,
        help=f"Consecutive frames below threshold to count a blink (default: {EAR_CONSEC_FRAMES}).",
    )
    parser.add_argument(
        "--output-dir",
        default=".",
        help="Directory to store blink logs (default: current directory).",
    )
    parser.add_argument(
        "--fps",
        type=float,
        default=None,
        help="Requested capture FPS (default: camera default).",
    )
    parser.add_argument(
        "--csv-output",
        action="store_true",
        help="Enable CSV export for blink metrics (default: disabled).",
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help="Path to SQLite database for blink events (default: <output-dir>/blinks.db).",
    )
    return parser.parse_args()

# Play a sound alert when no blink is detected for a while
def play_alert_sound():
    """
    Play an alert sound asynchronously using a best-effort, platform-specific backend.

    The sound is played in a separate daemon thread so that calls to this function
    are non-blocking and do not interrupt the main video-processing loop.

    Platform behavior:
      * Windows: use ``winsound.Beep`` if available.
      * macOS (Darwin): use ``afplay`` to play the system ``Glass.aiff`` sound if
        the command and sound file are present.
      * Linux/other Unix-like systems:
          - Prefer ``paplay`` (PulseAudio) with common freedesktop sound files, if
            both the command and at least one sound file exist.
          - Otherwise, try ``aplay`` (ALSA) with a common system sound file.

    If no platform-specific method succeeds, the function falls back to writing the
    ASCII bell character (``\\a``) to standard output to trigger a terminal beep
    when supported.
    """
    def _play():
        if platform.system() == "Windows":
            try:
                import winsound
                winsound.Beep(1000, 500)
                return
            except Exception:
                pass

        if platform.system() == "Darwin":
            mac_sound = "/System/Library/Sounds/Glass.aiff"
            if shutil.which("afplay") and os.path.exists(mac_sound):
                subprocess.Popen(
                    ["afplay", mac_sound],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return

        if shutil.which("paplay"):
            for sound_path in (
                "/usr/share/sounds/freedesktop/stereo/alarm-clock-elapsed.oga",
                "/usr/share/sounds/freedesktop/stereo/complete.oga",
            ):
                if os.path.exists(sound_path):
                    subprocess.Popen(
                        ["paplay", sound_path],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    return

        if shutil.which("aplay"):
            for sound_path in ("/usr/share/sounds/alsa/Front_Center.wav",):
                if os.path.exists(sound_path):
                    subprocess.Popen(
                        ["aplay", sound_path],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    return

        sys.stdout.write("\a")
        sys.stdout.flush()

    threading.Thread(target=_play, daemon=True).start()

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

args = parse_args()
EAR_THRESHOLD = args.ear_threshold
EAR_CONSEC_FRAMES = args.ear_consec_frames

output_dir = args.output_dir
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
app_logger = logging.getLogger("app")
try:
    os.makedirs(output_dir, exist_ok=True)
except OSError as e:
    app_logger.error("Could not create output directory '%s': %s", output_dir, e)
    sys.exit(1)

def output_path(filename: str) -> str:
    return os.path.join(output_dir, filename)

def setup_logging() -> tuple[logging.Logger, logging.Logger]:
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    blink_handler = logging.handlers.RotatingFileHandler(
        output_path("blink_events.log"),
        maxBytes=1_000_000,
        backupCount=3,
    )
    blink_handler.setFormatter(formatter)
    blink_logger = logging.getLogger("blink_events")
    blink_logger.setLevel(logging.INFO)
    blink_logger.addHandler(blink_handler)
    blink_logger.propagate = False

    aggregate_handler = logging.handlers.RotatingFileHandler(
        output_path("aggregate_metrics.log"),
        maxBytes=1_000_000,
        backupCount=3,
    )
    aggregate_handler.setFormatter(formatter)
    aggregate_logger = logging.getLogger("aggregate_metrics")
    aggregate_logger.setLevel(logging.INFO)
    aggregate_logger.addHandler(aggregate_handler)
    aggregate_logger.propagate = False

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    app_logger.setLevel(logging.INFO)
    app_logger.propagate = False
    # Ensure there is exactly one console StreamHandler attached to app_logger
    app_logger.handlers = [
        h for h in app_logger.handlers
        if not isinstance(h, logging.StreamHandler)
    ]
    app_logger.addHandler(console_handler)
    return blink_logger, aggregate_logger

def write_csv_row(path: str, headers: list[str], row: list[object]) -> None:
    with open(path, "a", newline="") as csvfile:
        writer = csv.writer(csvfile)
        # Write headers if the file is empty (new or truncated).
        if csvfile.tell() == 0:
            writer.writerow(headers)
        writer.writerow(row)

blink_logger, aggregate_logger = setup_logging()
db_path = args.db_path or output_path("blinks.db")
db_conn = init_db(db_path)

# Init mediapipe
mp_face_mesh = mp.solutions.face_mesh
face_mesh = mp_face_mesh.FaceMesh(static_image_mode=False, max_num_faces=1, refine_landmarks=True)

# Init camera
cap = cv2.VideoCapture(args.camera_index)
if not cap.isOpened():
    app_logger.error("Cannot open camera.")
    sys.exit(1)
if args.fps is not None:
    cap.set(cv2.CAP_PROP_FPS, args.fps)

app_logger.info("Camera started. Press ESC or Ctrl+C to exit.")

# Time trackers
last_stats_time = time.time()
last_logged_minute = None
last_logged_10minute = None
last_logged_hour = None
last_logged_day = None
# NOTE: These time-tracking variables are written from the main thread only.
# Background threads may read them, and we currently rely on CPython's GIL and
# simple float assignments being effectively atomic. If more complex, compound
# operations are added in the future, protect access with a threading.Lock or
# another explicit synchronization mechanism.
last_blink_time = time.time()
last_alert_time = 0.0

# Values to show on screen
blinks_1m = 0
blinks_10m = 0
blinks_1h = 0
blinks_day = 0



try:
    while True:
        ret, frame = cap.read()
        if not ret:
            app_logger.warning("Failed to read frame.")
            break

        h, w = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = face_mesh.process(rgb)
        now_dt = datetime.now()
        now_ts = time.time()

        date_str = now_dt.strftime("%Y-%m-%d")


        if results.multi_face_landmarks:
            for face_landmarks in results.multi_face_landmarks:
                landmarks = [(lm.x * w, lm.y * h) for lm in face_landmarks.landmark]

                left_ear = eye_aspect_ratio(landmarks, LEFT_EYE)
                right_ear = eye_aspect_ratio(landmarks, RIGHT_EYE)
                ear = (left_ear + right_ear) / 2.0

                if ear < EAR_THRESHOLD:
                    frame_counter += 1
                else:
                    if frame_counter >= EAR_CONSEC_FRAMES:
                        blink_counter += 1
                        last_blink_time = now_ts
                        blink_logger.info("Blink #%d", blink_counter)
                        record_blink_event(db_conn, now_dt)
                    frame_counter = 0

        # Every second: check if it's time to log full intervals
        if time.time() - last_stats_time >= 1.0:
            last_stats_time = time.time()

            if (
                now_ts - last_blink_time >= ALERT_NO_BLINK_SECONDS
                and now_ts - last_alert_time >= ALERT_REPEAT_SECONDS
            ):
                play_alert_sound()
                last_alert_time = now_ts

            # FULL MINUTE LOG
            current_minute = now_dt.replace(second=0, microsecond=0) - timedelta(minutes=1)
            if last_logged_minute != current_minute:
                minute_end = current_minute + timedelta(minutes=1) - timedelta(seconds=1)
                blinks_1m = count_blinks_in_range(db_conn, current_minute, minute_end)
                aggregate_logger.info(
                    "minute_interval start=%s blinks=%d",
                    current_minute.strftime("%Y-%m-%d %H:%M:%S"),
                    blinks_1m,
                )
                record_aggregate(db_conn, "minute", current_minute, minute_end, blinks_1m)
                if args.csv_output:
                    write_csv_row(
                        output_path("blinks_per_minute.csv"),
                        ["date", "interval_start", "blinks"],
                        [date_str, current_minute.strftime("%H:%M:%S"), blinks_1m],
                    )
                last_logged_minute = current_minute

            # FULL 10-MINUTE LOG
            minute_mod = now_dt.minute % 10
            current_10minute = now_dt.replace(minute=now_dt.minute - minute_mod, second=0, microsecond=0) - timedelta(minutes=10)
            if last_logged_10minute != current_10minute:
                ten_minute_end = current_10minute + timedelta(minutes=10) - timedelta(seconds=1)
                blinks_10m = count_blinks_in_range(db_conn, current_10minute, ten_minute_end)
                aggregate_logger.info(
                    "ten_minute_interval start=%s blinks=%d",
                    current_10minute.strftime("%Y-%m-%d %H:%M:%S"),
                    blinks_10m,
                )
                record_aggregate(db_conn, "ten_minute", current_10minute, ten_minute_end, blinks_10m)
                if args.csv_output:
                    write_csv_row(
                        output_path("blinks_per_10_minutes.csv"),
                        ["date", "interval_start", "blinks"],
                        [date_str, current_10minute.strftime("%H:%M:%S"), blinks_10m],
                    )
                last_logged_10minute = current_10minute

            # FULL HOUR LOG
            current_hour = now_dt.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
            if last_logged_hour != current_hour:
                hour_end = current_hour + timedelta(hours=1) - timedelta(seconds=1)
                blinks_1h = count_blinks_in_range(db_conn, current_hour, hour_end)
                aggregate_logger.info(
                    "hour_interval start=%s blinks=%d",
                    current_hour.strftime("%Y-%m-%d %H:%M:%S"),
                    blinks_1h,
                )
                record_aggregate(db_conn, "hour", current_hour, hour_end, blinks_1h)
                if args.csv_output:
                    write_csv_row(
                        output_path("blinks_per_hour.csv"),
                        ["date", "interval_start", "blinks"],
                        [date_str, current_hour.strftime("%H:%M:%S"), blinks_1h],
                    )
                last_logged_hour = current_hour

            # DAILY LOG (aggregate previous full day, show current day total)
            current_day_start = now_dt.replace(hour=0, minute=0, second=0, microsecond=0)
            previous_day_start = current_day_start - timedelta(days=1)
            if last_logged_day != previous_day_start:
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
                last_logged_day = previous_day_start

            blinks_day = count_blinks_in_range(
                db_conn,
                current_day_start,
                now_dt,
            )
            aggregate_logger.info("daily_total date=%s blinks=%d", date_str, blinks_day)
            if args.csv_output:
                write_csv_row(
                    output_path("blinks_per_day.csv"),
                    ["date", "blinks"],
                    [date_str, blinks_day],
                )

        # Display info on camera frame
        cv2.putText(frame, "Blinks (full intervals):", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.putText(frame, f"  min:   {blinks_1m}", (10, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.putText(frame, f"  10min: {blinks_10m}", (10, 90),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.putText(frame, f"  hour:  {blinks_1h}", (10, 120),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        cv2.imshow("Blink detection", frame)
        if cv2.waitKey(1) & 0xFF == 27:
            break

except KeyboardInterrupt:
    app_logger.info("Stopped by Ctrl+C")

finally:
    db_conn.close()
    cap.release()
    cv2.destroyAllWindows()
    app_logger.info("Camera and windows closed. Goodbye!")
