import argparse

from blink_app import __version__
from blink_app.constants import (
    ALERT_NO_BLINK_SECONDS,
    ALERT_REPEAT_SECONDS,
    ALERT_SOUND,
    CAMERA_STARTUP_TIMEOUT_SECONDS,
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


def positive_int(value: str) -> int:
    try:
        ivalue = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Invalid integer value: {value}") from exc
    if ivalue <= 0:
        raise argparse.ArgumentTypeError("Value must be a positive integer.")
    return ivalue


def positive_float(value: str) -> float:
    try:
        fvalue = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Invalid float value: {value}") from exc
    if fvalue <= 0:
        raise argparse.ArgumentTypeError("Value must be a positive number.")
    return fvalue


def ear_threshold_value(value: str) -> float:
    fvalue = positive_float(value)
    if fvalue > 1.0:
        raise argparse.ArgumentTypeError("EAR threshold must be <= 1.0.")
    return fvalue


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Detect blinks and log blink counts.")
    parser.add_argument(
        "--version",
        action="version",
        version=f"Blink Tracker {__version__}",
    )
    parser.add_argument(
        "--camera-index",
        type=non_negative_int,
        default=0,
        help="Camera index to open (must be a non-negative integer, default: 0).",
    )
    parser.add_argument(
        "--ear-threshold",
        type=ear_threshold_value,
        default=EAR_THRESHOLD,
        help=f"EAR threshold for blink detection in (0.0, 1.0] (default: {EAR_THRESHOLD}).",
    )
    parser.add_argument(
        "--ear-consec-frames",
        type=positive_int,
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
        type=positive_float,
        default=None,
        help="Requested capture FPS (default: camera default).",
    )
    parser.add_argument(
        "--camera-startup-timeout-seconds",
        type=positive_float,
        default=CAMERA_STARTUP_TIMEOUT_SECONDS,
        help=(
            "Seconds to wait for first camera frame per backend during startup "
            f"(default: {CAMERA_STARTUP_TIMEOUT_SECONDS})."
        ),
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
        "--alert-sound",
        choices=(
            "exclamation",
            "asterisk",
            "hand",
            "question",
            "beep",
            "glass",
            "ping",
            "pop",
            "basso",
            "tink",
            "submarine",
            "none",
        ),
        default=ALERT_SOUND,
        help=(
            "Alert sound to play when no blinks are detected for the configured interval "
            f"(default: {ALERT_SOUND}). Use 'none' to disable."
        ),
    )
    parser.add_argument(
        "--alert-sound-file",
        default=None,
        help=(
            "Path to a custom sound file (WAV/AIFF, best-effort) to play for alerts; "
            "overrides --alert-sound."
        ),
    )
    parser.add_argument(
        "--alert-after-seconds",
        type=positive_float,
        default=ALERT_NO_BLINK_SECONDS,
        help=(
            "Seconds without a blink before playing an alert "
            f"(default: {ALERT_NO_BLINK_SECONDS})."
        ),
    )
    parser.add_argument(
        "--alert-repeat-seconds",
        type=positive_float,
        default=ALERT_REPEAT_SECONDS,
        help=(
            "Seconds to wait between alert sounds when no blink is detected "
            f"(default: {ALERT_REPEAT_SECONDS})."
        ),
    )
    alert_group = parser.add_mutually_exclusive_group()
    alert_group.add_argument(
        "--enable-alerts",
        action="store_true",
        dest="enable_alerts",
        help="Enable audio alerts when no blink is detected.",
    )
    alert_group.add_argument(
        "--disable-alerts",
        action="store_false",
        dest="enable_alerts",
        help="Disable audio alerts when no blink is detected.",
    )
    parser.set_defaults(enable_alerts=False)
    return parser.parse_args(argv)
