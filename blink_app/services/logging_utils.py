import logging
import logging.handlers
import os
from collections.abc import Iterable


def setup_logging(output_dir: str) -> tuple[logging.Logger, logging.Logger, logging.Logger]:
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    app_handler = logging.handlers.RotatingFileHandler(
        os.path.join(output_dir, "app.log"),
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    blink_handler = logging.handlers.RotatingFileHandler(
        os.path.join(output_dir, "blink_events.log"),
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    aggregate_handler = logging.handlers.RotatingFileHandler(
        os.path.join(output_dir, "aggregate_metrics.log"),
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )

    app_handler.setFormatter(formatter)
    blink_handler.setFormatter(formatter)
    aggregate_handler.setFormatter(formatter)

    app_logger = _configure_logger(
        "app",
        (app_handler, _build_console_handler(formatter)),
    )
    blink_logger = _configure_logger(
        "blink_events",
        (blink_handler, _build_console_handler(formatter)),
    )
    aggregate_logger = _configure_logger(
        "aggregate_metrics",
        (aggregate_handler, _build_console_handler(formatter)),
    )

    return app_logger, blink_logger, aggregate_logger


def _configure_logger(name: str, handlers: Iterable[logging.Handler]) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    for existing_handler in list(logger.handlers):
        logger.removeHandler(existing_handler)
        existing_handler.close()

    for handler in handlers:
        logger.addHandler(handler)

    return logger


def _build_console_handler(formatter: logging.Formatter) -> logging.StreamHandler:
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    return handler
