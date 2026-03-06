import logging
import signal
import sqlite3
import sys

from PySide6 import QtCore, QtWidgets

from blink_app.cli import parse_args
from blink_app.services.db import init_db, resolve_db_path
from blink_app.services.logging_utils import setup_logging
from blink_app.services.path_utils import resolve_runtime_output_dir
from blink_app.ui.window import BlinkWindow


def _install_signal_handlers(app: QtWidgets.QApplication) -> QtCore.QTimer:
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, lambda *_: app.quit())

    signal_timer = QtCore.QTimer()
    signal_timer.timeout.connect(lambda: None)
    signal_timer.start(250)
    return signal_timer


def main() -> int:
    args = parse_args()
    allow_output_fallback = args.output_dir == "."
    try:
        output_dir, output_dir_warning = resolve_runtime_output_dir(
            args.output_dir,
            allow_fallback=allow_output_fallback,
        )
    except OSError as exc:
        logging.basicConfig(level=logging.INFO)
        logging.getLogger("app").error(
            "Could not prepare output directory '%s': %s",
            args.output_dir,
            exc,
        )
        return 1

    app_logger, blink_logger, aggregate_logger = setup_logging(output_dir)
    if output_dir_warning is not None:
        app_logger.warning("%s", output_dir_warning)

    db_path = ""
    try:
        db_path = resolve_db_path(output_dir, args.db_path)
        db_conn = init_db(db_path)
    except (OSError, sqlite3.Error) as exc:
        app_logger.error("Could not initialize database '%s': %s", db_path or args.db_path, exc)
        return 1

    app_logger.info("Starting blink detection. Initializing camera...")

    app = QtWidgets.QApplication(sys.argv)
    signal_timer = _install_signal_handlers(app)

    try:
        window = BlinkWindow(
            args,
            output_dir,
            app_logger,
            blink_logger,
            aggregate_logger,
            db_conn,
        )
    except Exception:
        signal_timer.stop()
        db_conn.close()
        app_logger.exception("Application startup failed.")
        return 1

    window.show()
    exit_code = app.exec()
    signal_timer.stop()
    return exit_code
