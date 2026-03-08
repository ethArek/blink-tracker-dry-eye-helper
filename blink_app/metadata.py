"""Application metadata shared across runtime modules."""

from blink_app import __version__

APP_NAME = "Blink Tracker"
APP_EXECUTABLE_NAME = "BlinkTracker"
APP_EXECUTABLE_FILENAME = f"{APP_EXECUTABLE_NAME}.exe"
APP_WINDOWS_DATA_DIR = "BlinkTracker"
APP_POSIX_DATA_DIR = "blink-tracker"
APP_DESCRIPTION = "Blink Tracker webcam app for blink counting and dry-eye reminders"
APP_VERSION = __version__
APP_VERSION_LABEL = f"{APP_NAME} {APP_VERSION}"
