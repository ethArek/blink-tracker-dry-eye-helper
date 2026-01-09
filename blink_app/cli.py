import argparse

from blink_app.constants import ALERT_SOUND, EAR_CONSEC_FRAMES, EAR_THRESHOLD


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
    return parser.parse_args()
