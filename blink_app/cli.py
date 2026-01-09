import argparse

from blink_app.constants import (
    ALERT_NO_BLINK_SECONDS,
    ALERT_REPEAT_SECONDS,
    EAR_CONSEC_FRAMES,
    EAR_THRESHOLD,
)


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
    parser.add_argument(
        "--alert-after-seconds",
        type=float,
        default=ALERT_NO_BLINK_SECONDS,
        help=(
            "Seconds without a blink before playing an alert "
            f"(default: {ALERT_NO_BLINK_SECONDS})."
        ),
    )
    parser.add_argument(
        "--alert-repeat-seconds",
        type=float,
        default=ALERT_REPEAT_SECONDS,
        help=(
            "Seconds to wait between alert sounds when no blink is detected "
            f"(default: {ALERT_REPEAT_SECONDS})."
        ),
    )
    parser.add_argument(
        "--enable-alerts",
        action="store_false",
        dest="disable_alerts",
        help="Enable audio alerts when no blink is detected.",
    )
    parser.set_defaults(disable_alerts=True)
    return parser.parse_args()
